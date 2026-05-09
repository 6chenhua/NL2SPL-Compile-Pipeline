"""Stage 11: SPLRenderer - Render WorkerIR to SPL text."""

from __future__ import annotations

import json
import re

from nl2spl.compiler.spl_formatter import SPLFormatter
from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import ChildWorkerIR, WorkerIR
from nl2spl.validator.static_validator import StaticValidator


class SPLRenderer:
    """SPL rendering (code logic).

    This stage renders WorkerIR into SPL text format.
    """

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
            parts.append(f"    {self._aspect_name(aspect.name)}: {aspect.text}")
        parts.append("[END_PERSONA]")

        # 3. DEFINE_AUDIENCE
        if profile.audience_aspects:
            parts.append("[DEFINE_AUDIENCE:]")
            for aspect in profile.audience_aspects:
                parts.append(f"    {self._aspect_name(aspect.name)}: {aspect.text}")
            parts.append("[END_AUDIENCE]")

        # 4. DEFINE_CONCEPTS
        if profile.concepts:
            parts.append("[DEFINE_CONCEPTS:]")
            for concept in profile.concepts:
                parts.append(f"    {self._aspect_name(concept.term)}: {concept.definition}")
            parts.append("[END_CONCEPTS]")

        # 5. DEFINE_CONSTRAINTS
        if constraints:
            parts.append("[DEFINE_CONSTRAINTS:]")
            for constraint in constraints:
                parts.append(
                    f"    {self._constraint_aspect(constraint.kind)}: {constraint.text}"
                )
            parts.append("[END_CONSTRAINTS]")

        # 6. DEFINE_VARIABLES
        variable_declarations = self._variable_declarations(resources, symbol_table)
        if variable_declarations:
            parts.append("[DEFINE_VARIABLES:]")
            for name, data_type, description in variable_declarations:
                parts.append(
                    f'    "{self._quote_text(description)}" {name}: '
                    f"{self._format_data_type(data_type)}"
                )
            parts.append("[END_VARIABLES]")

        # 7. DEFINE_FILES
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

        # 8. DEFINE_TYPES
        if resources.types:
            parts.append("[DEFINE_TYPES:]")
            for type_spec in resources.types:
                definition = type_spec.definition or type_spec.type_kind
                parts.append(
                    f"    {type_spec.type_name} = {self._format_data_type(definition)}"
                )
            parts.append("[END_TYPES]")

        # 9. DEFINE_APIS
        if resources.apis:
            parts.append("[DEFINE_APIS:]")
            for api in resources.apis:
                auth = api.auth or "none"
                parts.append(
                    f'    "{self._quote_text(api.description)}" {api.api_name} <{auth}>'
                )
                parts.append("    {}")
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

        errors.extend(self._validate_worker_invocations(worker, steps))

        # 11. DEFINE_WORKER
        parts.append(f'[DEFINE_WORKER: "{worker.description}" {worker.worker_name}]')

        # 12. INPUTS
        parts.append("    [INPUTS]")
        for inp in worker.inputs:
            req = "REQUIRED" if inp.required else "OPTIONAL"
            parts.append(f"        {req} <REF>{inp.name}</REF>")
        parts.append("    [END_INPUTS]")

        # 13. OUTPUTS
        parts.append("    [OUTPUTS]")
        for out in worker.outputs:
            req = "REQUIRED" if out.required else "OPTIONAL"
            parts.append(f"        {req} <REF>{out.name}</REF>")
        parts.append("    [END_OUTPUTS]")

        # 14. MAIN_FLOW
        self._produced_variables = {inp.name for inp in worker.inputs}
        parts.append("    [MAIN_FLOW]")
        parts.extend(self._render_blocks(worker.main_flow.blocks, steps, indent=8))
        parts.append("    [END_MAIN_FLOW]")

        # 15. ALTERNATIVE_FLOWs
        for alt_flow in worker.alternative_flows:
            condition = self._render_condition(alt_flow.condition_text)
            parts.append(f"    [ALTERNATIVE_FLOW: {condition}]")
            parts.extend(
                self._render_blocks(
                    alt_flow.blocks,
                    steps,
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
                    steps,
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
        """Render a concrete child worker generated from delegation."""
        lines = [f'[DEFINE_WORKER: "{self._quote_text(worker.description)}" {worker.worker_name}]']
        previous_produced = self._produced_variables
        self._produced_variables = {inp.name for inp in worker.inputs}

        lines.append("    [INPUTS]")
        for inp in worker.inputs:
            req = "REQUIRED" if inp.required else "OPTIONAL"
            lines.append(f"        {req} <REF>{inp.name}</REF>")
        lines.append("    [END_INPUTS]")

        lines.append("    [OUTPUTS]")
        for out in worker.outputs:
            req = "REQUIRED" if out.required else "OPTIONAL"
            lines.append(f"        {req} <REF>{out.name}</REF>")
        lines.append("    [END_OUTPUTS]")

        lines.append("    [MAIN_FLOW]")
        lines.append("        [SEQUENTIAL_BLOCK]")
        child_step = StepIR(
            step_id="st_child",
            text=worker.task_text,
            source_span_ids=[],
            command_type="GENERAL_COMMAND",
            inputs=[inp.name for inp in worker.inputs],
            outputs=[out.name for out in worker.outputs],
        )
        lines.append(f"            {self._render_step(child_step)}")
        lines.append("        [END_SEQUENTIAL_BLOCK]")
        lines.append("    [END_MAIN_FLOW]")
        lines.append("[END_WORKER]")
        self._produced_variables = previous_produced
        return lines

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

    def _render_blocks(
        self,
        blocks: list[BlockIR],
        steps: list[StepIR],
        indent: int,
        outer_condition_text: str | None = None,
    ) -> list[str]:
        """Render flow blocks with SPL grammar block names."""
        lines = []
        indent_str = " " * indent

        for block in blocks:
            block_steps = self._steps_for_block(block, steps)

            if block.block_type == "SEQUENTIAL":
                lines.append(f"{indent_str}[SEQUENTIAL_BLOCK]")
                lines.extend(self._render_step_lines(block_steps, indent + 4))
                lines.append(f"{indent_str}[END_SEQUENTIAL_BLOCK]")
            elif block.block_type == "IF":
                condition = self._render_condition(block.condition_text or "condition")
                if (
                    outer_condition_text
                    and self._condition_key(condition)
                    == self._condition_key(outer_condition_text)
                ):
                    lines.append(f"{indent_str}[SEQUENTIAL_BLOCK]")
                    lines.extend(
                        self._render_step_lines(block_steps, indent + 4, condition)
                    )
                    lines.append(f"{indent_str}[END_SEQUENTIAL_BLOCK]")
                    continue
                lines.append(
                    f"{indent_str}{self._next_decision()} [IF {condition}]"
                )
                lines.extend(
                    self._render_step_lines(block_steps, indent + 4, condition)
                )
                lines.append(f"{indent_str}[END_IF]")
            elif block.block_type == "FOR":
                condition = self._render_condition(block.condition_text or "items")
                lines.append(
                    f"{indent_str}{self._next_decision()} [FOR {condition}]"
                )
                lines.extend(
                    self._render_step_lines(block_steps, indent + 4, condition)
                )
                lines.append(f"{indent_str}[END_FOR]")
            elif block.block_type == "WHILE":
                condition = self._render_condition(block.condition_text or "condition")
                lines.append(
                    f"{indent_str}{self._next_decision()} [WHILE {condition}]"
                )
                lines.extend(
                    self._render_step_lines(block_steps, indent + 4, condition)
                )
                lines.append(f"{indent_str}[END_WHILE]")

        return lines

    def _render_step_lines(
        self,
        steps: list[StepIR],
        indent: int,
        condition_text: str | None = None,
    ) -> list[str]:
        """Render command lines at the requested indentation."""
        indent_str = " " * indent
        return [
            f"{indent_str}{self._render_step(step, condition_text)}"
            for step in steps
        ]

    def _steps_for_block(self, block: BlockIR, steps: list[StepIR]) -> list[StepIR]:
        """Return steps that belong to a block, preserving block span order."""
        span_order = {span_id: i for i, span_id in enumerate(block.spans)}
        selected: list[tuple[int, int, StepIR]] = []

        for step_index, step in enumerate(steps):
            if step.block_ref:
                if step.block_ref != block.block_id:
                    continue
                matching_positions = [
                    span_order[span_id]
                    for span_id in step.source_span_ids
                    if span_id in span_order
                ]
                position = min(matching_positions) if matching_positions else len(span_order)
                selected.append((position, step_index, step))
                continue

            matching_positions = [
                span_order[span_id]
                for span_id in step.source_span_ids
                if span_id in span_order
            ]
            if matching_positions:
                selected.append((min(matching_positions), step_index, step))
            elif step.block_ref == block.block_id:
                selected.append((len(span_order), step_index, step))

        selected.sort(key=lambda item: (item[0], item[1]))
        return [step for _, _, step in selected]

    def _render_step(self, step: StepIR, condition_text: str | None = None) -> str:
        """Render a single step as a grammar-shaped SPL command."""
        command_index = self._next_command()
        command_text = self._canonical_command_text(step.text, condition_text)
        text = self._description_with_refs(command_text, step.inputs)

        if step.command_type == "GENERAL_COMMAND":
            return f"{command_index} [COMMAND {text}{self._result_clause('RESULT', step.outputs)}]"

        if step.command_type == "CALL_API":
            api_name = step.integration_ref or "Api"
            return (
                f"{command_index} [CALL {api_name}"
                f"{self._with_clause(step.inputs)}"
                f"{self._result_clause('RESPONSE', step.outputs)}]"
            )

        if step.command_type == "INVOKE_WORKER":
            worker_name = step.integration_ref or "<UNRESOLVED_WORKER>"
            return (
                f"{command_index} [INVOKE {worker_name}"
                f"{self._with_clause(step.inputs)}"
                f"{self._result_clause('RESPONSE', step.outputs)}]"
            )

        if step.command_type == "REQUEST_INPUT":
            result_clause = self._result_clause("VALUE", step.outputs)
            if not result_clause:
                result_clause = " VALUE user_input:text SET"
            return f"{command_index} [INPUT {text}{result_clause}]"

        if step.command_type == "DISPLAY_MESSAGE":
            return f"{command_index} [DISPLAY {text}]"

        return f"{command_index} [COMMAND {text}{self._result_clause('RESULT', step.outputs)}]"

    def _canonical_command_text(
        self,
        text: str,
        condition_text: str | None = None,
    ) -> str:
        """Rewrite extracted step text into a clean command description."""
        description = self._clean_text(text) or "Perform the step"
        condition = self._clean_text(condition_text or "")

        description = self._strip_leading_condition_clause(description)
        if condition:
            description = self._strip_trailing_condition_clause(description, condition)
            if self._condition_key(description) == self._condition_key(condition):
                description = "Evaluate whether the condition holds"

        return self._capitalize_first(self._strip_terminal_punctuation(description))

    def _description_with_refs(self, text: str, inputs: list[str]) -> str:
        """Append variable references to a command description."""
        description = self._strip_terminal_punctuation(
            self._clean_text(text) or "Perform the step"
        )
        refs = self._refs(inputs)
        missing_refs = [ref for ref in refs if ref not in description]
        if missing_refs:
            description = f"{description} based on {self._join_refs(missing_refs)}"
        return description

    def _with_clause(self, inputs: list[str]) -> str:
        """Render an invocation WITH clause."""
        refs = self._refs(inputs)
        if not refs:
            return ""
        return f" WITH {', '.join(refs)}"

    def _result_clause(self, keyword: str, outputs: list[str]) -> str:
        """Render the first declared output as a command result clause."""
        if not outputs:
            return ""
        output = outputs[0]
        if output not in self._produced_variables:
            data_type = self._result_data_types.get(output, "text")
            result = f"{output}: {self._format_data_type(data_type)}"
        else:
            result = f"<REF>{output}</REF>"
        self._produced_variables.add(output)
        return f" {keyword} {result} SET"

    def _refs(self, names: list[str]) -> list[str]:
        """Render variable names as SPL REF tags."""
        return [f"<REF>{name}</REF>" for name in names if name]

    def _join_refs(self, refs: list[str]) -> str:
        """Join REF tags into readable text."""
        if len(refs) <= 1:
            return "".join(refs)
        if len(refs) == 2:
            return f"{refs[0]} and {refs[1]}"
        return f"{', '.join(refs[:-1])}, and {refs[-1]}"

    def _render_condition(self, text: str) -> str:
        """Render a condition without redundant trigger words."""
        condition = self._strip_terminal_punctuation(self._clean_text(text))
        condition = re.sub(r"^(if|when)\s+", "", condition, flags=re.IGNORECASE)
        return condition or "condition"

    def _strip_leading_condition_clause(self, text: str) -> str:
        """Remove a leading natural-language condition from a command."""
        return re.sub(
            r"^(if|when|unless)\s+[^,]+,\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

    def _strip_trailing_condition_clause(self, text: str, condition_text: str) -> str:
        """Remove a trailing condition already represented by a block."""
        condition_key = self._condition_key(condition_text)
        for keyword in ("if", "when", "unless"):
            pattern = rf"\s+{keyword}\s+(.+)$"
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match and self._condition_key(match.group(1)) == condition_key:
                return text[: match.start()]
        return text

    def _condition_key(self, text: str) -> str:
        """Normalize condition text for duplicate detection."""
        key = self._strip_terminal_punctuation(self._clean_text(text)).lower()
        key = re.sub(r"^(if|when)\s+", "", key)
        return re.sub(r"[^a-z0-9_]+", " ", key).strip()

    def _clean_text(self, text: str) -> str:
        """Collapse whitespace in free text."""
        return " ".join(str(text).strip().split())

    def _strip_terminal_punctuation(self, text: str) -> str:
        """Remove punctuation that reads badly before RESULT/RESPONSE."""
        return text.rstrip(" .")

    def _capitalize_first(self, text: str) -> str:
        """Capitalize the first character of a command description."""
        if not text:
            return text
        return text[0].upper() + text[1:]

    def _next_command(self) -> str:
        """Return the next command index."""
        value = f"COMMAND-{self._command_index}"
        self._command_index += 1
        return value

    def _next_decision(self) -> str:
        """Return the next decision index."""
        value = f"DECISION-{self._decision_index}"
        self._decision_index += 1
        return value

    def _renderable_role(self, profile: AgentProfileIR, warnings: list[str]) -> str:
        """Return a non-empty ROLE string."""
        role = profile.persona.role.strip()
        if role:
            return role
        warnings.append("Persona ROLE was empty; rendered fallback ROLE.")
        return "General Assistant"

    def _variable_declarations(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
    ) -> list[tuple[str, str, str]]:
        """Return variables declared by resources plus normalized step variables."""
        declarations: list[tuple[str, str, str]] = []
        seen: set[str] = set()

        for var in resources.variables:
            declarations.append((var.name, var.data_type, var.description))
            seen.add(var.name)

        for var in symbol_table.variables.values():
            if var.name in seen:
                continue
            declarations.append((var.name, var.data_type, var.description))
            seen.add(var.name)

        return declarations

    def _result_type_lookup(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
    ) -> dict[str, str]:
        """Return data types for result declarations."""
        data_types = {var.name: var.data_type for var in resources.variables}
        for var in symbol_table.variables.values():
            data_types.setdefault(var.name, var.data_type)
        return data_types

    def _constraint_aspect(self, kind: str) -> str:
        """Map constraint kind to a grammar-safe aspect label."""
        return "".join(part.capitalize() for part in kind.split("_")) or "Requirement"

    def _aspect_name(self, name: str) -> str:
        """Render a grammar-safe optional aspect name."""
        cleaned = re.sub(r"[^A-Za-z0-9_]+", "", name.strip())
        if not cleaned:
            return "Aspect"
        return cleaned[0].upper() + cleaned[1:]

    def _quote_text(self, text: str) -> str:
        """Escape free text for quoted SPL descriptions."""
        return self._clean_text(text).replace('"', '\\"')

    def _format_data_type(self, data_type: str) -> str:
        """Normalize common array type spelling to the SPL grammar form."""
        text = data_type.strip()
        match = re.fullmatch(r"List\s*\[(.+)\]", text)
        if match:
            return f"List [{self._format_data_type(match.group(1))}]"
        return text
