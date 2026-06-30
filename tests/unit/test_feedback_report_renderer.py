"""Unit tests for the Markdown feedback report renderer."""

from __future__ import annotations

from nl2spl.compiler.compile_result import CompileAssumption, MissingSlot
from nl2spl.compiler.feedback_report_renderer import render_feedback_report
from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord

PROMOTION_SLOTS = (
    "promotion_input_contract",
    "promotion_output_contract",
    "promotion_invocation_point",
    "promotion_result_handoff",
)


def _promotion_diag(
    slot_name: str,
    diagnostic_id: str,
    *,
    target: str = "worker_promotion:candidate_retrieve_sources_with_provenance",
    spans: list[str] | None = None,
) -> CompileDiagnostic:
    source_spans = spans or ["s15d", "s15e", "s16a"]
    return CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind="type_or_contract_ambiguity",
        severity="warning",
        message=f"Missing {slot_name}",
        target_ref=target,
        source_span_ids=list(source_spans),
        missing_slot=MissingSlot(
            slot_name=slot_name,
            required_for="complete",
            reason=f"Missing {slot_name}",
            source_span_ids=list(source_spans),
        ),
        blocks_rendering=False,
        blocks_completion=True,
    )


def _promotion_diags(
    *,
    target: str = "worker_promotion:candidate_retrieve_sources_with_provenance",
    spans: list[str] | None = None,
    id_prefix: str = "D_PROMO",
) -> list[CompileDiagnostic]:
    return [
        _promotion_diag(slot, f"{id_prefix}_{index}", target=target, spans=spans)
        for index, slot in enumerate(PROMOTION_SLOTS)
    ]


def _child_worker_partial_diag() -> CompileDiagnostic:
    return CompileDiagnostic(
        diagnostic_id="D_CHILD_PARTIAL",
        kind="type_or_contract_ambiguity",
        severity="warning",
        message="Child worker input contract is incomplete.",
        target_ref="child_worker:worker_child",
        source_span_ids=["s2"],
        missing_slot=MissingSlot(
            slot_name="input_contract",
            required_for="complete",
            reason="Input contract is unknown.",
            source_span_ids=["s2"],
        ),
        metadata={
            "irs_ref": {
                "construct_type": "CHILD_WORKER",
                "construct_id": "child_worker:worker_child",
                "slot_name": "input_contract",
                "construct_path": ["worker_plan", "workers", "worker_child"],
                "source_authority": "stage_local_irs",
            }
        },
        blocks_rendering=False,
        blocks_completion=True,
    )


def _assumption_for(diag: CompileDiagnostic, index: int) -> CompileAssumption:
    return CompileAssumption(
        assumption_id=f"ASM_{index:04d}",
        target_ref=diag.target_ref or "",
        text="Command has an ambiguous or incomplete contract.",
        reason="Contract detail is missing.",
        suggested_resolution="Provide the missing contract detail.",
        related_diagnostic_id=diag.diagnostic_id,
    )


class TestFeedbackReportRenderer:
    def test_partial_report_explains_missing_handler(self) -> None:
        diag = CompileDiagnostic(
            diagnostic_id="D001",
            kind="missing_handler",
            severity="warning",
            message="Exception flow has no handler step.",
            target_ref="exception_flow:exc_1",
            source_span_ids=["s_failure"],
            suggested_resolution="Specify the handler action.",
            blocks_completion=True,
        )
        report = render_feedback_report(
            spl_text="[EXCEPTION_FLOW: Missing timeframe]\n[END_EXCEPTION_FLOW]",
            completeness="partial",
            diagnostics=[diag],
            assumptions=[
                CompileAssumption(
                    assumption_id="ASM_001",
                    target_ref="exception_flow:exc_1",
                    text="Add a source-backed handler action.",
                    related_diagnostic_id="D001",
                ),
            ],
            traces=[
                TraceRecord(
                    target_ref="flow:exc_1",
                    source_span_ids=["s_failure"],
                    source_section_id="sec_failure_handling",
                    source_packet_id="p_failure_1",
                    relation="direct",
                ),
            ],
        )

        assert "# NL2SPL Feedback Report" in report
        assert "Completeness: `partial`" in report
        assert "missing_handler" in report
        assert "Exception conditions without handler action" in report
        assert "section=`sec_failure_handling`" in report
        assert "```spl" in report

    def test_missing_output_producer_explains_no_synthetic_producer(self) -> None:
        diag = CompileDiagnostic(
            diagnostic_id="D002",
            kind="missing_output_producer",
            severity="warning",
            message="Required output has no source-backed producer.",
            target_ref="variable:final_report",
            blocks_completion=True,
        )
        report = render_feedback_report(
            spl_text="[OUTPUTS]\n    final_report\n[END_OUTPUTS]",
            completeness="partial",
            diagnostics=[diag],
        )

        assert "Required outputs without a source-backed producer" in report
        assert "no synthetic producer command is invented" in report
        assert "variable:final_report" in report

    def test_clean_report_still_has_feedback_sections(self) -> None:
        report = render_feedback_report(
            spl_text="[DEFINE_WORKER: MainWorker]",
            completeness="complete",
            traces=[
                TraceRecord(
                    target_ref="worker:MainWorker",
                    relation="inferred",
                    explanation="Main worker from task.",
                ),
            ],
        )

        assert "No completion-blocking diagnostic was emitted." in report
        assert "Materialized Source-Backed Structure" in report
        assert "worker:MainWorker" in report
        assert "No report-only assumptions were generated." in report

    def test_semantic_conflict_rendered_in_feedback_report(self) -> None:
        diag = CompileDiagnostic(
            diagnostic_id="SC001",
            kind="semantic_conflict",
            severity="warning",
            message="Likely conflict between policy 'Do not invent' and step 'Generate content'.",
            target_ref="step:st_1",
            source_span_ids=["s1", "s2"],
            blocks_completion=False,
        )
        report = render_feedback_report(
            spl_text="[COMMAND Generate content RESULT draft: text SET]",
            completeness="complete",
            diagnostics=[diag],
            assumptions=[],
            traces=[
                TraceRecord(
                    target_ref="step:st_1",
                    source_span_ids=["s1", "s2"],
                    relation="direct",
                ),
            ],
        )
        assert "semantic_conflict" in report
        assert "step:st_1" in report
        assert "s1" in report


# ===========================================================================
# D7: Route-derived exception flow evidence in feedback report
# ===========================================================================


def test_d7_feedback_report_names_failure_condition_and_evidence() -> None:
    """D7: feedback report shows failure condition + section/packet/span evidence."""
    diag = CompileDiagnostic(
        diagnostic_id="MH001",
        kind="missing_handler",
        severity="warning",
        message="Exception flow 'exc_adapter_00': Missing timeframe. has no handler.",
        target_ref="exception_flow:exc_adapter_00",
        source_span_ids=["s_fail"],
        blocks_completion=True,
    )
    report = render_feedback_report(
        spl_text="[EXCEPTION_FLOW: Missing timeframe]\n[END_EXCEPTION_FLOW]",
        completeness="partial",
        diagnostics=[diag],
        assumptions=[],
        traces=[
            TraceRecord(
                target_ref="flow:exc_adapter_00",
                source_span_ids=["s_fail"],
                source_section_id="sec_failure_handling",
                source_packet_id="p_failure_mode_missing",
                relation="direct",
                explanation="Exception flow 'exc_adapter_00': Missing timeframe.",
            ),
        ],
    )
    assert "Missing timeframe" in report
    assert "exc_adapter_00" in report
    assert "s_fail" in report
    assert "sec_failure_handling" in report
    assert "p_failure_mode_missing" in report
    # Diagnostic details section has exactly one MH001 entry
    diag_section = report.split("## 4. Diagnostics")[1].split("## 5.")[0]
    assert diag_section.count("MH001") == 1, (
        "Exactly one missing_handler diagnostic entry for exc_adapter_00"
    )


def test_r10_phase6_source_signal_section_rendered() -> None:
    """R10 Phase 6: source_signal:delegation_intent:* traces appear in
    the materialized section under 'Source Signals', NOT 'Delegation Intents'."""
    trace = TraceRecord(
        target_ref="source_signal:delegation_intent:source_gathering",
        source_span_ids=["s_del_1"],
        source_section_id="sec_delegation_policy",
        relation="inferred",
        explanation="Delegation intent 'source_gathering': Source gathering text",
    )

    report = render_feedback_report(
        spl_text="// SPL",
        traces=[trace],
        diagnostics=[],
        assumptions=[],
    )

    # Must contain Source Signals section
    assert "### Source Signals" in report, (
        f"Expected '### Source Signals' in report:\n{report}"
    )
    # Must contain the trace target
    assert "source_signal:delegation_intent:source_gathering" in report
    # Must contain the source spans
    assert "s_del_1" in report
    # Must NOT contain the old Delegation Intents section
    assert "### Delegation Intents" not in report, (
        "R10 Phase 6: 'Delegation Intents' section must not appear"
    )


def test_r10_phase6_multiple_source_signals_render_together() -> None:
    """R10 Phase 6: multiple source_signal: traces group under one section."""
    traces = [
        TraceRecord(
            target_ref="source_signal:delegation_intent:src_gathering",
            source_span_ids=["s1"],
            relation="inferred",
            explanation="Delegation intent 'src_gathering'",
        ),
        TraceRecord(
            target_ref="source_signal:delegation_intent:template_matching",
            source_span_ids=["s2"],
            relation="inferred",
            explanation="Delegation intent 'template_matching'",
        ),
    ]

    report = render_feedback_report(
        spl_text="// SPL",
        traces=traces,
        diagnostics=[],
        assumptions=[],
    )

    assert "### Source Signals" in report
    assert "source_signal:delegation_intent:src_gathering" in report
    assert "source_signal:delegation_intent:template_matching" in report
    # Check section only appears once
    assert report.count("### Source Signals") == 1


def test_worker_promotion_diagnostics_grouped_in_report_sections() -> None:
    """Same worker promotion target/source renders as one grouped block."""
    diags = _promotion_diags()

    report = render_feedback_report(
        spl_text="// SPL",
        completeness="partial",
        diagnostics=diags,
        assumptions=[],
    )

    assert "- Compile diagnostics: `4`" in report

    partial_section = report.split("## 3. Not Materialized / Kept Partial")[1].split(
        "## 4. Diagnostics"
    )[0]
    assert partial_section.count(
        "`worker_promotion:candidate_retrieve_sources_with_provenance`"
    ) == 1
    assert "WORKER_PROMOTION blocked by missing promotion slots" in partial_section

    diag_section = report.split("## 4. Diagnostics")[1].split(
        "## 5. Assumptions / Suggestions"
    )[0]
    assert diag_section.count(
        "Target: `worker_promotion:candidate_retrieve_sources_with_provenance`"
    ) == 1
    assert diag_section.count("### grouped:worker_promotion:") == 1
    for diag in diags:
        assert diag.diagnostic_id in diag_section
    for slot in PROMOTION_SLOTS:
        assert diag_section.count(f"`{slot}`") == 1


def test_child_worker_partial_definition_wording_distinct_from_blocked_invocation() -> None:
    report = render_feedback_report(
        spl_text="[WORKER: Child]\n[INPUTS]\n[OUTPUTS]\n[MAIN_FLOW]\n[END_WORKER]",
        completeness="partial",
        diagnostics=[_child_worker_partial_diag()],
        assumptions=[],
    )

    assert "Partial child worker definition can render" in report
    assert "child worker skeleton is renderable" in report
    assert "no executable worker invocation is invented" in report
    assert "WORKER_PROMOTION blocked" not in report
    assert "blocked invocation" not in report


def test_worker_promotion_assumptions_grouped_by_related_diagnostics() -> None:
    diags = _promotion_diags()
    assumptions = [_assumption_for(diag, index) for index, diag in enumerate(diags)]

    report = render_feedback_report(
        spl_text="// SPL",
        completeness="partial",
        diagnostics=diags,
        assumptions=assumptions,
    )

    assumption_section = report.split("## 6. Assumptions / Suggestions")[1].split(
        "## 7. Provenance / TraceRecords"
    )[0]
    assert assumption_section.count(
        "for `worker_promotion:candidate_retrieve_sources_with_provenance`"
    ) == 1
    assert "Worker promotion has an incomplete contract" in assumption_section
    assert "Related diagnostics:" in assumption_section
    for diag in diags:
        assert diag.diagnostic_id in assumption_section
    for assumption in assumptions:
        assert assumption.assumption_id in assumption_section


def test_worker_promotion_diagnostics_with_different_targets_not_grouped_together() -> None:
    diags = (
        _promotion_diags(target="worker_promotion:candidate_a", id_prefix="D_A")[:2]
        + _promotion_diags(target="worker_promotion:candidate_b", id_prefix="D_B")[:2]
    )

    report = render_feedback_report(
        spl_text="// SPL",
        completeness="partial",
        diagnostics=diags,
    )

    diag_section = report.split("## 4. Diagnostics")[1].split(
        "## 5. Assumptions / Suggestions"
    )[0]
    assert diag_section.count("### grouped:worker_promotion:") == 2
    assert diag_section.count("Target: `worker_promotion:candidate_a`") == 1
    assert diag_section.count("Target: `worker_promotion:candidate_b`") == 1


def test_worker_promotion_diagnostics_with_different_sources_not_grouped_together() -> None:
    target = "worker_promotion:candidate_same"
    diags = (
        _promotion_diags(target=target, spans=["s1"], id_prefix="D_S1")[:2]
        + _promotion_diags(target=target, spans=["s2"], id_prefix="D_S2")[:2]
    )

    report = render_feedback_report(
        spl_text="// SPL",
        completeness="partial",
        diagnostics=diags,
    )

    diag_section = report.split("## 4. Diagnostics")[1].split(
        "## 5. Assumptions / Suggestions"
    )[0]
    assert diag_section.count("### grouped:worker_promotion:") == 2
    assert diag_section.count("Target: `worker_promotion:candidate_same`") == 2
    assert "Source spans: `s1`" in diag_section
    assert "Source spans: `s2`" in diag_section


def test_regular_type_or_contract_ambiguity_remains_ungrouped() -> None:
    diag = CompileDiagnostic(
        diagnostic_id="D_ORDINARY",
        kind="type_or_contract_ambiguity",
        severity="warning",
        message="Missing API name",
        target_ref="step:call_api_1",
        source_span_ids=["s_api"],
        missing_slot=MissingSlot(
            slot_name="api_name",
            required_for="complete",
            reason="Missing API name",
            source_span_ids=["s_api"],
        ),
        blocks_completion=True,
    )

    report = render_feedback_report(
        spl_text="// SPL",
        completeness="partial",
        diagnostics=[diag],
    )

    diag_section = report.split("## 4. Diagnostics")[1].split(
        "## 5. Assumptions / Suggestions"
    )[0]
    assert "### D_ORDINARY: `type_or_contract_ambiguity`" in diag_section
    assert "### grouped:worker_promotion:" not in diag_section
    assert "Target: `step:call_api_1`" in diag_section
