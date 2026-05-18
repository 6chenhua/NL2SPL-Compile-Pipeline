"""Unit tests for FailureModeFact -> ExceptionFlow bridge (Phase 4)
and DelegationIntent -> diagnostic bridge (Phase 5)."""

from __future__ import annotations

from nl2spl.canonical import DelegationIntentFact, EvidenceRef, FailureModeFact
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import (
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.fact_bridges import (
    bridge_delegation_intents,
    bridge_failure_modes,
    bridge_failure_modes_worker_scoped,
)


# -- helpers -------------------------------------------------------------


def _span(sid: str, section: str) -> SpanIR:
    return SpanIR(sid, f"Text for {sid}.", source_section_id=section)


def _fact(name: str, text: str, section: str, span_ids: list[str] | None = None) -> FailureModeFact:
    ev = EvidenceRef(source_section_id=section)
    if span_ids:
        ev.source_span_ids = list(span_ids)
    return FailureModeFact(
        name=name, text=text,
        source_section_id=section,
        evidence=[ev],
    )


# -- Tests ----------------------------------------------------------------


class TestFailureModeBridge:
    def test_single_failure_creates_exception_flow(self) -> None:
        spans = [_span("s1", "sec_failure_handling")]
        facts = [_fact("missing_timeframe", "Missing timeframe.", "sec_failure_handling")]

        result = bridge_failure_modes(facts, spans, FlowStructureIR())

        assert len(result.exception_flows) == 1
        exc = result.exception_flows[0]
        assert exc.flow_id == "exc_adapter_00"
        assert exc.condition_text == "Missing timeframe."
        assert "s1" in exc.spans

    def test_multiple_failures_create_multiple_flows(self) -> None:
        spans = [
            _span("s1", "sec_failure_handling"),
            _span("s2", "sec_other_failure"),
        ]
        facts = [
            _fact("f1", "First failure.", "sec_failure_handling"),
            _fact("f2", "Second failure.", "sec_other_failure"),
        ]

        result = bridge_failure_modes(facts, spans, FlowStructureIR())

        assert len(result.exception_flows) == 2

    def test_different_span_fact_appends(self) -> None:
        """Fact with span NOT in existing flow -> appended."""
        spans = [
            _span("s1", "sec_failure_handling"),
            _span("s2", "sec_other"),
        ]
        existing = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_existing",
                    condition_text="Already covered.",
                    spans=["s1"],
                )
            ]
        )
        facts = [_fact("f_new", "New failure.", "sec_other")]

        result = bridge_failure_modes(facts, spans, existing)

        assert len(result.exception_flows) == 2
        assert result.exception_flows[1].flow_id == "exc_adapter_01"

    def test_same_section_different_conditions_create_multiple_flows(self) -> None:
        """Two facts from the same section with different conditions → both included."""
        spans = [
            _span("s1", "sec_failure_handling"),
            _span("s2", "sec_failure_handling"),
        ]
        facts = [
            _fact("missing_timeframe", "Missing timeframe.", "sec_failure_handling"),
            _fact("conflicting_instructions", "Conflicting instructions.", "sec_failure_handling"),
        ]

        result = bridge_failure_modes(facts, spans, FlowStructureIR())

        assert len(result.exception_flows) == 2
        assert result.exception_flows[0].condition_text == "Missing timeframe."
        assert result.exception_flows[1].condition_text == "Conflicting instructions."

    def test_same_condition_different_span_suppressed(self) -> None:
        """Fact with same normalized condition text as existing → skipped (dedup)."""
        spans = [_span("s1", "sec_a"), _span("s2", "sec_b")]
        existing = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_existing",
                    condition_text="Missing timeframe.",
                    spans=["s1"],
                )
            ]
        )
        facts = [_fact("f1", "Missing timeframe.", "sec_b")]

        result = bridge_failure_modes(facts, spans, existing)

        assert len(result.exception_flows) == 1
        assert result.exception_flows[0].flow_id == "exc_existing"

    def test_no_failure_modes_returns_unchanged(self) -> None:
        existing = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(flow_id="exc_1", condition_text="X.", spans=["s1"])
            ]
        )
        result = bridge_failure_modes([], [], existing)
        assert result == existing

    def test_existing_flow_not_mutated(self) -> None:
        existing = FlowStructureIR()
        facts = [_fact("f1", "Fail.", "sec_failure_handling")]
        spans = [_span("s1", "sec_failure_handling")]

        result = bridge_failure_modes(facts, spans, existing)
        assert existing.exception_flows == []
        assert len(result.exception_flows) == 1

    def test_preserves_existing_flows(self) -> None:
        existing = FlowStructureIR(
            main_flow_spans=["s_main"],
            alternative_flows=[],
            exception_flows=[
                ExceptionFlow(flow_id="exc_old", condition_text="Old.", spans=["s_old"]),
            ],
        )
        spans = [
            _span("s_old", "sec_failure_handling"),
            _span("s_new", "sec_other_failure"),
        ]
        facts = [_fact("f_new", "New failure.", "sec_other_failure")]

        result = bridge_failure_modes(facts, spans, existing)
        assert len(result.exception_flows) == 2
        assert result.exception_flows[0].flow_id == "exc_old"
        assert result.exception_flows[1].flow_id == "exc_adapter_01"

    def test_flow_ids_increment_across_calls(self) -> None:
        spans = [_span("s1", "sec_failure_handling")]
        facts = [_fact("f1", "Fail.", "sec_failure_handling")]
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(flow_id="exc_1", condition_text="X.", spans=["s_x"]),
            ]
        )
        result = bridge_failure_modes(facts, spans, flow)
        # Starts counting after existing flows (1 existing -> adapter_01)
        assert len(result.exception_flows) == 2
        assert result.exception_flows[1].flow_id == "exc_adapter_01"

    def test_uses_evidence_span_ids_for_resolution(self) -> None:
        spans = [
            _span("s_fail", "sec_failure_handling"),
            _span("s_other", "sec_other"),
        ]
        fact = _fact("f1", "Specific failure.", "sec_failure_handling",
                       span_ids=["s_fail"])

        result = bridge_failure_modes([fact], spans, FlowStructureIR())

        assert len(result.exception_flows) == 1
        assert "s_fail" in result.exception_flows[0].spans


# =========================================================================
# Phase 5: DelegationIntent -> diagnostic
# =========================================================================


def _dintent(name: str, section: str = "sec_delegation_policy") -> DelegationIntentFact:
    return DelegationIntentFact(
        name=name, text="Delegate something.",
        evidence=[EvidenceRef(source_section_id=section)],
    )


def _invoke_handoff(hid: str, to_worker: str | None = "w_child",
                    after_span: str = "s_del",
                    ) -> WorkerHandoffIR:
    return WorkerHandoffIR(
        handoff_id=hid, from_worker="w_main", to_worker=to_worker,
        api_ref=None, mode="invoke", condition_text=None, ordering="after",
        input_bindings=[InputBindingIR("a", "b", True)],
        output_bindings=[OutputBindingIR("c", "d", True, "set")],
        invoke_location_hint=InvokeLocationHintIR(
            flow_kind="main", flow_id=None,
            after_span_id=after_span, before_span_id=None,
            block_hint="unknown",
        ),
    )


class TestDelegationBridge:
    def test_no_intents_no_diagnostics(self) -> None:
        diags = bridge_delegation_intents([], [], [])
        assert diags == []

    def test_intent_without_handoff_emits_diagnostic(self) -> None:
        spans = [_span("s_del", "sec_delegation_policy")]
        diags = bridge_delegation_intents(
            [_dintent("source_gathering")], handoffs=None, spans=spans,
        )
        assert len(diags) == 1
        assert diags[0].kind == "type_or_contract_ambiguity"
        assert "source_gathering" in diags[0].message

    def test_invalid_handoff_still_emits_diagnostic(self) -> None:
        """Handoff with no to_worker -> not valid -> diagnostic emitted."""
        spans = [_span("s_del", "sec_delegation_policy")]
        h = _invoke_handoff("h1", to_worker=None)
        diags = bridge_delegation_intents(
            [_dintent("source_gathering")], handoffs=[h], spans=spans,
        )
        assert len(diags) == 1, "Invalid handoff must not suppress diagnostic"

    def test_handoff_without_bindings_emits_diagnostic(self) -> None:
        """Handoff with no IO bindings -> not valid -> diagnostic emitted."""
        spans = [_span("s_del", "sec_delegation_policy")]
        h = _invoke_handoff("h1")
        h.input_bindings = []
        diags = bridge_delegation_intents(
            [_dintent("source_gathering")], handoffs=[h], spans=spans,
        )
        assert len(diags) == 1

    def test_valid_invoke_handoff_suppresses_diagnostic(self) -> None:
        """Valid invoke handoff -> no diagnostic."""
        spans = [_span("s_del", "sec_delegation_policy")]
        h = _invoke_handoff("h1", to_worker="w_child")
        diags = bridge_delegation_intents(
            [_dintent("source_gathering")], handoffs=[h], spans=spans,
        )
        assert diags == []

    def test_ghost_worker_handoff_emits_diagnostic(self) -> None:
        """Handoff with to_worker not in known_child_worker_ids -> diagnostic."""
        spans = [_span("s_del", "sec_delegation_policy")]
        h = _invoke_handoff("h1", to_worker="ghost")
        diags = bridge_delegation_intents(
            [_dintent("source_gathering")], handoffs=[h], spans=spans,
            known_child_worker_ids={"w_child"},
        )
        assert len(diags) == 1


# =========================================================================
# Worker-scoped failure mode bridge
# =========================================================================


def _worker_plan(main_wid: str = "w_main") -> WorkerPlanIR:
    return WorkerPlanIR(
        main_worker_id=main_wid,
        workers=[
            WorkerSpecIR(
                worker_id=main_wid,
                worker_name="MainWorker",
                kind="main",
                purpose="Test main worker.",
                owned_span_ids=[],
            ),
        ],
    )


def _worker_flow_plan(
    main_wid: str = "w_main",
    main_flow: FlowStructureIR | None = None,
) -> WorkerFlowPlanIR:
    if main_flow is None:
        main_flow = FlowStructureIR()
    return WorkerFlowPlanIR(worker_flows={main_wid: main_flow})


class TestWorkerScopedFailureModeBridge:
    def test_single_failure_creates_exception_flow_for_main_worker(self) -> None:
        spans = [_span("s1", "sec_failure_handling")]
        facts = [_fact("missing_timeframe", "Missing timeframe.", "sec_failure_handling")]

        wp = _worker_plan()
        wfp = _worker_flow_plan()
        result = bridge_failure_modes_worker_scoped(facts, spans, wfp, wp)

        main_flow = result.worker_flows["w_main"]
        assert len(main_flow.exception_flows) == 1
        exc = main_flow.exception_flows[0]
        assert exc.flow_id == "exc_adapter_00"
        assert exc.condition_text == "Missing timeframe."
        assert "s1" in exc.spans

    def test_multiple_failure_modes_all_land_in_main_worker(self) -> None:
        spans = [
            _span("s24", "sec_failure_handling"),
            _span("s25", "sec_failure_handling"),
            _span("s26", "sec_failure_handling"),
            _span("s27", "sec_failure_handling"),
            _span("s28", "sec_failure_handling"),
            _span("s29", "sec_failure_handling"),
        ]
        facts = [
            _fact("missing_timeframe", "Missing timeframe.", "sec_failure_handling"),
            _fact("conflicting_instructions", "Conflicting instructions.", "sec_failure_handling"),
            _fact("insufficient_source", "Insufficient source access.", "sec_failure_handling"),
            _fact("evidence_shortage", "Evidence shortage.", "sec_failure_handling"),
            _fact("user_refusal", "User refusal to answer.", "sec_failure_handling"),
            _fact("provenance_failure", "Provenance failure.", "sec_failure_handling"),
        ]

        wp = _worker_plan()
        wfp = _worker_flow_plan()
        result = bridge_failure_modes_worker_scoped(facts, spans, wfp, wp)

        main_flow = result.worker_flows["w_main"]
        assert len(main_flow.exception_flows) == 6
        conditions = {exc.condition_text for exc in main_flow.exception_flows}
        assert "Missing timeframe." in conditions
        assert "Conflicting instructions." in conditions
        assert "Insufficient source access." in conditions
        assert "Evidence shortage." in conditions
        assert "User refusal to answer." in conditions
        assert "Provenance failure." in conditions

    def test_preserves_existing_worker_flows(self) -> None:
        existing_main_flow = FlowStructureIR(
            main_flow_spans=["s_main"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_existing",
                    condition_text="Already covered.",
                    spans=["s1"],
                ),
            ],
        )
        spans = [
            _span("s1", "sec_failure_handling"),
            _span("s2", "sec_other"),
        ]
        facts = [_fact("f_new", "New failure.", "sec_other")]

        wp = _worker_plan()
        wfp = _worker_flow_plan(main_flow=existing_main_flow)
        result = bridge_failure_modes_worker_scoped(facts, spans, wfp, wp)

        main_flow = result.worker_flows["w_main"]
        assert len(main_flow.exception_flows) == 2
        assert main_flow.exception_flows[0].flow_id == "exc_existing"
        assert main_flow.exception_flows[1].condition_text == "New failure."

    def test_does_not_mutate_input(self) -> None:
        spans = [_span("s1", "sec_failure_handling")]
        facts = [_fact("f1", "Fail.", "sec_failure_handling")]

        wfp = _worker_flow_plan()
        wp = _worker_plan()
        result = bridge_failure_modes_worker_scoped(facts, spans, wfp, wp)

        assert wfp.worker_flows["w_main"].exception_flows == []
        assert len(result.worker_flows["w_main"].exception_flows) == 1

    def test_dedup_by_normalized_condition_text(self) -> None:
        spans = [_span("s1", "sec_failure_handling")]
        existing = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    spans=["s1"],
                ),
            ]
        )
        facts = [_fact("f1", "Missing timeframe.", "sec_failure_handling")]

        wp = _worker_plan()
        wfp = _worker_flow_plan(main_flow=existing)
        result = bridge_failure_modes_worker_scoped(facts, spans, wfp, wp)

        main_flow = result.worker_flows["w_main"]
        assert len(main_flow.exception_flows) == 1

    def test_no_failure_modes_returns_unchanged(self) -> None:
        wfp = _worker_flow_plan()
        wp = _worker_plan()
        result = bridge_failure_modes_worker_scoped([], [], wfp, wp)
        assert result == wfp

    def test_main_worker_not_in_flow_plan_returns_unchanged(self) -> None:
        spans = [_span("s1", "sec_failure_handling")]
        facts = [_fact("f1", "Fail.", "sec_failure_handling")]

        # WorkerFlowPlanIR with a different worker, not w_main
        wfp = WorkerFlowPlanIR(worker_flows={"w_other": FlowStructureIR()})
        wp = _worker_plan(main_wid="w_main")
        result = bridge_failure_modes_worker_scoped(facts, spans, wfp, wp)

        assert result == wfp

    def test_uses_evidence_span_ids(self) -> None:
        spans = [
            _span("s_fail", "sec_failure_handling"),
            _span("s_other", "sec_other"),
        ]
        fact = _fact(
            "f1", "Specific failure.", "sec_failure_handling", span_ids=["s_fail"]
        )

        wp = _worker_plan()
        wfp = _worker_flow_plan()
        result = bridge_failure_modes_worker_scoped([fact], spans, wfp, wp)

        main_flow = result.worker_flows["w_main"]
        assert len(main_flow.exception_flows) == 1
        assert "s_fail" in main_flow.exception_flows[0].spans

    def test_preserves_other_worker_flows(self) -> None:
        """Only main worker flow gets augmented; child worker flows are untouched."""
        spans = [_span("s1", "sec_failure_handling")]
        facts = [_fact("f1", "Fail.", "sec_failure_handling")]

        child_flow = FlowStructureIR(main_flow_spans=["s_child"])
        wfp = WorkerFlowPlanIR(
            worker_flows={
                "w_main": FlowStructureIR(),
                "w_child": child_flow,
            }
        )
        wp = _worker_plan(main_wid="w_main")
        result = bridge_failure_modes_worker_scoped(facts, spans, wfp, wp)

        assert len(result.worker_flows["w_main"].exception_flows) == 1
        assert result.worker_flows["w_child"] == child_flow
