"""Data models for SPL Editing Preview."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _to_tuple_of_strings(val: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(val, (list, tuple)):
        raise TypeError(
            f"Field '{field_name}' must be a sequence, got {type(val).__name__}"
        )
    res = []
    for item in val:
        if not isinstance(item, str):
            raise TypeError(
                f"Element in '{field_name}' must be str, got {type(item).__name__}"
            )
        res.append(item)
    return tuple(res)


def _assert_non_empty_str(val: Any, field_name: str) -> None:
    if not isinstance(val, str):
        raise TypeError(
            f"Field '{field_name}' must be str, got {type(val).__name__}"
        )
    if not val.strip():
        raise ValueError(f"Field '{field_name}' cannot be empty or blank")


@dataclass(frozen=True)
class StageSliceTypedPlanRef:
    """Ref to a single stage slice's typed plan hash."""

    slice_id: str
    typed_plan_hash: str

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.slice_id, "slice_id")
        _assert_non_empty_str(self.typed_plan_hash, "typed_plan_hash")


@dataclass(frozen=True)
class PreviewMaterializationResult:
    """Immutable preview result carrying stale detection hashes and rendered copy."""

    preview_id: str
    base_snapshot_id: str
    intent_hash: str
    directive_hash: str
    closure_plan_hash: str
    selected_refset_id: str
    slice_typed_plan_hashes: tuple[StageSliceTypedPlanRef, ...]
    preview_construct_hashes: tuple[str, ...]
    llm_generation_config_hash: str
    rendered_preview: str
    strategy_id: str = ""
    option_id: str = ""
    interaction_contract_hash: str = ""
    normalized_directive_hash: str = ""
    admitted_fact_hashes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _assert_non_empty_str(self.preview_id, "preview_id")
        _assert_non_empty_str(self.base_snapshot_id, "base_snapshot_id")
        _assert_non_empty_str(self.intent_hash, "intent_hash")
        _assert_non_empty_str(self.directive_hash, "directive_hash")
        _assert_non_empty_str(self.closure_plan_hash, "closure_plan_hash")
        _assert_non_empty_str(self.selected_refset_id, "selected_refset_id")
        _assert_non_empty_str(
            self.llm_generation_config_hash, "llm_generation_config_hash"
        )
        _assert_non_empty_str(self.rendered_preview, "rendered_preview")

        # Normalize tuples
        object.__setattr__(
            self,
            "preview_construct_hashes",
            _to_tuple_of_strings(
                self.preview_construct_hashes, "preview_construct_hashes"
            ),
        )
        object.__setattr__(
            self,
            "admitted_fact_hashes",
            _to_tuple_of_strings(self.admitted_fact_hashes, "admitted_fact_hashes"),
        )

        # Validate and normalize slice_typed_plan_hashes
        if not isinstance(self.slice_typed_plan_hashes, (list, tuple)):
            raise TypeError(
                "slice_typed_plan_hashes must be a sequence of StageSliceTypedPlanRef"
            )
        refs = []
        for ref in self.slice_typed_plan_hashes:
            if not isinstance(ref, StageSliceTypedPlanRef):
                raise TypeError(
                    "Element in slice_typed_plan_hashes must be "
                    f"StageSliceTypedPlanRef, got {type(ref).__name__}"
                )
            refs.append(ref)
        object.__setattr__(self, "slice_typed_plan_hashes", tuple(refs))
