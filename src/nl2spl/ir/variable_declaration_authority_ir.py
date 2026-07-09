"""VariableDeclarationAuthority — declaration authority metadata for SymbolTable.

Every variable that enters SymbolTable must carry or resolve to a
declaration authority classification.  This module provides the types
and a sidecar pattern so authority can be attached to ContractFieldIR,
VariableSpec, VariableSymbol, and candidate IO without requiring a
full IR dataclass rewrite.

Design decision (S6V2.5): MVP uses a **sidecar** keyed by variable name
or (scope, name) rather than adding fields to every IR dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Authority literal
# ---------------------------------------------------------------------------

DeclarationAuthority = Literal[
    "adapter_hard_fact",
    "resource_contract_demand",
    "explicit_action_output_intent",
    "api_contract_response",
    "worker_handoff_binding",
    "request_input_value_target",
    "user_confirmed_repair",
    "llm_candidate_io",
    "control_predicate_guess",
    "read_context_only",
]

# ---------------------------------------------------------------------------
# Admissibility defaults
# ---------------------------------------------------------------------------

# Authorities that are admissible as SymbolTable variables by default.
ADMISSIBLE_AUTHORITIES: frozenset[DeclarationAuthority] = frozenset({
    "adapter_hard_fact",
    "resource_contract_demand",
    "explicit_action_output_intent",
    "request_input_value_target",
})

# Authorities that are admissible only with additional evidence.
CONDITIONALLY_ADMISSIBLE_AUTHORITIES: frozenset[DeclarationAuthority] = frozenset({
    "api_contract_response",
    "worker_handoff_binding",
    "user_confirmed_repair",
})

# Authorities that are NEVER admissible as SymbolTable variables.
INADMISSIBLE_AUTHORITIES: frozenset[DeclarationAuthority] = frozenset({
    "llm_candidate_io",
    "control_predicate_guess",
    "read_context_only",
})


def is_admissible_by_default(authority: DeclarationAuthority) -> bool:
    """Return True if this authority category is admissible without
    additional evidence checks."""
    return authority in ADMISSIBLE_AUTHORITIES


def is_conditionally_admissible(authority: DeclarationAuthority) -> bool:
    """Return True if this authority may be admissible with additional
    evidence (e.g. confirmed contract, admitted binding)."""
    return authority in CONDITIONALLY_ADMISSIBLE_AUTHORITIES


def is_inadmissible(authority: DeclarationAuthority) -> bool:
    """Return True if this authority can never admit a variable."""
    return authority in INADMISSIBLE_AUTHORITIES


# ---------------------------------------------------------------------------
# Sidecar
# ---------------------------------------------------------------------------


@dataclass
class DeclarationAuthoritySidecar:
    """Sidecar carrying declaration authority metadata for a variable.

    Stored separately from the main IR dataclass so we don't need to
    rewrite ContractFieldIR, VariableSpec, VariableSymbol, etc.

    Attributes:
        variable_name: Name of the variable this sidecar describes.
        declaration_authority: Classification of the authority source.
        admissible_as_symbol: Whether this variable may enter SymbolTable.
        evidence_role: Human-readable role label.
        source_span_ids: Span IDs that carry declaration evidence.
        source_section_id: Adapter section provenance.
        source_packet_id: Adapter packet provenance.
        contract_demand_id: Back-reference to a resource contract demand.
        producer_intent_id: Back-reference to an action output intent.
    """

    variable_name: str
    declaration_authority: DeclarationAuthority
    admissible_as_symbol: bool
    evidence_role: str
    source_span_ids: tuple[str, ...] = ()
    source_section_id: str | None = None
    source_packet_id: str | None = None
    contract_demand_id: str | None = None
    producer_intent_id: str | None = None

    def has_any_evidence(self) -> bool:
        """Return True if this sidecar has at least one evidence trace."""
        return bool(
            self.source_span_ids
            or self.source_section_id
            or self.source_packet_id
            or self.contract_demand_id
            or self.producer_intent_id
        )


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def sidecar_from_adapter_fact(
    name: str,
    data_type: str,
    source_section_id: str | None = None,
    source_packet_id: str | None = None,
    source_span_ids: tuple[str, ...] = (),
) -> DeclarationAuthoritySidecar:
    """Create a sidecar for an adapter hard fact variable."""
    return DeclarationAuthoritySidecar(
        variable_name=name,
        declaration_authority="adapter_hard_fact",
        admissible_as_symbol=True,
        evidence_role=f"adapter hard fact ({data_type})",
        source_span_ids=source_span_ids,
        source_section_id=source_section_id,
        source_packet_id=source_packet_id,
    )


def sidecar_from_resource_contract_demand(
    name: str,
    data_type: str,
    demand_id: str,
    source_span_ids: tuple[str, ...] = (),
    source_section_id: str | None = None,
    source_packet_id: str | None = None,
) -> DeclarationAuthoritySidecar:
    """Create a sidecar for a resource contract demand variable."""
    return DeclarationAuthoritySidecar(
        variable_name=name,
        declaration_authority="resource_contract_demand",
        admissible_as_symbol=True,
        evidence_role=f"resource contract demand ({data_type})",
        contract_demand_id=demand_id,
        source_span_ids=source_span_ids,
        source_section_id=source_section_id,
        source_packet_id=source_packet_id,
    )


def sidecar_from_action_output_intent(
    name: str,
    data_type: str,
    producer_intent_id: str | None = None,
    source_span_ids: tuple[str, ...] = (),
) -> DeclarationAuthoritySidecar:
    """Create a sidecar for an explicit action output intent variable."""
    return DeclarationAuthoritySidecar(
        variable_name=name,
        declaration_authority="explicit_action_output_intent",
        admissible_as_symbol=True,
        evidence_role=f"action output intent ({data_type})",
        producer_intent_id=producer_intent_id,
        source_span_ids=source_span_ids,
    )


def sidecar_from_candidate_io(
    name: str,
    data_type: str,
    source_span_ids: tuple[str, ...] = (),
) -> DeclarationAuthoritySidecar:
    """Create a sidecar for a Stage 3.5 candidate IO variable.

    IMPORTANT: candidate IO is NOT admissible by default.
    It only becomes admissible when upgraded by explicit evidence.
    """
    return DeclarationAuthoritySidecar(
        variable_name=name,
        declaration_authority="llm_candidate_io",
        admissible_as_symbol=False,
        evidence_role=f"candidate IO ({data_type})",
        source_span_ids=source_span_ids,
    )


def sidecar_from_worker_contract_field(
    field: object,  # ContractFieldIR — avoid circular import
) -> DeclarationAuthoritySidecar:
    """Create a sidecar from a ContractFieldIR.

    Worker contract fields default to llm_candidate_io unless the field
    carries explicit evidence (contract_demand_id, source_span_ids).
    """
    name: str = getattr(field, "name", "")
    data_type: str = getattr(field, "data_type", "text")
    demand_id: str | None = getattr(field, "contract_demand_id", None)
    span_ids: list[str] = getattr(field, "source_span_ids", []) or []
    section_id: str | None = getattr(field, "source_section_id", None)
    packet_id: str | None = getattr(field, "source_packet_id", None)

    if demand_id:
        # Contract field backed by a resource demand → admissible
        return sidecar_from_resource_contract_demand(
            name=name,
            data_type=data_type,
            demand_id=demand_id,
            source_span_ids=tuple(span_ids),
            source_section_id=section_id,
            source_packet_id=packet_id,
        )
    # Span/section/packet evidence alone is NOT declaration authority.
    # Explicit action output intent requires a producer_intent_id
    # (from Stage 7 typed relation plan) or resource contract demand.
    # Without these, the field is candidate IO → inadmissible.
    # No evidence → candidate IO, not admissible
    return sidecar_from_candidate_io(
        name=name,
        data_type=data_type,
        source_span_ids=tuple(span_ids),
    )


def sidecar_for_handoff_binding(
    name: str,
    data_type: str,
    admitted: bool = False,
) -> DeclarationAuthoritySidecar:
    """Create a sidecar for a worker handoff binding variable."""
    return DeclarationAuthoritySidecar(
        variable_name=name,
        declaration_authority="worker_handoff_binding",
        admissible_as_symbol=admitted,
        evidence_role=f"handoff binding ({data_type})",
    )


def sidecar_for_repair(
    name: str,
    data_type: str,
    source_span_ids: tuple[str, ...] = (),
) -> DeclarationAuthoritySidecar:
    """Create a sidecar for a user-confirmed SPL Editing repair variable."""
    return DeclarationAuthoritySidecar(
        variable_name=name,
        declaration_authority="user_confirmed_repair",
        admissible_as_symbol=True,
        evidence_role=f"user-confirmed repair ({data_type})",
        source_span_ids=source_span_ids,
    )


# ---------------------------------------------------------------------------
# Sidecar registry — keyed by variable name
# ---------------------------------------------------------------------------


@dataclass
class DeclarationAuthorityRegistry:
    """Registry of declaration authority sidecars.

    Keyed by variable name for simple lookup.  For worker-scoped paths,
    the key can be augmented with scope information at the call site.
    """

    sidecars: dict[str, DeclarationAuthoritySidecar] = field(default_factory=dict)

    def register(self, sidecar: DeclarationAuthoritySidecar) -> None:
        """Register a sidecar (last-write-wins for same name)."""
        self.sidecars[sidecar.variable_name] = sidecar

    def lookup(self, name: str) -> DeclarationAuthoritySidecar | None:
        """Look up a sidecar by variable name."""
        return self.sidecars.get(name)

    def is_admissible(self, name: str) -> bool:
        """Check whether a variable is admissible as a SymbolTable entry."""
        sc = self.sidecars.get(name)
        if sc is None:
            return False  # No authority → not admissible
        return sc.admissible_as_symbol

    def authority_of(self, name: str) -> DeclarationAuthority | None:
        """Get the authority classification for a variable."""
        sc = self.sidecars.get(name)
        return sc.declaration_authority if sc else None

    def register_from_contract_fields(
        self,
        fields: list[object],  # list[ContractFieldIR]
    ) -> None:
        """Bulk-register sidecars from a list of ContractFieldIR objects."""
        for field in fields:
            sc = sidecar_from_worker_contract_field(field)
            self.register(sc)

    def get_admissible_names(self) -> set[str]:
        """Return the set of variable names that are admissible."""
        return {name for name, sc in self.sidecars.items() if sc.admissible_as_symbol}

    def get_inadmissible_names(self) -> set[str]:
        """Return the set of variable names that are NOT admissible."""
        return {name for name, sc in self.sidecars.items() if not sc.admissible_as_symbol}
