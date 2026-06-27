"""Result contracts for repair-mode stage slices."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nl2spl.compiler.spl_editing.stage_slices.errors import StageSliceValidationError


def _assert_non_empty_str(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _to_tuple_of_strings(value: Any, field_name: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a sequence")
    result: list[str] = []
    for item in value:
        _assert_non_empty_str(item, field_name)
        result.append(item)
    if not allow_empty and not result:
        raise ValueError(f"{field_name} must not be empty")
    return tuple(result)


@dataclass(frozen=True)
class StageSliceResult:
    """Structured output from a repair-mode stage slice."""

    slice_id: str
    stage_authority: str
    policy_id: str
    changed_artifact_refs: tuple[str, ...]
    generated_construct_refs: tuple[str, ...]
    consumed_selected_ref_ids: tuple[str, ...]
    consumed_directive_id: str
    allocated_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    trace: dict[str, Any] = field(default_factory=dict)
    artifact_updates: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.slice_id, "slice_id")
        _assert_non_empty_str(self.stage_authority, "stage_authority")
        _assert_non_empty_str(self.policy_id, "policy_id")
        _assert_non_empty_str(self.consumed_directive_id, "consumed_directive_id")
        object.__setattr__(
            self,
            "changed_artifact_refs",
            _to_tuple_of_strings(self.changed_artifact_refs, "changed_artifact_refs"),
        )
        object.__setattr__(
            self,
            "generated_construct_refs",
            _to_tuple_of_strings(self.generated_construct_refs, "generated_construct_refs"),
        )
        object.__setattr__(
            self,
            "consumed_selected_ref_ids",
            _to_tuple_of_strings(self.consumed_selected_ref_ids, "consumed_selected_ref_ids"),
        )
        object.__setattr__(
            self,
            "allocated_ids",
            _to_tuple_of_strings(self.allocated_ids, "allocated_ids"),
        )
        object.__setattr__(
            self,
            "warnings",
            _to_tuple_of_strings(self.warnings, "warnings"),
        )
        forbidden_trace_keys = {"accepted", "overlay_event", "patched_snapshot"}
        if any(key in self.trace for key in forbidden_trace_keys):
            raise StageSliceValidationError(
                "StageSliceResult trace cannot carry accepted overlay authority."
            )