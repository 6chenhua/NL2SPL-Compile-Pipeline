from __future__ import annotations

from nl2spl.compiler.construct_plan import ConstructPlanner
from nl2spl.compiler.construct_plan.exception_materializer import (
    materialize_exception_flows_from_construct_plan,
    materialize_handler_blocks_from_construct_plan,
    materialize_worker_exception_flows_from_construct_plan,
)
from nl2spl.config import PipelineConfig
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
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
from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler
from nl2spl.pipeline.stages.stage5_block_assembler import BlockAssembler
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor
from nl2spl.pipeline.stages.stage7_step_extractor.worker_scoped import (
    _materialize_exception_handler_steps,
)


class _FakeClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[dict[str, str]] = []

    def call_json(self, **kwargs: str) -> dict:
        self.calls.append(dict(kwargs))
        return self.response


def _span(span_id: str, text: str, section: str = "sec_failure") -> SpanIR:
    return SpanIR(
        span_id=span_id,
        text=text,
        source_section_id=section,
        source_packet_id=f"p_{span_id}",
    )


def _condition(span_id: str, *, group: str = "g1") -> RouteAnnotation:
    return RouteAnnotation(
        span_id=span_id,
        field="behavior",
        semantic_role="failure_mode",
        route_family="exception",
        construct_target="EXCEPTION_FLOW",
        slot_target="condition",
        executable=False,
        source_section_id="sec_failure",
        source_packet_id=f"p_{span_id}",
        metadata={"construct_group_id": group},
    )


def _handler(span_id: str, *, group: str = "g1") -> RouteAnnotation:
    return RouteAnnotation(
        span_id=span_id,
        field="behavior",
        semantic_role="exception_handler_action",
        route_family="exception",
        construct_target="EXCEPTION_FLOW",
        slot_target="handler",
        executable=True,
        source_section_id="sec_failure",
        source_packet_id=f"p_{span_id}",
        metadata={"construct_group_id": group},
    )


def test_construct_plan_pairs_condition_and_handler_into_one_demand() -> None:
    spans = [_span("s2", "Missing timeframe."), _span("s3", "Ask user for timeframe.")]
    routes = FieldRouteIR(
        behavior=["s2", "s3"],
        annotations=[_condition("s2"), _handler("s3")],
    )

    plan = ConstructPlanner().plan(spans, routes)

    demands = plan.exception_flow_demands()
    assert len(demands) == 1
    demand = demands[0]
    assert demand.condition_span_ids == ["s2"]
    assert demand.handler_span_ids == ["s3"]
    assert demand.slots["condition"].source_span_ids == ["s2"]
    assert demand.slots["handler"].source_span_ids == ["s3"]
    assert demand.pairing_status == "condition_with_handler"
    assert "s3" in plan.reserved_span_ids


def test_guarded_exception_span_owns_condition_and_handler_without_reservation() -> None:
    span = SpanIR(
        span_id="s2",
        text="If information is missing, ask the user.",
        source_section_id="sec_failure",
        source_packet_id="p_s2",
        segmentation_kind="guarded_action",
        guard_text_exact="information is missing",
        action_text_exact="ask the user",
    )
    routes = FieldRouteIR(
        behavior=["s2"],
        annotations=[
            _condition("s2"),
            _handler("s2"),
        ],
    )

    plan = ConstructPlanner().plan([span], routes)

    demand = plan.exception_flow_demands()[0]
    assert demand.condition_text == "information is missing"
    assert demand.condition_span_ids == ["s2"]
    assert demand.handler_span_ids == ["s2"]
    assert demand.pairing_status == "condition_with_handler"
    assert "s2" in plan.dual_role_span_ids
    assert "s2" not in plan.reserved_without_dual_role()


def test_adjacent_orphan_handler_extends_previous_exception_demand() -> None:
    condition_span = SpanIR(
        span_id="s2",
        text="If instructions conflict, document the conflict.",
        source_section_id="sec_failure",
        source_packet_id="p_s2",
        segmentation_kind="guarded_action",
        guard_text_exact="instructions conflict",
        action_text_exact="document the conflict",
    )
    continuation = _span(
        "s3",
        "Do not finalize until the conflict is resolved.",
    )
    routes = FieldRouteIR(
        behavior=["s2", "s3"],
        annotations=[
            _condition("s2", group="g1"),
            _handler("s2", group="g1"),
            _handler("s3", group="g2"),
        ],
    )

    plan = ConstructPlanner().plan(
        [condition_span, continuation],
        routes,
    )

    assert len(plan.exception_flow_demands()) == 1
    demand = plan.exception_flow_demands()[0]
    assert demand.handler_span_ids == ["s2", "s3"]
    assert demand.metadata["adjacent_handler_continuation"] == "s3"
    assert "s3" in demand.reserved_span_ids


def test_dual_role_handler_is_not_reserved_from_executable_candidates() -> None:
    spans = [_span("s2", "Missing timeframe."), _span("s3", "Ask user for timeframe.")]
    routes = FieldRouteIR(
        behavior=["s2", "s3"],
        annotations=[
            _condition("s2"),
            _handler("s3"),
            RouteAnnotation(
                span_id="s3",
                field="behavior",
                semantic_role="process_step",
                executable=True,
                source_section_id="sec_failure",
                source_packet_id="p_s3",
            ),
        ],
    )

    plan = ConstructPlanner().plan(spans, routes)

    assert "s3" in plan.dual_role_span_ids
    assert "s3" not in plan.reserved_without_dual_role()


def test_condition_only_materializes_partial_skeleton() -> None:
    spans = [_span("s2", "Missing timeframe.")]
    routes = FieldRouteIR(behavior=["s2"], annotations=[_condition("s2")])
    plan = ConstructPlanner().plan(spans, routes)

    flow = materialize_exception_flows_from_construct_plan(
        FlowStructureIR(),
        plan,
        spans,
    )

    assert len(flow.exception_flows) == 1
    assert flow.exception_flows[0].condition_text == "Missing timeframe."
    assert flow.exception_flows[0].spans == ["s2"]


def test_worker_ownership_moves_handler_to_condition_owner() -> None:
    spans = [_span("s2", "Missing timeframe."), _span("s3", "Ask user for timeframe.")]
    routes = FieldRouteIR(
        behavior=["s2", "s3"],
        annotations=[_condition("s2"), _handler("s3")],
    )
    plan = ConstructPlanner().plan(spans, routes)
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="Main",
                kind="main",
                purpose="main",
                owned_span_ids=["s2"],
            ),
            WorkerSpecIR(
                worker_id="worker_child",
                worker_name="Child",
                kind="child",
                purpose="child",
                owned_span_ids=["s3"],
            ),
        ],
    )

    warnings = plan.enforce_exception_flow_ownership(worker_plan)

    assert warnings
    assert worker_plan.workers[0].owned_span_ids == ["s2", "s3"]
    assert worker_plan.workers[1].owned_span_ids == []


def test_multiple_conditions_and_handlers_are_not_force_paired() -> None:
    spans = [
        _span("s2", "Missing timeframe."),
        _span("s3", "Ask user for timeframe."),
        _span("s4", "Missing evidence."),
        _span("s5", "Ask user for evidence."),
    ]
    routes = FieldRouteIR(
        behavior=["s2", "s3", "s4", "s5"],
        annotations=[
            _condition("s2", group="same"),
            _handler("s3", group="same"),
            _condition("s4", group="same"),
            _handler("s5", group="same"),
        ],
    )

    plan = ConstructPlanner().plan(spans, routes)

    assert [d.condition_span_ids for d in plan.exception_flow_demands()] == [
        ["s2"],
        ["s4"],
    ]
    assert all(d.handler_span_ids == [] for d in plan.exception_flow_demands())
    assert {d.pairing_status for d in plan.exception_flow_demands()} == {
        "ambiguous_pairing"
    }
    assert plan.reserved_span_ids == {"s3", "s5"}
    assert [diag.kind for diag in plan.diagnostics] == [
        "construct_plan_ambiguous_exception_pairing"
    ]


def test_stage4_consumes_construct_plan_reserved_spans(tmp_path) -> None:
    spans = [_span("s2", "Missing timeframe."), _span("s3", "Ask user for timeframe.")]
    routes = FieldRouteIR(
        behavior=["s2", "s3"],
        annotations=[_condition("s2"), _handler("s3")],
    )
    plan = ConstructPlanner().plan(spans, routes)
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="Main",
                kind="main",
                purpose="main",
                owned_span_ids=["s2", "s3"],
            )
        ],
    )
    stage = FlowAssembler(
        PipelineConfig(output_dir=tmp_path, run_name="run", save_intermediate=False),
        _FakeClient({"main_flow_spans": ["s3"], "exception_flows": []}),
    )

    result = stage.execute((spans, routes, worker_plan, plan))

    worker_flow = result.worker_flows["worker_main"]
    assert worker_flow.main_flow_spans == []
    assert len(worker_flow.exception_flows) == 1
    assert worker_flow.exception_flows[0].spans == ["s2"]


def test_stage7_consumes_construct_plan_reserved_spans(tmp_path) -> None:
    spans = [_span("s2", "Missing timeframe."), _span("s3", "Ask user for timeframe.")]
    routes = FieldRouteIR(
        behavior=["s2", "s3"],
        annotations=[_condition("s2"), _handler("s3")],
    )
    plan = ConstructPlanner().plan(spans, routes)
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="Main",
                kind="main",
                purpose="main",
                owned_span_ids=["s2", "s3"],
            )
        ],
    )
    client = _FakeClient({"steps": []})
    stage = StepExtractor(
        PipelineConfig(output_dir=tmp_path, run_name="run", save_intermediate=False),
        client,
    )
    flow = materialize_exception_flows_from_construct_plan(
        FlowStructureIR(),
        plan,
        spans,
    )
    blocks = materialize_handler_blocks_from_construct_plan(
        BlockStructureIR(),
        flow,
        plan,
    )

    worker_steps, _ = stage.execute_worker_scoped(
        spans,
        routes,
        WorkerFlowPlanIR(
            worker_flows={"worker_main": flow},
        ),
        WorkerBlockPlanIR(
            worker_blocks={"worker_main": blocks},
        ),
        SymbolTable(),
        worker_plan,
        plan,
    )

    user_prompt = client.calls[0]["user_prompt"]
    behavior_section = user_prompt.split("behavior spans:", 1)[1].split(
        "Flow structure:", 1
    )[0]
    assert "Ask user for timeframe" not in behavior_section
    handler_steps = [
        step
        for step in worker_steps.worker_steps["worker_main"]
        if step.source_span_ids == ["s3"]
    ]
    assert len(handler_steps) == 1
    assert handler_steps[0].text == "Ask user for timeframe"
    assert handler_steps[0].flow_ref.startswith("exc_")


def test_stage5_consumes_construct_plan_handler_slot(tmp_path) -> None:
    spans = [_span("s2", "Missing timeframe."), _span("s3", "Ask user for timeframe.")]
    routes = FieldRouteIR(
        behavior=["s2", "s3"],
        annotations=[_condition("s2"), _handler("s3")],
    )
    plan = ConstructPlanner().plan(spans, routes)
    flow = FlowStructureIR(
        exception_flows=[
            materialize_exception_flows_from_construct_plan(
                FlowStructureIR(), plan, spans
            ).exception_flows[0]
        ]
    )
    stage = BlockAssembler(
        PipelineConfig(output_dir=tmp_path, run_name="run", save_intermediate=False),
        _FakeClient(
            {
                "main_flow_blocks": [],
                "alternative_flow_blocks": {},
                "exception_flow_blocks": {},
            }
        ),
    )

    blocks = stage.execute((spans, routes, flow, plan))

    flow_id = flow.exception_flows[0].flow_id
    assert blocks.exception_flow_blocks[flow_id][0].spans == ["s3"]


def test_worker_exception_materialization_replaces_overlapping_stage4_flows() -> None:
    spans = [
        _span("s2", "Missing timeframe."),
        _span("s3", "Ask user for timeframe."),
        _span("s4", "Missing evidence."),
        _span("s5", "Ask user for evidence."),
    ]
    routes = FieldRouteIR(
        behavior=["s2", "s3", "s4", "s5"],
        annotations=[
            _condition("s2", group="g1"),
            _handler("s3", group="g1"),
            _condition("s4", group="g2"),
            _handler("s5", group="g2"),
        ],
    )
    plan = ConstructPlanner().plan(spans, routes)
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="Main",
                kind="main",
                purpose="main",
                owned_span_ids=["s2", "s3", "s4", "s5"],
            )
        ],
    )
    worker_flows = {
        "worker_main": FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_llm_1", "Missing timeframe.", ["s2", "s3"]),
                ExceptionFlow("exc_llm_2", "Missing evidence.", ["s4"]),
            ]
        )
    }

    materialize_worker_exception_flows_from_construct_plan(
        worker_flows,
        plan,
        spans,
        worker_plan,
        [],
    )

    result = worker_flows["worker_main"].exception_flows
    assert [flow.flow_id for flow in result] == ["exc_adapter_00", "exc_adapter_01"]
    assert [flow.spans for flow in result] == [["s2"], ["s4"]]


def test_same_span_condition_handler_uses_sequential_handler_block() -> None:
    span = SpanIR(
        span_id="s2",
        text="If information is missing, ask the user.",
        source_section_id="sec_failure",
        source_packet_id="p_s2",
        segmentation_kind="guarded_action",
        guard_text_exact="information is missing",
        action_text_exact="ask the user",
    )
    routes = FieldRouteIR(
        behavior=["s2"],
        annotations=[_condition("s2"), _handler("s2")],
    )
    plan = ConstructPlanner().plan([span], routes)
    flow = materialize_exception_flows_from_construct_plan(
        FlowStructureIR(),
        plan,
        [span],
    )
    flow_id = flow.exception_flows[0].flow_id
    blocks = materialize_handler_blocks_from_construct_plan(
        BlockStructureIR(
            exception_flow_blocks={
                flow_id: [
                    BlockIR(
                        block_id="b_llm",
                        block_type="IF",
                        condition_text="information is missing",
                        spans=["s2"],
                    )
                ]
            }
        ),
        flow,
        plan,
    )

    assert len(blocks.exception_flow_blocks[flow_id]) == 1
    assert blocks.exception_flow_blocks[flow_id][0].block_type == "SEQUENTIAL"
    assert blocks.exception_flow_blocks[flow_id][0].condition_text is None


def test_stage5_d4_preserves_dual_role_handler_block(tmp_path) -> None:
    span = SpanIR(
        span_id="s2",
        text="If information is missing, ask the user.",
        source_section_id="sec_failure",
        source_packet_id="p_s2",
        segmentation_kind="guarded_action",
        guard_text_exact="information is missing",
        action_text_exact="ask the user",
    )
    routes = FieldRouteIR(
        behavior=["s2"],
        annotations=[_condition("s2"), _handler("s2")],
    )
    plan = ConstructPlanner().plan([span], routes)
    flow = materialize_exception_flows_from_construct_plan(
        FlowStructureIR(),
        plan,
        [span],
    )
    flow_id = flow.exception_flows[0].flow_id
    stage = BlockAssembler(
        PipelineConfig(output_dir=tmp_path, run_name="run", save_intermediate=False),
        _FakeClient(
            {
                "main_flow_blocks": [],
                "alternative_flow_blocks": {},
                "exception_flow_blocks": {
                    flow_id: [
                        {
                            "block_id": "b_llm",
                            "block_type": "IF",
                            "condition_text": "information is missing",
                            "spans": ["s2"],
                        }
                    ]
                },
            }
        ),
    )

    blocks = stage.execute(([span], routes, flow, plan))

    assert len(blocks.exception_flow_blocks[flow_id]) == 1
    assert blocks.exception_flow_blocks[flow_id][0].block_type == "SEQUENTIAL"


def test_construct_plan_replaces_wrongly_placed_dual_role_handler_step() -> None:
    span = SpanIR(
        span_id="s2",
        text="If information is missing, ask the user.",
        source_section_id="sec_failure",
        source_packet_id="p_s2",
        segmentation_kind="guarded_action",
        guard_text_exact="information is missing",
        action_text_exact="ask the user",
    )
    routes = FieldRouteIR(
        behavior=["s2"],
        annotations=[_condition("s2"), _handler("s2")],
    )
    plan = ConstructPlanner().plan([span], routes)
    flow = materialize_exception_flows_from_construct_plan(
        FlowStructureIR(),
        plan,
        [span],
    )
    flow_id = flow.exception_flows[0].flow_id
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="Main",
                kind="main",
                purpose="main",
                owned_span_ids=["s2"],
            )
        ],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_wrong",
                    text="Paraphrased handler",
                    source_span_ids=["s2"],
                    command_type="GENERAL_COMMAND",
                    flow_ref="main",
                    block_ref="b_wrong",
                )
            ]
        },
    )

    _materialize_exception_handler_steps(
        worker_steps,
        WorkerFlowPlanIR(worker_flows={"worker_main": flow}),
        WorkerBlockPlanIR(
            worker_blocks={
                "worker_main": BlockStructureIR(
                    exception_flow_blocks={
                        flow_id: [
                            BlockIR(
                                block_id="b_handler",
                                block_type="SEQUENTIAL",
                                spans=["s2"],
                            )
                        ]
                    }
                )
            }
        ),
        worker_plan,
        plan,
        [span],
    )

    result = worker_steps.worker_steps["worker_main"]
    assert len(result) == 1
    assert result[0].step_id == f"st_exception_{flow_id}_s2"
    assert result[0].text == "ask the user"
    assert result[0].flow_ref == flow_id
    assert result[0].block_ref == "b_handler"
