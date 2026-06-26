"""Adapter from R1 ``SelectableRef`` to LLM context ``SelectableReference``.

Only refs with roles that the intent schema actually accepts are exposed.
For ``InsertProducerStepIntentPayload`` that means ``target_output`` and
``selectable_input`` only — ``source_evidence`` and other roles are
filtered out so the LLM is never prompted to use them.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.spl_editing.llm_context.model import (
    SelectableKind,
    SelectableReference,
)

# ---------------------------------------------------------------------------
# Mappings
# ---------------------------------------------------------------------------

_REF_KIND_TO_SELECTABLE_KIND: dict[str, SelectableKind] = {
    "variable": "variable",
    "worker_input": "variable",
    "step_output": "variable",
    "required_output": "output",
    "existing_step": "step",
    "exception_flow": "flow",
    "worker": "worker",
    "handoff": "handoff",
    "source_span": "variable",
    "resource": "resource",
}

_REF_ROLE_TO_PAYLOAD_FIELD: dict[str, str] = {
    "target_output": "target_output_ref_id",
    "selectable_input": "selected_input_ref_ids",
    "placement_anchor": "placement_hint_ref_id",
    "source_evidence": "source_evidence_ref_id",
}

# Only these roles are accepted by InsertProducerStepIntentPayload.
_ADAPTABLE_ROLES = frozenset({"target_output", "selectable_input"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def adapt_selectable_ref_to_llm(r1_ref: Any) -> SelectableReference:
    """Adapt one R1 ``SelectableRef`` to an LLM context ``SelectableReference``.

    Args:
        r1_ref: A ``SelectableRef`` from the R1 ``selectable_refs`` module.

    Returns:
        An LLM-ready ``SelectableReference`` whose ``id`` is the stable
        R1 ``ref_id``.
    """
    kind = _REF_KIND_TO_SELECTABLE_KIND.get(r1_ref.ref_kind, "variable")
    payload_field = _REF_ROLE_TO_PAYLOAD_FIELD.get(r1_ref.ref_role, "ref_id")

    return SelectableReference(
        id=r1_ref.ref_id,
        label=f"{r1_ref.ref_kind}:{r1_ref.ref_role}",
        summary=r1_ref.canonical_name,
        kind=kind,
        payload_field=payload_field,
        business_summary={
            "ref_kind": r1_ref.ref_kind,
            "ref_role": r1_ref.ref_role,
            "canonical_name": r1_ref.canonical_name,
            "worker_id": r1_ref.worker_id or "",
        },
    )


def adapt_refset_to_selectable_references(refset: Any) -> tuple[SelectableReference, ...]:
    """Adapt a full ``SelectableRefSet``, keeping only schema-allowed roles.

    Only refs whose ``ref_role`` is in ``_ADAPTABLE_ROLES`` are emitted.
    For ``InsertProducerStepIntentPayload`` this means ``target_output``
    and ``selectable_input``.  ``source_evidence`` and all other roles
    are silently dropped.
    """
    return tuple(
        adapt_selectable_ref_to_llm(ref) for ref in refset.refs if ref.ref_role in _ADAPTABLE_ROLES
    )
