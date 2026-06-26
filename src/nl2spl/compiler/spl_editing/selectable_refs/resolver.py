"""SelectableRef resolution and role/policy validation."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.selectable_refs.errors import (
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
from nl2spl.compiler.spl_editing.selectable_refs.policy import get_policy


def resolve_ref_id(refset: SelectableRefSet, ref_id: str) -> SelectableRef:
    """Resolve a SelectableRef by ID or raise SelectableRefNotFoundError."""
    ref = refset.get_ref(ref_id)
    if not ref:
        raise SelectableRefNotFoundError(
            f"SelectableRef with ID '{ref_id}' not found in SelectableRefSet '{refset.set_id}'"
        )
    return ref


def resolve_ref_ids(
    refset: SelectableRefSet,
    ref_ids: tuple[str, ...],
    expected_role: str,
) -> list[SelectableRef]:
    """Resolve multiple ref IDs and validate that each matches the expected role and policy rules."""  # noqa: E501
    results = []
    for ref_id in ref_ids:
        ref = resolve_ref_id(refset, ref_id)
        if ref.ref_role != expected_role:
            raise SelectableRefRoleMismatchError(
                f"SelectableRef '{ref_id}' has role '{ref.ref_role}', expected '{expected_role}'"
            )
        results.append(ref)

    policy = get_policy(refset.policy_id)
    if policy:
        policy.validate(refset, results, expected_role)

    return results


def resolve_ref_ids_to_result(
    refset: SelectableRefSet,
    ref_ids: tuple[str, ...],
    expected_role: str,
) -> SelectableRefResolutionResult:
    """Resolve multiple ref IDs into a structured SelectableRefResolutionResult.

    Catches validation and resolution errors, returning a success/error report.
    """
    resolved_list = []
    errors_list = []

    for ref_id in ref_ids:
        try:
            ref = resolve_ref_id(refset, ref_id)
            if ref.ref_role != expected_role:
                errors_list.append(
                    f"SelectableRef '{ref_id}' has role '{ref.ref_role}', expected '{expected_role}'"  # noqa: E501
                )
                continue

            scope_matched = (
                ref.worker_id is None
                or refset.worker_scope is None
                or ref.worker_id == refset.worker_scope
            )
            resolved_list.append(
                ResolvedSelectableRef(
                    ref=ref,
                    resolved_role=expected_role,
                    scope_matched=scope_matched,
                )
            )
        except SelectableRefNotFoundError as e:
            errors_list.append(str(e))

    if not errors_list:
        policy = get_policy(refset.policy_id)
        if policy:
            try:
                policy.validate(refset, [r.ref for r in resolved_list], expected_role)
            except SelectableRefPolicyViolationError as e:
                errors_list.append(str(e))

    is_success = len(errors_list) == 0
    return SelectableRefResolutionResult(
        resolved_refs=tuple(resolved_list) if is_success else (),
        errors=tuple(errors_list),
        is_success=is_success,
    )
