"""Unit tests for compute_completeness (Phase 7)."""

from __future__ import annotations

from nl2spl.compiler.completeness import compute_completeness
from nl2spl.ir.diagnostics import CompileDiagnostic


class TestCompleteness:
    def test_clean_no_errors_no_diagnostics_is_complete(self) -> None:
        assert compute_completeness() == "complete"
        assert compute_completeness([], []) == "complete"

    def test_validation_errors_cause_blocked(self) -> None:
        result = compute_completeness(
            validation_errors=["Syntax error at line 5"],
            diagnostics=[],
        )
        assert result == "blocked"

    def test_diagnostics_cause_partial(self) -> None:
        diag = CompileDiagnostic(
            "D1", "missing_handler", "warning", "No handler for exc_1",
        )
        result = compute_completeness(diagnostics=[diag])
        assert result == "partial"

    def test_errors_and_diagnostics_still_blocked(self) -> None:
        diag = CompileDiagnostic(
            "D1", "missing_output_producer", "warning", "No producer.",
        )
        result = compute_completeness(
            validation_errors=["Reference error"],
            diagnostics=[diag],
        )
        assert result == "blocked"

    def test_multiple_diagnostics_still_partial(self) -> None:
        diags = [
            CompileDiagnostic("D1", "missing_handler", "warning", "m1"),
            CompileDiagnostic("D2", "missing_output_producer", "warning", "m2"),
            CompileDiagnostic("D3", "type_or_contract_ambiguity", "warning", "m3"),
            CompileDiagnostic("D4", "assumed_command_not_renderable", "warning", "m4"),
            CompileDiagnostic("D5", "unmapped_behavior_span", "warning", "m5"),
            CompileDiagnostic("D6", "missing_provenance", "warning", "m6"),
        ]
        assert compute_completeness(diagnostics=diags) == "partial"

    def test_none_params_treated_as_empty(self) -> None:
        assert compute_completeness(validation_errors=None, diagnostics=None) == "complete"


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------

class TestAcceptanceCriteria:
    def test_missing_handler_is_partial(self) -> None:
        diag = CompileDiagnostic("D1", "missing_handler", "warning", "test")
        assert compute_completeness(diagnostics=[diag]) == "partial"

    def test_missing_output_producer_is_partial(self) -> None:
        diag = CompileDiagnostic("D1", "missing_output_producer", "warning", "test")
        assert compute_completeness(diagnostics=[diag]) == "partial"

    def test_assumed_command_not_renderable_is_partial(self) -> None:
        diag = CompileDiagnostic("D1", "assumed_command_not_renderable", "warning", "test")
        assert compute_completeness(diagnostics=[diag]) == "partial"

    def test_validation_error_is_blocked(self) -> None:
        assert compute_completeness(validation_errors=["err"]) == "blocked"

    def test_clean_happy_path_is_complete(self) -> None:
        assert compute_completeness([], []) == "complete"

    def test_non_completion_blocking_diagnostic_keeps_complete(self) -> None:
        """missing_provenance has blocks_completion=False — must not cause partial."""
        diag = CompileDiagnostic(
            "D1", "missing_provenance", "warning", "No provenance.",
            blocks_completion=False,
        )
        assert compute_completeness(diagnostics=[diag]) == "complete"

    def test_mixed_blocking_and_non_blocking_is_partial(self) -> None:
        diags = [
            CompileDiagnostic(
                "D1", "missing_provenance", "warning", "No provenance.",
                blocks_completion=False,
            ),
            CompileDiagnostic(
                "D2", "missing_handler", "warning", "No handler.",
                blocks_completion=True,
            ),
        ]
        assert compute_completeness(diagnostics=diags) == "partial"
