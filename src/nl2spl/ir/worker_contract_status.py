"""Shared helpers for contract / binding status determination.

Used by IRS checkers, validators, and materializers to consistently
interpret ``ContractSideStatus`` / ``BindingSideStatus`` values.  Each
call site should consume these helpers rather than hand-writing
``bool(list) or status == "known_empty"`` checks.
"""

from __future__ import annotations

from nl2spl.ir.worker_plan_ir import BindingSideStatus, ContractSideStatus


def contract_side_satisfied(
    fields: list, status: ContractSideStatus,
) -> bool:
    """Return True when the contract side can be considered satisfied.

    A side is satisfied when it has concrete fields OR has been
    explicitly confirmed empty.  ``unknown`` (default) means
    incomplete — it does NOT satisfy this predicate.
    """
    return bool(fields) or status == "known_empty"


def binding_side_satisfied(
    bindings: list, status: BindingSideStatus,
) -> bool:
    """Return True when the binding side can be considered satisfied.

    Same semantics as ``contract_side_satisfied`` but for handoff bindings.
    """
    return bool(bindings) or status == "known_empty"


def derive_contract_status(
    fields: list,
    *,
    declared_status: ContractSideStatus | None = None,
    source: str | None = None,
) -> ContractSideStatus:
    """Derive the canonical contract status from field evidence and an
    optional explicit declaration.

    Callers that have a structured reason to assert ``"known_empty"``
    (e.g. ``user_confirmed_repair``, ``adapter_hard_fact``,
    ``explicit_llm_schema_field``) must pass *declared_status* and a
    non-empty *source* string.  Status is NOT inferred from an empty
    field list alone.

    Priority:
    1. Non-empty *fields* → ``"known_present"``.
    2. Explicit ``declared_status="known_empty"`` + non-empty *source*
       → ``"known_empty"``.
    3. Otherwise → ``"unknown"``.
    """
    if fields:
        return "known_present"

    if declared_status == "known_empty":
        if isinstance(source, str) and source.strip():
            return "known_empty"
        import warnings as _warnings
        _warnings.warn(
            "derive_contract_status: declared_status='known_empty' but "
            "source is missing or empty; requires auditable source. "
            "Returning 'unknown'.",
            stacklevel=2,
        )
        return "unknown"

    if declared_status is not None and declared_status != "known_empty":
        import warnings as _warnings
        _warnings.warn(
            f"derive_contract_status: declared_status={declared_status!r} "
            f"but fields are empty; only 'known_empty' is accepted as an "
            f"explicit empty-side declaration. Returning 'unknown'.",
            stacklevel=2,
        )

    return "unknown"


def derive_handoff_materialization_status(
    *,
    input_bindings: list,
    output_bindings: list,
    input_status: BindingSideStatus,
    output_status: BindingSideStatus,
) -> str:
    """Derive the expected ``HandoffMaterializationStatus`` from both sides.

    Rules:
    - Input or output status ``"unknown"`` → ``"partial_contract_unknown"``.
    - Both sides ``"known_empty"`` with empty bindings → ``"confirmed_empty_contract"``.
    - At least one side ``"known_present"`` with non-empty bindings → ``"complete"``.
    - Otherwise → ``"partial_contract_unknown"``.
    """
    if input_status == "unknown" or output_status == "unknown":
        return "partial_contract_unknown"

    in_satisfied = binding_side_satisfied(input_bindings, input_status)
    out_satisfied = binding_side_satisfied(output_bindings, output_status)

    if not in_satisfied or not out_satisfied:
        return "partial_contract_unknown"

    if bool(input_bindings) or bool(output_bindings):
        return "complete"
    return "confirmed_empty_contract"


__all__ = [
    "binding_side_satisfied",
    "contract_side_satisfied",
    "derive_contract_status",
    "derive_handoff_materialization_status",
]
