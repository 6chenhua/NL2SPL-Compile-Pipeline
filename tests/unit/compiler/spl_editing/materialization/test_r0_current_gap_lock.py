"""R0: Contract Freeze / Current Gap Lock tests for SPL Editing repair materialization.

These tests capture and lock the current direct IR mutation risks and future target contracts.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairEvidence,
    RepairPatch,
    RepairTarget,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.handlers.missing_output_producer.handler import (
    MissingOutputProducerHandler,
)
from nl2spl.compiler.spl_editing.patches.insert_producer_step.applier import (
    InsertProducerStepApplier,
)
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.step_ir import StepIR
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
    """Gap: InsertProducerStepApplier currently accepts payload inputs and writes them directly to StepIR."""
    # Arrange
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

    # Act
    patched_snap, event = InsertProducerStepApplier().apply(patch, snap)

    # Assert
    wsp = patched_snap.worker_step_plan
    assert wsp is not None
    steps = wsp.worker_steps["w_main"]
    assert len(steps) == 1
    assert steps[0].inputs == ["project_data"]


def test_missing_output_handler_currently_builds_ir_like_payload_as_gap() -> None:
    """Gap: MissingOutputProducerHandler currently builds an IR-like payload carrying inputs/outputs."""
    # Arrange
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

    # Act
    suggestions = handler.generate_suggestions(
        issue=issue,
        target=target,
        context=context,
        catalog_entries=(catalog_entry,),
    )

    # Assert
    assert len(suggestions) == 1
    patch = suggestions[0].patch
    assert "inputs" in patch.payload
    assert "outputs" in patch.payload
    assert patch.payload["inputs"] == ("project_data",)
    assert patch.payload["outputs"] == ("draft",)


@pytest.mark.contract_pending
def test_project_data_must_be_rejected_target_contract() -> None:
    """Target Contract: Applying a patch with a hallucinated variable 'project_data' must be rejected."""
    # Future design: LLM suggestions trying to use project_data (which is not in the SelectableRefSet)
    # must be validated/rejected with PatchValidationError before they can be materialized.
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

    # Assert that PatchValidationError is raised due to invalid/hallucinated selectable ref
    with pytest.raises(PatchValidationError, match="project_data|hallucinated|SelectableRef"):
        InsertProducerStepApplier().apply(patch, snap)


def test_add_exception_handler_direct_step_construction_gap() -> None:
    """Gap: AddExceptionHandlerStepApplier directly creates BlockIR/StepIR and mutates plans."""
    # Arrange
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

    # Act
    patched_snap, event = AddExceptionHandlerStepApplier().apply(patch, snap)

    # Assert
    wsp = patched_snap.worker_step_plan
    assert wsp is not None
    steps = wsp.worker_steps["w_main"]
    assert len(steps) == 1
    step = steps[0]

    assert step.text == "Handle exception"
    assert step.flow_ref == "exc_1"
    assert step.block_ref == "b_repair_exc_1"

    wbp = patched_snap.worker_block_plan
    assert wbp is not None
    blocks = wbp.worker_blocks["w_main"].exception_flow_blocks["exc_1"]
    assert len(blocks) == 1
    assert blocks[0].block_id == "b_repair_exc_1"
    assert blocks[0].block_type == "SEQUENTIAL"


def test_create_worker_handoff_direct_ir_construction_gap() -> None:
    """Gap: CreateWorkerHandoffContractApplier directly constructs WorkerHandoffIR and INVOKE_WORKER StepIR."""
    # Arrange
    from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.applier import (
        CreateWorkerHandoffContractApplier,
    )
    from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR

    worker_spec = WorkerSpecIR(worker_id="w_main", worker_name="w_main", kind="main", purpose="test")
    child_spec = WorkerSpecIR(worker_id="w_child", worker_name="w_child", kind="child", purpose="test")

    snap = _snap(
        worker_plan=WorkerPlanIR(main_worker_id="w_main", workers=[worker_spec, child_spec], handoffs=[]),
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

    # Act
    patched_snap, event = CreateWorkerHandoffContractApplier().apply(patch, snap)

    # Assert
    handoffs = patched_snap.worker_plan.handoffs
    assert len(handoffs) == 1
    handoff = handoffs[0]
    assert handoff.handoff_id == "handoff_repair_promo_1"
    assert handoff.from_worker == "w_main"
    assert handoff.to_worker == "w_child"
    assert len(handoff.input_bindings) == 1
    assert handoff.input_bindings[0].parent_variable == "request_data"
    assert len(handoff.output_bindings) == 1
    assert handoff.output_bindings[0].parent_variable == "response_data"

    steps = patched_snap.worker_step_plan.worker_steps["w_main"]
    assert len(steps) == 1
    step = steps[0]
    assert step.command_type == "INVOKE_WORKER"
    assert step.handoff_id == "handoff_repair_promo_1"
    assert step.inputs == ["request_data"]
    assert step.outputs == ["response_data"]
