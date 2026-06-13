"""BindExistingProducerStep previewer."""

from typing import Any
from nl2spl.compiler.spl_editing.patches.base import PatchPreviewer


class BindExistingProducerStepPreviewer(PatchPreviewer):
    def preview(self, payload: dict[str, Any]) -> str:
        step_id = payload.get("step_id", "?")
        output_name = payload.get("output_name", "?")
        return f"Bind step '{step_id}' as producer of '{output_name}'"
