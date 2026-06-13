"""Handoff target resolver (stub for INVOKE_WORKER handoff scenarios)."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.targets.base import IssueTargetResolver


class HandoffTargetResolver(IssueTargetResolver):
    """Stub resolver for handoff-level constructs."""

    resolver_id = "handoff_target_generic"

    def resolve(
        self, issue: EditableIssue, snapshot: ArtifactSnapshot,
    ) -> RepairTarget:
        return RepairTarget(
            target_ref=issue.target_ref,
            target_kind=issue.irs_ref.construct_type,
            irs_ref=issue.irs_ref,
            affordance_id=issue.default_affordance_id or "",
            construct_path=issue.irs_ref.construct_path,
            editable_artifacts=("WorkerHandoffIR",),
        )
