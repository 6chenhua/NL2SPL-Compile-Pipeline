"""R7.1 Authority Baseline Audit — lock diagnostic authority boundaries.

Tests that verify:
- Gate does NOT emit missing_handler for exception flows that never had a handler
- DiagnosticAnalyzer is NOT called by the production orchestrator path
- PostNormalizeIRSChecker diagnostics flow into compile_diagnostics
- Exactly-once dedup for each of the 4 diagnostic kinds
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import (
    ExceptionFlowRef,
    FlowRef,
    StepIR,
    WorkerIR,
)
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerBlockPlanIR
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.pipeline.orchestrator import PipelineOrchestrator
from nl2spl.pipeline.stages.stage9_5_normalizer.final_irs_checker import (
    PostNormalizeIRSChecker,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _diag(
    diagnostic_id: str = "d1",
    kind: str = "missing_handler",
    target_ref: str = "exception_flow:exc_1",
    source_span_ids: list[str] | None = None,
    message: str = "Test diagnostic",
    blocks_completion: bool = True,
    blocks_rendering: bool = False,
    missing_slot: object | None = None,
) -> CompileDiagnostic:
    """Factory for CompileDiagnostic."""
    return CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind=kind,
        severity="warning",
        message=message,
        target_ref=target_ref,
        source_span_ids=source_span_ids or [],
        blocks_completion=blocks_completion,
        blocks_rendering=blocks_rendering,
        missing_slot=missing_slot,
    )


def _make_worker(**kwargs: object) -> WorkerIR:
    """Factory for WorkerIR with sensible defaults."""
    defaults: dict[str, object] = dict(
        worker_name="main",
        description="Main worker",
        main_flow=FlowRef(),
        steps=[],
    )
    defaults.update(kwargs)
    return WorkerIR(**defaults)  # type: ignore[arg-type]


# ------------------------------------------------------------------
# Gate: "never had handler" boundary
# ------------------------------------------------------------------


class TestGateNeverHadHandler:
    """Gate must NOT emit missing_handler for flows that never had a handler."""

    def test_gate_does_not_emit_missing_handler_for_never_had_handler(
        self,
    ) -> None:
        """Exception flow exists but no step references it → Gate skips it.

        The Gate only emits missing_handler when a handler step existed
        BEFORE filtering but was removed.  If no handler ever existed,
        PostNormalizeIRSChecker (not Gate) is responsible.
        """
        gate = ExecutableElementGate()
        worker = _make_worker(
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    blocks=[],
                ),
            ],
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                # No step with flow_ref="exc_1" → handler never existed
            ],
        )
        _, _, diags = gate.apply(worker)

        # Gate must NOT emit missing_handler for a flow that never had a handler
        gate_mh = [d for d in diags if d.kind == "missing_handler"]
        assert len(gate_mh) == 0

    def test_gate_emits_missing_handler_when_handler_filtered(self) -> None:
        """Handler step existed but was filtered → Gate emits missing_handler."""
        gate = ExecutableElementGate()
        worker = _make_worker(
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Handle failures.",
                    blocks=[],
                ),
            ],
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
                StepIR(
                    "st_handler",
                    "Handle failures",
                    [],  # empty source spans → assumed → filtered
                    "GENERAL_COMMAND",
                    flow_ref="exc_1",
                ),
            ],
        )
        filtered, _, diags = gate.apply(worker)

        # Handler was filtered out
        assert not any(s.step_id == "st_handler" for s in filtered.steps)

        # Gate SHOULD emit missing_handler (handler existed before gate)
        gate_mh = [d for d in diags if d.kind == "missing_handler"]
        assert len(gate_mh) == 1


# ------------------------------------------------------------------
# DiagnosticAnalyzer: not in production path
# ------------------------------------------------------------------


class TestDiagnosticAnalyzerBoundary:
    """DiagnosticAnalyzer is NOT called by the production orchestrator."""

    def test_diagnostic_analyzer_not_imported_by_orchestrator(self) -> None:
        """Orchestrator source does not import DiagnosticAnalyzer."""
        import inspect

        source = inspect.getsource(PipelineOrchestrator)
        assert "DiagnosticAnalyzer" not in source

    def test_post_normalize_checker_is_final_authority(self) -> None:
        """PostNormalizeIRSChecker produces construct-level diagnostic kinds."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    blocks=[],
                ),
            ],
            steps=[
                StepIR("st1", "Do work", [], "GENERAL_COMMAND"),
            ],
        )
        diags = checker.check(worker)
        kinds = {d.kind for d in diags}

        # PostNormalizeIRSChecker should produce missing_handler and
        # assumed_command_not_renderable for this input
        assert "missing_handler" in kinds
        assert "assumed_command_not_renderable" in kinds


# ------------------------------------------------------------------
# Exactly-once dedup per diagnostic kind
# ------------------------------------------------------------------


class TestExactlyOncePerKind:
    """Each diagnostic kind should dedup to exactly one when duplicates exist."""

    def _make_orchestrator(self, tmp_path: Path) -> PipelineOrchestrator:
        return PipelineOrchestrator(
            PipelineConfig(
                llm=LLMConfig(api_key="test-key"),
                output_dir=tmp_path / "output",
                save_intermediate=False,
            )
        )

    def test_missing_handler_exactly_once(self, tmp_path: Path) -> None:
        """Two missing_handler with same target/spans → deduped to one."""
        orch = self._make_orchestrator(tmp_path)
        existing = [
            _diag("d1", "missing_handler",
                  target_ref="exception_flow:exc_1",
                  source_span_ids=["s1"]),
        ]
        intermediate = {
            "stage_local_diagnostics": {
                "final_check": [
                    _diag("d2", "missing_handler",
                          target_ref="exception_flow:exc_1",
                          source_span_ids=["s1"]),
                ],
            },
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        mh = [d for d in result if d.kind == "missing_handler"]
        assert len(mh) == 1

    def test_type_or_contract_ambiguity_exactly_once(self, tmp_path: Path) -> None:
        """Two type_or_contract_ambiguity with same target/spans → deduped."""
        orch = self._make_orchestrator(tmp_path)
        existing = [
            _diag("d1", "type_or_contract_ambiguity",
                  target_ref="step:st_1",
                  source_span_ids=["s1"]),
        ]
        intermediate = {
            "stage_local_diagnostics": {
                "stage7": [
                    _diag("d2", "type_or_contract_ambiguity",
                          target_ref="step:st_1",
                          source_span_ids=["s1"]),
                ],
            },
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        tca = [d for d in result if d.kind == "type_or_contract_ambiguity"]
        assert len(tca) == 1

    def test_assumed_command_exactly_once(self, tmp_path: Path) -> None:
        """Two assumed_command_not_renderable with same target/spans → deduped."""
        orch = self._make_orchestrator(tmp_path)
        existing = [
            _diag("d1", "assumed_command_not_renderable",
                  target_ref="step:st_1",
                  source_span_ids=[]),
        ]
        intermediate = {
            "stage_local_diagnostics": {
                "stage7": [
                    _diag("d2", "assumed_command_not_renderable",
                          target_ref="step:st_1",
                          source_span_ids=[]),
                ],
            },
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        acr = [d for d in result if d.kind == "assumed_command_not_renderable"]
        assert len(acr) == 1

    def test_missing_output_producer_exactly_once(self, tmp_path: Path) -> None:
        """Two missing_output_producer with same target/spans → deduped."""
        orch = self._make_orchestrator(tmp_path)
        existing = [
            _diag("d1", "missing_output_producer",
                  target_ref="variable:draft",
                  source_span_ids=["s1"]),
        ]
        intermediate = {
            "stage_local_diagnostics": {
                "final_check": [
                    _diag("d2", "missing_output_producer",
                          target_ref="variable:draft",
                          source_span_ids=["s1"]),
                ],
            },
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        mop = [d for d in result if d.kind == "missing_output_producer"]
        assert len(mop) == 1

    def test_different_target_not_deduped(self, tmp_path: Path) -> None:
        """Same kind but different target → both kept."""
        orch = self._make_orchestrator(tmp_path)
        existing = [
            _diag("d1", "missing_handler",
                  target_ref="exception_flow:exc_1",
                  source_span_ids=["s1"]),
        ]
        intermediate = {
            "stage_local_diagnostics": {
                "final_check": [
                    _diag("d2", "missing_handler",
                          target_ref="exception_flow:exc_2",
                          source_span_ids=["s1"]),
                ],
            },
        }
        result = orch._consolidate_compile_diagnostics(existing, intermediate)
        mh = [d for d in result if d.kind == "missing_handler"]
        assert len(mh) == 2
