"""Exception types for ConstructClosurePlan."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError


class ClosurePlanError(SPLEditingError):
    """Exception related to ConstructClosurePlan creation or validation."""
