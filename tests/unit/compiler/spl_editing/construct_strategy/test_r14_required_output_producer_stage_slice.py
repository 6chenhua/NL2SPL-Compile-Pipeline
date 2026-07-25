"""R14 required_output producer strategy/stage-slice migration tests."""

from __future__ import annotations

import ast
import pathlib

import pytest

from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.intent.model import (
    InsertProducerStepIntentPayload,
    RepairEvidencePacket,
)
from nl2spl.compiler.spl_editing.materialization.id_allocator import IdAllocator
from nl2spl.compiler.spl_editing.materialization.model import MaterializationInput
from nl2spl.compiler.spl_editing.materialization.registry import (
    build_default_materialization_registry,
)
from nl2spl.compiler.spl_editing.materialization.stage7.producer_step import (
    Stage7ProducerRepairMaterializer,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import (
    ResolvedSelectableRef,
    SelectableRef,
    SelectableRefSet,
)
from nl2spl.compiler.spl_editing.stage_slices import StagePolicy, StageSliceInput
from nl2spl.compiler.spl_editing.stage_slices.errors import StageSliceValidationError
from nl2spl.compiler.spl_editing.stage_slices.stage7 import (
    Stage7RequiredOutputProducerCommandRepairSlice,
)
from nl2spl.compiler.spl_editing.strategy import RepairDirective
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from tests.unit.compiler.spl_editing.test_b6_missing_output_producer_patch import (
    _make_intent_payload,
    _snap,
)


def _irs_ref() -> DiagnosticIRSRef:
    return DiagnosticIRSRef(
        construct_type="REQUIRED_OUTPUT",
        construct_id="draft",
        slot_name="producer",
        construct_path=("worker", "w_main", "outputs", "draft"),
        source_authority="post_normalize_irs",
    )


def _target() -> RepairTarget:
    return RepairTarget(
        target_ref="required_output:w_main:required_output_context::draft",
        target_kind="element",
        irs_ref=_irs_ref(),
        affordance_id="required_output.insert_or_bind_producer",
        construct_path=("worker", "w_main", "outputs", "draft"),
        worker_id="w_main",
        canonical_name="draft",
        editable_artifacts=("WorkerStepPlanIR",),
    )


def _refset() -> SelectableRefSet:
    return SelectableRefSet(
        set_id="refset_producer",
        issue_id="issue_1",
        snapshot_id="snap_1",
        worker_scope="w_main",
        refs=(
            SelectableRef(
                ref_id="required_output:w_main:required_output_context::draft",
                ref_kind="required_output",
                ref_role="target_output",
                canonical_name="draft",
                display_label="draft",
                worker_id="w_main",
            ),
            SelectableRef(
                ref_id="var:w_main:ctx::topic",
                ref_kind="variable",
                ref_role="selectable_input",
                canonical_name="topic",
                display_label="topic",
                worker_id="w_main",
            ),
        ),
        policy_id="required_output.producer.selectable_refs.v1",
    )


def _intent(selected_ref_ids: tuple[str, ...] = ("var:w_main:ctx::topic",)):
    return _make_intent_payload(
        selected_ref_ids=selected_ref_ids,
        payload=InsertProducerStepIntentPayload(
            target_output_ref_id="required_output:w_main:required_output_context::draft",
            selected_input_ref_ids=selected_ref_ids,
            producer_goal="Draft the document from selected context.",
        ),
    )


def _directive(selected_ref_ids: tuple[str, ...] = ("var:w_main:ctx::topic",)) -> RepairDirective:
    return RepairDirective(
        directive_id="dir_producer",
        source="system_default",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        requested_behavior="Draft the document from selected context.",
        selected_ref_hints=selected_ref_ids,
    )


def _slice_input(selected_ref_ids: tuple[str, ...] = ("var:w_main:ctx::topic",)) -> StageSliceInput:
    snap = _snap()
    return StageSliceInput(
        slice_id="stage7.required_output_producer_command_repair.v1",
        stage_authority="stage7.worker_step_plan",
        snapshot=snap,
        target=_target(),
        refset=_refset(),
        directive=_directive(selected_ref_ids),
        intent=_intent(selected_ref_ids),
        dependency_closure=(),
        stage_policy=StagePolicy(
            policy_id="required_output.producer_command.v1",
            stage_authority="stage7.worker_step_plan",
            allowed_typed_plan_kinds=("CommandIntentPlan",),
            generation_mode="none",
        ),
        selected_ref_ids=selected_ref_ids,
        id_allocator=IdAllocator.from_snapshot(snap, ("step",)),
        dry_run=False,
    )


def _materialization_input(selected_ref_ids: tuple[str, ...] = ("var:w_main:ctx::topic",)) -> MaterializationInput:
    snap = _snap()
    refset = _refset()
    selected_ref = refset.get_ref("var:w_main:ctx::topic")
    resolved_refs = ()
    if selected_ref_ids:
        assert selected_ref is not None
        resolved_refs = (ResolvedSelectableRef(selected_ref, "selectable_input", True),)
    return MaterializationInput(
        snapshot=snap,
        issue=EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="diag_1",
            related_diagnostic_ids=(),
            issue_group_id=None,
            kind="missing_output_producer",
            target_ref="required_output:w_main:required_output_context::draft",
            source_span_ids=(),
            message="Required output has no producer.",
            irs_ref=_irs_ref(),
            missing_slot="producer",
            repairability="editable",
            affordance_ids=("required_output.insert_or_bind_producer",),
            default_affordance_id="required_output.insert_or_bind_producer",
        ),
        target=_target(),
        catalog_entry=RepairCatalogEntry(
            entry_id="REQUIRED_OUTPUT.producer.missing_output_producer.required_output.insert_or_bind_producer",
            affordance_id="required_output.insert_or_bind_producer",
            construct_type="REQUIRED_OUTPUT",
            slot_name="producer",
            diagnostic_kind="missing_output_producer",
            supported_patch_types=("InsertProducerStep",),
            default_patch_type="InsertProducerStep",
            handler_id="missing_output_producer",
            context_id="required_output_context",
            target_resolver_id="required_output_target",
            selectable_ref_policy_id="required_output.producer.selectable_refs.v1",
            materialization_plan_id="stage7.step_producer_repair.v1",
            default_verification_lane="B",
            editable_artifacts=("WorkerStepPlanIR",),
        ),
        intent=_intent(selected_ref_ids),
        refset=refset,
        resolved_refs=resolved_refs,
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="ev_patch_1",
            confirmed_intent_id="int_001",
            repair_patch_id="patch_1",
            related_diagnostic_id="diag_1",
            user_text="Confirm producer",
            confirmed_selected_ref_ids=selected_ref_ids,
        ),
        plan=build_default_materialization_registry().get("stage7.step_producer_repair.v1"),
        id_allocator=IdAllocator.from_snapshot(snap, ("step",)),
    )


def test_stage7_required_output_slice_materializes_producer_command() -> None:
    result = Stage7RequiredOutputProducerCommandRepairSlice().execute(_slice_input())
    step_plan = result.artifact_updates["worker_step_plan"]
    step = step_plan.worker_steps["w_main"][-1]

    assert step.outputs == ["draft"]
    assert step.inputs == ["topic"]
    assert step.metadata["target_output_name"] == "draft"
    assert result.consumed_selected_ref_ids == ("var:w_main:ctx::topic",)


def test_stage7_required_output_slice_rejects_unknown_selected_ref() -> None:
    with pytest.raises(StageSliceValidationError, match="Unknown selected ref"):
        Stage7RequiredOutputProducerCommandRepairSlice().execute(
            _slice_input(("var:w_main:ctx::missing",))
        )


def test_stage7_required_output_slice_records_no_input_warning() -> None:
    result = Stage7RequiredOutputProducerCommandRepairSlice().execute(_slice_input(()))

    assert result.trace["warnings"] == ("no_selected_inputs",)


def test_producer_materializer_returns_stage_slice_result_and_producer_index_sees_output() -> None:
    result = Stage7ProducerRepairMaterializer().materialize(_materialization_input())
    step = result.patched_snapshot.worker_step_plan.worker_steps["w_main"][-1]
    index = ProducerIndex(steps=[step])

    assert [r.slice_id for r in result.stage_slice_results] == [
        "stage7.required_output_producer_command_repair.v1"
    ]
    assert index.is_produced("draft") is True


def test_producer_materializer_no_longer_constructs_step_ir_directly() -> None:
    source = pathlib.Path(
        "src/nl2spl/compiler/spl_editing/materialization/stage7/producer_step.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_names = set()
    call_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            call_names.add(node.func.id)

    assert "StepIR" not in imported_names
    assert "StepIR" not in call_names
