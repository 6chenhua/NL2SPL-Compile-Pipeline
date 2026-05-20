"""Regression fixtures for LLM Adapter Engine.

These tests use the real StructuralNLAdapter + SpanSlicer (no LLM) to
produce canonical input, then assert behavior from the fact-to-IR bridges.

  Phase 4: FailureModeFact -> partial ExceptionFlow bridge
    (PASSES: the real bridge_failure_modes() is used; downstream pipeline
     produces exception flow skeleton, missing_handler, partial status,
     failure section provenance)
  Phase 5: DelegationIntentFact -> traceable non-renderable candidate
    (PASSES: ProvenanceAggregator traces delegation intents with
     section provenance; no executable INVOKE)
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.assumptions import AssumptionBuilder
from nl2spl.compiler.completeness import compute_completeness
from nl2spl.compiler.diagnostic_analyzer import AnalyzeInput, DiagnosticAnalyzer
from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.compiler.report_renderer import render_report
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.pipeline.provenance import ProvenanceAggregator
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler
from nl2spl.pipeline.stages.stage11_spl_renderer import SPLRenderer
from nl2spl.pipeline.stages.stage9_5_normalizer import IRNormalizer

_MIN_PROFILE = AgentProfileIR(persona=PersonaIR(role="Assistant"))


def _adapt_and_slice(text: str) -> tuple:
    """Run the real adapter + Stage 1, return (spans, canonical_input)."""
    from nl2spl.adapters import InputAdapterRegistry
    from nl2spl.config import PipelineConfig
    from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer

    registry = InputAdapterRegistry()
    canonical = registry.adapt(text)
    cfg = PipelineConfig(save_intermediate=False)
    slicer = SpanSlicer(cfg, _MagicLLM())
    spans = slicer.execute(canonical)
    return spans, canonical


class _MagicLLM:
    """Fake LLM -- SpanSlicer uses canonical path for structured input."""
    call_json = None  # type: ignore[assignment]
    call_text = None  # type: ignore[assignment]


# =========================================================================
# Phase 4: FailureModeFact -> partial ExceptionFlow
# =========================================================================


def test_failure_bridge_creates_partial_exception_flow() -> None:
    """Phase 4: structural failure mode creates exception flow skeleton
    via the real bridge_failure_modes().  No handler step.  missing_handler
    diagnostic.  partial status.  Failure section provenance in report."""

    from nl2spl.pipeline.fact_bridges import bridge_failure_modes

    text = (
        "Task family: Internal reporting\n"
        "\n"
        "Inputs for each run:\n"
        "- user request: The user's question.\n"
        "\n"
        "Required outputs:\n"
        "- final_report: A compiled report.\n"
        "\n"
        "Failure handling:\n"
        "- Missing timeframe: The user did not provide a timeframe.\n"
    )

    spans, canonical = _adapt_and_slice(text)
    assert canonical.hard_facts.failure_modes, (
        "Adapter must produce FailureModeFact from failure_handling section"
    )

    # Use the real bridge to create exception flows from failure facts
    flow = bridge_failure_modes(
        canonical.hard_facts.failure_modes,
        spans,
        FlowStructureIR(),
    )
    assert flow.exception_flows, "Bridge must create exception flow(s)"

    # Build blocks for the exception flow so provenance can resolve spans
    blocks = BlockStructureIR()
    for exc in flow.exception_flows:
        if exc.spans:
            blocks.exception_flow_blocks[exc.flow_id] = [
                BlockIR("b_exc", "SEQUENTIAL", spans=exc.spans),
            ]

    normalizer = IRNormalizer()
    n_flow, n_blocks, n_steps, _nc, n_syms, n_errs, n_warns = normalizer.normalize(
        flow, blocks, ResourceRegistryIR(), SymbolTable(), [], [], None,
    )

    assembler = WorkerAssembler()
    worker = assembler.assemble(n_flow, n_blocks, n_steps,
                                ResourceRegistryIR(), n_syms, None)

    from nl2spl.pipeline.stages.stage9_5_normalizer.final_irs_checker import (
        PostNormalizeIRSChecker,
    )
    post_norm_checker = PostNormalizeIRSChecker()
    post_norm_diags = post_norm_checker.check(worker=worker)

    gate = ExecutableElementGate()
    worker, _ri, gate_diags = gate.apply(worker)

    prov_steps = list(worker.steps)
    renderer = SPLRenderer()
    spl_text, spl_errs, spl_warns = renderer.render(
        worker, _MIN_PROFILE, ResourceRegistryIR(), n_syms, prov_steps, [],
    )

    aggregator = ProvenanceAggregator()
    traces, prov_diags = aggregator.aggregate(
        worker=worker, steps=prov_steps, constraints=[],
        resources=ResourceRegistryIR(), symbol_table=n_syms, spans=spans,
    )

    all_diags = list(post_norm_diags) + gate_diags + prov_diags
    analyzer = DiagnosticAnalyzer()
    analyzer_diags = analyzer.analyze(AnalyzeInput(
        worker=worker, steps=prov_steps,
    ))
    all_diags.extend(analyzer_diags)

    completeness = compute_completeness(
        validation_errors=n_errs + spl_errs,
        diagnostics=all_diags,
    )
    assumptions = AssumptionBuilder().build(all_diags)
    report = render_report(
        spl_text=spl_text, completeness=completeness,
        diagnostics=all_diags, assumptions=assumptions,
        traces=traces,
        validation_errors=n_errs + spl_errs,
        validation_warnings=n_warns + spl_warns,
    )

    # Target assertions
    assert "[EXCEPTION_FLOW:" in spl_text, "SPL must contain exception flow skeleton"
    assert "Missing timeframe" in spl_text
    assert "REQUEST_INPUT" not in spl_text, "No invented handler"
    mh = [d for d in all_diags if d.kind == "missing_handler"]
    assert mh, "missing_handler must be emitted"
    assert completeness == "partial", f"Expected partial, got {completeness}"
    ft = next(t for t in traces if t.target_ref.startswith("flow:exc_adapter"))
    assert ft.source_section_id == "sec_failure_handling", (
        f"Flow trace must carry failure section provenance, "
        f"got {ft.source_section_id}"
    )
    assert "section=sec_failure_handling" in report
    assert "Status: partial" in report


# =========================================================================
# Phase 5: DelegationIntentFact -> traceable non-renderable candidate
# =========================================================================


def test_delegation_bridge_preserves_incomplete_delegation_provenance() -> None:
    """Phase 5: delegation intent produces non-executable trace record
    with section provenance.  No INVOKE in SPL.  No executable child."""

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

    # Adapter produces delegation intents (Phase 1)
    assert canonical.hard_facts.delegation_intents, (
        "Adapter must produce DelegationIntentFact from delegation_policy section"
    )

    del_spans = [s for s in spans if s.source_section_id == "sec_delegation_policy"]
    assert del_spans, "Must have spans from delegation_policy section"
    del_span_id = del_spans[0].span_id

    flow = FlowStructureIR()
    blocks = BlockStructureIR(
        main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", spans=[del_span_id])],
    )
    steps = [
        StepIR("st1", "Do work", [del_span_id], "GENERAL_COMMAND"),
    ]

    normalizer = IRNormalizer()
    n_flow, n_blocks, n_steps, _nc, n_syms, n_errs, n_warns = normalizer.normalize(
        flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, [], None,
    )

    assembler = WorkerAssembler()
    worker = assembler.assemble(n_flow, n_blocks, n_steps,
                                ResourceRegistryIR(), n_syms, None)

    from nl2spl.pipeline.stages.stage9_5_normalizer.final_irs_checker import (
        PostNormalizeIRSChecker,
    )
    post_norm_checker = PostNormalizeIRSChecker()
    post_norm_diags = post_norm_checker.check(worker=worker)

    gate = ExecutableElementGate()
    worker, _ri, gate_diags = gate.apply(worker)

    prov_steps = list(worker.steps)
    renderer = SPLRenderer()
    spl_text, spl_errs, spl_warns = renderer.render(
        worker, _MIN_PROFILE, ResourceRegistryIR(), n_syms, prov_steps, [],
    )

    # Phase 5: ProvenanceAggregator traces delegation intents
    aggregator = ProvenanceAggregator()
    traces, prov_diags = aggregator.aggregate(
        worker=worker, steps=prov_steps, constraints=[],
        resources=ResourceRegistryIR(), symbol_table=n_syms, spans=spans,
        delegation_intents=list(canonical.hard_facts.delegation_intents),
    )

    all_diags = list(post_norm_diags) + gate_diags + prov_diags

    # Phase 5: delegation intent diagnostic bridge
    from nl2spl.pipeline.fact_bridges import bridge_delegation_intents
    delegation_diags = bridge_delegation_intents(
        list(canonical.hard_facts.delegation_intents),
        handoffs=None,
        spans=spans,
    )
    all_diags.extend(delegation_diags)

    completeness = compute_completeness(
        validation_errors=n_errs + spl_errs,
        diagnostics=all_diags,
    )
    assumptions = AssumptionBuilder().build(all_diags)
    report = render_report(
        spl_text=spl_text, completeness=completeness,
        diagnostics=all_diags, assumptions=assumptions,
        traces=traces,
        validation_errors=n_errs + spl_errs,
        validation_warnings=n_warns + spl_warns,
    )

    # No executable INVOKE (delegation intent is non-executable)
    assert "[INVOKE" not in spl_text, "SPL must NOT contain [INVOKE"
    # Diagnostic for incomplete delegation
    diag_kinds = {d.kind for d in all_diags}
    assert "type_or_contract_ambiguity" in diag_kinds, (
        f"Must have type_or_contract_ambiguity for incomplete delegation, "
        f"got {diag_kinds}"
    )
    assert completeness == "partial", (
        f"Expected partial, got {completeness}"
    )
    assert "Status: partial" in report
    assert "Diagnostics" in report
    # Delegation intent trace with section provenance
    di_traces = [t for t in traces if t.target_ref.startswith("delegation_intent:")]
    assert di_traces, "Must have delegation intent trace record"
    assert any(
        t.source_section_id == "sec_delegation_policy" for t in di_traces
    ), "Delegation intent trace must carry delegation section provenance"
    assert "section=sec_delegation_policy" in report
    assert len(traces) > 0
    assert "Provenance Traces" in report
