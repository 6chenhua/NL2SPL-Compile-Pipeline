"""Unit tests for AssumptionBuilder (Phase 5)."""

from __future__ import annotations

from nl2spl.compiler.assumptions import AssumptionBuilder
from nl2spl.ir.diagnostics import CompileDiagnostic


# ---------------------------------------------------------------------------
# missing_handler
# ---------------------------------------------------------------------------

class TestMissingHandler:
    def test_generates_assumption(self) -> None:
        diag = CompileDiagnostic(
            "D001", "missing_handler", "warning",
            "Exception flow 'exc_1' has no handler.",
            target_ref="exception_flow:exc_1",
            source_span_ids=["s5"],
        )
        builder = AssumptionBuilder()
        asms = builder.build([diag])
        assert len(asms) == 1
        a = asms[0]
        assert a.target_ref == "exception_flow:exc_1"
        assert a.source_span_ids == ["s5"]
        assert a.related_diagnostic_id == "D001"
        assert "handler" in a.text.lower()
        assert "handler" in a.reason.lower()
        assert "handler" in a.suggested_resolution.lower()


# ---------------------------------------------------------------------------
# missing_output_producer
# ---------------------------------------------------------------------------

class TestMissingOutputProducer:
    def test_generates_assumption(self) -> None:
        diag = CompileDiagnostic(
            "D002", "missing_output_producer", "warning",
            "Required output 'report' has no producer.",
            target_ref="variable:report",
        )
        builder = AssumptionBuilder()
        asms = builder.build([diag])
        assert len(asms) == 1
        a = asms[0]
        assert a.target_ref == "variable:report"
        assert a.related_diagnostic_id == "D002"
        assert "producer" in a.text.lower()
        assert "output" in a.reason.lower()


# ---------------------------------------------------------------------------
# type_or_contract_ambiguity
# ---------------------------------------------------------------------------

class TestContractAmbiguity:
    def test_generates_assumption(self) -> None:
        diag = CompileDiagnostic(
            "D003", "type_or_contract_ambiguity", "warning",
            "Step 'st_api' has no integration_ref.",
            target_ref="step:st_api",
        )
        builder = AssumptionBuilder()
        asms = builder.build([diag])
        assert len(asms) == 1
        a = asms[0]
        assert a.target_ref == "step:st_api"
        assert a.related_diagnostic_id == "D003"
        assert "contract" in a.text.lower()


# ---------------------------------------------------------------------------
# assumed_command_not_renderable
# ---------------------------------------------------------------------------

class TestAssumedCommand:
    def test_generates_assumption(self) -> None:
        diag = CompileDiagnostic(
            "D004", "assumed_command_not_renderable", "warning",
            "Step 'st_synth' blocked from rendering.",
            target_ref="step:st_synth",
        )
        builder = AssumptionBuilder()
        asms = builder.build([diag])
        assert len(asms) == 1
        a = asms[0]
        assert a.target_ref == "step:st_synth"
        assert a.related_diagnostic_id == "D004"
        assert "source" in a.text.lower() or "blocked" in a.text.lower()


# ---------------------------------------------------------------------------
# unmapped_behavior_span
# ---------------------------------------------------------------------------

class TestUnmappedSpan:
    def test_generates_assumption(self) -> None:
        diag = CompileDiagnostic(
            "D005", "unmapped_behavior_span", "warning",
            "Behavior span 's99' was not mapped.",
            target_ref="span:s99",
            source_span_ids=["s99"],
        )
        builder = AssumptionBuilder()
        asms = builder.build([diag])
        assert len(asms) == 1
        a = asms[0]
        assert a.target_ref == "span:s99"
        assert a.related_diagnostic_id == "D005"
        assert "mapped" in a.text.lower() or "span" in a.text.lower()


# ---------------------------------------------------------------------------
# missing_provenance
# ---------------------------------------------------------------------------

class TestMissingProvenance:
    def test_generates_assumption(self) -> None:
        diag = CompileDiagnostic(
            "D006", "missing_provenance", "warning",
            "Variable 'orphan' has no provenance.",
            target_ref="variable:orphan",
        )
        builder = AssumptionBuilder()
        asms = builder.build([diag])
        assert len(asms) == 1
        a = asms[0]
        assert a.target_ref == "variable:orphan"
        assert a.related_diagnostic_id == "D006"
        assert "provenance" in a.text.lower() or "source" in a.reason.lower()


# ---------------------------------------------------------------------------
# Integration: multiple diagnostics
# ---------------------------------------------------------------------------

class TestMultiple:
    def test_all_kinds_produce_assumptions(self) -> None:
        diags = [
            CompileDiagnostic("D1", "missing_handler", "warning",
                              "No handler.", target_ref="exc:e1"),
            CompileDiagnostic("D2", "missing_output_producer", "warning",
                              "No producer.", target_ref="v:r"),
            CompileDiagnostic("D3", "type_or_contract_ambiguity", "warning",
                              "Ambiguous API.", target_ref="step:s1"),
            CompileDiagnostic("D4", "assumed_command_not_renderable", "warning",
                              "Blocked.", target_ref="step:s2"),
            CompileDiagnostic("D5", "unmapped_behavior_span", "warning",
                              "Unmapped.", target_ref="span:s3"),
            CompileDiagnostic("D6", "missing_provenance", "warning",
                              "No source.", target_ref="v:x"),
        ]
        builder = AssumptionBuilder()
        asms = builder.build(diags)
        assert len(asms) == 6
        # Each assumption links to exactly one diagnostic
        diag_ids = {a.related_diagnostic_id for a in asms}
        assert diag_ids == {"D1", "D2", "D3", "D4", "D5", "D6"}

    def test_unknown_kind_skipped(self) -> None:
        diag = CompileDiagnostic(
            "D_unknown", "some_future_kind", "info", "test",
            target_ref="x:y",
        )
        builder = AssumptionBuilder()
        assert builder.build([diag]) == []

    def test_empty_diagnostics(self) -> None:
        builder = AssumptionBuilder()
        assert builder.build([]) == []

    def test_default_factory_lists_not_shared(self) -> None:
        diag1 = CompileDiagnostic("A1", "missing_handler", "warning", "x",
                                  target_ref="e:e1")
        diag2 = CompileDiagnostic("A2", "missing_output_producer", "warning", "x",
                                  target_ref="v:r")
        builder = AssumptionBuilder()
        a1, a2 = builder.build([diag1, diag2])
        a1.source_span_ids.append("s1")
        assert a2.source_span_ids == []


# ---------------------------------------------------------------------------
# related_diagnostic_id linking
# ---------------------------------------------------------------------------

class TestRelatedDiagnosticId:
    def test_assumption_links_to_correct_diagnostic(self) -> None:
        """Each assumption's related_diagnostic_id matches the diagnostic
        that spawned it.  This prevents duplicate reporting of related items."""
        diags = [
            CompileDiagnostic("D_A", "missing_handler", "warning", "A",
                              target_ref="exc:e_a"),
            CompileDiagnostic("D_B", "missing_handler", "warning", "B",
                              target_ref="exc:e_b"),
        ]
        builder = AssumptionBuilder()
        asms = builder.build(diags)
        assert len(asms) == 2
        assert asms[0].related_diagnostic_id == "D_A"
        assert asms[1].related_diagnostic_id == "D_B"
        # Target refs match source diagnostics
        assert asms[0].target_ref == "exc:e_a"
        assert asms[1].target_ref == "exc:e_b"


# ---------------------------------------------------------------------------
# Assumption ID uniqueness
# ---------------------------------------------------------------------------

class TestIdUniqueness:
    def test_ids_are_sequential_and_unique(self) -> None:
        diags = [
            CompileDiagnostic(f"D{i}", "missing_handler", "warning", f"msg{i}",
                              target_ref=f"exc:e{i}")
            for i in range(5)
        ]
        builder = AssumptionBuilder()
        asms = builder.build(diags)
        ids = {a.assumption_id for a in asms}
        assert len(ids) == 5
        assert ids == {"ASM_0000", "ASM_0001", "ASM_0002", "ASM_0003", "ASM_0004"}
