"""Stage 11: SPLRenderer - Render WorkerIR to SPL text."""

from __future__ import annotations

import json

from nl2spl.compiler.spl_formatter import SPLFormatter
from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import ChildWorkerIR, WorkerIR
from nl2spl.pipeline.stages.stage11_spl_renderer.block_renderer import BlockRendererMixin
from nl2spl.pipeline.stages.stage11_spl_renderer.clause_builder import ClauseBuilderMixin
from nl2spl.pipeline.stages.stage11_spl_renderer.formatting import FormattingMixin
from nl2spl.pipeline.stages.stage11_spl_renderer.text_utils import TextUtilsMixin
from nl2spl.validator.static_validator import StaticValidator


def _required_keyword(required: bool | None) -> str:
    """Return SPL REQUIRED/OPTIONAL keyword or empty string for None.

    Before B1 this was a truthiness check: ``"REQUIRED" if x.required else "OPTIONAL"``.
    Now it is a tri-state branch:
      - ``True`` → ``"REQUIRED"``
      - ``False`` → ``"OPTIONAL"``
      - ``None`` → ``""`` (unspecified — render nothing)
    """
    if required is True:
        return "REQUIRED"
    if required is False:
        return "OPTIONAL"
    return ""


class SPLRenderer(
    BlockRendererMixin,
    ClauseBuilderMixin,
    FormattingMixin,
    TextUtilsMixin,
):
    """SPL rendering (code logic).

    This stage renders WorkerIR into SPL text format.
    """

    def __init__(self) -> None:
        """Initialize renderer state."""
        self._command_index: int = 1
        self._decision_index: int = 1
        self._produced_variables: set[str] = set()
        self._result_data_types: dict[str, str] = {}

    def render(
        self,
        worker: WorkerIR,
        profile: AgentProfileIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
        constraints: list[ConstraintIR],
    ) -> tuple[str, list[str], list[str]]:
        """Render SPL text.

        Args:
            worker: Worker IR
            profile: Agent profile IR
            resources: Resource registry IR
            symbol_table: Symbol table
            steps: List of step IRs
            constraints: List of constraint IRs

        Returns:
            Tuple of (spl_text, errors, warnings)
        """
        errors: list[str] = []
        warnings: list[str] = []
        parts = []
        self._command_index = 1
        self._decision_index = 1
        self._result_data_types = self._result_type_lookup(resources, symbol_table)
        self._produced_variables: set[str] = set()

        # 1. DEFINE_AGENT header
        parts.append(f'[DEFINE_AGENT: {worker.worker_name} "{worker.description}"]')

        # 2. DEFINE_PERSONA
        role = self._renderable_role(profile, warnings)
        parts.append("[DEFINE_PERSONA:]")
        parts.append(f"    ROLE: {role}")
        for aspect in profile.persona.aspects:
            if not self._source_backed_profile_item(aspect):
                continue
            parts.append(f"    {self._aspect_name(aspect.name)}: {aspect.text}")
        parts.append("[END_PERSONA]")

        # 3. DEFINE_AUDIENCE
        renderable_audience_aspects = [
            aspect for aspect in profile.audience_aspects
            if self._source_backed_profile_item(aspect)
        ]
        if renderable_audience_aspects:
            parts.append("[DEFINE_AUDIENCE:]")
            for aspect in renderable_audience_aspects:
                parts.append(f"    {self._aspect_name(aspect.name)}: {aspect.text}")
            parts.append("[END_AUDIENCE]")

        # 4. DEFINE_CONCEPTS
        renderable_concepts = [
            concept for concept in profile.concepts
            if self._source_backed_profile_item(concept)
        ]
        if renderable_concepts:
            parts.append("[DEFINE_CONCEPTS:]")
            for concept in renderable_concepts:
                parts.append(f"    {self._aspect_name(concept.term)}: {concept.definition}")
            parts.append("[END_CONCEPTS]")

        # 5. DEFINE_CONSTRAINTS
        if constraints:
            parts.append("[DEFINE_CONSTRAINTS:]")
            for constraint in constraints:
                parts.append(f"    {self._constraint_aspect(constraint.kind)}: {constraint.text}")
            parts.append("[END_CONSTRAINTS]")

        # 6. DEFINE_TYPES
        if resources.types:
            parts.append("[DEFINE_TYPES:]")
            for type_spec in resources.types:
                definition = type_spec.definition or type_spec.type_kind
                if isinstance(definition, dict):
                    fields = [f"{k}: {v}" for k, v in definition.items()]
                    definition_str = "{ " + ", ".join(fields) + " }"
                else:
                    definition_str = str(definition)
                parts.append(
                    f"    {type_spec.type_name} = {self._format_data_type(definition_str)}"
                )
            parts.append("[END_TYPES]")

        # 7. DEFINE_VARIABLES
        variable_declarations = self._variable_declarations(resources, symbol_table)
        if variable_declarations:
            parts.append("[DEFINE_VARIABLES:]")
            for name, data_type, description in variable_declarations:
                parts.append(
                    f'    "{self._quote_text(description)}" {name}: '
                    f"{self._format_data_type(data_type)}"
                )
            parts.append("[END_VARIABLES]")

        # 8. DEFINE_FILES
        if resources.files:
            parts.append("[DEFINE_FILES:]")
            for file_spec in resources.files:
                path = file_spec.path or "< >"
                if path == "<runtime>":
                    path = "< >"
                parts.append(
                    f'    "{self._quote_text(file_spec.description)}" '
                    f"{file_spec.name} {path}: "
                    f"{self._format_data_type(file_spec.data_type)}"
                )
            parts.append("[END_FILES]")

        # 9. DEFINE_APIS
        if resources.apis:
            parts.append("[DEFINE_APIS:]")
            for api in resources.apis:
                parts.append(
                    f'    "{self._quote_text(api.description)}" {api.api_name} <{api.auth}>'
                )
                parts.append(f"    {api.openapi_schema.canonical_text}")
                functions = [
                    {
                        "name": function.name,
                        "description": function.description,
                        "parameters": function.parameters,
                        "return": {
                            "type": self._format_data_type(function.return_type),
                            "controlled-output": False,
                        },
                    }
                    for function in api.functions
                ]
                parts.append(
                    "    "
                    + json.dumps(
                        {"functions": functions},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
            parts.append("[END_APIS]")

        # 10. DEFINE_WORKER for generated child workers
        for child_worker in worker.child_workers:
            parts.extend(self._render_child_worker(child_worker))

        main_steps = worker.steps if worker.scoped_steps else (worker.steps or steps)

        errors.extend(self._validate_worker_invocations(worker, main_steps))

        # 11. DEFINE_WORKER
        parts.append(f'[DEFINE_WORKER: "{worker.description}" {worker.worker_name}]')

        # 12. INPUTS
        parts.append("    [INPUTS]")
        for inp in worker.inputs:
            req = _required_keyword(inp.required)
            parts.append(f"        {req} <REF>{inp.name}</REF>")
        parts.append("    [END_INPUTS]")

        # 13. OUTPUTS
        parts.append("    [OUTPUTS]")
        for out in worker.outputs:
            req = _required_keyword(out.required)
            parts.append(f"        {req} <REF>{out.name}</REF>")
        parts.append("    [END_OUTPUTS]")

        # 14. MAIN_FLOW
        self._produced_variables = {inp.name for inp in worker.inputs}
        parts.append("    [MAIN_FLOW]")
        parts.extend(self._render_blocks(worker.main_flow.blocks, main_steps, indent=8))
        parts.append("    [END_MAIN_FLOW]")

        # 15. ALTERNATIVE_FLOWs
        for alt_flow in worker.alternative_flows:
            condition = self._render_condition(alt_flow.condition_text)
            parts.append(f"    [ALTERNATIVE_FLOW: {condition}]")
            parts.extend(
                self._render_blocks(
                    alt_flow.blocks,
                    main_steps,
                    indent=8,
                    outer_condition_text=alt_flow.condition_text,
                )
            )
            parts.append("    [END_ALTERNATIVE_FLOW]")

        # 16. EXCEPTION_FLOWs
        for exc_flow in worker.exception_flows:
            condition = self._render_condition(exc_flow.condition_text)
            parts.append(f"    [EXCEPTION_FLOW: {condition}]")
            parts.extend(
                self._render_blocks(
                    exc_flow.blocks,
                    main_steps,
                    indent=8,
                    outer_condition_text=exc_flow.condition_text,
                )
            )
            parts.append("    [END_EXCEPTION_FLOW]")

        # 17. END_WORKER
        parts.append("[END_WORKER]")

        # 18. END_AGENT
        parts.append("[END_AGENT]")

        formatter = SPLFormatter()
        spl_text = formatter.format("\n".join(parts))
        warnings.extend(formatter.validate_indentation(spl_text))
        validator = StaticValidator()
        validation = validator.validate(spl_text)
        for validation_error in validation.errors:
            message = f"Line {validation_error.line + 1}: {validation_error.message}"
            if validation_error.severity == "error":
                errors.append(message)
            else:
                warnings.append(message)
        for variable_error in validator.validate_variables(spl_text):
            if variable_error.startswith("Undeclared variable"):
                errors.append(variable_error)
            else:
                warnings.append(variable_error)

        return spl_text, errors, warnings

    def _render_child_worker(self, worker: ChildWorkerIR) -> list[str]:
        """Render child worker with full flow support.

        Uses worker.main_flow.blocks and worker.steps for rendering,
        instead of the synthetic st_child approach.
        """
        lines = [f'[DEFINE_WORKER: "{self._quote_text(worker.description)}" {worker.worker_name}]']
        previous_produced = self._produced_variables
        self._produced_variables = {inp.name for inp in worker.inputs}

        # INPUTS
        lines.append("    [INPUTS]")
        for inp in worker.inputs:
            req = _required_keyword(inp.required)
            lines.append(f"        {req} <REF>{inp.name}</REF>")
        lines.append("    [END_INPUTS]")

        # OUTPUTS
        lines.append("    [OUTPUTS]")
        for out in worker.outputs:
            req = _required_keyword(out.required)
            lines.append(f"        {req} <REF>{out.name}</REF>")
        lines.append("    [END_OUTPUTS]")

        # MAIN_FLOW - use actual blocks and steps
        lines.append("    [MAIN_FLOW]")
        if worker.main_flow.blocks:
            lines.extend(self._render_blocks(worker.main_flow.blocks, worker.steps, indent=8))
        elif worker.steps:
            fallback_block = self._fallback_block_for_steps(
                f"b_{worker.worker_name}_fallback",
                worker.steps,
            )
            lines.extend(self._render_blocks([fallback_block], worker.steps, indent=8))
        else:
            # No blocks and no steps: render an empty main flow.
            # Do NOT synthesize a fallback command — missing behavior is
            # surfaced through compile diagnostics, not invented here.
            pass
        lines.append("    [END_MAIN_FLOW]")

        # ALTERNATIVE_FLOWs
        for alt_flow in worker.alternative_flows:
            condition = self._render_condition(alt_flow.condition_text)
            lines.append(f"    [ALTERNATIVE_FLOW: {condition}]")
            lines.extend(
                self._render_blocks(
                    alt_flow.blocks,
                    worker.steps,
                    indent=8,
                    outer_condition_text=alt_flow.condition_text,
                )
            )
            lines.append("    [END_ALTERNATIVE_FLOW]")

        # EXCEPTION_FLOWs
        for exc_flow in worker.exception_flows:
            condition = self._render_condition(exc_flow.condition_text)
            lines.append(f"    [EXCEPTION_FLOW: {condition}]")
            lines.extend(
                self._render_blocks(
                    exc_flow.blocks,
                    worker.steps,
                    indent=8,
                    outer_condition_text=exc_flow.condition_text,
                )
            )
            lines.append("    [END_EXCEPTION_FLOW]")

        lines.append("[END_WORKER]")
        self._produced_variables = previous_produced
        return lines

    def _fallback_block_for_steps(
        self,
        block_id: str,
        steps: list[StepIR],
    ) -> BlockIR:
        """Create a renderable fallback block for existing steps."""
        span_ids: list[str] = []
        seen: set[str] = set()
        for step in steps:
            if not step.block_ref:
                step.block_ref = block_id
            for span_id in step.source_span_ids:
                if span_id not in seen:
                    span_ids.append(span_id)
                    seen.add(span_id)
        return BlockIR(block_id=block_id, block_type="SEQUENTIAL", spans=span_ids)

    def _validate_worker_invocations(
        self,
        worker: WorkerIR,
        steps: list[StepIR],
    ) -> list[str]:
        """Reject unresolved worker invocations before final rendering."""
        errors = []
        known_child_workers = set(worker.child_worker_refs)
        for step in steps:
            if step.command_type != "INVOKE_WORKER":
                continue
            if not step.integration_ref or step.integration_ref in {"Worker", "child_worker"}:
                errors.append(
                    f"Step {step.step_id} is INVOKE_WORKER but has no concrete worker target."
                )
            elif known_child_workers and step.integration_ref not in known_child_workers:
                errors.append(
                    f"Step {step.step_id} invokes unknown child worker: {step.integration_ref}"
                )
        return errors
