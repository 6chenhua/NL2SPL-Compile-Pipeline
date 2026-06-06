"""R7.1 Authority Baseline Audit 鈥?lock diagnostic authority boundaries.

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
        """Exception flow exists but no step references it 鈫?Gate skips it.

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
                # No step with flow_ref="exc_1" 鈫?handler never existed
            ],
        )
        _, _, diags = gate.apply(worker)

        # Gate must NOT emit missing_handler for a flow that never had a handler
        gate_mh = [d for d in diags if d.kind == "missing_handler"]
        assert len(gate_mh) == 0

    def test_gate_emits_missing_handler_when_handler_filtered(self) -> None:
        """Handler step existed but was filtered 鈫?Gate emits missing_handler."""
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
                    [],  # empty source spans 鈫?assumed 鈫?filtered
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

