"""Stage 9.5: IRNormalizer - Normalize and validate IRs."""

from __future__ import annotations

import re

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.flow_structure_ir import DelegationCandidate, FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, TypeSpec, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable


class IRNormalizer:
    """IR Normalization and validation.

    This stage normalizes all IRs and validates consistency across
    steps, constraints, and resources.
    """

    def normalize(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
        constraints: list[ConstraintIR],
    ) -> tuple[
        FlowStructureIR,
        BlockStructureIR,
        list[StepIR],
        list[ConstraintIR],
        SymbolTable,
        list[str],
        list[str],
    ]:
        """Normalize all IRs and validate consistency.

        Args:
            flow: Flow structure IR
            blocks: Block structure IR
            resources: Resource registry IR
            symbol_table: Symbol table
            steps: List of step IRs
            constraints: List of constraint IRs

        Returns:
            Tuple of (flow, blocks, steps, constraints, symbol_table, errors, warnings)
        """
        errors = []
        warnings = []
        self._step_replacements: dict[str, str] = {}

        # 1. Move ordinary conditional work out of exception flows.
        flow, blocks, moved_warnings = self._normalize_flow_classification(flow, blocks)
        warnings.extend(moved_warnings)

        # 2. Reconcile step flow_ref/block_ref before validations that depend on path.
        steps = self._reconcile_steps(steps, flow, blocks)
        self._sync_symbol_table_from_steps(steps, symbol_table)

        # 3. Materialize child worker candidates into concrete invocations.
        warnings.extend(
            self._materialize_child_worker_invocations(flow, blocks, symbol_table, steps)
        )
        blocks.main_flow_blocks.sort(key=self._block_sort_key)
        blocks.main_flow_blocks = self._deduplicate_blocks(blocks.main_flow_blocks)
        steps = self._reconcile_steps(steps, flow, blocks)
        self._sync_symbol_table_from_steps(steps, symbol_table)

        # 4. Normalize obvious dataflow gaps and resolve delegation targets.
        warnings.extend(self._normalize_source_retrieval_inputs(steps, symbol_table))
        errors.extend(self._resolve_worker_invocations(flow, steps, warnings))
        warnings.extend(
            self._normalize_multi_output_steps(resources, symbol_table, steps)
        )
        warnings.extend(self._ensure_required_main_outputs(blocks, resources, symbol_table, steps))

        # 5. Reconcile again for any synthetic steps.
        steps = self._reconcile_steps(steps, flow, blocks)
        self._sync_symbol_table_from_steps(steps, symbol_table)
        warnings.extend(self._prune_unused_step_variables(resources, symbol_table, steps))

        # 6. Reconcile constraint targets before reference validation.
        constraints = self._reconcile_constraints(constraints, steps, blocks)

        # 7. Validate references
        errors.extend(self._validate_references(steps, constraints, symbol_table, resources))

        # 8. Validate coverage
        warnings.extend(self._validate_coverage(flow, steps))

        # 9. Validate path consistency
        warnings.extend(self._validate_path_dataflow(steps, resources))

        # 10. Update SymbolTable with new_variables
        # (already done in Stage 7)

        return flow, blocks, steps, constraints, symbol_table, errors, warnings

    def _normalize_flow_classification(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
    ) -> tuple[FlowStructureIR, BlockStructureIR, list[str]]:
        """Move non-exception conditional spans back to the main path."""
        warnings = []
        retained_alternative_flows = []
        for alt_flow in flow.alternative_flows:
            if self._should_inline_alternative_flow(alt_flow.condition_text):
                for span_id in alt_flow.spans:
                    if span_id not in flow.main_flow_spans:
                        flow.main_flow_spans.append(span_id)
                moved_blocks = blocks.alternative_flow_blocks.pop(alt_flow.flow_id, [])
                self._append_nonduplicate_main_blocks(blocks, moved_blocks)
                warnings.append(
                    "Moved ordinary alternative flow "
                    f"{alt_flow.flow_id} into main flow: {alt_flow.condition_text}"
                )
            else:
                retained_alternative_flows.append(alt_flow)

        flow.alternative_flows = retained_alternative_flows

        retained_exception_flows = []
        for exc_flow in flow.exception_flows:
            if self._is_loop_condition(exc_flow.condition_text):
                for span_id in exc_flow.spans:
                    if span_id not in flow.main_flow_spans:
                        flow.main_flow_spans.append(span_id)
                moved_blocks = blocks.exception_flow_blocks.pop(exc_flow.flow_id, [])
                for block in moved_blocks:
                    block.block_type = "WHILE"
                    block.condition_text = self._loop_condition_text(exc_flow.condition_text)
                self._append_nonduplicate_main_blocks(blocks, moved_blocks)
                warnings.append(
                    "Moved loop-like exception flow "
                    f"{exc_flow.flow_id} into main flow: {exc_flow.condition_text}"
                )
                continue

            if self._is_exception_condition(exc_flow.condition_text):
                retained_exception_flows.append(exc_flow)
                continue

            for span_id in exc_flow.spans:
                if span_id not in flow.main_flow_spans:
                    flow.main_flow_spans.append(span_id)
            moved_blocks = blocks.exception_flow_blocks.pop(exc_flow.flow_id, [])
            self._append_nonduplicate_main_blocks(blocks, moved_blocks)
            warnings.append(
                "Moved non-exception conditional flow "
                f"{exc_flow.flow_id} into main flow: {exc_flow.condition_text}"
            )

        flow.exception_flows = retained_exception_flows
        flow.main_flow_spans = self._sort_span_ids(flow.main_flow_spans)
        blocks.main_flow_blocks.sort(key=self._block_sort_key)
        blocks.main_flow_blocks = self._deduplicate_blocks(blocks.main_flow_blocks)
        return flow, blocks, warnings

    def _should_inline_alternative_flow(self, condition_text: str) -> bool:
        """Return True when an alternative is ordinary conditional work."""
        text = condition_text.strip().lower()
        return text.startswith(("if ", "when ")) and not self._is_exception_condition(text)

    def _append_nonduplicate_main_blocks(
        self,
        blocks: BlockStructureIR,
        moved_blocks: list[BlockIR],
    ) -> None:
        """Append moved blocks unless their span set is already represented."""
        existing_span_sets = {tuple(block.spans) for block in blocks.main_flow_blocks}
        for block in moved_blocks:
            signature = tuple(block.spans)
            if signature and signature in existing_span_sets:
                continue
            blocks.main_flow_blocks.append(block)
            existing_span_sets.add(signature)

    def _deduplicate_blocks(self, blocks: list[BlockIR]) -> list[BlockIR]:
        """Remove duplicate block span sets while preserving the first block."""
        seen = set()
        deduped = []
        for block in blocks:
            signature = tuple(block.spans)
            if signature and signature in seen:
                continue
            seen.add(signature)
            deduped.append(block)
        return deduped

    def _sync_symbol_table_from_steps(
        self,
        steps: list[StepIR],
        symbol_table: SymbolTable,
    ) -> None:
        """Refresh producer and consumer links from StepIR."""
        for variable in symbol_table.variables.values():
            variable.consumer_steps = []
            if variable.source in {"step", "output"}:
                variable.producer_step = None

        for step in steps:
            for input_name in step.inputs:
                symbol_table.add_consumer(input_name, step.step_id)
            for output_name in step.outputs:
                symbol_table.add_producer(output_name, step.step_id)

    def _is_loop_condition(self, condition_text: str) -> bool:
        """Return True for gate conditions that require repeated resolution."""
        text = condition_text.lower()
        return "do not finalize" in text and "missing" in text

    def _loop_condition_text(self, condition_text: str) -> str:
        """Rewrite a gate sentence into a WHILE condition."""
        text = condition_text.strip().rstrip(".")
        if self._is_loop_condition(text):
            return (
                "required slots remain missing and the draft is not explicitly "
                "marked as assumption-bearing with user confirmation"
            )
        return text

    def _is_exception_condition(self, condition_text: str) -> bool:
        """Return True when a condition describes failure, blocking, or refusal."""
        text = condition_text.lower()
        exception_markers = (
            "fail",
            "failure",
            "error",
            "exception",
            "missing",
            "invalid",
            "conflict",
            "insufficient",
            "shortage",
            "refusal",
            "refuse",
            "unavailable",
            "blocked",
            "deny",
            "do not finalize",
            "cannot",
            "provenance failure",
        )
        return any(marker in text for marker in exception_markers)

    def _sort_span_ids(self, span_ids: list[str]) -> list[str]:
        """Sort span ids by numeric suffix while preserving unknown ids."""
        return sorted(dict.fromkeys(span_ids), key=self._span_sort_key)

    def _block_sort_key(self, block: object) -> tuple[int, str]:
        """Sort blocks by their earliest source span."""
        spans = getattr(block, "spans", [])
        if not spans:
            return (10**9, getattr(block, "block_id", ""))
        return (
            min(self._span_sort_key(span_id) for span_id in spans),
            getattr(block, "block_id", ""),
        )

    def _span_sort_key(self, span_id: str) -> int:
        digits = "".join(ch for ch in span_id if ch.isdigit())
        return int(digits) if digits else 10**9

    def _materialize_child_worker_invocations(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
    ) -> list[str]:
        """Turn child-worker delegation candidates into concrete invocations."""
        warnings = []
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
            key=lambda candidate: self._span_sort_key(candidate.spans[0])
            if candidate.spans
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
            mapped_inputs = []
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
        """Ensure delegated normal-work spans have a main-flow block."""
        if not candidate.spans:
            return

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
    ) -> list[str]:
        """Attach concrete child worker names to INVOKE_WORKER steps."""
        errors = []
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

    def _compact_step_id(self, step_id: str) -> str:
        """Return st_12 as st12 for reconciling LLM target variants."""
        return re.sub(r"^st_", "st", step_id)

    def _normalize_source_retrieval_inputs(
        self,
        steps: list[StepIR],
        symbol_table: SymbolTable,
    ) -> list[str]:
        """Prefer declared runtime inputs over unproduced planning variables."""
        if "available_connectors" not in symbol_table.variables:
            return []

        warnings = []
        for step in steps:
            text = step.text.lower()
            if "retriev" not in text and "gather" not in text:
                continue
            original_inputs = list(step.inputs)
            step.inputs = [
                name
                for name in step.inputs
                if not self._is_unproduced_step_variable(name, symbol_table)
            ]
            if "available_connectors" not in step.inputs:
                step.inputs.append("available_connectors")
            if step.inputs != original_inputs:
                warnings.append(
                    f"Normalized source retrieval inputs for step {step.step_id}."
                )
        return warnings

    def _prune_unused_step_variables(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
    ) -> list[str]:
        """Remove orphan step variables left behind by earlier LLM stages."""
        used_names = {
            name
            for step in steps
            for name in [*step.inputs, *step.outputs]
        }
        pruned = [
            variable.name
            for variable in resources.variables
            if variable.source == "step" and variable.name not in used_names
        ]
        if not pruned:
            return []

        resources.variables = [
            variable
            for variable in resources.variables
            if variable.name not in pruned
        ]
        for name in pruned:
            symbol_table.variables.pop(name, None)

        return [f"Pruned unused step variable: {name}" for name in pruned]

    def _normalize_multi_output_steps(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
    ) -> list[str]:
        """Aggregate multi-output commands into one structured result variable."""
        warnings = []
        used_ids = {step.step_id for step in steps}
        normalized_steps: list[StepIR] = []

        for step in steps:
            normalized_steps.append(step)
            if len(step.outputs) <= 1:
                continue

            original_outputs = list(step.outputs)
            result_name = self._aggregate_result_name(step)
            type_name = self._aggregate_type_name(result_name)
            definition = self._structured_type_definition(original_outputs, symbol_table)

            self._ensure_type(resources, type_name, definition)
            self._ensure_variable(
                resources,
                symbol_table,
                result_name,
                type_name,
                f"Structured result for {step.step_id}.",
            )
            step.outputs = [result_name]
            symbol_table.add_producer(result_name, step.step_id)

            for output_name in original_outputs:
                unpack_step_id = self._next_synthetic_step_id(used_ids)
                unpack_step = StepIR(
                    step_id=unpack_step_id,
                    text=f"Extract {output_name} from {result_name}",
                    source_span_ids=[],
                    command_type="GENERAL_COMMAND",
                    inputs=[result_name],
                    outputs=[output_name],
                    flow_ref=step.flow_ref,
                    block_ref=step.block_ref,
                )
                normalized_steps.append(unpack_step)
                symbol_table.add_producer(output_name, unpack_step_id)

            warnings.append(
                f"Aggregated multi-output step {step.step_id} into {result_name}: {type_name}."
            )

        steps[:] = normalized_steps
        return warnings

    def _aggregate_result_name(self, step: StepIR) -> str:
        base = step.integration_ref or step.step_id
        return f"{self._safe_name(base)}_result"

    def _aggregate_type_name(self, result_name: str) -> str:
        return "".join(
            part[:1].upper() + part[1:]
            for part in self._safe_name(result_name).split("_")
            if part
        )

    def _safe_name(self, name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", name.strip())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_").lower()
        return cleaned or "step"

    def _structured_type_definition(
        self,
        field_names: list[str],
        symbol_table: SymbolTable,
    ) -> str:
        fields = []
        for field_name in field_names:
            data_type = self._format_struct_data_type(
                symbol_table.variables.get(field_name).data_type
                if field_name in symbol_table.variables
                else "text"
            )
            fields.append(f"{field_name}: {data_type}")
        return "{ " + ", ".join(fields) + " }"

    def _format_struct_data_type(self, data_type: str) -> str:
        return re.sub(r"List\s*\[\s*([^\]]+)\s*\]", r"List [\1]", data_type.strip())

    def _ensure_type(
        self,
        resources: ResourceRegistryIR,
        type_name: str,
        definition: str,
    ) -> None:
        if any(type_spec.type_name == type_name for type_spec in resources.types):
            return
        resources.types.append(TypeSpec(type_name, "structured", definition))

    def _ensure_variable(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        name: str,
        data_type: str,
        description: str,
    ) -> None:
        if not any(variable.name == name for variable in resources.variables):
            resources.variables.append(
                VariableSpec(
                    name=name,
                    data_type=data_type,
                    required=True,
                    description=description,
                    source="step",
                )
            )
        if name not in symbol_table.variables:
            symbol_table.declare(name, data_type, "step", description)

    def _is_unproduced_step_variable(self, name: str, symbol_table: SymbolTable) -> bool:
        var = symbol_table.variables.get(name)
        return bool(var and var.source == "step" and not var.producer_step)

    def _ensure_required_main_outputs(
        self,
        blocks: BlockStructureIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
    ) -> list[str]:
        """Ensure every required output has a producer on the normal path."""
        warnings = []
        required_outputs = [
            var.name
            for var in resources.variables
            if var.source == "output" and var.required
        ]
        produced_on_main = {
            output
            for step in steps
            if step.flow_ref == "main"
            for output in step.outputs
        }
        missing_outputs = [
            output for output in required_outputs if output not in produced_on_main
        ]
        if not missing_outputs:
            return warnings

        block_id = self._normal_completion_block_id(blocks)
        used_ids = {step.step_id for step in steps}
        existing_main_outputs = [
            output
            for output in required_outputs
            if output in produced_on_main
        ]
        for output in missing_outputs:
            step_id = self._next_synthetic_step_id(used_ids)
            text = self._completion_step_text(output)
            inputs = self._completion_inputs_for_output(
                output,
                existing_main_outputs,
                symbol_table,
            )
            step = StepIR(
                step_id=step_id,
                text=text,
                source_span_ids=[],
                command_type="GENERAL_COMMAND",
                inputs=inputs,
                outputs=[output],
                flow_ref="main",
                block_ref=block_id,
            )
            steps.append(step)
            symbol_table.add_producer(output, step_id)
            warnings.append(f"Added normal-path producer for required output {output}.")

        return warnings

    def _completion_inputs_for_output(
        self,
        output: str,
        existing_main_outputs: list[str],
        symbol_table: SymbolTable,
    ) -> list[str]:
        """Choose semantically useful inputs for synthetic completion outputs."""
        if output == "source_evidence_set":
            evidence_inputs = [
                name
                for name in ("retrieved_sources", "provenance_log")
                if name in symbol_table.variables
            ]
            if evidence_inputs:
                return evidence_inputs

        return [name for name in existing_main_outputs if name != output]

    def _normal_completion_block_id(self, blocks: BlockStructureIR) -> str:
        """Return a main-flow block id suitable for synthetic completion steps."""
        if not blocks.main_flow_blocks:
            from nl2spl.ir.block_structure_ir import BlockIR

            blocks.main_flow_blocks.append(BlockIR("b_normal_completion", "SEQUENTIAL", None, []))
            return "b_normal_completion"

        last_block = blocks.main_flow_blocks[-1]
        if last_block.block_type == "SEQUENTIAL":
            return last_block.block_id

        from nl2spl.ir.block_structure_ir import BlockIR

        block_id = self._next_block_id(blocks)
        blocks.main_flow_blocks.append(BlockIR(block_id, "SEQUENTIAL", None, []))
        return block_id

    def _next_block_id(self, blocks: BlockStructureIR) -> str:
        used = {block.block_id for block in blocks.get_all_blocks()}
        index = 1
        while f"b_norm_{index}" in used:
            index += 1
        return f"b_norm_{index}"

    def _next_synthetic_step_id(self, used_ids: set[str]) -> str:
        index = 1
        while f"st_norm_{index}" in used_ids:
            index += 1
        step_id = f"st_norm_{index}"
        used_ids.add(step_id)
        return step_id

    def _completion_step_text(self, output: str) -> str:
        text_by_output = {
            "assumptions_log": "Record assumptions for unresolved items",
            "completion_status": "Set completion status for the normal completion path",
            "source_evidence_set": "Produce the source evidence set for normal completion",
            "draft": "Produce the draft for normal completion",
        }
        return text_by_output.get(output, f"Produce required output {output}")

    def _validate_references(
        self,
        steps: list[StepIR],
        constraints: list[ConstraintIR],
        symbol_table: SymbolTable,
        resources: ResourceRegistryIR,
    ) -> list[str]:
        """Validate all references.

        Args:
            steps: List of step IRs
            constraints: List of constraint IRs
            symbol_table: Symbol table
            resources: Resource registry IR

        Returns:
            List of validation errors
        """
        errors = []
        step_ids = {s.step_id for s in steps}
        api_names = {a.api_name for a in resources.apis}

        # Validate step variable references
        for step in steps:
            for var_name in step.inputs + step.outputs:
                if var_name not in symbol_table.variables:
                    errors.append(f"Step {step.step_id} references unknown variable: {var_name}")

            if (
                step.command_type == "CALL_API"
                and step.integration_ref
                and step.integration_ref not in api_names
            ):
                errors.append(f"Step {step.step_id} references unknown API: {step.integration_ref}")

        # Validate constraint targets
        for constraint in constraints:
            for target in constraint.targets:
                if ":" in target:
                    target_type, target_id = target.split(":", 1)
                    if target_type == "step" and target_id not in step_ids:
                        errors.append(
                            "Constraint "
                            f"{constraint.constraint_id} references unknown step: {target_id}"
                        )
                    elif target_type == "variable" and target_id not in symbol_table.variables:
                        errors.append(
                            "Constraint "
                            f"{constraint.constraint_id} references unknown variable: {target_id}"
                        )

        return errors

    def _validate_coverage(self, flow: FlowStructureIR, steps: list[StepIR]) -> list[str]:
        """Validate all spans are covered by steps.

        Args:
            flow: Flow structure IR
            steps: List of step IRs

        Returns:
            List of validation warnings
        """
        warnings = []
        flow_spans = flow.get_all_flow_spans()
        covered_spans = set()
        for step in steps:
            covered_spans.update(step.source_span_ids)

        uncovered = flow_spans - covered_spans
        if uncovered:
            warnings.append(f"Spans not covered by any step: {uncovered}")

        return warnings

    def _reconcile_steps(
        self, steps: list[StepIR], flow: FlowStructureIR, blocks: BlockStructureIR
    ) -> list[StepIR]:
        """Reconcile step flow_ref and block_ref.

        Args:
            steps: List of step IRs
            flow: Flow structure IR
            blocks: Block structure IR

        Returns:
            List of reconciled step IRs
        """
        for step in steps:
            if not step.flow_ref:
                if step.source_span_ids:
                    step.flow_ref = flow.get_flow_for_span(step.source_span_ids[0]) or "main"
                else:
                    step.flow_ref = "main"
            elif step.source_span_ids:
                step.flow_ref = flow.get_flow_for_span(step.source_span_ids[0]) or step.flow_ref
            if not step.block_ref:
                block = None
                if step.source_span_ids:
                    block = blocks.get_block_for_span(step.source_span_ids[0])
                step.block_ref = block.block_id if block else ""
            elif step.source_span_ids:
                block = blocks.get_block_for_span(step.source_span_ids[0])
                if block:
                    step.block_ref = block.block_id
        return steps

    def _validate_path_dataflow(
        self,
        steps: list[StepIR],
        resources: ResourceRegistryIR,
    ) -> list[str]:
        """Warn when a main-path step consumes a value before a main-path producer."""
        warnings = []
        runtime_inputs = {
            var.name for var in resources.variables if var.source in {"input", "file"}
        }
        produced = set(runtime_inputs)

        main_steps = [step for step in steps if step.flow_ref == "main"]
        main_steps.sort(
            key=lambda step: (
                self._span_sort_key(step.source_span_ids[0])
                if step.source_span_ids
                else 10**9,
                step.step_id,
            )
        )

        for step in main_steps:
            for input_name in step.inputs:
                if input_name not in produced:
                    warnings.append(
                        f"Main-path step {step.step_id} consumes {input_name} before a producer."
                    )
            produced.update(step.outputs)

        return warnings

    def _reconcile_constraints(
        self, constraints: list[ConstraintIR], steps: list[StepIR], blocks: BlockStructureIR
    ) -> list[ConstraintIR]:
        """Reconcile constraint targets.

        Args:
            constraints: List of constraint IRs
            steps: List of step IRs
            blocks: Block structure IR

        Returns:
            List of reconciled constraint IRs
        """
        step_ids = {step.step_id for step in steps}
        compact_to_step_id = {
            self._compact_step_id(step_id): step_id for step_id in step_ids
        }

        for constraint in constraints:
            if not constraint.targets:
                constraint.targets = ["global"]
                continue

            reconciled_targets = []
            for target in constraint.targets:
                if not target.startswith("step:"):
                    reconciled_targets.append(target)
                    continue

                target_id = target.split(":", 1)[1]
                replacement = (
                    self._step_replacements.get(target_id)
                    or compact_to_step_id.get(target_id)
                    or target_id
                )
                reconciled_targets.append(f"step:{replacement}")
            constraint.targets = reconciled_targets
        return constraints
