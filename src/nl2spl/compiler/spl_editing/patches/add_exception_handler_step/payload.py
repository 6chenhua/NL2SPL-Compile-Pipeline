"""AddExceptionHandlerStep payload schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nl2spl.compiler.spl_editing.patches.base import PatchPayload

CommandType = Literal["GENERAL_COMMAND", "REQUEST_INPUT", "DISPLAY_MESSAGE"]


@dataclass(frozen=True)
class AddExceptionHandlerStepPayload(PatchPayload):
    """Payload for adding a handler step to an exception flow."""

    worker_id: str
    exception_flow_id: str
    handler_text: str
    command_type: CommandType = "GENERAL_COMMAND"
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    insertion_policy: Literal["append_to_exception_flow"] = "append_to_exception_flow"
