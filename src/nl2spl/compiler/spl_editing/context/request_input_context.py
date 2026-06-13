"""Request input context builder (stub for later expansion)."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.context.base import RepairContextBuilder
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairContext, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot


class RequestInputContextBuilder(RepairContextBuilder):
    context_id = "request_input_context"

    def build(
        self, issue: EditableIssue, target: RepairTarget,
        snapshot: ArtifactSnapshot, user_instruction: str | None = None,
    ) -> RepairContext:
        return RepairContext(issue=issue, target=target, user_instruction=user_instruction)
