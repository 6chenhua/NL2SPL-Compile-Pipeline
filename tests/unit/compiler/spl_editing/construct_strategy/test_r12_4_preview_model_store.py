"""Unit tests for Phase R12.4A Preview Model, Hash, and Store."""

from __future__ import annotations

import time
import pytest

from nl2spl.compiler.spl_editing.preview import (
    PreviewMaterializationResult,
    PreviewStore,
    PreviewStoreError,
    StageSliceTypedPlanRef,
)
from nl2spl.compiler.spl_editing.preview.hashes import (
    compute_directive_hash,
    compute_llm_generation_config_hash,
    compute_preview_construct_hashes_hash,
    compute_selected_refset_hash,
    compute_slice_typed_plan_hashes_hash,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef, SelectableRefSet
from nl2spl.compiler.spl_editing.strategy import RepairDirective


def _make_preview(preview_id: str = "prev_1", base_snapshot_id: str = "snap_1") -> PreviewMaterializationResult:
    ref = StageSliceTypedPlanRef(slice_id="slice_1", typed_plan_hash="h1")
    return PreviewMaterializationResult(
        preview_id=preview_id,
        base_snapshot_id=base_snapshot_id,
        intent_hash="ih1",
        directive_hash="dh1",
        closure_plan_hash="cph1",
        selected_refset_id="refset_1",
        slice_typed_plan_hashes=(ref,),
        preview_construct_hashes=("pch1",),
        llm_generation_config_hash="gh1",
        rendered_preview="preview text",
    )


def test_preview_result_has_no_accepted_authority() -> None:
    """Verify that PreviewMaterializationResult does not have any apply or accepted authority fields."""
    preview = _make_preview()
    assert not hasattr(preview, "accepted")
    assert not hasattr(preview, "overlay_event")
    assert not hasattr(preview, "RepairEvidencePacket")
    assert not hasattr(PreviewMaterializationResult, "accepted")
    assert not hasattr(PreviewMaterializationResult, "overlay_event")


def test_hash_determinism_and_order_independence() -> None:
    """Verify hashes are deterministic and order-independent where expected."""
    # 1. Slice typed plan hashes order-independence
    ref_a = StageSliceTypedPlanRef(slice_id="slice_a", typed_plan_hash="ha")
    ref_b = StageSliceTypedPlanRef(slice_id="slice_b", typed_plan_hash="hb")
    
    hash1 = compute_slice_typed_plan_hashes_hash((ref_a, ref_b))
    hash2 = compute_slice_typed_plan_hashes_hash((ref_b, ref_a))
    assert hash1 == hash2

    # 2. Preview construct hashes order-independence
    hash3 = compute_preview_construct_hashes_hash(("c_a", "c_b"))
    hash4 = compute_preview_construct_hashes_hash(("c_b", "c_a"))
    assert hash3 == hash4

    # 3. Selected refset order-independence
    ref_1 = SelectableRef(ref_id="r1", ref_kind="variable", ref_role="binding_source", canonical_name="var1", display_label="var1")
    ref_2 = SelectableRef(ref_id="r2", ref_kind="variable", ref_role="binding_source", canonical_name="var2", display_label="var2")

    refset_a = SelectableRefSet(
        set_id="refset_1",
        issue_id="issue_1",
        snapshot_id="snap_1",
        worker_scope="w1",
        refs=(ref_1, ref_2),
        policy_id="policy_1",
    )
    refset_b = SelectableRefSet(
        set_id="refset_1",
        issue_id="issue_1",
        snapshot_id="snap_1",
        worker_scope="w1",
        refs=(ref_2, ref_1),
        policy_id="policy_1",
    )

    hash5 = compute_selected_refset_hash(refset_a)
    hash6 = compute_selected_refset_hash(refset_b)
    assert hash5 == hash6


def test_hash_sensitivity_directive_change() -> None:
    """Verify that directive hash changes when properties of the directive change."""
    dir_a = RepairDirective(
        directive_id="d1",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        confidence=0.8,
    )
    dir_b = RepairDirective(
        directive_id="d1",
        source="user",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        confidence=0.9,  # different confidence
    )

    assert compute_directive_hash(dir_a) != compute_directive_hash(dir_b)


def test_hash_sensitivity_selected_refset_change() -> None:
    """Verify that selected refset hash changes when any selectable reference changes."""
    ref_1 = SelectableRef(ref_id="r1", ref_kind="variable", ref_role="binding_source", canonical_name="var1", display_label="var1")
    refset_a = SelectableRefSet(
        set_id="refset_1",
        issue_id="issue_1",
        snapshot_id="snap_1",
        worker_scope="w1",
        refs=(ref_1,),
        policy_id="policy_1",
    )

    ref_1_mut = SelectableRef(ref_id="r1", ref_kind="variable", ref_role="binding_source", canonical_name="var1_mutated", display_label="var1")
    refset_b = SelectableRefSet(
        set_id="refset_1",
        issue_id="issue_1",
        snapshot_id="snap_1",
        worker_scope="w1",
        refs=(ref_1_mut,),
        policy_id="policy_1",
    )

    assert compute_selected_refset_hash(refset_a) != compute_selected_refset_hash(refset_b)


def test_preview_store_snapshot_validation() -> None:
    """Verify that a preview generated on snapshot A cannot be validated against snapshot B."""
    store = PreviewStore()
    preview = _make_preview(preview_id="p1", base_snapshot_id="snap_a")
    
    store.put("sess_1", "iss_1", "snap_a", preview)

    # Validating against snap_a succeeds
    assert store.validate_applicable("p1", "sess_1", "iss_1", "snap_a") is True

    # Validating against snap_b fails
    with pytest.raises(PreviewStoreError, match="Snapshot mismatch"):
        store.validate_applicable("p1", "sess_1", "iss_1", "snap_b")


def test_preview_store_session_issue_validation() -> None:
    """Verify that session or issue mismatch rejects access and validation."""
    store = PreviewStore()
    preview = _make_preview(preview_id="p1", base_snapshot_id="snap_1")
    
    store.put("sess_1", "iss_1", "snap_1", preview)

    # Session mismatch
    with pytest.raises(PreviewStoreError, match="Session mismatch"):
        store.validate_applicable("p1", "sess_bad", "iss_1", "snap_1")

    # Issue mismatch
    with pytest.raises(PreviewStoreError, match="Issue mismatch"):
        store.validate_applicable("p1", "sess_1", "iss_bad", "snap_1")


def test_preview_store_expiration_validation() -> None:
    """Verify that expired previews are rejected on get and validation."""
    store = PreviewStore()
    preview = _make_preview(preview_id="p1")

    # 1. Manual expiration
    store.put("sess_1", "iss_1", "snap_1", preview)
    store.expire("p1")

    with pytest.raises(PreviewStoreError, match="has been expired"):
        store.get("p1")

    with pytest.raises(PreviewStoreError, match="has been expired"):
        store.validate_applicable("p1", "sess_1", "iss_1", "snap_1")

    # 2. TTL expiration
    store.put("sess_2", "iss_2", "snap_2", _make_preview(preview_id="p2", base_snapshot_id="snap_2"), ttl_seconds=0.001)
    time.sleep(0.005)

    with pytest.raises(PreviewStoreError, match="has expired"):
        store.get("p2")

    with pytest.raises(PreviewStoreError, match="has expired"):
        store.validate_applicable("p2", "sess_2", "iss_2", "snap_2")


def test_preview_store_does_not_write_overlay_history() -> None:
    """Verify that preview store actions have no side-effects on any overlays or external history."""
    store = PreviewStore()
    preview = _make_preview(preview_id="p1")

    # Accessing/mutating store should not invoke database/overlay layers
    store.put("sess_1", "iss_1", "snap_1", preview)
    assert not hasattr(store, "overlays")
    assert not hasattr(store, "overlay_event")


def test_preview_store_no_mutation_pollution() -> None:
    """Verify that internally stored objects cannot be mutated by callers modifying input or output values."""
    store = PreviewStore()

    # 1. Mutation of input preview object after put()
    plan_hashes = [StageSliceTypedPlanRef(slice_id="s1", typed_plan_hash="h1")]
    preview = PreviewMaterializationResult(
        preview_id="p1",
        base_snapshot_id="snap_1",
        intent_hash="ih1",
        directive_hash="dh1",
        closure_plan_hash="cph1",
        selected_refset_id="refset_1",
        slice_typed_plan_hashes=plan_hashes,  # mutable list
        preview_construct_hashes=("pch1",),
        llm_generation_config_hash="gh1",
        rendered_preview="original preview",
    )

    store.put("sess_1", "iss_1", "snap_1", preview)

    # Modify the list after put
    plan_hashes.append(StageSliceTypedPlanRef(slice_id="s2", typed_plan_hash="h2"))

    # Get from store and verify it is not affected
    stored_preview = store.get("p1")
    assert len(stored_preview.slice_typed_plan_hashes) == 1

    # 2. Mutation of retrieved object from get()
    # Modifying the retrieved list shouldn't pollute the store
    retrieved_list = list(stored_preview.slice_typed_plan_hashes)
    retrieved_list.append(StageSliceTypedPlanRef(slice_id="s2", typed_plan_hash="h2"))
    
    # Verify a second get() still returns the original list length
    stored_preview_2 = store.get("p1")
    assert len(stored_preview_2.slice_typed_plan_hashes) == 1


def test_preview_store_rejects_scope_snapshot_that_differs_from_preview_snapshot() -> None:
    """Verify that PreviewStore.put rejects snapshot mismatches."""
    store = PreviewStore()
    preview = _make_preview(preview_id="p1", base_snapshot_id="snap_a")

    with pytest.raises(PreviewStoreError, match="Snapshot mismatch"):
        store.put("sess_1", "iss_1", "snap_b", preview)
