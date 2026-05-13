"""Formatting methods for Stage 11 SPLRenderer."""

from __future__ import annotations

import re

from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.symbol_table import SymbolTable


class FormattingMixin:
    """Mixin class containing formatting methods for SPLRenderer."""

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

        for var in symbol_table.get_all_declared_variables().values():
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
        for var in symbol_table.get_all_declared_variables().values():
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

    def _format_data_type(self, data_type: str) -> str:
        """Normalize common array type spelling to the SPL grammar form."""
        text = data_type.strip()
        match = re.fullmatch(r"List\s*\[(.+)\]", text)
        if match:
            return f"List [{self._format_data_type(match.group(1))}]"
        return text
