"""Canonical Annotation Role Contract Registry.

The single source of truth for mapping ``semantic_role`` → compiler-facing
annotation fields.  Every canonical semantic role has exactly one contract;
expected ``None`` is explicit.

Structural aliases (``task_family``, ``policy``, etc.) are resolved to
canonical roles through a separate alias layer.  Aliases are NOT LLM-visible
unless explicitly approved.

Usage::

    from nl2spl.compiler.annotation_role_contract.registry import (
        ROLE_CONTRACT_REGISTRY,
    )

    contract = ROLE_CONTRACT_REGISTRY.get_role_contract("input_contract")
    canonical = ROLE_CONTRACT_REGISTRY.resolve_semantic_role("task_family")
    # canonical == "profile_domain"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from nl2spl.compiler.annotation_role_contract.model import (
    AnnotationRoleAlias,
    AnnotationRoleContract,
)

# ===========================================================================
# Internal: canonical role contracts
# ===========================================================================
# One entry per canonical semantic_role.  Expected None is explicit.
# Requiredness is intentionally absent.


def _build_contracts() -> dict[str, AnnotationRoleContract]:
    """Return the canonical role contract table."""

    def c(
        semantic_role: str,
        field: str,
        *,
        route_family: str | None = None,
        construct_target: str | None = None,
        slot_target: str | None = None,
        executable: bool = False,
        llm_visible: bool = True,
        notes: str | None = None,
    ) -> AnnotationRoleContract:
        return AnnotationRoleContract(
            semantic_role=semantic_role,
            field=field,
            route_family=route_family,
            construct_target=construct_target,
            slot_target=slot_target,
            executable=executable,
            llm_visible=llm_visible,
            notes=notes,
        )

    return {
        # ── profile / domain ─────────────────────────────────────────
        "profile_domain": c(
            "profile_domain",
            "domain",
            route_family="profile",
            executable=False,
            notes="profile_domain has no construct or slot; expected None is explicit",
        ),
        # ── resource contracts ───────────────────────────────────────
        "input_contract": c(
            "input_contract",
            "resources",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
        ),
        "output_contract": c(
            "output_contract",
            "resources",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="output",
            executable=False,
        ),
        # ── flow / behavior ──────────────────────────────────────────
        "process_step": c(
            "process_step",
            "behavior",
            route_family="flow_relevant",
            executable=True,
            notes="process_step has no construct or slot; expected None is explicit",
        ),
        "failure_mode": c(
            "failure_mode",
            "behavior",
            route_family="flow_relevant",
            construct_target="EXCEPTION_FLOW",
            slot_target="condition",
            executable=False,
        ),
        "failure_condition": c(
            "failure_condition",
            "behavior",
            route_family="flow_relevant",
            construct_target="EXCEPTION_FLOW",
            slot_target="condition",
            executable=False,
            llm_visible=False,
            notes="Internal prior role only; not exposed to LLM prompt schema.",
        ),
        "exception_handler_action": c(
            "exception_handler_action",
            "behavior",
            route_family="flow_relevant",
            construct_target="EXCEPTION_FLOW",
            slot_target="handler",
            executable=True,
        ),
        # ── delegation ───────────────────────────────────────────────
        "delegation_intent": c(
            "delegation_intent",
            "behavior",
            route_family="delegation_boundary",
            construct_target="WORKER_HANDOFF",
            slot_target="target",
            executable=False,
        ),
        "delegation_boundary_constraint": c(
            "delegation_boundary_constraint",
            "rules",
            route_family="delegation_boundary",
            construct_target="CONSTRAINT",
            slot_target="boundary",
            executable=False,
        ),
        "delegation_prohibition": c(
            "delegation_prohibition",
            "rules",
            route_family="delegation_boundary",
            construct_target="CONSTRAINT",
            slot_target="prohibition",
            executable=False,
        ),
        "worker_handoff_candidate": c(
            "worker_handoff_candidate",
            "behavior",
            route_family="delegation_boundary",
            construct_target="WORKER_HANDOFF",
            slot_target="target",
            executable=False,
        ),
        "handoff_condition": c(
            "handoff_condition",
            "rules",
            route_family="delegation_boundary",
            construct_target="WORKER_HANDOFF",
            slot_target="condition",
            executable=False,
        ),
        # ── constraints ──────────────────────────────────────────────
        "constraint": c(
            "constraint",
            "rules",
            route_family="constraint",
            executable=False,
            notes="constraint has no construct or slot; expected None is explicit",
        ),
        # ── integrations ─────────────────────────────────────────────
        "api_candidate": c(
            "api_candidate",
            "integrations",
            route_family="integration_candidate",
            construct_target="API_DECLARATION",
            slot_target="source_evidence",
            executable=False,
        ),
        "integration_hint": c(
            "integration_hint",
            "integrations",
            route_family="integration_candidate",
            construct_target="API_DECLARATION",
            slot_target="source_evidence",
            executable=False,
        ),
    }


# ===========================================================================
# Internal: structural aliases
# ===========================================================================


def _build_aliases() -> dict[str, AnnotationRoleAlias]:
    """Return the structural alias resolution table.

    Every alias MUST resolve to a canonical semantic role that exists in
    ``_build_contracts()``.  Aliases are NOT LLM-visible by default.
    """

    def a(
        alias: str,
        canonical: str,
        source_kind: str,
    ) -> AnnotationRoleAlias:
        return AnnotationRoleAlias(
            alias=alias,
            canonical_semantic_role=canonical,
            source_kind=source_kind,  # type: ignore[arg-type]
        )

    return {
        "task_family": a("task_family", "profile_domain", "packet_type"),
        "policy": a("policy", "constraint", "packet_type"),
        "exception_handler": a("exception_handler", "exception_handler_action", "route_prior"),
        "runtime_input": a("runtime_input", "input_contract", "packet_type"),
        "required_output": a("required_output", "output_contract", "packet_type"),
    }


# ===========================================================================
# Registry
# ===========================================================================


@dataclass(frozen=True)
class AnnotationRoleContractRegistry:
    """Canonical role contract registry.

    Provides the single source of truth for:
    - Role → compiler-field contract
    - Alias → canonical role resolution
    - Derived allowed-schema sets for prompt/validator consumers
    """

    _contracts: dict[str, AnnotationRoleContract] = field(
        default_factory=_build_contracts
    )
    _aliases: dict[str, AnnotationRoleAlias] = field(
        default_factory=_build_aliases
    )

    # -- role contract lookup -------------------------------------------------

    def get_role_contract(self, role: str) -> AnnotationRoleContract | None:
        """Return the contract for *role*, or ``None`` if unknown."""
        return self._contracts.get(role)

    def require_role_contract(self, role: str) -> AnnotationRoleContract:
        """Return the contract for *role*, raising ``KeyError`` if unknown."""
        contract = self._contracts.get(role)
        if contract is None:
            available = sorted(self._contracts.keys())
            raise KeyError(
                f"Unknown semantic_role {role!r}. "
                f"Available: {available}"
            )
        return contract

    def iter_contracts(self) -> Iterator[AnnotationRoleContract]:
        """Yield all canonical role contracts."""
        return iter(self._contracts.values())

    # -- alias resolution -----------------------------------------------------

    def resolve_semantic_role(self, role_or_alias: str) -> str | None:
        """Resolve *role_or_alias* to a canonical semantic role.

        - If *role_or_alias* is a canonical role → return it unchanged.
        - If *role_or_alias* is a known alias → return the canonical role.
        - Otherwise → return ``None``.
        """
        # Direct canonical match
        if role_or_alias in self._contracts:
            return role_or_alias
        # Alias lookup
        alias = self._aliases.get(role_or_alias)
        if alias is not None:
            return alias.canonical_semantic_role
        return None

    def get_alias(self, alias: str) -> AnnotationRoleAlias | None:
        """Return the alias entry for *alias*, or ``None``."""
        return self._aliases.get(alias)

    def iter_aliases(self) -> Iterator[AnnotationRoleAlias]:
        """Yield all alias entries."""
        return iter(self._aliases.values())

    # -- derived allowed-schema sets ------------------------------------------
    #
    # Two families of derived sets exist:
    #
    #   1. **Contract-derived sets** — reflect every contract in the registry,
    #      including internal roles.  These are the complete universe of
    #      valid compiler values.  Used for validation, normalization,
    #      and deterministic annotation construction.
    #
    #   2. **Prompt-visible sets** — subsets of the contract-derived sets
    #      that are safe to expose in LLM prompt schemas.  These EXCLUDE
    #      internal roles and INCLUDE legacy field values (``identity``,
    #      ``audience``) that no semantic role currently maps to but are
    #      part of the historical LLM output schema.
    #
    # ARC2 will source prompt constants from the prompt-visible APIs so
    # that the LLM schema remains byte-for-byte stable.

    # -- contract-derived sets (complete universe) -----------------------------

    def allowed_semantic_roles(self) -> frozenset[str]:
        """All canonical semantic roles (LLM-visible + internal).

        This is the complete set — every role that has a contract.
        """
        return frozenset(self._contracts.keys())

    def allowed_llm_semantic_roles(self) -> frozenset[str]:
        """Canonical semantic roles that are LLM-visible.

        Excludes internal/prior-only roles (e.g. ``failure_condition``)
        and structural aliases (e.g. ``task_family``, ``policy``).
        """
        # LLM-visible = all canonical roles MINUS internal-only roles
        internal = self.allowed_internal_prior_roles()
        return self.allowed_semantic_roles() - internal

    def allowed_internal_prior_roles(self) -> frozenset[str]:
        """Internal / prior-only semantic roles NOT visible to the LLM.

        These roles exist in the registry for route-prior / packet-type
        resolution but must never appear in LLM prompt schemas.

        Visibility is governed by the typed ``llm_visible`` field on
        ``AnnotationRoleContract``, NOT by notes string matching.
        """
        return frozenset({
            role
            for role, contract in self._contracts.items()
            if not contract.llm_visible
        })

    def allowed_fields(self) -> frozenset[str]:
        """All ``field`` values from canonical role contracts.

        This is the **contract-derived** set: the five fields that at
        least one semantic role maps to (``behavior``, ``domain``,
        ``integrations``, ``resources``, ``rules``).

        For the LLM-facing prompt schema, use :meth:`allowed_prompt_fields`
        which also includes ``identity`` and ``audience`` (legacy fields
        with no semantic role contract).
        """
        return frozenset(c.field for c in self._contracts.values())

    def allowed_construct_targets(self) -> frozenset[str]:
        """All valid ``construct_target`` values across all contracts.

        ``None`` is excluded — it is an explicit contract value, not an
        allowed-schema literal.
        """
        return frozenset(
            c.construct_target
            for c in self._contracts.values()
            if c.construct_target is not None
        ) | frozenset({"CALL_API"})

    def allowed_slot_targets(self) -> frozenset[str]:
        """All valid ``slot_target`` values across all contracts.

        ``None`` is excluded — it is an explicit contract value, not an
        allowed-schema literal.
        """
        return frozenset(
            c.slot_target
            for c in self._contracts.values()
            if c.slot_target is not None
        ) | frozenset({"call_action"})

    def non_executable_roles(self) -> frozenset[str]:
        """All roles whose contract specifies ``executable=False``.

        This is the **contract-derived** set: includes internal roles
        such as ``failure_condition`` that must not appear in LLM prompts.

        For the LLM-facing prompt schema, use :meth:`prompt_non_executable_roles`
        which excludes internal roles.
        """
        return frozenset(
            c.semantic_role
            for c in self._contracts.values()
            if not c.executable
        )

    def executable_roles(self) -> frozenset[str]:
        """All roles whose contract specifies ``executable=True``.

        This set is LLM-visible by construction (no internal role is
        executable), but :meth:`prompt_executable_roles` is available
        for symmetry and forward compatibility.
        """
        return frozenset(
            c.semantic_role
            for c in self._contracts.values()
            if c.executable
        )

    # -- prompt-visible sets (safe for LLM prompt schemas) ---------------------

    # Legacy fields that exist in the historical LLM output schema but
    # have no corresponding semantic role contract.  These must be
    # preserved in the prompt ``allowed_schema`` for backward compatibility.
    _LEGACY_PROMPT_FIELDS: frozenset[str] = frozenset({"identity", "audience"})

    def allowed_prompt_fields(self) -> frozenset[str]:
        """All ``field`` values for the LLM-facing prompt schema.

        Returns the contract-derived fields PLUS legacy fields
        (``identity``, ``audience``) that have no semantic role contract
        but are part of the historical LLM output schema.

        This is the set that should source ``ALLOWED_FIELDS``.
        """
        return self.allowed_fields() | self._LEGACY_PROMPT_FIELDS

    def prompt_non_executable_roles(self) -> frozenset[str]:
        """LLM-visible roles whose contract specifies ``executable=False``.

        Excludes internal roles (e.g. ``failure_condition``) that are not
        LLM-visible.  This is the set that should source
        ``NON_EXECUTABLE_ROLES``.
        """
        return self.non_executable_roles() & self.allowed_llm_semantic_roles()

    def prompt_executable_roles(self) -> frozenset[str]:
        """LLM-visible roles whose contract specifies ``executable=True``.

        This is the set that should source ``EXECUTABLE_ROLES``.
        """
        return self.executable_roles() & self.allowed_llm_semantic_roles()


# ===========================================================================
# Singleton instance
# ===========================================================================

ROLE_CONTRACT_REGISTRY = AnnotationRoleContractRegistry()
"""The canonical role contract registry singleton.

Import this instance for all role contract lookups::

    from nl2spl.compiler.annotation_role_contract.registry import (
        ROLE_CONTRACT_REGISTRY,
    )
"""
