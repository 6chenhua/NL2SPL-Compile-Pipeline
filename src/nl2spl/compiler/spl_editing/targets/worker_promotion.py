"""Worker promotion target resolver."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.targets.base import IssueTargetResolver


class WorkerPromotionTargetResolver(IssueTargetResolver):
    """Resolve worker promotion issues to a candidate + worker plan target."""

    resolver_id = "worker_promotion_target"

    def resolve(
        self, issue: EditableIssue, snapshot: ArtifactSnapshot,
    ) -> RepairTarget:
        self._guard_construct(issue)
        candidate_id = self._extract_candidate_id(issue.target_ref)
        if candidate_id is None:
            raise UnsupportedIssueError(
                f"Cannot parse 'worker_promotion:{{id}}' from "
                f"target_ref '{issue.target_ref}'"
            )
        return RepairTarget(
            target_ref=issue.target_ref,
            target_kind="WORKER_PROMOTION",
            irs_ref=issue.irs_ref,
            affordance_id=(
                issue.default_affordance_id
                or "worker_promotion.resolve_contract"
            ),
            construct_path=issue.irs_ref.construct_path,
            worker_id=candidate_id,
            editable_artifacts=(
                "WorkerPlanIR", "WorkerHandoffIR", "WorkerStepPlanIR",
            ),
            subtype="delegation_intent_contract",
        )

    @staticmethod
    def _extract_candidate_id(ref: str) -> str | None:
        if ref.startswith("worker_promotion:"):
            cid = ref[len("worker_promotion:"):]
            return cid if cid else None
        return None

    @staticmethod
    def _guard_construct(issue: EditableIssue) -> None:
        if issue.irs_ref.construct_type != "WORKER_PROMOTION":
            raise UnsupportedIssueError(
                f"WorkerPromotionTargetResolver cannot resolve "
                f"construct_type '{issue.irs_ref.construct_type}'"
            )
