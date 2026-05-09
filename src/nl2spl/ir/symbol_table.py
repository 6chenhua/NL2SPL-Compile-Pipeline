"""SymbolTable - Variable declaration and reference management."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VariableSymbol:
    """Variable symbol information.

    Attributes:
        name: Variable name
        data_type: Data type
        source: Variable source
        description: Variable description
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
    flow_ref: str = "main"
    block_ref: str | None = None
    producer_step: str | None = None
    consumer_steps: list[str] = field(default_factory=list)
    declared: bool = True


class SymbolTable:
    """Symbol table for variable management.

    Manages variable declarations and references for SPL generation.
    """

    def __init__(self) -> None:
        """Initialize empty symbol table."""
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
        """Declare a new variable.

        Args:
            name: Variable name
            data_type: Data type
            source: Variable source
            description: Variable description
            flow_ref: Associated flow
            block_ref: Associated block
        """
        self.variables[name] = VariableSymbol(
            name=name,
            data_type=data_type,
            source=source,
            description=description,
            flow_ref=flow_ref,
            block_ref=block_ref,
        )

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
        if not self.variables:
            return "(No known variables)"

        lines = []
        for name, var in self.variables.items():
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

    def add_consumer(self, name: str, step_id: str) -> None:
        """Record which step consumes a variable.

        Args:
            name: Variable name
            step_id: Step ID
        """
        if name in self.variables:
            if step_id not in self.variables[name].consumer_steps:
                self.variables[name].consumer_steps.append(step_id)

    def validate_references(self, known_step_ids: set[str]) -> list[str]:
        """Validate all references.

        Args:
            known_step_ids: Set of known step IDs

        Returns:
            List of validation errors
        """
        errors = []
        for name, var in self.variables.items():
            if var.producer_step and var.producer_step not in known_step_ids:
                errors.append(
                    f"Variable {name} references unknown producer step: {var.producer_step}"
                )
            for step_id in var.consumer_steps:
                if step_id not in known_step_ids:
                    errors.append(
                        f"Variable {name} references unknown consumer step: {step_id}"
                    )
        return errors
