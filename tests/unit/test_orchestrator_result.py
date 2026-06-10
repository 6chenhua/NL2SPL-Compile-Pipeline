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
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, WorkerScopedResourceIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import FlowRef, WorkerIR
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.pipeline.orchestrator import PipelineOrchestrator, PipelineResult
from nl2spl.pipeline.provenance import ProvenanceAggregator


class TestPipelineResultMvpFields:
    """PipelineResult must expose completeness and feedback diagnostics."""

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

    def test_readable_report_compat_field_can_be_populated(self) -> None:
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
    """Verify run() fills completeness, assumptions, and diagnostics."""

    def _worker_plan(self, owned_span_ids: list[str]) -> WorkerPlanIR:
        return WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    "worker_main", "MainWorker", "main", "Main worker",
                    owned_span_ids, [], [], [], [], "main_worker", [], "",
                )
            ],
            candidates=[],
            decisions=[],
            handoffs=[],
        )

    def _patch_worker_aware_stages(
        self,
        monkeypatch: pytest.MonkeyPatch,
        spans: list[SpanIR],
        stage7_diagnostics: list[CompileDiagnostic] | None = None,
        worker: WorkerIR | None = None,
    ) -> None:
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR

        span_ids = [span.span_id for span in spans]
        worker_plan = self._worker_plan(span_ids)
        worker_flow_plan = WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR(main_flow_spans=span_ids)}
        )
        worker_block_plan = WorkerBlockPlanIR(
            worker_blocks={
                "worker_main": BlockStructureIR(
                    main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", spans=span_ids)]
                )
            }
        )
        worker_step_plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    StepIR("st1", "Do work", span_ids, "GENERAL_COMMAND")
                ]
            },
        )
        result_worker = worker or WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(blocks=[BlockIR("b1", "SEQUENTIAL", spans=span_ids)]),
            steps=[StepIR("st1", "Do work", span_ids, "GENERAL_COMMAND")],
        )

        monkeypatch.setattr(PipelineOrchestrator, "_run_stage3_5", lambda s, *a, **kw: worker_plan)
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage4", lambda s, *a, **kw: worker_flow_plan)
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage5", lambda s, *a, **kw: worker_block_plan)
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage6_worker_scoped",
            lambda s, *a, **kw: (
                WorkerScopedResourceIR(global_resources=ResourceRegistryIR()),
                SymbolTable(),
                [],
            ),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage7_worker_scoped",
            lambda s, *a, **kw: (worker_step_plan, SymbolTable(), stage7_diagnostics or []),
        )
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_stage8",
            lambda s, *a, **kw: AgentProfileIR(persona=PersonaIR(role="T")),
        )
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage9", lambda s, *a, **kw: [])
        monkeypatch.setattr(
            PipelineOrchestrator,
            "_run_normalization_worker_scoped",
            lambda s, *a, **kw: (worker_flow_plan, worker_block_plan, worker_step_plan, SymbolTable(), [], []),
        )
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage10_worker_scoped", lambda s, *a, **kw: result_worker)
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage11", lambda s, *a, **kw: ("[DEFINE_WORKER: MainWorker]", [], []))

    def test_run_fills_mvp_fields_with_diagnostics(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from nl2spl.config import LLMConfig, PipelineConfig

        config = PipelineConfig(llm=LLMConfig(api_key="sk-fake"), output_dir=Path("output"), run_name="test_run_path")
        span = SpanIR("s1", "Do work.")
        stage7_diag = CompileDiagnostic("D_stage7", "unmapped_behavior_span", "warning", "Unmapped span s1.")
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage1", lambda s, *a, **kw: [span])
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage2", lambda s, *a, **kw: (FieldRouteIR(behavior=["s1"]), []))
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage3", lambda s, *a, **kw: ([span], FieldRouteIR(behavior=["s1"])))
        self._patch_worker_aware_stages(monkeypatch, [span], [stage7_diag])

        def _fake_gate_apply(g, worker, worker_plan=None):
            diag = CompileDiagnostic("D_gate", "assumed_command_not_renderable", "warning", "Blocked.", target_ref="step:st_synth")
            return worker, [StepRenderInfo("st1", "source_backed", True)], [diag]

        monkeypatch.setattr(ExecutableElementGate, "apply", _fake_gate_apply)
        monkeypatch.setattr(ProvenanceAggregator, "aggregate", lambda s, **kw: ([TraceRecord("step:st1", ["s1"], relation="direct", explanation="From source.")], []))
        result = PipelineOrchestrator(config).run("Do work.")
        assert result.completeness == "partial"
        assert len(result.assumptions) > 0
        assert result.readable_report == ""

    def test_clean_run_is_complete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from nl2spl.config import LLMConfig, PipelineConfig

        config = PipelineConfig(llm=LLMConfig(api_key="sk-fake"), output_dir=Path("output"), run_name="test_clean")
        span = SpanIR("s1", "Do work.")
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage1", lambda s, *a, **kw: [span])
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage2", lambda s, *a, **kw: (FieldRouteIR(behavior=["s1"]), []))
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage3", lambda s, *a, **kw: ([span], FieldRouteIR(behavior=["s1"])))
        self._patch_worker_aware_stages(monkeypatch, [span])
        monkeypatch.setattr(ExecutableElementGate, "apply", lambda g, w, wp=None: (w, [], []))
        monkeypatch.setattr(ProvenanceAggregator, "aggregate", lambda s, **kw: ([], []))
        result = PipelineOrchestrator(config).run("Do work.")
        assert result.completeness == "complete"
        assert result.assumptions == []
        assert result.readable_report == ""

    def test_structural_spans_produce_section_in_traces(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from nl2spl.config import LLMConfig, PipelineConfig

        config = PipelineConfig(llm=LLMConfig(api_key="sk-fake"), output_dir=Path("output"), run_name="test_section_prov")
        span = SpanIR("s1", "Do work.", source_section_id="sec_reusable_process", source_packet_id="p_process_1")
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage1", lambda s, *a, **kw: [span])
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage2", lambda s, *a, **kw: (FieldRouteIR(behavior=["s1"]), []))
        monkeypatch.setattr(PipelineOrchestrator, "_run_stage3", lambda s, *a, **kw: ([span], FieldRouteIR(behavior=["s1"])))
        self._patch_worker_aware_stages(monkeypatch, [span])
        monkeypatch.setattr(ExecutableElementGate, "apply", lambda g, w, wp=None: (w, [], []))
        captured_kwargs: dict = {}
        _orig_aggregate = ProvenanceAggregator.aggregate

        def _spy_aggregate(self, **kw):
            captured_kwargs.update(kw)
            return _orig_aggregate(self, **kw)

        monkeypatch.setattr(ProvenanceAggregator, "aggregate", _spy_aggregate)
        result = PipelineOrchestrator(config).run("Do work.")
        assert any(
            trace.source_section_id == "sec_reusable_process"
            for trace in result.traces
        )
        assert any(
            trace.source_packet_id == "p_process_1"
            for trace in result.traces
        )
        assert result.completeness == "complete"
        assert "variable_facts" in captured_kwargs
        assert captured_kwargs["variable_facts"] == []
# ---------------------------------------------------------------------------

class TestCliReportFile:
    """Verify main.py writes only the MVP user-facing report artifact."""

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
        assert not report_path.exists()

        feedback_path = tmp_path / "feedback_report.md"
        assert feedback_path.exists(), f"feedback_report.md missing in {tmp_path}"
        feedback = feedback_path.read_text(encoding="utf-8")
        assert "NL2SPL Feedback Report" in feedback
        assert "Completeness: `partial`" in feedback
        assert "missing_handler" in feedback
        assert "section=`sec_failure_handling`" in feedback

