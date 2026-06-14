"""Worker promotion context builder."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.context.base import RepairContextBuilder
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairTarget,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot


class WorkerPromotionContextBuilder(RepairContextBuilder):
    context_id = "worker_promotion_context"

    def build(
        self, issue: EditableIssue, target: RepairTarget,
        snapshot: ArtifactSnapshot, user_instruction: str | None = None,
    ) -> RepairContext:
        # Find the single child worker from worker plan, if exactly one exists
        child_worker_id: str | None = None
        plan = snapshot.worker_plan
        if plan is not None:
            child_workers = [
                w.worker_id for w in plan.workers
                if getattr(w, "kind", None) == "child"
            ]
            if len(child_workers) == 1:
                child_worker_id = child_workers[0]

        extra: dict = {}
        if child_worker_id is not None:
            extra["derived_child_worker_id"] = child_worker_id

        meta: dict[str, object] = {}
        if child_worker_id is not None:
            meta["derived_child_worker_id"] = child_worker_id
            child = next(
                (
                    w for w in (plan.workers if plan is not None else [])
                    if w.worker_id == child_worker_id
                ),
                None,
            )
            if child is not None:
                meta["child_input_fields"] = [
                    field.name for field in child.input_contract
                ]
                meta["child_output_fields"] = [
                    field.name for field in child.output_contract
                ]
        if plan is not None:
            meta["parent_worker_id"] = plan.main_worker_id

        return RepairContext(
            issue=issue, target=target,
            worker_scope=target.worker_id,
            user_instruction=user_instruction,
            related_worker_plan_refs=(issue.target_ref,),
            metadata=meta,
        )
