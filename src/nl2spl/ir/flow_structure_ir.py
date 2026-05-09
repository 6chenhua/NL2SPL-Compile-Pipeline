"""FlowStructureIR - Flow structure with delegation candidates."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DelegationCandidate:
    """Delegation candidate identified by LLM.

    Attributes:
        candidate_id: Unique identifier (format: dc_{N})
        spans: Related span IDs
        reason: Why this is a delegation candidate
        suggested_type: Suggested type (child_worker or api_call)
        input_variables: Input variables for the subtask
        output_variables: Output variables from the subtask
    """

    candidate_id: str
    spans: list[str]
    reason: str
    suggested_type: str  # "child_worker" or "api_call"
    input_variables: list[str] = field(default_factory=list)
    output_variables: list[str] = field(default_factory=list)


@dataclass
class AlternativeFlow:
    """Alternative flow definition.

    Attributes:
        flow_id: Unique identifier (format: alt_{N})
        condition_text: Trigger condition
        spans: Span IDs in this flow
    """

    flow_id: str
    condition_text: str
    spans: list[str]


@dataclass
class ExceptionFlow:
    """Exception flow definition.

    Attributes:
        flow_id: Unique identifier (format: exc_{N})
        condition_text: Trigger condition
        spans: Span IDs in this flow
    """

    flow_id: str
    condition_text: str
    spans: list[str]


@dataclass
class FlowStructureIR:
    """Flow structure information.

    Attributes:
        main_flow_spans: Spans in main flow
        alternative_flows: Alternative flow definitions
        exception_flows: Exception flow definitions
        delegation_candidates: Delegation candidates
    """

    main_flow_spans: list[str] = field(default_factory=list)
    alternative_flows: list[AlternativeFlow] = field(default_factory=list)
    exception_flows: list[ExceptionFlow] = field(default_factory=list)
    delegation_candidates: list[DelegationCandidate] = field(default_factory=list)

    def get_all_flow_spans(self) -> set[str]:
        """Get all spans across all flows."""
        spans = set(self.main_flow_spans)
        for alt_flow in self.alternative_flows:
            spans.update(alt_flow.spans)
        for exc_flow in self.exception_flows:
            spans.update(exc_flow.spans)
        return spans

    def get_flow_for_span(self, span_id: str) -> str | None:
        """Get the flow a span belongs to.

        Args:
            span_id: Span ID to look up

        Returns:
            Flow ID or None if not found
        """
        if span_id in self.main_flow_spans:
            return "main"
        for alt_flow in self.alternative_flows:
            if span_id in alt_flow.spans:
                return alt_flow.flow_id
        for exc_flow in self.exception_flows:
            if span_id in exc_flow.spans:
                return exc_flow.flow_id
        return None
