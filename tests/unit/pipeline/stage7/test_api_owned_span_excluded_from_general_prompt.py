from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.compiler.construct_plan import APICallDemand, ConstructPlan, OperationCoverageIR
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR
from nl2spl.pipeline.stages.stage7_step_extractor.extractor import StepExtractor


def test_api_consumed_span_is_not_sent_to_general_step_prompt() -> None:
    client = MagicMock()
    client.call_json.return_value = {"steps": [], "new_variables": []}
    extractor = StepExtractor(MagicMock(), client)
    extractor._pending_unmapped_data = {}

    spans = [
        SpanIR(span_id="s1", text="Prepare request."),
        SpanIR(span_id="s2", text="retrieve them using approved source recipes."),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
    blocks = BlockStructureIR(
        main_flow_blocks=[
            BlockIR(block_id="b_main", block_type="SEQUENTIAL", spans=["s1", "s2"])
        ]
    )
    worker = WorkerSpecIR(
        worker_id="worker_main",
        worker_name="MainWorker",
        kind="main",
        purpose="Main worker.",
        owned_span_ids=["s1", "s2"],
    )
    worker_plan = WorkerPlanIR(main_worker_id="worker_main", workers=[worker])
    construct_plan = ConstructPlan(
        plan_id="cp",
        demands=[
            APICallDemand(
                demand_id="api_call_s2",
                declaration_demand_id="api_decl_s2",
                source_span_ids=["s2"],
                operation_coverage=[
                    OperationCoverageIR(
                        coverage_id="cov_s2",
                        source_span_id="s2",
                        operation_surface="retrieve them using approved source recipes",
                        char_start=0,
                        char_end=len("retrieve them using approved source recipes"),
                    )
                ],
                consumes_behavior_span_ids=["s2"],
                residual_behavior_span_ids=["s2"],
                behavior_lowering_policy="api_call_augments_behavior",
            )
        ],
    )

    extractor._extract_steps_for_worker(
        spans,
        routes,
        flow,
        blocks,
        SymbolTable(),
        worker,
        worker_plan,
        construct_plan,
    )

    user_prompt = client.call_json.call_args.kwargs["user_prompt"]
    assert "Prepare request." in user_prompt
    assert "retrieve them using approved source recipes" not in user_prompt
