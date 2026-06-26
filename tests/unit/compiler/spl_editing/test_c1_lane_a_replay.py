"""C1: Lane A real compiler replay — integration tests."""

import pytest

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairEvidence, RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.verification.lanes import (
    LaneAReplayAdapter,
    VerificationArtifacts,
)
from nl2spl.compiler.spl_editing.verification.runner import VerificationRunner
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
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


def _make_snapshot(**kw) -> ArtifactSnapshot:
    plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[
            WorkerSpecIR(
                "w_main",
                "MainWorker",
                "main",
                "Main worker",
                boundary_kind="main_worker",
            )
        ],
    )
    d = dict(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=0,
        worker_plan=plan,
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={
                "w_main": FlowStructureIR(
                    exception_flows=[
                        ExceptionFlowRef(
                            flow_id="exc_1", condition_text="Error occurred.", blocks=[]
                        )
                    ],
                ),
            }
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "w_main": BlockStructureIR(),
            }
        ),
        resources=ResourceRegistryIR(),
        symbol_table=SymbolTable(),
        agent_profile=AgentProfileIR(
            persona=PersonaIR(role="Assistant", aspects=[]),
        ),
    )
    d.update(kw)
    return ArtifactSnapshot(**d)


def test_lane_a_replays_real_compiler() -> None:
    """C1: Lane A produces non-empty rendered SPL through real compiler."""
    adapter = LaneAReplayAdapter()
    snap = _make_snapshot(
        worker_step_plan=WorkerStepPlanIR(
            "w_main",
            {
                "w_main": [StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
            },
        ),
    )
    result = adapter.replay(snap)
    assert isinstance(result, VerificationArtifacts)
    assert result.rendered_spl != ""


def test_lane_a_fails_fast_on_missing_artifacts() -> None:
    """C1: Lane A raises PatchValidationError when required artifacts missing."""
    adapter = LaneAReplayAdapter()
    snap = ArtifactSnapshot("snap_1", "run_1", 0)
    with pytest.raises(PatchValidationError, match="worker_step_plan"):
        adapter.replay(snap)


def test_applied_patch_verified_with_real_lane_a() -> None:
    """C1: Applied AddExceptionHandlerStep → real Lane A replay →
    VerificationRunner sees gated_worker and verifier can inspect it."""
    diag = CompileDiagnostic(
        "diag_target",
        "missing_handler",
        "warning",
        "No handler.",
        target_ref="worker:w_main.exception_flow:exc_1",
        blocks_completion=True,
    )
    snap = _make_snapshot(compile_diagnostics=(diag,))
    patch = RepairPatch(
        patch_id="p1",
        affordance_id="exception_flow.add_handler_step",
        patch_type="AddExceptionHandlerStep",
        target_ref="worker:w_main.exception_flow:exc_1",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="x",
            slot_name="handler_action",
        ),
        base_compile_run_id="run_1",
        artifact_snapshot_id="snap_1",
        overlay_version=0,
        verification_lane="A",
        payload={
            "worker_id": "w_main",
            "exception_flow_id": "exc_1",
            "handler_text": "Handle the error",
            "command_type": "GENERAL_COMMAND",
        },
        evidence=RepairEvidence(related_diagnostic_id="diag_target"),
    )

    patched = _make_snapshot(
        compile_diagnostics=(diag,),
        worker_step_plan=WorkerStepPlanIR(
            "w_main",
            {
                "w_main": [
                    StepIR(
                        "st_repair_exc_1",
                        "Handle the error",
                        [],
                        "GENERAL_COMMAND",
                        flow_ref="exc_1",
                        block_ref="b_repair_exc_1",
                        metadata={
                            "origin": "user_confirmed_repair",
                            "repair_patch_id": "p1",
                            "related_diagnostic_id": "diag_target",
                        },
                    )
                ],
            },
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "w_main": BlockStructureIR(
                    exception_flow_blocks={"exc_1": [BlockIR("b_repair_exc_1", "SEQUENTIAL")]},
                ),
            }
        ),
    )

    # Verify with real Lane A + patch-specific verifier
    from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.verifier import (
        AddExceptionHandlerStepVerifier,
    )

    runner = VerificationRunner(lane_a=LaneAReplayAdapter())
    result = runner.verify(patch, snap, patched, AddExceptionHandlerStepVerifier())
    assert result.lane == "A"
    assert result.accepted is True
    assert result.failure_reasons == ()
    assert "diag_target" in result.resolved_diagnostic_ids
