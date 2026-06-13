"""B4.5/C5: Lane B harness proof tests."""

import pytest

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.verification.lanes import (
    LaneBReplayAdapter,
    VerificationArtifacts,
)
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
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


def _snap(**kw):
    plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[WorkerSpecIR(
            "w_main", "MainWorker", "main", "Main",
            boundary_kind="main_worker",
            owned_span_ids=["s1"],
        )],
    )
    d = dict(
        snapshot_id="snap_1", compile_run_id="run_1", overlay_version=0,
        worker_plan=plan,
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": [
            StepIR("st1", "Work", ["s1"], "GENERAL_COMMAND"),
        ]}),
        worker_flow_plan=WorkerFlowPlanIR(worker_flows={
            "w_main": FlowStructureIR(),
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


def test_lane_b_with_all_artifacts_produces_spl() -> None:
    result = LaneBReplayAdapter().replay(_snap())
    assert isinstance(result, VerificationArtifacts)
    assert result.rendered_spl != ""


def test_lane_b_fails_fast_on_missing_artifacts() -> None:
    with pytest.raises(PatchValidationError):
        LaneBReplayAdapter().replay(ArtifactSnapshot("s", "r", 0))


def test_lane_b_does_not_mutate_snapshot() -> None:
    snap = _snap()
    ov = snap.overlay_version
    LaneBReplayAdapter().replay(snap)
    assert snap.overlay_version == ov


def test_lane_b_unchanged_snapshot_is_deterministic() -> None:
    adapter = LaneBReplayAdapter()
    snap = _snap()
    assert adapter.replay(snap).rendered_spl == adapter.replay(snap).rendered_spl
