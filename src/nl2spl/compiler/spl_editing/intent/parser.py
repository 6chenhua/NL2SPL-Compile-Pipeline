"""Parser for parsing raw LLM JSON suggestion into a ConstructRepairIntent."""

from __future__ import annotations

import json
from typing import Any

from nl2spl.compiler.spl_editing.intent.model import (
    AddExceptionHandlerStepIntentPayload,
    ConstructRepairIntent,
    InsertProducerStepIntentPayload,
    IntentParseResult,
)


def parse_raw_intent(
    raw_json: str,
    issue_id: str,
    patch_type: str,
    affordance_id: str,
) -> IntentParseResult:
    """Parse raw JSON payload from LLM into a ConstructRepairIntent, checking for forbidden fields."""  # noqa: E501
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return IntentParseResult(intent=None, errors=(f"Invalid JSON: {e}",), is_success=False)

    if not isinstance(data, dict):
        return IntentParseResult(intent=None, errors=("Expected JSON object.",), is_success=False)

    errors: list[str] = []

    # 1. Check for forbidden fields
    forbidden_keys = {
        "inputs",
        "outputs",
        "command_type",
        "step_id",
        "flow_ref",
        "block_ref",
        "handoff_id",
    }

    # Top-level check
    for key in forbidden_keys:
        if key in data:
            errors.append(f"Forbidden field '{key}' found at top-level of intent.")

    if patch_type in {"InsertProducerStep", "AddExceptionHandlerStep"}:
        allowed_top_keys = {
            "intent_id",
            "target_ref_id",
            "selected_ref_ids",
            "target_construct_type",
            "target_construct_id",
            "target_slot_name",
            "intent_summary",
            "repair_goal",
            "materialization_plan_id",
            "constraints",
            "payload",
        }
        for key in data:
            if key not in allowed_top_keys:
                errors.append(f"Forbidden or unknown top-level field '{key}' found in raw intent.")

    payload_data = data.get("payload")
    if payload_data is None:
        errors.append("Missing 'payload' field in raw intent.")
        return IntentParseResult(intent=None, errors=tuple(errors), is_success=False)

    if not isinstance(payload_data, dict):
        errors.append("Expected 'payload' to be a dictionary.")
        return IntentParseResult(intent=None, errors=tuple(errors), is_success=False)

    # Payload-level check
    for key in forbidden_keys:
        if key in payload_data:
            errors.append(f"Forbidden field '{key}' found in payload of intent.")

    if errors:
        return IntentParseResult(intent=None, errors=tuple(errors), is_success=False)

    # 2. Parse payload according to patch_type
    payload: Any = None
    if patch_type == "InsertProducerStep":
        # Strict schema for InsertProducerStepIntentPayload
        allowed_payload_keys = {
            "target_output_ref_id",
            "selected_input_ref_ids",
            "producer_goal",
            "placement_hint_ref_id",
            "notes_for_user",
        }
        for key in payload_data:
            if key not in allowed_payload_keys:
                errors.append(f"Forbidden or unknown field '{key}' found in payload of intent.")

        target_output_ref_id = payload_data.get("target_output_ref_id")
        if not target_output_ref_id:
            errors.append("Missing required payload field 'target_output_ref_id'.")

        selected_input_ref_ids = payload_data.get("selected_input_ref_ids", ())
        if not isinstance(selected_input_ref_ids, (list, tuple)):
            errors.append("Field 'selected_input_ref_ids' must be a list or tuple.")
            selected_input_ref_ids = ()

        payload = InsertProducerStepIntentPayload(
            target_output_ref_id=str(target_output_ref_id or ""),
            selected_input_ref_ids=tuple(str(x) for x in selected_input_ref_ids),
            producer_goal=str(payload_data.get("producer_goal") or ""),
            placement_hint_ref_id=payload_data.get("placement_hint_ref_id"),
            notes_for_user=payload_data.get("notes_for_user"),
        )
    elif patch_type == "AddExceptionHandlerStep":
        allowed_payload_keys = {
            "target_exception_flow_ref_id",
            "selected_input_ref_ids",
            "handler_goal",
            "notes_for_user",
        }
        for key in payload_data:
            if key not in allowed_payload_keys:
                errors.append(f"Forbidden or unknown field '{key}' found in payload of intent.")

        target_exception_flow_ref_id = payload_data.get("target_exception_flow_ref_id")
        if not target_exception_flow_ref_id:
            errors.append("Missing required payload field 'target_exception_flow_ref_id'.")

        selected_input_ref_ids = payload_data.get("selected_input_ref_ids", ())
        if not isinstance(selected_input_ref_ids, (list, tuple)):
            errors.append("Field 'selected_input_ref_ids' must be a list or tuple.")
            selected_input_ref_ids = ()

        payload = AddExceptionHandlerStepIntentPayload(
            target_exception_flow_ref_id=str(target_exception_flow_ref_id or ""),
            selected_input_ref_ids=tuple(str(x) for x in selected_input_ref_ids),
            handler_goal=str(payload_data.get("handler_goal") or ""),
            notes_for_user=payload_data.get("notes_for_user"),
        )
    else:
        payload = payload_data

    if errors:
        return IntentParseResult(intent=None, errors=tuple(errors), is_success=False)

    # 3. Construct ConstructRepairIntent DTO
    if patch_type == "InsertProducerStep":
        target_ref_id = payload.target_output_ref_id
        selected_ref_ids = payload.selected_input_ref_ids
        target_mismatch_message = (
            "Top-level target_ref_id does not match payload target_output_ref_id."
        )
    elif patch_type == "AddExceptionHandlerStep":
        target_ref_id = payload.target_exception_flow_ref_id
        selected_ref_ids = payload.selected_input_ref_ids
        target_mismatch_message = (
            "Top-level target_ref_id does not match payload target_exception_flow_ref_id."
        )
    else:
        target_ref_id = str(data.get("target_ref_id") or "")
        selected_ref_ids = tuple(str(x) for x in data.get("selected_ref_ids", ()))
        target_mismatch_message = "Top-level target_ref_id mismatch."

    if patch_type in {"InsertProducerStep", "AddExceptionHandlerStep"}:
        top_target_ref_id = data.get("target_ref_id")
        if top_target_ref_id is not None and str(top_target_ref_id) != target_ref_id:
            errors.append(target_mismatch_message)

        top_selected_ref_ids = data.get("selected_ref_ids")
        if top_selected_ref_ids is not None:
            top_sel_tuple = tuple(str(x) for x in top_selected_ref_ids)
            if top_sel_tuple != selected_ref_ids:
                errors.append(
                    "Top-level selected_ref_ids do not match payload selected_input_ref_ids."
                )

    if errors:
        return IntentParseResult(intent=None, errors=tuple(errors), is_success=False)

    intent = ConstructRepairIntent(
        intent_id=str(data.get("intent_id") or f"int_{issue_id}"),
        issue_id=issue_id,
        patch_type=patch_type,
        affordance_id=affordance_id,
        target_construct_type=str(data.get("target_construct_type") or ""),
        target_construct_id=str(data.get("target_construct_id") or ""),
        target_slot_name=str(data.get("target_slot_name") or ""),
        target_ref_id=target_ref_id,
        selected_ref_ids=selected_ref_ids,
        intent_summary=str(
            data.get("intent_summary")
            or (
                payload.producer_goal
                if hasattr(payload, "producer_goal")
                else (payload.handler_goal if hasattr(payload, "handler_goal") else "")
            )
        ),
        repair_goal=str(
            data.get("repair_goal")
            or (
                payload.producer_goal
                if hasattr(payload, "producer_goal")
                else (payload.handler_goal if hasattr(payload, "handler_goal") else "")
            )
        ),
        materialization_plan_id=data.get("materialization_plan_id"),
        constraints=tuple(str(x) for x in data.get("constraints", ())),
        payload=payload,
    )

    return IntentParseResult(intent=intent, errors=(), is_success=True)
