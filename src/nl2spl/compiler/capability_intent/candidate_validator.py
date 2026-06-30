"""Programmatic source-anchor validation for Phase-B LLM output."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

from nl2spl.compiler.capability_intent.model import (
    CapabilityEvidenceIR,
    CapabilityExtractionDispositionIR,
    EarlyCapabilityEvidenceView,
    ExternalCapabilityIntentCandidateIR,
)
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.span_ir import SpanIR

SCHEMA_VERSION = "ExternalCapabilityIntentCandidateIR.v1"
NORMALIZER_VERSION = "CapabilitySurfaceNormalizerV1"

_TOP_FIELDS = {"candidates", "dispositions"}
_CANDIDATE_FIELDS = {
    "source_span_ids",
    "operation_surface",
    "capability_surface",
    "capability_ref_candidate",
    "boundary_claim",
    "identity_claim",
    "invocation_claim",
    "evidence",
}
_EVIDENCE_FIELDS = {"source_span_id", "claim", "surface_text", "relation"}
_DISPOSITION_FIELDS = {"source_span_id", "status", "reason_code"}
_BOUNDARY = {"external", "candidate_external", "unresolved"}
_IDENTITY = {"explicit_name", "described_unnamed", "missing", "ambiguous"}
_INVOCATION = {"executable", "mention_only", "policy_only", "unresolved"}
_CLAIMS = {"boundary", "identity", "invocation", "operation"}
_RELATIONS = {"direct", "normalized", "inferred"}
_DISPOSITIONS = {"no_external_boundary", "policy_only", "insufficient_evidence"}


@dataclass(frozen=True)
class CandidateValidationResult:
    candidates: tuple[ExternalCapabilityIntentCandidateIR, ...]
    dispositions: tuple[CapabilityExtractionDispositionIR, ...]
    diagnostics: tuple[CompileDiagnostic, ...]


class ExternalCapabilityCandidateValidator:
    """Reject unknown schema and candidates that cannot be source-anchored."""

    def validate(
        self,
        payload: dict[str, Any],
        spans: Iterable[SpanIR],
        early_evidence: EarlyCapabilityEvidenceView,
    ) -> CandidateValidationResult:
        spans_by_id = {span.span_id: span for span in spans}
        diagnostics: list[CompileDiagnostic] = []
        if not isinstance(payload, dict):
            raise ValueError("capability extractor payload must be an object")
        unknown_top = set(payload) - _TOP_FIELDS
        if unknown_top:
            raise ValueError(f"unknown capability payload fields: {sorted(unknown_top)}")
        raw_candidates = payload.get("candidates", [])
        raw_dispositions = payload.get("dispositions", [])
        if not isinstance(raw_candidates, list) or not isinstance(raw_dispositions, list):
            raise ValueError("candidates and dispositions must be arrays")

        candidates: list[ExternalCapabilityIntentCandidateIR] = []
        seen_ids: set[str] = set()
        for index, raw in enumerate(raw_candidates):
            try:
                candidate = self._candidate(raw, spans_by_id, early_evidence)
            except ValueError as exc:
                diagnostics.append(_invalid_candidate_diagnostic(index, raw, str(exc)))
                continue
            if candidate.candidate_id in seen_ids:
                diagnostics.append(
                    _invalid_candidate_diagnostic(
                        index, raw, "duplicate_candidate_identity"
                    )
                )
                continue
            seen_ids.add(candidate.candidate_id)
            candidates.append(candidate)

        candidate_ids_by_span: dict[str, list[str]] = {}
        for candidate in candidates:
            for span_id in candidate.source_span_ids:
                candidate_ids_by_span.setdefault(span_id, []).append(candidate.candidate_id)

        supplied_dispositions = self._dispositions(raw_dispositions, spans_by_id)
        dispositions: list[CapabilityExtractionDispositionIR] = []
        for span_id in sorted(spans_by_id, key=_span_sort_key):
            related = tuple(sorted(candidate_ids_by_span.get(span_id, [])))
            if related:
                dispositions.append(
                    CapabilityExtractionDispositionIR(
                        source_span_id=span_id,
                        status="candidate_emitted",
                        related_candidate_ids=related,
                    )
                )
                continue
            supplied = supplied_dispositions.get(span_id)
            dispositions.append(
                supplied
                if supplied is not None
                else CapabilityExtractionDispositionIR(
                    source_span_id=span_id,
                    status="insufficient_evidence",
                    reason_code="extractor_disposition_missing",
                )
            )

        return CandidateValidationResult(
            candidates=tuple(sorted(candidates, key=lambda item: item.candidate_id)),
            dispositions=tuple(dispositions),
            diagnostics=tuple(sorted(diagnostics, key=lambda item: item.diagnostic_id)),
        )

    def _candidate(
        self,
        raw: Any,
        spans_by_id: dict[str, SpanIR],
        early_evidence: EarlyCapabilityEvidenceView,
    ) -> ExternalCapabilityIntentCandidateIR:
        if not isinstance(raw, dict):
            raise ValueError("candidate must be an object")
        unknown = set(raw) - _CANDIDATE_FIELDS
        if unknown:
            raise ValueError(f"unknown candidate fields: {sorted(unknown)}")
        missing = _CANDIDATE_FIELDS - set(raw)
        if missing:
            raise ValueError(f"missing candidate fields: {sorted(missing)}")
        span_ids = _string_tuple(raw["source_span_ids"], "source_span_ids")
        if not span_ids or any(span_id not in spans_by_id for span_id in span_ids):
            raise ValueError("candidate references an unknown or empty span set")
        operation_surface = _required_string(raw["operation_surface"], "operation_surface")
        operation_relation = _surface_relation(operation_surface, span_ids, spans_by_id)
        if operation_relation is None:
            raise ValueError("operation_surface is not anchored to a referenced span")
        capability_surface = _optional_string(raw["capability_surface"], "capability_surface")
        if capability_surface is not None and _surface_relation(
            capability_surface, span_ids, spans_by_id
        ) is None:
            raise ValueError("capability_surface is not anchored to a referenced span")
        capability_ref = _optional_string(
            raw["capability_ref_candidate"], "capability_ref_candidate"
        )
        if capability_ref is not None and not _explicit_ref_anchored(
            capability_ref, span_ids, spans_by_id, early_evidence
        ):
            raise ValueError("capability_ref_candidate is not source-anchored")
        if raw["boundary_claim"] not in _BOUNDARY:
            raise ValueError("invalid boundary_claim")
        if raw["identity_claim"] not in _IDENTITY:
            raise ValueError("invalid identity_claim")
        if raw["invocation_claim"] not in _INVOCATION:
            raise ValueError("invalid invocation_claim")

        evidence = self._evidence(raw["evidence"], spans_by_id)
        required_claims = {"operation", "boundary"}
        if raw["identity_claim"] in {"explicit_name", "described_unnamed"}:
            required_claims.add("identity")
        if raw["invocation_claim"] != "unresolved":
            required_claims.add("invocation")
        evidence_claims = {item.claim for item in evidence}
        if not required_claims.issubset(evidence_claims):
            raise ValueError(
                f"missing claim evidence: {sorted(required_claims - evidence_claims)}"
            )

        candidate_id = _candidate_id(
            span_ids,
            operation_surface,
            capability_surface,
            capability_ref,
            raw["boundary_claim"],
            raw["identity_claim"],
            raw["invocation_claim"],
        )
        first_span = spans_by_id[span_ids[0]]
        return ExternalCapabilityIntentCandidateIR(
            candidate_id=candidate_id,
            source_span_ids=span_ids,
            operation_surface=operation_surface,
            operation_text=normalize_operation_text(operation_surface),
            capability_surface=capability_surface,
            capability_ref_candidate=capability_ref,
            boundary_claim=raw["boundary_claim"],
            identity_claim=raw["identity_claim"],
            invocation_claim=raw["invocation_claim"],
            evidence=evidence,
            source_section_id=first_span.source_section_id,
            source_packet_id=first_span.source_packet_id,
            metadata={
                "operation_anchor_relation": operation_relation,
                "normalizer_version": NORMALIZER_VERSION,
            },
        )

    def _evidence(
        self,
        raw_evidence: Any,
        spans_by_id: dict[str, SpanIR],
    ) -> tuple[CapabilityEvidenceIR, ...]:
        if not isinstance(raw_evidence, list) or not raw_evidence:
            raise ValueError("candidate evidence must be a non-empty array")
        result: list[CapabilityEvidenceIR] = []
        for raw in raw_evidence:
            if not isinstance(raw, dict):
                raise ValueError("evidence must be an object")
            unknown = set(raw) - _EVIDENCE_FIELDS
            if unknown or _EVIDENCE_FIELDS - set(raw):
                raise ValueError("evidence has unknown or missing fields")
            span_id = _required_string(raw["source_span_id"], "evidence.source_span_id")
            if span_id not in spans_by_id:
                raise ValueError("evidence references unknown span")
            if raw["claim"] not in _CLAIMS or raw["relation"] not in _RELATIONS:
                raise ValueError("evidence claim or relation is invalid")
            surface = _required_string(raw["surface_text"], "evidence.surface_text")
            actual_relation = _surface_relation(surface, (span_id,), spans_by_id)
            if actual_relation is None:
                raise ValueError("evidence surface is not source-anchored")
            span = spans_by_id[span_id]
            evidence_id = _evidence_id(span_id, raw["claim"], surface, raw["relation"])
            result.append(
                CapabilityEvidenceIR(
                    evidence_id=evidence_id,
                    source_span_id=span_id,
                    claim=raw["claim"],
                    surface_text=surface,
                    relation=raw["relation"],
                    source_section_id=span.source_section_id,
                    source_packet_id=span.source_packet_id,
                    metadata={"validated_anchor_relation": actual_relation},
                )
            )
        return tuple(sorted(result, key=lambda item: item.evidence_id))

    def _dispositions(
        self,
        raw_dispositions: list[Any],
        spans_by_id: dict[str, SpanIR],
    ) -> dict[str, CapabilityExtractionDispositionIR]:
        result: dict[str, CapabilityExtractionDispositionIR] = {}
        for raw in raw_dispositions:
            if not isinstance(raw, dict) or set(raw) - _DISPOSITION_FIELDS:
                continue
            if _DISPOSITION_FIELDS - set(raw):
                continue
            span_id = raw.get("source_span_id")
            status = raw.get("status")
            reason_code = raw.get("reason_code")
            if span_id not in spans_by_id or status not in _DISPOSITIONS:
                continue
            if reason_code is not None and not isinstance(reason_code, str):
                continue
            result[span_id] = CapabilityExtractionDispositionIR(
                source_span_id=span_id,
                status=status,
                reason_code=reason_code,
            )
        return result


def normalize_surface(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def normalize_operation_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).strip(" .,:;!?，。；：！？")


def _surface_relation(
    surface: str,
    span_ids: tuple[str, ...],
    spans_by_id: dict[str, SpanIR],
) -> str | None:
    if any(surface in spans_by_id[span_id].text for span_id in span_ids):
        return "direct"
    normalized_surface = normalize_surface(surface)
    if normalized_surface and any(
        normalized_surface in normalize_surface(spans_by_id[span_id].text)
        for span_id in span_ids
    ):
        return "normalized"
    return None


def _explicit_ref_anchored(
    ref: str,
    span_ids: tuple[str, ...],
    spans_by_id: dict[str, SpanIR],
    early_evidence: EarlyCapabilityEvidenceView,
) -> bool:
    if _surface_relation(ref, span_ids, spans_by_id) is not None:
        return True
    normalized_ref = normalize_surface(ref)
    return any(
        item.claim_hint == "adapter_declaration"
        and normalize_surface(item.surface_text) == normalized_ref
        for item in early_evidence.candidates
    )


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, field_name)


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be an array of strings")
    return tuple(dict.fromkeys(value))


def _candidate_id(*parts: Any) -> str:
    stable = "\x1f".join(
        "|".join(part) if isinstance(part, tuple) else str(part or "")
        for part in parts
    )
    return "cap_candidate_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]


def _evidence_id(span_id: str, claim: str, surface: str, relation: str) -> str:
    stable = "\x1f".join((span_id, claim, surface, relation))
    return "cap_sem_ev_" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]


def _invalid_candidate_diagnostic(index: int, raw: Any, reason: str) -> CompileDiagnostic:
    stable = hashlib.sha256(f"{index}\x1f{reason}".encode("utf-8")).hexdigest()[:12]
    span_ids = raw.get("source_span_ids", []) if isinstance(raw, dict) else []
    return CompileDiagnostic(
        diagnostic_id=f"diag_capability_candidate_invalid_{stable}",
        kind="capability_intent_candidate_invalid",
        severity="warning",
        message=f"External capability candidate was rejected: {reason}",
        target_ref=f"capability_candidate_output:{index}",
        source_span_ids=[item for item in span_ids if isinstance(item, str)],
        metadata={"reason": reason, "candidate_index": index},
        blocks_rendering=False,
        blocks_completion=False,
    )


def _span_sort_key(span_id: str) -> tuple[str, int, str]:
    match = re.match(r"^(.*?)(\d+)(.*)$", span_id)
    if match is None:
        return span_id, -1, ""
    return match.group(1), int(match.group(2)), match.group(3)
