from __future__ import annotations

from dataclasses import replace

from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairContext, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.presentation.resolvers.issue_subject import (
    issue_subject_for,
)
from nl2spl.compiler.spl_editing.resolution import PromotionResolutionMarker
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR

TARGET_REF = "worker_promotion:del_s31"


def _irs_ref() -> DiagnosticIRSRef:
    return DiagnosticIRSRef(
        construct_type="WORKER_PROMOTION",
        construct_id=TARGET_REF,
        slot_name="promotion_input_contract",
        construct_path=("routes", "annotations", "s31"),
    )


def _issue() -> EditableIssue:
    return EditableIssue(
        issue_id="issue_worker_promotion",
        primary_diagnostic_id="diag_worker_promotion",
        related_diagnostic_ids=("diag_worker_promotion",),
        issue_group_id="worker_promotion_group:del_s31",
        kind="type_or_contract_ambiguity",
        target_ref=TARGET_REF,
        irs_ref=_irs_ref(),
        missing_slot="promotion_input_contract",
        source_span_ids=("s31",),
        message="Worker promotion is incomplete.",
        affordance_ids=("worker_delegation.complete_closure.v2",),
        default_affordance_id="worker_delegation.complete_closure.v2",
    )


def _target() -> RepairTarget:
    return RepairTarget(
        target_ref=TARGET_REF,
        target_kind="WORKER_PROMOTION",
        irs_ref=_irs_ref(),
        affordance_id="worker_delegation.complete_closure.v2",
        construct_path=("routes", "annotations", "s31"),
        canonical_name="del_s31",
    )


def _context(issue: EditableIssue, target: RepairTarget) -> RepairContext:
    return RepairContext(
        issue=issue,
        target=target,
        metadata={
            "derived_child_worker_id": "retrieve_approved_sources",
            "candidate_task_summary": "source gathering or template matching",
        },
    )


def _snapshot(
    marker: PromotionResolutionMarker | None = None,
) -> ArtifactSnapshot:
    main = WorkerSpecIR(
        worker_id="worker_main",
        worker_name="MainWorker",
        kind="main",
        purpose="Main workflow",
    )
    child = WorkerSpecIR(
        worker_id="retrieve_approved_sources",
        worker_name="Worker_retrieve_approved_sources",
        kind="child",
        purpose="Retrieve approved sources",
    )
    return ArtifactSnapshot(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=0,
        spans=(SpanIR("s31", "Retrieve approved sources before answering."),),
        worker_plan=WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[main, child],
        ),
        promotion_resolution_markers=() if marker is None else (marker,),
    )


def _marker(**overrides) -> PromotionResolutionMarker:
    marker = PromotionResolutionMarker(
        marker_id="promotion_resolution:directive_1",
        target_worker_promotion_id=TARGET_REF,
        resolved_diagnostic_group_id="worker_promotion_group:del_s31",
        resolution_kind="defined_child_worker",
        normalized_directive_id="directive_1",
        materialized_construct_refs=("worker:retrieve_approved_sources",),
        evidence_ref="evidence_packet_1",
        repair_patch_id="patch_1",
        user_confirmed=True,
    )
    return replace(marker, **overrides)


def test_unresolved_promotion_ignores_derived_child_worker_metadata() -> None:
    issue = _issue()
    target = _target()

    subject = issue_subject_for(
        issue,
        _snapshot(),
        target=target,
        context=_context(issue, target),
    )

    assert subject.subject_kind == "delegated_task_candidate"
    assert subject.display_name is None
    assert subject.summary == "source gathering or template matching"
    assert subject.specificity == "candidate"


def test_unconfirmed_marker_does_not_project_child_worker_identity() -> None:
    issue = _issue()
    target = _target()

    subject = issue_subject_for(
        issue,
        _snapshot(_marker(user_confirmed=False)),
        target=target,
        context=_context(issue, target),
    )

    assert subject.subject_kind == "delegated_task_candidate"
    assert subject.display_name is None


def test_target_mismatched_marker_does_not_project_child_worker_identity() -> None:
    issue = _issue()
    target = _target()

    subject = issue_subject_for(
        issue,
        _snapshot(_marker(target_worker_promotion_id="worker_promotion:other")),
        target=target,
        context=_context(issue, target),
    )

    assert subject.subject_kind == "delegated_task_candidate"
    assert subject.display_name is None


def test_confirmed_define_child_marker_projects_worker_identity() -> None:
    issue = _issue()
    target = _target()

    subject = issue_subject_for(
        issue,
        _snapshot(_marker()),
        target=target,
        context=_context(issue, target),
    )

    assert subject.subject_kind == "worker"
    assert subject.display_name == "Worker_retrieve_approved_sources"
    assert subject.summary == "Retrieve approved sources"
    assert subject.specificity == "concrete"


def test_confirmed_keep_main_marker_projects_resolved_candidate() -> None:
    issue = _issue()
    target = _target()

    subject = issue_subject_for(
        issue,
        _snapshot(
            _marker(
                resolution_kind="kept_in_main_flow",
                materialized_construct_refs=("step:worker_main:cmd_1",),
            )
        ),
        target=target,
        context=_context(issue, target),
    )

    assert subject.subject_kind == "delegated_task_candidate"
    assert subject.display_name is None
    assert subject.summary == "source gathering or template matching"
    assert subject.specificity == "concrete"
