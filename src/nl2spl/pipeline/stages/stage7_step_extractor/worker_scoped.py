"""Worker-scoped methods for Stage 7 StepExtractor."""

from __future__ import annotations

import json
from dataclasses import asdict

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.compiler.irs_prompt_builder import irs_checklist_for_stage
from nl2spl.llm.prompts import load_prompt


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
            )

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
        if self.config.enable_irs_prompt_builder:
            system_prompt += "\n\n" + irs_checklist_for_stage("stage7")

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

        user_prompt = f"""请从以下文本中提取 step：

behavior spans：
---
{behavior_json}
---

{non_exec_context}Flow 结构：
---
{flow_json}
---

Block 结构：
---
{blocks_json}
---

已知变量：
---
{variable_list}
---

Worker 信息：
- worker_id: {worker.worker_id}
- worker_name: {worker.worker_name}
- kind: {worker.kind}
- purpose: {worker.purpose}
- handoff_rule: {handoff_rule}

输出 JSON："""

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
                )
                steps.append(step)
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid step: %s", e)
                continue

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

        # 子 worker 不应包含 INVOKE_WORKER 步骤（只有主 worker 通过 handoff
        # 生成 INVOKE）。LLM 可能因 prompt 中列出了 INVOKE_WORKER 类型而误生成。
        # 不能直接 drop——会丢失 child-owned span 的真实行为。
        # 改为降级为 GENERAL_COMMAND，保留 text / source_span_ids / inputs / outputs。
        if worker.kind == "child":
            allowed_handoff_ids = set(outgoing_handoffs)
            rewritten = 0
            for s in steps:
                if (
                    s.command_type in ("INVOKE_WORKER", "CALL_API")
                    and s.handoff_id not in allowed_handoff_ids
                ):
                    s.command_type = "GENERAL_COMMAND"
                    s.kind = "normal"
                    s.integration_ref = None
                    s.handoff_id = None
                    self.logger.warning(
                        "Rewriting handoff step %s to GENERAL_COMMAND "
                        "in child worker %s",
                        s.step_id, worker.worker_id,
                    )
                    rewritten += 1
            if rewritten:
                self.logger.info(
                    "Rewrote %d invalid handoff steps in child worker %s",
                    rewritten, worker.worker_id,
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
    ) -> None:
        """Emit unmapped_behavior_span diagnostics for the final step list.

        Must be called AFTER all step sources (LLM + generated handoffs) are
        assembled so source-backed handoff steps count as coverage.
        """
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
                    errors.append(
                        f"Worker {worker.worker_id} step {step.step_id} "
                        f"references span {span_id} not in owned_span_ids"
                    )

        return errors
