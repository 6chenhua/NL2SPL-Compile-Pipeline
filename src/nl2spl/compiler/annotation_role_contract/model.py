"""Canonical Annotation Role Contract model.

Defines the typed contract between ``semantic_role`` and compiler-facing
annotation fields.  This is the single source of truth for:

- ``field``
- ``route_family``
- ``construct_target``
- ``slot_target``
- ``executable``

``requiredness`` is intentionally ABSENT — it is independent tri-state
metadata from structural sources, not derived by role contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AnnotationRoleContract:
    """Deterministic mapping from ``semantic_role`` to compiler-facing fields.

    Every canonical semantic role MUST have exactly one contract.  Expected
    ``None`` is explicit — a role that must not carry ``construct_target``
    has ``construct_target=None`` in its contract, not a missing key.
    """

    semantic_role: str
    """Canonical semantic role (e.g. ``input_contract``, ``profile_domain``)."""

    field: str
    """Primary legacy field for backward compatibility."""

    route_family: str | None
    """Route family (e.g. ``resource_contract``, ``flow_relevant``).
    ``None`` means this role has no route family expectation."""

    construct_target: str | None
    """Target SPL construct (e.g. ``RESOURCE_CONTRACT``, ``EXCEPTION_FLOW``).
    ``None`` is an explicit contract: this role MUST NOT target a construct."""

    slot_target: str | None
    """Target slot within the construct (e.g. ``input``, ``condition``).
    ``None`` is an explicit contract: this role MUST NOT target a slot."""

    executable: bool
    """Whether annotations with this role may produce executable SPL."""

    llm_visible: bool = True
    """Whether this role is visible in LLM prompt schemas.

    Set ``False`` for internal / prior-only roles such as
    ``failure_condition`` that exist for route-prior resolution but
    must never appear in ``ALLOWED_SEMANTIC_ROLES``, prompt examples,
    or any other LLM-facing output schema.
    """

    materialization_authority: str = "annotation_role_contract"
    """Authority marker for downstream materialization stages."""

    notes: str | None = None
    """Human-readable rationale or migration note.

    This field carries NO machine semantics.  Visibility, executable
    state, and construct/slot expectations are all governed by typed
    fields on this dataclass — never by notes string matching.
    """


@dataclass(frozen=True)
class AnnotationRoleAlias:
    """Resolves a structural/legacy identifier to a canonical semantic role.

    Aliases are NOT confirmed semantic roles.  They must resolve to a
    canonical semantic role before contract lookup.  Structural aliases
    are NOT LLM-visible unless explicitly approved.
    """

    alias: str
    """The alias string (e.g. ``task_family``, ``policy``, ``runtime_input``)."""

    canonical_semantic_role: str
    """The canonical semantic role this alias resolves to."""

    source_kind: Literal["packet_type", "route_prior", "section_context", "legacy"]
    """Where this alias originates in the adapter/pipeline."""

    llm_visible: bool = False
    """Whether this alias may appear in LLM-facing prompt schemas.
    Default ``False`` — structural aliases are NOT prompt-visible."""
