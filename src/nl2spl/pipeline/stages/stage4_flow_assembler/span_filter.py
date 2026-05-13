"""Stage 4: FlowAssembler - SpanFilterMixin (_restrict_flow_to_span_ids)."""

from __future__ import annotations

from nl2spl.ir.flow_structure_ir import (
    AlternativeFlow,
    ExceptionFlow,
    FlowStructureIR,
)


class SpanFilterMixin:
    """Mixin containing span filtering for worker boundaries."""

    def _restrict_flow_to_span_ids(
        self,
        flow: FlowStructureIR,
        allowed_span_ids: set[str],
    ) -> FlowStructureIR:
        """Keep worker-scoped flows inside the WorkerSpecIR ownership boundary."""
        return FlowStructureIR(
            main_flow_spans=[
                span_id
                for span_id in flow.main_flow_spans
                if span_id in allowed_span_ids
            ],
            alternative_flows=[
                AlternativeFlow(
                    flow_id=alt_flow.flow_id,
                    condition_text=alt_flow.condition_text,
                    spans=[
                        span_id
                        for span_id in alt_flow.spans
                        if span_id in allowed_span_ids
                    ],
                )
                for alt_flow in flow.alternative_flows
            ],
            exception_flows=[
                ExceptionFlow(
                    flow_id=exc_flow.flow_id,
                    condition_text=exc_flow.condition_text,
                    spans=[
                        span_id
                        for span_id in exc_flow.spans
                        if span_id in allowed_span_ids
                    ],
                )
                for exc_flow in flow.exception_flows
            ],
            delegation_candidates=[],
        )
