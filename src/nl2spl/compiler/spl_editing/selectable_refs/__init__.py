"""SelectableRef Foundation package."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.selectable_refs.audit import audit_refset_quality
from nl2spl.compiler.spl_editing.selectable_refs.builder import SelectableRefSetBuilder
from nl2spl.compiler.spl_editing.selectable_refs.errors import (
    SelectableRefCollisionError,
    SelectableRefError,
    SelectableRefNotFoundError,
    SelectableRefPolicyViolationError,
    SelectableRefRoleMismatchError,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import (
    ResolvedSelectableRef,
    SelectableRef,
    SelectableRefResolutionResult,
    SelectableRefSet,
)
from nl2spl.compiler.spl_editing.selectable_refs.policy import (
    SelectableRefPolicy,
    SelectableRefRoleRequirement,
    get_policy,
)
from nl2spl.compiler.spl_editing.selectable_refs.resolver import (
    resolve_ref_id,
    resolve_ref_ids,
    resolve_ref_ids_to_result,
)

__all__ = [
    "SelectableRef",
    "SelectableRefSet",
    "ResolvedSelectableRef",
    "SelectableRefResolutionResult",
    "SelectableRefPolicy",
    "SelectableRefRoleRequirement",
    "get_policy",
    "SelectableRefError",
    "SelectableRefNotFoundError",
    "SelectableRefRoleMismatchError",
    "SelectableRefPolicyViolationError",
    "SelectableRefCollisionError",
    "resolve_ref_id",
    "resolve_ref_ids",
    "resolve_ref_ids_to_result",
    "SelectableRefSetBuilder",
    "audit_refset_quality",
]
