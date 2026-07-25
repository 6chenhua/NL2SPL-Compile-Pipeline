"""Deterministic early capability-evidence collection.

The collector projects only structured adapter/route clues. It intentionally
does not inspect words in source text to decide that a capability exists.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.compiler.capability_intent.model import (
    CapabilityEvidenceCandidateIR,
    EarlyCapabilityEvidenceView,
)
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR


class EarlyCapabilityEvidenceCollector:
    """Collect source-backed clues without semantic or admission authority."""

    def collect(
        self,
        canonical_input: CanonicalCompileInput,
        spans: Iterable[SpanIR],
        routes: FieldRouteIR,
    ) -> EarlyCapabilityEvidenceView:
        spans_by_id = {span.span_id: span for span in spans}
        collected: dict[str, CapabilityEvidenceCandidateIR] = {}

        for annotation in routes.annotations:
            if not _is_structured_capability_clue(annotation):
                continue
            span = spans_by_id.get(annotation.span_id)
            if span is None:
                continue
            item = _from_annotation(annotation, span)
            collected[item.evidence_id] = item

        for index, hint in enumerate(canonical_input.compile_hints.resource_hints):
            if not _is_structured_adapter_capability_clue(hint):
                continue
            span_ids = tuple(
                dict.fromkeys(
                    span_id
                    for evidence in hint.evidence
                    for span_id in evidence.source_span_ids
                    if span_id in spans_by_id
                )
            )
            hint_id = _hint_id(hint.source_section_id, index)
            for span_id in span_ids or (None,):
                surface = spans_by_id[span_id].text if span_id else hint.text
                item = _make_candidate(
                    source_span_id=span_id,
                    source_hint_ids=(hint_id,),
                    surface_text=surface,
                    claim_hint=(
                        "adapter_declaration"
                        if hint.metadata.get("capability_declaration") is True
                        else "possible_boundary"
                    ),
                    origin="adapter",
                    source_section_id=hint.source_section_id,
                    source_packet_id=_first_packet_id(hint.evidence),
                    metadata={
                        "target": hint.target or "",
                        "suggested_kind": hint.suggested_kind or "",
                    },
                )
                collected[item.evidence_id] = item

        ordered = tuple(collected[key] for key in sorted(collected))
        return EarlyCapabilityEvidenceView(
            candidates=ordered,
            metadata={
                "authority": "non_authoritative",
                "collector_version": "EarlyCapabilityEvidenceCollectorV1",
            },
        )


def _is_structured_capability_clue(annotation: RouteAnnotation) -> bool:
    return (
        annotation.construct_target in {"API_DECLARATION", "CALL_API"}
        or annotation.semantic_role in {"api_candidate", "integration_hint"}
        or annotation.route_family == "external_capability"
    )


def _is_structured_adapter_capability_clue(hint: object) -> bool:
    target = getattr(hint, "target", None)
    suggested_kind = getattr(hint, "suggested_kind", None)
    metadata = getattr(hint, "metadata", {}) or {}
    return (
        target in {"API_DECLARATION", "CALL_API", "external_capability"}
        or suggested_kind in {"api", "external_capability", "integration"}
        or metadata.get("capability_declaration") is True
        or metadata.get("external_capability") is True
    )


def _from_annotation(
    annotation: RouteAnnotation,
    span: SpanIR,
) -> CapabilityEvidenceCandidateIR:
    if annotation.construct_target == "CALL_API":
        claim_hint = "possible_invocation"
    elif annotation.construct_target == "API_DECLARATION":
        claim_hint = "possible_identity"
    else:
        claim_hint = "possible_boundary"
    return _make_candidate(
        source_span_id=annotation.span_id,
        source_hint_ids=tuple(sorted(annotation.source_hint_ids)),
        surface_text=span.text,
        claim_hint=claim_hint,
        origin="stage2_annotation",
        source_section_id=annotation.source_section_id or span.source_section_id,
        source_packet_id=annotation.source_packet_id or span.source_packet_id,
        metadata={
            "construct_target": annotation.construct_target or "",
            "semantic_role": annotation.semantic_role or "",
            "route_family": annotation.route_family or "",
        },
    )


def _make_candidate(**kwargs: object) -> CapabilityEvidenceCandidateIR:
    stable_parts = [
        str(kwargs.get("origin") or ""),
        str(kwargs.get("source_span_id") or ""),
        str(kwargs.get("claim_hint") or ""),
        str(kwargs.get("surface_text") or ""),
        "|".join(kwargs.get("source_hint_ids") or ()),
    ]
    digest = hashlib.sha256("\x1f".join(stable_parts).encode("utf-8")).hexdigest()[:16]
    return CapabilityEvidenceCandidateIR(evidence_id=f"cap_ev_{digest}", **kwargs)


def _hint_id(source_section_id: str | None, index: int) -> str:
    digest = hashlib.sha256(
        f"{source_section_id or ''}\x1f{index}".encode()
    ).hexdigest()[:12]
    return f"adapter_hint_{digest}"


def _first_packet_id(evidence: list[object]) -> str | None:
    for item in evidence:
        packet_id = getattr(item, "source_packet_id", None)
        if packet_id:
            return packet_id
    return None
