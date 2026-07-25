"""Unit tests for Phase R13.1 Stage5ExceptionHandlerBlockRepairSlice."""

from __future__ import annotations

import ast
import pathlib

import pytest

from nl2spl.compiler.spl_editing.core.model import RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import (
    AddExceptionHandlerStepIntentPayload,
    ConstructRepairIntent,
)
from nl2spl.compiler.spl_editing.materialization.id_allocator import IdAllocator
from nl2spl.compiler.spl_editing.materialization.model import MaterializationDependencyClosure
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRefSet
from nl2spl.compiler.spl_editing.stage_slices import (
    BlockShapePlan,
    StagePolicy,
    StageSliceInput,
    StageSliceValidationError,
    TypedPlanValidator,
)
from nl2spl.compiler.spl_editing.stage_slices.stage5 import (
    Stage5ExceptionHandlerBlockRepairSlice,
)
from nl2spl.compiler.spl_editing.strategy import RepairDirective
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR


def _snapshot(existing_block: bool = False) -> ArtifactSnapshot:
    flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "w_main": FlowStructureIR(
                exception_flows=[ExceptionFlow(flow_id="exc_1", condition_text="missing access", spans=[])]
            )
        }
    )
    exception_blocks = {}
    if existing_block:
        exception_blocks["exc_1"] = [BlockIR(block_id="b_existing_1", block_type="SEQUENTIAL")]
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "w_main": BlockStructureIR(exception_flow_blocks=exception_blocks)
        }
    )
    return ArtifactSnapshot(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=0,
        worker_flow_plan=flow_plan,
        worker_block_plan=block_plan,
    )


def _target() -> RepairTarget:
    return RepairTarget(
        target_ref="t_exc_1",
        target_kind="element",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="exc_1",
            slot_name="handler_action",
            construct_path=("worker", "w_main", "exception_flows", "exc_1"),
            source_authority="post_normalize_irs",
        ),
        affordance_id="exception_flow.add_handler_step",
        construct_path=("worker", "w_main", "exception_flows", "exc_1"),
        worker_id="w_main",
        canonical_name="exc_1",
        editable_artifacts=("WorkerBlockPlanIR",),
    )


def _input(snapshot: ArtifactSnapshot, directive: RepairDirective | None = None, typed_plan=None) -> StageSliceInput:
    payload = AddExceptionHandlerStepIntentPayload(
        target_exception_flow_ref_id="t_exc_1",
        handler_goal="Handle the exception",
    )
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
        intent_summary="Complete exception handler action",
        repair_goal="Ensure handler block",
        materialization_plan_id="stage7.exception_handler_step_repair.v1",
        payload=payload,
    )
    return StageSliceInput(
        slice_id="stage5.exception_handler_block_repair.v1",
        stage_authority="stage5.worker_block_plan",
        snapshot=snapshot,
        target=_target(),
        refset=SelectableRefSet(
            set_id="refset_1",
            issue_id="issue_1",
            snapshot_id="snap_1",
            worker_scope="w_main",
            refs=(),
            policy_id="exception_flow.handler.selectable_refs.v1",
        ),
        directive=directive
        or RepairDirective(
            directive_id="dir_1",
            source="system_default",
            target_construct_type="EXCEPTION_FLOW",
            target_slot_name="handler_action",
        ),
        intent=intent,
        dependency_closure=MaterializationDependencyClosure(
            required_artifacts=("worker_flow_plan", "worker_block_plan"),
            required_id_allocator_namespaces=("block",),
        ),
        stage_policy=StagePolicy(
            policy_id="exception_handler.minimal_block.v1",
            stage_authority="stage5.worker_block_plan",
            allowed_typed_plan_kinds=("BlockShapePlan",),
            generation_mode="stored_typed_plan" if typed_plan else "none",
        ),
        selected_ref_ids=(),
        id_allocator=IdAllocator.from_snapshot(snapshot, ("block",)),
        typed_plan=typed_plan,
        dry_run=True,
    )


def test_existing_handler_block_is_bound_without_duplicate() -> None:
    result = Stage5ExceptionHandlerBlockRepairSlice().execute(_input(_snapshot(existing_block=True)))

    assert result.trace["action"] == "bind_existing"
    assert result.generated_construct_refs == ("block:w_main:b_existing_1",)
    assert result.allocated_ids == ()
    assert result.changed_artifact_refs == ()
    assert result.artifact_updates == {}


def test_missing_handler_block_materializes_exactly_one_block() -> None:
    result = Stage5ExceptionHandlerBlockRepairSlice().execute(_input(_snapshot()))

    assert result.trace["action"] == "materialize"
    assert result.allocated_ids == ("b_repair_1",)
    block_plan = result.artifact_updates["worker_block_plan"]
    blocks = block_plan.worker_blocks["w_main"].exception_flow_blocks["exc_1"]
    assert [block.block_id for block in blocks] == ["b_repair_1"]
    assert [block.block_type for block in blocks] == ["SEQUENTIAL"]


def test_allocated_block_id_is_stable_after_existing_ids() -> None:
    snapshot = _snapshot(existing_block=True)
    result = Stage5ExceptionHandlerBlockRepairSlice().execute(_input(snapshot))

    assert result.trace["block_id"] == "b_existing_1"

    missing_snapshot = _snapshot(existing_block=False)
    missing_snapshot.worker_block_plan.worker_blocks["w_main"].main_flow_blocks.append(
        BlockIR(block_id="b_repair_4", block_type="SEQUENTIAL")
    )
    result_2 = Stage5ExceptionHandlerBlockRepairSlice().execute(_input(missing_snapshot))
    assert result_2.allocated_ids == ("b_repair_5",)


def test_directive_driven_block_shape_plan_can_choose_allowed_block_shape() -> None:
    result = Stage5ExceptionHandlerBlockRepairSlice().execute(
        _input(
            _snapshot(),
            directive=RepairDirective(
                directive_id="dir_2",
                source="user",
                target_construct_type="EXCEPTION_FLOW",
                target_slot_name="handler_action",
                requested_behavior="Use a conditional handler block",
            ),
            typed_plan=BlockShapePlan(
                block_type="IF",
                rationale="directive asks for condition",
                child_action_slots=("handler_action",),
            ),
        )
    )

    blocks = result.artifact_updates["worker_block_plan"].worker_blocks[
        "w_main"
    ].exception_flow_blocks["exc_1"]
    assert blocks[0].block_type == "IF"


def test_stage5_slice_rejects_diagnostic_metadata_sourced_facts() -> None:
    directive = RepairDirective(
        directive_id="dir_bad",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        constraints=("condition_source=diagnostic.message",),
    )

    with pytest.raises(StageSliceValidationError, match="structured target facts"):
        Stage5ExceptionHandlerBlockRepairSlice().execute(_input(_snapshot(), directive=directive))


def test_block_shape_plan_validator_rejects_block_ir_payload() -> None:
    with pytest.raises(StageSliceValidationError):
        TypedPlanValidator().validate({"BlockIR": {"block_id": "b1"}})


def test_stage5_slice_source_does_not_construct_step_ir() -> None:
    source = pathlib.Path(
        "src/nl2spl/compiler/spl_editing/stage_slices/stage5/exception_handler_block.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id != "StepIR"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "StepIR"
