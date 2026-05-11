"""Stage 7: StepExtractor - Extract atomic actions from spans."""

from __future__ import annotations

import json
from dataclasses import asdict

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerHandoffIR, WorkerPlanIR, WorkerSpecIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


class StepExtractor(
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable]
        | tuple[
            list[SpanIR],
            FieldRouteIR,
            FlowStructureIR,
            BlockStructureIR,
            SymbolTable,
            WorkerPlanIR,
        ],
        tuple[list[StepIR], SymbolTable],
    ]
):
    """Extract atomic actions (steps) from behavior spans.

    This stage takes behavior spans, field routes, flow structure,
    block structure, and symbol table, then extracts steps with
    their input/output variables.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage7_step_extractor"

    def execute(
        self,
        input_data: tuple[
            list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable
        ]
        | tuple[
            list[SpanIR],
            FieldRouteIR,
            FlowStructureIR,
            BlockStructureIR,
            SymbolTable,
            WorkerPlanIR,
        ],
    ) -> tuple[list[StepIR], SymbolTable]:
        """Execute step extraction.

        Args:
            input_data: Tuple of (spans, field routes, flow structure,
                       block structure, symbol table)

        Returns:
            Tuple of (list of StepIR, updated SymbolTable)

        Raises:
            StageError: If step extraction fails
        """
        worker_plan = input_data[5] if len(input_data) == 6 else None
        spans, routes, flow_structure, block_structure, symbol_table = input_data[:5]
        self.logger.info(
            "Starting step extraction with %d spans and %d known variables",
            len(spans),
            len(symbol_table.variables),
        )

        # 1. Build prompts with variable list
        behavior_span_ids = list(routes.behavior)
        if worker_plan is not None:
            self._assert_legacy_main_view_excludes_child_spans(
                flow_structure,
                worker_plan,
            )
            main_view_span_ids = flow_structure.get_all_flow_spans()
            if main_view_span_ids:
                behavior_span_ids = [
                    span_id for span_id in behavior_span_ids if span_id in main_view_span_ids
                ]
        behavior_spans = [s for s in spans if s.span_id in set(behavior_span_ids)]
        behavior_json = json.dumps(
            [s.to_dict() for s in behavior_spans], ensure_ascii=False
        )
        flow_json = json.dumps(asdict(flow_structure), ensure_ascii=False)
        blocks_json = json.dumps(asdict(block_structure), ensure_ascii=False)
        variable_list = symbol_table.get_variable_list_for_prompt()

        system_prompt = load_prompt("stage7").replace(
            "{variable_list}", variable_list
        )
        user_prompt = f"""请从以下文本中提取 step：

behavior spans：
---
{behavior_json}
---

Flow 结构：
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

输出 JSON："""

        # 2. Call LLM
        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed: %s", e)
            raise StageError(
                message=f"LLM call failed in {self.name}: {e}",
                stage=self.name,
            ) from e

        # 3. Parse steps (just parse, don't update symbol table yet)
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

        # 4. Handle new_variables (declare before updating producers/consumers)
        for new_var_data in result.get("new_variables", []):
            try:
                new_var_name = new_var_data["name"]
                if new_var_name not in symbol_table.variables:
                    symbol_table.declare(
                        name=new_var_name,
                        data_type=new_var_data.get("data_type", "text"),
                        source="step",
                        description=new_var_data.get("description", ""),
                    )
                    symbol_table.add_producer(
                        new_var_name, new_var_data.get("producer_step", "")
                    )
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid new variable: %s", e)
                continue

        # 5. Update SymbolTable with producer/consumer (after new_variables are declared)
        for step in steps:
            for var_name in step.inputs:
                symbol_table.add_consumer(var_name, step.step_id)
            for var_name in step.outputs:
                symbol_table.add_producer(var_name, step.step_id)

        if worker_plan is not None:
            steps = self._apply_worker_plan_handoffs(
                steps,
                worker_plan,
                flow_structure,
                block_structure,
                symbol_table,
            )

        self.logger.info(
            "Extracted %d steps, %d new variables",
            len(steps),
            len(result.get("new_variables", [])),
        )

        # 6. Save checkpoint
        self.save_checkpoint({
            "steps": [asdict(s) for s in steps],
            "new_variables": result.get("new_variables", []),
        })

        return steps, symbol_table

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
