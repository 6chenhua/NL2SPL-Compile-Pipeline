"""SPL preview for AddExceptionHandlerStep."""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.spl_editing.patches.base import PatchPreviewer


class AddExceptionHandlerStepPreviewer(PatchPreviewer):
    """Generate a human-readable SPL preview."""

    def preview(self, payload: dict[str, Any]) -> str:
        cmd = payload.get("command_type", "GENERAL_COMMAND")
        text = payload.get("handler_text", "")
        inputs = payload.get("inputs", [])
        outputs = payload.get("outputs", [])
        parts = [f"[{cmd}] {text}"]
        if inputs:
            parts.append(f"  inputs: {', '.join(inputs)}")
        if outputs:
            parts.append(f"  outputs: {', '.join(outputs)}")
        return "\n".join(parts)
