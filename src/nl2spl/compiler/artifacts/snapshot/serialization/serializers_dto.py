"""Serializers for S0 editing history DTOs.

These are the simplest serializers — no nested dataclasses, only
tuple<->list conversions for ``error_messages`` and ``metadata``.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
    SnapshotAcceptedPatchDTO,
    SnapshotOverlayEventDTO,
    SnapshotVerificationRecordDTO,
)
from nl2spl.compiler.artifacts.snapshot.serialization._canonical import (
    list_to_tuple,
    tuple_to_list,
)
from nl2spl.compiler.artifacts.snapshot.serialization.protocol import (
    ArtifactSerializer,
)
from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    SerializerRegistry,
)


class SnapshotOverlayEventDTOSerializer(ArtifactSerializer):
    type_id = "SnapshotOverlayEventDTO"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        dto: SnapshotOverlayEventDTO = obj
        return {
            "$type": self.type_id,
            "overlay_id": dto.overlay_id,
            "base_compile_run_id": dto.base_compile_run_id,
            "base_artifact_snapshot_id": dto.base_artifact_snapshot_id,
            "overlay_version": dto.overlay_version,
            "patch_type": dto.patch_type,
            "affordance_id": dto.affordance_id,
            "patch_id": dto.patch_id,
            "accepted": dto.accepted,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return SnapshotOverlayEventDTO(
            overlay_id=data["overlay_id"],
            base_compile_run_id=data["base_compile_run_id"],
            base_artifact_snapshot_id=data["base_artifact_snapshot_id"],
            overlay_version=data["overlay_version"],
            patch_type=data["patch_type"],
            affordance_id=data["affordance_id"],
            patch_id=data["patch_id"],
            accepted=data["accepted"],
        )


class SnapshotAcceptedPatchDTOSerializer(ArtifactSerializer):
    type_id = "SnapshotAcceptedPatchDTO"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        dto: SnapshotAcceptedPatchDTO = obj
        return {
            "$type": self.type_id,
            "patch_id": dto.patch_id,
            "patch_type": dto.patch_type,
            "affordance_id": dto.affordance_id,
            "overlay_id": dto.overlay_id,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return SnapshotAcceptedPatchDTO(
            patch_id=data["patch_id"],
            patch_type=data["patch_type"],
            affordance_id=data["affordance_id"],
            overlay_id=data["overlay_id"],
        )


class SnapshotVerificationRecordDTOSerializer(ArtifactSerializer):
    type_id = "SnapshotVerificationRecordDTO"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        dto: SnapshotVerificationRecordDTO = obj
        return {
            "$type": self.type_id,
            "verification_id": dto.verification_id,
            "overlay_id": dto.overlay_id,
            "lane": dto.lane,
            "passed": dto.passed,
            "diagnostic_count_before": dto.diagnostic_count_before,
            "diagnostic_count_after": dto.diagnostic_count_after,
            "error_messages": tuple_to_list(dto.error_messages),
            "metadata": [list(entry) for entry in dto.metadata],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        raw_metadata: list[list[str]] = data.get("metadata", [])
        metadata = tuple(tuple(entry) for entry in raw_metadata)
        return SnapshotVerificationRecordDTO(
            verification_id=data["verification_id"],
            overlay_id=data["overlay_id"],
            lane=data["lane"],
            passed=data["passed"],
            diagnostic_count_before=data["diagnostic_count_before"],
            diagnostic_count_after=data["diagnostic_count_after"],
            error_messages=list_to_tuple(data.get("error_messages", [])),
            metadata=metadata,
        )


def register_all(registry: SerializerRegistry) -> None:
    s1 = SnapshotOverlayEventDTOSerializer()
    s2 = SnapshotAcceptedPatchDTOSerializer()
    s3 = SnapshotVerificationRecordDTOSerializer()
    registry.register(s1)
    registry.register(s2)
    registry.register(s3)
    registry.register_for_class(SnapshotOverlayEventDTO, s1)
    registry.register_for_class(SnapshotAcceptedPatchDTO, s2)
    registry.register_for_class(SnapshotVerificationRecordDTO, s3)
