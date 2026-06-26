"""SPL Construct Repair Materialization Framework."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.materialization.dependency_closure import (
    validate_dependency_closure,
)
from nl2spl.compiler.spl_editing.materialization.errors import (
    DependencyClosureValidationError,
    DuplicateMaterializationPlanError,
    MaterializationConsistencyError,
    MaterializationError,
    MaterializationPlanNotFoundError,
)
from nl2spl.compiler.spl_editing.materialization.id_allocator import IdAllocator
from nl2spl.compiler.spl_editing.materialization.model import (
    DependencyValidationResult,
    MaterializationDependencyClosure,
    MaterializationInput,
    MaterializationPlan,
    MaterializationRequest,
    MaterializationResult,
    RefRoleConstraint,
    RequiredArtifactField,
    WriteLayer,
)
from nl2spl.compiler.spl_editing.materialization.registry import (
    MaterializationPlanRegistry,
    Materializer,
    build_default_materialization_registry,
)
from nl2spl.compiler.spl_editing.materialization.service import RepairMaterializationService

__all__ = [
    "MaterializationError",
    "MaterializationPlanNotFoundError",
    "DuplicateMaterializationPlanError",
    "DependencyClosureValidationError",
    "MaterializationConsistencyError",
    "WriteLayer",
    "RefRoleConstraint",
    "RequiredArtifactField",
    "MaterializationDependencyClosure",
    "MaterializationPlan",
    "MaterializationRequest",
    "MaterializationInput",
    "MaterializationResult",
    "DependencyValidationResult",
    "IdAllocator",
    "validate_dependency_closure",
    "Materializer",
    "MaterializationPlanRegistry",
    "build_default_materialization_registry",
    "RepairMaterializationService",
]
