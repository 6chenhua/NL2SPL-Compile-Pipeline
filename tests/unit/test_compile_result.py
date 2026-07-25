"""Unit tests for compile_result.py and PipelineResult backward compatibility."""

from __future__ import annotations

from nl2spl.compiler.compile_result import (
    CompileAssumption,
    CompileResult,
    Completeness,
    DiagnosticKind,
    MissingSlot,
    Severity,
    TraceRelation,
)
from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord
from nl2spl.pipeline.orchestrator import PipelineResult


class TestMissingSlot:
    def test_minimal_construction(self) -> None:
        slot = MissingSlot(
            slot_name="handler_action",
            required_for="exception_flow:exc_1",
            reason="No handler step specified",
        )
        assert slot.slot_name == "handler_action"
        assert slot.required_for == "exception_flow:exc_1"
        assert slot.source_span_ids == []
        assert slot.suggested_question is None

    def test_with_question(self) -> None:
        slot = MissingSlot(
            slot_name="timeframe",
            required_for="variable:timeframe",
            reason="Required output needs timeframe input",
            suggested_question="What timeframe should the report cover?",
        )
        assert slot.suggested_question == "What timeframe should the report cover?"

    def test_with_source_spans(self) -> None:
        slot = MissingSlot(
            slot_name="api_target",
            required_for="step:st_api",
            reason="API call has no named target",
            source_span_ids=["s5", "s12"],
        )
        assert slot.source_span_ids == ["s5", "s12"]


class TestCompileAssumption:
    def test_minimal_construction(self) -> None:
        a = CompileAssumption(
            assumption_id="A001",
            target_ref="exception_flow:exc_1",
        )
        assert a.assumption_id == "A001"
        assert a.target_ref == "exception_flow:exc_1"
        assert a.source_span_ids == []
        assert a.text == ""
        assert a.reason == ""
        assert a.suggested_resolution is None
        assert a.related_missing_slot is None
        assert a.related_diagnostic_id is None

    def test_full_construction(self) -> None:
        a = CompileAssumption(
            assumption_id="A002",
            target_ref="step:st_synth",
            source_span_ids=["s8"],
            text="Ask user for missing timeframe.",
            reason="Handler is required but not specified in source.",
            suggested_resolution="Specify handler action for missing timeframe.",
            related_missing_slot="handler_action",
            related_diagnostic_id="diag_001",
        )
        assert a.text == "Ask user for missing timeframe."
        assert a.related_diagnostic_id == "diag_001"

    def test_default_factory_lists_do_not_share(self) -> None:
        a1 = CompileAssumption("A1", "step:st1")
        a2 = CompileAssumption("A2", "step:st2")
        a1.source_span_ids.append("s1")
        assert a2.source_span_ids == []


class TestCompileResult:
    def test_minimal_construction(self) -> None:
        r = CompileResult(spl_text="[DEFINE_WORKER: MainWorker]")
        assert r.spl_text == "[DEFINE_WORKER: MainWorker]"
        assert r.completeness == "complete"
        assert r.diagnostics == []
        assert r.traces == []
        assert r.assumptions == []
        assert r.adapter_warnings == []
        assert r.validation_errors == []
        assert r.validation_warnings == []
        assert r.readable_report == ""

    def test_partial_result(self) -> None:
        diag = CompileDiagnostic(
            diagnostic_id="D001",
            kind="missing_handler",
            severity="warning",
            message="No handler for exc_1",
            target_ref="exception_flow:exc_1",
        )
        trace = TraceRecord(
            target_ref="step:st1",
            source_span_ids=["s1"],
            relation="direct",
            explanation="From source.",
        )
        assumption = CompileAssumption(
            assumption_id="A001",
            target_ref="step:st_synth",
            text="Synthetic handler",
            reason="No source evidence",
        )
        r = CompileResult(
            spl_text="[DEFINE_WORKER: W]",
            completeness="partial",
            diagnostics=[diag],
            traces=[trace],
            assumptions=[assumption],
            adapter_warnings=["adapter: section missing"],
            validation_warnings=["SPL: undefined reference"],
            readable_report="Report text.",
        )
        assert r.completeness == "partial"
        assert len(r.diagnostics) == 1
        assert len(r.traces) == 1
        assert len(r.assumptions) == 1
        assert r.adapter_warnings == ["adapter: section missing"]
        assert r.readable_report == "Report text."

    def test_default_factory_lists_do_not_share(self) -> None:
        r1 = CompileResult(spl_text="")
        r2 = CompileResult(spl_text="")
        r1.diagnostics.append(
            CompileDiagnostic("D1", "missing_handler", "warning", "test")
        )
        assert r2.diagnostics == []

    def test_validation_errors_preserved(self) -> None:
        r = CompileResult(
            spl_text="bad spl",
            validation_errors=["Syntax error at line 5"],
            validation_warnings=["Unused variable x"],
        )
        assert len(r.validation_errors) == 1
        assert len(r.validation_warnings) == 1


class TestTypeAliases:
    def test_diagnostic_kind_literals(self) -> None:
        kinds: list[DiagnosticKind] = [
            "missing_handler",
            "missing_output_producer",
            "type_or_contract_ambiguity",
            "assumed_command_not_renderable",
            "unmapped_behavior_span",
            "missing_provenance",
        ]
        assert len(kinds) == 6

    def test_severity_literals(self) -> None:
        severities: list[Severity] = ["info", "warning", "error"]
        assert len(severities) == 3

    def test_completeness_literals(self) -> None:
        levels: list[Completeness] = ["complete", "partial", "blocked"]
        assert len(levels) == 3

    def test_trace_relation_literals(self) -> None:
        relations: list[TraceRelation] = ["direct", "normalized", "inferred", "assumed"]
        assert len(relations) == 4


class TestPipelineResultBackwardCompat:
    """Existing callers must see NO breaking changes."""

    def test_legacy_construction_still_works(self) -> None:
        """spl_text, errors, warnings are still positional."""
        r = PipelineResult(
            spl_text="[DEFINE_WORKER: W]",
            validation_errors=["e1"],
            validation_warnings=["w1"],
        )
        assert r.spl_text == "[DEFINE_WORKER: W]"
        assert r.validation_errors == ["e1"]
        assert r.validation_warnings == ["w1"]

    def test_compile_diagnostics_still_accessible(self) -> None:
        r = PipelineResult("", [], [])
        assert r.compile_diagnostics == []

    def test_new_fields_have_sane_defaults(self) -> None:
        r = PipelineResult("", [], [])
        assert r.completeness == "complete"
        assert r.assumptions == []
        assert r.readable_report == ""

    def test_diagnostics_alias_points_to_compile_diagnostics(self) -> None:
        r = PipelineResult("", [], [])
        diag = CompileDiagnostic("D1", "missing_handler", "warning", "test")
        r.compile_diagnostics.append(diag)
        assert r.diagnostics == [diag]
        assert r.diagnostics is r.compile_diagnostics

    def test_full_kwargs_still_work(self) -> None:
        r = PipelineResult(
            spl_text="spl",
            validation_errors=[],
            validation_warnings=[],
            compile_diagnostics=[],
            traces=[],
            adapter_warnings=[],
            intermediate_results={},
        )
        assert r.spl_text == "spl"
        assert r.completeness == "complete"

    def test_new_fields_accept_data(self) -> None:
        assumption = CompileAssumption("A1", "step:st1")
        r = PipelineResult(
            spl_text="spl",
            validation_errors=[],
            validation_warnings=[],
            completeness="partial",
            assumptions=[assumption],
            readable_report="Report",
        )
        assert r.completeness == "partial"
        assert len(r.assumptions) == 1
        assert r.readable_report == "Report"

    def test_compile_diagnostics_mutate_visible_via_diagnostics(self) -> None:
        r = PipelineResult("", [], [])
        diag = CompileDiagnostic("D2", "missing_output_producer", "warning", "test")
        r.compile_diagnostics.append(diag)
        assert len(r.diagnostics) == 1
        assert r.diagnostics[0].diagnostic_id == "D2"


class TestCompilerReExports:
    """Callers should be able to import everything from nl2spl.compiler."""

    def test_compile_diagnostic_re_exported(self) -> None:
        from nl2spl.compiler import CompileDiagnostic
        from nl2spl.ir.diagnostics import CompileDiagnostic as IRCompileDiagnostic

        assert CompileDiagnostic is IRCompileDiagnostic

    def test_trace_record_re_exported(self) -> None:
        from nl2spl.compiler import TraceRecord
        from nl2spl.ir.diagnostics import TraceRecord as IRTraceRecord

        assert TraceRecord is IRTraceRecord

    def test_step_render_info_re_exported(self) -> None:
        from nl2spl.compiler import StepRenderInfo

        assert StepRenderInfo is not None


class TestCompileDiagnosticMissingSlot:
    def test_default_missing_slot_is_none(self) -> None:
        d = CompileDiagnostic("D1", "missing_handler", "warning", "test")
        assert d.missing_slot is None

    def test_can_set_missing_slot(self) -> None:
        slot = MissingSlot("action", "exc_1", "No handler")
        d = CompileDiagnostic(
            "D1", "missing_handler", "warning", "test",
            missing_slot=slot,
        )
        assert d.missing_slot is slot
        assert d.missing_slot.slot_name == "action"
