"""Required output context builder."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.context.base import RepairContextBuilder
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairTarget,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot


class RequiredOutputContextBuilder(RepairContextBuilder):
    context_id = "required_output_context"

    def build(
        self,
        issue: EditableIssue,
        target: RepairTarget,
        snapshot: ArtifactSnapshot,
        user_instruction: str | None = None,
    ) -> RepairContext:
        # Collect existing renderable steps for the target worker
        existing_steps: list = []
        sp = snapshot.worker_step_plan
        if sp is not None and target.worker_id is not None:
            existing_steps = list(sp.worker_steps.get(target.worker_id, []))

        return RepairContext(
            issue=issue,
            target=target,
            worker_scope=target.worker_id,
            user_instruction=user_instruction,
            related_steps=tuple(existing_steps),
            related_outputs=(target.canonical_name,) if target.canonical_name else (),
        )
