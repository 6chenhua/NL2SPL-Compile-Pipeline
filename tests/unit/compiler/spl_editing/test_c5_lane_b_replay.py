"""C5: Lane B real compiler replay tests."""

import pytest

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairEvidence, RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.applier import (
    AddExceptionHandlerStepApplier,
)
from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.verifier import (
    AddExceptionHandlerStepVerifier,
)
from nl2spl.compiler.spl_editing.verification.lanes import (
    LaneBReplayAdapter,
    VerificationArtifacts,
)
from nl2spl.compiler.spl_editing.verification.runner import VerificationRunner
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import ExceptionFlowRef
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)

LANE = "B"


def _make_snapshot(**kw) -> ArtifactSnapshot:
    plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[WorkerSpecIR(
            "w_main", "MainWorker", "main", "Main worker",
            boundary_kind="main_worker",
            owned_span_ids=["s1"],
        )],
    )
    d = dict(
        snapshot_id="snap_1", compile_run_id="run_1", overlay_version=0,
        worker_plan=plan,
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        worker_flow_plan=WorkerFlowPlanIR(worker_flows={
            "w_main": FlowStructureIR(
                exception_flows=[ExceptionFlowRef(
                    flow_id="exc_1", condition_text="Error.", blocks=[],
                )],
            ),
        }),
        worker_block_plan=WorkerBlockPlanIR(worker_blocks={
            "w_main": BlockStructureIR(),
        }),
        resources=ResourceRegistryIR(),
        symbol_table=SymbolTable(),
        agent_profile=AgentProfileIR(
            persona=PersonaIR(role="Assistant", aspects=[]),
        ),
    )
    d.update(kw)
    return ArtifactSnapshot(**d)


def test_lane_b_replays_real_compiler() -> None:
    """C5: Lane B with all required artifacts produces non-empty SPL."""
    snap = _make_snapshot(
        worker_step_plan=WorkerStepPlanIR("w_main", {
            "w_main": [StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
        }),
    )
    result = LaneBReplayAdapter().replay(snap)
    assert result.rendered_spl != ""


def test_lane_b_fails_fast_on_missing_artifacts() -> None:
    """C5: Lane B raises PatchValidationError when required artifacts missing."""
    with pytest.raises(PatchValidationError, match="worker_plan"):
        LaneBReplayAdapter().replay(ArtifactSnapshot("s", "r", 0))


def test_lane_b_applied_patch_verified() -> None:
    """C5: Applied AddExceptionHandlerStep → Lane B replay → verification."""
    diag = CompileDiagnostic(
        "diag_target", "missing_handler", "warning",
        "No handler.", target_ref="worker:w_main.exception_flow:exc_1",
        blocks_completion=True,
    )
    snap = _make_snapshot(compile_diagnostics=(diag,))

    patch = RepairPatch(
        patch_id="p1", affordance_id="exception_flow.add_handler_step",
        patch_type="AddExceptionHandlerStep",
        target_ref="worker:w_main.exception_flow:exc_1",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW", construct_id="x",
            slot_name="handler_action",
        ),
        base_compile_run_id="run_1", artifact_snapshot_id="snap_1",
        overlay_version=0, verification_lane=LANE,
        payload={"worker_id": "w_main", "exception_flow_id": "exc_1",
                 "handler_text": "Handle the error",
                 "command_type": "GENERAL_COMMAND"},
        evidence=RepairEvidence(related_diagnostic_id="diag_target"),
    )
    patched, _ = AddExceptionHandlerStepApplier().apply(patch, snap)
    runner = VerificationRunner(lane_b=LaneBReplayAdapter())
    result = runner.verify(patch, snap, patched, AddExceptionHandlerStepVerifier())
    assert result.lane == LANE
    assert result.accepted is True
    assert result.failure_reasons == ()


def test_lane_b_rejects_normalizer_errors() -> None:
    """C5: Lane B fails fast when normalizer returns structural errors.
    DISPLAY_MESSAGE with outputs is a validation error in Stage 9.5."""
    snap = _make_snapshot(
        worker_step_plan=WorkerStepPlanIR("w_main", {
            "w_main": [StepIR(
                "st_bad", "Show message", [],
                "DISPLAY_MESSAGE", outputs=["forbidden_output"],
            )],
        }),
    )
    with pytest.raises(PatchValidationError, match="normalizer"):
        LaneBReplayAdapter().replay(snap)
