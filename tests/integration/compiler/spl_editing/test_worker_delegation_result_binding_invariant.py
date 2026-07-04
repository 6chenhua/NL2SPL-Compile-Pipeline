from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from types import SimpleNamespace

from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.compiler.spl_editing.core.model import RepairEvidence, RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.define_child_worker_closure.verifier import (
    DefineChildWorkerClosureVerifier,
)
from nl2spl.compiler.spl_editing.resolution import PromotionResolutionMarker
from nl2spl.compiler.spl_editing.verification.lanes import VerificationArtifacts
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    InputBindingIR,
    OutputBindingIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)

TARGET_REF = "worker_promotion:del_s31"
PATCH_ID = "patch_define_child_1"


@dataclass(frozen=True)
class _Ref:
    ref_id: str
    canonical_name: str
    ref_kind: str = "variable"


@dataclass(frozen=True)
class _SelectedInput:
    ref: _Ref


@dataclass(frozen=True)
class _Output:
    output_id: str
    canonical_name: str


@dataclass(frozen=True)
class _ResultUsage:
    output_id: str
    parent_ref: object | None = None
    parent_temporary_name: str | None = None


def _patch() -> RepairPatch:
    return RepairPatch(
        patch_id=PATCH_ID,
        affordance_id="worker_promotion.resolve_contract",
        patch_type="DefineChildWorkerClosure",
        target_ref=TARGET_REF,
        irs_ref=DiagnosticIRSRef(
            "WORKER_PROMOTION",
            TARGET_REF,
            "promotion_input_contract",
        ),
        base_compile_run_id="run_1",
        artifact_snapshot_id="snap_1",
        overlay_version=0,
        payload=SimpleNamespace(payload=_directive()),
        evidence=RepairEvidence(
            user_text="confirmed",
            related_diagnostic_id="diag_worker_promotion",
        ),
        verification_lane="B",
    )


def _directive():
    return SimpleNamespace(
        directive_id="directive_1",
        delegated_responsibility="Gather approved source evidence",
        selected_input_refs=(
            _SelectedInput(_Ref("variable:worker_main:user_request", "user_request")),
        ),
        admitted_outputs=(_Output("evidence", "delegated_evidence"),),
        result_usage=(
            _ResultUsage("evidence", parent_temporary_name="source_evidence_set"),
        ),
    )


def _snapshot() -> ArtifactSnapshot:
    input_field = ContractFieldIR(
        "user_request",
        "text",
        True,
        "User request",
        "input",
    )
    output_field = ContractFieldIR(
        "delegated_evidence",
        "text",
        True,
        "Delegated evidence",
        "derived",
    )
    main = WorkerSpecIR(
        "worker_main",
        "MainWorker",
        "main",
        "Main workflow",
        input_contract=[input_field],
    )
    child = WorkerSpecIR(
        "worker_child",
        "Worker_child",
        "child",
        "Gather approved source evidence",
        input_contract=[input_field],
        output_contract=[output_field],
    )
    handoff = WorkerHandoffIR(
        "handoff_1",
        "worker_main",
        "worker_child",
        None,
        "invoke",
        None,
        "after",
        input_bindings=[InputBindingIR("user_request", "user_request", True)],
        output_bindings=[
            OutputBindingIR("delegated_evidence", "source_evidence_set", True, "set")
        ],
        materialization_status="materialized",
    )
    child_step = StepIR(
        "st_child",
        "Gather approved source evidence",
        ["s31"],
        "GENERAL_COMMAND",
        inputs=["user_request"],
        outputs=["delegated_evidence"],
        block_ref="b_child",
    )
    invoke = StepIR(
        "st_invoke",
        "Invoke Worker_child",
        [],
        "INVOKE_WORKER",
        inputs=["user_request"],
        outputs=["source_evidence_set"],
        integration_ref="Worker_child",
        block_ref="b_main",
        kind="invoke",
        handoff_id="handoff_1",
    )
    symbols = SymbolTable()
    symbols.declare_scoped(
        "user_request",
        "text",
        "input",
        "User request",
        scope_kind="worker",
        scope_id="worker_main",
    )
    symbols.declare_scoped(
        "source_evidence_set",
        "text",
        "user_confirmed_repair",
        "Parent-local temporary handoff result",
        scope_kind="worker",
        scope_id="worker_main",
        block_ref="b_main",
    )
    symbols._variables[("worker", "worker_main", "source_evidence_set")].declared = False
    symbols._variables[
        ("worker", "worker_main", "source_evidence_set")
    ].producer_step = "st_invoke"
    return ArtifactSnapshot(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=1,
        worker_plan=WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[main, child],
            handoffs=[handoff],
        ),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_child": FlowStructureIR(main_flow_spans=["s31"])}
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "worker_child": BlockStructureIR(
                    main_flow_blocks=[BlockIR("b_child", "SEQUENTIAL", spans=["s31"])]
                )
            }
        ),
        worker_step_plan=WorkerStepPlanIR(
            "worker_main",
            {
                "worker_main": [invoke],
                "worker_child": [child_step],
            },
        ),
        symbol_table=symbols,
        promotion_resolution_markers=(
            PromotionResolutionMarker(
                marker_id="promotion_resolution:directive_1",
                target_worker_promotion_id=TARGET_REF,
                resolved_diagnostic_group_id="worker_promotion_group:del_s31",
                resolution_kind="defined_child_worker",
                normalized_directive_id="directive_1",
                materialized_construct_refs=(
                    "worker:worker_child",
                    "flow:worker_child:main",
                    "block:worker_child:b_child",
                    "step:worker_child:st_child",
                    "handoff:handoff_1",
                    "step:worker_main:st_invoke",
                ),
                evidence_ref="evidence_packet_1",
                repair_patch_id=PATCH_ID,
                user_confirmed=True,
            ),
        ),
    )


def _artifacts() -> VerificationArtifacts:
    return VerificationArtifacts(rendered_spl="Gather approved source evidence")


def test_define_child_closure_accepts_complete_result_binding_chain() -> None:
    snapshot = _snapshot()

    failures = DefineChildWorkerClosureVerifier().verify(
        _patch(),
        replace(snapshot, overlay_version=0, promotion_resolution_markers=()),
        snapshot,
        _artifacts(),
    )

    assert failures == ()


def test_define_child_closure_rejects_invoke_result_binding_drift() -> None:
    snapshot = copy.deepcopy(_snapshot())
    snapshot.worker_step_plan.worker_steps["worker_main"][0].outputs = ["other_result"]

    failures = DefineChildWorkerClosureVerifier().verify(
        _patch(),
        replace(snapshot, overlay_version=0, promotion_resolution_markers=()),
        snapshot,
        _artifacts(),
    )

    assert "Parent invocation does not match the handoff plan" in failures
    index = ProducerIndex(
        steps=snapshot.worker_step_plan.get_all_steps(),
        handoffs=snapshot.worker_plan.handoffs,
        known_child_worker_ids={"worker_child"},
    )
    assert index.is_produced("source_evidence_set") is True


def test_define_child_closure_rejects_parent_symbol_producer_drift() -> None:
    snapshot = copy.deepcopy(_snapshot())
    snapshot.symbol_table._variables[
        ("worker", "worker_main", "source_evidence_set")
    ].producer_step = "st_other"

    failures = DefineChildWorkerClosureVerifier().verify(
        _patch(),
        replace(snapshot, overlay_version=0, promotion_resolution_markers=()),
        snapshot,
        _artifacts(),
    )

    assert "Parent temporary result producer does not match invoke step" in failures


def test_define_child_closure_rejects_non_renderable_handoff_producer() -> None:
    snapshot = copy.deepcopy(_snapshot())
    snapshot.worker_plan.handoffs[0].output_bindings = []

    failures = DefineChildWorkerClosureVerifier().verify(
        _patch(),
        replace(snapshot, overlay_version=0, promotion_resolution_markers=()),
        snapshot,
        _artifacts(),
    )

    assert "Handoff output bindings do not match result usage" in failures
    assert (
        "Parent result binding is not backed by a renderable handoff producer"
        in failures
    )


def test_define_child_closure_rejects_required_output_as_parent_binding() -> None:
    directive = _directive()
    required_ref = SimpleNamespace(
        ref=_Ref(
            "required_output:worker_main:required_outputs::final_report",
            "final_report",
            ref_kind="required_output",
        )
    )
    invalid = SimpleNamespace(
        **{
            **directive.__dict__,
            "result_usage": (
                _ResultUsage("evidence", parent_ref=required_ref),
            ),
        }
    )
    patch = replace(_patch(), payload=SimpleNamespace(payload=invalid))

    failures = DefineChildWorkerClosureVerifier().verify(
        patch,
        replace(_snapshot(), overlay_version=0, promotion_resolution_markers=()),
        _snapshot(),
        _artifacts(),
    )

    assert "Parent required output is not a valid result binding target" in failures
