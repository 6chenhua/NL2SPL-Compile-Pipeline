"""Unit tests for Phase R13.2 Stage7ExceptionHandlerCommandRepairSlice."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.model import RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import (
    AddExceptionHandlerStepIntentPayload,
    ConstructRepairIntent,
    RepairEvidencePacket,
)
from nl2spl.compiler.spl_editing.materialization.id_allocator import IdAllocator
from nl2spl.compiler.spl_editing.materialization.model import MaterializationDependencyClosure
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef, SelectableRefSet
from nl2spl.compiler.spl_editing.stage_slices import (
    CommandIntentPlan,
    StagePolicy,
    StageSliceInput,
    StageSliceResult,
    StageSliceValidationError,
)
from nl2spl.compiler.spl_editing.stage_slices.stage7 import (
    Stage7ExceptionHandlerCommandRepairSlice,
)
from nl2spl.compiler.spl_editing.strategy import RepairDirective
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR


def _snapshot() -> ArtifactSnapshot:
    return ArtifactSnapshot(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=0,
        worker_step_plan=WorkerStepPlanIR(main_worker_id="w_main", worker_steps={"w_main": []}),
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
        editable_artifacts=("WorkerStepPlanIR",),
    )


def _refset() -> SelectableRefSet:
    return SelectableRefSet(
        set_id="refset_1",
        issue_id="issue_1",
        snapshot_id="snap_1",
        worker_scope="w_main",
        refs=(
            SelectableRef(
                ref_id="ref_input_1",
                ref_kind="variable",
                ref_role="selectable_input",
                canonical_name="source_access",
                display_label="source_access",
                worker_id="w_main",
            ),
        ),
        policy_id="exception_flow.handler.selectable_refs.v1",
    )


def _intent(selected_ref_ids: tuple[str, ...] = ()) -> ConstructRepairIntent:
    return ConstructRepairIntent(
        intent_id="intent_1",
        issue_id="issue_1",
        patch_type="AddExceptionHandlerStep",
        affordance_id="exception_flow.add_handler_step",
        target_construct_type="EXCEPTION_FLOW",
        target_construct_id="exc_1",
        target_slot_name="handler_action",
        target_ref_id="t_exc_1",
        selected_ref_ids=selected_ref_ids,
        intent_summary="Complete exception handler action",
        repair_goal="Materialize handler command",
        materialization_plan_id="stage7.exception_handler_step_repair.v1",
        payload=AddExceptionHandlerStepIntentPayload(
            target_exception_flow_ref_id="t_exc_1",
            selected_input_ref_ids=selected_ref_ids,
            handler_goal="Handle the exception",
        ),
    )


def _evidence(selected_ref_ids: tuple[str, ...] = ()) -> RepairEvidencePacket:
    return RepairEvidencePacket(
        evidence_packet_id="ev_1",
        confirmed_intent_id="intent_1",
        repair_patch_id="patch_1",
        related_diagnostic_id="diag_1",
        user_text="confirm",
        confirmed_selected_ref_ids=selected_ref_ids,
        confirmed_at="2026-06-26T00:00:00Z",
    )


def _stage5_result() -> StageSliceResult:
    return StageSliceResult(
        slice_id="stage5.exception_handler_block_repair.v1",
        stage_authority="stage5.worker_block_plan",
        policy_id="exception_handler.minimal_block.v1",
        changed_artifact_refs=("worker_block_plan",),
        generated_construct_refs=("block:w_main:b_repair_1",),
        consumed_selected_ref_ids=(),
        consumed_directive_id="dir_1",
        allocated_ids=("b_repair_1",),
        trace={"block_id": "b_repair_1", "action": "materialize"},
    )


def _input(
    *,
    directive: RepairDirective | None = None,
    typed_plan=None,
    selected_ref_ids: tuple[str, ...] = (),
    evidence: bool = True,
) -> StageSliceInput:
    snapshot = _snapshot()
    return StageSliceInput(
        slice_id="stage7.exception_handler_command_repair.v1",
        stage_authority="stage7.worker_step_plan",
        snapshot=snapshot,
        target=_target(),
        refset=_refset(),
        directive=directive
        or RepairDirective(
            directive_id="dir_1",
            source="system_default",
            target_construct_type="EXCEPTION_FLOW",
            target_slot_name="handler_action",
        ),
        intent=_intent(selected_ref_ids),
        dependency_closure=MaterializationDependencyClosure(
            required_artifacts=("worker_step_plan",),
            required_id_allocator_namespaces=("step",),
        ),
        stage_policy=StagePolicy(
            policy_id="exception_handler.command_intent.v1",
            stage_authority="stage7.worker_step_plan",
            allowed_typed_plan_kinds=("CommandIntentPlan",),
            generation_mode="stored_typed_plan" if typed_plan else "none",
        ),
        selected_ref_ids=selected_ref_ids,
        evidence_packet=_evidence(selected_ref_ids) if evidence else None,
        id_allocator=IdAllocator.from_snapshot(snapshot, ("step",)),
        typed_plan=typed_plan,
        upstream_stage_results=(_stage5_result(),),
        dry_run=not evidence,
    )


def test_minimal_default_creates_general_command_in_stage5_block() -> None:
    result = Stage7ExceptionHandlerCommandRepairSlice().execute(
        _input(selected_ref_ids=("ref_input_1",))
    )

    step_plan = result.artifact_updates["worker_step_plan"]
    step = step_plan.worker_steps["w_main"][0]
    assert step.command_type == "GENERAL_COMMAND"
    assert step.block_ref == "b_repair_1"
    assert step.flow_ref == "exc_1"
    assert step.inputs == ["source_access"]
    assert step.metadata["origin"] == "user_confirmed_repair"
    assert step.metadata["materialization_authority"] == "stage7.worker_step_plan"
    assert step.metadata["evidence_packet_id"] == "ev_1"
    assert result.consumed_selected_ref_ids == ("ref_input_1",)


def test_request_input_directive_requires_validated_typed_plan() -> None:
    directive = RepairDirective(
        directive_id="dir_request",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        requested_behavior="ask user to request input",
    )

    with pytest.raises(StageSliceValidationError, match="requires a validated CommandIntentPlan"):
        Stage7ExceptionHandlerCommandRepairSlice().execute(_input(directive=directive))


def test_request_input_typed_plan_materializes_request_input_step() -> None:
    directive = RepairDirective(
        directive_id="dir_request",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        requested_behavior="ask user to request input",
    )
    typed_plan = CommandIntentPlan(
        command_family="REQUEST_INPUT",
        user_facing_text="Ask the user for source access",
        selected_ref_ids=(),
        output_intent="source_access_answer",
    )

    result = Stage7ExceptionHandlerCommandRepairSlice().execute(
        _input(directive=directive, typed_plan=typed_plan, selected_ref_ids=())
    )

    step = result.artifact_updates["worker_step_plan"].worker_steps["w_main"][0]
    assert step.command_type == "REQUEST_INPUT"
    assert step.inputs == []
    assert step.outputs == ["source_access_answer"]


def test_unknown_selected_ref_id_is_rejected() -> None:
    with pytest.raises(StageSliceValidationError, match="Unknown selected ref id"):
        Stage7ExceptionHandlerCommandRepairSlice().execute(
            _input(
                typed_plan=CommandIntentPlan(
                    command_family="GENERAL_COMMAND",
                    user_facing_text="Use selected input",
                    selected_ref_ids=("missing_ref",),
                )
            )
        )


def test_raw_llm_inputs_payload_is_rejected() -> None:
    with pytest.raises(StageSliceValidationError):
        Stage7ExceptionHandlerCommandRepairSlice().execute(
            _input(typed_plan={"command_family": "GENERAL_COMMAND", "inputs": ["x"]})
        )


def test_missing_stage5_block_result_is_rejected() -> None:
    data = _input()
    data = StageSliceInput(
        slice_id=data.slice_id,
        stage_authority=data.stage_authority,
        snapshot=data.snapshot,
        target=data.target,
        refset=data.refset,
        directive=data.directive,
        intent=data.intent,
        dependency_closure=data.dependency_closure,
        stage_policy=data.stage_policy,
        selected_ref_ids=data.selected_ref_ids,
        evidence_packet=data.evidence_packet,
        id_allocator=data.id_allocator,
        typed_plan=data.typed_plan,
        upstream_stage_results=(),
        dry_run=data.dry_run,
    )

    with pytest.raises(StageSliceValidationError, match="requires Stage5 handler block result"):
        Stage7ExceptionHandlerCommandRepairSlice().execute(data)