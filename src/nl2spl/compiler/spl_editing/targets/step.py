"""Step target resolver (stub for REQUEST_INPUT, CALL_API, INVOKE_WORKER).

These construct types are not in the MVP repair scope yet but need
resolvers so the extractor can reference them without crashing.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.targets.base import IssueTargetResolver


class StepTargetResolver(IssueTargetResolver):
    """Stub resolver for step-level constructs.

    Returns a minimal ``RepairTarget`` with ``editable_artifacts``
    set to ``("WorkerStepPlanIR",)``.  MVP consumers should check
    the ``RepairCatalog`` and only call this for supported subtypes.
    """

    resolver_id = "step_target"

    def resolve(
        self, issue: EditableIssue, snapshot: ArtifactSnapshot,
    ) -> RepairTarget:
        return RepairTarget(
            target_ref=issue.target_ref,
            target_kind=issue.irs_ref.construct_type,
            irs_ref=issue.irs_ref,
            affordance_id=issue.default_affordance_id or "",
            construct_path=issue.irs_ref.construct_path,
            editable_artifacts=("WorkerStepPlanIR",),
        )
