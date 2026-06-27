"""Stale-preview validation for confirmed apply candidates."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.preview.errors import PreviewStaleError
from nl2spl.compiler.spl_editing.preview.model import (
    PreviewMaterializationResult,
    StageSliceTypedPlanRef,
)
from nl2spl.compiler.spl_editing.preview.store import PreviewStore


@dataclass(frozen=True)
class PreviewApplyExpectedState:
    """Expected preview identity fields for a confirmed apply candidate."""

    session_id: str
    issue_id: str
    base_snapshot_id: str
    intent_hash: str
    directive_hash: str
    closure_plan_hash: str
    selected_refset_id: str
    slice_typed_plan_hashes: tuple[StageSliceTypedPlanRef, ...]
    preview_construct_hashes: tuple[str, ...]
    llm_generation_config_hash: str

    def __post_init__(self) -> None:
        for field_name in (
            "session_id",
            "issue_id",
            "base_snapshot_id",
            "intent_hash",
            "directive_hash",
            "closure_plan_hash",
            "selected_refset_id",
            "llm_generation_config_hash",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be str")
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")

        typed_plan_hashes = tuple(self.slice_typed_plan_hashes)
        for ref in typed_plan_hashes:
            if not isinstance(ref, StageSliceTypedPlanRef):
                raise TypeError(
                    "slice_typed_plan_hashes must contain StageSliceTypedPlanRef"
                )
        object.__setattr__(self, "slice_typed_plan_hashes", typed_plan_hashes)

        construct_hashes = tuple(self.preview_construct_hashes)
        for value in construct_hashes:
            if not isinstance(value, str):
                raise TypeError("preview_construct_hashes must contain str values")
            if not value.strip():
                raise ValueError("preview_construct_hashes must not contain blanks")
        object.__setattr__(self, "preview_construct_hashes", construct_hashes)


def validate_preview_not_stale(
    store: PreviewStore,
    preview_id: str,
    expected: PreviewApplyExpectedState,
) -> PreviewMaterializationResult:
    """Return a stored preview only when it still matches the apply candidate.

    This function intentionally creates no evidence packet and writes no overlay state.
    It is the lifecycle boundary that confirmed apply must pass before creating
    user-confirmed repair evidence.
    """
    store.validate_applicable(
        preview_id,
        expected.session_id,
        expected.issue_id,
        expected.base_snapshot_id,
    )
    preview = store.get(preview_id)

    comparisons = {
        "base_snapshot_id": (preview.base_snapshot_id, expected.base_snapshot_id),
        "intent_hash": (preview.intent_hash, expected.intent_hash),
        "directive_hash": (preview.directive_hash, expected.directive_hash),
        "closure_plan_hash": (preview.closure_plan_hash, expected.closure_plan_hash),
        "selected_refset_id": (preview.selected_refset_id, expected.selected_refset_id),
        "slice_typed_plan_hashes": (
            preview.slice_typed_plan_hashes,
            expected.slice_typed_plan_hashes,
        ),
        "preview_construct_hashes": (
            preview.preview_construct_hashes,
            expected.preview_construct_hashes,
        ),
        "llm_generation_config_hash": (
            preview.llm_generation_config_hash,
            expected.llm_generation_config_hash,
        ),
    }
    for field_name, (actual, expected_value) in comparisons.items():
        if actual != expected_value:
            raise PreviewStaleError(
                f"Preview '{preview_id}' is stale: {field_name} mismatch."
            )

    return preview