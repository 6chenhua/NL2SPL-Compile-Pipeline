"""Provider-scoped typed values inferred by repair drafting providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from nl2spl.compiler.spl_editing.drafting.errors import RepairFieldValueScopeError


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _normalize_str_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} must be tuple[str, ...]")
    normalized: list[str] = []
    for item in values:
        _require_non_empty(item, field_name)
        normalized.append(item)
    return tuple(normalized)


@dataclass(frozen=True)
class ResponsibilityValue:
    provider_id: str
    text: str

    def __post_init__(self) -> None:
        _require_non_empty(self.provider_id, "provider_id")
        _require_non_empty(self.text, "text")


@dataclass(frozen=True)
class BusinessLogicValue:
    provider_id: str
    text: str

    def __post_init__(self) -> None:
        _require_non_empty(self.provider_id, "provider_id")
        _require_non_empty(self.text, "text")


@dataclass(frozen=True)
class SelectedInputRefsValue:
    provider_id: str
    ref_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.provider_id, "provider_id")
        object.__setattr__(self, "ref_ids", _normalize_str_tuple(self.ref_ids, "ref_ids"))


@dataclass(frozen=True)
class NewOutputDraftValue:
    provider_id: str
    local_id: str
    display_name: str
    semantic_description: str
    data_type_hint: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.provider_id, "provider_id")
        _require_non_empty(self.local_id, "local_id")
        _require_non_empty(self.display_name, "display_name")
        _require_non_empty(self.semantic_description, "semantic_description")
        if self.data_type_hint is not None:
            _require_non_empty(self.data_type_hint, "data_type_hint")


@dataclass(frozen=True)
class PlacementIntentValue:
    provider_id: str
    mode: Literal["append", "before", "after"]
    ref_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.provider_id, "provider_id")
        if self.mode not in {"append", "before", "after"}:
            raise ValueError(f"Unsupported placement mode: {self.mode}")
        if self.mode in {"before", "after"} and self.ref_id is None:
            raise ValueError("before/after placement requires ref_id")
        if self.ref_id is not None:
            _require_non_empty(self.ref_id, "ref_id")


@dataclass(frozen=True)
class ResultBindingValue:
    provider_id: str
    output_local_id: str
    parent_ref_id: str | None = None
    create_parent_local_temporary: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.provider_id, "provider_id")
        _require_non_empty(self.output_local_id, "output_local_id")
        if self.parent_ref_id is not None:
            _require_non_empty(self.parent_ref_id, "parent_ref_id")
        if bool(self.parent_ref_id) == bool(self.create_parent_local_temporary):
            raise ValueError("Choose exactly one result binding target mode")


@dataclass(frozen=True)
class ExplicitNoneValue:
    provider_id: str
    reason: str

    def __post_init__(self) -> None:
        _require_non_empty(self.provider_id, "provider_id")
        _require_non_empty(self.reason, "reason")


RepairFieldValue: TypeAlias = (
    ResponsibilityValue
    | BusinessLogicValue
    | SelectedInputRefsValue
    | NewOutputDraftValue
    | PlacementIntentValue
    | ResultBindingValue
    | ExplicitNoneValue
)


def assert_provider_scope(value: RepairFieldValue, expected_provider_id: str) -> None:
    """Reject typed values created for a different drafting provider."""

    if value.provider_id != expected_provider_id:
        raise RepairFieldValueScopeError(
            f"Value belongs to provider {value.provider_id}, expected {expected_provider_id}"
        )


def is_repair_field_value(value: object) -> bool:
    return isinstance(
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
    )
