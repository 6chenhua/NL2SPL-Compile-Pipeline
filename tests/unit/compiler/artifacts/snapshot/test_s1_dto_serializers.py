"""S1 DTO serializer round-trip tests."""

from __future__ import annotations

import dataclasses

import pytest

from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
    SnapshotAcceptedPatchDTO,
    SnapshotOverlayEventDTO,
    SnapshotPromotionResolutionDTO,
    SnapshotVerificationRecordDTO,
)
from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    build_default_registry,
)


def _rt(registry, obj):
    data = registry.serialize(obj)
    restored = registry.deserialize(data)
    return data, restored


class TestOverlayEventDTORoundTrip:
    def test_full_roundtrip(self) -> None:
        reg = build_default_registry()
        dto = SnapshotOverlayEventDTO(
            overlay_id="ov-001",
            base_compile_run_id="run-001",
            base_artifact_snapshot_id="snap-001",
            overlay_version=1,
            patch_type="add_exception_handler_step",
            affordance_id="MISSING_HANDLER.ADD_HANDLER_STEP",
            patch_id="patch-001",
            accepted=True,
        )
        data, restored = _rt(reg, dto)
        assert data["$type"] == "SnapshotOverlayEventDTO"
        assert restored.overlay_id == dto.overlay_id
        assert restored.patch_type == dto.patch_type
        assert restored.accepted is True


class TestAcceptedPatchDTORoundTrip:
    def test_full_roundtrip(self) -> None:
        reg = build_default_registry()
        dto = SnapshotAcceptedPatchDTO(
            patch_id="patch-001",
            patch_type="add_exception_handler_step",
            affordance_id="MISSING_HANDLER.ADD_HANDLER_STEP",
            overlay_id="ov-001",
        )
        data, restored = _rt(reg, dto)
        assert data["$type"] == "SnapshotAcceptedPatchDTO"
        assert restored.patch_id == dto.patch_id


class TestVerificationRecordDTORoundTrip:
    def test_full_roundtrip(self) -> None:
        reg = build_default_registry()
        dto = SnapshotVerificationRecordDTO(
            verification_id="vrf-001",
            overlay_id="ov-001",
            lane="A",
            passed=True,
            diagnostic_count_before=3,
            diagnostic_count_after=1,
            error_messages=("missing_handler", "ambiguous_type"),
            metadata=(("irs_version", "1.0.0"), ("authority", "post_normalize_irs")),
        )
        data, restored = _rt(reg, dto)
        assert data["$type"] == "SnapshotVerificationRecordDTO"
        assert restored.verification_id == dto.verification_id
        assert restored.lane == "A"
        assert restored.passed is True
        # Tuple preservation
        assert isinstance(restored.error_messages, tuple)
        assert restored.error_messages == dto.error_messages
        assert isinstance(restored.metadata, tuple)
        assert restored.metadata == dto.metadata

    def test_empty_tuples_roundtrip(self) -> None:
        reg = build_default_registry()
        dto = SnapshotVerificationRecordDTO(
            verification_id="vrf-002",
            overlay_id="ov-002",
            lane="B",
            passed=False,
            diagnostic_count_before=0,
            diagnostic_count_after=0,
        )
        _data, restored = _rt(reg, dto)
        assert restored.error_messages == ()
        assert restored.metadata == ()

    def test_metadata_remains_tuple_after_roundtrip(self) -> None:
        """metadata must be tuple, not list, after deserialization."""
        reg = build_default_registry()
        dto = SnapshotVerificationRecordDTO(
            verification_id="vrf-003",
            overlay_id="ov-003",
            lane="A",
            passed=True,
            diagnostic_count_before=5,
            diagnostic_count_after=2,
            metadata=(("key1", "val1"),),
        )
        _data, restored = _rt(reg, dto)
        assert isinstance(restored.metadata, tuple)
        # Verify frozen (cannot mutate)

        with pytest.raises(dataclasses.FrozenInstanceError):
            restored.metadata = ()  # type: ignore[misc]


class TestPromotionResolutionDTORoundTrip:
    def test_full_roundtrip_preserves_closure_refs(self) -> None:
        reg = build_default_registry()
        dto = SnapshotPromotionResolutionDTO(
            marker_id="promotion_resolution:directive_1",
            target_worker_promotion_id="worker_promotion:candidate_1",
            resolved_diagnostic_group_id="worker_promotion_group:candidate_1",
            resolution_kind="defined_child_worker",
            normalized_directive_id="directive_1",
            materialized_construct_refs=("worker:w_child", "handoff:h_1", "step:w_main:s_1"),
            evidence_ref="ev_packet_1",
        )
        data, restored = _rt(reg, dto)
        assert data["$type"] == "SnapshotPromotionResolutionDTO"
        assert restored == dto
        assert isinstance(restored.materialized_construct_refs, tuple)
