"""Regression fixtures for the current adapter boundary.

The input adapter preserves structure and provenance only. Semantic delegation
diagnostics are produced from final RouteAnnotations, not from adapter hard-fact
bridges.
"""

from __future__ import annotations

from nl2spl.adapters import InputAdapterRegistry
from nl2spl.config import PipelineConfig
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.pipeline.delegation_diagnostics import (
    diagnose_delegation_intents_from_routes,
)
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer


class _MagicLLM:
    """Fake LLM; SpanSlicer uses the canonical path for structured input."""

    call_json = None  # type: ignore[assignment]
    call_text = None  # type: ignore[assignment]


def _adapt_and_slice(text: str) -> tuple:
    registry = InputAdapterRegistry()
    canonical = registry.adapt(text)
    cfg = PipelineConfig(save_intermediate=False)
    slicer = SpanSlicer(cfg, _MagicLLM())
    spans = slicer.execute(canonical)
    return spans, canonical


def test_adapter_preserves_delegation_policy_without_bridge_facts() -> None:
    text = (
        "Task family: Internal reporting\n"
        "\n"
        "Inputs for each run:\n"
        "- user request: The user's question.\n"
        "\n"
        "Required outputs:\n"
        "- final_report: A compiled report.\n"
        "\n"
        "Delegation policy:\n"
        "- Source gathering: Delegate to a specialized source gathering agent.\n"
    )

    spans, canonical = _adapt_and_slice(text)

    assert canonical.hard_facts.delegation_intents == []

    del_spans = [s for s in spans if s.source_section_id == "sec_delegation_policy"]
    assert del_spans, "Delegation policy text must preserve section provenance"
    del_span = del_spans[0]

    routes = FieldRouteIR(
        behavior=[del_span.span_id],
        annotations=[
            RouteAnnotation(
                span_id=del_span.span_id,
                field="behavior",
                semantic_role="delegation_intent",
                route_family="delegation_boundary",
                executable=False,
                source_section_id=del_span.source_section_id,
                source_packet_id=del_span.source_packet_id,
            )
        ],
    )

    diags = diagnose_delegation_intents_from_routes(routes, spans)

    assert len(diags) == 1
    assert diags[0].kind == "type_or_contract_ambiguity"
    assert diags[0].target_ref == f"delegation_intent:{del_span.span_id}"
    assert diags[0].source_span_ids == [del_span.span_id]
