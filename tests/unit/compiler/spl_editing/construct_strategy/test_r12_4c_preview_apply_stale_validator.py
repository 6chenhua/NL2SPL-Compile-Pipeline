"""Unit tests for Phase R12.4C preview apply stale validation."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.preview import (
    PreviewApplyExpectedState,
    PreviewMaterializationResult,
    PreviewStaleError,
    PreviewStore,
    PreviewStoreError,
    StageSliceTypedPlanRef,
    validate_preview_not_stale,
)


def _make_preview() -> PreviewMaterializationResult:
    return PreviewMaterializationResult(
        preview_id="prev_1",
        base_snapshot_id="snap_1",
        intent_hash="intent_h1",
        directive_hash="directive_h1",
        closure_plan_hash="closure_h1",
        selected_refset_id="refset_1",
        slice_typed_plan_hashes=(
            StageSliceTypedPlanRef(slice_id="stage5.block", typed_plan_hash="block_h1"),
            StageSliceTypedPlanRef(slice_id="stage7.command", typed_plan_hash="command_h1"),
        ),
        preview_construct_hashes=("construct_h1", "construct_h2"),
        llm_generation_config_hash="config_h1",
        rendered_preview="preview text",
    )


def _make_expected(**overrides) -> PreviewApplyExpectedState:
    values = {
        "session_id": "sess_1",
        "issue_id": "issue_1",
        "base_snapshot_id": "snap_1",
        "intent_hash": "intent_h1",
        "directive_hash": "directive_h1",
        "closure_plan_hash": "closure_h1",
        "selected_refset_id": "refset_1",
        "slice_typed_plan_hashes": (
            StageSliceTypedPlanRef(slice_id="stage5.block", typed_plan_hash="block_h1"),
            StageSliceTypedPlanRef(slice_id="stage7.command", typed_plan_hash="command_h1"),
        ),
        "preview_construct_hashes": ("construct_h1", "construct_h2"),
        "llm_generation_config_hash": "config_h1",
    }
    values.update(overrides)
    return PreviewApplyExpectedState(**values)


def _make_store(preview: PreviewMaterializationResult | None = None) -> PreviewStore:
    store = PreviewStore()
    store.put("sess_1", "issue_1", "snap_1", preview or _make_preview())
    return store


def test_preview_apply_validator_accepts_exact_matching_state() -> None:
    store = _make_store()

    preview = validate_preview_not_stale(store, "prev_1", _make_expected())

    assert preview.preview_id == "prev_1"
    assert preview.rendered_preview == "preview text"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("intent_hash", "intent_h2"),
        ("directive_hash", "directive_h2"),
        ("closure_plan_hash", "closure_h2"),
        ("selected_refset_id", "refset_2"),
        (
            "slice_typed_plan_hashes",
            (StageSliceTypedPlanRef(slice_id="stage5.block", typed_plan_hash="block_h2"),),
        ),
        ("preview_construct_hashes", ("construct_h3",)),
        ("llm_generation_config_hash", "config_h2"),
    ],
)
def test_preview_apply_validator_rejects_any_identity_drift(field_name: str, value) -> None:
    store = _make_store()

    with pytest.raises(PreviewStaleError, match=f"{field_name} mismatch"):
        validate_preview_not_stale(store, "prev_1", _make_expected(**{field_name: value}))


def test_preview_apply_validator_rejects_scope_mismatch_before_hash_checks() -> None:
    store = _make_store()

    with pytest.raises(PreviewStoreError, match="Session mismatch"):
        validate_preview_not_stale(
            store,
            "prev_1",
            _make_expected(session_id="other_session", intent_hash="intent_h2"),
        )


def test_preview_apply_validator_rejects_expired_preview() -> None:
    store = _make_store()
    store.expire("prev_1")

    with pytest.raises(PreviewStoreError, match="has been expired"):
        validate_preview_not_stale(store, "prev_1", _make_expected())


def test_preview_apply_validator_does_not_create_apply_authority() -> None:
    store = _make_store()

    preview = validate_preview_not_stale(store, "prev_1", _make_expected())

    assert not hasattr(preview, "evidence_packet")
    assert not hasattr(preview, "overlay_event")
    assert not hasattr(preview, "accepted")
    assert not hasattr(store, "overlay_event")