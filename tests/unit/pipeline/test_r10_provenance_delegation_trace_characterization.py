"""R10 Phase 0: Characterization tests for provenance/delegation trace.

This file LOCKS the current provenance and feedback rendering behavior
around delegation_intent:* targets and traces.

Coverage targets per Section 4.5:
  1. current provenance/trace contains delegation_intent:* target
  2. feedback_report_renderer groups delegation_intent:* under "Delegation Intents"
  3. provenance generator creates TraceRecord with target_ref="delegation_intent:*"
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.feedback_report_renderer import _trace_group
from nl2spl.compiler.irs.checkers.worker_delegation import WorkerDelegationIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.projector import DiagnosticProjector
from nl2spl.compiler.irs.registry import IRSCheckerRegistry
from nl2spl.compiler.irs.runner import IRSRunner
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.worker_plan_ir import (
    WorkerPlanIR,
)
from nl2spl.pipeline.provenance import TraceRecord

# ===========================================================================
# Characterization: _trace_group delegates delegation_intent:* → "Delegation Intents"
# ===========================================================================


class TestCharTraceGroupDelegationIntent:
    """Characterize: feedback_report_renderer._trace_group currently maps
    delegation_intent:* target_ref to "Delegation Intents" group.
    """

    def test_delegation_intent_trace_group(self) -> None:
        """R10 Phase 6: _trace_group for source_signal:delegation_intent:*
        returns "Source Signals".
        """
        result = _trace_group("source_signal:delegation_intent:s_foo")
        assert result == "Source Signals"

    def test_delegation_intent_with_colon_variants(self) -> None:
        """R10 Phase 6: source_signal:delegation_intent:* maps to Source Signals."""
        assert _trace_group("source_signal:delegation_intent:anything") == "Source Signals"
        assert _trace_group("source_signal:delegation_intent:some.span.id") == "Source Signals"

    def test_worker_promotion_trace_group(self) -> None:
        """worker_promotion:* falls to 'Other' group (no special grouping)."""
        result = _trace_group("worker_promotion:cand_1")
        assert result == "Other"

    def test_worker_handoff_trace_group(self) -> None:
        """worker_handoff:* does not have specific group."""
        result = _trace_group("worker_handoff:handoff_1")
        assert result == "Other"

    def test_old_delegation_intent_prefix_falls_to_other(self) -> None:
        """R10 Phase 6: bare delegation_intent:* (without source_signal: prefix)
        now falls to 'Other' — it is no longer a recognized construct prefix."""
        result = _trace_group("delegation_intent:worker_boundary_x")
        assert result == "Other"


# ===========================================================================
# Characterization: provenance.py generates TraceRecord with delegation_intent:*
# ===========================================================================


class TestCharProvenanceDelegationTrace:
    """Characterize: provenance generator creates TraceRecord with
    target_ref="delegation_intent:<name>" from DelegationIntentFact.
    """

    def test_delegation_intent_trace_record_format(self) -> None:
        """R10 Phase 6: TraceRecord uses source_signal:delegation_intent:<name>
        format — provenance-only, not a construct/diagnostic target."""
        trace = TraceRecord(
            target_ref="source_signal:delegation_intent:source_gathering",
            source_span_ids=["s1", "s2"],
            source_section_id="sec_delegation_policy",
            source_packet_id="pkt_delegate",
            relation="inferred",
            explanation=(
                "Delegation intent 'source_gathering': "
                "Source gathering may be used if bounded"
            ),
        )

        assert trace.target_ref == "source_signal:delegation_intent:source_gathering"
        assert trace.relation == "inferred"
        assert trace.source_span_ids == ["s1", "s2"]
        assert trace.source_section_id == "sec_delegation_policy"

    def test_trace_record_metadata_defaults_empty(self) -> None:
        """TraceRecord carries optional metadata for auditable provenance."""
        trace = TraceRecord(
            target_ref="source_signal:delegation_intent:test",
            source_span_ids=["s1"],
            relation="direct",
        )
        assert trace.metadata == {}

    def test_source_signal_format_not_currently_used(self) -> None:
        """R10 Phase 6: source_signal:delegation_intent:* format IS now used
        by ProvenanceAggregator."""
        trace = TraceRecord(
            target_ref="source_signal:delegation_intent:some_name",
            source_span_ids=["s1"],
            relation="inferred",
        )
        assert trace.target_ref.startswith("source_signal:")
        assert "delegation_intent" in trace.target_ref


# ===========================================================================
# Characterization: _trace_group check ordering relative to other groups
# ===========================================================================


class TestCharTraceGroupOrdering:
    """Characterize: the specific ordering of _trace_group prefix checks."""

    def test_handoff_group(self) -> None:
        """handoff:* is grouped under Handoffs."""
        result = _trace_group("handoff:invoke_worker_1")
        assert result == "Handoffs"

    def test_flow_group(self) -> None:
        """flow:* is grouped under Flows."""
        result = _trace_group("flow:main_flow")
        assert result == "Flows"


# ===========================================================================
# Characterization: IRS diagnostics → feedback/provenance chain
# ===========================================================================


class TestCharIRSDiagnosticsProvenanceChain:
    """Characterize: the full chain from IRS diagnostics through provenance."""

    def test_delegation_diagnostic_has_source_span_ids(self) -> None:
        """R10 Phase 1: IRS diagnostics from delegation intent
        preserve source_span_ids from the route annotation.
        Diagnostics now target worker_promotion:* instead of delegation_intent:*.
        """
        routes = FieldRouteIR(
            behavior=["s_delegate"],
            annotations=[
                RouteAnnotation(
                    span_id="s_delegate",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                    source_section_id="sec_del",
                    source_packet_id="pkt_del",
                )
            ],
        )

        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        checker_registry = IRSCheckerRegistry()
        checker_registry.register(WorkerDelegationIRSChecker())
        runner = IRSRunner(
            registry=checker_registry,
            construct_registry=SPLConstructRegistry.default(),
            projector=DiagnosticProjector(),
        )
        result = runner.run_stage(
            "stage3_5",
            IRSCheckContext(
                stage_name="stage3_5",
                routes=routes,
                worker_plan=plan,
            ),
        )

        # R10 Phase 1: diagnostics target worker_promotion:*
        diags = [
            d for d in result.diagnostics
            if (d.target_ref or "").startswith("worker_promotion:")
            and d.kind == "type_or_contract_ambiguity"
        ]
        assert len(diags) >= 1
        diag = diags[0]

        # Source span ID should be preserved
        assert "s_delegate" in diag.source_span_ids, (
            "CHARACTERIZATION: delegation diagnostic preserves source_span_ids. "
            "This must remain true after migration."
        )

    def test_delegation_diagnostic_has_irs_prefix_id(self) -> None:
        """R10 Phase 1: delegation diagnostic_id starts with 'irs_'."""
        routes = FieldRouteIR(
            behavior=["s_delegate"],
            annotations=[
                RouteAnnotation(
                    span_id="s_delegate",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                )
            ],
        )

        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        checker_registry = IRSCheckerRegistry()
        checker_registry.register(WorkerDelegationIRSChecker())
        runner = IRSRunner(
            registry=checker_registry,
            construct_registry=SPLConstructRegistry.default(),
            projector=DiagnosticProjector(),
        )
        result = runner.run_stage(
            "stage3_5",
            IRSCheckContext(
                stage_name="stage3_5",
                routes=routes,
                worker_plan=plan,
            ),
        )

        # R10 Phase 1: diagnostics target worker_promotion:*
        diags = [
            d for d in result.diagnostics
            if (d.target_ref or "").startswith("worker_promotion:")
            and d.kind == "type_or_contract_ambiguity"
        ]
        assert len(diags) >= 1
        assert diags[0].diagnostic_id.startswith("irs_"), (
            "CHARACTERIZATION: delegation diagnostic uses irs_ prefix. "
            "This must remain true after migration."
        )


# ===========================================================================
# Characterization: ProvenanceAggregator._trace_delegation_intents
# ===========================================================================


class TestCharProvenanceAggregatorDelegationIntents:
    """Characterize: ProvenanceAggregator currently produces TraceRecord
    with target_ref="delegation_intent:<name>" from DelegationIntentFact.
    """

    @staticmethod
    def _minimal_aggregator_args():
        """Build minimal valid args for ProvenanceAggregator.aggregate."""
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.ir.worker_ir import WorkerIR

        worker = WorkerIR(
            worker_name="MainWorker",
            description="Main worker",
        )
        return worker, ResourceRegistryIR(), SymbolTable()

    def test_aggregate_produces_delegation_intent_trace(self) -> None:
        """R10 Phase 6: ProvenanceAggregator now produces
        TraceRecord(target_ref="source_signal:delegation_intent:<name>")."""
        from nl2spl.canonical.compile_input import DelegationIntentFact, EvidenceRef
        from nl2spl.pipeline.provenance import ProvenanceAggregator

        intent = DelegationIntentFact(
            name="source_gathering",
            text="Source gathering may be used if bounded",
            suggested_worker_name="SourceGatherer",
            evidence=[
                EvidenceRef(
                    source_section_id="sec_delegation_policy",
                    source_packet_id="pkt_delegate",
                    source_span_ids=["s_del_1", "s_del_2"],
                )
            ],
        )

        worker, resources, symbols = self._minimal_aggregator_args()

        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker,
            steps=[],
            constraints=[],
            resources=resources,
            symbol_table=symbols,
            spans=[],
            delegation_intents=[intent],
        )

        delegation_traces = [
            t for t in traces
            if "delegation_intent" in (t.target_ref or "")
        ]
        assert len(delegation_traces) == 1

        trace = delegation_traces[0]
        assert trace.target_ref == "source_signal:delegation_intent:source_gathering"
        assert trace.relation == "inferred"
        assert "s_del_1" in trace.source_span_ids
        assert "s_del_2" in trace.source_span_ids
        assert trace.source_section_id == "sec_delegation_policy"
        assert trace.source_packet_id == "pkt_delegate"

    def test_aggregate_no_delegation_intents_no_traces(self) -> None:
        """CHARACTERIZATION: without delegation_intents, no
        delegation_intent:* traces are produced.
        """
        from nl2spl.pipeline.provenance import ProvenanceAggregator

        worker, resources, symbols = self._minimal_aggregator_args()

        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker,
            steps=[],
            constraints=[],
            resources=resources,
            symbol_table=symbols,
            spans=[],
        )

        delegation_traces = [
            t for t in traces
            if "delegation_intent" in (t.target_ref or "")
        ]
        assert len(delegation_traces) == 0

    def test_aggregate_multiple_delegation_intents(self) -> None:
        """R10 Phase 6: multiple DelegationIntentFact → one TraceRecord each."""
        from nl2spl.canonical.compile_input import DelegationIntentFact, EvidenceRef
        from nl2spl.pipeline.provenance import ProvenanceAggregator

        intents = [
            DelegationIntentFact(
                name="src_gathering",
                text="Source gathering",
                evidence=[
                    EvidenceRef(source_section_id="sec_del", source_span_ids=["s1"]),
                ],
            ),
            DelegationIntentFact(
                name="template_matching",
                text="Template matching",
                evidence=[
                    EvidenceRef(source_section_id="sec_del", source_span_ids=["s2"]),
                ],
            ),
        ]

        worker, resources, symbols = self._minimal_aggregator_args()

        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker,
            steps=[],
            constraints=[],
            resources=resources,
            symbol_table=symbols,
            spans=[],
            delegation_intents=intents,
        )

        delegation_traces = [
            t for t in traces
            if "delegation_intent" in (t.target_ref or "")
        ]
        assert len(delegation_traces) == 2
        refs = {t.target_ref for t in delegation_traces}
        assert refs == {
            "source_signal:delegation_intent:src_gathering",
            "source_signal:delegation_intent:template_matching",
        }

    def test_delegation_intent_trace_explanation_includes_text(self) -> None:
        """CHARACTERIZATION: TraceRecord explanation includes the
        delegation intent text and suggested worker name.
        """
        from nl2spl.canonical.compile_input import DelegationIntentFact, EvidenceRef
        from nl2spl.pipeline.provenance import ProvenanceAggregator

        intent = DelegationIntentFact(
            name="src_gathering",
            text="Source gathering may be used if bounded",
            suggested_worker_name="SourceGatherer",
            evidence=[
                EvidenceRef(source_section_id="sec_del", source_span_ids=["s1"]),
            ],
        )

        worker, resources, symbols = self._minimal_aggregator_args()

        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker,
            steps=[],
            constraints=[],
            resources=resources,
            symbol_table=symbols,
            spans=[],
            delegation_intents=[intent],
        )

        delegation_traces = [
            t for t in traces
            if "delegation_intent" in (t.target_ref or "")
        ]
        assert len(delegation_traces) == 1
        trace = delegation_traces[0]
        assert "Source gathering" in trace.explanation
        assert "SourceGatherer" in trace.explanation

    def test_provenance_does_not_use_source_signal_prefix(self) -> None:
        """R10 Phase 6: ProvenanceAggregator now uses
        source_signal:delegation_intent:* format."""
        from nl2spl.canonical.compile_input import DelegationIntentFact, EvidenceRef
        from nl2spl.pipeline.provenance import ProvenanceAggregator

        intent = DelegationIntentFact(
            name="test_delegation",
            text="A delegation intent",
            evidence=[
                EvidenceRef(source_section_id="sec_del"),
            ],
        )

        worker, resources, symbols = self._minimal_aggregator_args()

        aggregator = ProvenanceAggregator()
        traces, _ = aggregator.aggregate(
            worker,
            steps=[],
            constraints=[],
            resources=resources,
            symbol_table=symbols,
            spans=[],
            delegation_intents=[intent],
        )

        delegation_traces = [
            t for t in traces
            if "delegation_intent" in (t.target_ref or "")
        ]
        assert len(delegation_traces) == 1
        assert delegation_traces[0].target_ref == (
            "source_signal:delegation_intent:test_delegation"
        )
        assert delegation_traces[0].target_ref.startswith("source_signal:")
