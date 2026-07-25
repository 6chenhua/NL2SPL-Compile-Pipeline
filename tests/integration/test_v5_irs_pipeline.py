"""Integration tests for v5 IRS pipeline -- scenarios with IRS flags enabled.

Tests mock LLM stages but exercise the full orchestrator path with
Stage 4/7 IRS checks, consolidation, and resource hardening enabled.
"""

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import (
    ResourceRegistryIR,
    WorkerScopedResourceIR,
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.orchestrator import PipelineOrchestrator, PipelineResult


def _orch(tmp_path: Path) -> PipelineOrchestrator:
    return PipelineOrchestrator(
        PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
        )
    )


def _run_orch(
    orch: PipelineOrchestrator,
    *,
    flow_plan: WorkerFlowPlanIR | None = None,
    extra_patches: list | None = None,
) -> PipelineResult:
    from nl2spl.ir.worker_ir import FlowRef, WorkerIR

    spans = [SpanIR("s1", "Process.")]
    routes = FieldRouteIR(behavior=["s1"])
    symbols = SymbolTable()
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main", "Main", "main", "Main worker",
                ["s1"], [], [], [], [], "main_worker", [], "",
            )
        ],
        candidates=[],
        decisions=[],
        handoffs=[],
    )
    fp = flow_plan or WorkerFlowPlanIR(
        worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])}
    )
    bp = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", spans=["s1"])]
            )
        }
    )
    step_plan = WorkerStepPlanIR(main_worker_id="worker_main", worker_steps={"worker_main": []})
    ws_resources = WorkerScopedResourceIR(global_resources=ResourceRegistryIR())
    worker = WorkerIR(worker_name="MainWorker", description="Main", main_flow=FlowRef(), steps=[])

    patches = [
        patch.object(orch, "_run_stage1", return_value=spans),
        patch.object(orch, "_run_stage2", return_value=(routes, [])),
        patch.object(orch, "_run_stage3", return_value=(spans, routes)),
        patch.object(orch, "_run_stage3_5", return_value=worker_plan),
        patch.object(orch, "_run_stage4", return_value=fp),
        patch.object(orch, "_run_stage5", return_value=bp),
        patch.object(orch, "_run_stage6_worker_scoped", return_value=(ws_resources, symbols, [])),
        patch.object(orch, "_run_stage7_worker_scoped", return_value=(step_plan, symbols, [])),
        patch.object(orch, "_run_stage8", return_value=MagicMock()),
        patch.object(orch, "_run_stage9", return_value=[]),
        patch.object(
            orch,
            "_run_normalization_worker_scoped",
            return_value=(fp, bp, step_plan, symbols, [], []),
        ),
        patch.object(orch, "_run_stage10_worker_scoped", return_value=worker),
        patch.object(orch, "_run_stage11", return_value=("SPL", [], [])),
    ]
    patches.extend(extra_patches or [])
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        return orch.run("test")


class TestConflictAnalyzerDisabled:
    def test_disabled_analyzer_no_semantic_conflict(self, tmp_path: Path):
        orch = _orch(tmp_path)
        result = _run_orch(orch)
        kinds = {d.kind for d in result.compile_diagnostics}
        assert "semantic_conflict" not in kinds


# ---------------------------------------------------------------------------
# Scenario 10: Resource hardening
class TestPostGateMissingHandler:
    def test_handler_removed_by_gate_emits_missing_handler(self, tmp_path: Path):
        """Gate post-gate check: handler removed → missing_handler from Gate."""
        from nl2spl.ir.worker_ir import (
            ExceptionFlowRef,
            FlowRef,
            WorkerIR,
        )

        orch = _orch(tmp_path)
        exc_flow = ExceptionFlow("exc_1", "Missing timeframe.", ["s1"])
        flow_plan = WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR(
                main_flow_spans=["s1"],
                exception_flows=[exc_flow],
            )},
        )
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Main",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    blocks=[],
                ),
            ],
            steps=[
                StepIR(
                    step_id="st_h", text="Handle missing timeframe.",
                    source_span_ids=[],  # no source → Gate filters
                    command_type="GENERAL_COMMAND",
                    flow_ref="exc_1",
                ),
            ],
            child_workers=[],
        )
        result = _run_orch(
            orch, flow_plan=flow_plan,
            extra_patches=[
                patch.object(orch, "_run_stage10_worker_scoped",
                            return_value=worker),
            ],
        )
        mh = [d for d in result.compile_diagnostics
              if d.kind == "missing_handler"]
        # Gate's _post_gate_missing_handler emits a single diagnostic
        # with worker-scoped target_ref.
        assert len(mh) == 1
        assert "exc_1" in mh[0].target_ref
        assert mh[0].blocks_completion is True
        assert mh[0].blocks_rendering is False

    def test_handler_with_source_survives_gate_no_duplicate_mh(self, tmp_path: Path):
        """Handler step with source_span_ids survives Gate → no missing_handler."""
        from nl2spl.ir.worker_ir import (
            ExceptionFlowRef,
            FlowRef,
            WorkerIR,
        )

        orch = _orch(tmp_path)
        exc_flow = ExceptionFlow("exc_1", "Missing timeframe.", ["s1"])
        flow_plan = WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR(
                main_flow_spans=["s1"],
                exception_flows=[exc_flow],
            )},
        )
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Main",
            main_flow=FlowRef(),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    blocks=[],
                ),
            ],
            steps=[
                StepIR(
                    step_id="st_h", text="Handle missing timeframe.",
                    source_span_ids=["s1"],
                    command_type="GENERAL_COMMAND",
                    flow_ref="exc_1",
                ),
            ],
            child_workers=[],
        )
        result = _run_orch(
            orch, flow_plan=flow_plan,
            extra_patches=[
                patch.object(orch, "_run_stage10_worker_scoped",
                            return_value=worker),
            ],
        )
        mh = [d for d in result.compile_diagnostics
              if d.kind == "missing_handler"]
        assert len(mh) == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_slot(report, slot_name: str):
    for s in report.slots:
        if s.slot_name == slot_name:
            return s
    raise KeyError(slot_name)



