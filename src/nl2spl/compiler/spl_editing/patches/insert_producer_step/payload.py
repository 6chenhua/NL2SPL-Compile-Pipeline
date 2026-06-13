"""InsertProducerStep payload."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nl2spl.compiler.spl_editing.patches.base import PatchPayload


@dataclass(frozen=True)
class InsertProducerStepPayload(PatchPayload):
    worker_id: str
    output_name: str
    producer_text: str
    command_type: Literal["GENERAL_COMMAND", "REQUEST_INPUT"] = "GENERAL_COMMAND"
    insertion_target: Literal["main_flow", "block", "before_output"] = "main_flow"
    block_ref: str | None = None
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
