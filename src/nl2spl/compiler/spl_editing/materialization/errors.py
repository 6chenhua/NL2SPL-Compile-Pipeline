"""Materialization framework exceptions."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError


class MaterializationError(SPLEditingError):
    """Base exception for all materialization errors."""


class MaterializationPlanNotFoundError(MaterializationError):
    """Raised when a requested materialization plan is not found in the registry."""


class DuplicateMaterializationPlanError(MaterializationError):
    """Raised when registering a plan with a duplicate plan_id."""


class DependencyClosureValidationError(MaterializationError):
    """Raised when dependency closure check constraints are not met."""


class MaterializationConsistencyError(MaterializationError):
    """Raised when tri-party or authority consistency checks fail."""
