"""Worker handoff target resolver."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.targets.base import IssueTargetResolver


class WorkerHandoffTargetResolver(IssueTargetResolver):
    """Resolve worker handoff issues (MVP-required, not stub)."""

    resolver_id = "handoff_target"

    def resolve(
        self, issue: EditableIssue, snapshot: ArtifactSnapshot,
    ) -> RepairTarget:
        self._guard_construct(issue)
        handoff_id = self._extract_handoff_id(issue.target_ref)
        if handoff_id is None:
            raise UnsupportedIssueError(
                f"Cannot parse 'worker_handoff:{{id}}' from "
                f"target_ref '{issue.target_ref}'"
            )
        return RepairTarget(
            target_ref=issue.target_ref,
            target_kind="WORKER_HANDOFF",
            irs_ref=issue.irs_ref,
            affordance_id=(
                issue.default_affordance_id
                or "worker_handoff.specify_target"
            ),
            construct_path=issue.irs_ref.construct_path,
            worker_id=handoff_id,
            editable_artifacts=("WorkerHandoffIR",),
        )

    @staticmethod
    def _extract_handoff_id(ref: str) -> str | None:
        if ref.startswith("worker_handoff:"):
            hid = ref[len("worker_handoff:"):]
            return hid if hid else None
        return None

    @staticmethod
    def _guard_construct(issue: EditableIssue) -> None:
        if issue.irs_ref.construct_type != "WORKER_HANDOFF":
            raise UnsupportedIssueError(
                f"WorkerHandoffTargetResolver cannot resolve "
                f"construct_type '{issue.irs_ref.construct_type}'"
            )
