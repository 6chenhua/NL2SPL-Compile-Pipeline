"""
Unit tests for SPL Editing fail-closed gate.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.compiler.spl_editing.core.model import EditingSession, RepairEvidence, RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.core.service import SPLEditingService
from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR


def test_editing_service_fail_closed_on_multi_output_patched_snapshot() -> None:
    # 1. Setup mock dependencies for SPLEditingService
    runtime_registry = MagicMock()
    service = SPLEditingService(runtime_registry)

    # Mock stores and internal getters
    service._sessions = MagicMock()
    service._confirmation_contexts = MagicMock()
    service._materialization = MagicMock()
    service._snapshots = MagicMock()
    service._overlays = MagicMock()
    service._suggestions = MagicMock()

    # Setup session
    session = EditingSession(
        session_id="session_123",
        compile_run_id="run_123",
        artifact_snapshot_id="snap_123",
        overlay_version=1,
        issue=MagicMock(),
        created_at="2026-07-07",
    )
    service._sessions.get.return_value = session

    # Setup snapshot and mock _get_snapshot
    base_snapshot = MagicMock(spec=ArtifactSnapshot)
    base_snapshot.snapshot_id = "snap_123"
    base_snapshot.overlay_version = 1
    base_snapshot.compile_run_id = "run_123"
    service._get_snapshot = MagicMock(return_value=base_snapshot)

    # Setup confirmation context
    ctx = MagicMock()
    ctx.session_id = "session_123"
    ctx.snapshot_id = "snap_123"
    ctx.overlay_version = 1
    ctx.intent_id = "intent_123"
    ctx.selected_ref_ids = ("ref_123",)
    ctx.catalog_entry = MagicMock()
    ctx.target = MagicMock()
    ctx.refset = MagicMock()
    ctx.resolved_refs = MagicMock()
    service._confirmation_contexts.begin_apply.return_value = ctx

    # Setup patch
    intent = ConstructRepairIntent(
        intent_id="intent_123",
        issue_id="issue_1",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="required_output:w_main:required_output_context::draft",
        target_slot_name="producer",
        target_ref_id="required_output:w_main:required_output_context::draft",
        selected_ref_ids=("ref_123",),
        materialization_plan_id="stage7.step_producer_repair.v1",
    )
    repair_patch = RepairPatch(
        patch_id="patch_123",
        affordance_id="aff_123",
        patch_type="SpecifyValueTarget",
        target_ref="step:st7",
        irs_ref=MagicMock(),
        base_compile_run_id="run_123",
        artifact_snapshot_id="snap_123",
        overlay_version=1,
        payload=intent,
        preconditions=(),
        evidence=RepairEvidence("user_confirmed_repair", "evidence text"),
        verification_lane="A",
    )

    # Mock suggestion
    suggestion = MagicMock()
    suggestion.session_id = "session_123"
    suggestion.patch = repair_patch
    service._suggestions.get.return_value = suggestion

    # Setup materialization result with multi-output step in patched snapshot
    multi_output_step = StepIR(
        step_id="st7",
        text="multi output",
        command_type="GENERAL_COMMAND",
        source_span_ids=["s20"],
        outputs=["out1", "out2"], # MULTIPLE OUTPUTS!
    )

    patched_snapshot = MagicMock(spec=ArtifactSnapshot)
    patched_snapshot.compile_run_id = "run_123"
    patched_snapshot.snapshot_id = "snap_124"
    patched_snapshot.overlay_version = 2
    patched_snapshot.worker_step_plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [multi_output_step]},
    )

    materialization_result = MagicMock()
    materialization_result.patched_snapshot = patched_snapshot
    materialization_result.overlay_event.overlay_id = "overlay_123"
    service._materialization.materialize.return_value = materialization_result

    # 2. Applying the suggestion must trigger the fail-closed gate ValueError
    with pytest.raises(ValueError, match="SPL Editing fail-closed gate: multiple outputs not allowed."):
        service.apply_suggestion(
            session_id="session_123",
            suggestion_id="sugg_123",
            user_text="help",
        )

    # Verify that the materializer was called, but snapshot write/overlay append was NEVER executed
    service._materialization.materialize.assert_called_once()
    service._snapshots.put.assert_not_called()
    service._overlays.append.assert_not_called()
