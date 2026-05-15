"""Normalization methods for Stage 9.5 IRNormalizer."""

from __future__ import annotations

from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic
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

            self.diagnostics.append(
                self._build_missing_output_producer_diagnostic(
                    output=output,
                    symbol_table=symbol_table,
                )
            )

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
        """Build handoff_id → api_ref lookup from api_call-mode handoffs."""
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

    def _is_handler_step(self, step: StepIR, flow_id: str) -> bool:
        """Return True when *step* qualifies as an executable handler.

        A step is a handler for an exception flow when it references the
        flow's flow_id.  The helper exists so later executable-element gating
        (TODO 6) can add renderability / source-backing checks in one place.
        """
        return step.flow_ref == flow_id

    def _diagnose_exception_flow_handlers(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        steps: list[StepIR],
        worker_id: str | None = None,
    ) -> None:
        """Emit missing_handler diagnostics for exception flows without handlers.

        An exception flow has a handler only when at least one *executable
        step* references its flow_id.  Blocks are structural containers, not
        handlers — a skeleton exception-flow block without a handler step is
        still a partial element that must be surfaced.
        """
        for exc_flow in flow.exception_flows:
            handler_steps = [
                s for s in steps
                if self._is_handler_step(s, exc_flow.flow_id)
            ]
            if handler_steps:
                continue

            condition_snippet = exc_flow.condition_text[:80]
            if worker_id is not None:
                scope_note = f" in worker '{worker_id}'"
                target_ref = (
                    f"worker:{worker_id}.exception_flow:{exc_flow.flow_id}"
                )
            else:
                scope_note = ""
                target_ref = f"exception_flow:{exc_flow.flow_id}"

            self.diagnostics.append(
                CompileDiagnostic(
                    diagnostic_id=self._next_diagnostic_id(),
                    kind="missing_handler",
                    severity="warning",
                    message=(
                        f"Exception flow '{exc_flow.flow_id}' "
                        f"('{condition_snippet}') has no handler "
                        f"step{scope_note}."
                    ),
                    target_ref=target_ref,
                    source_span_ids=list(exc_flow.spans) if exc_flow.spans else [],
                    suggested_resolution=(
                        f"Add a handler step for "
                        f"'{exc_flow.condition_text}', or mark this "
                        f"exception as acknowledged without handling."
                    ),
                    blocks_rendering=False,
                    blocks_completion=True,
                )
            )

    def _diagnose_type_contract_ambiguities(
        self,
        steps: list[StepIR],
        symbol_table: SymbolTable,
        resources: ResourceRegistryIR,
        extra_api_names: set[str] | None = None,
        api_handoff_refs: dict[str, str] | None = None,
    ) -> None:
        """Emit type_or_contract_ambiguity diagnostics for commands with
        unclear or incomplete contract evidence.

        - CALL_API without a named API reference
        - INVOKE_WORKER without a concrete worker target
        - REQUEST_INPUT without source-span backing (the step may be an
          assumption rather than a requirement)
        """
        declared_apis = {api.api_name for api in resources.apis}
        for step in steps:
            kind = ""
            detail = ""
            blocks_render = False

            if step.command_type == "CALL_API" and not step.integration_ref:
                kind = "type_or_contract_ambiguity"
                detail = "CALL_API step has no integration_ref (API name)"
                blocks_render = True
            elif step.command_type == "CALL_API" and step.integration_ref:
                if not self._call_api_is_declared(
                    step, declared_apis, extra_api_names, api_handoff_refs
                ):
                    kind = "type_or_contract_ambiguity"
                    detail = (
                        f"CALL_API references undeclared API "
                        f"'{step.integration_ref}'"
                    )
                    blocks_render = True
            elif (
                step.command_type == "INVOKE_WORKER"
                and not step.integration_ref
            ):
                kind = "type_or_contract_ambiguity"
                detail = "INVOKE_WORKER step has no concrete worker target"
                blocks_render = True
            elif (
                step.command_type == "REQUEST_INPUT"
                and not step.source_span_ids
            ):
                kind = "type_or_contract_ambiguity"
                detail = (
                    "REQUEST_INPUT step has no source-span evidence — "
                    "may be an assumed interaction"
                )
                blocks_render = False

            if not kind:
                continue

            self.diagnostics.append(
                CompileDiagnostic(
                    diagnostic_id=self._next_diagnostic_id(),
                    kind=kind,
                    severity="warning",
                    message=(
                        f"Step '{step.step_id}' ({step.command_type}): "
                        f"{detail}."
                    ),
                    target_ref=f"step:{step.step_id}",
                    source_span_ids=list(step.source_span_ids),
                    blocks_rendering=blocks_render,
                    blocks_completion=True,
                )
            )

    def _diagnose_assumed_commands(
        self,
        steps: list[StepIR],
        valid_handoff_ids: set[str] | None = None,
    ) -> None:
        """Emit assumed_command_not_renderable for steps that lack source
        evidence and are not legitimate compiler scaffolding.

        A step is assumed/synthetic when:
        - source_span_ids is empty, AND
        - handoff_id is not in *valid_handoff_ids* (an LLM-invented
          handoff_id does NOT count), AND
        - metadata origin is not ``compiler_unpack``.
        """
        for step in steps:
            if step.source_span_ids:
                continue
            if (
                step.handoff_id is not None
                and valid_handoff_ids is not None
                and step.handoff_id in valid_handoff_ids
            ):
                continue
            # Legacy path: handoff steps are materialised before this check
            # runs, so a non-None handoff_id without a validity set is
            # accepted for backward compatibility.
            if step.handoff_id is not None and valid_handoff_ids is None:
                continue
            if step.metadata.get("origin") == "compiler_unpack":
                continue

            self.diagnostics.append(
                CompileDiagnostic(
                    diagnostic_id=self._next_diagnostic_id(),
                    kind="assumed_command_not_renderable",
                    severity="warning",
                    message=(
                        f"Step '{step.step_id}' "
                        f"('{step.text[:80]}') has no source evidence "
                        f"and is not compiler scaffolding — it should "
                        f"not be rendered as executable SPL."
                    ),
                    target_ref=f"step:{step.step_id}",
                    source_span_ids=[],
                    suggested_resolution=(
                        "Provide a source span that describes this "
                        "behavior, or remove the step if the behavior "
                        "is not required."
                    ),
                    blocks_rendering=True,
                    blocks_completion=True,
                )
            )

    def _build_missing_output_producer_diagnostic(
        self,
        output: str,
        symbol_table: SymbolTable,
        worker_id: str | None = None,
    ) -> CompileDiagnostic:
        """Build a diagnostic for a required output with no source-backed producer."""
        suggestion = self._completion_step_text(output)
        variable = symbol_table.variables.get(output)
        description = variable.description if variable else output

        if worker_id is not None:
            target_ref = f"worker:{worker_id}.output:{output}"
            scope_note = f" in worker '{worker_id}'"
        else:
            target_ref = f"variable:{output}"
            scope_note = ""

        return CompileDiagnostic(
            diagnostic_id=self._next_diagnostic_id(),
            kind="missing_output_producer",
            severity="warning",
            message=(
                f"Required output '{output}' ({description}) has no "
                f"source-backed producer step{scope_note}."
            ),
            target_ref=target_ref,
            source_span_ids=[],
            suggested_resolution=(
                f"Add a step that produces '{output}', e.g. '{suggestion}'. "
                f"If the source requirement does not specify how to produce "
                f"this output, mark it as optional or remove it from the "
                f"output contract."
            ),
            blocks_rendering=False,
            blocks_completion=True,
        )

    def _next_diagnostic_id(self) -> str:
        """Generate a unique diagnostic identifier."""
        idx = len(self.diagnostics)
        return f"diag_{idx:04d}"

    def _completion_step_text(self, output: str) -> str:
        text_by_output = {
            "assumptions_log": "Record assumptions for unresolved items",
            "completion_status": "Set completion status for the normal completion path",
            "source_evidence_set": "Produce the source evidence set for normal completion",
            "draft": "Produce the draft for normal completion",
        }
        return text_by_output.get(output, f"Produce required output {output}")
