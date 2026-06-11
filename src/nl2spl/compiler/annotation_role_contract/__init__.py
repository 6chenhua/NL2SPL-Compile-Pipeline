"""Annotation Role Contract — canonical role contract registry and model.

The single source of truth for mapping ``semantic_role`` → compiler-facing
annotation fields (``field``, ``route_family``, ``construct_target``,
``slot_target``, ``executable``).

Usage::

    from nl2spl.compiler.annotation_role_contract import (
        ROLE_CONTRACT_REGISTRY,
    )

    contract = ROLE_CONTRACT_REGISTRY.get_role_contract("input_contract")
    canonical = ROLE_CONTRACT_REGISTRY.resolve_semantic_role("task_family")
"""

from __future__ import annotations

from nl2spl.compiler.annotation_role_contract.diagnostics import (
    ANNOTATION_COVERAGE_GAP,
    ANNOTATION_INVALID_CONSTRUCT_TARGET_FOR_ROLE,
    ANNOTATION_INVALID_EXECUTABLE_FOR_ROLE,
    ANNOTATION_INVALID_FIELD_FOR_ROLE,
    ANNOTATION_INVALID_ROUTE_FAMILY_FOR_ROLE,
    ANNOTATION_INVALID_SLOT_TARGET_FOR_ROLE,
    ANNOTATION_LEGACY_FIELD_OVERRIDDEN_BY_ROLE_CONTRACT,
    ANNOTATION_MISSING_REQUIREDNESS,
    ANNOTATION_REJECTED_AFTER_ROLE_CONTRACT_VALIDATION,
    ANNOTATION_ROLE_CONTRACT_CONFLICT,
    AnnotationValidationDiagnostic,
)
from nl2spl.compiler.annotation_role_contract.model import (
    AnnotationRoleAlias,
    AnnotationRoleContract,
)
from nl2spl.compiler.annotation_role_contract.registry import (
    ROLE_CONTRACT_REGISTRY,
    AnnotationRoleContractRegistry,
)

__all__ = [
    # Registry
    "AnnotationRoleContractRegistry",
    "ROLE_CONTRACT_REGISTRY",
    # Model
    "AnnotationRoleContract",
    "AnnotationRoleAlias",
    # Diagnostic kinds
    "ANNOTATION_ROLE_CONTRACT_CONFLICT",
    "ANNOTATION_INVALID_FIELD_FOR_ROLE",
    "ANNOTATION_INVALID_ROUTE_FAMILY_FOR_ROLE",
    "ANNOTATION_INVALID_CONSTRUCT_TARGET_FOR_ROLE",
    "ANNOTATION_INVALID_SLOT_TARGET_FOR_ROLE",
    "ANNOTATION_INVALID_EXECUTABLE_FOR_ROLE",
    "ANNOTATION_MISSING_REQUIREDNESS",
    "ANNOTATION_REJECTED_AFTER_ROLE_CONTRACT_VALIDATION",
    "ANNOTATION_LEGACY_FIELD_OVERRIDDEN_BY_ROLE_CONTRACT",
    "ANNOTATION_COVERAGE_GAP",
    # Typed diagnostic model
    "AnnotationValidationDiagnostic",
]
