"""Unit tests for PipelineResult MVP fields and orchestrator run path (Phase 9)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nl2spl.compiler.compile_result import CompileAssumption
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic, StepRenderInfo, TraceRecord
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import FlowRef, WorkerIR
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.pipeline.orchestrator import PipelineOrchestrator, PipelineResult
from nl2spl.pipeline.provenance import ProvenanceAggregator


class TestPipelineResultMvpFields:
    """PipelineResult must expose completeness, assumptions, readable_report."""

    def test_result_has_completeness(self) -> None:
        r = PipelineResult("spl", [], [])
        assert r.completeness == "complete"

    def test_result_has_assumptions(self) -> None:
        r = PipelineResult("spl", [], [])
        assert r.assumptions == []

    def test_result_has_readable_report(self) -> None:
        r = PipelineResult("spl", [], [])
        assert r.readable_report == ""

    def test_all_new_fields_populated_together(self) -> None:
        diags = [
            CompileDiagnostic("D1", "missing_handler", "warning",
                              "No handler.", target_ref="exc:e1"),
        ]
        asm = CompileAssumption(
            assumption_id="A1", target_ref="exc:e1",
            text="Add handler.", related_diagnostic_id="D1",
        )
        traces = [TraceRecord("s:s1", ["s1"], relation="direct")]
        r = PipelineResult(
            spl_text="[DEFINE_WORKER: W]",
            validation_errors=[],
            validation_warnings=["w1"],
            compile_diagnostics=diags,
            traces=traces,
            adapter_warnings=["aw1"],
            completeness="partial",
            assumptions=[asm],
            readable_report="Report content.",
        )
        assert r.completeness == "partial"
        assert len(r.assumptions) == 1
        assert r.assumptions[0].assumption_id == "A1"
        assert "Report content." in r.readable_report
        assert len(r.compile_diagnostics) == 1
        assert len(r.traces) == 1
        assert r.diagnostics is r.compile_diagnostics

    def test_backward_compat_still_works_with_new_fields_default(self) -> None:
        r = PipelineResult("spl", ["e1"], ["w1"])
        assert r.spl_text == "spl"
        assert r.validation_errors == ["e1"]
        assert r.completeness == "complete"
        assert r.assumptions == []
        assert r.readable_report == ""
        assert r.diagnostics == []

    def test_readable_report_written(self) -> None:
        diags = [
            CompileDiagnostic("D1", "missing_handler", "warning", "No handler."),
        ]
        asms = [
            CompileAssumption("A1", "e:e1", text="Add handler.",
                              related_diagnostic_id="D1"),
        ]
        traces = [TraceRecord("s:s1", relation="direct")]
        r = PipelineResult(
            spl_text="[DEFINE_WORKER: W]",
            validation_errors=[],
            validation_warnings=[],
            compile_diagnostics=diags,
            assumptions=asms,
            traces=traces,
            completeness="partial",
            readable_report="NL2SPL Compile Report\nStatus: partial\n...",
        )
        assert "NL2SPL Compile Report" in r.readable_report
        assert "Status: partial" in r.readable_report


# ---------------------------------------------------------------------------
# P2: orchestrator run() path regression
# ---------------------------------------------------------------------------

class TestOrchestratorRunPath:
    """Verify run() fills completeness, assumptions, readable_report."""

    def test_run_fills_mvp_fields_with_diagnostics(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from nl2spl.config import LLMConfig, PipelineConfig
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR

        config = PipelineConfig(
            llm=LLMConfig(api_key="sk-fake"),
            output_dir=Path("output"),
            run_name="test_run_path",
            enable_worker_boundary_planner=False,
        )

        # Diagnostic that Stage 7 would produce
        stage7_diag = CompileDiagnostic(
            "D_stage7", "unmapped_behavior_span", "warning",
            "Unmapped span s1.",
        )

        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage1",
            lambda s, *a, **kw: [SpanIR("s1", "Do work.")],
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage2",
            lambda s, *a, **kw: (FieldRouteIR(behavior=["s1"]), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage3",
            lambda s, *a, **kw: (
                [SpanIR("s1", "Do work.")], FieldRouteIR(behavior=["s1"]),
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage4",
            lambda s, *a, **kw: FlowStructureIR(),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage5",
            lambda s, *a, **kw: BlockStructureIR(),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage6",
            lambda s, *a, **kw: (ResourceRegistryIR(), SymbolTable(), []),
        )

        # Stage 7 — inject a diagnostic via the orchestrator's _run_stage7 wrapper
        def _fake_stage7(s, *a, **kw):
            s._test_stage7_diags = [stage7_diag]
            return (
                [StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
                SymbolTable(),
                [],
            )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage7", _fake_stage7,
        )

        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage8",
            lambda s, *a, **kw: AgentProfileIR(persona=PersonaIR(role="T")),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage9",
            lambda s, *a, **kw: [],
        )

        def _fake_stage10(s, *a, **kw):
            return WorkerIR(
                worker_name="MainWorker", description="Test",
                main_flow=FlowRef(),
                steps=[StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
            )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage10", _fake_stage10,
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage11",
            lambda s, *a, **kw: ("[DEFINE_WORKER: MainWorker]", [], []),
        )

        # Gate produces a diagnostic
        def _fake_gate_apply(g, worker, worker_plan=None):
            diag = CompileDiagnostic(
                "D_gate", "assumed_command_not_renderable", "warning",
                "Blocked.", target_ref="step:st_synth",
            )
            infos = [
                StepRenderInfo("st1", "source_backed", True),
            ]
            return worker, infos, [diag]
        monkeypatch.setattr(
            ExecutableElementGate, "apply", _fake_gate_apply,
        )

        # Provenance
        monkeypatch.setattr(
            ProvenanceAggregator, "aggregate",
            lambda s, **kw: (
                [TraceRecord("step:st1", ["s1"], relation="direct",
                             explanation="From source.")],
                [],
            ),
        )

        # Override the Stage 7 diagnostic extraction to use our injected value.
        # The orchestrator calls getattr(stage, "stage7_diagnostics", [])
        # but we patched _run_stage7 — the orchestrator's wrapper calls
        # stage.execute(...) and then reads stage.stage7_diagnostics.
        # Since we replaced _run_stage7 entirely, we need a different
        # approach: patch the orchestrator's _run_stage7 to return a 3-tuple.
        orig_run = PipelineOrchestrator.run

        # Simpler: just monkeypatch the run method's call to _run_stage7
        # to return (steps, symbols, [stage7_diag])
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage7",
            lambda s, *a, **kw: (
                [StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
                SymbolTable(),
                [stage7_diag],
            ),
        )

        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run("Do work.")

        assert result.completeness == "partial", (
            f"Expected partial, got {result.completeness}"
        )
        assert len(result.assumptions) > 0, (
            "Must produce assumptions from diagnostics"
        )
        assert "NL2SPL Compile Report" in result.readable_report
        assert "Status: partial" in result.readable_report

    def test_clean_run_is_complete(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from nl2spl.config import LLMConfig, PipelineConfig
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR

        config = PipelineConfig(
            llm=LLMConfig(api_key="sk-fake"),
            output_dir=Path("output"),
            run_name="test_clean",
            enable_worker_boundary_planner=False,
        )

        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage1",
            lambda s, *a, **kw: [SpanIR("s1", "Do work.")],
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage2",
            lambda s, *a, **kw: (FieldRouteIR(behavior=["s1"]), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage3",
            lambda s, *a, **kw: (
                [SpanIR("s1", "Do work.")], FieldRouteIR(behavior=["s1"]),
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage4",
            lambda s, *a, **kw: FlowStructureIR(),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage5",
            lambda s, *a, **kw: BlockStructureIR(),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage6",
            lambda s, *a, **kw: (ResourceRegistryIR(), SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage7",
            lambda s, *a, **kw: (
                [StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
                SymbolTable(),
                [],
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage8",
            lambda s, *a, **kw: AgentProfileIR(persona=PersonaIR(role="T")),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage9",
            lambda s, *a, **kw: [],
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage10",
            lambda s, *a, **kw: WorkerIR(
                worker_name="MainWorker", description="Test",
                main_flow=FlowRef(),
                steps=[StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage11",
            lambda s, *a, **kw: ("[DEFINE_WORKER: MainWorker]", [], []),
        )
        monkeypatch.setattr(
            ExecutableElementGate, "apply",
            lambda g, w, wp=None: (w, [], []),
        )
        monkeypatch.setattr(
            ProvenanceAggregator, "aggregate",
            lambda s, **kw: ([], []),
        )

        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run("Do work.")

        assert result.completeness == "complete"
        assert result.assumptions == []
        assert "Status: complete" in result.readable_report

    def test_structural_spans_produce_section_in_report(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """P1: Spans with source_section_id propagate through the REAL
        ProvenanceAggregator into the report.  No mock on aggregator --
        the test proves the full orchestrator-to-report chain."""
        from nl2spl.config import LLMConfig, PipelineConfig
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR

        config = PipelineConfig(
            llm=LLMConfig(api_key="sk-fake"),
            output_dir=Path("output"),
            run_name="test_section_prov",
            enable_worker_boundary_planner=False,
        )

        span = SpanIR(
            "s1", "Do work.",
            source_section_id="sec_reusable_process",
            source_packet_id="p_process_1",
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage1",
            lambda s, *a, **kw: [span],
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage2",
            lambda s, *a, **kw: (FieldRouteIR(behavior=["s1"]), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage3",
            lambda s, *a, **kw: ([span], FieldRouteIR(behavior=["s1"])),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage4",
            lambda s, *a, **kw: FlowStructureIR(),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage5",
            lambda s, *a, **kw: BlockStructureIR(),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage6",
            lambda s, *a, **kw: (ResourceRegistryIR(), SymbolTable(), []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage7",
            lambda s, *a, **kw: (
                [StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
                SymbolTable(),
                [],
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage8",
            lambda s, *a, **kw: AgentProfileIR(persona=PersonaIR(role="T")),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage9",
            lambda s, *a, **kw: [],
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage10",
            lambda s, *a, **kw: WorkerIR(
                worker_name="MainWorker", description="Test",
                main_flow=FlowRef(blocks=[
                    BlockIR("b1", "SEQUENTIAL", spans=["s1"]),
                ]),
                steps=[StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator, "_run_stage11",
            lambda s, *a, **kw: ("[DEFINE_WORKER: MainWorker]", [], []),
        )
        monkeypatch.setattr(
            ExecutableElementGate, "apply",
            lambda g, w, wp=None: (w, [], []),
        )
        # Capture kwargs passed to the real ProvenanceAggregator.aggregate
        captured_kwargs: dict = {}
        _orig_aggregate = ProvenanceAggregator.aggregate

        def _spy_aggregate(self, **kw):
            captured_kwargs.update(kw)
            return _orig_aggregate(self, **kw)

        monkeypatch.setattr(
            ProvenanceAggregator, "aggregate", _spy_aggregate,
        )

        orchestrator = PipelineOrchestrator(config)
        result = orchestrator.run("Do work.")

        # Report must contain section provenance from the real aggregator
        assert "section=sec_reusable_process" in result.readable_report, (
            f"Report missing section provenance:\n{result.readable_report[:600]}"
        )
        assert "packet=p_process_1" in result.readable_report
        assert result.completeness == "complete"
        # Verify the orchestrator passed variable_facts (empty for generic NL)
        assert "variable_facts" in captured_kwargs
        assert captured_kwargs["variable_facts"] == []


# ---------------------------------------------------------------------------
# P3: CLI report file writing regression
# ---------------------------------------------------------------------------

class TestCliReportFile:
    """Verify main.py writes report artifacts to run_dir."""

    def test_report_files_written(self, tmp_path: Path) -> None:
        from nl2spl import main as main_module

        fake_result = PipelineResult(
            spl_text="[DEFINE_WORKER: W]",
            validation_errors=[],
            validation_warnings=[],
            completeness="partial",
            compile_diagnostics=[
                CompileDiagnostic(
                    "D1", "missing_handler", "warning",
                    "No handler.", target_ref="exception_flow:exc_1",
                ),
            ],
            assumptions=[
                CompileAssumption("A1", "e:e1", text="Add handler."),
            ],
            traces=[
                TraceRecord(
                    "flow:exc_1",
                    ["s1"],
                    source_section_id="sec_failure_handling",
                    relation="direct",
                ),
            ],
            readable_report="NL2SPL Compile Report\nStatus: partial\n...",
        )

        class FakeConfig:
            run_dir = tmp_path

        with patch.object(
            main_module, "load_config", return_value=FakeConfig,
        ), patch.object(
            main_module, "PipelineOrchestrator",
        ) as mock_orch_class, patch.object(
            main_module.sys, "argv", ["nl2spl", str(tmp_path / "input.txt")],
        ):
            (tmp_path / "input.txt").write_text("Do work.", encoding="utf-8")
            mock_orch_class.return_value.run.return_value = fake_result
            with patch.object(main_module.sys, "stdout", MagicMock()), \
                 patch.object(main_module.sys, "stderr", MagicMock()):
                main_module.main()

        report_path = tmp_path / "compile_report.txt"
        assert report_path.exists(), f"compile_report.txt missing in {tmp_path}"
        content = report_path.read_text(encoding="utf-8")
        assert "NL2SPL Compile Report" in content
        assert "Status: partial" in content

        feedback_path = tmp_path / "feedback_report.md"
        assert feedback_path.exists(), f"feedback_report.md missing in {tmp_path}"
        feedback = feedback_path.read_text(encoding="utf-8")
        assert "NL2SPL Feedback Report" in feedback
        assert "Completeness: `partial`" in feedback
        assert "missing_handler" in feedback
        assert "section=`sec_failure_handling`" in feedback
