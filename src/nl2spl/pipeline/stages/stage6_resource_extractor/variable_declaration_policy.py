"""Stage6VariableDeclarationPolicy: deterministic SymbolTable admission gate.

This gate rejects variable candidates that lack declaration authority before
they enter ``ResourceRegistryIR`` or ``SymbolTable``. It is pure code: no LLM
calls, no variable-name blacklist, and no source-only fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from nl2spl.ir.resource_registry_ir import VariableSpec
from nl2spl.ir.variable_declaration_authority_ir import (
    DeclarationAuthorityRegistry,
)

RejectionReason = Literal[
    "control_clause_only",
    "read_context_only",
    "unbacked_step_variable",
    "inadmissible_candidate_io",
    "predicate_as_variable_without_declaration_authority",
    "missing_declaration_authority",
]

REJECTION_DESCRIPTIONS: dict[RejectionReason, str] = {
    "control_clause_only": (
        "Variable is supported only by control/guard clause text; "
        "not a declaration source."
    ),
    "read_context_only": (
        "Variable is supported only by read-only context; "
        "not a declaration source."
    ),
    "unbacked_step_variable": (
        "Variable has source='step' but no executable action output intent "
        "supports it."
    ),
    "inadmissible_candidate_io": (
        "Variable originates from candidate IO (llm_candidate_io) without "
        "explicit declaration authority."
    ),
    "predicate_as_variable_without_declaration_authority": (
        "Variable appears to be a boolean predicate derived from a guard "
        "clause; no declaration authority."
    ),
    "missing_declaration_authority": (
        "Variable has no source_span_ids, no contract_demand_id, and no "
        "explicit authority; cannot be admitted."
    ),
}


@dataclass
class VariableCandidateAudit:
    """Audit record for a single variable candidate decision."""

    variable_name: str
    accepted: bool
    reason: str
    rejection_reason: RejectionReason | None = None
    authority: str | None = None
    source: str = "unknown"
    data_type: str = "text"


@dataclass
class DeclarationEvidenceView:
    """Structured declaration evidence for the policy gate."""

    declared_input_names: set[str] = field(default_factory=set)
    declared_output_names: set[str] = field(default_factory=set)
    action_output_names: set[str] = field(default_factory=set)
    response_target_names: set[str] = field(default_factory=set)
    read_only_context_terms: set[str] = field(default_factory=set)


class Stage6VariableDeclarationPolicy:
    """Deterministic gate: admit or reject variable candidates."""

    def __init__(
        self,
        evidence: DeclarationEvidenceView,
        authority_registry: DeclarationAuthorityRegistry | None = None,
    ) -> None:
        self._evidence = evidence
        self._registry = authority_registry or DeclarationAuthorityRegistry()

    def evaluate(self, candidates: list[VariableSpec]) -> PolicyResult:
        """Evaluate candidates. No evidence means reject non-empty candidates."""
        accepted: list[VariableSpec] = []
        rejected: list[VariableCandidateAudit] = []

        for var in candidates:
            audit = self._evaluate_one(var)
            if audit.accepted:
                accepted.append(var)
            else:
                rejected.append(audit)

        return PolicyResult(accepted=accepted, rejected=rejected)

    def _evaluate_one(self, var: VariableSpec) -> VariableCandidateAudit:
        name = var.name
        source = var.source
        data_type = var.data_type

        authority = self._registry.authority_of(name)
        if authority is not None:
            if self._registry.is_admissible(name):
                return VariableCandidateAudit(
                    variable_name=name,
                    accepted=True,
                    reason=f"Authority: {authority}",
                    authority=authority,
                    source=source,
                    data_type=data_type,
                )
            rejection = self._rejection_for_authority(authority)
            return VariableCandidateAudit(
                variable_name=name,
                accepted=False,
                reason=REJECTION_DESCRIPTIONS[rejection],
                rejection_reason=rejection,
                authority=authority,
                source=source,
                data_type=data_type,
            )

        if name in self._evidence.declared_input_names:
            return VariableCandidateAudit(
                variable_name=name,
                accepted=True,
                reason="Declared input (adapter/contract).",
                authority="declared_input",
                source=source,
                data_type=data_type,
            )

        if name in self._evidence.declared_output_names:
            return VariableCandidateAudit(
                variable_name=name,
                accepted=True,
                reason="Declared output / required deliverable.",
                authority="declared_output",
                source=source,
                data_type=data_type,
            )

        if name in self._evidence.action_output_names:
            return VariableCandidateAudit(
                variable_name=name,
                accepted=True,
                reason="Explicit action output intent.",
                authority="explicit_action_output_intent",
                source=source,
                data_type=data_type,
            )

        if name in self._evidence.response_target_names:
            return VariableCandidateAudit(
                variable_name=name,
                accepted=True,
                reason="Confirmed response target.",
                authority="confirmed_response_target",
                source=source,
                data_type=data_type,
            )

        var_terms = _variable_terms(name, var.description, data_type)
        if var_terms & self._evidence.read_only_context_terms:
            if data_type == "boolean":
                return VariableCandidateAudit(
                    variable_name=name,
                    accepted=False,
                    reason=REJECTION_DESCRIPTIONS[
                        "predicate_as_variable_without_declaration_authority"
                    ],
                    rejection_reason=(
                        "predicate_as_variable_without_declaration_authority"
                    ),
                    authority="control_predicate_guess",
                    source=source,
                    data_type=data_type,
                )
            return VariableCandidateAudit(
                variable_name=name,
                accepted=False,
                reason=REJECTION_DESCRIPTIONS["control_clause_only"],
                rejection_reason="control_clause_only",
                authority="control_predicate_guess",
                source=source,
                data_type=data_type,
            )

        if source == "input":
            if (
                self._evidence.declared_input_names
                and name not in self._evidence.declared_input_names
            ):
                return VariableCandidateAudit(
                    variable_name=name,
                    accepted=False,
                    reason=REJECTION_DESCRIPTIONS["missing_declaration_authority"],
                    rejection_reason="missing_declaration_authority",
                    authority=None,
                    source=source,
                    data_type=data_type,
                )
            return VariableCandidateAudit(
                variable_name=name,
                accepted=True,
                reason="Input variable, no read-only contamination.",
                authority="input_variable_clean",
                source=source,
                data_type=data_type,
            )

        if source == "output":
            if (
                self._evidence.declared_output_names
                and name not in self._evidence.declared_output_names
            ):
                return VariableCandidateAudit(
                    variable_name=name,
                    accepted=False,
                    reason=REJECTION_DESCRIPTIONS["missing_declaration_authority"],
                    rejection_reason="missing_declaration_authority",
                    authority=None,
                    source=source,
                    data_type=data_type,
                )
            return VariableCandidateAudit(
                variable_name=name,
                accepted=True,
                reason="Output variable, no read-only contamination.",
                authority="output_variable_clean",
                source=source,
                data_type=data_type,
            )

        if source == "step":
            return VariableCandidateAudit(
                variable_name=name,
                accepted=False,
                reason=REJECTION_DESCRIPTIONS["unbacked_step_variable"],
                rejection_reason="unbacked_step_variable",
                authority=None,
                source=source,
                data_type=data_type,
            )

        return VariableCandidateAudit(
            variable_name=name,
            accepted=False,
            reason=REJECTION_DESCRIPTIONS["missing_declaration_authority"],
            rejection_reason="missing_declaration_authority",
            authority=None,
            source=source,
            data_type=data_type,
        )

    @staticmethod
    def _rejection_for_authority(authority: str) -> RejectionReason:
        if authority == "llm_candidate_io":
            return "inadmissible_candidate_io"
        if authority == "control_predicate_guess":
            return "predicate_as_variable_without_declaration_authority"
        if authority == "read_context_only":
            return "read_context_only"
        return "missing_declaration_authority"


@dataclass
class PolicyResult:
    """Result of running ``Stage6VariableDeclarationPolicy.evaluate()``."""

    accepted: list[VariableSpec]
    rejected: list[VariableCandidateAudit]

    @property
    def accepted_names(self) -> set[str]:
        return {v.name for v in self.accepted}

    @property
    def rejected_names(self) -> set[str]:
        return {r.variable_name for r in self.rejected}


def _variable_terms(name: str, description: str, data_type: str) -> set[str]:
    """Extract lowercase terms for read-only-context comparison."""
    terms: set[str] = set()
    terms.update(name.lower().replace("_", " ").split())
    terms.update(description.lower().split()[:6])
    if data_type == "boolean":
        terms.add("whether")
    return terms
