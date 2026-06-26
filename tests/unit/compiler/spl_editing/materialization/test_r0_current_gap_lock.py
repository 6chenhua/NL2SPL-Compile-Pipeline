"""R0: Contract Freeze / Current Gap Lock tests for SPL Editing repair materialization.

These tests capture and lock the current direct IR mutation risks and future target contracts.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.errors import PatchValidationError, SPLEditingError
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairEvidence,
    RepairPatch,
    RepairTarget,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.handlers.missing_output_producer.handler import (
    MissingOutputProducerHandler,
)
from nl2spl.compiler.spl_editing.patches.insert_producer_step.applier import (
    InsertProducerStepApplier,
)
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR
from tests.spl_editing_stub_llm import StubSuggestionLLM


def _snap(**kw: object) -> ArtifactSnapshot:
    d: dict[str, object] = dict(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=0,
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
    )
    d.update(kw)
    return ArtifactSnapshot(**d)  # type: ignore[arg-type]


def _patch(patch_type: str, **kw: object) -> RepairPatch:
    d: dict[str, object] = dict(
        patch_id="p1",
        affordance_id="required_output.insert_or_bind_producer",
        patch_type=patch_type,
        target_ref="worker:w_main.output:draft",
        irs_ref=DiagnosticIRSRef(
            construct_type="REQUIRED_OUTPUT",
            construct_id="x",
            slot_name="producer",
        ),
        base_compile_run_id="run_1",
        artifact_snapshot_id="snap_1",
        overlay_version=0,
        verification_lane="A",
        payload={
            "worker_id": "w_main",
            "output_name": "draft",
            "producer_text": "Draft the document.",
            "command_type": "GENERAL_COMMAND",
            "inputs": [],
            "outputs": [],
        },
        evidence=RepairEvidence(
            related_diagnostic_id="diag_target",
            user_text="Add producer.",
        ),
    )
    d.update(kw)
    return RepairPatch(**d)  # type: ignore[arg-type]


def _issue(**kw: object) -> EditableIssue:
    d: dict[str, object] = dict(
        issue_id="i1",
        primary_diagnostic_id="d1",
        related_diagnostic_ids=("d1",),
        issue_group_id=None,
        kind="missing_output_producer",
        target_ref="worker:w_main.output:draft",
        irs_ref=DiagnosticIRSRef(
            construct_type="REQUIRED_OUTPUT",
            construct_id="x",
            slot_name="producer",
        ),
        missing_slot="producer",
        source_span_ids=(),
        message="Producer unavailable.",
    )
    d.update(kw)
    return EditableIssue(**d)  # type: ignore[arg-type]


def test_insert_producer_currently_accepts_payload_inputs_as_gap() -> None:
    """R6: GAP CLOSED — InsertProducerStepApplier is disabled.

    Dict payloads are rejected; InsertProducerStep must go through
    the materialization path.  Direct StepIR mutation is no longer
    possible through the applier.
    """
    snap = _snap(worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}))
    patch = _patch(
        "InsertProducerStep",
        payload={
            "worker_id": "w_main",
            "output_name": "draft",
            "producer_text": "Produce it",
            "command_type": "GENERAL_COMMAND",
            "inputs": ["project_data"],
            "outputs": ["draft"],
        },
    )

    # R6: Applier is disabled — always raises
    with pytest.raises(SPLEditingError, match="disabled"):
        InsertProducerStepApplier().apply(patch, snap)


def test_missing_output_handler_currently_builds_ir_like_payload_as_gap() -> None:
    """R6: GAP CLOSED — InsertProducerStep without selectable_refset cannot
    produce suggestions.  The handler requires a SelectableRefSet for the
    intent path; without it, Insert is skipped (no dict fallback)."""
    fixed_response = {
        "patch_type": "InsertProducerStep",
        "title": "Add producer step",
        "explanation": "Create a step",
        "payload": {
            "producer_text": "Produce it",
            "command_type": "GENERAL_COMMAND",
            "inputs": ["project_data"],
            "outputs": ["draft"],
        },
    }
    llm = StubSuggestionLLM(fixed_response)
    handler = MissingOutputProducerHandler(llm)

    issue = _issue()
    target = RepairTarget(
        target_ref="worker:w_main.output:draft",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=issue.irs_ref,
        affordance_id="required_output.insert_or_bind_producer",
        construct_path=(),
        worker_id="w_main",
    )
    context = RepairContext(issue=issue, target=target, related_steps=())
    catalog_entry = RepairCatalogEntry(
        entry_id="REQUIRED_OUTPUT.producer.missing_output_producer.required_output.insert_or_bind_producer",
        affordance_id="required_output.insert_or_bind_producer",
        construct_type="REQUIRED_OUTPUT",
        slot_name="producer",
        diagnostic_kind="missing_output_producer",
        handler_id="missing_output_producer",
        context_id="required_output_context",
        target_resolver_id="required_output_target",
        supported_patch_types=("InsertProducerStep", "BindExistingProducerStep"),
        default_patch_type="InsertProducerStep",
        default_verification_lane="A",
    )

    # R6: Without selectable_refset, Insert is skipped.
    # The handler raises because no valid suggestions were produced.
    with pytest.raises(PatchValidationError, match="did not produce a valid"):
        handler.generate_suggestions(
            issue=issue,
            target=target,
            context=context,
            catalog_entries=(catalog_entry,),
            selected_patch_types=("InsertProducerStep",),
        )


def test_project_data_must_be_rejected_target_contract() -> None:
    """R6: CONTRACT FULFILLED — Dict payload with hallucinated variable
    'project_data' is rejected by the disabled applier.

    The contract_pending marker is removed — this is now a passing guardrail.
    """
    snap = _snap(worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}))
    patch = _patch(
        "InsertProducerStep",
        payload={
            "worker_id": "w_main",
            "output_name": "draft",
            "producer_text": "Produce it",
            "command_type": "GENERAL_COMMAND",
            "inputs": ["project_data"],
            "outputs": ["draft"],
        },
    )

    # R6: Applier is disabled — hallucinated variables can't enter StepIR
    with pytest.raises(SPLEditingError, match="disabled"):
        InsertProducerStepApplier().apply(patch, snap)


def test_add_exception_handler_direct_step_construction_gap_closed() -> None:
    """R11: AddExceptionHandlerStepApplier no longer directly creates BlockIR/StepIR."""
    from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.applier import (
        AddExceptionHandlerStepApplier,
    )
    from nl2spl.ir.block_structure_ir import BlockStructureIR
    from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR

    snap = _snap(
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        worker_block_plan=WorkerBlockPlanIR(worker_blocks={"w_main": BlockStructureIR()}),
    )
    patch = _patch(
        "AddExceptionHandlerStep",
        payload={
            "worker_id": "w_main",
            "exception_flow_id": "exc_1",
            "handler_text": "Handle exception",
            "command_type": "GENERAL_COMMAND",
            "inputs": [],
            "outputs": [],
        },
    )

    with pytest.raises(SPLEditingError, match="RepairMaterializationService"):
        AddExceptionHandlerStepApplier().apply(patch, snap)
    assert snap.worker_step_plan.worker_steps["w_main"] == []


def test_create_worker_handoff_direct_ir_construction_gap_closed() -> None:
    """R11: CreateWorkerHandoffContractApplier no longer directly constructs handoff IR."""
    from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.applier import (
        CreateWorkerHandoffContractApplier,
    )
    from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR

    worker_spec = WorkerSpecIR(
        worker_id="w_main", worker_name="w_main", kind="main", purpose="test"
    )
    child_spec = WorkerSpecIR(
        worker_id="w_child", worker_name="w_child", kind="child", purpose="test"
    )

    snap = _snap(
        worker_plan=WorkerPlanIR(
            main_worker_id="w_main", workers=[worker_spec, child_spec], handoffs=[]
        ),
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": [], "w_child": []}),
    )
    patch = _patch(
        "CreateWorkerHandoffContract",
        payload={
            "parent_worker_id": "w_main",
            "child_worker_id": "w_child",
            "worker_promotion_id": "promo_1",
            "input_bindings": {"request_data": "request_data"},
            "output_bindings": {"response_data": "response_data"},
            "invocation_point": "main",
        },
    )

    with pytest.raises(SPLEditingError, match="RepairMaterializationService"):
        CreateWorkerHandoffContractApplier().apply(patch, snap)
    assert snap.worker_plan.handoffs == []
