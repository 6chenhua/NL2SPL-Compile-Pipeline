"""Worker-scoped methods for Stage 7 StepExtractor."""

from __future__ import annotations

import json
from dataclasses import asdict

from nl2spl.compiler.construct_plan import APICallPlacementIR, ConstructPlan
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.step_variable_relation_ir import (
    StepVariableRelation,
    StepVariableRelationPlan,
)
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_contract_status import binding_side_satisfied
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
    APIMaterializationPlanIR,
)
from nl2spl.pipeline.stages.stage7_step_extractor.action_model import (
    ExecutableActionIR,
    WorkerActionPlanIR,
    canonicalize_action_text,
)
from nl2spl.pipeline.stages.stage7_step_extractor.action_projection import (
    APIResidualActionProjection,
    APIResidualActionProjector,
)
from nl2spl.pipeline.stages.stage7_step_extractor.api_call_materializer import (
    materialize_direct_api_calls,
)


class WorkerScopedMethodsMixin:
    """Mixin class containing worker-scoped methods for StepExtractor."""

    def execute_worker_scoped(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        symbol_table: SymbolTable,
        worker_plan: WorkerPlanIR,
        construct_plan: ConstructPlan | None = None,
        api_materialization_plan: APIMaterializationPlanIR | None = None,
        api_call_placements: list[APICallPlacementIR] | None = None,
        resources: ResourceRegistryIR | None = None,
    ) -> tuple[WorkerStepPlanIR, SymbolTable]:
        """Execute worker-scoped step extraction.

        对每个 worker 独立提取 steps：
        - main worker: 从 main flow 提取普通 steps + 从 handoffs 生成 INVOKE_WORKER
        - child worker: 从 child flow 提取自己的 steps

        Args:
            spans: All spans
            routes: Field routes
            worker_flow_plan: Worker-scoped flow plan
            worker_block_plan: Worker-scoped block plan
            symbol_table: Symbol table
            worker_plan: Worker plan

        Returns:
            Tuple of (WorkerStepPlanIR, updated SymbolTable)
        """
        worker_step_plan = WorkerStepPlanIR(main_worker_id=worker_plan.main_worker_id)
        all_warnings: list[str] = []
        self.stage7_diagnostics: list[CompileDiagnostic] = []
        self._pending_unmapped_data: dict[str, tuple[list[SpanIR], dict[str, str], set[str]]] = {}

        # 1. 对每个 worker 提取 steps
        for worker in worker_plan.workers:
            worker_id = worker.worker_id
            flow = worker_flow_plan.worker_flows.get(worker_id)
            blocks = worker_block_plan.worker_blocks.get(worker_id)

            if flow is None or blocks is None:
                all_warnings.append(
                    f"Worker {worker_id} missing flow/blocks, skipping step extraction"
                )
                continue

            # 获取该 worker 拥有的 spans
            worker_span_ids = set(worker.owned_span_ids)
            worker_spans = [s for s in spans if s.span_id in worker_span_ids]

            # 提取该 worker 的 steps（使用 worker-scoped prompt）
            worker_steps, symbol_table = self._extract_steps_for_worker(
                worker_spans,
                routes,
                flow,
                blocks,
                symbol_table,
                worker,
                worker_plan,
                construct_plan,
            )

            worker_step_plan.worker_steps[worker_id] = worker_steps

        # 2. 为 main worker 从 handoffs 生成 INVOKE_WORKER / CALL_API steps
        handoff_steps_by_worker = self._generate_handoff_steps(
            worker_plan,
            symbol_table,
        )
        for worker_id, handoff_steps in handoff_steps_by_worker.items():
            if worker_id in worker_step_plan.worker_steps:
                worker_step_plan.worker_steps[worker_id].extend(handoff_steps)
            else:
                worker_step_plan.worker_steps[worker_id] = handoff_steps

        projections_by_call_id: dict[str, APIResidualActionProjection] = {}
        if (
            construct_plan is not None
            and api_materialization_plan is not None
            and api_call_placements is not None
            and resources is not None
        ):
            self.stage7_diagnostics.extend(
                materialize_direct_api_calls(
                    worker_step_plan,
                    construct_plan,
                    api_materialization_plan,
                    api_call_placements,
                    resources,
                    spans,
                    projections_by_call_id,
                )
            )

        # 3. Run unmapped-span detection NOW that all steps (LLM + generated
        #    handoffs) are assembled per worker.
        for worker in worker_plan.workers:
            pending = self._pending_unmapped_data.get(worker.worker_id)
            if pending is None:
                continue
            behavior_spans, llm_unmapped, *extra = pending
            non_exec_ids: set[str] = extra[0] if extra else set()
            final_steps = worker_step_plan.worker_steps.get(worker.worker_id, [])
            self._detect_unmapped_spans(
                final_steps,
                behavior_spans,
                llm_unmapped,
                worker.worker_id,
                non_exec_ids,
                construct_plan,
            )

        relation_plan = _build_step_variable_relation_plan(
            worker_step_plan,
            symbol_table,
            span_by_id={span.span_id: span for span in spans},
        )
        if _remove_redundant_same_source_output_steps(worker_step_plan):
            relation_plan = _build_step_variable_relation_plan(
                worker_step_plan,
                symbol_table,
                span_by_id={span.span_id: span for span in spans},
            )
        worker_step_plan.step_variable_relation_plan = relation_plan

        # Assemble WorkerActionPlanIR intermediate and expose it on StepExtractor
        worker_actions: dict[str, list[ExecutableActionIR]] = {}
        for worker_id, steps in worker_step_plan.worker_steps.items():
            actions_list: list[ExecutableActionIR] = []
            for step in steps:
                demand_ids = (
                    step.metadata.get("construct_demand_ids") if step.metadata else None
                )
                api_call_demand_id = (
                    step.metadata.get("api_call_demand_id") if step.metadata else None
                )
                projection = None
                if demand_ids:
                    projection = projections_by_call_id.get(demand_ids[0])
                elif api_call_demand_id:
                    projection = projections_by_call_id.get(api_call_demand_id)

                if projection is not None:
                    if step.command_type == "CALL_API" and projection.call_action is not None:
                        actions_list.append(projection.call_action)
                        continue
                    elif step.command_type == "GENERAL_COMMAND" and projection.residual_actions:
                        matching_res = None
                        for res in projection.residual_actions:
                            is_match = (
                                res.action_id == step.step_id
                                or f"st_{res.action_id}" == step.step_id
                            )
                            if is_match:
                                matching_res = res
                                break
                        if matching_res is not None:
                            actions_list.append(matching_res)
                            continue

                action_kind = "source_slice"
                if step.handoff_id:
                    action_kind = "handoff_derived"
                output_policy = "no_output"
                if step.outputs:
                    output_policy = "produces_output"

                actions_list.append(
                    ExecutableActionIR(
                        action_id=step.step_id,
                        action_kind=action_kind,  # type: ignore[arg-type]
                        source_span_ids=tuple(step.source_span_ids),
                        action_text=step.text,
                        normalized_action_key=canonicalize_action_text(step.text),
                        command_type=step.command_type,  # type: ignore[arg-type]
                        owning_authority="stage7.step_extractor",
                        flow_ref=step.flow_ref,
                        block_ref=step.block_ref,
                        placement_status="placed" if step.flow_ref else "unplaced",
                        output_policy=output_policy,  # type: ignore[arg-type]
                        coverage_status="exact",
                    )
                )
            worker_actions[worker_id] = actions_list

        coverage_reports = [p.coverage_report for p in projections_by_call_id.values()]
        action_plan = WorkerActionPlanIR(
            main_worker_id=worker_plan.main_worker_id,
            worker_actions={w_id: tuple(acts) for w_id, acts in worker_actions.items()},
            coverage_reports=tuple(coverage_reports),
            diagnostics=tuple(self.stage7_diagnostics),
        )
        self.last_action_plan = action_plan

        worker_step_plan.warnings = all_warnings
        return worker_step_plan, symbol_table

    def _extract_steps_for_worker(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        symbol_table: SymbolTable,
        worker: WorkerSpecIR,
        worker_plan: WorkerPlanIR | None = None,
        construct_plan: ConstructPlan | None = None,
    ) -> tuple[list[StepIR], SymbolTable]:
        """Extract steps for a single worker.

        关键：prompt 中包含以下变量：
        - worker input contract
        - worker output contract
        - already-known global variables
        - current worker known variables
        - handoff-bound parent variables for main worker
        """
        # 构建 worker-scoped prompt 变量
        prompt_variables = self._build_worker_prompt_variables(worker, symbol_table)

        # 获取 behavior spans（使用 routes.behavior 和 flow 的交集）
        non_exec_span_ids: set[str] = set()
        if routes.annotations:
            behavior_span_ids = set(routes.get_executable_behavior_span_ids())
            non_exec_span_ids = set(routes.get_non_executable_behavior_span_ids())
        else:
            behavior_span_ids = set(routes.behavior)
        behavior_span_ids.update(
            span.span_id
            for span in spans
            if _is_stage1_process_action_span(span)
        )
        if construct_plan is not None:
            behavior_span_ids -= construct_plan.reserved_without_dual_role()
            api_consumed_span_ids = {
                span_id
                for call in construct_plan.api_call_demands()
                for span_id in call.consumes_behavior_span_ids
            }
            behavior_span_ids -= api_consumed_span_ids
        flow_span_ids = set(flow.get_all_flow_spans())
        if flow_span_ids:
            behavior_span_ids = behavior_span_ids.intersection(flow_span_ids)
        behavior_spans = [s for s in spans if s.span_id in behavior_span_ids]

        # 构建 behavior spans JSON
        behavior_json = json.dumps(
            [s.to_dict() for s in behavior_spans], ensure_ascii=False
        )

        # 构建 flow 和 blocks JSON
        flow_json = json.dumps(asdict(flow), ensure_ascii=False)
        blocks_json = json.dumps(asdict(blocks), ensure_ascii=False)

        # 构建变量列表
        variable_list = "\n".join(
            f"- {name}: {desc}" for name, desc in prompt_variables.items()
        )
        outgoing_handoffs = [
            handoff.handoff_id
            for handoff in (worker_plan.handoffs if worker_plan else [])
            if handoff.from_worker == worker.worker_id
        ]
        if outgoing_handoffs:
            handoff_rule = (
                "Allowed outgoing handoff IDs for INVOKE_WORKER/CALL_API: "
                + ", ".join(outgoing_handoffs)
            )
        else:
            handoff_rule = (
                "This worker has no outgoing handoffs. Do not output "
                "INVOKE_WORKER or CALL_API; use GENERAL_COMMAND for worker-local work."
            )

        # 构建 prompt
        system_prompt = load_prompt("stage7").replace(
            "{variable_list}", variable_list
        )

        non_exec_context = ""
        if non_exec_span_ids:
            owned_non_exec = non_exec_span_ids & set(worker.owned_span_ids)
            if owned_non_exec:
                non_exec_spans = [s for s in spans if s.span_id in owned_non_exec]
                non_exec_json = json.dumps(
                    [s.to_dict() for s in non_exec_spans], ensure_ascii=False
                )
                non_exec_context = (
                    "Non-executable context only (failure conditions, "
                    "delegation boundaries — do NOT create COMMAND, REQUEST_INPUT, "
                    "INVOKE_WORKER, or CALL_API from these spans):\n"
                    f"---\n{non_exec_json}\n---\n\n"
                )

        user_prompt = f"""Extract steps from the following text:

behavior spans:
---
{behavior_json}
---

{non_exec_context}Flow structure:
---
{flow_json}
---

Block structure:
---
{blocks_json}
---

Known variables:
---
{variable_list}
---

Worker information:
- worker_id: {worker.worker_id}
- worker_name: {worker.worker_name}
- kind: {worker.kind}
- purpose: {worker.purpose}
- handoff_rule: {handoff_rule}

Output JSON:"""

        # 调用 LLM
        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed for worker %s: %s", worker.worker_id, e)
            raise StageError(
                message=f"LLM call failed in {self.name} for worker {worker.worker_id}: {e}",
                stage=self.name,
            ) from e

        # 解析 steps
        steps: list[StepIR] = []
        for step_data in result.get("steps", []):
            try:
                step = StepIR(
                    step_id=step_data["step_id"],
                    text=step_data["text"],
                    source_span_ids=step_data["source_span_ids"],
                    command_type=step_data["command_type"],
                    inputs=step_data.get("inputs", []),
                    outputs=step_data.get("outputs", []),
                    integration_ref=step_data.get("integration_ref"),
                    flow_ref=step_data.get("flow_ref", "main"),
                    block_ref=step_data.get("block_ref", ""),
                    kind=step_data.get("kind", "normal"),
                    handoff_id=step_data.get("handoff_id"),
                    metadata=step_data.get("metadata", {}),
                )
                steps.append(step)
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid step: %s", e)
                continue

        self._validate_step_type_contracts(steps, worker.worker_id)

        # D6 guard: drop steps sourced only from non-executable spans
        if non_exec_span_ids:
            kept_steps: list[StepIR] = []
            for step in steps:
                source_ids = set(step.source_span_ids)
                if source_ids and source_ids.issubset(non_exec_span_ids):
                    self.logger.info(
                        "D6 guard (worker %s): dropped non-executable step %s",
                        worker.worker_id, step.step_id,
                    )
                    continue
                kept_steps.append(step)
            steps = kept_steps

        _add_source_backed_provenance_maintenance_steps(
            steps,
            behavior_spans,
            blocks,
        )

        # Child workers may emit handoff commands only when backed by an
        # accepted outgoing handoff. Invalid handoff-shaped commands are LLM
        # contract errors and must fail fast instead of being rewritten.
        if worker.kind == "child":
            allowed_handoff_ids = set(outgoing_handoffs)
            invalid_handoff_steps = [
                s for s in steps
                if s.command_type in ("INVOKE_WORKER", "CALL_API")
                and s.handoff_id not in allowed_handoff_ids
            ]
            if invalid_handoff_steps:
                details = [
                    f"{s.step_id}:{s.command_type}:handoff_id={s.handoff_id or '<none>'}"
                    for s in invalid_handoff_steps
                ]
                raise StageError(
                    message=(
                        f"LLM emitted invalid handoff command(s) for child worker "
                        f"{worker.worker_id}: {details}. Child-worker handoff "
                        "commands must be backed by accepted outgoing handoffs."
                    ),
                    stage=self.name,
                )

        # Store detection data for deferred unmapped-span check.  Generated
        # handoff steps are appended later in execute_worker_scoped, so the
        # actual detection runs there once the final step list is assembled.
        llm_unmapped: dict[str, str] = {}
        for item in (result.get("unmapped_spans") or []):
            if not isinstance(item, dict):
                self.logger.warning("Skipping non-dict unmapped_span item: %s", item)
                continue
            span_id = item.get("span_id")
            if span_id:
                llm_unmapped[span_id] = item.get("reason", "No reason given")
        self._pending_unmapped_data[worker.worker_id] = (
            list(behavior_spans),
            llm_unmapped,
            non_exec_span_ids,  # D6: skip non-executable in unmapped check
        )

        # 处理 new_variables — declare with worker scope
        for new_var_data in result.get("new_variables", []):
            try:
                new_var_name = new_var_data["name"]
                if symbol_table.lookup(new_var_name) is None:
                    symbol_table.declare_scoped(
                        name=new_var_name,
                        data_type=new_var_data.get("data_type", "text"),
                        source="step",
                        description=new_var_data.get("description", ""),
                        scope_kind="worker",
                        scope_id=worker.worker_id,
                    )
            except (KeyError, TypeError) as e:
                self.logger.warning("Skipping invalid new variable: %s", e)

        # 更新 producers/consumers
        for step in steps:
            for var_name in step.inputs:
                symbol_table.add_consumer(var_name, step.step_id)
            for var_name in step.outputs:
                symbol_table.add_producer(var_name, step.step_id)

        # 验证 span ownership（D5: error）
        ownership_errors = self._validate_step_span_ownership(steps, worker)
        if ownership_errors:
            raise StageError(
                message=(
                    "Step span ownership validation failed for worker "
                    f"{worker.worker_id}: {ownership_errors}"
                ),
                stage=self.name,
            )

        return steps, symbol_table

    def _detect_unmapped_spans(
        self,
        steps: list[StepIR],
        behavior_spans: list[SpanIR],
        llm_unmapped: dict[str, str],
        worker_id: str,
        non_exec_span_ids: set[str] | None = None,
        construct_plan: ConstructPlan | None = None,
    ) -> None:
        """Emit unmapped_behavior_span diagnostics for the final step list.

        Must be called AFTER all step sources (LLM + generated handoffs) are
        assembled so source-backed handoff steps count as coverage.
        """
        # 1. Action-level unmaterialized residual checks
        if construct_plan is not None:
            span_by_id = {span.span_id: span for span in behavior_spans}
            projector = APIResidualActionProjector()
            for call in construct_plan.api_call_demands():
                if not set(call.source_span_ids).intersection(span_by_id.keys()):
                    continue
                projection = projector.project(
                    call=call,
                    span_by_id=span_by_id,
                    placement=None,
                )
                if projection.coverage_report.status == "has_uncovered_residual":
                    has_residual_step = any(
                        step.metadata
                        and step.metadata.get("origin") == "residual_generated"
                        and step.metadata.get("api_call_demand_id") == call.demand_id
                        for step in steps
                    )
                    if not has_residual_step:
                        self.stage7_diagnostics.append(
                            CompileDiagnostic(
                                diagnostic_id=f"diag_unmat_{call.demand_id}",
                                kind="stage7_residual_action_unmaterialized",
                                severity="warning",
                                message=(
                                    f"Residual action for API call '{call.demand_id}' "
                                    f"is unmaterialized."
                                ),
                                target_ref=f"api_call_demand:{call.demand_id}",
                                source_span_ids=list(call.source_span_ids),
                                metadata={
                                    "call_demand_id": call.demand_id,
                                    "reason": "residual_unmaterialized",
                                },
                                blocks_rendering=False,
                                blocks_completion=True,
                            )
                        )

        # 2. Standard unmapped span checks
        covered_behavior_span_ids = {
            span_id
            for step in steps
            for span_id in step.source_span_ids
        }
        missing_behavior_span_ids = {
            span.span_id
            for span in behavior_spans
            if span.span_id not in covered_behavior_span_ids
        }
        skip_ids = non_exec_span_ids or set()
        for span_id in sorted(missing_behavior_span_ids):
            if span_id in skip_ids:
                continue  # D6: non-executable spans are not expected to map to steps
            reason = llm_unmapped.get(
                span_id,
                "Behavior span not mapped to any step by LLM",
            )
            span_text = next(
                (s.text for s in behavior_spans if s.span_id == span_id),
                span_id,
            )
            self.stage7_diagnostics.append(
                CompileDiagnostic(
                    diagnostic_id=f"diag_s7_{len(self.stage7_diagnostics):04d}",
                    kind="unmapped_behavior_span",
                    severity="warning",
                    message=(
                        f"Worker '{worker_id}' behavior span "
                        f"'{span_id}' ({span_text[:80]}) was not mapped "
                        f"to a step: {reason}"
                    ),
                    target_ref=f"worker:{worker_id}.span:{span_id}",
                    source_span_ids=[span_id],
                    blocks_rendering=False,
                    blocks_completion=True,
                )
            )

    def _build_worker_prompt_variables(
        self,
        worker: WorkerSpecIR,
        symbol_table: SymbolTable,
    ) -> dict[str, str]:
        """Build variables for worker-scoped prompt.

        包含：
        - worker input contract
        - worker output contract
        - already-known global variables
        - current worker known variables
        - handoff-bound parent variables for main worker
        """
        variables: dict[str, str] = {}

        # 1. Worker input contract
        for field in worker.input_contract:
            variables[field.name] = f"[input] {field.data_type}: {field.description}"

        # 2. Worker output contract
        for field in worker.output_contract:
            variables[field.name] = f"[output] {field.data_type}: {field.description}"

        # 3. Scoped variables visible to this worker
        for name, var in symbol_table.get_variables_for_worker(worker.worker_id).items():
            if name not in variables:
                scope_tag = var.scope_kind if var.scope_kind != "global" else "global"
                variables[name] = f"[{scope_tag}] {var.data_type}: {var.description}"

        return variables

    def _generate_handoff_steps(
        self,
        worker_plan: WorkerPlanIR,
        symbol_table: SymbolTable,
    ) -> dict[str, list[StepIR]]:
        """Generate INVOKE_WORKER / CALL_API steps from handoffs.

        关键：只从 WorkerHandoffIR 生成，不从 decisions 生成。（D1）
        """
        handoff_steps: dict[str, list[StepIR]] = {}

        for handoff in worker_plan.handoffs:
            if not self._handoff_ready_for_executable_step(handoff):
                self.logger.info(
                    "Skipping executable handoff step for %s "
                    "(materialization_status=%s)",
                    handoff.handoff_id,
                    getattr(handoff, "materialization_status", "unknown"),
                )
                continue
            if handoff.mode == "invoke":
                step = self._build_invoke_step(handoff, worker_plan)
            elif handoff.mode == "api_call":
                step = self._build_api_call_step(handoff, worker_plan)
            else:
                self.logger.warning(
                    "Unknown handoff mode: %s for handoff %s",
                    handoff.mode,
                    handoff.handoff_id,
                )
                continue

            handoff_steps.setdefault(handoff.from_worker, []).append(step)

            # 更新 symbol table
            for var_name in step.inputs:
                symbol_table.add_consumer(var_name, step.step_id)
            for var_name in step.outputs:
                symbol_table.add_producer(var_name, step.step_id)

        return handoff_steps

    @staticmethod
    def _handoff_ready_for_executable_step(handoff: WorkerHandoffIR) -> bool:
        """Return True only when a handoff can materialize an executable step."""
        if handoff.materialization_status in {"blocked", "partial_contract_unknown"}:
            return False
        return binding_side_satisfied(
            handoff.input_bindings,
            handoff.input_binding_status,
        ) and binding_side_satisfied(
            handoff.output_bindings,
            handoff.output_binding_status,
        )

    def _build_invoke_step(
        self,
        handoff: WorkerHandoffIR,
        worker_plan: WorkerPlanIR,
    ) -> StepIR:
        """Build INVOKE_WORKER step from handoff."""
        # 查找 target worker
        to_worker = next(
            (w for w in worker_plan.workers if w.worker_id == handoff.to_worker),
            None,
        )

        # 获取 source spans（优先使用 invoke_location_hint）（D2）
        source_spans = self._get_invoke_source_spans(handoff, worker_plan)
        block_ref = self._handoff_block_ref_for_empty_source(handoff, source_spans)

        # 从 input_bindings 提取 inputs
        inputs = [b.parent_variable for b in handoff.input_bindings]

        # 从 output_bindings 提取 outputs
        outputs = [b.parent_variable for b in handoff.output_bindings]

        return StepIR(
            step_id=f"st_invoke_{handoff.handoff_id}",
            text=f"Invoke worker: {to_worker.worker_name if to_worker else handoff.to_worker}",
            source_span_ids=source_spans,
            command_type="INVOKE_WORKER",
            inputs=inputs,
            outputs=outputs,
            integration_ref=to_worker.worker_name if to_worker else None,
            block_ref=block_ref,
            kind="invoke",
            handoff_id=handoff.handoff_id,
        )

    def _build_api_call_step(
        self,
        handoff: WorkerHandoffIR,
        worker_plan: WorkerPlanIR,
    ) -> StepIR:
        """Build CALL_API step from handoff."""
        source_spans = self._get_invoke_source_spans(handoff, worker_plan)
        block_ref = self._handoff_block_ref_for_empty_source(handoff, source_spans)
        inputs = [b.parent_variable for b in handoff.input_bindings]
        outputs = [b.parent_variable for b in handoff.output_bindings]

        return StepIR(
            step_id=f"st_api_{handoff.handoff_id}",
            text=f"Call API: {handoff.api_ref}",
            source_span_ids=source_spans,
            command_type="CALL_API",
            inputs=inputs,
            outputs=outputs,
            integration_ref=handoff.api_ref,
            block_ref=block_ref,
            kind="tool",
            handoff_id=handoff.handoff_id,
        )

    @staticmethod
    def _handoff_block_ref_for_empty_source(
        handoff: WorkerHandoffIR,
        source_span_ids: list[str],
    ) -> str:
        if source_span_ids:
            return ""
        before_span_id = handoff.invoke_location_hint.before_span_id
        return f"before:{before_span_id}" if before_span_id else ""

    def _get_invoke_source_spans(
        self,
        handoff: WorkerHandoffIR,
        worker_plan: WorkerPlanIR,
    ) -> list[str]:
        """Get source spans for invoke/api_call step.

        优先使用 invoke_location_hint，但必须校验 hint span 属于 caller
        (from_worker)。如果 hint span 属于 child worker，返回空并 warning（D2）。
        """
        hint = handoff.invoke_location_hint

        # 构建 caller-owned span 集合，用于校验 hint span 归属
        caller_owned: set[str] = set()
        for w in worker_plan.workers:
            if w.worker_id == handoff.from_worker:
                caller_owned = set(w.owned_span_ids)
                break

        def _is_caller_owned(span_id: str | None) -> bool:
            if not span_id:
                return False
            if span_id not in caller_owned:
                self.logger.warning(
                    "Handoff %s invoke_location_hint span %s is not owned "
                    "by caller %s; falling back to empty source_span_ids.",
                    handoff.handoff_id, span_id, handoff.from_worker,
                )
                return False
            return True

        # 优先使用 caller-owned invocation span
        if hint.after_span_id and _is_caller_owned(hint.after_span_id):
            return [hint.after_span_id]
        if hint.before_span_id and _is_caller_owned(hint.before_span_id):
            return []

        # Fallback：不要绑定到 from_worker 的全部 owned spans。
        # 过宽 source_span_ids 会破坏 block 排序，也可能重新引入 ownership 污染。
        self.logger.warning(
            "Handoff %s has no valid caller-owned invoke_location_hint; "
            "using empty source_span_ids.",
            handoff.handoff_id,
        )

        return []

    def _validate_step_span_ownership(
        self,
        steps: list[StepIR],
        worker: WorkerSpecIR,
    ) -> list[str]:
        """Validate that steps only reference worker-owned spans.

        D5: span ownership violation 是 error，不是 warning。

        Rules:
        - Non-handoff step references span outside owner worker => error
        - Main ordinary step references child-owned span => error
        - Child ordinary step references parent-owned span => error
        - Handoff step source_span_ids must be caller-owned or empty-with-warning
        """
        errors: list[str] = []
        owned_spans = set(worker.owned_span_ids)

        for step in steps:
            # INVOKE_WORKER 和 CALL_API 可以引用 caller span
            if step.command_type in ("INVOKE_WORKER", "CALL_API"):
                # Handoff step source_span_ids 必须是 caller-owned 或 empty
                for span_id in step.source_span_ids:
                    if span_id and span_id not in owned_spans:
                        # 这是 warning，不是 error（因为 handoff 可能引用 caller span）
                        self.logger.warning(
                            "Handoff step %s references span %s not owned by worker %s",
                            step.step_id, span_id, worker.worker_id,
                        )
                continue

            # 其他 steps 只能引用 owned spans（D5: error）
            for span_id in step.source_span_ids:
                if span_id not in owned_spans:
                    metadata = step.metadata or {}
                    if (
                        metadata.get("origin") == "residual_generated"
                        and metadata.get("api_call_demand_id")
                    ):
                        self.logger.warning(
                            "API residual step %s references API-owned span %s "
                            "outside worker ownership",
                            step.step_id, span_id,
                        )
                        continue
                    errors.append(
                        f"Worker {worker.worker_id} step {step.step_id} "
                        f"references span {span_id} not in owned_span_ids"
                    )

        return errors


def _build_step_variable_relation_plan(
    worker_step_plan: WorkerStepPlanIR,
    symbol_table: SymbolTable,
    span_by_id: dict[str, SpanIR] | None = None,
) -> StepVariableRelationPlan:
    relations: list[StepVariableRelation] = []
    diagnostics: list[str] = []
    variables = _symbol_variables(symbol_table)

    for step in worker_step_plan.get_all_steps():
        if step.command_type == "CALL_API":
            for output in step.outputs:
                relations.append(
                    StepVariableRelation(
                        step_id=step.step_id,
                        variable_name=output,
                        relation="produces",
                        source_span_ids=tuple(step.source_span_ids),
                        evidence_kind="api_contract",
                        evidence_source="api_contract",
                        confidence="high",
                    )
                )
            continue
        _strip_control_condition_inputs(step)
        _strip_unbacked_provenance_inputs(step)
        _strip_unbacked_output_contract_inputs(step, variables, span_by_id or {})
        _augment_source_backed_outputs(step, variables, span_by_id or {})
        if _is_no_output_provenance_maintenance(step, span_by_id or {}):
            for output in list(step.outputs):
                relations.append(
                    StepVariableRelation(
                        step_id=step.step_id,
                        variable_name=output,
                        relation="ambiguous",
                        source_span_ids=tuple(step.source_span_ids),
                        evidence_kind="stage7_provenance_maintenance_no_output",
                        evidence_source="inferred_unconfirmed",
                        reason="provenance_maintenance_not_output_producer",
                        confidence="high",
                    )
                )
                diagnostics.append(
                    f"step_variable_relation_ambiguous:{step.step_id}:{output}"
                )
            step.outputs = []
            continue
        kept_outputs: list[str] = []
        for output in list(step.outputs):
            if _output_is_source_backed(step, output, variables):
                relation = _source_backed_output_relation(step, output)
                if relation == "produces":
                    kept_outputs.append(output)
                relations.append(
                    StepVariableRelation(
                        step_id=step.step_id,
                        variable_name=output,
                        relation=relation,
                        source_span_ids=tuple(step.source_span_ids),
                        evidence_kind="stage7_structured_output_source_match",
                        evidence_source="source_text",
                        evidence_text=step.text,
                        confidence="medium",
                    )
                )
            else:
                relations.append(
                    StepVariableRelation(
                        step_id=step.step_id,
                        variable_name=output,
                        relation="ambiguous",
                        source_span_ids=tuple(step.source_span_ids),
                        evidence_kind=(
                            "stage7_structured_output_without_source_match"
                        ),
                        evidence_source="inferred_unconfirmed",
                        reason="output_name_or_description_not_mentioned",
                        confidence="low",
                    )
                )
                diagnostics.append(
                    f"step_variable_relation_ambiguous:{step.step_id}:{output}"
                )
        step.outputs = kept_outputs

    return StepVariableRelationPlan(
        relations=tuple(relations),
        diagnostics=tuple(diagnostics),
    )


def _is_stage1_process_action_span(span: SpanIR) -> bool:
    return (
        span.source_section_id == "sec_reusable_process"
        and span.segmentation_kind in {
            "atomic_action_candidate",
            "guarded_action",
            "continuation_repaired",
        }
    )


def _add_source_backed_provenance_maintenance_steps(
    steps: list[StepIR],
    behavior_spans: list[SpanIR],
    blocks: BlockStructureIR,
) -> None:
    covered_span_ids = {
        span_id
        for step in steps
        for span_id in step.source_span_ids
    }
    existing_ids = {step.step_id for step in steps}
    for span in behavior_spans:
        if span.span_id in covered_span_ids:
            continue
        if span.segmentation_kind != "atomic_action_candidate":
            continue
        normalized = _normalize_relation_text(span.text)
        if "maintain provenance" not in normalized:
            continue
        step_id = f"st_fallback_{span.span_id}"
        if step_id in existing_ids:
            continue
        steps.append(
            StepIR(
                step_id=step_id,
                text=span.text.rstrip("."),
                source_span_ids=[span.span_id],
                command_type="GENERAL_COMMAND",
                inputs=[],
                outputs=[],
                block_ref=_block_ref_for_span(blocks, span.span_id),
                metadata={
                    "origin": "source_backed_provenance_maintenance",
                },
            )
        )
        covered_span_ids.add(span.span_id)
        existing_ids.add(step_id)


def _block_ref_for_span(blocks: BlockStructureIR, span_id: str) -> str:
    for block in blocks.main_flow_blocks:
        if span_id in block.spans:
            return block.block_id
    for block in blocks.alternative_flow_blocks.values():
        if span_id in block.spans:
            return block.block_id
    for block_list in blocks.exception_flow_blocks.values():
        for block in block_list:
            if span_id in block.spans:
                return block.block_id
    return ""


def _remove_redundant_same_source_output_steps(
    worker_step_plan: WorkerStepPlanIR,
) -> bool:
    changed = False
    for worker_id, steps in list(worker_step_plan.worker_steps.items()):
        kept: list[StepIR] = []
        outputs_by_source: dict[tuple[str, ...], set[str]] = {}
        for step in steps:
            source_key = tuple(step.source_span_ids)
            output_set = set(step.outputs)
            if output_set and output_set.issubset(outputs_by_source.get(source_key, set())):
                changed = True
                continue
            kept.append(step)
            outputs_by_source.setdefault(source_key, set()).update(output_set)
        worker_step_plan.worker_steps[worker_id] = kept
    return changed


def _strip_unbacked_provenance_inputs(step: StepIR) -> None:
    action_text = _normalize_relation_text(step.text)
    if "maintain provenance" not in action_text:
        return
    step.inputs = [
        input_name
        for input_name in step.inputs
        if _tokens_mentioned(_meaningful_tokens(input_name), action_text)
    ]


def _strip_control_condition_inputs(step: StepIR) -> None:
    control_state_inputs = {
        "sources_needed_and_available",
        "enough_required_information",
        "enough_required_information_available",
        "user_asks_for_revision",
        "required_slots_remain_missing",
        "required_fields_missing",
    }
    step.inputs = [
        input_name
        for input_name in step.inputs
        if input_name not in control_state_inputs
        and not _looks_like_control_state_variable(input_name)
    ]


def _looks_like_control_state_variable(input_name: str) -> bool:
    normalized = input_name.lower()
    return (
        "enough_required_information" in normalized
        or normalized.startswith("required_fields_")
        or normalized.startswith("required_slots_")
        or normalized.endswith("_needed_and_available")
        or normalized.endswith("_asks_for_revision")
    )


def _strip_unbacked_output_contract_inputs(
    step: StepIR,
    variables: dict[str, object],
    span_by_id: dict[str, SpanIR],
) -> None:
    if not span_by_id:
        return
    source_text = _source_text_for_step(step, span_by_id)
    if not source_text:
        return
    normalized_source = _normalize_relation_text(source_text)
    step.inputs = [
        input_name
        for input_name in step.inputs
        if _input_relation_is_source_backed(
            input_name,
            variables,
            normalized_source,
        )
    ]


def _input_relation_is_source_backed(
    input_name: str,
    variables: dict[str, object],
    normalized_source_text: str,
) -> bool:
    variable = variables.get(input_name)
    if variable is None:
        return True
    if getattr(variable, "source", "") != "output":
        return True
    return _output_mentioned_in_text(input_name, variable, normalized_source_text)


def _is_no_output_provenance_maintenance(
    step: StepIR,
    span_by_id: dict[str, SpanIR] | None = None,
) -> bool:
    action_text = _normalize_relation_text(step.text)
    source_text = _normalize_relation_text(
        _source_text_for_step(step, span_by_id or {}) if span_by_id else ""
    )
    evidence_text = f"{source_text} {action_text}".strip()
    provenance_markers = (
        "maintain provenance",
        "preserve provenance",
        "track provenance",
        "with provenance",
        "provenance for externally sourced facts",
    )
    if not any(marker in evidence_text for marker in provenance_markers):
        return False
    return True


def _symbol_descriptions(symbol_table: SymbolTable) -> dict[str, str]:
    return {
        name: getattr(variable, "description", "") or ""
        for name, variable in _symbol_variables(symbol_table).items()
    }


def _symbol_variables(symbol_table: SymbolTable) -> dict[str, object]:
    variables = dict(symbol_table.variables)
    for key, variable in getattr(symbol_table, "_variables", {}).items():
        variables.setdefault(key[2], variable)
    return variables


def _augment_source_backed_outputs(
    step: StepIR,
    variables: dict[str, object],
    span_by_id: dict[str, SpanIR],
) -> None:
    """Recover source-backed output mentions omitted by the LLM step text.

    This is intentionally narrow: the source span, not keyword matching over the
    generated command text, must mention an output contract variable by name or
    description before we add it to the step.
    """
    if not span_by_id:
        return
    source_text = _source_text_for_step(step, span_by_id)
    if not source_text:
        return
    normalized_source = _normalize_relation_text(source_text)
    added_outputs: list[str] = []
    for name, variable in variables.items():
        if name in step.outputs:
            continue
        if getattr(variable, "source", "") != "output":
            continue
        if not _output_mentioned_in_text(name, variable, normalized_source):
            continue
        step.outputs.append(name)
        added_outputs.append(name)
    if added_outputs:
        step.metadata["source_backed_output_recovery"] = ",".join(added_outputs)
        _append_recovered_outputs_to_step_text(step, added_outputs)


def _source_text_for_step(step: StepIR, span_by_id: dict[str, SpanIR]) -> str:
    parts = [
        span_by_id[span_id].text
        for span_id in step.source_span_ids
        if span_id in span_by_id
    ]
    return " ".join(parts)


def _output_mentioned_in_text(
    output: str,
    variable: object,
    normalized_text: str,
) -> bool:
    if _tokens_mentioned(_meaningful_tokens(output), normalized_text):
        return True
    description = getattr(variable, "description", "") or ""
    if _tokens_mentioned(_meaningful_tokens(description), normalized_text):
        return True
    if output == "completion_status" and "completion status" in normalized_text:
        return True
    if output.endswith("_log") and output[:-4].replace("_", " ") in normalized_text:
        return True
    return False


def _append_recovered_outputs_to_step_text(
    step: StepIR,
    added_outputs: list[str],
) -> None:
    normalized_text = _normalize_relation_text(step.text)
    additions: list[str] = []
    for output in added_outputs:
        display = output.replace("_", " ")
        if display in normalized_text:
            continue
        if output == "completion_status":
            additions.append("set completion status")
        else:
            additions.append(f"produce {display}")
    if additions:
        step.text = f"{step.text.rstrip('.')} and {' and '.join(additions)}."


def _output_is_source_backed(
    step: StepIR,
    output: str,
    variables: dict[str, object],
) -> bool:
    action_text = _normalize_relation_text(step.text)
    output_tokens = _meaningful_tokens(output)
    variable = variables.get(output)
    description = getattr(variable, "description", "") if variable else ""
    description_tokens = _meaningful_tokens(description)
    if _tokens_mentioned(output_tokens, action_text):
        return True
    if _tokens_mentioned(description_tokens, action_text):
        return True
    if output == "completion_status" and "completion status" in action_text:
        return True
    if output.endswith("_log") and output[:-4].replace("_", " ") in action_text:
        return True
    return False


def _source_backed_output_relation(step: StepIR, output: str) -> str:
    del output
    action_text = _normalize_relation_text(step.text)
    action_tokens = action_text.split()
    if action_tokens and action_tokens[0] in {"revise", "refine", "update"}:
        return "refines"
    if " revise " in f" {action_text} " or " refine " in f" {action_text} ":
        return "refines"
    return "produces"


def _normalize_relation_text(text: str) -> str:
    chars = [ch.lower() if ch.isalnum() else " " for ch in text]
    return " ".join("".join(chars).split())


def _meaningful_tokens(text: str) -> set[str]:
    stop = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "by",
        "for",
        "from",
        "in",
        "is",
        "of",
        "or",
        "set",
        "the",
        "to",
        "with",
    }
    normalized = _normalize_relation_text(text.replace("_", " "))
    return {
        token
        for token in normalized.split()
        if len(token) > 2 and token not in stop
    }


def _tokens_mentioned(tokens: set[str], action_text: str) -> bool:
    if not tokens:
        return False
    action_tokens = set(action_text.split())
    required = min(len(tokens), 2)
    return len(tokens & action_tokens) >= required
