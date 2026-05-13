"""Worker handoff methods for Stage 9.5 IRNormalizer."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import DelegationCandidate, FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerHandoffIR, WorkerPlanIR, WorkerSpecIR


class WorkerHandoffsMixin:
    """Mixin class containing worker handoff methods for IRNormalizer."""

    def _materialize_child_worker_invocations(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
    ) -> list[str]:
        """Turn child-worker delegation candidates into concrete invocations."""
        warnings: list[str] = []
        child_candidates = [
            candidate
            for candidate in flow.delegation_candidates
            if candidate.suggested_type == "child_worker"
        ]
        if not child_candidates:
            return warnings

        used_ids = {step.step_id for step in steps}
        original_indexes = {id(step): index for index, step in enumerate(steps)}
        materialized_steps: list[StepIR] = []
        skipped_step_ids: set[str] = set()

        for candidate in sorted(
            child_candidates,
            key=lambda c: self._span_sort_key(c.spans[0])
            if c.spans
            else 10**9,
        ):
            self._ensure_candidate_spans_in_main_flow(flow, blocks, candidate)
            candidate_spans = set(candidate.spans)
            child_name = self._child_worker_name(candidate.candidate_id)
            invoke_step = next(
                (
                    step
                    for step in steps
                    if step.command_type == "INVOKE_WORKER"
                    and candidate_spans.intersection(step.source_span_ids)
                ),
                None,
            )

            first_span = self._sort_span_ids(candidate.spans)[0] if candidate.spans else ""
            block = blocks.get_block_for_span(first_span) if first_span else None
            flow_ref = flow.get_flow_for_span(first_span) or "main"
            block_ref = block.block_id if block else ""

            if invoke_step is None:
                invoke_step = StepIR(
                    step_id=self._next_synthetic_step_id(used_ids),
                    text=candidate.reason,
                    source_span_ids=self._sort_span_ids(candidate.spans),
                    command_type="INVOKE_WORKER",
                    inputs=list(candidate.input_variables),
                    outputs=list(candidate.output_variables),
                    integration_ref=child_name,
                    flow_ref=flow_ref,
                    block_ref=block_ref,
                    kind="invoke",
                )
                materialized_steps.append(invoke_step)
                warnings.append(
                    "Materialized child worker invocation "
                    f"{invoke_step.step_id} for delegation candidate {candidate.candidate_id}."
                )
            else:
                invoke_step.text = candidate.reason
                invoke_step.source_span_ids = self._sort_span_ids(candidate.spans)
                invoke_step.outputs = list(candidate.output_variables)
                invoke_step.integration_ref = child_name
                invoke_step.flow_ref = flow_ref
                invoke_step.block_ref = block_ref
                if invoke_step.kind != "invoke":
                    invoke_step.kind = "invoke"
                warnings.append(
                    "Expanded existing INVOKE_WORKER step "
                    f"{invoke_step.step_id} to delegation candidate {candidate.candidate_id}."
                )

            self._normalize_delegated_step_io(symbol_table, invoke_step)

            for step in steps:
                if step is invoke_step:
                    continue
                if candidate_spans.intersection(step.source_span_ids):
                    skipped_step_ids.add(step.step_id)
                    self._step_replacements[step.step_id] = invoke_step.step_id
                    self._step_replacements[
                        self._compact_step_id(step.step_id)
                    ] = invoke_step.step_id

        retained_steps = [
            step for step in steps if step.step_id not in skipped_step_ids
        ]
        retained_steps.extend(materialized_steps)
        retained_steps.sort(
            key=lambda step: (
                self._span_sort_key(step.source_span_ids[0])
                if step.source_span_ids
                else 10**9,
                original_indexes.get(id(step), 10**9),
                step.step_id,
            )
        )

        steps[:] = retained_steps
        for skipped_step_id in skipped_step_ids:
            warnings.append(f"Replaced delegated step {skipped_step_id} with child worker invoke.")

        self._sync_symbol_table_from_steps(steps, symbol_table)
        return warnings

    def _materialize_worker_plan_handoffs(
        self,
        worker_plan: WorkerPlanIR,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
    ) -> list[str]:
        """Create or repair steps from WorkerPlanIR handoffs."""
        warnings: list[str] = []
        worker_by_id = {worker.worker_id: worker for worker in worker_plan.workers}
        child_span_ids = {
            span_id
            for worker in worker_plan.workers
            if worker.kind != "main"
            for span_id in worker.owned_span_ids
        }

        retained_steps = [
            step
            for step in steps
            if not child_span_ids.intersection(step.source_span_ids)
            or step.command_type in {"INVOKE_WORKER", "CALL_API"}
        ]
        removed_step_ids = {step.step_id for step in steps} - {
            step.step_id for step in retained_steps
        }
        for step_id in removed_step_ids:
            warnings.append(
                f"Removed child-owned behavior step {step_id}; WorkerPlanIR owns the handoff."
            )

        used_ids = {step.step_id for step in retained_steps}
        for handoff in worker_plan.handoffs:
            planned_step = self._planned_handoff_step(
                handoff,
                worker_by_id,
                flow,
                blocks,
                used_ids,
            )
            if planned_step is None:
                continue

            existing = self._matching_worker_plan_step(retained_steps, planned_step)
            if existing is None:
                retained_steps.append(planned_step)
                existing = planned_step
                warnings.append(
                    f"Materialized {planned_step.command_type} step "
                    f"{planned_step.step_id} from handoff {handoff.handoff_id}."
                )
            else:
                existing.text = planned_step.text
                existing.source_span_ids = planned_step.source_span_ids
                existing.command_type = planned_step.command_type
                existing.inputs = planned_step.inputs
                existing.outputs = planned_step.outputs
                existing.integration_ref = planned_step.integration_ref
                existing.flow_ref = planned_step.flow_ref
                existing.block_ref = planned_step.block_ref
                existing.kind = planned_step.kind
                existing.handoff_id = planned_step.handoff_id

            target_worker = worker_by_id.get(handoff.to_worker or "")
            self._ensure_handoff_output_variables(symbol_table, existing, handoff, target_worker)

        retained_steps.sort(
            key=lambda step: (
                self._span_sort_key(step.source_span_ids[0])
                if step.source_span_ids
                else 10**9,
                step.step_id,
            )
        )
        self._sync_symbol_table_from_steps(retained_steps, symbol_table)
        steps[:] = retained_steps
        return warnings

    def _planned_handoff_step(
        self,
        handoff: WorkerHandoffIR,
        worker_by_id: dict[str, WorkerSpecIR],
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        used_ids: set[str],
    ) -> StepIR | None:
        """Build the StepIR that should represent one handoff."""
        target = worker_by_id.get(handoff.to_worker or "")
        if handoff.mode == "invoke":
            if target is None:
                return None
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

        if handoff.mode == "api_call" and handoff.api_ref:
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

        return None

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
        return list(dict.fromkeys(spans))

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

    def _matching_worker_plan_step(
        self,
        steps: list[StepIR],
        planned_step: StepIR,
    ) -> StepIR | None:
        for step in steps:
            if step.command_type != planned_step.command_type:
                continue
            if step.handoff_id and step.handoff_id == planned_step.handoff_id:
                return step
            if step.handoff_id:
                continue
            if not self._same_handoff_location_and_bindings(step, planned_step):
                continue
            if step.integration_ref == planned_step.integration_ref:
                return step
            if (
                planned_step.command_type == "INVOKE_WORKER"
                and step.integration_ref in {None, "Worker", "child_worker"}
            ):
                return step
        return None

    def _same_handoff_location_and_bindings(
        self,
        step: StepIR,
        planned_step: StepIR,
    ) -> bool:
        """Match a handoff by location and IO, not only integration_ref."""
        if step.flow_ref and planned_step.flow_ref and step.flow_ref != planned_step.flow_ref:
            return False
        if step.block_ref and planned_step.block_ref and step.block_ref != planned_step.block_ref:
            return False
        if set(step.source_span_ids) != set(planned_step.source_span_ids):
            return False
        if list(step.inputs) != list(planned_step.inputs):
            return False
        return list(step.outputs) == list(planned_step.outputs)

    def _ensure_handoff_output_variables(
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
                symbol_table.declare(
                    binding.parent_variable,
                    contract_types.get(binding.child_output, "text"),
                    "step",
                    f"Output from handoff {handoff.handoff_id}.",
                    step.flow_ref,
                    step.block_ref,
                )
            symbol_table.add_producer(binding.parent_variable, step.step_id)

    def _normalize_delegated_step_io(
        self,
        symbol_table: SymbolTable,
        step: StepIR,
    ) -> None:
        """Map delegated task IO onto variables that exist on the main path."""
        text = step.text.lower()
        if "source" in text or "retriev" in text or "provenance" in text:
            if "available_connectors" in symbol_table.variables:
                step.inputs = ["available_connectors"]

        if "revision" in text or "revise" in text:
            mapped_inputs: list[str] = []
            if "draft_communication_artifact" in symbol_table.variables:
                mapped_inputs.append("draft_communication_artifact")
            elif "draft_artifact" in symbol_table.variables:
                mapped_inputs.append("draft_artifact")
            elif "draft" in step.inputs:
                mapped_inputs.append("draft")

            if "user_request" in symbol_table.variables:
                mapped_inputs.append("user_request")
            elif "user_revision_request" in step.inputs:
                mapped_inputs.append("user_revision_request")

            if mapped_inputs:
                step.inputs = list(dict.fromkeys(mapped_inputs))

            if "draft_communication_artifact" in symbol_table.variables:
                step.outputs = ["draft_communication_artifact"]
            elif "draft_artifact" in symbol_table.variables:
                step.outputs = ["draft_artifact"]

    def _ensure_candidate_spans_in_main_flow(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        candidate: DelegationCandidate,
    ) -> None:
        missing_spans = [
            span_id
            for span_id in candidate.spans
            if flow.get_flow_for_span(span_id) is None
        ]
        if not missing_spans:
            return

        for span_id in missing_spans:
            if span_id not in flow.main_flow_spans:
                flow.main_flow_spans.append(span_id)

        existing_block = next(
            (
                block
                for block in blocks.main_flow_blocks
                if any(span_id in block.spans for span_id in candidate.spans)
            ),
            None,
        )
        if existing_block:
            for span_id in candidate.spans:
                if span_id not in existing_block.spans:
                    existing_block.spans.append(span_id)
            existing_block.spans = self._sort_span_ids(existing_block.spans)
            return

        block_id = self._next_block_id(blocks)
        block_type = "IF" if self._is_source_candidate(candidate) else "SEQUENTIAL"
        condition_text = "If sources are needed and available" if block_type == "IF" else None
        blocks.main_flow_blocks.append(
            BlockIR(
                block_id,
                block_type,
                condition_text,
                self._sort_span_ids(candidate.spans),
            )
        )

    def _is_source_candidate(self, candidate: DelegationCandidate) -> bool:
        """Return True for source retrieval/provenance delegation."""
        text = f"{candidate.reason} {' '.join(candidate.output_variables)}".lower()
        return "source" in text or "retriev" in text or "provenance" in text

    def _resolve_worker_invocations(
        self,
        flow: FlowStructureIR,
        steps: list[StepIR],
        warnings: list[str],
        worker_plan: WorkerPlanIR | None = None,
    ) -> list[str]:
        """Attach concrete child worker names to INVOKE_WORKER steps."""
        errors: list[str] = []
        if worker_plan is not None:
            worker_by_id = {worker.worker_id: worker for worker in worker_plan.workers}
            known_worker_names = {
                worker_by_id[handoff.to_worker].worker_name
                for handoff in worker_plan.handoffs
                if handoff.mode == "invoke"
                and handoff.to_worker in worker_by_id
                and worker_by_id[handoff.to_worker].kind != "main"
            }

            for step in steps:
                if step.command_type != "INVOKE_WORKER":
                    continue
                if not step.integration_ref or step.integration_ref in {"Worker", "child_worker"}:
                    errors.append(
                        f"Step {step.step_id} is INVOKE_WORKER but has no concrete child worker."
                    )
                elif step.integration_ref not in known_worker_names:
                    errors.append(
                        f"Step {step.step_id} invokes worker not present in WorkerPlanIR handoffs: "
                        f"{step.integration_ref}."
                    )
            return errors

        child_candidates: list[DelegationCandidate] = [
            candidate
            for candidate in flow.delegation_candidates
            if candidate.suggested_type == "child_worker"
        ]
        candidate_names = {
            candidate.candidate_id: self._child_worker_name(candidate.candidate_id)
            for candidate in child_candidates
        }
        known_worker_names = set(candidate_names.values())

        for step in steps:
            if step.command_type != "INVOKE_WORKER":
                continue

            if step.integration_ref in known_worker_names:
                continue

            matched_candidate = self._matching_child_candidate(step, child_candidates)
            if matched_candidate:
                step.integration_ref = candidate_names[matched_candidate.candidate_id]
                warnings.append(
                    "Resolved INVOKE_WORKER step "
                    f"{step.step_id} to child worker {step.integration_ref}."
                )
                continue

            if not step.integration_ref or step.integration_ref in {"Worker", "child_worker"}:
                errors.append(
                    f"Step {step.step_id} is INVOKE_WORKER but has no concrete child worker."
                )

        return errors

    def _matching_child_candidate(
        self,
        step: StepIR,
        candidates: list[DelegationCandidate],
    ) -> DelegationCandidate | None:
        """Return the child-worker candidate whose spans overlap the step."""
        step_spans = set(step.source_span_ids)
        if not step_spans:
            return None

        for candidate in candidates:
            if step_spans.intersection(candidate.spans):
                return candidate
        return None

    def _child_worker_name(self, candidate_id: str) -> str:
        """Return the concrete child worker name for a delegation candidate."""
        return f"child_{candidate_id}"
