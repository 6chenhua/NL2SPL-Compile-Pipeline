"""Worker-scoped methods for Stage 9.5 IRNormalizer."""

from __future__ import annotations

from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerStepPlanIR,
)


class WorkerScopedMixin:
    """Mixin class containing worker-scoped methods for IRNormalizer."""

    def normalize_worker_scoped(
        self,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        worker_step_plan: WorkerStepPlanIR,
        worker_plan: WorkerPlanIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
    ) -> tuple[
        WorkerFlowPlanIR,
        WorkerBlockPlanIR,
        WorkerStepPlanIR,
        SymbolTable,
        list[str],  # errors
        list[str],  # warnings
    ]:
        """Normalize and validate worker-scoped IRs.

        校验内容（D5: span ownership violation 是 error）：
        1. main worker steps 不引用 child-owned spans => error
        2. child worker steps 只引用自己 owned spans => error
        3. handoff step 存在且绑定完整 => error/warning
        4. child output 是否被 parent 消费或声明为 final => error
        5. worker-local producer/consumer reachability => warning
        6. CALL_API handoff 和 INVOKE_WORKER handoff 分开校验 => error
        """
        errors: list[str] = []
        warnings: list[str] = []
        self.construct_findings: dict[str, list[dict]] = {}

        # 1. 验证 span ownership（D5: error）
        span_errors = self._validate_span_ownership(worker_step_plan, worker_plan)
        errors.extend(span_errors)

        # 2. 验证 handoff completeness
        handoff_errors, handoff_warnings = self._validate_handoffs(
            worker_step_plan, worker_plan
        )
        errors.extend(handoff_errors)
        warnings.extend(handoff_warnings)

        # 3. 验证 output binding
        output_errors = self._validate_output_binding(
            worker_step_plan, worker_plan, symbol_table
        )
        errors.extend(output_errors)

        # 4. 验证 producer/consumer reachability
        reachability_warnings = self._validate_reachability(
            worker_step_plan, worker_plan, symbol_table
        )
        warnings.extend(reachability_warnings)

        # 5. 分离 invoke 和 api_call handoff 校验
        handoff_type_errors = self._validate_handoff_types(worker_plan)
        errors.extend(handoff_type_errors)

        # 6. Normalize worker-local multi-output steps. SPL commands can only
        # declare one RESULT/RESPONSE variable, so multi-output steps must be
        # represented as a structured result plus unpack commands.
        for steps in worker_step_plan.worker_steps.values():
            warnings.extend(
                self._normalize_multi_output_steps(resources, symbol_table, steps)
            )

        # 7. Required worker outputs must have producers in their own worker
        # scope. Output contracts declare obligations, not produced values.
        warnings.extend(
            self._ensure_required_worker_outputs(
                worker_block_plan,
                worker_step_plan,
                worker_plan,
                resources,
                symbol_table,
            )
        )
        self._sync_symbol_table_from_steps(
            worker_step_plan.get_all_steps(),
            symbol_table,
        )

        # 8. Diagnose exception flows without handlers per worker.
        for worker in worker_plan.workers:
            worker_flow = worker_flow_plan.worker_flows.get(worker.worker_id)
            worker_blocks = worker_block_plan.worker_blocks.get(worker.worker_id)
            if worker_flow is None or worker_blocks is None:
                continue
            worker_steps = worker_step_plan.worker_steps.get(worker.worker_id, [])
            self._diagnose_exception_flow_handlers(
                worker_flow,
                worker_blocks,
                worker_steps,
                worker_id=worker.worker_id,
            )

        # 9. Diagnose type/contract ambiguities and assumed commands
        #    across the full assembled step list.
        all_steps = worker_step_plan.get_all_steps()
        handoff_api_names = {
            h.api_ref
            for h in worker_plan.handoffs
            if h.mode == "api_call" and h.api_ref
        }
        api_handoff_refs = {
            h.handoff_id: h.api_ref
            for h in worker_plan.handoffs
            if h.mode == "api_call" and h.api_ref
        }
        valid_handoff_ids = {h.handoff_id for h in worker_plan.handoffs}
        self._diagnose_type_contract_ambiguities(
            all_steps, symbol_table, resources,
            extra_api_names=handoff_api_names,
            api_handoff_refs=api_handoff_refs,
        )
        self._diagnose_assumed_commands(
            all_steps,
            valid_handoff_ids=valid_handoff_ids,
        )

        return (
            worker_flow_plan,
            worker_block_plan,
            worker_step_plan,
            symbol_table,
            errors,
            warnings,
        )

    def _validate_span_ownership(
        self,
        worker_step_plan: WorkerStepPlanIR,
        worker_plan: WorkerPlanIR,
    ) -> list[str]:
        """Validate span ownership across workers.

        D5: span ownership violation 是 error，不是 warning。

        Rules:
        - Non-handoff step references span outside owner worker => error
        - Main ordinary step references child-owned span => error
        - Child ordinary step references parent-owned span => error
        - Handoff step source_span_ids must be caller-owned or empty-with-warning
        """
        errors: list[str] = []

        # 构建 worker -> owned spans 映射
        worker_spans: dict[str, set[str]] = {}
        for worker in worker_plan.workers:
            worker_spans[worker.worker_id] = set(worker.owned_span_ids)

        # 检查每个 worker 的 steps
        for worker_id, steps in worker_step_plan.worker_steps.items():
            owned = worker_spans.get(worker_id, set())

            for step in steps:
                # INVOKE_WORKER 和 CALL_API 可以引用 caller span
                if step.command_type in ("INVOKE_WORKER", "CALL_API"):
                    continue

                # 其他 steps 只能引用 owned spans（D5: error）
                for span_id in step.source_span_ids:
                    if span_id not in owned:
                        errors.append(
                            f"Worker {worker_id} step {step.step_id} "
                            f"references span {span_id} not in owned_span_ids"
                        )

        # 检查 main worker steps 不引用 child-owned spans（D5: error）
        main_steps = worker_step_plan.main_worker_steps
        child_spans: set[str] = set()
        for worker in worker_plan.workers:
            if worker.kind == "child":
                child_spans.update(worker.owned_span_ids)

        for step in main_steps:
            if step.command_type in ("INVOKE_WORKER", "CALL_API"):
                continue
            for span_id in step.source_span_ids:
                if span_id in child_spans:
                    errors.append(
                        f"Main worker step {step.step_id} "
                        f"references child-owned span {span_id}"
                    )

        return errors

    def _validate_handoffs(
        self,
        worker_step_plan: WorkerStepPlanIR,
        worker_plan: WorkerPlanIR,
    ) -> tuple[list[str], list[str]]:
        """Validate handoff completeness."""
        errors: list[str] = []
        warnings: list[str] = []

        # 构建 handoff_id -> [(worker_id, step)] 映射。
        # D10: 不能只检查 handoff_id 是否存在，还必须检查 step shape。
        handoff_steps: dict[str, list[tuple[str, StepIR]]] = {}
        for worker_id, steps in worker_step_plan.worker_steps.items():
            for step in steps:
                if step.handoff_id:
                    handoff_steps.setdefault(step.handoff_id, []).append((worker_id, step))

        worker_by_id = {worker.worker_id: worker for worker in worker_plan.workers}

        for handoff in worker_plan.handoffs:
            matching_steps = handoff_steps.get(handoff.handoff_id, [])
            if not matching_steps:
                errors.append(
                    f"Handoff {handoff.handoff_id} has no corresponding step"
                )
                continue

            if len(matching_steps) > 1:
                errors.append(
                    f"Handoff {handoff.handoff_id} has multiple corresponding steps"
                )
                continue

            step_worker_id, step = matching_steps[0]
            if step_worker_id != handoff.from_worker:
                errors.append(
                    f"Handoff {handoff.handoff_id} step is in worker {step_worker_id}, "
                    f"expected {handoff.from_worker}"
                )

            expected_inputs = [binding.parent_variable for binding in handoff.input_bindings]
            expected_outputs = [
                binding.parent_variable for binding in handoff.output_bindings
            ]
            if list(step.inputs) != expected_inputs:
                errors.append(
                    f"Handoff {handoff.handoff_id} input mismatch: "
                    f"{step.inputs} != {expected_inputs}"
                )
            if list(step.outputs) != expected_outputs:
                errors.append(
                    f"Handoff {handoff.handoff_id} output mismatch: "
                    f"{step.outputs} != {expected_outputs}"
                )

            if handoff.mode == "invoke":
                target = worker_by_id.get(handoff.to_worker or "")
                if step.command_type != "INVOKE_WORKER":
                    errors.append(
                        f"Handoff {handoff.handoff_id} expected INVOKE_WORKER step, "
                        f"got {step.command_type}"
                    )
                if target is not None and step.integration_ref != target.worker_name:
                    errors.append(
                        f"Handoff {handoff.handoff_id} target mismatch: "
                        f"{step.integration_ref} != {target.worker_name}"
                    )
            elif handoff.mode == "api_call":
                if step.command_type != "CALL_API":
                    errors.append(
                        f"Handoff {handoff.handoff_id} expected CALL_API step, "
                        f"got {step.command_type}"
                    )
                if step.integration_ref != handoff.api_ref:
                    errors.append(
                        f"Handoff {handoff.handoff_id} api_ref mismatch: "
                        f"{step.integration_ref} != {handoff.api_ref}"
                    )

            # 检查 input_bindings 完整性
            if not handoff.input_bindings:
                warnings.append(
                    f"Handoff {handoff.handoff_id} has no input_bindings"
                )

            # 检查 output_bindings 完整性
            if not handoff.output_bindings:
                warnings.append(
                    f"Handoff {handoff.handoff_id} has no output_bindings"
                )

        return errors, warnings

    def _validate_output_binding(
        self,
        worker_step_plan: WorkerStepPlanIR,
        worker_plan: WorkerPlanIR,
        symbol_table: SymbolTable,
    ) -> list[str]:
        """Validate child output is consumed by parent or declared as final."""
        errors: list[str] = []

        for worker in worker_plan.workers:
            if worker.kind != "child":
                continue

            # 获取 child worker 的 output contract
            for output_field in worker.output_contract:
                # 检查是否有 handoff 将此 output 绑定到 parent variable
                bound = False
                for handoff in worker_plan.handoffs:
                    if handoff.to_worker != worker.worker_id:
                        continue
                    for binding in handoff.output_bindings:
                        if binding.child_output == output_field.name:
                            bound = True
                            break

                if not bound:
                    errors.append(
                        f"Child worker {worker.worker_id} output "
                        f"'{output_field.name}' is not bound to parent"
                    )

        return errors

    def _validate_reachability(
        self,
        worker_step_plan: WorkerStepPlanIR,
        worker_plan: WorkerPlanIR,
        symbol_table: SymbolTable,
    ) -> list[str]:
        """Validate worker-local producer/consumer reachability."""
        warnings: list[str] = []

        for worker_id, steps in worker_step_plan.worker_steps.items():
            # 构建该 worker 的 producer/consumer 映射
            producers: dict[str, str] = {}  # variable -> step_id
            consumers: dict[str, list[str]] = {}  # variable -> [step_ids]

            for step in steps:
                for output in step.outputs:
                    if output in producers:
                        warnings.append(
                            f"Worker {worker_id}: variable '{output}' "
                            f"produced by multiple steps"
                        )
                    producers[output] = step.step_id

                for input_var in step.inputs:
                    if input_var not in consumers:
                        consumers[input_var] = []
                    consumers[input_var].append(step.step_id)

            # 检查每个 consumer 的 input 是否有 producer
            for input_var in consumers:
                if input_var not in producers:
                    # 可能是 worker input，检查 contract
                    worker = next(
                        (w for w in worker_plan.workers if w.worker_id == worker_id),
                        None
                    )
                    if worker:
                        contract_inputs = {f.name for f in worker.input_contract}
                        if input_var not in contract_inputs:
                            warnings.append(
                                f"Worker {worker_id}: variable '{input_var}' "
                                f"consumed but not produced or declared as input"
                            )

        return warnings

    def _ensure_required_worker_outputs(
        self,
        worker_block_plan: WorkerBlockPlanIR,
        worker_step_plan: WorkerStepPlanIR,
        worker_plan: WorkerPlanIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
    ) -> list[str]:
        """Check required output contracts have worker-local producers.

        Does NOT synthesize producer steps.  Missing producers are reported as
        CompileDiagnostic records.

        Uses ProducerIndex per worker so handoff output bindings and declared
        APIs contribute to producer detection.
        """
        warnings: list[str] = []
        declared_apis = {api.api_name for api in resources.apis}
        extra_api_names = self._collect_extra_api_names(worker_plan)
        api_handoff_refs = self._build_api_handoff_refs(worker_plan)

        for worker_spec in worker_plan.workers:
            required_outputs = [
                field.name for field in worker_spec.output_contract
                if field.required
            ]
            if not required_outputs:
                continue

            steps = worker_step_plan.worker_steps.get(worker_spec.worker_id, [])
            # Filter handoffs to those originating from this worker
            worker_handoffs = [
                h for h in worker_plan.handoffs
                if h.from_worker == worker_spec.worker_id
            ]
            # Child workers this worker is allowed to invoke: all other
            # workers except self, the main worker, and sentinels.
            child_ids = {
                w.worker_id for w in worker_plan.workers
                if w.worker_id != worker_spec.worker_id
                and w.worker_id != worker_plan.main_worker_id
                and w.boundary_kind != "main_worker"
                and w.boundary_kind != "not_a_worker"
            }

            index = ProducerIndex(
                steps=steps,
                handoffs=worker_handoffs if worker_handoffs else None,
                declared_apis=declared_apis,
                extra_api_names=extra_api_names,
                api_handoff_refs=api_handoff_refs,
                known_child_worker_ids=child_ids,
            )

            for output in required_outputs:
                if index.is_produced(output):
                    continue

                variable = symbol_table.variables.get(output)
                self.construct_findings.setdefault(
                    "missing_output_producer", []
                ).append({
                    "output": output,
                    "description": variable.description if variable else output,
                    "worker_id": worker_spec.worker_id,
                })

        return warnings

    def _validate_handoff_types(
        self,
        worker_plan: WorkerPlanIR,
    ) -> list[str]:
        """Validate CALL_API and INVOKE_WORKER handoffs separately."""
        errors: list[str] = []

        for handoff in worker_plan.handoffs:
            if handoff.mode == "invoke":
                # INVOKE_WORKER 必须有 to_worker
                if not handoff.to_worker:
                    errors.append(
                        f"INVOKE handoff {handoff.handoff_id} "
                        f"missing to_worker"
                    )
                # 检查 to_worker 存在
                to_worker = next(
                    (w for w in worker_plan.workers if w.worker_id == handoff.to_worker),
                    None
                )
                if not to_worker:
                    errors.append(
                        f"INVOKE handoff {handoff.handoff_id} "
                        f"references non-existent worker {handoff.to_worker}"
                    )

            elif handoff.mode == "api_call":
                # CALL_API 必须有 api_ref
                if not handoff.api_ref:
                    errors.append(
                        f"API_CALL handoff {handoff.handoff_id} "
                        f"missing api_ref"
                    )

        return errors
