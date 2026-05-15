"""StepIR - Atomic action in workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CommandType = Literal[
    "GENERAL_COMMAND",
    "CALL_API",
    "INVOKE_WORKER",
    "REQUEST_INPUT",
    "DISPLAY_MESSAGE",
]

StepKind = Literal["normal", "tool", "user_input", "invoke", "display"]


@dataclass
class StepIR:
    """Atomic action in workflow.

    Attributes:
        step_id: Unique identifier (format: st{N})
        text: Step description
        source_span_ids: Source span IDs
        command_type: Command type
        inputs: Input variable names
        outputs: Output variable names
        integration_ref: Referenced API name (for CALL_API)
        flow_ref: Associated flow
        block_ref: Associated block
        kind: Step semantic type
        handoff_id: WorkerPlanIR handoff that produced this step, when applicable
    """

    step_id: str
    text: str
    source_span_ids: list[str]
    command_type: CommandType
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    integration_ref: str | None = None
    flow_ref: str = "main"
    block_ref: str = ""
    kind: StepKind = "normal"
    handoff_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate step_id format."""
        if not self.step_id.startswith("st"):
            raise ValueError(f"step_id must start with 'st', got: {self.step_id}")
