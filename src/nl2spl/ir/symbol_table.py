"""SymbolTable - Variable declaration and reference management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class VariableSymbol:
    """Variable symbol information.

    Attributes:
        name: Variable name
        data_type: Data type
        source: Variable source
        description: Variable description
        scope_kind: Scope type (global/worker/handoff) - D4 decision
        scope_id: Scope ID (worker_id or handoff_id) - D4 decision
        flow_ref: Associated flow
        block_ref: Associated block
        producer_step: Step that produces this variable
        consumer_steps: Steps that consume this variable
        declared: Whether variable is declared in DEFINE_VARIABLES
    """

    name: str
    data_type: str
    source: str
    description: str
    scope_kind: Literal["global", "worker", "handoff"] = "global"
    scope_id: str | None = None
    flow_ref: str = "main"
    block_ref: str | None = None
    producer_step: str | None = None
    consumer_steps: list[str] = field(default_factory=list)
    declared: bool = True


class SymbolTable:
    """Symbol table for variable management.

    Manages variable declarations and references for SPL generation.

    Supports worker-aware variable scoping (D4 decision):
    - Variables can be scoped to global, worker, or handoff
    - Uses composite key (scope_kind, scope_id, name) for storage
    - Maintains backward compatibility with simple name-based access
    """

    def __init__(self) -> None:
        """Initialize empty symbol table."""
        # New interface: composite key storage
        self._variables: dict[tuple[str, str | None, str], VariableSymbol] = {}
        # Legacy interface: global variables only (backward compatibility)
        self.variables: dict[str, VariableSymbol] = {}

    def declare(
        self,
        name: str,
        data_type: str,
        source: str,
        description: str,
        flow_ref: str = "main",
        block_ref: str | None = None,
    ) -> None:
        """Declare a new variable (global scope).

        Args:
            name: Variable name
            data_type: Data type
            source: Variable source
            description: Variable description
            flow_ref: Associated flow
            block_ref: Associated block
        """
        var = VariableSymbol(
            name=name,
            data_type=data_type,
            source=source,
            description=description,
            scope_kind="global",
            scope_id=None,
            flow_ref=flow_ref,
            block_ref=block_ref,
        )
        # Store in both interfaces
        key = ("global", None, name)
        self._variables[key] = var
        self.variables[name] = var

    def reference(self, name: str) -> str:
        """Generate REF tag for variable.

        Args:
            name: Variable name

        Returns:
            REF tag string
        """
        return f"<REF>{name}</REF>"

    def value_reference(self, name: str) -> str:
        """Generate value REF tag for variable.

        Args:
            name: Variable name

        Returns:
            Value REF tag string
        """
        return f"<REF>*{name}</REF>"

    def get_variable_list_for_prompt(self) -> str:
        """Generate variable list text for LLM prompt.

        Returns:
            Formatted variable list
        """
        all_vars = dict(self.variables)
        for key, var in self._variables.items():
            if key[2] not in all_vars:
                all_vars[key[2]] = var

        if not all_vars:
            return "(No known variables)"

        lines = []
        for name, var in all_vars.items():
            lines.append(f"- {name}: {var.data_type} ({var.source}) - {var.description}")
        return "\n".join(lines)

    def add_producer(self, name: str, step_id: str) -> None:
        """Record which step produces a variable.

        Args:
            name: Variable name
            step_id: Step ID
        """
        if name in self.variables:
            self.variables[name].producer_step = step_id
        for key, var in self._variables.items():
            if key[2] == name:
                var.producer_step = step_id

    def add_consumer(self, name: str, step_id: str) -> None:
        """Record which step consumes a variable.

        Args:
            name: Variable name
            step_id: Step ID
        """
        if name in self.variables:
            if step_id not in self.variables[name].consumer_steps:
                self.variables[name].consumer_steps.append(step_id)
        for key, var in self._variables.items():
            if key[2] == name and step_id not in var.consumer_steps:
                var.consumer_steps.append(step_id)

    def validate_references(self, known_step_ids: set[str]) -> list[str]:
        """Validate all references.

        Args:
            known_step_ids: Set of known step IDs

        Returns:
            List of validation errors
        """
        errors = []
        seen = set()
        for name, var in self.variables.items():
            if var.producer_step and var.producer_step not in known_step_ids:
                errors.append(
                    f"Variable {name} references unknown producer step: {var.producer_step}"
                )
            for step_id in var.consumer_steps:
                if step_id not in known_step_ids:
                    errors.append(f"Variable {name} references unknown consumer step: {step_id}")
            seen.add(name)
        for key, var in self._variables.items():
            if key[2] in seen:
                continue
            if var.producer_step and var.producer_step not in known_step_ids:
                errors.append(
                    f"Variable {key[2]} (scope: {key[0]}) references "
                    f"unknown producer step: {var.producer_step}"
                )
            for step_id in var.consumer_steps:
                if step_id not in known_step_ids:
                    errors.append(
                        f"Variable {key[2]} (scope: {key[0]}) references "
                        f"unknown consumer step: {step_id}"
                    )
        return errors

    def lookup(self, name: str) -> VariableSymbol | None:
        """Look up a variable by name across all scopes.

        Prefers global scope when the same name exists in multiple scopes.

        Args:
            name: Variable name

        Returns:
            VariableSymbol if found, None otherwise
        """
        # Prefer global scope
        if name in self.variables:
            return self.variables[name]
        # Search all scopes
        for key, var in self._variables.items():
            if key[2] == name:
                return var
        return None

    def declare_scoped(
        self,
        name: str,
        data_type: str,
        source: str,
        description: str,
        scope_kind: Literal["global", "worker", "handoff"] = "global",
        scope_id: str | None = None,
        flow_ref: str = "main",
        block_ref: str | None = None,
    ) -> None:
        """Declare a variable with scope support.

        Args:
            name: Variable name
            data_type: Data type
            source: Variable source
            description: Variable description
            scope_kind: Scope type (global/worker/handoff)
            scope_id: Scope ID (worker_id or handoff_id)
            flow_ref: Associated flow
            block_ref: Associated block

        Design Decision D4: Uses composite key (scope_kind, scope_id, name)
        """
        key = (scope_kind, scope_id, name)
        var = VariableSymbol(
            name=name,
            data_type=data_type,
            source=source,
            description=description,
            scope_kind=scope_kind,
            scope_id=scope_id,
            flow_ref=flow_ref,
            block_ref=block_ref,
        )
        self._variables[key] = var

        # Backward compatibility: global variables also stored in self.variables
        if scope_kind == "global":
            self.variables[name] = var

    def get_variables_for_worker(self, worker_id: str) -> dict[str, VariableSymbol]:
        """Get variables visible to a specific worker.

        Returns global + worker-scoped variables.

        Args:
            worker_id: Worker ID

        Returns:
            Dictionary mapping variable name to VariableSymbol
        """
        result = {}

        for key, var in self._variables.items():
            if key[0] == "global" or (key[0] == "worker" and key[1] == worker_id):
                result[var.name] = var

        return result

    def get_variables_for_handoff(self, handoff_id: str) -> dict[str, VariableSymbol]:
        """Get variables visible to a specific handoff.

        Returns global + handoff-scoped variables.

        Args:
            handoff_id: Handoff ID

        Returns:
            Dictionary mapping variable name to VariableSymbol
        """
        result = {}

        for key, var in self._variables.items():
            if key[0] == "global" or (key[0] == "handoff" and key[1] == handoff_id):
                result[var.name] = var

        return result

    def get_variable_list_for_worker_prompt(self, worker_id: str) -> str:
        """Generate variable list text for a worker's LLM prompt.

        Args:
            worker_id: Worker ID

        Returns:
            Formatted variable list string
        """
        visible_vars = self.get_variables_for_worker(worker_id)
        if not visible_vars:
            return "No variables available."

        lines = []
        for var in visible_vars.values():
            scope_info = ""
            if var.scope_kind == "worker":
                scope_info = f" [worker: {var.scope_id}]"
            elif var.scope_kind == "handoff":
                scope_info = f" [handoff: {var.scope_id}]"
            lines.append(
                f"- {var.name}: {var.data_type} ({var.source}){scope_info} - {var.description}"
            )
        return "\n".join(lines)

    def get_all_declared_variables(self) -> dict[str, VariableSymbol]:
        """Get all declared variables for SPL DEFINE_VARIABLES.

        Includes:
        - Global variables
        - All contract variables (input/output)
        - All rendered step variables (if declared)

        Excludes:
        - Worker internal variables (unless declared as contract)
        """
        result = {}

        for key, var in self._variables.items():
            # Global variables always included
            if key[0] == "global":
                result[var.name] = var
            # Contract variables (input/output) always included
            elif var.source in ("input", "output"):
                result[var.name] = var
            # Rendered step variables included if declared
            elif var.declared:
                result[var.name] = var

        return result
