"""Stage 5: BlockAssembler - PromptEnricherMixin (span text enrichment and validation helpers)."""

from __future__ import annotations

from typing import Any, Literal

from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR


class PromptEnricherMixin:
    """Mixin containing prompt enrichment and validation helpers."""

    def _flow_with_span_text(
        self,
        flow: FlowStructureIR,
        spans: list[SpanIR],
        include_delegation_context: bool,
    ) -> dict[str, object]:
        """Return flow JSON with span IDs paired with source text."""
        span_text_by_id = {span.span_id: span.text for span in spans}
        flow_json: dict[str, object] = {
            "main_flow_spans": self._span_refs(flow.main_flow_spans, span_text_by_id),
            "alternative_flows": [
                {
                    "flow_id": alt_flow.flow_id,
                    "condition_text": alt_flow.condition_text,
                    "spans": self._span_refs(alt_flow.spans, span_text_by_id),
                }
                for alt_flow in flow.alternative_flows
            ],
            "exception_flows": [
                {
                    "flow_id": exc_flow.flow_id,
                    "condition_text": exc_flow.condition_text,
                    "spans": self._span_refs(exc_flow.spans, span_text_by_id),
                }
                for exc_flow in flow.exception_flows
            ],
        }
        if include_delegation_context:
            flow_json["delegation_candidates"] = [
                {
                    "candidate_id": candidate.candidate_id,
                    "spans": self._span_refs(candidate.spans, span_text_by_id),
                    "reason": candidate.reason,
                    "suggested_type": candidate.suggested_type,
                    "input_variables": candidate.input_variables,
                    "output_variables": candidate.output_variables,
                }
                for candidate in flow.delegation_candidates
            ]
        return flow_json

    def _span_refs(
        self,
        span_ids: list[str],
        span_text_by_id: dict[str, str],
    ) -> list[dict[str, str]]:
        """Pair span ids with text while preserving IDs for output references."""
        return [
            {
                "span_id": span_id,
                "text": span_text_by_id.get(span_id, ""),
            }
            for span_id in span_ids
        ]

    def _span_ids(self, spans: list[Any]) -> list[str]:
        """Normalize model span refs to span_id strings."""
        span_ids: list[str] = []
        for span in spans:
            if isinstance(span, str):
                span_ids.append(span)
            elif isinstance(span, dict) and isinstance(span.get("span_id"), str):
                span_ids.append(span["span_id"])
        return span_ids

    def _valid_outer_control(
        self,
        value: Any,
    ) -> Literal["SEQUENTIAL", "IF", "FOR", "WHILE", "unknown"]:
        """Clamp outer_control to the ControlComplexityRegionIR enum."""
        if value in {"SEQUENTIAL", "IF", "FOR", "WHILE", "unknown"}:
            return value
        return "unknown"

    def _valid_inner_control(
        self,
        value: Any,
    ) -> Literal["IF", "FOR", "WHILE", "multiple", "unknown"]:
        """Clamp inner_control to the ControlComplexityRegionIR enum."""
        if value in {"IF", "FOR", "WHILE", "multiple", "unknown"}:
            return value
        return "unknown"

    def _valid_severity(self, value: Any) -> Literal["info", "warning", "error"]:
        """Clamp severity to the ControlComplexityRegionIR enum."""
        if value in {"info", "warning", "error"}:
            return value
        return "warning"

    def _dedupe(self, values: list[str]) -> list[str]:
        """Deduplicate strings while preserving order."""
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                deduped.append(value)
        return deduped
