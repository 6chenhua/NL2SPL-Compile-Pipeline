"""Structured display context resolution.

This module does not parse diagnostic prose.  It reads structured snapshot
artifacts, target resolver output, repair context metadata, and source spans.
"""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairTarget,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.presentation.contract.categories import (
    IssueCategory,
)
from nl2spl.compiler.spl_editing.presentation.contract.quality import (
    PresentationQuality,
)
from nl2spl.compiler.spl_editing.presentation.resolvers.source_excerpt import (
    source_excerpt_for_issue,
)

_PROMOTION_SLOT_LABELS = {
    "promotion_input_contract": "input contract",
    "promotion_output_contract": "output contract",
    "promotion_invocation_point": "invocation point",
    "promotion_result_handoff": "result handoff",
}


@dataclass(frozen=True)
class DisplayContext:
    category: IssueCategory
    condition_text: str | None = None
    output_name: str | None = None
    missing_items: tuple[str, ...] = ()
    source_excerpt: str | None = None
    quality: PresentationQuality = PresentationQuality.COMPLETE
    degradation_reason: str | None = None


def build_display_context(
    issue: EditableIssue,
    snapshot: ArtifactSnapshot,
    *,
    target: RepairTarget | None = None,
    context: RepairContext | None = None,
    related_diagnostics: tuple[object, ...] = (),
) -> DisplayContext:
    category = category_for_issue(issue)
    source = source_excerpt_for_issue(issue, snapshot, related_diagnostics)

    if category == IssueCategory.EXCEPTION_HANDLING:
        condition = _exception_condition(issue, snapshot, target, context)
        return DisplayContext(
            category=category,
            condition_text=condition,
            source_excerpt=source,
            quality=(
                PresentationQuality.COMPLETE
                if condition
                else PresentationQuality.DEGRADED
            ),
            degradation_reason=None if condition else "Condition unavailable",
        )

    if category == IssueCategory.REQUIRED_OUTPUTS:
        output_name = _required_output_name(issue, target, context)
        return DisplayContext(
            category=category,
            output_name=output_name,
            source_excerpt=source,
            quality=(
                PresentationQuality.COMPLETE
                if output_name
                else PresentationQuality.DEGRADED
            ),
            degradation_reason=None if output_name else "Output name unavailable",
        )

    if category == IssueCategory.WORKER_DELEGATION:
        missing_items = _worker_delegation_missing_items(issue, related_diagnostics)
        return DisplayContext(
            category=category,
            missing_items=missing_items,
            source_excerpt=source,
            quality=PresentationQuality.COMPLETE,
        )

    return DisplayContext(
        category=category,
        source_excerpt=source,
        quality=PresentationQuality.DEGRADED,
        degradation_reason="Display context unavailable",
    )


def category_for_issue(issue: EditableIssue) -> IssueCategory:
    if issue.kind == "missing_handler" and issue.irs_ref.construct_type == "EXCEPTION_FLOW":
        return IssueCategory.EXCEPTION_HANDLING
    if (
        issue.kind == "missing_output_producer"
        and issue.irs_ref.construct_type == "REQUIRED_OUTPUT"
    ):
        return IssueCategory.REQUIRED_OUTPUTS
    if (
        issue.kind == "type_or_contract_ambiguity"
        and issue.irs_ref.construct_type == "WORKER_PROMOTION"
    ):
        return IssueCategory.WORKER_DELEGATION
    if issue.repairability == "review_only":
        return IssueCategory.REVIEW_ONLY
    return IssueCategory.OTHER_EDITABLE


def _exception_condition(
    issue: EditableIssue,
    snapshot: ArtifactSnapshot,
    target: RepairTarget | None,
    context: RepairContext | None,
) -> str | None:
    meta_condition = None
    if context is not None:
        value = context.metadata.get("condition_text")
        if isinstance(value, str) and value.strip():
            meta_condition = value.strip()
    if meta_condition:
        return meta_condition

    worker_id = (
        target.worker_id
        if target is not None
        else _worker_from_target_ref(issue.target_ref)
    )
    flow_id = _flow_id_from_exception_target(issue.target_ref)
    if not worker_id or not flow_id:
        return None
    flow_plan = snapshot.worker_flow_plan
    if flow_plan is None:
        return None
    worker_flow = flow_plan.worker_flows.get(worker_id)
    if worker_flow is None:
        return None
    for exc_flow in worker_flow.exception_flows:
        if exc_flow.flow_id == flow_id and exc_flow.condition_text.strip():
            return exc_flow.condition_text
    return None


def _required_output_name(
    issue: EditableIssue,
    target: RepairTarget | None,
    context: RepairContext | None,
) -> str | None:
    if context is not None and context.related_outputs:
        for value in context.related_outputs:
            if isinstance(value, str) and value.strip() and value != "producer":
                return value
    ref = target.target_ref if target is not None else issue.target_ref
    marker = ".output:"
    if ref.startswith("worker:") and marker in ref:
        value = ref.split(marker, 1)[1]
        return value if value.strip() else None
    return None


def _worker_delegation_missing_items(
    issue: EditableIssue,
    related_diagnostics: tuple[object, ...],
) -> tuple[str, ...]:
    labels: list[str] = []
    diagnostics = related_diagnostics or ()
    for diagnostic in diagnostics:
        irs_ref = getattr(diagnostic, "metadata", {}).get("irs_ref", {})
        slot = irs_ref.get("slot_name", "") if isinstance(irs_ref, dict) else ""
        label = _PROMOTION_SLOT_LABELS.get(slot)
        if label and label not in labels:
            labels.append(label)
    if not labels:
        label = _PROMOTION_SLOT_LABELS.get(issue.irs_ref.slot_name)
        if label:
            labels.append(label)
    return tuple(labels)


def _worker_from_target_ref(ref: str) -> str | None:
    if not ref.startswith("worker:"):
        return None
    rest = ref[len("worker:"):]
    marker = ".exception_flow:"
    if marker not in rest:
        return None
    worker_id = rest.split(marker, 1)[0]
    return worker_id or None


def _flow_id_from_exception_target(ref: str) -> str | None:
    marker = ".exception_flow:"
    if marker not in ref:
        return None
    value = ref.split(marker, 1)[1]
    return value or None


__all__ = ["DisplayContext", "build_display_context", "category_for_issue"]
