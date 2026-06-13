"""Worker handoff context builder."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.context.base import RepairContextBuilder
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairContext, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot


class WorkerHandoffContextBuilder(RepairContextBuilder):
    context_id = "handoff_context"

    def build(
        self, issue: EditableIssue, target: RepairTarget,
        snapshot: ArtifactSnapshot, user_instruction: str | None = None,
    ) -> RepairContext:
        return RepairContext(
            issue=issue, target=target,
            worker_scope=target.worker_id,
            user_instruction=user_instruction,
            related_worker_plan_refs=(issue.target_ref,),
        )
