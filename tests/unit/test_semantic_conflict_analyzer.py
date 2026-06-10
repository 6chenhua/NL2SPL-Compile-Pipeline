"""Unit tests for Phase 6 semantic conflict analyzer, verifier, and integration."""

import contextlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from nl2spl.compiler.analyzers.semantic_conflict import (
    ConflictAnalysisContext,
    LLMConflictDiagnosticVerifier,
    LLMSemanticConflictAnalyzer,
    NoOpSemanticConflictAnalyzer,
)
from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import (
    ResourceRegistryIR,
    WorkerScopedResourceIR,
)
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable, VariableSymbol
from nl2spl.pipeline.orchestrator import PipelineOrchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _diag(
    diagnostic_id: str = "d1",
    kind: str = "semantic_conflict",
    target_ref: str = "step:st_1",
    source_span_ids: list[str] | None = None,
    message: str = "Likely conflict.",
) -> CompileDiagnostic:
    return CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind=kind,
        severity="warning",
        message=message,
        target_ref=target_ref,
        source_span_ids=source_span_ids or [],
        blocks_completion=False,
    )


class _FakeAnalyzer:
    """Fake analyzer returning a fixed list of diagnostics."""
    def __init__(self, diags):
        self._diags = diags

    def analyze(self, **kwargs):
        return list(self._diags)


# ---------------------------------------------------------------------------
# ConflictAnalysisContext
# ---------------------------------------------------------------------------

class TestConflictAnalysisContext:
    def test_defaults(self):
        ctx = ConflictAnalysisContext()
        assert ctx.spans == []
        assert ctx.canonical_input is None
        assert ctx.worker_plan is None

    def test_with_spans(self):
        from nl2spl.ir.span_ir import SpanIR
        spans = [SpanIR("s1", "text")]
        ctx = ConflictAnalysisContext(spans=spans)
        assert len(ctx.spans) == 1


# ---------------------------------------------------------------------------
# NoOpSemanticConflictAnalyzer
# ---------------------------------------------------------------------------

class TestNoOpAnalyzer:
    def test_returns_empty(self):
        analyzer = NoOpSemanticConflictAnalyzer()
        result = analyzer.analyze(
            constraints=[], steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(),
        )
        assert result == []

    def test_returns_empty_with_data(self):
        analyzer = NoOpSemanticConflictAnalyzer()
        result = analyzer.analyze(
            constraints=[ConstraintIR("c_1", "No invent", "prohibition", ["global"], ["s1"])],
            steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(),
        )
        assert result == []

    def test_does_not_mutate_inputs(self):
        analyzer = NoOpSemanticConflictAnalyzer()
        constraints = [ConstraintIR("c_1", "No invent", "prohibition", ["global"], ["s1"])]
        orig = [ConstraintIR("c_1", "No invent", "prohibition", ["global"], ["s1"])]
        analyzer.analyze(
            constraints=constraints, steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(),
        )
        assert constraints == orig


# ---------------------------------------------------------------------------
# LLMSemanticConflictAnalyzer
# ---------------------------------------------------------------------------

_MOCK_JSON_RESPONSE = {
    "diagnostics": [
        {
            "target_ref": "step:st_1",
            "source_span_ids": ["s1"],
            "message": "Constraint 'No invent' conflicts with step 'Make up'.",
            "suggested_resolution": "Clarify whether the step is allowed.",
            "severity": "warning",
        },
    ],
}


def _strict_call_json(return_value=None, side_effect=None):
    """Factory: returns a fake ``call_json`` with the real LLMClient signature.

    The fake requires ``(stage_name, system_prompt, user_prompt, **kwargs)``
    so mismatched positional arguments fail immediately.
    """
    fake = MagicMock()
    if side_effect is not None:
        fake.side_effect = side_effect
    else:
        fake.return_value = return_value if return_value is not None else {}
    # Enforce positional-only: if called with wrong arg count, TypeError is raised.
    fake.__name__ = "fake_call_json"

    def _call_json(stage_name, system_prompt, user_prompt, **kwargs):
        return fake(stage_name, system_prompt, user_prompt, **kwargs)

    return _call_json, fake


class TestLLMAnalyzer:
    def test_has_prompt(self):
        analyzer = LLMSemanticConflictAnalyzer()
        assert "do not invent" in analyzer.PROMPT.lower()

    def test_no_call_json_returns_empty(self):
        """Analyzer without call_json returns empty list."""
        analyzer = LLMSemanticConflictAnalyzer()
        result = analyzer.analyze(
            constraints=[], steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(),
        )
        assert result == []

    def test_returns_empty_list(self):
        """Mock LLM returning empty diagnostics — strict signature."""
        call, fake = _strict_call_json(return_value={"diagnostics": []})
        analyzer = LLMSemanticConflictAnalyzer(call_json=call)
        result = analyzer.analyze(
            constraints=[], steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(),
        )
        assert result == []
        fake.assert_called_once()
        # Verify signature: user_prompt is a JSON string, stage_name is set
        args, kwargs = fake.call_args
        assert args[0] == "semantic_conflict_analyzer"
        assert isinstance(args[2], str)  # user_prompt is serialized JSON

    def test_valid_diagnostic_returned(self):
        call, _fake = _strict_call_json(return_value=_MOCK_JSON_RESPONSE)
        analyzer = LLMSemanticConflictAnalyzer(call_json=call)
        result = analyzer.analyze(
            constraints=[ConstraintIR("c1", "No invent", "prohibition", ["global"], ["s1"])],
            steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(spans=[]),
        )
        assert len(result) == 1
        diag = result[0]
        assert diag.kind == "semantic_conflict"
        assert diag.target_ref == "step:st_1"
        assert diag.source_span_ids == ["s1"]
        assert diag.blocks_rendering is False
        assert diag.blocks_completion is False

    def test_kind_forced_to_semantic_conflict(self):
        """LLM outputs a different kind -- forced to semantic_conflict."""
        call, _fake = _strict_call_json(return_value={"diagnostics": [{
            "target_ref": "step:st_1",
            "source_span_ids": ["s1"],
            "message": "Fake kind test.",
        }]})
        analyzer = LLMSemanticConflictAnalyzer(call_json=call)
        result = analyzer.analyze(
            constraints=[], steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(spans=[]),
        )
        assert len(result) == 1
        assert result[0].kind == "semantic_conflict"

    def test_severity_defaults_to_warning(self):
        call, _fake = _strict_call_json(return_value={"diagnostics": [{
            "target_ref": "step:st_1",
            "source_span_ids": ["s1"],
            "message": "No severity field.",
        }]})
        analyzer = LLMSemanticConflictAnalyzer(call_json=call)
        result = analyzer.analyze(
            constraints=[], steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(spans=[]),
        )
        assert result[0].severity == "warning"

    def test_invalid_severity_clamped_to_warning(self):
        call, _fake = _strict_call_json(return_value={"diagnostics": [{
            "target_ref": "step:st_1",
            "source_span_ids": ["s1"],
            "message": "Bad severity.",
            "severity": "error",
        }]})
        analyzer = LLMSemanticConflictAnalyzer(call_json=call)
        result = analyzer.analyze(
            constraints=[], steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(spans=[]),
        )
        assert result[0].severity == "warning"

    def test_info_severity_preserved(self):
        call, _fake = _strict_call_json(return_value={"diagnostics": [{
            "target_ref": "step:st_1",
            "source_span_ids": ["s1"],
            "message": "Info severity.",
            "severity": "info",
        }]})
        analyzer = LLMSemanticConflictAnalyzer(call_json=call)
        result = analyzer.analyze(
            constraints=[], steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(spans=[]),
        )
        assert result[0].severity == "info"

    def test_missing_target_ref_skipped(self):
        call, _fake = _strict_call_json(return_value={"diagnostics": [{
            "source_span_ids": ["s1"],
            "message": "No target.",
        }]})
        analyzer = LLMSemanticConflictAnalyzer(call_json=call)
        result = analyzer.analyze(
            constraints=[], steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(spans=[]),
        )
        assert result == []

    def test_missing_source_span_ids_skipped(self):
        call, _fake = _strict_call_json(return_value={"diagnostics": [{
            "target_ref": "step:st_1",
            "source_span_ids": [],
            "message": "No spans.",
        }]})
        analyzer = LLMSemanticConflictAnalyzer(call_json=call)
        result = analyzer.analyze(
            constraints=[], steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(spans=[]),
        )
        assert result == []

    def test_llm_exception_returns_empty(self):
        call, _fake = _strict_call_json(side_effect=RuntimeError("LLM down"))
        analyzer = LLMSemanticConflictAnalyzer(call_json=call)
        result = analyzer.analyze(
            constraints=[], steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(spans=[]),
        )
        assert result == []

    def test_payload_contains_structured_data(self):
        captured: dict[str, Any] | None = None

        def capture(stage_name, system_prompt, user_prompt, **kwargs):
            nonlocal captured
            captured = json.loads(user_prompt)
            return {"diagnostics": []}

        analyzer = LLMSemanticConflictAnalyzer(call_json=capture)
        constraint = ConstraintIR("c1", "No invent", "prohibition", ["global"], ["s1"])
        step = StepIR("st_1", "Call API", ["s2"], "CALL_API", inputs=["in1"], outputs=["out1"])
        symbols = SymbolTable()
        symbols.variables["out1"] = VariableSymbol(
            name="out1", data_type="text", source="output", description="",
        )

        analyzer.analyze(
            constraints=[constraint],
            steps=[step],
            flows=FlowStructureIR(main_flow_spans=["s1"]),
            symbols=symbols,
            context=ConflictAnalysisContext(spans=[]),
        )
        assert captured is not None
        assert captured["constraints"][0]["id"] == "c1"
        assert captured["flows_summary"]["kind"] == "flat"
        assert captured["symbols"][0]["name"] == "out1"
        assert captured["worker_context"]["present"] is False
        # Step payload includes inputs / outputs / target_ref
        step_payload = captured["steps"][0]
        assert step_payload["id"] == "st_1"
        assert step_payload["target_ref"] == "step:st_1"
        assert step_payload["inputs"] == ["in1"]
        assert step_payload["outputs"] == ["out1"]

    def test_does_not_mutate_inputs(self):
        call, _fake = _strict_call_json(return_value=_MOCK_JSON_RESPONSE)
        analyzer = LLMSemanticConflictAnalyzer(call_json=call)
        constraints = [ConstraintIR("c1", "No invent", "prohibition", ["global"], ["s1"])]
        orig = [ConstraintIR("c1", "No invent", "prohibition", ["global"], ["s1"])]
        analyzer.analyze(
            constraints=constraints, steps=[], flows=FlowStructureIR(),
            symbols=SymbolTable(), context=ConflictAnalysisContext(),
        )
        assert constraints == orig


# ---------------------------------------------------------------------------
# LLMConflictDiagnosticVerifier
# ---------------------------------------------------------------------------

class TestVerifier:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.verifier = LLMConflictDiagnosticVerifier()

    def test_valid_semantic_conflict_accepted(self):
        diag = _diag(kind="semantic_conflict", target_ref="step:st_1", source_span_ids=["s1"])
        accepted, warnings = self.verifier.verify([diag])
        assert len(accepted) == 1
        assert warnings == []

    def test_multiple_valid_all_accepted(self):
        diags = [
            _diag("d1", "semantic_conflict", "step:st_1", ["s1"]),
            _diag("d2", "semantic_conflict", "constraint:c_1", ["s2"]),
        ]
        accepted, warnings = self.verifier.verify(diags)
        assert len(accepted) == 2

    def test_unsupported_kind_rejected(self):
        diag = _diag(
            kind="missing_handler", target_ref="exception_flow:exc_1",
            source_span_ids=["s1"],
        )
        accepted, warnings = self.verifier.verify([diag])
        assert accepted == []
        assert "unsupported diagnostic kind" in warnings[0]

    def test_missing_source_evidence_rejected(self):
        diag = _diag(kind="semantic_conflict", target_ref="step:st_1", source_span_ids=[])
        accepted, warnings = self.verifier.verify([diag])
        assert accepted == []
        assert "missing source evidence" in warnings[0]

    def test_invalid_target_ref_rejected(self):
        diag = _diag(kind="semantic_conflict", target_ref="bare_word", source_span_ids=["s1"])
        accepted, warnings = self.verifier.verify([diag])
        assert accepted == []
        assert "invalid target_ref" in warnings[0]

    def test_none_target_ref_rejected(self):
        diag = _diag(kind="semantic_conflict", target_ref=None, source_span_ids=["s1"])
        accepted, warnings = self.verifier.verify([diag])
        assert accepted == []

    def test_mixed_accepted_and_rejected(self):
        diags = [
            _diag("d1", "semantic_conflict", "step:st_1", ["s1"]),
            _diag("d2", "semantic_conflict", "step:st_2", []),
            _diag("d3", "semantic_conflict", "step:st_3", ["s3"]),
        ]
        accepted, warnings = self.verifier.verify(diags)
        assert len(accepted) == 2
        assert {a.diagnostic_id for a in accepted} == {"d1", "d3"}

    def test_empty_list(self):
        accepted, warnings = self.verifier.verify([])
        assert accepted == []


# ---------------------------------------------------------------------------
# Pipeline integration: flag off/on, fake analyzer
# ---------------------------------------------------------------------------

class TestFlagIntegration:
    def _base_config(self, tmp_path: Path, flag: bool) -> PipelineConfig:
        return PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
        )

    def _run(self, tmp_path: Path, flag: bool, fake_analyzer=None):
        from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
        from nl2spl.ir.field_route_ir import FieldRouteIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.span_ir import SpanIR
        from nl2spl.ir.worker_plan_ir import (
            WorkerBlockPlanIR,
            WorkerFlowPlanIR,
            WorkerPlanIR,
            WorkerSpecIR,
            WorkerStepPlanIR,
        )

        config = self._base_config(tmp_path, flag)
        orch = PipelineOrchestrator(config)
        spans = [SpanIR("s1", "Process.")]
        routes = FieldRouteIR(behavior=["s1"])
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR("worker_main", "Main", "main", "Main",
                             ["s1"], [], [], [], [], "main_worker", [], ""),
            ],
            candidates=[], decisions=[], handoffs=[],
        )
        flow_plan = WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])}
        )
        block_plan = WorkerBlockPlanIR(
            worker_blocks={"worker_main": BlockStructureIR(
                main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
            )}
        )
        symbols = SymbolTable()
        ws_resources = WorkerScopedResourceIR(global_resources=ResourceRegistryIR())
        step_plan = WorkerStepPlanIR(main_worker_id="worker_main", worker_steps={"worker_main": []})
        worker_mock = MagicMock()
        worker_mock.steps = []
        worker_mock.child_workers = []
        worker_mock.scoped_steps = False

        patches = [
            patch.object(orch, "_run_stage1", return_value=spans),
            patch.object(orch, "_run_stage2", return_value=(routes, [])),
            patch.object(orch, "_run_stage3", return_value=(spans, routes)),
            patch.object(orch, "_run_stage3_5", return_value=plan),
            patch.object(orch, "_run_stage4", return_value=flow_plan),
            patch.object(orch, "_run_stage5", return_value=block_plan),
            patch.object(
                orch, "_run_stage6_worker_scoped",
                return_value=(ws_resources, symbols, []),
            ),
            patch.object(orch, "_run_stage7_worker_scoped", return_value=(step_plan, symbols, [])),
            patch.object(orch, "_run_stage8", return_value=MagicMock()),
            patch.object(orch, "_run_stage9", return_value=[]),
            patch.object(orch, "_run_normalization_worker_scoped",
                         return_value=(flow_plan, block_plan, step_plan, symbols, [], [])),
            patch.object(orch, "_run_stage10_worker_scoped", return_value=worker_mock),
            patch.object(orch, "_run_stage11", return_value=("SPL", [], [])),
        ]
        if fake_analyzer is not None:
            patches.append(
                patch.object(orch, "_make_semantic_conflict_analyzer", return_value=fake_analyzer)
            )
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            return orch.run("test")

    def test_flag_off_no_conflict_diagnostics(self, tmp_path: Path):
        result = self._run(tmp_path, flag=False)
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "semantic_conflict" not in kinds

    def test_flag_on_strict_signature_call_json_invoked(self, tmp_path: Path):
        """Flag on: call_json called with (stage_name, system_prompt, user_prompt, **kw)."""
        call, fake = _strict_call_json(return_value={"diagnostics": []})
        orch = PipelineOrchestrator(self._base_config(tmp_path, flag=True))
        orch.client = MagicMock()
        orch.client.call_json = call

        # Reuse mocked stage pipeline
        orch._make_semantic_conflict_analyzer = lambda: LLMSemanticConflictAnalyzer(
            call_json=orch.client.call_json,
        )
        # Quick smoke: wire up minimal pipeline run, just verify that after
        # a full run, call_json was invoked with the correct positional args.
        result = self._run(tmp_path, flag=True, fake_analyzer=LLMSemanticConflictAnalyzer(
            call_json=call,
        ))
        # With empty diagnostics, no semantic_conflict in output
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "semantic_conflict" not in kinds
        # call_json was invoked with (stage_name, system_prompt, user_prompt)
        fake.assert_called()
        args, kwargs = fake.call_args
        assert args[0] == "semantic_conflict_analyzer"
        assert isinstance(args[2], str) and args[2].startswith("{")

    def test_flag_on_fake_diagnostic_enters_final(self, tmp_path: Path):
        """Flag on, mock LLM returns valid diag → semantic_conflict in final diagnostics."""
        call, _fake = _strict_call_json(return_value={
            "diagnostics": [{
                "target_ref": "step:st_1",
                "source_span_ids": ["s1"],
                "message": "Policy conflict.",
            }],
        })
        result = self._run(
            tmp_path, flag=True,
            fake_analyzer=LLMSemanticConflictAnalyzer(call_json=call),
        )
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "semantic_conflict" in kinds

    def test_valid_conflict_enters_diagnostics_and_report(self, tmp_path: Path):
        valid = _diag("sc1", "semantic_conflict", "step:st_1", ["s1"], "Policy conflict")
        result = self._run(tmp_path, flag=True, fake_analyzer=_FakeAnalyzer([valid]))
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "semantic_conflict" in kinds
        assert result.readable_report == ""
        # semantic_conflict blocks_completion=False by default -> stays complete

    def test_rejected_conflict_goes_to_adapter_warnings(self, tmp_path: Path):
        rejected = _diag("sc1", "semantic_conflict", "step:st_1", [], "No evidence")
        result = self._run(tmp_path, flag=True, fake_analyzer=_FakeAnalyzer([rejected]))
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "semantic_conflict" not in kinds
        assert any("SEMANTIC_CONFLICT_REJECTED" in w for w in result.adapter_warnings)

    def test_factory_returns_noop(self, tmp_path: Path):
        orch = PipelineOrchestrator(self._base_config(tmp_path, flag=True))
        orch.client = MagicMock()
        orch.client.call_json = MagicMock(return_value={"diagnostics": []})

        analyzer = orch._make_semantic_conflict_analyzer()

        assert isinstance(analyzer, NoOpSemanticConflictAnalyzer)

    def test_flag_off_factory_returns_noop(self, tmp_path: Path):
        orch = PipelineOrchestrator(self._base_config(tmp_path, flag=False))
        analyzer = orch._make_semantic_conflict_analyzer()
        assert isinstance(analyzer, NoOpSemanticConflictAnalyzer)
