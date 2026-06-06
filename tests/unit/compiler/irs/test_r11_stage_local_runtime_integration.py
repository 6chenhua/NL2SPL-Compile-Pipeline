"""R11: Stage-local IRS Runtime Integration tests.

Covers the 10 required test cases from the R11 implementation plan:
1. config.irs.enabled=False → no construct_satisfaction
2. stage_local_enabled=True → stage3_5 reports
3. stage4 reports
4. stage7 reports
5. Stage-local IRS does not modify WorkerPlanIR
6. Stage-local IRS does not modify WorkerFlowPlanIR
7. Stage-local IRS does not modify WorkerStepPlanIR
8. Stage-local diagnostics default not in compile_diagnostics
9. Existing SPL output unchanged by stage-local IRS
10. WorkerPlanValidator failure → no IRS
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nl2spl.compiler.irs.policy import IRSRuntimeConfig
from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import (
    ResourceRegistryIR,
    VariableSpec,
    WorkerScopedResourceIR,
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    ControlComplexityRegionIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerBlockPlanIR,
    WorkerBoundaryDecisionIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.orchestrator import PipelineOrchestrator


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _spans() -> list[SpanIR]:
    return [
        SpanIR("s1", "Prepare the request context."),
        SpanIR("s2", "Gather approved sources."),
        SpanIR("s3", "Produce the final answer."),
    ]


def _routes() -> FieldRouteIR:
    return FieldRouteIR(behavior=["s1", "s2", "s3"])


def _field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(
        name=name,
        data_type="text",
        required=True,
        description=f"{name} field",
        source=source,  # type: ignore[arg-type]
    )


def _worker_plan() -> WorkerPlanIR:
    main_worker = WorkerSpecIR(
        worker_id="worker_main",
        worker_name="MainWorker",
        kind="main",
        purpose="Coordinate the request.",
        owned_span_ids=["s1", "s3"],
        input_contract=[_field("request")],
        output_contract=[_field("draft", "output")],
        boundary_kind="main_worker",
    )
    child_worker = WorkerSpecIR(
        worker_id="worker_source",
        worker_name="SourceWorker",
        kind="child",
        purpose="Gather source evidence.",
        owned_span_ids=["s2"],
        input_contract=[_field("request")],
        output_contract=[_field("evidence", "output")],
        boundary_kind="bounded_subtask",
    )
    handoff = WorkerHandoffIR(
        handoff_id="handoff_source",
        from_worker="worker_main",
        to_worker="worker_source",
        api_ref=None,
        mode="invoke",
        condition_text="when source evidence is needed",
        ordering="conditional",
        input_bindings=[InputBindingIR("request", "request", True)],
        output_bindings=[OutputBindingIR("evidence", "evidence", True, "set")],
        invoke_location_hint=InvokeLocationHintIR(
            flow_kind="main",
            flow_id=None,
            after_span_id="s1",
            before_span_id="s3",
            block_hint="sequential",
        ),
    )
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker, child_worker],
        candidates=[],
        decisions=[],
        handoffs=[handoff],
    )


def _worker_flow_plan() -> WorkerFlowPlanIR:
    return WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(main_flow_spans=["s1", "s3"]),
            "worker_source": FlowStructureIR(main_flow_spans=["s2"]),
        }
    )


def _worker_block_plan() -> WorkerBlockPlanIR:
    return WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR("b1", "SEQUENTIAL", None, ["s1", "s3"]),
                ]
            ),
            "worker_source": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR("b_child", "SEQUENTIAL", None, ["s2"]),
                ]
            ),
        },
        control_complexity_regions=[],
    )


def _make_config(
    tmp_path: Path,
    irs_config: IRSRuntimeConfig | None = None,
) -> PipelineConfig:
    return PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=tmp_path / "output",
        save_intermediate=False,
        irs=irs_config or IRSRuntimeConfig(),
    )


def _patch_all_stages(
    orchestrator: PipelineOrchestrator,
    plan: WorkerPlanIR,
    span_list: list[SpanIR],
    route_ir: FieldRouteIR,
    flow_plan: WorkerFlowPlanIR,
    block_plan: WorkerBlockPlanIR,
    symbols: SymbolTable,
):
    """Return a context manager that patches all stages for a full run."""
    worker_scoped_resources = WorkerScopedResourceIR(
        global_resources=ResourceRegistryIR()
    )
    return (
        patch.object(orchestrator, "_run_stage1", return_value=span_list),
        patch.object(orchestrator, "_run_stage2", return_value=(route_ir, [])),
        patch.object(orchestrator, "_run_stage3", return_value=(span_list, route_ir)),
        patch.object(orchestrator, "_run_stage3_5", return_value=plan),
        patch.object(orchestrator, "_run_stage4", return_value=flow_plan),
        patch.object(orchestrator, "_run_stage5", return_value=block_plan),
        patch.object(
            orchestrator,
            "_run_stage6_worker_scoped",
            return_value=(worker_scoped_resources, symbols, []),
        ),
        patch.object(
            orchestrator,
            "_run_stage7_worker_scoped",
            return_value=(MagicMock(), symbols, []),
        ),
        patch.object(orchestrator, "_run_stage8", return_value=MagicMock()),
        patch.object(orchestrator, "_run_stage9", return_value=[]),
        patch.object(
            orchestrator,
            "_run_normalization_worker_scoped",
            return_value=(flow_plan, block_plan, MagicMock(), symbols, [], []),
        ),
        patch.object(
            orchestrator, "_run_stage10_worker_scoped", return_value=MagicMock()
        ),
        patch.object(orchestrator, "_run_stage11", return_value=("SPL", [], [])),
    )


# ------------------------------------------------------------------
# 1. config.irs.enabled=False → no construct_satisfaction
# ------------------------------------------------------------------


class TestIRSDisabled:
    """Verify IRS subsystem produces no results when disabled."""

    def test_no_construct_satisfaction_when_disabled(self, tmp_path: Path) -> None:
        irs_config = IRSRuntimeConfig(enabled=False)
        config = _make_config(tmp_path, irs_config)
        orchestrator = PipelineOrchestrator(config)
        plan = _worker_plan()
        span_list = _spans()
        route_ir = _routes()
        flow_plan = _worker_flow_plan()
        block_plan = _worker_block_plan()
        symbols = SymbolTable()

        patches = _patch_all_stages(
            orchestrator, plan, span_list, route_ir, flow_plan, block_plan, symbols
        )
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result = orchestrator.run("test input")

        intermediate = result.intermediate_results
        # construct_satisfaction should be empty when IRS is disabled
        assert intermediate.get("construct_satisfaction", {}) == {}

    def test_no_stage_local_diagnostics_when_disabled(self, tmp_path: Path) -> None:
        irs_config = IRSRuntimeConfig(enabled=False)
        config = _make_config(tmp_path, irs_config)
        orchestrator = PipelineOrchestrator(config)
        plan = _worker_plan()
        span_list = _spans()
        route_ir = _routes()
        flow_plan = _worker_flow_plan()
        block_plan = _worker_block_plan()
        symbols = SymbolTable()

        patches = _patch_all_stages(
            orchestrator, plan, span_list, route_ir, flow_plan, block_plan, symbols
        )
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result = orchestrator.run("test input")

        intermediate = result.intermediate_results
        # No IRS stage_local_diagnostics entries (stage2 may still exist)
        irs_keys = {
            k for k in intermediate.get("stage_local_diagnostics", {})
            if k.startswith("stage3") or k.startswith("stage4") or k == "stage7"
        }
        assert irs_keys == set()


# ------------------------------------------------------------------
# 2-4. Stage-local reports produced
# ------------------------------------------------------------------


class TestStageLocalReports:
    """Verify stage-local IRS reports are produced for each stage."""

    def test_stage3_5_reports_in_intermediate(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        orchestrator = PipelineOrchestrator(config)
        plan = _worker_plan()
        span_list = _spans()
        route_ir = _routes()
        flow_plan = _worker_flow_plan()
        block_plan = _worker_block_plan()
        symbols = SymbolTable()

        patches = _patch_all_stages(
            orchestrator, plan, span_list, route_ir, flow_plan, block_plan, symbols
        )
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result = orchestrator.run("test input")

        intermediate = result.intermediate_results
        assert "stage3_5" in intermediate.get("construct_satisfaction", {})

    def test_stage4_reports_in_intermediate(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        orchestrator = PipelineOrchestrator(config)
        plan = _worker_plan()
        span_list = _spans()
        route_ir = _routes()
        flow_plan = _worker_flow_plan()
        block_plan = _worker_block_plan()
        symbols = SymbolTable()

        patches = _patch_all_stages(
            orchestrator, plan, span_list, route_ir, flow_plan, block_plan, symbols
        )
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result = orchestrator.run("test input")

        intermediate = result.intermediate_results
        assert "stage4" in intermediate.get("construct_satisfaction", {})

    def test_stage7_reports_in_intermediate(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        orchestrator = PipelineOrchestrator(config)
        plan = _worker_plan()
        span_list = _spans()
        route_ir = _routes()
        flow_plan = _worker_flow_plan()
        block_plan = _worker_block_plan()
        symbols = SymbolTable()

        patches = _patch_all_stages(
            orchestrator, plan, span_list, route_ir, flow_plan, block_plan, symbols
        )
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result = orchestrator.run("test input")

        intermediate = result.intermediate_results
        assert "stage7" in intermediate.get("construct_satisfaction", {})


# ------------------------------------------------------------------
# 5-7. Stage-local IRS does not modify IR objects
# ------------------------------------------------------------------


class TestIRNotModified:
    """Verify stage-local IRS does not mutate IR objects."""

    def test_worker_plan_not_modified(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        orchestrator = PipelineOrchestrator(config)
        plan = _worker_plan()
        original_span_ids = {
            w.worker_id: list(w.owned_span_ids) for w in plan.workers
        }
        span_list = _spans()
        route_ir = _routes()
        flow_plan = _worker_flow_plan()
        block_plan = _worker_block_plan()
        symbols = SymbolTable()

        patches = _patch_all_stages(
            orchestrator, plan, span_list, route_ir, flow_plan, block_plan, symbols
        )
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result = orchestrator.run("test input")

        # WorkerPlanIR should not be mutated
        for w in plan.workers:
            assert list(w.owned_span_ids) == original_span_ids[w.worker_id]

    def test_worker_flow_plan_not_modified(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        orchestrator = PipelineOrchestrator(config)
        plan = _worker_plan()
        flow_plan = _worker_flow_plan()
        original_flow_keys = set(flow_plan.worker_flows.keys())
        span_list = _spans()
        route_ir = _routes()
        block_plan = _worker_block_plan()
        symbols = SymbolTable()

        patches = _patch_all_stages(
            orchestrator, plan, span_list, route_ir, flow_plan, block_plan, symbols
        )
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result = orchestrator.run("test input")

        assert set(flow_plan.worker_flows.keys()) == original_flow_keys

    def test_worker_step_plan_not_modified(self, tmp_path: Path) -> None:
        """The step plan returned by _run_stage7_worker_scoped is a MagicMock,
        so we verify it's passed through unchanged."""
        config = _make_config(tmp_path)
        orchestrator = PipelineOrchestrator(config)
        plan = _worker_plan()
        span_list = _spans()
        route_ir = _routes()
        flow_plan = _worker_flow_plan()
        block_plan = _worker_block_plan()
        symbols = SymbolTable()
        mock_step_plan = MagicMock()

        worker_scoped_resources = WorkerScopedResourceIR(
            global_resources=ResourceRegistryIR()
        )
        with (
            patch.object(orchestrator, "_run_stage1", return_value=span_list),
            patch.object(orchestrator, "_run_stage2", return_value=(route_ir, [])),
            patch.object(orchestrator, "_run_stage3", return_value=(span_list, route_ir)),
            patch.object(orchestrator, "_run_stage3_5", return_value=plan),
            patch.object(orchestrator, "_run_stage4", return_value=flow_plan),
            patch.object(orchestrator, "_run_stage5", return_value=block_plan),
            patch.object(
                orchestrator,
                "_run_stage6_worker_scoped",
                return_value=(worker_scoped_resources, symbols, []),
            ),
            patch.object(
                orchestrator,
                "_run_stage7_worker_scoped",
                return_value=(mock_step_plan, symbols, []),
            ),
            patch.object(orchestrator, "_run_stage8", return_value=MagicMock()),
            patch.object(orchestrator, "_run_stage9", return_value=[]),
            patch.object(
                orchestrator,
                "_run_normalization_worker_scoped",
                return_value=(flow_plan, block_plan, MagicMock(), symbols, [], []),
            ),
            patch.object(
                orchestrator, "_run_stage10_worker_scoped", return_value=MagicMock()
            ),
            patch.object(orchestrator, "_run_stage11", return_value=("SPL", [], [])),
        ):
            result = orchestrator.run("test input")

        assert result.intermediate_results["stage7_worker_step_plan"] is mock_step_plan


# ------------------------------------------------------------------
# 8. Stage-local diagnostics default not in compile_diagnostics
# ------------------------------------------------------------------


class TestStageLocalDiagnosticsNotInFinal:
    """Verify stage-local IRS diagnostics do not enter compile_diagnostics by default."""

    def test_stage_local_irs_diags_not_in_compile_diagnostics(
        self, tmp_path: Path,
    ) -> None:
        config = _make_config(tmp_path)
        orchestrator = PipelineOrchestrator(config)
        plan = _worker_plan()
        span_list = _spans()
        route_ir = _routes()
        flow_plan = _worker_flow_plan()
        block_plan = _worker_block_plan()
        symbols = SymbolTable()

        patches = _patch_all_stages(
            orchestrator, plan, span_list, route_ir, flow_plan, block_plan, symbols
        )
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            result = orchestrator.run("test input")

        # IRS stage-local diagnostics are in intermediate but NOT in compile_diagnostics
        irs_stage_diag_ids = set()
        for stage_name, diags in result.intermediate_results.get(
            "stage_local_diagnostics", {}
        ).items():
            if stage_name in ("stage3_5", "stage4", "stage7"):
                irs_stage_diag_ids.update(d.diagnostic_id for d in diags)

        compile_diag_ids = {d.diagnostic_id for d in result.compile_diagnostics}
        # No overlap — stage-local IRS diags should not be in final diagnostics
        assert irs_stage_diag_ids.isdisjoint(compile_diag_ids)


# ------------------------------------------------------------------
# 9. Existing SPL output unchanged
# ------------------------------------------------------------------


class TestSPLOutputStable:
    """Verify SPL output is not changed by stage-local IRS."""

    def test_spl_output_unchanged(self, tmp_path: Path) -> None:
        # Run without IRS
        config_no_irs = _make_config(tmp_path / "no_irs", IRSRuntimeConfig(enabled=False))
        orchestrator_no_irs = PipelineOrchestrator(config_no_irs)
        plan = _worker_plan()
        span_list = _spans()
        route_ir = _routes()
        flow_plan = _worker_flow_plan()
        block_plan = _worker_block_plan()
        symbols = SymbolTable()

        patches1 = _patch_all_stages(
            orchestrator_no_irs, plan, span_list, route_ir, flow_plan, block_plan, symbols
        )
        with ExitStack() as stack:
            for p in patches1:
                stack.enter_context(p)
            result_no_irs = orchestrator_no_irs.run("test input")

        # Run with IRS
        config_with_irs = _make_config(tmp_path / "with_irs", IRSRuntimeConfig())
        orchestrator_with_irs = PipelineOrchestrator(config_with_irs)

        patches2 = _patch_all_stages(
            orchestrator_with_irs, plan, span_list, route_ir, flow_plan, block_plan, symbols
        )
        with ExitStack() as stack:
            for p in patches2:
                stack.enter_context(p)
            result_with_irs = orchestrator_with_irs.run("test input")

        # SPL text should be identical
        assert result_no_irs.spl_text == result_with_irs.spl_text


# ------------------------------------------------------------------
# 10. WorkerPlanValidator failure → no IRS
# ------------------------------------------------------------------


class TestValidationFailureNoIRS:
    """Verify IRS does not run when WorkerPlanValidator fails."""

    def test_validation_failure_skips_irs(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        orchestrator = PipelineOrchestrator(config)
        span_list = _spans()
        route_ir = _routes()

        # Create a plan that will fail validation (empty workers)
        bad_plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[],
            candidates=[],
            decisions=[],
            handoffs=[],
        )

        flow_plan = _worker_flow_plan()
        block_plan = _worker_block_plan()
        symbols = SymbolTable()

        worker_scoped_resources = WorkerScopedResourceIR(
            global_resources=ResourceRegistryIR()
        )
        with (
            patch.object(orchestrator, "_run_stage1", return_value=span_list),
            patch.object(orchestrator, "_run_stage2", return_value=(route_ir, [])),
            patch.object(orchestrator, "_run_stage3", return_value=(span_list, route_ir)),
            patch.object(orchestrator, "_run_stage3_5", return_value=bad_plan),
        ):
            with pytest.raises(ValueError, match="WorkerPlanIR validation failed"):
                orchestrator.run("test input")

        # If validation fails, we never reach IRS — no construct_satisfaction
        # This is verified by the ValueError being raised before IRS runs
