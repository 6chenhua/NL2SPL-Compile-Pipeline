"""Exception flow target resolver.

Resolves ``EXCEPTION_FLOW.handler_action`` issues to a concrete
worker + exception flow target.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.targets.base import IssueTargetResolver


class ExceptionFlowTargetResolver(IssueTargetResolver):
    """Resolve missing-handler issues to a worker + exception flow target."""

    resolver_id = "exception_flow_target"

    def resolve(
        self, issue: EditableIssue, snapshot: ArtifactSnapshot,
    ) -> RepairTarget:
        self._guard_construct(issue)
        worker_id, flow_id = self._parse_target(issue.target_ref)
        if worker_id is None or flow_id is None:
            raise UnsupportedIssueError(
                f"Cannot parse 'worker:{{id}}.exception_flow:{{fid}}' "
                f"from target_ref '{issue.target_ref}'"
            )
        return RepairTarget(
            target_ref=issue.target_ref,
            target_kind="EXCEPTION_FLOW",
            irs_ref=issue.irs_ref,
            affordance_id=(
                issue.default_affordance_id
                or "exception_flow.add_handler_step"
            ),
            construct_path=issue.irs_ref.construct_path,
            worker_id=worker_id,
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        )

    @staticmethod
    def _parse_target(ref: str) -> tuple[str | None, str | None]:
        """Parse ``worker:{worker_id}.exception_flow:{flow_id}``.

        Returns ``(None, None)`` when the shape does not match or
        either ID is empty.
        """
        if not ref.startswith("worker:"):
            return None, None
        rest = ref[len("worker:"):]
        marker = ".exception_flow:"
        idx = rest.find(marker)
        if idx <= 0:
            return None, None
        worker_id = rest[:idx]
        flow_id = rest[idx + len(marker):]
        if not worker_id or not flow_id:
            return None, None
        return worker_id, flow_id

    @staticmethod
    def _guard_construct(issue: EditableIssue) -> None:
        if issue.irs_ref.construct_type != "EXCEPTION_FLOW":
            raise UnsupportedIssueError(
                f"ExceptionFlowTargetResolver cannot resolve "
                f"construct_type '{issue.irs_ref.construct_type}'"
            )
