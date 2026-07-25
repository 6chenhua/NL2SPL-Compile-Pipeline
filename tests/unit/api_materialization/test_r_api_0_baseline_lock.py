from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerBoundaryDecisionIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor
from nl2spl.pipeline.stages.stage11_spl_renderer import SPLRenderer


class TestRAPIBaselineLockUnit:
    """Baseline lock tests for unit components."""

    def test_renderer_rejects_missing_call_api_integration_ref(self) -> None:
        """R-API-5 regression: CALL_API without integration_ref must not render as 'Api'."""
        renderer = SPLRenderer()
        step = StepIR(
            step_id="st1",
            text="Execute API call",
            source_span_ids=["s1"],
            command_type="CALL_API",
            integration_ref=None,  # Missing API name reference!
        )

        with pytest.raises(ValueError, match="has no integration_ref"):
            renderer._render_step(step)

    def test_compile_as_call_api_currently_not_consumed_by_stage6(self) -> None:
        """Lock current behavior: compile_as_call_api boundary decision does not create APISpec.

        Current Gap: Stage 6 resource extractor does not consume compile_as_call_api to generate APISpec.
        Future Behavior: compile_as_call_api remains a lowering hint and is NOT treated as an API declaration
        source evidence to generate APISpec.
        """
        config = MagicMock()
        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "variables": [],
            "files": [],
            "apis": [],
            "types": [],
        }
        extractor = ResourceExtractor(config, mock_client)

        decision = WorkerBoundaryDecisionIR(
            candidate_id="cand_1",
            decision="compile_as_call_api",
            boundary_strength="strong",
            boundary_kind="integration_wrapper",
            rejection_reason=None,
            reason="API boundary",
        )

        worker_plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_main",
                    worker_name="MainWorker",
                    kind="main",
                    purpose="Main worker",
                    owned_span_ids=["s1"],
                )
            ],
            decisions=[decision],
        )

        spans = [SpanIR(span_id="s1", text="Call external SearchAPI service.")]
        routes = FieldRouteIR(behavior=["s1"])
        flow_plan = WorkerFlowPlanIR(worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])})
        block_plan = WorkerBlockPlanIR(
            worker_blocks={"worker_main": BlockStructureIR(main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])])}
        )

        worker_res_plan, _ = extractor.execute_worker_scoped(
            spans, routes, flow_plan, block_plan, worker_plan
        )

        # Assert current gap / baseline: no APISpec generated in resources
        main_res = worker_res_plan.worker_resources.get("worker_main")
        assert main_res is None or len(main_res.apis) == 0

    def test_stage7_handoff_generated_call_api_requires_api_call_mode(self) -> None:
        """Lock deterministic path: Stage 7 handoff step generator only creates CALL_API for api_call mode handoffs.

        Deterministic Baseline: Without a WorkerHandoffIR(mode="api_call"), Stage 7's deterministic handoff
        generator produces no CALL_API steps.
        """
        config = MagicMock()
        mock_client = MagicMock()
        mock_client.call_json.return_value = {"steps": []}
        extractor = StepExtractor(config, mock_client)

        worker_plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_main",
                    worker_name="MainWorker",
                    kind="main",
                    purpose="Main worker",
                    owned_span_ids=["s1"],
                )
            ],
            handoffs=[],  # No handoffs!
        )

        spans = [SpanIR(span_id="s1", text="Call weather API")]
        routes = FieldRouteIR(behavior=["s1"])
        flow_plan = WorkerFlowPlanIR(worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])})
        block_plan = WorkerBlockPlanIR(
            worker_blocks={"worker_main": BlockStructureIR(main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])])}
        )

        worker_step_plan, _ = extractor.execute_worker_scoped(
            spans, routes, flow_plan, block_plan, SymbolTable(), worker_plan
        )

        steps = worker_step_plan.worker_steps.get("worker_main", [])
        # Assert deterministic path produces zero steps when LLM returns none and handoffs=[]
        assert len(steps) == 0

    def test_stage7_currently_accepts_unbounded_llm_call_api_in_main_worker(self) -> None:
        """Lock current gap/leak: Stage 7 currently accepts raw LLM-emitted CALL_API for main worker without handoff.

        Current Gap / Drift: In worker_scoped.py, invalid handoff-command validation only checks child workers
        (worker.kind == "child"). When worker.kind == "main", raw LLM-emitted CALL_API commands without a backing
        handoff are accepted directly into worker_steps.
        Future Behavior (R-API-4): Stage 7 will sanitize/reject unplaced and undeclared CALL_API demands and enforce
        placement authority across all workers.
        """
        config = MagicMock()
        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st1",
                    "text": "Call weather API via SearchAPI",
                    "source_span_ids": ["s1"],
                    "command_type": "CALL_API",
                    "integration_ref": "SearchAPI",
                }
            ]
        }
        extractor = StepExtractor(config, mock_client)

        worker_plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_main",
                    worker_name="MainWorker",
                    kind="main",
                    purpose="Main worker",
                    owned_span_ids=["s1"],
                )
            ],
            handoffs=[],  # No handoffs!
        )

        spans = [SpanIR(span_id="s1", text="Call weather API via SearchAPI")]
        routes = FieldRouteIR(behavior=["s1"])
        flow_plan = WorkerFlowPlanIR(worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])})
        block_plan = WorkerBlockPlanIR(
            worker_blocks={"worker_main": BlockStructureIR(main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])])}
        )

        worker_step_plan, _ = extractor.execute_worker_scoped(
            spans, routes, flow_plan, block_plan, SymbolTable(), worker_plan
        )

        steps = worker_step_plan.worker_steps.get("worker_main", [])
        # Assert current gap: main worker accepts raw LLM-emitted CALL_API without handoff
        assert len(steps) == 1
        assert steps[0].command_type == "CALL_API"
        assert steps[0].integration_ref == "SearchAPI"

    def test_api_action_currently_can_fallback_general_command(self) -> None:
        """Lock current behavior: API action falls back to GENERAL_COMMAND in Stage 7 LLM extraction.

        Current Gap: An API call span gets extracted as GENERAL_COMMAND.
        Future Behavior (R-API-4): GENERAL_COMMAND fallback for API call demands will be rejected/sanitized.
        """
        config = MagicMock()
        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st1",
                    "text": "Fetch data from SearchAPI",
                    "source_span_ids": ["s1"],
                    "command_type": "GENERAL_COMMAND",
                }
            ]
        }
        extractor = StepExtractor(config, mock_client)

        worker_plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_main",
                    worker_name="MainWorker",
                    kind="main",
                    purpose="Main worker",
                    owned_span_ids=["s1"],
                )
            ],
        )

        spans = [SpanIR(span_id="s1", text="Fetch data from SearchAPI")]
        routes = FieldRouteIR(behavior=["s1"])
        flow_plan = WorkerFlowPlanIR(worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])})
        block_plan = WorkerBlockPlanIR(
            worker_blocks={"worker_main": BlockStructureIR(main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])])}
        )

        worker_step_plan, _ = extractor.execute_worker_scoped(
            spans, routes, flow_plan, block_plan, SymbolTable(), worker_plan
        )

        steps = worker_step_plan.worker_steps.get("worker_main", [])
        # Assert baseline: API action falls back to GENERAL_COMMAND
        assert len(steps) == 1
        assert steps[0].command_type == "GENERAL_COMMAND"

    def test_worker_candidate_promotion_warning_regression_lock(self) -> None:
        """Lock current regression behavior: WORKER_PROMOTION checker creates promotion instance for compile_as_call_api.

        Current Gap: WorkerDelegationIRSChecker creates WORKER_PROMOTION instances for all candidate task units in
        WorkerPlanIR.candidates, including compile_as_call_api candidates.
        Future Behavior: R-API-1/2 will refine candidate instance extraction so compile_as_call_api is not misdiagnosed
        as a missing child-worker promotion slot.
        """
        from nl2spl.compiler.irs.checker import IRSCheckContext
        from nl2spl.compiler.irs.checkers.worker_delegation import WorkerDelegationIRSChecker
        from nl2spl.ir.worker_plan_ir import CandidateTaskUnitIR

        checker = WorkerDelegationIRSChecker()

        candidate = CandidateTaskUnitIR(
            candidate_id="cand_api_1",
            source_span_ids=["s1"],
            task_text="Retrieve approved sources using SearchAPI",
            purpose="Integration candidate",
            candidate_kind="integration_wrapper",
        )

        worker_plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_main",
                    worker_name="MainWorker",
                    kind="main",
                    purpose="Main worker",
                    owned_span_ids=["s1"],
                )
            ],
            candidates=[candidate],
        )

        context = IRSCheckContext(
            worker_plan=worker_plan,
            stage_name="stage3_5_worker_boundary",
        )

        instances = checker.extract_instances(context)

        # Assert current baseline: WORKER_PROMOTION instance is created for candidate
        promotion_insts = [inst for inst in instances if inst.construct_type == "WORKER_PROMOTION"]
        assert len(promotion_insts) == 1
        assert promotion_insts[0].construct_id == "worker_promotion:cand_api_1"
