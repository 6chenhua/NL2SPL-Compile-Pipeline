"""Materialization plan and result DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent, RepairEvidencePacket
from nl2spl.compiler.spl_editing.materialization.id_allocator import IdAllocator
from nl2spl.compiler.spl_editing.selectable_refs.model import (
    ResolvedSelectableRef,
    SelectableRefSet,
)

WriteLayer = Literal[
    "worker_plan_pre_normalize",
    "worker_block_plan_pre_normalize",
    "worker_step_plan_pre_normalize",
    "worker_step_plan_post_normalize",
]


@dataclass(frozen=True)
class WriteLayerSpec:
    """Explicit mapping details for a write layer."""

    snapshot_field: str
    catalog_artifact: str


WRITE_LAYER_SPECS: dict[WriteLayer, WriteLayerSpec] = {
    "worker_plan_pre_normalize": WriteLayerSpec(
        snapshot_field="worker_plan",
        catalog_artifact="WorkerPlanIR",
    ),
    "worker_block_plan_pre_normalize": WriteLayerSpec(
        snapshot_field="worker_block_plan",
        catalog_artifact="WorkerBlockPlanIR",
    ),
    "worker_step_plan_pre_normalize": WriteLayerSpec(
        snapshot_field="worker_step_plan",
        catalog_artifact="WorkerStepPlanIR",
    ),
    "worker_step_plan_post_normalize": WriteLayerSpec(
        snapshot_field="worker_step_plan",
        catalog_artifact="WorkerStepPlanIR",
    ),
}


@dataclass(frozen=True)
class RefRoleConstraint:
    """Constraint on the number of selectable refs of a specific role."""

    role: str
    min_count: int
    max_count: int | None = None
    worker_scope: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize constraint to dict."""
        return {
            "role": self.role,
            "min_count": self.min_count,
            "max_count": self.max_count,
            "worker_scope": self.worker_scope,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RefRoleConstraint:
        """Deserialize constraint from dict."""
        return cls(
            role=data["role"],
            min_count=data["min_count"],
            max_count=data.get("max_count"),
            worker_scope=data.get("worker_scope"),
        )


@dataclass(frozen=True)
class RequiredArtifactField:
    """Declarative check path for fields within a specific artifact."""

    artifact_name: str
    field_path: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize field path to dict."""
        return {
            "artifact_name": self.artifact_name,
            "field_path": list(self.field_path),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequiredArtifactField:
        """Deserialize field path from dict."""
        return cls(
            artifact_name=data["artifact_name"],
            field_path=tuple(data["field_path"]),
        )


@dataclass(frozen=True)
class MaterializationDependencyClosure:
    """Dependency closure requirements for materialization."""

    required_artifacts: tuple[str, ...] = ()
    required_artifact_fields: tuple[RequiredArtifactField, ...] = ()
    required_ref_role_constraints: tuple[RefRoleConstraint, ...] = ()
    worker_scope_requirement: str | None = None
    required_id_allocator_namespaces: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize dependency closure to dict."""
        return {
            "required_artifacts": list(self.required_artifacts),
            "required_artifact_fields": [f.to_dict() for f in self.required_artifact_fields],
            "required_ref_role_constraints": [
                c.to_dict() for c in self.required_ref_role_constraints
            ],
            "worker_scope_requirement": self.worker_scope_requirement,
            "required_id_allocator_namespaces": list(self.required_id_allocator_namespaces),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MaterializationDependencyClosure:
        """Deserialize dependency closure from dict."""
        return cls(
            required_artifacts=tuple(data.get("required_artifacts", ())),
            required_artifact_fields=tuple(
                RequiredArtifactField.from_dict(f) for f in data.get("required_artifact_fields", ())
            ),
            required_ref_role_constraints=tuple(
                RefRoleConstraint.from_dict(c)
                for c in data.get("required_ref_role_constraints", ())
            ),
            worker_scope_requirement=data.get("worker_scope_requirement"),
            required_id_allocator_namespaces=tuple(
                data.get("required_id_allocator_namespaces", ())
            ),
        )


@dataclass(frozen=True)
class MaterializationPlan:
    """Plan that defines how to materialize a repair intent."""

    materialization_plan_id: str
    patch_type: str
    target_construct_type: str
    target_slot_name: str
    stage_authority: str
    dependency_closure: MaterializationDependencyClosure
    editable_artifacts: tuple[str, ...]
    output_artifacts: tuple[str, ...]
    writes_to: tuple[WriteLayer, ...]
    normalizer_required: bool
    stage10_rebuild_required: bool
    verification_lane: str
    materializer_id: str

    def to_audit_metadata(self) -> dict[str, Any]:
        """Serialize plan metadata for auditing."""
        return {
            "materialization_plan_id": self.materialization_plan_id,
            "patch_type": self.patch_type,
            "target_construct_type": self.target_construct_type,
            "target_slot_name": self.target_slot_name,
            "stage_authority": self.stage_authority,
            "dependency_closure": self.dependency_closure.to_dict(),
            "editable_artifacts": list(self.editable_artifacts),
            "output_artifacts": list(self.output_artifacts),
            "writes_to": list(self.writes_to),
            "normalizer_required": self.normalizer_required,
            "stage10_rebuild_required": self.stage10_rebuild_required,
            "verification_lane": self.verification_lane,
            "materializer_id": self.materializer_id,
        }

    @classmethod
    def from_audit_metadata(cls, data: dict[str, Any]) -> MaterializationPlan:
        """Reconstruct MaterializationPlan from serialized audit metadata."""
        return cls(
            materialization_plan_id=data["materialization_plan_id"],
            patch_type=data["patch_type"],
            target_construct_type=data["target_construct_type"],
            target_slot_name=data["target_slot_name"],
            stage_authority=data["stage_authority"],
            dependency_closure=MaterializationDependencyClosure.from_dict(
                data["dependency_closure"]
            ),
            editable_artifacts=tuple(data["editable_artifacts"]),
            output_artifacts=tuple(data["output_artifacts"]),
            writes_to=tuple(data["writes_to"]),
            normalizer_required=data["normalizer_required"],
            stage10_rebuild_required=data["stage10_rebuild_required"],
            verification_lane=data["verification_lane"],
            materializer_id=data["materializer_id"],
        )


@dataclass(frozen=True)
class MaterializationRequest:
    """External request to materialize a repair."""

    snapshot: ArtifactSnapshot
    issue: EditableIssue
    target: RepairTarget
    catalog_entry: RepairCatalogEntry
    intent: ConstructRepairIntent
    refset: SelectableRefSet
    resolved_refs: tuple[ResolvedSelectableRef, ...]
    evidence_packet: RepairEvidencePacket


@dataclass(frozen=True)
class MaterializationInput:
    """Internal input passed to a specific materializer."""

    snapshot: ArtifactSnapshot
    issue: EditableIssue
    target: RepairTarget
    catalog_entry: RepairCatalogEntry
    intent: ConstructRepairIntent
    refset: SelectableRefSet
    resolved_refs: tuple[ResolvedSelectableRef, ...]
    evidence_packet: RepairEvidencePacket
    plan: MaterializationPlan
    id_allocator: IdAllocator


@dataclass(frozen=True)
class MaterializationResult:
    """Result of materialization process."""

    patched_snapshot: ArtifactSnapshot
    overlay_event: Any
    changed_refs: tuple[str, ...]
    changed_step_ids: tuple[str, ...]
    changed_handoff_ids: tuple[str, ...]
    evidence_refs: tuple[Any, ...]
    materialization_plan_id: str
    materializer_id: str
    materialization_authority: str
    consumed_selected_ref_ids: tuple[str, ...]
    evidence_packet_id: str
    dependency_validation_metadata: dict[str, Any]
    stage_slice_results: tuple[Any, ...] = ()


@dataclass(frozen=True)
class DependencyValidationResult:
    """Outcome of dependency closure validation checks."""

    is_valid: bool
    errors: tuple[str, ...] = ()
    missing_artifacts: tuple[str, ...] = ()
    failed_constraints: tuple[str, ...] = ()
    validation_metadata: dict[str, Any] = field(default_factory=dict)
