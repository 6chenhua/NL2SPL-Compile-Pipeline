"""Required output target resolver."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.targets.base import IssueTargetResolver


class RequiredOutputTargetResolver(IssueTargetResolver):
    """Resolve missing-producer issues to the target output + worker."""

    resolver_id = "required_output_target"

    def resolve(
        self,
        issue: EditableIssue,
        snapshot: ArtifactSnapshot,
    ) -> RepairTarget:
        self._guard_construct(issue)
        worker_id, output_name = self._parse_target(issue.target_ref)
        if worker_id is None or output_name is None:
            raise UnsupportedIssueError(
                f"Cannot parse 'worker:{{id}}.output:{{name}}' from target_ref '{issue.target_ref}'"
            )
        return RepairTarget(
            target_ref=issue.target_ref,
            target_kind="REQUIRED_OUTPUT",
            irs_ref=issue.irs_ref,
            affordance_id=(
                issue.default_affordance_id or "required_output.insert_or_bind_producer"
            ),
            construct_path=issue.irs_ref.construct_path,
            worker_id=worker_id,
            canonical_name=output_name,
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        )

    @staticmethod
    def _parse_target(ref: str) -> tuple[str | None, str | None]:
        """Parse ``worker:{worker_id}.output:{output_name}``.

        Returns ``(None, None)`` when the shape does not match or
        either ID is empty.
        """
        if not ref.startswith("worker:"):
            return None, None
        rest = ref[len("worker:") :]
        marker = ".output:"
        idx = rest.find(marker)
        if idx <= 0:
            return None, None
        worker_id = rest[:idx]
        output_name = rest[idx + len(marker) :]
        if not worker_id or not output_name:
            return None, None
        return worker_id, output_name

    @staticmethod
    def _guard_construct(issue: EditableIssue) -> None:
        if issue.irs_ref.construct_type != "REQUIRED_OUTPUT":
            raise UnsupportedIssueError(
                f"RequiredOutputTargetResolver cannot resolve "
                f"construct_type '{issue.irs_ref.construct_type}'"
            )
