"""ConvertDelegationIntentToRequestInput payload."""

from dataclasses import dataclass
from typing import Literal

from nl2spl.compiler.spl_editing.patches.base import PatchPayload


@dataclass(frozen=True)
class ConvertDelegationIntentToRequestInputPayload(PatchPayload):
    worker_id: str
    prompt_text: str
    value_target: str
    outputs: tuple[str, ...] = ()
    insertion_target: Literal["main_flow", "block"] = "main_flow"
    source_signal_id: str | None = None
    block_ref: str | None = None
