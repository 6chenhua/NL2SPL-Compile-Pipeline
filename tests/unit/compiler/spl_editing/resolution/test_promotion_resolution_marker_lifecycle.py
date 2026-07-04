from __future__ import annotations

from dataclasses import replace

from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
    SnapshotPromotionResolutionDTO,
)
from nl2spl.compiler.artifacts.snapshot.serialization.registry import build_default_registry
from nl2spl.compiler.spl_editing.resolution import (
    PromotionResolutionMarker,
    PromotionResolutionStore,
    validate_promotion_resolution_marker,
)

TARGET_REF = "worker_promotion:del_s31"


def _marker(**overrides) -> PromotionResolutionMarker:
    marker = PromotionResolutionMarker(
        marker_id="promotion_resolution:directive_1",
        target_worker_promotion_id=TARGET_REF,
        resolved_diagnostic_group_id="worker_promotion_group:del_s31",
        resolution_kind="defined_child_worker",
        normalized_directive_id="directive_1",
        materialized_construct_refs=("worker:w_child", "handoff:h_1"),
        evidence_ref="evidence_packet_1",
        repair_patch_id="patch_1",
        user_confirmed=True,
    )
    return replace(marker, **overrides)


def test_marker_validity_requires_exact_target_confirmed_patch_and_refs() -> None:
    assert validate_promotion_resolution_marker(_marker(), TARGET_REF).valid is True
    assert validate_promotion_resolution_marker(
        _marker(), TARGET_REF, expected_repair_patch_id="patch_1"
    ).valid is True

    assert validate_promotion_resolution_marker(
        _marker(user_confirmed=False), TARGET_REF
    ).reasons == ("not_user_confirmed",)
    assert validate_promotion_resolution_marker(
        _marker(repair_patch_id=""), TARGET_REF
    ).reasons == ("missing_repair_patch_id",)
    assert validate_promotion_resolution_marker(
        _marker(target_worker_promotion_id="worker_promotion:other"), TARGET_REF
    ).reasons == ("target_mismatch",)
    assert validate_promotion_resolution_marker(
        _marker(), TARGET_REF, expected_repair_patch_id="patch_2"
    ).reasons == ("repair_patch_mismatch",)
    assert validate_promotion_resolution_marker(
        _marker(materialized_construct_refs=()), TARGET_REF
    ).reasons == ("missing_materialized_construct_refs",)
    assert validate_promotion_resolution_marker(
        _marker(materialized_construct_refs=("worker:w_child", "worker:w_child")),
        TARGET_REF,
    ).reasons == ("duplicate_materialized_construct_refs",)


def test_store_valid_target_filters_invalid_markers() -> None:
    store = PromotionResolutionStore()
    store.put(_marker(marker_id="valid"))
    store.put(_marker(marker_id="unconfirmed", user_confirmed=False))
    store.put(_marker(marker_id="missing_patch", repair_patch_id=""))

    assert tuple(marker.marker_id for marker in store.find_target(TARGET_REF)) == (
        "valid",
        "unconfirmed",
        "missing_patch",
    )
    assert tuple(marker.marker_id for marker in store.find_valid_target(TARGET_REF)) == (
        "valid",
    )


def test_snapshot_promotion_resolution_dto_roundtrip_preserves_lifecycle_fields() -> None:
    registry = build_default_registry()
    dto = SnapshotPromotionResolutionDTO(
        marker_id="promotion_resolution:directive_1",
        target_worker_promotion_id=TARGET_REF,
        resolved_diagnostic_group_id="worker_promotion_group:del_s31",
        resolution_kind="defined_child_worker",
        normalized_directive_id="directive_1",
        materialized_construct_refs=("worker:w_child", "handoff:h_1"),
        evidence_ref="evidence_packet_1",
        repair_patch_id="patch_1",
        user_confirmed=True,
    )

    data = registry.serialize(dto)
    restored = registry.deserialize(data)

    assert data["repair_patch_id"] == "patch_1"
    assert data["user_confirmed"] is True
    assert restored == dto
