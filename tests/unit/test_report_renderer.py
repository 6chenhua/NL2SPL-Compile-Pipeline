"""Unit tests for ReportRenderer (Phase 8)."""

from __future__ import annotations

from nl2spl.compiler.compile_result import CompileAssumption, MissingSlot
from nl2spl.compiler.report_renderer import render_report
from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord


class TestReportSections:
    def test_empty_report_still_produces_header_and_spl(self) -> None:
        report = render_report(spl_text="[DEFINE_WORKER: MainWorker]")
        assert "NL2SPL Compile Report" in report
        assert "Status: complete" in report
        assert "[DEFINE_WORKER: MainWorker]" in report

    def test_completeness_in_summary(self) -> None:
        report = render_report("", completeness="partial")
        assert "Status: partial" in report

    def test_diagnostics_section_present_when_diags_exist(self) -> None:
        diag = CompileDiagnostic(
            "D001", "missing_handler", "warning",
            "Exception flow 'exc_1' has no handler step.",
            target_ref="exception_flow:exc_1",
            source_span_ids=["s5"],
            suggested_resolution="Add a handler step for 'Missing timeframe'.",
        )
        report = render_report("spl", diagnostics=[diag])
        assert "Diagnostics" in report
        assert "[WARNING] [missing_handler] D001" in report
        assert "exception_flow:exc_1" in report
        assert "s5" in report
        assert "Suggested:" in report

    def test_assumptions_section_present(self) -> None:
        asm = CompileAssumption(
            assumption_id="ASM_0000",
            target_ref="exception_flow:exc_1",
            text="Exception flow has no handler.",
            reason="Source does not specify handler.",
            suggested_resolution="Specify handler action.",
            related_diagnostic_id="D001",
        )
        report = render_report("spl", assumptions=[asm])
        assert "Assumptions / Suggestions" in report
        assert "[ASM_0000]" in report
        assert "Specify handler action." in report

    def test_assumption_links_related_diagnostic(self) -> None:
        diag = CompileDiagnostic(
            "D001", "missing_handler", "warning",
            "No handler for exc_1.",
        )
        asm = CompileAssumption(
            assumption_id="ASM_0000",
            target_ref="exception_flow:exc_1",
            text="No handler.",
            related_diagnostic_id="D001",
        )
        report = render_report("spl", diagnostics=[diag], assumptions=[asm])
        assert "Related diagnostic:" in report
        assert "D001" in report.split("Related diagnostic:")[1]

    def test_traces_section_present(self) -> None:
        trace = TraceRecord(
            target_ref="step:st1",
            source_span_ids=["s1"],
            relation="direct",
            explanation="From source.",
        )
        report = render_report("spl", traces=[trace])
        assert "Provenance Traces" in report
        assert "[direct] step:st1" in report
        assert "spans=s1" in report

    def test_trace_needs_confirmation_shown(self) -> None:
        trace = TraceRecord(
            target_ref="variable:x",
            relation="assumed",
            explanation="No evidence.",
            needs_confirmation=True,
        )
        report = render_report("spl", traces=[trace])
        assert "[needs confirmation]" in report

    def test_adapter_warnings_section_present(self) -> None:
        report = render_report("spl", adapter_warnings=["Section missing: behavior"])
        assert "Adapter Warnings" in report
        assert "Section missing: behavior" in report

    def test_validation_errors_and_warnings_shown(self) -> None:
        report = render_report(
            "bad spl",
            validation_errors=["Syntax error at line 5"],
            validation_warnings=["Unused variable x"],
        )
        assert "Validation" in report
        assert "Syntax error at line 5" in report
        assert "Unused variable x" in report

    def test_diagnostics_sorted_by_severity_then_kind(self) -> None:
        diags = [
            CompileDiagnostic("D3", "missing_output_producer", "warning", "msg3"),
            CompileDiagnostic("D1", "missing_handler", "error", "msg1"),
            CompileDiagnostic("D2", "missing_handler", "warning", "msg2"),
        ]
        report = render_report("spl", diagnostics=diags)
        lines = report.split("\n")
        diag_lines = [line for line in lines if line.strip().startswith("[")]
        severities = [
            line.strip()
            for line in diag_lines
            if line.strip().startswith("[")
        ]
        # error before warning
        assert "ERROR" in severities[0]
        assert "WARNING" in severities[1] or "WARNING" in severities[2]

    def test_summary_counts(self) -> None:
        report = render_report(
            "spl",
            completeness="partial",
            diagnostics=[
                CompileDiagnostic("D1", "missing_handler", "warning", "m1"),
                CompileDiagnostic("D2", "missing_output_producer", "error", "m2"),
            ],
            assumptions=[CompileAssumption("A1", "e:e1")],
            traces=[TraceRecord("s:s1", relation="direct")],
            adapter_warnings=["w1", "w2"],
            validation_errors=["e1"],
            validation_warnings=["w1"],
        )
        assert "Adapter warnings: 2" in report
        assert "Diagnostics: 1 error(s), 1 warning(s)" in report
        assert "Assumptions (not rendered): 1" in report
        assert "Trace records: 1" in report
        assert "Validation errors: 1" in report
        assert "Validation warnings: 1" in report

    def test_missing_slot_in_diagnostic(self) -> None:
        slot = MissingSlot(
            slot_name="handler_action",
            required_for="exception_flow:exc_1",
            reason="No handler specified.",
            suggested_question="What should happen on failure?",
        )
        diag = CompileDiagnostic(
            "D1", "missing_handler", "warning", "No handler.",
            missing_slot=slot,
        )
        report = render_report("spl", diagnostics=[diag])
        assert "Missing: handler_action" in report
        assert "Question: What should happen on failure?" in report

    def test_no_spl_text_shown(self) -> None:
        report = render_report("")
        assert "(no SPL generated)" in report


class TestP2Fixes:
    def test_blocked_with_validation_error_no_spl_still_shows_no(self) -> None:
        """P2a: blocked + validation_errors + empty spl_text → 'no'."""
        report = render_report(
            "", completeness="blocked",
            validation_errors=["Syntax error"],
        )
        assert "SPL draft generated: no" in report

    def test_traces_sorted_for_stable_output(self) -> None:
        """P2b: traces sorted by (target_ref, relation, source_span_ids)."""
        traces = [
            TraceRecord("s:c", ["s3"], relation="inferred", explanation=""),
            TraceRecord("s:a", ["s1"], relation="direct", explanation=""),
            TraceRecord("s:b", ["s2"], relation="assumed", explanation=""),
        ]
        r1 = render_report("spl", traces=traces)
        r2 = render_report("spl", traces=list(reversed(traces)))
        assert r1 == r2
        # "s:a" (direct) should appear before "s:c" (inferred) in sorted output
        idx_a = r1.find("s:a")
        idx_b = r1.find("s:b")
        idx_c = r1.find("s:c")
        assert idx_a < idx_b < idx_c, "Traces not sorted by target_ref"


class TestSnapshotStability:
    """Report output must be stable — exact-text or snapshot-safe."""

    def test_deterministic_output(self) -> None:
        """Same inputs → identical output."""
        diag = CompileDiagnostic("D1", "missing_handler", "warning", "test",
                                 target_ref="e:e1")
        trace = TraceRecord("s:s1", ["s1"], relation="direct")
        r1 = render_report("spl", diagnostics=[diag], traces=[trace])
        r2 = render_report("spl", diagnostics=[diag], traces=[trace])
        assert r1 == r2

    def test_skeleton_sections_always_in_same_order(self) -> None:
        report = render_report(
            "spl", completeness="partial",
            diagnostics=[CompileDiagnostic("D1", "missing_handler", "warning", "m")],
            assumptions=[CompileAssumption("A1", "e:e1")],
            traces=[TraceRecord("s:s1", relation="direct")],
            adapter_warnings=["w1"],
            validation_errors=["e1"],
        )
        # Use the section header + underline pattern to avoid matching
        # summary-field substrings like "Adapter warnings: 1"
        sections = [
            "NL2SPL Compile Report",
            "\nStatus:",
            "\nAdapter Warnings\n" + "-" * 40,
            "\nDiagnostics\n" + "-" * 40,
            "\nAssumptions / Suggestions\n" + "-" * 40,
            "\nProvenance Traces\n" + "-" * 40,
            "\nValidation\n" + "-" * 40,
            "\nGenerated SPL\n" + "-" * 40,
        ]
        prev_idx = -1
        for section in sections:
            idx = report.find(section)
            assert idx > prev_idx, f"Section '{section.strip()}' out of order (idx={idx}, prev={prev_idx})"
            prev_idx = idx
