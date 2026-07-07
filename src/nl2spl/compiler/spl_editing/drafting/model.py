"""Common DTOs for SPL Editing repair drafting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nl2spl.compiler.spl_editing.drafting.constants import DRAFT_SCHEMA_VERSION
from nl2spl.compiler.spl_editing.drafting.values import (
    RepairFieldValue,
    is_repair_field_value,
)

InputMode = Literal["none", "free_text", "structured_form", "mixed"]
Confidence = Literal["high", "medium", "low", "blocked"]


@dataclass(frozen=True)
class UserRepairFieldValue:
    field_id: str
    value: str | bool | int | float | None | tuple[str, ...]
    source: Literal["user", "accepted_default", "ui_selection"] = "user"

    def __post_init__(self) -> None:
        _require_non_empty(self.field_id, "field_id")
        if self.source not in {"user", "accepted_default", "ui_selection"}:
            raise ValueError(f"Unsupported field value source: {self.source}")
        if isinstance(self.value, tuple) and not all(isinstance(item, str) for item in self.value):
            raise TypeError("tuple UserRepairFieldValue values must contain only strings")


@dataclass(frozen=True)
class UserRepairInput:
    input_mode: InputMode
    free_text: str | None = None
    field_values: tuple[UserRepairFieldValue, ...] = ()
    selected_option_id: str | None = None
    accepted_draft_id: str | None = None
    draft_accepted: bool = False
    materialized_preview_accepted: bool = False

    def __post_init__(self) -> None:
        if self.input_mode not in {"none", "free_text", "structured_form", "mixed"}:
            raise ValueError(f"Unsupported input mode: {self.input_mode}")
        if self.free_text is not None and not isinstance(self.free_text, str):
            raise TypeError("free_text must be str or None")
        if not isinstance(self.field_values, tuple):
            raise TypeError("field_values must be tuple[UserRepairFieldValue, ...]")
        if not all(isinstance(item, UserRepairFieldValue) for item in self.field_values):
            raise TypeError("field_values must contain UserRepairFieldValue values")
        if self.selected_option_id is not None:
            _require_non_empty(self.selected_option_id, "selected_option_id")
        if self.accepted_draft_id is not None:
            _require_non_empty(self.accepted_draft_id, "accepted_draft_id")


@dataclass(frozen=True)
class InferenceAlternative:
    label: str
    value: str
    confidence: Confidence = "medium"

    def __post_init__(self) -> None:
        _require_non_empty(self.label, "label")
        _require_non_empty(self.value, "value")
        _validate_confidence(self.confidence)


@dataclass(frozen=True)
class FieldInference:
    field_id: str
    value: RepairFieldValue | None
    confidence: Confidence
    evidence_refs: tuple[str, ...] = ()
    alternatives: tuple[InferenceAlternative, ...] = ()
    blocking_reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.field_id, "field_id")
        _validate_confidence(self.confidence)
        if self.value is not None and not is_repair_field_value(self.value):
            raise TypeError("FieldInference.value must be a typed RepairFieldValue or None")
        object.__setattr__(
            self,
            "evidence_refs",
            _normalize_str_tuple(self.evidence_refs, "evidence_refs"),
        )
        if not isinstance(self.alternatives, tuple):
            raise TypeError("alternatives must be tuple[InferenceAlternative, ...]")
        if not all(isinstance(item, InferenceAlternative) for item in self.alternatives):
            raise TypeError("alternatives must contain InferenceAlternative values")


@dataclass(frozen=True)
class RepairClarificationQuestion:
    question_id: str
    field_id: str
    prompt: str
    options: tuple[InferenceAlternative, ...] = ()
    required: bool = True

    def __post_init__(self) -> None:
        _require_non_empty(self.question_id, "question_id")
        _require_non_empty(self.field_id, "field_id")
        _require_non_empty(self.prompt, "prompt")
        if not isinstance(self.options, tuple):
            raise TypeError("options must be tuple[InferenceAlternative, ...]")
        if not all(isinstance(item, InferenceAlternative) for item in self.options):
            raise TypeError("options must contain InferenceAlternative values")


@dataclass(frozen=True)
class InferenceTraceRecord:
    field_id: str
    source: str
    evidence_refs: tuple[str, ...]
    decision: str
    confidence: Confidence
    alternatives: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.field_id, "field_id")
        _require_non_empty(self.source, "source")
        _require_non_empty(self.decision, "decision")
        _validate_confidence(self.confidence)
        object.__setattr__(
            self,
            "evidence_refs",
            _normalize_str_tuple(self.evidence_refs, "evidence_refs"),
        )
        object.__setattr__(
            self,
            "alternatives",
            _normalize_str_tuple(self.alternatives, "alternatives"),
        )


@dataclass(frozen=True)
class DraftPreview:
    title: str
    summary: str
    field_summaries: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.title, "title")
        _require_non_empty(self.summary, "summary")
        object.__setattr__(
            self,
            "field_summaries",
            _normalize_str_tuple(self.field_summaries, "field_summaries"),
        )
        object.__setattr__(self, "warnings", _normalize_str_tuple(self.warnings, "warnings"))


@dataclass(frozen=True)
class InferredRepairDraft:
    draft_id: str
    issue_id: str
    affordance_id: str
    strategy_id: str
    option_id: str
    fields: tuple[FieldInference, ...]
    clarification_questions: tuple[RepairClarificationQuestion, ...]
    trace: tuple[InferenceTraceRecord, ...]
    draft_preview: DraftPreview
    schema_version: str = DRAFT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("draft_id", "issue_id", "affordance_id", "strategy_id", "option_id"):
            _require_non_empty(getattr(self, name), name)
        if not isinstance(self.fields, tuple):
            raise TypeError("fields must be tuple[FieldInference, ...]")
        if not all(isinstance(item, FieldInference) for item in self.fields):
            raise TypeError("fields must contain FieldInference values")
        if not isinstance(self.clarification_questions, tuple):
            raise TypeError(
                "clarification_questions must be tuple[RepairClarificationQuestion, ...]"
            )
        if not all(
            isinstance(item, RepairClarificationQuestion)
            for item in self.clarification_questions
        ):
            raise TypeError(
                "clarification_questions must contain RepairClarificationQuestion values"
            )
        if not isinstance(self.trace, tuple):
            raise TypeError("trace must be tuple[InferenceTraceRecord, ...]")
        if not all(isinstance(item, InferenceTraceRecord) for item in self.trace):
            raise TypeError("trace must contain InferenceTraceRecord values")
        if not isinstance(self.draft_preview, DraftPreview):
            raise TypeError("draft_preview must be DraftPreview")
        _require_non_empty(self.schema_version, "schema_version")


@dataclass(frozen=True)
class StoredRepairDraft:
    draft_id: str
    session_id: str
    artifact_snapshot_id: str
    overlay_version: int
    issue_id: str
    option_id: str
    draft: InferredRepairDraft
    created_at: str
    schema_version: str = DRAFT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "draft_id",
            "session_id",
            "artifact_snapshot_id",
            "issue_id",
            "option_id",
            "created_at",
            "schema_version",
        ):
            _require_non_empty(getattr(self, name), name)
        if not isinstance(self.overlay_version, int) or self.overlay_version < 0:
            raise ValueError("overlay_version must be a non-negative int")
        if not isinstance(self.draft, InferredRepairDraft):
            raise TypeError("draft must be InferredRepairDraft")


def _validate_confidence(value: Confidence) -> None:
    if value not in {"high", "medium", "low", "blocked"}:
        raise ValueError(f"Unsupported confidence: {value}")


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _normalize_str_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple[str, ...]")
    normalized = []
    for item in values:
        _require_non_empty(item, field_name)
        normalized.append(item)
    return tuple(normalized)
