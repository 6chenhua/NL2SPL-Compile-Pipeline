"""R2 ConstructRepairIntent and EvidencePacket tests."""

from __future__ import annotations

import json

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.intent import (
    ConstructRepairIntent,
    IntentValidator,
    create_evidence_packet,
    parse_raw_intent,
)
from nl2spl.compiler.spl_editing.selectable_refs import SelectableRef, SelectableRefSet


def _catalog_entry(
    materialization_plan_id: str | None = "stage7.step_producer_repair.v1", **kw: object
) -> RepairCatalogEntry:
    d: dict[str, object] = dict(
        entry_id="REQUIRED_OUTPUT.producer.missing_output_producer.required_output.insert_or_bind_producer",
        affordance_id="required_output.insert_or_bind_producer",
        construct_type="REQUIRED_OUTPUT",
        slot_name="producer",
        diagnostic_kind="missing_output_producer",
        supported_patch_types=("InsertProducerStep",),
        default_verification_lane="A",
        materialization_plan_id=materialization_plan_id,
    )
    d.update(kw)
    return RepairCatalogEntry(**d)  # type: ignore[arg-type]


def _refset(refs: tuple[SelectableRef, ...] = (), **kw: object) -> SelectableRefSet:
    d: dict[str, object] = dict(
        set_id="set_1",
        issue_id="i1",
        snapshot_id="snap_1",
        worker_scope="w_main",
        refs=refs,
        policy_id="required_output.producer.selectable_refs.v1",
    )
    d.update(kw)
    return SelectableRefSet(**d)  # type: ignore[arg-type]


def test_insert_producer_intent_rejects_inputs_outputs_command_type() -> None:
    """Verify that parsing fails when raw JSON or payload contains forbidden IR fields."""
    # 1. Top-level forbidden field
    raw_top = json.dumps(
        {
            "intent_id": "int_1",
            "inputs": ["project_data"],
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::draft",
                "selected_input_ref_ids": [],
            },
        }
    )
    res_top = parse_raw_intent(
        raw_top, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert not res_top.is_success
    assert any("Forbidden field 'inputs'" in err for err in res_top.errors)

    # 2. Payload-level forbidden field
    raw_payload = json.dumps(
        {
            "intent_id": "int_2",
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::draft",
                "selected_input_ref_ids": [],
                "command_type": "GENERAL_COMMAND",
            },
        }
    )
    res_payload = parse_raw_intent(
        raw_payload, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert not res_payload.is_success
    assert any("Forbidden field 'command_type'" in err for err in res_payload.errors)


def test_target_output_ref_must_exist() -> None:
    """Verify that validation fails if target_output_ref_id does not exist in SelectableRefSet."""
    raw = json.dumps(
        {
            "target_construct_type": "REQUIRED_OUTPUT",
            "target_slot_name": "producer",
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::non_existent",  # noqa: E501
                "selected_input_ref_ids": [],
            },
            "materialization_plan_id": "stage7.step_producer_repair.v1",
        }
    )
    res = parse_raw_intent(
        raw, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert res.is_success
    intent = res.intent
    assert intent is not None

    refset = _refset(refs=())
    val_res = IntentValidator.validate(intent, refset, _catalog_entry())
    assert not val_res.is_success
    assert any("non_existent" in err and "not found" in err for err in val_res.errors)


def test_selected_input_refs_must_exist() -> None:
    """Verify that validation fails if selected_input_ref_ids do not exist in SelectableRefSet."""
    target_ref = SelectableRef(
        ref_id="required_output:w_main:required_output_context::draft",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name="draft",
        display_label="draft",
        worker_id="w_main",
    )
    refset = _refset(refs=(target_ref,))

    raw = json.dumps(
        {
            "target_construct_type": "REQUIRED_OUTPUT",
            "target_slot_name": "producer",
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::draft",
                "selected_input_ref_ids": ["variable:w_main:symbol_table:worker:hallucinated_var"],
            },
            "materialization_plan_id": "stage7.step_producer_repair.v1",
        }
    )
    res = parse_raw_intent(
        raw, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert res.is_success
    intent = res.intent
    assert intent is not None

    val_res = IntentValidator.validate(intent, refset, _catalog_entry())
    assert not val_res.is_success
    assert any("hallucinated_var" in err and "not found" in err for err in val_res.errors)


def test_selected_input_ref_role_mismatch_rejected() -> None:
    """Verify that validation fails if a selected input ref has the wrong role (e.g. target_output)."""  # noqa: E501
    target_ref = SelectableRef(
        ref_id="required_output:w_main:required_output_context::draft",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name="draft",
        display_label="draft",
        worker_id="w_main",
    )
    refset = _refset(refs=(target_ref,))

    # Pass the target_ref_id in selected_input_ref_ids (role is target_output, expected selectable_input)  # noqa: E501
    raw = json.dumps(
        {
            "target_construct_type": "REQUIRED_OUTPUT",
            "target_slot_name": "producer",
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::draft",
                "selected_input_ref_ids": ["required_output:w_main:required_output_context::draft"],
            },
            "materialization_plan_id": "stage7.step_producer_repair.v1",
        }
    )
    res = parse_raw_intent(
        raw, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert res.is_success
    intent = res.intent
    assert intent is not None

    val_res = IntentValidator.validate(intent, refset, _catalog_entry())
    assert not val_res.is_success
    assert any(
        "has role 'target_output', expected 'selectable_input'" in err for err in val_res.errors
    )


def test_materialization_plan_id_must_match_catalog() -> None:
    """Verify that validation fails if materialization_plan_id does not match catalog entry expected plan."""  # noqa: E501
    target_ref = SelectableRef(
        ref_id="required_output:w_main:required_output_context::draft",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name="draft",
        display_label="draft",
        worker_id="w_main",
    )
    refset = _refset(refs=(target_ref,))

    raw = json.dumps(
        {
            "target_construct_type": "REQUIRED_OUTPUT",
            "target_slot_name": "producer",
            "materialization_plan_id": "stage10.incorrect_plan",
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::draft",
                "selected_input_ref_ids": [],
            },
        }
    )
    res = parse_raw_intent(
        raw, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert res.is_success
    intent = res.intent
    assert intent is not None

    val_res = IntentValidator.validate(intent, refset, _catalog_entry())
    assert not val_res.is_success
    assert any(
        "does not match catalog expected 'stage7.step_producer_repair.v1'" in err
        for err in val_res.errors
    )


def test_evidence_packet_carries_user_text_and_selected_refs() -> None:
    """Verify that RepairEvidencePacket is correctly populated from user confirmation context."""
    intent = ConstructRepairIntent(
        intent_id="int_123",
        issue_id="i1",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="x",
        target_slot_name="producer",
        target_ref_id="required_output:w_main:required_output_context::draft",
        selected_ref_ids=("worker_input:w_main:w_main::main_input",),
    )

    ev = create_evidence_packet(
        intent=intent,
        repair_patch_id="p123",
        related_diagnostic_id="diag_123",
        user_text="User says: fix it",
    )

    assert ev.confirmed_intent_id == "int_123"
    assert ev.repair_patch_id == "p123"
    assert ev.related_diagnostic_id == "diag_123"
    assert ev.user_text == "User says: fix it"
    assert ev.confirmed_selected_ref_ids == ("worker_input:w_main:w_main::main_input",)
    assert ev.evidence_kind == "user_confirmed_repair"
    assert ev.confirmed_at is not None


def test_producer_goal_ref_text_is_not_treated_as_input_ref() -> None:
    """Verify that variable names inside producer_goal text are not parsed or resolved as selected input refs."""  # noqa: E501
    target_ref = SelectableRef(
        ref_id="required_output:w_main:required_output_context::draft",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name="draft",
        display_label="draft",
        worker_id="w_main",
    )
    refset = _refset(refs=(target_ref,))

    # producer_goal mentions "project_data" in its text but selected_input_ref_ids is empty.
    raw = json.dumps(
        {
            "target_construct_type": "REQUIRED_OUTPUT",
            "target_slot_name": "producer",
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::draft",
                "selected_input_ref_ids": [],
                "producer_goal": "Generate assumptions log using project_data.",
            },
            "materialization_plan_id": "stage7.step_producer_repair.v1",
        }
    )
    res = parse_raw_intent(
        raw, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert res.is_success
    intent = res.intent
    assert intent is not None

    val_res = IntentValidator.validate(intent, refset, _catalog_entry())
    # Should be valid because "project_data" is not in selected_input_ref_ids
    assert val_res.is_success
    assert len(val_res.errors) == 0


def test_producer_goal_with_unknown_ref_does_not_render_undefined_ref() -> None:
    """Verify that arbitrary string content in producer_goal does not trigger undefined ref errors during validation."""  # noqa: E501
    target_ref = SelectableRef(
        ref_id="required_output:w_main:required_output_context::draft",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name="draft",
        display_label="draft",
        worker_id="w_main",
    )
    refset = _refset(refs=(target_ref,))

    raw = json.dumps(
        {
            "target_construct_type": "REQUIRED_OUTPUT",
            "target_slot_name": "producer",
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::draft",
                "selected_input_ref_ids": [],
                "producer_goal": "Use whatever is in project_data and other context.",
            },
            "materialization_plan_id": "stage7.step_producer_repair.v1",
        }
    )
    res = parse_raw_intent(
        raw, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert res.is_success
    intent = res.intent
    assert intent is not None

    val_res = IntentValidator.validate(intent, refset, _catalog_entry())
    assert val_res.is_success
    assert len(val_res.errors) == 0


def test_payload_hallucinated_refs_and_top_level_valid_refs_must_fail() -> None:
    """Verify that validation or parsing fails when payload has hallucinated refs even if top-level has valid ones."""  # noqa: E501
    target_ref = SelectableRef(
        ref_id="required_output:w_main:required_output_context::draft",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name="draft",
        display_label="draft",
        worker_id="w_main",
    )
    refset = _refset(refs=(target_ref,))

    # Case A: Top-level target_ref_id differs from payload target_output_ref_id (fails parsing/mismatch check)  # noqa: E501
    raw_mismatch = json.dumps(
        {
            "target_construct_type": "REQUIRED_OUTPUT",
            "target_slot_name": "producer",
            "target_ref_id": "required_output:w_main:required_output_context::draft",
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::hallucinated",  # noqa: E501
                "selected_input_ref_ids": [],
            },
            "materialization_plan_id": "stage7.step_producer_repair.v1",
        }
    )
    res_mismatch = parse_raw_intent(
        raw_mismatch, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert not res_mismatch.is_success
    assert any("does not match" in err for err in res_mismatch.errors)

    # Case B: Top-level selected_ref_ids differs from payload selected_input_ref_ids
    raw_sel_mismatch = json.dumps(
        {
            "target_construct_type": "REQUIRED_OUTPUT",
            "target_slot_name": "producer",
            "selected_ref_ids": ["variable:w_main:symbol_table:worker:valid_input"],
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::draft",
                "selected_input_ref_ids": [
                    "variable:w_main:symbol_table:worker:hallucinated_input"
                ],
            },
            "materialization_plan_id": "stage7.step_producer_repair.v1",
        }
    )
    res_sel_mismatch = parse_raw_intent(
        raw_sel_mismatch, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert not res_sel_mismatch.is_success
    assert any("do not match" in err for err in res_sel_mismatch.errors)

    # Case C: Parsing succeeded but payload has hallucinated target ref id (validation must check payload and fail)  # noqa: E501
    # Note: parsing will sync them, but validator will check payload and fail if target_ref_id is invalid  # noqa: E501
    raw_hallucinated = json.dumps(
        {
            "target_construct_type": "REQUIRED_OUTPUT",
            "target_slot_name": "producer",
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::hallucinated",  # noqa: E501
                "selected_input_ref_ids": [],
            },
            "materialization_plan_id": "stage7.step_producer_repair.v1",
        }
    )
    res_hallucinated = parse_raw_intent(
        raw_hallucinated, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert res_hallucinated.is_success
    intent = res_hallucinated.intent
    assert intent is not None
    assert intent.target_ref_id == "required_output:w_main:required_output_context::hallucinated"

    val_res = IntentValidator.validate(intent, refset, _catalog_entry())
    assert not val_res.is_success
    assert any("hallucinated" in err for err in val_res.errors)


def test_unknown_payload_field_must_fail() -> None:
    """Verify that parsing fails if payload contains unknown or forbidden fields."""
    raw = json.dumps(
        {
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::draft",
                "selected_input_ref_ids": [],
                "raw_variable_name": "project_data",  # unknown field
            },
            "materialization_plan_id": "stage7.step_producer_repair.v1",
        }
    )
    res = parse_raw_intent(
        raw, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert not res.is_success
    assert any("Forbidden or unknown field 'raw_variable_name'" in err for err in res.errors)


def test_catalog_entry_missing_plan_id_must_fail() -> None:
    """Verify that validation fails if the catalog entry is missing materialization_plan_id (no fallback)."""  # noqa: E501
    target_ref = SelectableRef(
        ref_id="required_output:w_main:required_output_context::draft",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name="draft",
        display_label="draft",
        worker_id="w_main",
    )
    refset = _refset(refs=(target_ref,))

    intent = ConstructRepairIntent(
        intent_id="int_1",
        issue_id="i1",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="x",
        target_slot_name="producer",
        target_ref_id="required_output:w_main:required_output_context::draft",
        selected_ref_ids=(),
        materialization_plan_id="stage7.step_producer_repair.v1",
    )

    # _catalog_entry(materialization_plan_id=None) sets materialization_plan_id to None on entry
    entry_missing = _catalog_entry(materialization_plan_id=None)
    val_res = IntentValidator.validate(intent, refset, entry_missing)
    assert not val_res.is_success
    assert any(
        "Catalog metadata missing: materialization_plan_id is not defined" in err
        for err in val_res.errors
    )


def test_catalog_entry_with_explicit_plan_allows_match() -> None:
    """Verify that validation succeeds when materialization_plan_id matches catalog entry's explicit plan."""  # noqa: E501
    target_ref = SelectableRef(
        ref_id="required_output:w_main:required_output_context::draft",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name="draft",
        display_label="draft",
        worker_id="w_main",
    )
    refset = _refset(refs=(target_ref,))

    intent = ConstructRepairIntent(
        intent_id="int_1",
        issue_id="i1",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="x",
        target_slot_name="producer",
        target_ref_id="required_output:w_main:required_output_context::draft",
        selected_ref_ids=(),
        materialization_plan_id="stage7.step_producer_repair.v1",
    )

    entry_with_plan = _catalog_entry(materialization_plan_id="stage7.step_producer_repair.v1")
    val_res = IntentValidator.validate(intent, refset, entry_with_plan)
    assert val_res.is_success
    assert len(val_res.errors) == 0


def test_unknown_top_level_field_must_fail() -> None:
    """Verify that parsing fails when an unknown top-level field is present in the raw json."""
    raw = json.dumps(
        {
            "raw_variable_name": "project_data",  # unknown top-level field
            "payload": {
                "target_output_ref_id": "required_output:w_main:required_output_context::draft",
                "selected_input_ref_ids": [],
            },
            "materialization_plan_id": "stage7.step_producer_repair.v1",
        }
    )
    res = parse_raw_intent(
        raw, "i1", "InsertProducerStep", "required_output.insert_or_bind_producer"
    )
    assert not res.is_success
    assert any(
        "Forbidden or unknown top-level field 'raw_variable_name'" in err for err in res.errors
    )


def test_affordance_id_must_match_catalog_entry() -> None:
    """Verify that validation fails if the intent affordance_id does not match the catalog entry."""
    target_ref = SelectableRef(
        ref_id="required_output:w_main:required_output_context::draft",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name="draft",
        display_label="draft",
        worker_id="w_main",
    )
    refset = _refset(refs=(target_ref,))

    intent = ConstructRepairIntent(
        intent_id="int_1",
        issue_id="i1",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",  # mismatches catalog affordance_id
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="x",
        target_slot_name="producer",
        target_ref_id="required_output:w_main:required_output_context::draft",
        selected_ref_ids=(),
        materialization_plan_id="stage7.step_producer_repair.v1",
    )

    entry = _catalog_entry(affordance_id="different.affordance")
    val_res = IntentValidator.validate(intent, refset, entry)
    assert not val_res.is_success
    assert any("affordance_id" in err and "does not match" in err for err in val_res.errors)


def test_target_construct_type_and_slot_must_match_catalog_entry() -> None:
    """Verify that validation fails if target_construct_type or target_slot_name mismatches the catalog entry."""  # noqa: E501
    target_ref = SelectableRef(
        ref_id="required_output:w_main:required_output_context::draft",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name="draft",
        display_label="draft",
        worker_id="w_main",
    )
    refset = _refset(refs=(target_ref,))

    # Case A: target_construct_type mismatches
    intent_construct_mismatch = ConstructRepairIntent(
        intent_id="int_1",
        issue_id="i1",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="DIFFERENT_CONSTRUCT_TYPE",  # mismatches REQUIRED_OUTPUT
        target_construct_id="x",
        target_slot_name="producer",
        target_ref_id="required_output:w_main:required_output_context::draft",
        selected_ref_ids=(),
        materialization_plan_id="stage7.step_producer_repair.v1",
    )
    entry = _catalog_entry()
    val_res = IntentValidator.validate(intent_construct_mismatch, refset, entry)
    assert not val_res.is_success
    assert any("construct_type" in err and "does not match" in err for err in val_res.errors)

    # Case B: target_slot_name mismatches
    intent_slot_mismatch = ConstructRepairIntent(
        intent_id="int_2",
        issue_id="i1",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="x",
        target_slot_name="different_slot",  # mismatches producer
        target_ref_id="required_output:w_main:required_output_context::draft",
        selected_ref_ids=(),
        materialization_plan_id="stage7.step_producer_repair.v1",
    )
    val_res2 = IntentValidator.validate(intent_slot_mismatch, refset, entry)
    assert not val_res2.is_success
    assert any("slot_name" in err and "does not match" in err for err in val_res2.errors)
