"""R13.3 migration guards for missing_handler stage-slice apply path."""

from __future__ import annotations

import ast
import pathlib

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import (
    AddExceptionHandlerStepIntentPayload,
    ConstructRepairIntent,
    RepairEvidencePacket,
)
from nl2spl.compiler.spl_editing.materialization.id_allocator import IdAllocator
from nl2spl.compiler.spl_editing.materialization.model import MaterializationInput
from nl2spl.compiler.spl_editing.materialization.registry import build_default_materialization_registry
from nl2spl.compiler.spl_editing.materialization.stage7.exception_handler_step import (
    ExceptionHandlerStageSliceChainMaterializer,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRefSet
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR, WorkerStepPlanIR


def _irs_ref() -> DiagnosticIRSRef:
    return DiagnosticIRSRef(
        construct_type="EXCEPTION_FLOW",
        construct_id="exc_1",
        slot_name="handler_action",
        construct_path=("worker", "w_main", "exception_flows", "exc_1"),
        source_authority="post_normalize_irs",
    )


def _snapshot() -> ArtifactSnapshot:
    return ArtifactSnapshot(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=0,
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={
                "w_main": FlowStructureIR(
                    exception_flows=[ExceptionFlow("exc_1", "missing access", [])]
                )
            }
        ),
        worker_block_plan=WorkerBlockPlanIR(worker_blocks={"w_main": BlockStructureIR()}),
        worker_step_plan=WorkerStepPlanIR(main_worker_id="w_main", worker_steps={"w_main": []}),
    )


def _make_input() -> MaterializationInput:
    snapshot = _snapshot()
    intent = ConstructRepairIntent(
        intent_id="intent_1",
        issue_id="issue_1",
        patch_type="AddExceptionHandlerStep",
        affordance_id="exception_flow.add_handler_step",
        target_construct_type="EXCEPTION_FLOW",
        target_construct_id="exc_1",
        target_slot_name="handler_action",
        target_ref_id="t_exc_1",
        selected_ref_ids=(),
        materialization_plan_id="stage7.exception_handler_step_repair.v1",
        payload=AddExceptionHandlerStepIntentPayload(
            target_exception_flow_ref_id="t_exc_1",
            handler_goal="Handle the exception",
        ),
    )
    return MaterializationInput(
        snapshot=snapshot,
        issue=EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="diag_1",
            related_diagnostic_ids=(),
            issue_group_id=None,
            kind="missing_handler",
            target_ref="t_exc_1",
            source_span_ids=(),
            message="Exception flow has no handler.",
            irs_ref=_irs_ref(),
            missing_slot="handler_action",
            repairability="editable",
            affordance_ids=("exception_flow.add_handler_step",),
            default_affordance_id="exception_flow.add_handler_step",
        ),
        target=RepairTarget(
            target_ref="t_exc_1",
            target_kind="element",
            irs_ref=_irs_ref(),
            affordance_id="exception_flow.add_handler_step",
            construct_path=("worker", "w_main", "exception_flows", "exc_1"),
            worker_id="w_main",
            canonical_name="exc_1",
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        ),
        catalog_entry=RepairCatalogEntry(
            entry_id="EXCEPTION_FLOW.handler_action.missing_handler.exception_flow.add_handler_step",
            affordance_id="exception_flow.add_handler_step",
            construct_type="EXCEPTION_FLOW",
            slot_name="handler_action",
            diagnostic_kind="missing_handler",
            supported_patch_types=("AddExceptionHandlerStep",),
            default_patch_type="AddExceptionHandlerStep",
            handler_id="missing_handler",
            context_id="exception_flow_context",
            target_resolver_id="exception_flow_target",
            selectable_ref_policy_id="exception_flow.handler.selectable_refs.v1",
            materialization_plan_id="stage7.exception_handler_step_repair.v1",
            default_verification_lane="B",
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        ),
        intent=intent,
        refset=SelectableRefSet(
            set_id="refset_1",
            issue_id="issue_1",
            snapshot_id="snap_1",
            worker_scope="w_main",
            refs=(),
            policy_id="exception_flow.handler.selectable_refs.v1",
        ),
        resolved_refs=(),
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="ev_patch_1",
            confirmed_intent_id="intent_1",
            repair_patch_id="patch_1",
            related_diagnostic_id="diag_1",
            user_text="Confirm handler",
            confirmed_selected_ref_ids=(),
        ),
        plan=build_default_materialization_registry().get("stage7.exception_handler_step_repair.v1"),
        id_allocator=IdAllocator.from_snapshot(snapshot, ("step", "block")),
    )


def test_exception_handler_materializer_returns_stage_slice_audit_results() -> None:
    result = ExceptionHandlerStageSliceChainMaterializer().materialize(_make_input())

    assert [r.slice_id for r in result.stage_slice_results] == [
        "stage5.exception_handler_block_repair.v1",
        "stage7.exception_handler_command_repair.v1",
    ]
    assert result.stage_slice_results[0].trace["block_id"]
    assert result.stage_slice_results[1].trace["block_id"] == result.stage_slice_results[0].trace["block_id"]
    assert result.changed_step_ids == (result.stage_slice_results[1].trace["step_id"],)


def test_exception_handler_materializer_no_longer_constructs_block_or_step_ir_directly() -> None:
    source = pathlib.Path(
        "src/nl2spl/compiler/spl_editing/materialization/stage7/exception_handler_step.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_names = set()
    call_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            call_names.add(node.func.id)

    assert "BlockIR" not in imported_names
    assert "StepIR" not in imported_names
    assert "BlockIR" not in call_names
    assert "StepIR" not in call_names
