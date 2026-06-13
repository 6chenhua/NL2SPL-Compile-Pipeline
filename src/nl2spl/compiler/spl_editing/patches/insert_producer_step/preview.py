"""InsertProducerStep previewer."""

from typing import Any
from nl2spl.compiler.spl_editing.patches.base import PatchPreviewer


class InsertProducerStepPreviewer(PatchPreviewer):
    def preview(self, payload: dict[str, Any]) -> str:
        cmd = payload.get("command_type", "GENERAL_COMMAND")
        text = payload.get("producer_text", "")
        return f"[{cmd}] {text}"
