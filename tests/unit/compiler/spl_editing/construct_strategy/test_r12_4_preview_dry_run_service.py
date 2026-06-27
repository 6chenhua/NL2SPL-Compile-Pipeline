"""Unit tests for Phase R12.4B Preview Dry-Run Service."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.model import EditableIssue, EditingSession, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.materialization.registry import (
    build_default_materialization_registry,
)
from nl2spl.compiler.spl_editing.materialization.service import RepairMaterializationService
from nl2spl.compiler.spl_editing.preview import (
    PreviewDryRunService,
    PreviewError,
    PreviewStore,
    PreviewStoreError,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef, SelectableRefSet
from nl2spl.compiler.spl_editing.strategy import RepairDirective
from nl2spl.compiler.spl_editing.strategy.defaults import build_default_strategy_registry
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.worker_ir import ExceptionFlowRef
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)


@pytest.fixture
def strategy_registry():
    return build_default_strategy_registry()


@pytest.fixture
def mat_service():
    registry = build_default_materialization_registry()
    return RepairMaterializationService(registry)


@pytest.fixture
def preview_service(mat_service):
    return PreviewDryRunService(mat_service)


@pytest.fixture
def store():
    return PreviewStore()


def _make_snapshot(snapshot_id: str = "snap_1") -> ArtifactSnapshot:
    worker_plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[
            WorkerSpecIR("w_main", "Main", "main", "Main", boundary_kind="main_worker"),
            WorkerSpecIR(
                "child_worker",
                "Child Worker",
                "child",
                "Child worker",
                boundary_kind="bounded_subtask",
                input_contract=[
                    ContractFieldIR("request", "text", True, "Request", "input"),
                ],
                output_contract=[
                    ContractFieldIR("result", "text", True, "Result", "output"),
                ],
            ),
        ],
    )
    return ArtifactSnapshot(
        snapshot_id=snapshot_id,
        compile_run_id="run_1",
        overlay_version=0,
        worker_plan=worker_plan,
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={
                "w_main": FlowStructureIR(
                    exception_flows=[ExceptionFlowRef("exc_1", "Exception", [])],
                ),
                "child_worker": FlowStructureIR(),
            }
        ),
        worker_step_plan=WorkerStepPlanIR(
            "w_main",
            {
                "w_main": [],
                "child_worker": [],
            },
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "w_main": BlockStructureIR(),
                "child_worker": BlockStructureIR(),
            }
        ),
    )


def _make_refset(
    issue_id: str = "iss_1",
    snapshot_id: str = "snap_1",
    target_role: str = "target_exception_flow",
    target_worker: str = "w_main",
    target_name: str = "exc_1",
    policy_id: str = "exception_flow.handler.selectable_refs.v1",
    is_available: bool = True,
) -> SelectableRefSet:
    ref_1 = SelectableRef(
        ref_id="r1",
        ref_kind="variable",
        ref_role="selectable_input",
        canonical_name="var1",
        display_label="var1",
    )
    ref_2 = SelectableRef(
        ref_id="r2",
        ref_kind="variable",
        ref_role="selectable_input",
        canonical_name="var2",
        display_label="var2",
    )
    target_ref = SelectableRef(
        ref_id="t1",
        ref_kind="exception_flow",
        ref_role=target_role,  # type: ignore[arg-type]
        canonical_name=target_name,
        display_label=target_name,
        worker_id=target_worker,
    )
    return SelectableRefSet(
        set_id="refset_1",
        issue_id=issue_id,
        snapshot_id=snapshot_id,
        worker_scope="w_main",
        refs=(ref_1, ref_2, target_ref),
        policy_id=policy_id,
        is_available=is_available,
    )


def _make_target(
    target_ref: str = "t1",
    construct_type: str = "EXCEPTION_FLOW",
    slot_name: str = "handler_action",
    affordance_id: str = "exception_flow.add_handler_step",
    worker_id: str = "w_main",
    canonical_name: str = "exc_1",
) -> RepairTarget:
    return RepairTarget(
        target_ref=target_ref,
        target_kind="element",
        irs_ref=DiagnosticIRSRef(
            construct_type=construct_type,
            construct_id="target_1",
            slot_name=slot_name,
            construct_path=(),
            source_authority="post_normalize_irs",
        ),
        affordance_id=affordance_id,
        construct_path=(),
        worker_id=worker_id,
        canonical_name=canonical_name,
        editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
    )


def _make_session(
    session_id: str = "sess_1",
    issue_id: str = "iss_1",
    snapshot_id: str = "snap_1",
) -> EditingSession:
    issue = EditableIssue(
        issue_id=issue_id,
        primary_diagnostic_id="d1",
        related_diagnostic_ids=(),
        issue_group_id=None,
        kind="missing_handler",
        target_ref="t1",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="target_1",
            slot_name="handler_action",
            construct_path=(),
            source_authority="post_normalize_irs",
        ),
        missing_slot="handler_action",
        source_span_ids=(),
        message="msg",
        affordance_ids=("exception_flow.add_handler_step",),
        default_affordance_id="exception_flow.add_handler_step",
    )
    return EditingSession(
        session_id=session_id,
        compile_run_id="run_1",
        artifact_snapshot_id=snapshot_id,
        overlay_version=0,
        issue=issue,
        created_at="2026-06-26T20:00:00Z",
    )


def test_preview_dry_run_happy_path(preview_service, strategy_registry, store) -> None:
    """Verify happy path preview dry-run generates result and stores it correctly."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    snapshot = _make_snapshot("snap_1")
    refset = _make_refset("iss_1", "snap_1")
    target = _make_target()
    session = _make_session("sess_1", "iss_1", "snap_1")

    directive = RepairDirective(
        directive_id="dir_1",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        requested_behavior="test handler goal",
        selected_ref_hints=("r1",),
    )

    res = preview_service.preview(
        session=session,
        issue=session.issue,
        strategy=strategy,
        directive=directive,
        target=target,
        refset=refset,
        snapshot=snapshot,
        store=store,
    )

    # 1. Output Validation
    assert res is not None
    assert res.base_snapshot_id == "snap_1"
    assert "[EXCEPTION_FLOW]" in res.rendered_preview
    assert "test handler goal" in res.rendered_preview
    assert "Patch adapter" not in res.rendered_preview
    assert "stage5." not in res.rendered_preview
    assert "stage7." not in res.rendered_preview
    assert len(res.slice_typed_plan_hashes) == 2
    assert len(res.preview_construct_hashes) == 2

    # 2. Hash Fields Presence
    assert res.intent_hash != ""
    assert res.directive_hash != ""
    assert res.closure_plan_hash != ""
    assert res.selected_refset_id == "refset_1"
    assert res.llm_generation_config_hash != ""

    # 3. Store Retrieval and Validation
    retrieved = store.get(res.preview_id)
    assert retrieved.preview_id == res.preview_id
    assert store.validate_applicable(res.preview_id, "sess_1", "iss_1", "snap_1") is True


def test_preview_dry_run_rejects_session_issue_snapshot_mismatches(
    preview_service, strategy_registry, store
) -> None:
    """Verify that mismatching session, issue, or snapshot details reject preview generation."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    snapshot = _make_snapshot("snap_1")
    refset = _make_refset("iss_1", "snap_1")
    target = _make_target()
    directive = RepairDirective(
        directive_id="dir_1",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        selected_ref_hints=("r1",),
    )

    # Session issue mismatch
    session_ok = _make_session("sess_1", "iss_1", "snap_1")
    bad_issue = EditableIssue(
        issue_id="iss_bad",
        primary_diagnostic_id="d1",
        related_diagnostic_ids=(),
        issue_group_id=None,
        kind="missing_handler",
        target_ref="t1",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="target_1",
            slot_name="handler_action",
            construct_path=(),
            source_authority="post_normalize_irs",
        ),
        missing_slot="handler_action",
        source_span_ids=(),
        message="msg",
    )
    with pytest.raises(PreviewError, match="Session issue ID"):
        preview_service.preview(
            session=session_ok,
            issue=bad_issue,
            strategy=strategy,
            directive=directive,
            target=target,
            refset=refset,
            snapshot=snapshot,
            store=store,
        )

    # Session snapshot mismatch
    bad_session_snap = _make_session("sess_1", "iss_1", "snap_bad")
    with pytest.raises(PreviewError, match="Session snapshot ID"):
        preview_service.preview(
            session=bad_session_snap,
            issue=session_ok.issue,
            strategy=strategy,
            directive=directive,
            target=target,
            refset=refset,
            snapshot=snapshot,
            store=store,
        )

    # Refset issue mismatch
    bad_refset_issue = _make_refset("iss_bad", "snap_1")
    with pytest.raises(PreviewError, match="Refset issue ID"):
        preview_service.preview(
            session=session_ok,
            issue=session_ok.issue,
            strategy=strategy,
            directive=directive,
            target=target,
            refset=bad_refset_issue,
            snapshot=snapshot,
            store=store,
        )

    # Refset snapshot mismatch
    bad_refset_snap = _make_refset("iss_1", "snap_bad")
    with pytest.raises(PreviewError, match="Refset snapshot ID"):
        preview_service.preview(
            session=session_ok,
            issue=session_ok.issue,
            strategy=strategy,
            directive=directive,
            target=target,
            refset=bad_refset_snap,
            snapshot=snapshot,
            store=store,
        )


def test_preview_dry_run_rejects_unknown_selected_ref(
    preview_service, strategy_registry, store
) -> None:
    """Verify that directive selected refs not in the refset are rejected."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    snapshot = _make_snapshot("snap_1")
    refset = _make_refset("iss_1", "snap_1")
    target = _make_target()
    session = _make_session("sess_1", "iss_1", "snap_1")

    directive = RepairDirective(
        directive_id="dir_1",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        selected_ref_hints=("r_unknown",),
    )

    with pytest.raises(PreviewError, match="Selected reference hints validation failed"):
        preview_service.preview(
            session=session,
            issue=session.issue,
            strategy=strategy,
            directive=directive,
            target=target,
            refset=refset,
            snapshot=snapshot,
            store=store,
        )


def test_preview_dry_run_rejects_mismatching_target_ref_structurally(
    preview_service, strategy_registry, store
) -> None:
    """Reject target resolution when no matching SelectableRef exists."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    snapshot = _make_snapshot("snap_1")
    refset = _make_refset("iss_1", "snap_1", target_name="exc_mismatch")
    target = _make_target(canonical_name="exc_1")
    session = _make_session("sess_1", "iss_1", "snap_1")

    directive = RepairDirective(
        directive_id="dir_1",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
    )

    with pytest.raises(PreviewError, match="Could not structurally resolve target reference"):
        preview_service.preview(
            session=session,
            issue=session.issue,
            strategy=strategy,
            directive=directive,
            target=target,
            refset=refset,
            snapshot=snapshot,
            store=store,
        )


def test_preview_dry_run_no_mutation_side_effects(
    preview_service, strategy_registry, store
) -> None:
    """Verify that dry-run preview does not write overlay files, events or change version."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    snapshot = _make_snapshot("snap_1")
    refset = _make_refset("iss_1", "snap_1")
    target = _make_target()
    session = _make_session("sess_1", "iss_1", "snap_1")

    directive = RepairDirective(
        directive_id="dir_1",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
    )

    preview_service.preview(
        session=session,
        issue=session.issue,
        strategy=strategy,
        directive=directive,
        target=target,
        refset=refset,
        snapshot=snapshot,
        store=store,
    )

    assert session.overlay_version == 0
    assert snapshot.overlay_version == 0
    assert not hasattr(store, "_overlay_events") or len(store._overlay_events) == 0


def test_preview_id_scoped_uniqueness(preview_service, strategy_registry, store) -> None:
    """Verify that same directive in different sessions/snapshots yields different preview_ids."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    snapshot_1 = _make_snapshot("snap_1")
    snapshot_2 = _make_snapshot("snap_2")
    refset_1 = _make_refset("iss_1", "snap_1")
    refset_2 = _make_refset("iss_1", "snap_2")
    target = _make_target()

    directive = RepairDirective(
        directive_id="dir_1",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
    )

    session_1 = _make_session("sess_1", "iss_1", "snap_1")
    res_1 = preview_service.preview(
        session=session_1,
        issue=session_1.issue,
        strategy=strategy,
        directive=directive,
        target=target,
        refset=refset_1,
        snapshot=snapshot_1,
        store=store,
    )

    session_2 = _make_session("sess_2", "iss_1", "snap_1")
    refset_1_sess2 = _make_refset("iss_1", "snap_1")
    res_2 = preview_service.preview(
        session=session_2,
        issue=session_2.issue,
        strategy=strategy,
        directive=directive,
        target=target,
        refset=refset_1_sess2,
        snapshot=snapshot_1,
        store=store,
    )

    session_1_snap2 = _make_session("sess_1", "iss_1", "snap_2")
    res_3 = preview_service.preview(
        session=session_1_snap2,
        issue=session_1_snap2.issue,
        strategy=strategy,
        directive=directive,
        target=target,
        refset=refset_2,
        snapshot=snapshot_2,
        store=store,
    )

    assert res_1.preview_id != res_2.preview_id
    assert res_1.preview_id != res_3.preview_id
    assert res_2.preview_id != res_3.preview_id

    assert store.validate_applicable(res_1.preview_id, "sess_1", "iss_1", "snap_1") is True
    with pytest.raises(PreviewStoreError, match="Session mismatch"):
        store.validate_applicable(res_1.preview_id, "sess_2", "iss_1", "snap_1")


def test_preview_dry_run_policy_and_availability_checks(
    preview_service, strategy_registry, store
) -> None:
    """Verify that mismatching selectable ref policy or unavailable refsets are rejected."""
    strategy = strategy_registry.get("exception_flow.complete_handler_action.v1")
    snapshot = _make_snapshot("snap_1")
    target = _make_target()
    session = _make_session("sess_1", "iss_1", "snap_1")

    directive = RepairDirective(
        directive_id="dir_1",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
    )

    # 1. Unavailable refset
    unavailable_refset = _make_refset("iss_1", "snap_1", is_available=False)
    with pytest.raises(PreviewError, match="SelectableRefSet is marked as unavailable"):
        preview_service.preview(
            session=session,
            issue=session.issue,
            strategy=strategy,
            directive=directive,
            target=target,
            refset=unavailable_refset,
            snapshot=snapshot,
            store=store,
        )

    # 2. Policy ID mismatch
    wrong_policy_refset = _make_refset("iss_1", "snap_1", policy_id="wrong_policy")
    with pytest.raises(PreviewError, match="Policy mismatch"):
        preview_service.preview(
            session=session,
            issue=session.issue,
            strategy=strategy,
            directive=directive,
            target=target,
            refset=wrong_policy_refset,
            snapshot=snapshot,
            store=store,
        )


def test_preview_worker_delegation_explicit_routing(
    preview_service, strategy_registry, store
) -> None:
    """Verify routing of the three worker delegation patch types."""
    strategy = strategy_registry.get("worker_delegation.complete_closure.v1")
    snapshot = _make_snapshot("snap_1")
    refset = _make_refset(
        "iss_1",
        "snap_1",
        target_role="target_worker",
        target_worker="w_main",
        target_name="child_worker",
        policy_id="worker_promotion.handoff.selectable_refs.v1",
    )
    target = _make_target(
        construct_type="WORKER_PROMOTION",
        slot_name="promotion_input_contract",
        affordance_id="worker_promotion.resolve_contract",
        worker_id="w_main",
        canonical_name="child_worker",
    )
    session = _make_session("sess_1", "iss_1", "snap_1")

    # A. Handoff contract route
    directive_handoff = RepairDirective(
        directive_id="dir_1",
        source="user",
        target_construct_type="WORKER_PROMOTION",
        target_slot_name="promotion_input_contract",
        requested_behavior="create handoff contract",
    )
    res_handoff = preview_service.preview(
        session=session,
        issue=session.issue,
        strategy=strategy,
        directive=directive_handoff,
        target=target,
        refset=refset,
        snapshot=snapshot,
        store=store,
    )
    assert "[INVOKE_WORKER child_worker" in res_handoff.rendered_preview
    assert "stage3_5." not in res_handoff.rendered_preview

    # B. Main flow inline route
    directive_main = RepairDirective(
        directive_id="dir_2",
        source="user",
        target_construct_type="WORKER_PROMOTION",
        target_slot_name="promotion_input_contract",
        requested_behavior="convert delegation to main flow step",
    )
    res_main = preview_service.preview(
        session=session,
        issue=session.issue,
        strategy=strategy,
        directive=directive_main,
        target=target,
        refset=refset,
        snapshot=snapshot,
        store=store,
    )
    assert "[COMMAND" in res_main.rendered_preview
    assert "main flow" in res_main.rendered_preview
    assert "stage7." not in res_main.rendered_preview

    # C. Request input route
    directive_request = RepairDirective(
        directive_id="dir_3",
        source="user",
        target_construct_type="WORKER_PROMOTION",
        target_slot_name="promotion_input_contract",
        requested_behavior="convert to request input step",
    )
    res_request = preview_service.preview(
        session=session,
        issue=session.issue,
        strategy=strategy,
        directive=directive_request,
        target=target,
        refset=refset,
        snapshot=snapshot,
        store=store,
    )
    assert "[INPUT DISPLAY" in res_request.rendered_preview
    assert "stage7." not in res_request.rendered_preview

    # D. Ambiguous behavior raises PreviewError
    directive_ambiguous = RepairDirective(
        directive_id="dir_4",
        source="user",
        target_construct_type="WORKER_PROMOTION",
        target_slot_name="promotion_input_contract",
        requested_behavior="unclear goal",
    )
    with pytest.raises(
        PreviewError, match="Cannot determine target patch type for worker delegation"
    ):
        preview_service.preview(
            session=session,
            issue=session.issue,
            strategy=strategy,
            directive=directive_ambiguous,
            target=target,
            refset=refset,
            snapshot=snapshot,
            store=store,
        )
