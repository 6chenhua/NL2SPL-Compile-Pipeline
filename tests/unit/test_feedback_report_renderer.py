"""Unit tests for the Markdown feedback report renderer."""

from __future__ import annotations

from nl2spl.compiler.compile_result import CompileAssumption
from nl2spl.compiler.feedback_report_renderer import render_feedback_report
from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord


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
