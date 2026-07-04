from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from nl2spl.compiler.spl_editing.demo import _build_default_service
from nl2spl.compiler.spl_editing.intent.evidence import create_evidence_packet
from nl2spl.compiler.spl_editing.interaction.model import (
    SubmitRepairDirectiveDraftRequest,
)
from nl2spl.compiler.spl_editing.materialization.model import MaterializationRequest
from nl2spl.compiler.spl_editing.patches.convert_delegation_to_main_flow_step.verifier import (
    ConvertDelegationToMainFlowStepVerifier,
)
from nl2spl.compiler.spl_editing.patches.define_child_worker_closure.verifier import (
    DefineChildWorkerClosureVerifier,
)
from nl2spl.compiler.spl_editing.presentation.service import (
    SPLEditingPresentationService,
)
from nl2spl.compiler.spl_editing.preview.errors import PreviewStaleError
from nl2spl.compiler.spl_editing.preview.hashes import compute_sha256
from nl2spl.compiler.spl_editing.stage_slices.worker_delegation_plans import (
    build_worker_delegation_typed_plans,
    typed_plan_hashes,
)
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerSpecIR

SNAPSHOT = Path("examples/output/demo/spl_editing_snapshot.json")


def _runtime():
    editing = _build_default_service(suggestion_llm=object())
    run_id = editing.register_snapshot_file(SNAPSHOT)
    editing._snapshot_repository = None
    presentation = SPLEditingPresentationService(editing)
    issue = next(
        item
        for item in editing.list_issue_inventory(run_id).editable
        if item.irs_ref.construct_type == "WORKER_PROMOTION"
    )
    snapshot = editing._get_snapshot(run_id)
    revision = f"{snapshot.compile_run_id}:{snapshot.snapshot_id}:{snapshot.overlay_version}"
    return editing, presentation, run_id, issue, snapshot, revision


def test_keep_main_flow_typed_preview_apply_lane_b() -> None:
    editing, presentation, run_id, issue, snapshot, revision = _runtime()
    request = SubmitRepairDirectiveDraftRequest(
        run_id=run_id,
        issue_id=issue.issue_id,
        strategy_id="worker_delegation.complete_closure.v2",
        option_id="keep_in_main_flow",
        contract_id="worker_delegation.keep_in_main_flow.v1",
        contract_version="1",
        revision_token=revision,
        field_values={"task_selection": "source gathering"},
        selected_ref_ids={},
        new_fact_declarations=(),
    )
    submitted = presentation.submit_repair_directive_draft(request)
    assert submitted.input_readiness == "input_complete"
    handle = presentation.preview_repair_directive(submitted.normalized_directive_id)
    assert "[MAIN_FLOW]" in handle.preview.rendered_preview
    session, verification = presentation.apply_repair_preview(
        submitted.normalized_directive_id, handle.preview.preview_id
    )
    assert verification.accepted is True
    assert verification.lane == "B"
    assert issue.primary_diagnostic_id in verification.resolved_diagnostic_ids
    patched = editing._snapshots.get(
        run_id, snapshot.snapshot_id, overlay_version=session.overlay_version
    )
    markers = patched.promotion_resolution_markers
    assert len(markers) == 1
    assert markers[0].resolution_kind == "kept_in_main_flow"
    base_children = {worker.worker_id for worker in snapshot.worker_plan.workers}
    after_children = {worker.worker_id for worker in patched.worker_plan.workers}
    assert after_children == base_children
    assert {item.handoff_id for item in patched.worker_plan.handoffs} == {
        item.handoff_id for item in snapshot.worker_plan.handoffs
    }
    patch = next(reversed(editing._applied_patches.values()))
    artifacts = editing._verifier._lane_b.replay(patched)
    verifier = ConvertDelegationToMainFlowStepVerifier()
    assert verifier.verify(patch, snapshot, patched, artifacts) == ()
    extra_ref_marker = replace(
        markers[0],
        materialized_construct_refs=(
            *markers[0].materialized_construct_refs,
            "worker:unrelated",
        ),
    )
    duplicate_ref_marker = replace(
        markers[0],
        materialized_construct_refs=(
            *markers[0].materialized_construct_refs,
            markers[0].materialized_construct_refs[0],
        ),
    )
    for marker in (extra_ref_marker, duplicate_ref_marker):
        tampered = replace(patched, promotion_resolution_markers=(marker,))
        assert verifier.verify(patch, snapshot, tampered, artifacts)
    apply_result = next(reversed(editing._apply_results.values()))
    assert all(ref.user_text == handle.evidence_user_text for ref in apply_result.evidence_refs)
    assert handle.evidence_user_text.startswith('{"additional_instruction":')
    stage_results = apply_result.audit_metadata["stage_slice_results"]
    assert len(stage_results) == 4
    assert all(len(result.artifact_updates) == 1 for result in stage_results)


def test_keep_main_missing_task_selection_stays_input_required() -> None:
    _editing, presentation, run_id, issue, _snapshot, revision = _runtime()
    interaction = presentation.get_repair_interaction(
        run_id, issue.issue_id, "keep_in_main_flow", revision
    )
    assert interaction.input_readiness == "input_required"
    assert any(
        field.field_id == "task_selection" and field.required for field in interaction.fields
    )
    request = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        "keep_in_main_flow",
        "worker_delegation.keep_in_main_flow.v1",
        "1",
        revision,
        {},
        {},
        (),
    )
    submitted = presentation.submit_repair_directive_draft(request)
    assert submitted.input_readiness == "input_required"
    assert submitted.normalized_directive_id is None


def test_keep_main_does_not_delete_substring_matched_unowned_child() -> None:
    editing, presentation, run_id, issue, snapshot, revision = _runtime()
    target = presentation._worker_delegation_context(run_id, issue.issue_id, "keep_in_main_flow")[4]
    candidate_id = target.target_ref.removeprefix("worker_promotion:")
    unrelated_worker_id = "customer_archive_worker"
    unrelated_handoff_id = f"customer_{candidate_id}_archive"
    snapshot.worker_plan.workers.append(
        WorkerSpecIR(
            worker_id=unrelated_worker_id,
            worker_name="CustomerArchive",
            kind="child",
            purpose="Archive customer records",
            boundary_kind="child_worker",
        )
    )
    snapshot.worker_flow_plan.worker_flows[unrelated_worker_id] = FlowStructureIR()
    snapshot.worker_block_plan.worker_blocks[unrelated_worker_id] = BlockStructureIR(
        main_flow_blocks=[BlockIR("b_archive", "SEQUENTIAL", spans=[])]
    )
    snapshot.worker_step_plan.worker_steps[unrelated_worker_id] = [
        StepIR(
            "st_archive",
            "Archive records",
            [],
            "GENERAL_COMMAND",
            block_ref="b_archive",
        )
    ]
    snapshot.worker_step_plan.main_worker_steps.append(
        StepIR(
            "st_invoke_archive",
            "Invoke archive worker",
            [],
            "INVOKE_WORKER",
            integration_ref="CustomerArchive",
            handoff_id=unrelated_handoff_id,
        )
    )
    request = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        "keep_in_main_flow",
        "worker_delegation.keep_in_main_flow.v1",
        "1",
        revision,
        {"task_selection": "source gathering"},
        {},
        (),
    )
    submitted = presentation.submit_repair_directive_draft(request)
    handle = presentation.preview_repair_directive(submitted.normalized_directive_id)
    session = editing.apply_preview_result(
        handle.session_id,
        handle.suggestion_id,
        handle.preview.preview_id,
        user_text=handle.evidence_user_text,
    )
    patched = editing._snapshots.get(
        run_id, snapshot.snapshot_id, overlay_version=session.overlay_version
    )
    assert any(w.worker_id == unrelated_worker_id for w in patched.worker_plan.workers)
    assert unrelated_worker_id in patched.worker_step_plan.worker_steps
    assert any(
        step.handoff_id == unrelated_handoff_id
        for step in patched.worker_step_plan.main_worker_steps
    )


def test_define_child_worker_complete_closure_lane_b() -> None:
    editing, presentation, run_id, issue, snapshot, revision = _runtime()
    interaction = presentation.get_repair_interaction(
        run_id, issue.issue_id, "define_child_worker", revision
    )
    input_ref = next(
        option.value
        for field in interaction.fields
        if field.field_id == "input_refs"
        for option in field.options
        if option.label == "user_request"
    )
    request = SubmitRepairDirectiveDraftRequest(
        run_id=run_id,
        issue_id=issue.issue_id,
        strategy_id="worker_delegation.complete_closure.v2",
        option_id="define_child_worker",
        contract_id="worker_delegation.define_child_worker.v1",
        contract_version="1",
        revision_token=revision,
        field_values={
            "delegated_responsibility": "Gather approved source evidence",
            "invocation_timing": "append",
            "result_usage": (
                {
                    "output_local_id": "evidence",
                    "create_parent_local_temporary": "yes",
                },
            ),
        },
        selected_ref_ids={"input_refs": (input_ref,)},
        new_fact_declarations=(
            {
                "local_id": "evidence",
                "display_name": "delegated evidence",
                "semantic_description": "Evidence returned by the child worker",
                "data_type_hint": "text",
            },
        ),
    )
    submitted = presentation.submit_repair_directive_draft(request)
    assert submitted.input_readiness == "input_complete"
    handle = presentation.preview_repair_directive(submitted.normalized_directive_id)
    assert "[WORKER: ChildWorker_" in handle.preview.rendered_preview
    directive = presentation._directives.get(submitted.normalized_directive_id)
    target = presentation._directive_context[directive.directive_id][2]
    bundle = build_worker_delegation_typed_plans(snapshot, target, directive)
    actual_plan_hashes = {value for _name, value in typed_plan_hashes(bundle)}
    assert len(handle.preview.slice_typed_plan_hashes) == 7
    assert {item.typed_plan_hash for item in handle.preview.slice_typed_plan_hashes}.issubset(
        actual_plan_hashes
    )
    assert handle.preview.interaction_contract_hash == compute_sha256(
        ("worker_delegation.define_child_worker.v1", "1")
    )
    context = editing._confirmation_contexts.get(f"ctx_{handle.suggestion_id}")
    session, verification = presentation.apply_repair_preview(
        submitted.normalized_directive_id, handle.preview.preview_id
    )
    assert verification.accepted is True
    assert verification.lane == "B"
    assert issue.primary_diagnostic_id in verification.resolved_diagnostic_ids
    patched = editing._snapshots.get(
        run_id, snapshot.snapshot_id, overlay_version=session.overlay_version
    )
    marker = patched.promotion_resolution_markers[0]
    child_id = next(
        ref.removeprefix("worker:")
        for ref in marker.materialized_construct_refs
        if ref.startswith("worker:")
    )
    child = next(worker for worker in patched.worker_plan.workers if worker.worker_id == child_id)
    assert len(patched.worker_step_plan.worker_steps[child.worker_id]) == 1
    handoff = next(
        item for item in patched.worker_plan.handoffs if item.to_worker == child.worker_id
    )
    invoke = next(
        step
        for step in patched.worker_step_plan.main_worker_steps
        if step.handoff_id == handoff.handoff_id
    )
    assert invoke.command_type == "INVOKE_WORKER"
    assert patched.promotion_resolution_markers[0].resolution_kind == "defined_child_worker"
    rendered = editing._verifier._lane_b.replay(patched).rendered_spl
    assert "Gather approved source evidence" in rendered
    assert child.worker_name in rendered
    assert "tmp_delegated_evidence" not in rendered.split("[END_VARIABLES]", 1)[0]
    patch = next(reversed(editing._applied_patches.values()))
    reused = editing._materialization.materialize(
        MaterializationRequest(
            snapshot=patched,
            issue=context.issue,
            target=context.target,
            catalog_entry=context.catalog_entry,
            intent=patch.payload,
            refset=context.refset,
            resolved_refs=context.resolved_refs,
            evidence_packet=create_evidence_packet(
                intent=patch.payload,
                repair_patch_id="patch_reuse_probe",
                related_diagnostic_id=patch.evidence.related_diagnostic_id,
                user_text="historical artifact reuse probe",
            ),
        )
    )
    assert reused.changed_refs == ()
    assert reused.evidence_refs == ()
    assert all(result.trace["action"] == "bind_existing" for result in reused.stage_slice_results)


def test_define_child_interaction_exposes_typed_placement_and_result_targets() -> None:
    _editing, presentation, run_id, issue, _snapshot, revision = _runtime()
    interaction = presentation.get_repair_interaction(
        run_id, issue.issue_id, "define_child_worker", revision
    )
    placement = next(field for field in interaction.fields if field.field_id == "placement_ref")
    assert placement.ref_role == "placement_anchor"
    assert placement.options
    result_schema = next(
        schema
        for schema in interaction.schemas
        if schema.schema_id == "worker_delegation.result_usage.v1"
    )
    parent_target = next(
        field for field in result_schema.fields if field.field_id == "parent_ref_id"
    )
    assert parent_target.input_type == "reference_select"
    assert parent_target.ref_role == "binding_target"
    assert parent_target.options


def test_worker_options_unavailable_when_runtime_bundle_is_partial() -> None:
    editing, presentation, run_id, issue, _snapshot, _revision = _runtime()
    editing._materialization.registry._materializers.pop("worker_delegation.complete_closure.v2")
    detail = presentation.get_issue_detail_presentation(run_id, issue.issue_id)
    assert {option.availability.value for option in detail.available_repairs} == {
        "unavailable_incomplete_runtime_bundle"
    }
    revision = f"{_snapshot.compile_run_id}:{_snapshot.snapshot_id}:{_snapshot.overlay_version}"
    interaction = presentation.get_repair_interaction(
        run_id, issue.issue_id, "define_child_worker", revision
    )
    assert interaction.input_readiness == "not_evaluated"


def test_worker_options_unavailable_when_one_required_stage_slice_is_missing() -> None:
    editing, presentation, run_id, issue, _snapshot, _revision = _runtime()
    materializer = editing._materialization.registry.get_materializer(
        "worker_delegation.complete_closure.v2"
    )
    materializer.stage_slice_registry._slices.pop("stage7.worker_invoke.v2")
    detail = presentation.get_issue_detail_presentation(run_id, issue.issue_id)
    assert {option.availability.value for option in detail.available_repairs} == {
        "unavailable_incomplete_runtime_bundle"
    }


def test_define_child_accepts_existing_parent_binding_target() -> None:
    _editing, presentation, run_id, issue, _snapshot, revision = _runtime()
    interaction = presentation.get_repair_interaction(
        run_id, issue.issue_id, "define_child_worker", revision
    )
    input_ref = next(
        option.value
        for field in interaction.fields
        if field.field_id == "input_refs"
        for option in field.options
        if option.label == "user_request"
    )
    result_schema = next(
        schema
        for schema in interaction.schemas
        if schema.schema_id == "worker_delegation.result_usage.v1"
    )
    parent_ref = next(
        option.value
        for field in result_schema.fields
        if field.field_id == "parent_ref_id"
        for option in field.options
        if option.label == "user_request"
    )
    request = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        "define_child_worker",
        "worker_delegation.define_child_worker.v1",
        "1",
        revision,
        {
            "delegated_responsibility": "Normalize source evidence",
            "invocation_timing": "append",
            "result_usage": (
                {
                    "output_local_id": "normalized",
                    "parent_ref_id": parent_ref,
                    "create_parent_local_temporary": "no",
                },
            ),
        },
        {"input_refs": (input_ref,)},
        (
            {
                "local_id": "normalized",
                "display_name": "normalized evidence",
                "semantic_description": "Normalized evidence",
                "data_type_hint": "text",
            },
        ),
    )
    submitted = presentation.submit_repair_directive_draft(request)
    assert submitted.input_readiness == "input_complete"


def test_define_child_accepts_typed_before_placement_anchor() -> None:
    _editing, presentation, run_id, issue, _snapshot, revision = _runtime()
    interaction = presentation.get_repair_interaction(
        run_id, issue.issue_id, "define_child_worker", revision
    )
    input_ref = next(
        option.value
        for field in interaction.fields
        if field.field_id == "input_refs"
        for option in field.options
        if option.label == "user_request"
    )
    placement_ref = next(
        option.value
        for field in interaction.fields
        if field.field_id == "placement_ref"
        for option in field.options
    )
    request = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        "define_child_worker",
        "worker_delegation.define_child_worker.v1",
        "1",
        revision,
        {
            "delegated_responsibility": "Gather evidence before drafting",
            "invocation_timing": "before",
            "result_usage": (
                {
                    "output_local_id": "evidence",
                    "create_parent_local_temporary": "yes",
                },
            ),
        },
        {"input_refs": (input_ref,), "placement_ref": (placement_ref,)},
        (
            {
                "local_id": "evidence",
                "display_name": "early evidence",
                "semantic_description": "Evidence gathered before the selected step",
                "data_type_hint": "text",
            },
        ),
    )
    submitted = presentation.submit_repair_directive_draft(request)
    assert submitted.input_readiness == "input_complete"
    directive = presentation._directives.get(submitted.normalized_directive_id)
    assert directive.invocation_timing.placement_mode == "before"
    assert directive.placement_ref.ref.ref_id == placement_ref


def test_define_child_missing_fields_and_stale_revision_do_not_preview() -> None:
    _editing, presentation, run_id, issue, _snapshot, revision = _runtime()
    missing = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        "define_child_worker",
        "worker_delegation.define_child_worker.v1",
        "1",
        revision,
        {},
        {},
        (),
    )
    result = presentation.submit_repair_directive_draft(missing)
    assert result.normalized_directive_id is None
    assert result.input_readiness == "input_required"
    stale = SubmitRepairDirectiveDraftRequest(
        **{**missing.__dict__, "revision_token": revision.rsplit(":", 1)[0] + ":99"}
    )
    result = presentation.submit_repair_directive_draft(stale)
    assert result.normalized_directive_id is None
    assert result.input_readiness == "input_invalid"


def test_define_child_verifier_rejects_marker_and_closure_negative_matrix() -> None:
    editing, presentation, run_id, issue, base, revision = _runtime()
    interaction = presentation.get_repair_interaction(
        run_id, issue.issue_id, "define_child_worker", revision
    )
    input_ref = next(
        option.value
        for field in interaction.fields
        if field.field_id == "input_refs"
        for option in field.options
        if option.label == "user_request"
    )
    request = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        "define_child_worker",
        "worker_delegation.define_child_worker.v1",
        "1",
        revision,
        {
            "delegated_responsibility": "Verify closure consistency",
            "invocation_timing": "append",
            "result_usage": (
                {
                    "output_local_id": "verified",
                    "create_parent_local_temporary": "yes",
                },
            ),
        },
        {"input_refs": (input_ref,)},
        (
            {
                "local_id": "verified",
                "display_name": "verified result",
                "semantic_description": "Result used for closure verification",
                "data_type_hint": "text",
            },
        ),
    )
    submitted = presentation.submit_repair_directive_draft(request)
    handle = presentation.preview_repair_directive(submitted.normalized_directive_id)
    session, verification = presentation.apply_repair_preview(
        submitted.normalized_directive_id, handle.preview.preview_id
    )
    assert verification.accepted
    valid = editing._snapshots.get(
        run_id, base.snapshot_id, overlay_version=session.overlay_version
    )
    patch = next(reversed(editing._applied_patches.values()))
    artifacts = editing._verifier._lane_b.replay(valid)
    marker = valid.promotion_resolution_markers[0]
    child_id = next(
        ref.removeprefix("worker:")
        for ref in marker.materialized_construct_refs
        if ref.startswith("worker:")
    )
    child = next(worker for worker in valid.worker_plan.workers if worker.worker_id == child_id)
    handoff = next(item for item in valid.worker_plan.handoffs if item.to_worker == child.worker_id)

    closure_without_marker = replace(valid, promotion_resolution_markers=())

    marker_without_full_closure = copy.deepcopy(valid)
    marker_without_full_closure.worker_flow_plan.worker_flows.pop(child.worker_id)

    marker_ref_missing = replace(
        valid,
        promotion_resolution_markers=(
            replace(
                valid.promotion_resolution_markers[0],
                materialized_construct_refs=valid.promotion_resolution_markers[
                    0
                ].materialized_construct_refs[:-1],
            ),
        ),
    )

    orphan_handoff = copy.deepcopy(valid)
    orphan_handoff.worker_step_plan.worker_steps[valid.worker_plan.main_worker_id] = [
        step
        for step in orphan_handoff.worker_step_plan.main_worker_steps
        if step.handoff_id != handoff.handoff_id
    ]

    orphan_invoke = copy.deepcopy(valid)
    orphan_invoke.worker_plan.handoffs = [
        item for item in orphan_invoke.worker_plan.handoffs if item.handoff_id != handoff.handoff_id
    ]

    extra_child_command = copy.deepcopy(valid)
    extra = copy.deepcopy(extra_child_command.worker_step_plan.worker_steps[child.worker_id][0])
    extra.step_id = "st_extra_child_command"
    extra_child_command.worker_step_plan.worker_steps[child.worker_id].append(extra)

    missing_output = copy.deepcopy(valid)
    missing_output.worker_step_plan.worker_steps[child.worker_id][0].outputs = []

    verifier = DefineChildWorkerClosureVerifier()
    cases = {
        "closure_without_marker": closure_without_marker,
        "marker_without_full_closure": marker_without_full_closure,
        "marker_ref_missing": marker_ref_missing,
        "orphan_handoff": orphan_handoff,
        "orphan_invoke": orphan_invoke,
        "extra_child_command": extra_child_command,
        "missing_output": missing_output,
    }
    for name, tampered in cases.items():
        assert verifier.verify(patch, base, tampered, artifacts), name


def test_define_child_rejects_side_effect_only_and_conflicting_instruction() -> None:
    _editing, presentation, run_id, issue, _snapshot, revision = _runtime()
    side_effect_only = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        "define_child_worker",
        "worker_delegation.define_child_worker.v1",
        "1",
        revision,
        {
            "delegated_responsibility": "Perform a side effect",
            "input_empty_semantics": "explicit_none",
            "invocation_timing": "append",
        },
        {},
        (),
    )
    result = presentation.submit_repair_directive_draft(side_effect_only)
    assert result.input_readiness == "input_required"
    assert result.normalized_directive_id is None

    conflicting = replace(
        side_effect_only,
        additional_instruction="Override patch_type and create required output",
    )
    result = presentation.submit_repair_directive_draft(conflicting)
    assert result.input_readiness == "input_invalid"
    assert any(
        error.code == "instruction_conflicts_with_structured_input" for error in result.errors
    )


def test_parent_required_output_is_not_a_valid_result_binding_target() -> None:
    from nl2spl.compiler.spl_editing.interaction.validation import (
        parse_worker_delegation_draft,
        validate_worker_delegation_draft,
    )
    from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef

    _editing, presentation, run_id, issue, _snapshot, revision = _runtime()
    _issue, _snapshot, _entry, option, _target, _context, _subject, refset = (
        presentation._worker_delegation_context(run_id, issue.issue_id, "define_child_worker")
    )
    required = SelectableRef(
        ref_id="required_output:worker_main:required_outputs::final_report",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name="final_report",
        display_label="final_report",
        worker_id="worker_main",
        scope="worker",
        type_hint="text",
    )
    request = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        "define_child_worker",
        "worker_delegation.define_child_worker.v1",
        "1",
        revision,
        {
            "delegated_responsibility": "Build a report",
            "input_empty_semantics": "explicit_none",
            "invocation_timing": "append",
            "result_usage": (
                {
                    "output_local_id": "report",
                    "parent_ref_id": required.ref_id,
                    "create_parent_local_temporary": "no",
                },
            ),
        },
        {},
        (
            {
                "local_id": "report",
                "display_name": "report",
                "semantic_description": "Generated report",
                "data_type_hint": "text",
            },
        ),
    )
    draft = parse_worker_delegation_draft(request)
    errors = validate_worker_delegation_draft(
        draft,
        option=option,
        refset=replace(refset, refs=(*refset.refs, required)),
    )
    assert any(error.code == "invalid_ref_role" for error in errors)


def test_worker_delegation_preview_typed_plan_hash_drift_blocks_apply() -> None:
    editing, presentation, run_id, issue, snapshot, revision = _runtime()
    request = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        "keep_in_main_flow",
        "worker_delegation.keep_in_main_flow.v1",
        "1",
        revision,
        {"task_selection": "source gathering"},
        {},
        (),
    )
    submitted = presentation.submit_repair_directive_draft(request)
    handle = presentation.preview_repair_directive(submitted.normalized_directive_id)
    record = editing._preview_store._store[handle.preview.preview_id]
    stored = record["preview"]
    first = stored.slice_typed_plan_hashes[0]
    record["preview"] = replace(
        stored,
        slice_typed_plan_hashes=(
            replace(first, typed_plan_hash="tampered_typed_plan_hash"),
            *stored.slice_typed_plan_hashes[1:],
        ),
    )
    with pytest.raises(PreviewStaleError, match="slice_typed_plan_hashes mismatch"):
        presentation.apply_repair_preview(
            submitted.normalized_directive_id, handle.preview.preview_id
        )
    assert snapshot.overlay_version == 0
    assert editing._apply_results == {}
