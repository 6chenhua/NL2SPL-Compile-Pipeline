"""Construct provenance and source-span read-model projection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.ir.diagnostics import TraceRecord
from nl2spl.ir.span_ir import SpanIR
from spl_web_demo.card_projector import SplConstructCard, SplConstructType

TraceStatus = Literal["available", "missing"]


@dataclass(frozen=True)
class RepairProvenance:
    repair_patch_id: str | None
    related_diagnostic_id: str | None
    user_text: str | None


@dataclass(frozen=True)
class SpanPresentation:
    span_id: str
    text: str
    source_section_id: str | None
    source_packet_id: str | None
    section_context: str | None
    is_placeholder: bool
    ambiguity_is_ambiguous: bool
    ambiguity_reasons: tuple[str, ...]
    ambiguity_needs_split: bool


@dataclass(frozen=True)
class TracePresentation:
    target_ref: str
    relation: str
    explanation: str
    needs_confirmation: bool
    source_section_id: str | None
    source_packet_id: str | None
    source_span_ids: tuple[str, ...]
    repair: RepairProvenance | None


@dataclass(frozen=True)
class ConstructProvenancePresentation:
    construct_ref: str
    construct_type: SplConstructType
    title: str
    trace_status: TraceStatus
    provenance_kind: str
    matched_target_refs: tuple[str, ...]
    source_span_ids: tuple[str, ...]
    unresolved_span_ids: tuple[str, ...]
    traces: tuple[TracePresentation, ...]
    spans: tuple[SpanPresentation, ...]


@dataclass(frozen=True)
class ProvenanceReadModel:
    constructs: tuple[ConstructProvenancePresentation, ...]
    spans: tuple[SpanPresentation, ...]

    def get_construct(self, construct_ref: str) -> ConstructProvenancePresentation | None:
        return next(
            (item for item in self.constructs if item.construct_ref == construct_ref),
            None,
        )

    def get_span(self, span_id: str) -> SpanPresentation | None:
        return next((item for item in self.spans if item.span_id == span_id), None)


class ProvenanceProjector:
    """Resolve Card identities against public TraceRecord and SpanIR artifacts."""

    def project_snapshot(
        self,
        snapshot: ArtifactSnapshot,
        cards: tuple[SplConstructCard, ...],
    ) -> ProvenanceReadModel:
        spans = tuple(
            _span_to_presentation(span) for span in snapshot.spans if isinstance(span, SpanIR)
        )
        span_index = _unique_span_index(spans)
        trace_index = _trace_index(snapshot.traces)
        constructs = tuple(
            self._project_construct(card, trace_index=trace_index, span_index=span_index)
            for card in cards
        )
        return ProvenanceReadModel(constructs=constructs, spans=spans)

    def _project_construct(
        self,
        card: SplConstructCard,
        *,
        trace_index: dict[str, tuple[TraceRecord, ...]],
        span_index: dict[str, SpanPresentation],
    ) -> ConstructProvenancePresentation:
        traces = _matching_traces(card.trace_target_refs, trace_index)
        trace_views = tuple(_trace_to_presentation(trace) for trace in traces)
        source_span_ids = (
            _ordered_unique(
                span_id
                for trace in traces
                for span_id in trace.source_span_ids
                if isinstance(span_id, str) and span_id
            )
            if traces
            else _ordered_unique(card.source_span_ids)
        )
        resolved_spans = tuple(
            span_index[span_id] for span_id in source_span_ids if span_id in span_index
        )
        unresolved_span_ids = tuple(
            span_id for span_id in source_span_ids if span_id not in span_index
        )
        matched_target_refs = _ordered_unique(trace.target_ref for trace in traces)

        return ConstructProvenancePresentation(
            construct_ref=card.construct_ref,
            construct_type=card.construct_type,
            title=card.title,
            trace_status="available" if traces else "missing",
            provenance_kind=_provenance_kind(card, traces),
            matched_target_refs=matched_target_refs,
            source_span_ids=source_span_ids,
            unresolved_span_ids=unresolved_span_ids,
            traces=trace_views,
            spans=resolved_spans,
        )


def _unique_span_index(spans: tuple[SpanPresentation, ...]) -> dict[str, SpanPresentation]:
    result: dict[str, SpanPresentation] = {}
    for span in spans:
        if span.span_id in result:
            raise ValueError(f"duplicate span_id: {span.span_id}")
        result[span.span_id] = span
    return result


def _trace_index(values: tuple[TraceRecord, ...]) -> dict[str, tuple[TraceRecord, ...]]:
    grouped: dict[str, list[TraceRecord]] = {}
    for trace in values:
        if isinstance(trace, TraceRecord):
            grouped.setdefault(trace.target_ref, []).append(trace)
    return {target_ref: tuple(items) for target_ref, items in grouped.items()}


def _matching_traces(
    target_refs: tuple[str, ...],
    trace_index: dict[str, tuple[TraceRecord, ...]],
) -> tuple[TraceRecord, ...]:
    result: list[TraceRecord] = []
    seen: set[int] = set()
    for target_ref in target_refs:
        for trace in trace_index.get(target_ref, ()):
            identity = id(trace)
            if identity in seen:
                continue
            seen.add(identity)
            result.append(trace)
    return tuple(result)


def _span_to_presentation(span: SpanIR) -> SpanPresentation:
    return SpanPresentation(
        span_id=span.span_id,
        text=span.text,
        source_section_id=span.source_section_id,
        source_packet_id=span.source_packet_id,
        section_context=span.section_context,
        is_placeholder=span.is_placeholder,
        ambiguity_is_ambiguous=span.ambiguity.is_ambiguous,
        ambiguity_reasons=tuple(span.ambiguity.reasons),
        ambiguity_needs_split=span.ambiguity.needs_split,
    )


def _trace_to_presentation(trace: TraceRecord) -> TracePresentation:
    return TracePresentation(
        target_ref=trace.target_ref,
        relation=trace.relation,
        explanation=trace.explanation,
        needs_confirmation=trace.needs_confirmation,
        source_section_id=trace.source_section_id,
        source_packet_id=trace.source_packet_id,
        source_span_ids=_ordered_unique(
            span_id for span_id in trace.source_span_ids if isinstance(span_id, str) and span_id
        ),
        repair=_repair_provenance(trace),
    )


def _repair_provenance(trace: TraceRecord) -> RepairProvenance | None:
    if trace.relation != "user_confirmed_repair":
        return None
    metadata: dict[str, Any] = trace.metadata if isinstance(trace.metadata, dict) else {}
    return RepairProvenance(
        repair_patch_id=_optional_string(metadata.get("repair_patch_id")),
        related_diagnostic_id=_optional_string(metadata.get("related_diagnostic_id")),
        user_text=_optional_string(metadata.get("user_text")),
    )


def _provenance_kind(
    card: SplConstructCard,
    traces: tuple[TraceRecord, ...],
) -> str:
    relations = _ordered_unique(
        trace.relation for trace in traces if isinstance(trace.relation, str) and trace.relation
    )
    if len(relations) == 1:
        return relations[0]
    if len(relations) > 1:
        return "mixed"
    fallback = card.provenance_summary.kind
    return fallback if fallback in {"source_backed", "inferred", "assumed"} else "unresolved"


def _ordered_unique(values: Iterable[object]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
