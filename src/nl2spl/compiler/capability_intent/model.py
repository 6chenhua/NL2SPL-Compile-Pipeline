"""Typed artifacts for the external-capability intent lifecycle.

These artifacts deliberately separate non-authoritative early evidence,
post-ambiguity semantic candidates, and the resolver's final authority.
None of the types in this module are SPL grammar constructs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from nl2spl.ir.diagnostics import CompileDiagnostic

ClaimHint = Literal[
    "possible_boundary",
    "possible_identity",
    "possible_invocation",
    "adapter_declaration",
]
EvidenceOrigin = Literal["adapter", "stage1", "stage2_annotation"]
EvidenceClaim = Literal["boundary", "identity", "invocation", "operation"]
EvidenceRelation = Literal["direct", "normalized", "inferred"]


@dataclass(frozen=True)
class CapabilityEvidenceCandidateIR:
    """Source clue collected before semantic extraction.

    This artifact has no boundary, admission, or construct authority.
    """

    evidence_id: str
    source_span_id: str | None
    source_hint_ids: tuple[str, ...]
    surface_text: str
    claim_hint: ClaimHint
    origin: EvidenceOrigin
    source_section_id: str | None = None
    source_packet_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_span_id": self.source_span_id,
            "source_hint_ids": list(self.source_hint_ids),
            "surface_text": self.surface_text,
            "claim_hint": self.claim_hint,
            "origin": self.origin,
            "source_section_id": self.source_section_id,
            "source_packet_id": self.source_packet_id,
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass(frozen=True)
class EarlyCapabilityEvidenceView:
    """Deterministic, non-authoritative projection of source clues."""

    candidates: tuple[CapabilityEvidenceCandidateIR, ...] = ()
    rejected_evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidates": [item.to_payload() for item in self.candidates],
            "rejected_evidence_ids": list(self.rejected_evidence_ids),
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass(frozen=True)
class CapabilityEvidenceIR:
    """A source-anchored semantic claim emitted after Stage 3."""

    evidence_id: str
    source_span_id: str
    claim: EvidenceClaim
    surface_text: str
    relation: EvidenceRelation
    source_section_id: str | None = None
    source_packet_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_span_id": self.source_span_id,
            "claim": self.claim,
            "surface_text": self.surface_text,
            "relation": self.relation,
            "source_section_id": self.source_section_id,
            "source_packet_id": self.source_packet_id,
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass(frozen=True)
class ExternalCapabilityIntentCandidateIR:
    """Post-ambiguity semantic claims without admission authority."""

    candidate_id: str
    source_span_ids: tuple[str, ...]
    operation_surface: str
    operation_text: str
    capability_surface: str | None
    capability_ref_candidate: str | None
    boundary_claim: Literal["external", "candidate_external", "unresolved"]
    identity_claim: Literal[
        "explicit_name", "described_unnamed", "missing", "ambiguous"
    ]
    invocation_claim: Literal[
        "executable", "mention_only", "policy_only", "unresolved"
    ]
    evidence: tuple[CapabilityEvidenceIR, ...]
    source_section_id: str | None = None
    source_packet_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_span_ids": list(self.source_span_ids),
            "operation_surface": self.operation_surface,
            "operation_text": self.operation_text,
            "capability_surface": self.capability_surface,
            "capability_ref_candidate": self.capability_ref_candidate,
            "boundary_claim": self.boundary_claim,
            "identity_claim": self.identity_claim,
            "invocation_claim": self.invocation_claim,
            "evidence": [item.to_payload() for item in self.evidence],
            "source_section_id": self.source_section_id,
            "source_packet_id": self.source_packet_id,
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass(frozen=True)
class CapabilityExtractionDispositionIR:
    """Auditable outcome for every resolved span inspected by extraction."""

    source_span_id: str
    status: Literal[
        "candidate_emitted",
        "no_external_boundary",
        "policy_only",
        "insufficient_evidence",
        "rejected_invalid_evidence",
    ]
    related_candidate_ids: tuple[str, ...] = ()
    reason_code: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "source_span_id": self.source_span_id,
            "status": self.status,
            "related_candidate_ids": list(self.related_candidate_ids),
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class ExternalCapabilityExtractionResult:
    """Versioned Phase-B result, including explicit failure state."""

    candidates: tuple[ExternalCapabilityIntentCandidateIR, ...] = ()
    dispositions: tuple[CapabilityExtractionDispositionIR, ...] = ()
    diagnostics: tuple[CompileDiagnostic, ...] = ()
    status: Literal["available", "unavailable"] = "available"
    failure_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "failure_reason": self.failure_reason,
            "candidates": [item.to_payload() for item in self.candidates],
            "dispositions": [item.to_payload() for item in self.dispositions],
            "diagnostics": [_diagnostic_payload(item) for item in self.diagnostics],
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass(frozen=True)
class ExternalCapabilityIntentIR:
    """Resolver output and sole capability authority for ConstructPlan."""

    intent_id: str
    source_candidate_ids: tuple[str, ...]
    source_span_ids: tuple[str, ...]
    operation_text: str
    capability_surface: str | None
    capability_ref: str | None
    boundary_status: Literal[
        "confirmed_external", "candidate_external", "unresolved"
    ]
    identity_status: Literal[
        "explicit_name", "described_unnamed", "missing", "ambiguous"
    ]
    invocation_status: Literal[
        "executable", "mention_only", "policy_only", "unresolved"
    ]
    capability_admission_status: Literal[
        "confirmed_capability", "candidate_capability", "rejected"
    ]
    invocation_admission_status: Literal[
        "confirmed_invocation",
        "candidate_invocation",
        "no_invocation",
        "ambiguous_invocation",
    ]
    evidence: tuple[CapabilityEvidenceIR, ...]
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    binding_status: Literal[
        "fully_bound", "partially_bound", "unbound", "not_required"
    ] = "not_required"
    unresolved_binding_claims: tuple[str, ...] = ()
    source_section_id: str | None = None
    source_packet_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "source_candidate_ids": list(self.source_candidate_ids),
            "source_span_ids": list(self.source_span_ids),
            "operation_text": self.operation_text,
            "capability_surface": self.capability_surface,
            "capability_ref": self.capability_ref,
            "boundary_status": self.boundary_status,
            "identity_status": self.identity_status,
            "invocation_status": self.invocation_status,
            "capability_admission_status": self.capability_admission_status,
            "invocation_admission_status": self.invocation_admission_status,
            "evidence": [item.to_payload() for item in self.evidence],
            "input_refs": list(self.input_refs),
            "output_refs": list(self.output_refs),
            "binding_status": self.binding_status,
            "unresolved_binding_claims": list(self.unresolved_binding_claims),
            "source_section_id": self.source_section_id,
            "source_packet_id": self.source_packet_id,
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass(frozen=True)
class ExternalCapabilityIntentPlanIR:
    """Final capability plan with total candidate-to-intent coverage."""

    plan_id: str
    intents: tuple[ExternalCapabilityIntentIR, ...] = ()
    dispositions: tuple[CapabilityExtractionDispositionIR, ...] = ()
    candidate_resolution_map: Mapping[str, str | None] = field(default_factory=dict)
    diagnostics: tuple[CompileDiagnostic, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        candidate_ids = {
            candidate_id
            for intent in self.intents
            for candidate_id in intent.source_candidate_ids
        }
        mapped_ids = set(self.candidate_resolution_map)
        if candidate_ids - mapped_ids:
            missing = sorted(candidate_ids - mapped_ids)
            raise ValueError(f"candidate_resolution_map missing candidates: {missing}")
        intent_ids = {intent.intent_id for intent in self.intents}
        invalid_targets = sorted(
            target
            for target in self.candidate_resolution_map.values()
            if target is not None and target not in intent_ids
        )
        if invalid_targets:
            raise ValueError(
                "candidate_resolution_map references unknown intents: "
                f"{invalid_targets}"
            )
        for intent in self.intents:
            reverse = {
                candidate_id
                for candidate_id, target in self.candidate_resolution_map.items()
                if target == intent.intent_id
            }
            if reverse != set(intent.source_candidate_ids):
                raise ValueError(
                    f"intent {intent.intent_id} candidate mapping is not bidirectional"
                )

    def to_payload(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "intents": [item.to_payload() for item in self.intents],
            "dispositions": [item.to_payload() for item in self.dispositions],
            "candidate_resolution_map": {
                key: self.candidate_resolution_map[key]
                for key in sorted(self.candidate_resolution_map)
            },
            "diagnostics": [_diagnostic_payload(item) for item in self.diagnostics],
            "metadata": dict(sorted(self.metadata.items())),
        }


def _diagnostic_payload(diagnostic: CompileDiagnostic) -> dict[str, Any]:
    return {
        "diagnostic_id": diagnostic.diagnostic_id,
        "kind": diagnostic.kind,
        "severity": diagnostic.severity,
        "message": diagnostic.message,
        "target_ref": diagnostic.target_ref,
        "source_span_ids": list(diagnostic.source_span_ids),
        "metadata": dict(sorted((diagnostic.metadata or {}).items())),
        "blocks_rendering": diagnostic.blocks_rendering,
        "blocks_completion": diagnostic.blocks_completion,
    }
