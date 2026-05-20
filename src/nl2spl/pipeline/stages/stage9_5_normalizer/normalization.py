"""Normalization methods for Stage 9.5 IRNormalizer."""

from __future__ import annotations

from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, TypeSpec, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerPlanIR


class NormalizationMixin:
    """Mixin class containing normalization methods for IRNormalizer."""

    def _normalize_source_retrieval_inputs(
        self,
        steps: list[StepIR],
        symbol_table: SymbolTable,
    ) -> list[str]:
        """Prefer declared runtime inputs over unproduced planning variables."""
        warnings: list[str] = []
        if "available_connectors" not in symbol_table.variables:
            return warnings

        for step in steps:
            if step.command_type != "GENERAL_COMMAND":
                continue
            text = step.text.lower()
            if "source" not in text and "retriev" not in text and "provenance" not in text:
                continue
            if "available_connectors" in step.inputs:
                continue
            step.inputs = ["available_connectors"]
            warnings.append(
                f"Remapped inputs for step {step.step_id} to available_connectors."
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

        self._pruned_variable_names.update(pruned)
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
        warnings: list[str] = []
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
                    metadata={"origin": "compiler_unpack"},
                )
                normalized_steps.append(unpack_step)
                symbol_table.add_producer(output_name, unpack_step_id)

            warnings.append(
                f"Aggregated multi-output step {step.step_id} into "
                f"{result_name} with {len(original_outputs)} unpack steps."
            )

        steps[:] = normalized_steps
        return warnings

    def _aggregate_result_name(self, step: StepIR) -> str:
        """Derive a structured result variable name from a step."""
        base = step.outputs[0] if step.outputs else "result"
        return f"{self._safe_name(base)}_structured"

    def _aggregate_type_name(self, result_name: str) -> str:
        """Derive a type name for an aggregated result."""
        return f"{self._safe_name(result_name)}_type"

    def _structured_type_definition(
        self,
        original_outputs: list[str],
        symbol_table: SymbolTable,
    ) -> dict[str, str]:
        """Build a structured type definition from original outputs."""
        definition: dict[str, str] = {}
        for output_name in original_outputs:
            variable = symbol_table.variables.get(output_name)
            definition[output_name] = variable.data_type if variable else "text"
        return definition

    def _format_struct_data_type(self, data_type: str) -> str:
        """Format a structured data type for display."""
        return data_type

    def _ensure_type(
        self,
        resources: ResourceRegistryIR,
        type_name: str,
        definition: dict[str, str],
    ) -> None:
        """Ensure a type exists in the resource registry."""
        existing = next(
            (t for t in resources.types if t.type_name == type_name),
            None,
        )
        if existing is not None:
            return

        resources.types.append(
            TypeSpec(
                type_name=type_name,
                type_kind="structured",
                definition=self._structured_type_literal(definition),
            )
        )

    def _structured_type_literal(self, definition: dict[str, str]) -> str:
        """Render a SPL structured type declaration body."""
        fields = [
            f"{name}: {self._format_structured_field_type(data_type)}"
            for name, data_type in definition.items()
        ]
        return "{ " + ", ".join(fields) + " }"

    def _format_structured_field_type(self, data_type: str) -> str:
        """Normalize simple field data type spelling for SPL."""
        text = data_type.strip()
        if text.startswith("List[") and text.endswith("]"):
            return f"List [{text[5:-1].strip()}]"
        return text

    def _ensure_variable(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        name: str,
        data_type: str,
        description: str,
    ) -> None:
        """Ensure a variable exists in both resource registry and symbol table."""
        existing_resource = next(
            (v for v in resources.variables if v.name == name),
            None,
        )
        if existing_resource is None:
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
            symbol_table.declare(
                name=name,
                data_type=data_type,
                source="step",
                description=description,
            )

    def _is_unproduced_step_variable(self, name: str, symbol_table: SymbolTable) -> bool:
        """Return True when a step variable has no producer."""
        variable = symbol_table.variables.get(name)
        if variable is None:
            return True
        return variable.source == "step" and variable.producer_step is None

    def _ensure_required_main_outputs(
        self,
        blocks: BlockStructureIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
        worker_plan: WorkerPlanIR | None = None,
    ) -> list[str]:
        """Check required outputs have producers; emit diagnostics for missing ones.

        Does NOT synthesize producer steps.  Missing producers are reported as
        CompileDiagnostic records so they surface in the readable report instead
        of being silently invented.

        Uses ProducerIndex for consistent renderability classification so
        missing-output-producer diagnostics match what the executable-element
        gate would later allow through.
        """
        warnings: list[str] = []
        required_outputs = [
            variable.name
            for variable in resources.variables
            if variable.required and variable.source == "output"
        ]
        if not required_outputs:
            return warnings

        declared_apis = {api.api_name for api in resources.apis}
        extra_api_names = self._collect_extra_api_names(worker_plan)
        api_handoff_refs = self._build_api_handoff_refs(worker_plan)
        known_child_worker_ids = (
            {w.worker_id for w in worker_plan.workers
             if w.boundary_kind != "main_worker"
             and w.boundary_kind != "not_a_worker"}
            if worker_plan else None
        )

        index = ProducerIndex(
            steps=steps,
            handoffs=worker_plan.handoffs if worker_plan else None,
            declared_apis=declared_apis,
            extra_api_names=extra_api_names,
            api_handoff_refs=api_handoff_refs,
            known_child_worker_ids=known_child_worker_ids,
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
                "worker_id": None,
            })

        return warnings

    @staticmethod
    def _collect_extra_api_names(
        worker_plan: WorkerPlanIR | None,
    ) -> set[str]:
        """Collect API names from api_call-mode handoffs."""
        if worker_plan is None:
            return set()
        return {
            h.api_ref for h in worker_plan.handoffs
            if h.mode == "api_call" and h.api_ref
        }

    @staticmethod
    def _build_api_handoff_refs(
        worker_plan: WorkerPlanIR | None,
    ) -> dict[str, str]:
        """Build handoff_id -> api_ref lookup from api_call-mode handoffs."""
        if worker_plan is None:
            return {}
        return {
            h.handoff_id: h.api_ref for h in worker_plan.handoffs
            if h.mode == "api_call" and h.api_ref
        }

    @staticmethod
    def _call_api_is_declared(
        step: StepIR,
        declared_apis: set[str],
        extra_api_names: set[str] | None,
        api_handoff_refs: dict[str, str] | None,
    ) -> bool:
        """Check whether a CALL_API step's integration_ref has valid evidence.

        When the step carries a handoff_id, prefer the handoff-bound API ref
        as the authoritative evidence.  Otherwise fall back to the global API
        registry and any extra API names collected from handoffs.
        """
        if (
            step.handoff_id is not None
            and api_handoff_refs is not None
            and step.handoff_id in api_handoff_refs
        ):
            return step.integration_ref == api_handoff_refs[step.handoff_id]
        if step.integration_ref in declared_apis:
            return True
        if extra_api_names and step.integration_ref in extra_api_names:
            return True
        return False

    def _is_handler_step(
        self, step: StepIR, flow_id: str, exc_spans: set[str] | None = None
    ) -> bool:
        """Return True when *step* qualifies as an executable handler.

        A step is a handler for an exception flow when it references the
        flow's flow_id AND is NOT merely restating the exception condition
        from the same source spans.
        """
        if step.flow_ref != flow_id:
            return False
        if self._is_pseudo_handler(step, flow_id, exc_spans):
            return False
        return True

    def _is_pseudo_handler(
        self, step: StepIR, flow_id: str, exc_spans: set[str] | None = None
    ) -> bool:
        """Return True when *step* is a condition restatement, not a real handler.

        Only steps whose source spans are contained within the exception
        condition spans AND whose text matches condition/gate patterns
        (not action patterns) are flagged.

        REQUEST_INPUT, CALL_API, and INVOKE_WORKER steps are always treated
        as legitimate handlers -- they represent concrete user-facing or
        integration actions.  Everything else (GENERAL_COMMAND, DISPLAY,
        DISPLAY_MESSAGE, etc.) is checked because LLMs may reformulate
        the condition text as a display or generic command.
        """
        if step.command_type in {"REQUEST_INPUT", "CALL_API", "INVOKE_WORKER"}:
            return False
        if not step.source_span_ids:
            return False
        # Span containment check.
        span_match = (
            exc_spans is not None
            and set(step.source_span_ids).issubset(exc_spans)
        ) if exc_spans else False
        # Text pattern check: condition restatement vs action.
        text = step.text.lower()
        pseudo_markers = (
            "do not finalize", "check if", "ensure that",
            "required slots remain", "unless", "required slots missing",
            "mark as assumption-bearing", "mark the draft",
            "confirm with the user", "ask the user to confirm",
            # Display-type pseudo-handlers: show, report, indicate etc.
            "display a message", "show a message",
        )
        text_match = any(marker in text for marker in pseudo_markers)
        if exc_spans:
            return span_match and text_match
        # Post-MVP heuristic fallback (no spans).
        return text_match

    def _diagnose_exception_flow_handlers(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        steps: list[StepIR],
        worker_id: str | None = None,
    ) -> None:
        """Flag and remove pseudo-handler steps; record structured findings.

        Pseudo-handler steps (condition restatements from the same source
        spans) are marked and removed from the step list so they cannot
        render.  Diagnostic emission is deferred to PostNormalizeIRSChecker
        which receives these findings via ``self.construct_findings``.
        """
        for exc_flow in flow.exception_flows:
            exc_spans = set(exc_flow.spans)

            # Separate pseudo-handlers from real handlers.
            handler_steps: list[StepIR] = []
            pseudo_steps: list[StepIR] = []
            for s in steps:
                if s.flow_ref != exc_flow.flow_id:
                    continue
                if self._is_pseudo_handler(s, exc_flow.flow_id, exc_spans):
                    pseudo_steps.append(s)
                else:
                    handler_steps.append(s)

            # Flag and remove pseudo-handlers -- they are condition restatements.
            pseudo_ids: set[str] = set()
            for pseudo in pseudo_steps:
                pseudo_ids.add(pseudo.step_id)
                # Mark for downstream consumers (Gate, reports) so they
                # can distinguish pseudo-handlers from real handlers.
                pseudo.metadata["pseudo_exception_handler"] = "true"
                self.construct_findings.setdefault("pseudo_handlers", []).append({
                    "step_id": pseudo.step_id,
                    "flow_id": exc_flow.flow_id,
                    "worker_id": worker_id,
                    "text": pseudo.text,
                    "source_span_ids": list(pseudo.source_span_ids),
                })
            # Strip pseudo-handlers from the step list so they don't render.
            if pseudo_ids:
                steps[:] = [s for s in steps if s.step_id not in pseudo_ids]

            if handler_steps:
                continue

            # Record finding — PostNormalizeIRSChecker emits the final diagnostic.
            self.construct_findings.setdefault(
                "exception_flow_no_handler", []
            ).append({
                "flow_id": exc_flow.flow_id,
                "condition_text": exc_flow.condition_text,
                "worker_id": worker_id,
                "source_span_ids": list(exc_flow.spans) if exc_flow.spans else [],
            })

    def _diagnose_type_contract_ambiguities(
        self,
        steps: list[StepIR],
        symbol_table: SymbolTable,
        resources: ResourceRegistryIR,
        extra_api_names: set[str] | None = None,
        api_handoff_refs: dict[str, str] | None = None,
    ) -> None:
        """Diagnostic emission deferred to PostNormalizeIRSChecker.

        This method exists for backward compatibility of the call sites
        in normalizer.py.  All type/contract ambiguity detection now
        runs in PostNormalizeIRSChecker._check_type_contract_ambiguities.
        """

    def _diagnose_assumed_commands(
        self,
        steps: list[StepIR],
        valid_handoff_ids: set[str] | None = None,
    ) -> None:
        """Diagnostic emission deferred to PostNormalizeIRSChecker.

        This method exists for backward compatibility of the call sites
        in normalizer.py.  All assumed-command detection now runs in
        PostNormalizeIRSChecker._check_assumed_commands.
        """

    def _completion_step_text(self, output: str) -> str:
        text_by_output = {
            "assumptions_log": "Record assumptions for unresolved items",
            "completion_status": "Set completion status for the normal completion path",
            "source_evidence_set": "Produce the source evidence set for normal completion",
            "draft": "Produce the draft for normal completion",
        }
        return text_by_output.get(output, f"Produce required output {output}")
