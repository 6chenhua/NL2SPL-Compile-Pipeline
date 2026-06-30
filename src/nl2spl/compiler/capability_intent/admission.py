"""Deterministic capability and invocation admission policy."""

from __future__ import annotations

from nl2spl.compiler.capability_intent.model import (
    CapabilityEvidenceIR,
    ExternalCapabilityIntentCandidateIR,
)


def capability_admission(
    candidate: ExternalCapabilityIntentCandidateIR,
) -> tuple[str, str]:
    """Return ``(boundary_status, capability_admission_status)``."""
    source_backed_boundary = any(
        item.claim == "boundary" and item.relation in {"direct", "normalized"}
        for item in candidate.evidence
    )
    identity_usable = candidate.identity_claim in {
        "explicit_name",
        "described_unnamed",
    }
    if (
        candidate.boundary_claim == "external"
        and source_backed_boundary
        and candidate.capability_surface
        and identity_usable
    ):
        return "confirmed_external", "confirmed_capability"
    if candidate.boundary_claim in {"external", "candidate_external"}:
        return "candidate_external", "candidate_capability"
    if candidate.boundary_claim == "unresolved":
        return "unresolved", "candidate_capability"
    return "unresolved", "rejected"


def invocation_admission(
    invocation_claim: str,
    evidence: tuple[CapabilityEvidenceIR, ...],
    capability_status: str,
) -> str:
    """Return invocation admission independently from resource binding."""
    if invocation_claim in {"mention_only", "policy_only"}:
        return "no_invocation"
    if invocation_claim == "unresolved":
        return "candidate_invocation"
    source_backed = any(
        item.claim == "invocation" and item.relation in {"direct", "normalized"}
        for item in evidence
    )
    if (
        invocation_claim == "executable"
        and source_backed
        and capability_status == "confirmed_capability"
    ):
        return "confirmed_invocation"
    return "candidate_invocation"
