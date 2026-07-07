"""Stable JSON serialization for repair drafting DTOs."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from typing import Any

from nl2spl.compiler.spl_editing.drafting.errors import RepairDraftSerializationError
from nl2spl.compiler.spl_editing.drafting.model import (
    DraftPreview,
    FieldInference,
    InferenceAlternative,
    InferenceTraceRecord,
    InferredRepairDraft,
    RepairClarificationQuestion,
    StoredRepairDraft,
    UserRepairFieldValue,
    UserRepairInput,
)
from nl2spl.compiler.spl_editing.drafting.values import (
    BusinessLogicValue,
    ExplicitNoneValue,
    NewOutputDraftValue,
    PlacementIntentValue,
    RepairFieldValue,
    ResponsibilityValue,
    ResultBindingValue,
    SelectedInputRefsValue,
)

_VALUE_TYPES = {
    "ResponsibilityValue": ResponsibilityValue,
    "BusinessLogicValue": BusinessLogicValue,
    "SelectedInputRefsValue": SelectedInputRefsValue,
    "NewOutputDraftValue": NewOutputDraftValue,
    "PlacementIntentValue": PlacementIntentValue,
    "ResultBindingValue": ResultBindingValue,
    "ExplicitNoneValue": ExplicitNoneValue,
}


def to_json_text(value: UserRepairInput | InferredRepairDraft | StoredRepairDraft) -> str:
    return json.dumps(
        to_json_data(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def to_json_data(value: Any) -> Any:
    if isinstance(value, tuple):
        return [to_json_data(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if is_dataclass(value):
        data = {field.name: to_json_data(getattr(value, field.name)) for field in fields(value)}
        if isinstance(
            value,
            (
                ResponsibilityValue,
                BusinessLogicValue,
                SelectedInputRefsValue,
                NewOutputDraftValue,
                PlacementIntentValue,
                ResultBindingValue,
                ExplicitNoneValue,
            ),
        ):
            data["value_type"] = type(value).__name__
        return data
    raise RepairDraftSerializationError(f"Unsupported serialization value {type(value).__name__}")


def user_input_from_json_text(text: str) -> UserRepairInput:
    return user_input_from_json_data(_loads(text))


def inferred_draft_from_json_text(text: str) -> InferredRepairDraft:
    return inferred_draft_from_json_data(_loads(text))


def stored_draft_from_json_text(text: str) -> StoredRepairDraft:
    return stored_draft_from_json_data(_loads(text))


def user_input_from_json_data(data: dict[str, Any]) -> UserRepairInput:
    _require_mapping(data)
    return UserRepairInput(
        input_mode=data["input_mode"],
        free_text=data.get("free_text"),
        field_values=tuple(
            UserRepairFieldValue(
                field_id=item["field_id"],
                value=_tuple_if_list(item.get("value")),
                source=item.get("source", "user"),
            )
            for item in data.get("field_values", ())
        ),
        selected_option_id=data.get("selected_option_id"),
        accepted_draft_id=data.get("accepted_draft_id"),
        draft_accepted=bool(data.get("draft_accepted", False)),
        materialized_preview_accepted=bool(data.get("materialized_preview_accepted", False)),
    )


def inferred_draft_from_json_data(data: dict[str, Any]) -> InferredRepairDraft:
    _require_mapping(data)
    return InferredRepairDraft(
        draft_id=data["draft_id"],
        issue_id=data["issue_id"],
        affordance_id=data["affordance_id"],
        strategy_id=data["strategy_id"],
        option_id=data["option_id"],
        fields=tuple(_field_from_json(item) for item in data.get("fields", ())),
        clarification_questions=tuple(
            _question_from_json(item) for item in data.get("clarification_questions", ())
        ),
        trace=tuple(_trace_from_json(item) for item in data.get("trace", ())),
        draft_preview=DraftPreview(
            title=data["draft_preview"]["title"],
            summary=data["draft_preview"]["summary"],
            field_summaries=tuple(data["draft_preview"].get("field_summaries", ())),
            warnings=tuple(data["draft_preview"].get("warnings", ())),
        ),
        schema_version=data.get("schema_version", "repair_drafting.v1"),
    )


def stored_draft_from_json_data(data: dict[str, Any]) -> StoredRepairDraft:
    _require_mapping(data)
    return StoredRepairDraft(
        draft_id=data["draft_id"],
        session_id=data["session_id"],
        artifact_snapshot_id=data["artifact_snapshot_id"],
        overlay_version=int(data["overlay_version"]),
        issue_id=data["issue_id"],
        option_id=data["option_id"],
        draft=inferred_draft_from_json_data(data["draft"]),
        created_at=data["created_at"],
        schema_version=data.get("schema_version", "repair_drafting.v1"),
    )


def _field_from_json(data: dict[str, Any]) -> FieldInference:
    return FieldInference(
        field_id=data["field_id"],
        value=_value_from_json(data.get("value")) if data.get("value") is not None else None,
        confidence=data["confidence"],
        evidence_refs=tuple(data.get("evidence_refs", ())),
        alternatives=tuple(_alternative_from_json(item) for item in data.get("alternatives", ())),
        blocking_reason=data.get("blocking_reason"),
    )


def _question_from_json(data: dict[str, Any]) -> RepairClarificationQuestion:
    return RepairClarificationQuestion(
        question_id=data["question_id"],
        field_id=data["field_id"],
        prompt=data["prompt"],
        options=tuple(_alternative_from_json(item) for item in data.get("options", ())),
        required=bool(data.get("required", True)),
    )


def _trace_from_json(data: dict[str, Any]) -> InferenceTraceRecord:
    return InferenceTraceRecord(
        field_id=data["field_id"],
        source=data["source"],
        evidence_refs=tuple(data.get("evidence_refs", ())),
        decision=data["decision"],
        confidence=data["confidence"],
        alternatives=tuple(data.get("alternatives", ())),
    )


def _alternative_from_json(data: dict[str, Any]) -> InferenceAlternative:
    return InferenceAlternative(
        label=data["label"],
        value=data["value"],
        confidence=data.get("confidence", "medium"),
    )


def _value_from_json(data: dict[str, Any]) -> RepairFieldValue:
    _require_mapping(data)
    value_type = data.get("value_type")
    cls = _VALUE_TYPES.get(value_type)
    if cls is None:
        raise RepairDraftSerializationError(f"Unknown RepairFieldValue type: {value_type}")
    clean = {key: _tuple_if_list(val) for key, val in data.items() if key != "value_type"}
    return cls(**clean)


def _tuple_if_list(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(value)
    return value


def _loads(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RepairDraftSerializationError(str(exc)) from exc
    _require_mapping(data)
    return data


def _require_mapping(data: Any) -> None:
    if not isinstance(data, dict):
        raise RepairDraftSerializationError("Expected JSON object")
