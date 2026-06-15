"""Legacy methods for Stage 7 StepExtractor."""

from __future__ import annotations

from copy import deepcopy

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_contract_status import binding_side_satisfied
from nl2spl.ir.worker_plan_ir import WorkerHandoffIR, WorkerPlanIR, WorkerSpecIR


class LegacyMethodsMixin:
    """Mixin class containing legacy methods for StepExtractor."""

    def _flow_for_step_prompt(
        self,
        flow: FlowStructureIR,
        worker_plan: WorkerPlanIR | None,
    ) -> FlowStructureIR:
        """Return the flow view safe to expose to the Stage 7 LLM prompt."""
        if worker_plan is None:
            return flow

        prompt_flow = deepcopy(flow)
        # WorkerPlanIR handoffs are materialized deterministically after the LLM
        # call. Keeping legacy delegation candidates in the prompt exposes
        # child-owned span ids and invites duplicate ordinary steps.
        prompt_flow.delegation_candidates = []
        return prompt_flow

    def _assert_legacy_main_view_excludes_child_spans(
        self,
        flow: FlowStructureIR,
        worker_plan: WorkerPlanIR,
    ) -> None:
        """Ensure the legacy main view supplied to Stage 7 has no child spans."""
        child_span_ids = {
            span_id
            for worker in worker_plan.workers
            if worker.kind != "main"
            for span_id in worker.owned_span_ids
        }
        leaked_span_ids = sorted(child_span_ids.intersection(flow.get_all_flow_spans()))
        if leaked_span_ids:
            raise StageError(
                message=(
                    "Worker-aware main flow view leaked child-owned span(s) into "
                    f"Stage 7: {', '.join(leaked_span_ids)}"
                ),
                stage=self.name,
            )

    def _apply_worker_plan_handoffs(
        self,
        steps: list[StepIR],
        worker_plan: WorkerPlanIR,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        symbol_table: SymbolTable,
    ) -> list[StepIR]:
        """Make WorkerPlanIR handoffs concrete in StepIR."""
        worker_by_id = {worker.worker_id: worker for worker in worker_plan.workers}
        used_ids = {step.step_id for step in steps}
        child_span_ids = {
            span_id
            for worker in worker_plan.workers
            if worker.kind != "main"
            for span_id in worker.owned_span_ids
        }
        leaked_steps = [
            step.step_id
            for step in steps
            if child_span_ids.intersection(step.source_span_ids)
        ]
        if leaked_steps:
            raise StageError(
                message=(
                    "Stage 7 generated step(s) for child-owned span(s) from the "
                    f"legacy main view: {', '.join(leaked_steps)}"
                ),
                stage=self.name,
            )
        retained_steps = list(steps)

        for handoff in worker_plan.handoffs:
            if not self._handoff_ready_for_executable_step(handoff):
                continue
            target: WorkerSpecIR | None = None
            if handoff.mode == "invoke":
                target = worker_by_id.get(handoff.to_worker or "")
                if target is None:
                    continue
                step = self._step_for_invoke_handoff(
                    handoff,
                    target,
                    flow,
                    blocks,
                    used_ids,
                )
            elif handoff.mode == "api_call" and handoff.api_ref:
                step = self._step_for_api_handoff(handoff, flow, blocks, used_ids)
            else:
                continue

            existing = self._matching_handoff_step(retained_steps, step, handoff)
            if existing is None:
                retained_steps.append(step)
                existing = step
            else:
                existing.text = step.text
                existing.source_span_ids = step.source_span_ids
                existing.command_type = step.command_type
                existing.inputs = step.inputs
                existing.outputs = step.outputs
                existing.integration_ref = step.integration_ref
                existing.flow_ref = step.flow_ref
                existing.block_ref = step.block_ref
                existing.kind = step.kind
                existing.handoff_id = step.handoff_id

            target_worker = target if handoff.mode == "invoke" else None
            self._declare_handoff_outputs(symbol_table, existing, handoff, target_worker)

        retained_steps.sort(
            key=lambda step: (
                self._span_sort_key(step.source_span_ids[0])
                if step.source_span_ids
                else 10**9,
                step.step_id,
            )
        )
        self._refresh_symbol_links(retained_steps, symbol_table)
        return retained_steps

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

    def _step_for_invoke_handoff(
        self,
        handoff: WorkerHandoffIR,
        target: WorkerSpecIR,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        used_ids: set[str],
    ) -> StepIR:
        source_span_ids = self._handoff_source_spans(handoff, target)
        flow_ref, block_ref = self._handoff_location(handoff, source_span_ids, flow, blocks)
        return StepIR(
            step_id=self._next_synthetic_step_id(used_ids),
            text=handoff.condition_text or target.purpose or f"Invoke {target.worker_name}",
            source_span_ids=source_span_ids,
            command_type="INVOKE_WORKER",
            inputs=[
                binding.parent_variable
                for binding in handoff.input_bindings
                if binding.parent_variable
            ],
            outputs=[
                binding.parent_variable
                for binding in handoff.output_bindings
                if binding.parent_variable
            ],
            integration_ref=target.worker_name,
            flow_ref=flow_ref,
            block_ref=block_ref,
            kind="invoke",
            handoff_id=handoff.handoff_id,
        )

    def _step_for_api_handoff(
        self,
        handoff: WorkerHandoffIR,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        used_ids: set[str],
    ) -> StepIR:
        source_span_ids = self._handoff_source_spans(handoff, None)
        flow_ref, block_ref = self._handoff_location(handoff, source_span_ids, flow, blocks)
        return StepIR(
            step_id=self._next_synthetic_step_id(used_ids),
            text=handoff.condition_text or f"Call {handoff.api_ref}",
            source_span_ids=source_span_ids,
            command_type="CALL_API",
            inputs=[
                binding.parent_variable
                for binding in handoff.input_bindings
                if binding.parent_variable
            ],
            outputs=[
                binding.parent_variable
                for binding in handoff.output_bindings
                if binding.parent_variable
            ],
            integration_ref=handoff.api_ref,
            flow_ref=flow_ref,
            block_ref=block_ref,
            kind="tool",
            handoff_id=handoff.handoff_id,
        )

    def _handoff_source_spans(
        self,
        handoff: WorkerHandoffIR,
        target: WorkerSpecIR | None,
    ) -> list[str]:
        spans = [
            span_id
            for span_id in [
                handoff.invoke_location_hint.after_span_id,
                handoff.invoke_location_hint.before_span_id,
            ]
            if span_id
        ]
        if not spans and target is not None:
            spans = list(target.owned_span_ids)
        return self._dedupe(spans)

    def _handoff_location(
        self,
        handoff: WorkerHandoffIR,
        source_span_ids: list[str],
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
    ) -> tuple[str, str]:
        hint = handoff.invoke_location_hint
        flow_ref = hint.flow_id or ("main" if hint.flow_kind == "main" else "")
        for span_id in source_span_ids:
            flow_ref = flow.get_flow_for_span(span_id) or flow_ref or "main"
            block = blocks.get_block_for_span(span_id)
            if block is not None:
                return flow_ref, block.block_id
        return flow_ref or "main", ""

    def _matching_handoff_step(
        self,
        steps: list[StepIR],
        planned_step: StepIR,
        handoff: WorkerHandoffIR,
    ) -> StepIR | None:
        for step in steps:
            if step.command_type != planned_step.command_type:
                continue
            if step.handoff_id and step.handoff_id == handoff.handoff_id:
                return step
            if step.handoff_id:
                continue
            if not self._same_handoff_location_and_bindings(step, planned_step):
                continue
            if step.integration_ref == planned_step.integration_ref:
                return step
            if (
                handoff.mode == "invoke"
                and step.integration_ref in {"Worker", "child_worker", None}
            ):
                return step
        return None

    def _same_handoff_location_and_bindings(
        self,
        step: StepIR,
        planned_step: StepIR,
    ) -> bool:
        """Match a handoff step by location and binding shape, not worker name alone."""
        if step.flow_ref and planned_step.flow_ref and step.flow_ref != planned_step.flow_ref:
            return False
        if step.block_ref and planned_step.block_ref and step.block_ref != planned_step.block_ref:
            return False
        if set(step.source_span_ids) != set(planned_step.source_span_ids):
            return False
        if list(step.inputs) != list(planned_step.inputs):
            return False
        return list(step.outputs) == list(planned_step.outputs)

    def _declare_handoff_outputs(
        self,
        symbol_table: SymbolTable,
        step: StepIR,
        handoff: WorkerHandoffIR,
        target: WorkerSpecIR | None,
    ) -> None:
        contract_types = {
            field.name: field.data_type
            for field in (target.output_contract if target is not None else [])
        }
        for binding in handoff.output_bindings:
            if binding.parent_variable not in symbol_table.variables:
                data_type = contract_types.get(binding.child_output, "text")
                symbol_table.declare(
                    binding.parent_variable,
                    data_type,
                    "step",
                    f"Output from handoff {handoff.handoff_id}.",
                    flow_ref=step.flow_ref,
                    block_ref=step.block_ref,
                )
            symbol_table.add_producer(binding.parent_variable, step.step_id)

    def _refresh_symbol_links(
        self,
        steps: list[StepIR],
        symbol_table: SymbolTable,
    ) -> None:
        for variable in symbol_table.variables.values():
            variable.consumer_steps = []
            if variable.source in {"step", "output"}:
                variable.producer_step = None
        for step in steps:
            for var_name in step.inputs:
                symbol_table.add_consumer(var_name, step.step_id)
            for var_name in step.outputs:
                symbol_table.add_producer(var_name, step.step_id)

    def _next_synthetic_step_id(self, used_ids: set[str]) -> str:
        index = 1
        while f"st_handoff_{index}" in used_ids:
            index += 1
        step_id = f"st_handoff_{index}"
        used_ids.add(step_id)
        return step_id

    def _span_sort_key(self, span_id: str) -> int:
        digits = "".join(ch for ch in span_id if ch.isdigit())
        return int(digits) if digits else 10**9

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result = []
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result
