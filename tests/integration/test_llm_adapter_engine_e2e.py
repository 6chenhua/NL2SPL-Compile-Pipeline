"""Regression fixtures for the current adapter boundary.

The input adapter preserves structure and provenance only. Semantic delegation
diagnostics are produced from final RouteAnnotations through IRS, not from
adapter hard-fact bridges.
"""

from __future__ import annotations

from nl2spl.adapters import InputAdapterRegistry
from nl2spl.config import PipelineConfig
from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.worker_delegation import WorkerDelegationIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.projector import DiagnosticProjector
from nl2spl.compiler.irs.registry import IRSCheckerRegistry
from nl2spl.compiler.irs.runner import IRSRunner
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.worker_plan_ir import WorkerPlanIR
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


def _run_stage3_5_irs(routes: FieldRouteIR):
    registry = IRSCheckerRegistry()
    registry.register(WorkerDelegationIRSChecker())
    runner = IRSRunner(
        registry=registry,
        construct_registry=SPLConstructRegistry.default(),
        projector=DiagnosticProjector(),
    )
    return runner.run_stage(
        "stage3_5",
        IRSCheckContext(
            stage_name="stage3_5",
            routes=routes,
            worker_plan=WorkerPlanIR(main_worker_id="worker_main"),
        ),
    )


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

    result = _run_stage3_5_irs(routes)
    diags = result.diagnostics

    # R10 Phase 1: diagnostic now targets worker_promotion:* (not delegation_intent:*)
    assert len(diags) >= 1, (
        f"Expected diagnostics from IRS, got {[(d.target_ref, d.kind) for d in diags]}"
    )
    # Filter to the type_or_contract_ambiguity diagnostics from worker_promotion
    ambiguity_diags = [
        d for d in diags
        if d.kind == "type_or_contract_ambiguity"
        and (d.target_ref or "").startswith("worker_promotion:")
    ]
    assert len(ambiguity_diags) >= 1
    diag = ambiguity_diags[0]
    assert diag.diagnostic_id.startswith("irs_")
    assert diag.kind == "type_or_contract_ambiguity"
    assert del_span.span_id in diag.source_span_ids
