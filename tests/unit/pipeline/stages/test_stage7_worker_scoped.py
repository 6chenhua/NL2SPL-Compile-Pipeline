"""Unit tests for Stage 7 worker-scoped step extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor


def _contract(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(
        name=name,
        data_type="text",
        required=True,
        description=name,
        source=source,  # type: ignore[arg-type]
    )


def _worker_plan(handoff: WorkerHandoffIR) -> WorkerPlanIR:
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker",
                owned_span_ids=["s1"],
                input_contract=[_contract("request")],
                output_contract=[_contract("result", "output")],
            ),
            WorkerSpecIR(
                worker_id="worker_child",
                worker_name="ChildWorker",
                kind="child",
                purpose="Child worker",
                owned_span_ids=["s2"],
                input_contract=[_contract("child_input")],
                output_contract=[_contract("child_output", "output")],
            ),
        ],
        handoffs=[handoff],
    )


def _flow_plan() -> WorkerFlowPlanIR:
    return WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(main_flow_spans=["s1"]),
            "worker_child": FlowStructureIR(main_flow_spans=["s2"]),
        }
    )


def _block_plan() -> WorkerBlockPlanIR:
    return WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR("b_main", "SEQUENTIAL", spans=["s1"]),
                ]
            ),
            "worker_child": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR("b_child", "SEQUENTIAL", spans=["s2"]),
                ]
            ),
        }
    )


def _extractor(pipeline_config: MagicMock) -> StepExtractor:
    client = MagicMock()
    client.call_json.return_value = {"steps": [], "new_variables": []}
    return StepExtractor(pipeline_config, client)


def test_child_origin_handoff_is_injected_into_child_worker(
    pipeline_config: MagicMock,
) -> None:
    handoff = WorkerHandoffIR(
        handoff_id="handoff_child_api",
        from_worker="worker_child",
        to_worker=None,
        api_ref="ChildApi",
        mode="api_call",
        condition_text=None,
        ordering="after",
        input_bindings=[InputBindingIR("child_input", "query", True)],
        output_bindings=[OutputBindingIR("api_result", "child_output", True, "set")],
        invoke_location_hint=InvokeLocationHintIR("main", None, "s2", None, "sequential"),
    )

    worker_step_plan, _ = _extractor(pipeline_config).execute_worker_scoped(
        spans=[SpanIR("s1", "Main work"), SpanIR("s2", "Child work")],
        routes=FieldRouteIR(behavior=["s1", "s2"], integrations=[]),
        worker_flow_plan=_flow_plan(),
        worker_block_plan=_block_plan(),
        symbol_table=SymbolTable(),
        worker_plan=_worker_plan(handoff),
    )

    assert worker_step_plan.worker_steps["worker_main"] == []
    child_steps = worker_step_plan.worker_steps["worker_child"]
    assert len(child_steps) == 1
    assert child_steps[0].handoff_id == "handoff_child_api"
    assert child_steps[0].command_type == "CALL_API"
    assert child_steps[0].integration_ref == "ChildApi"


def test_invalid_invoke_location_returns_empty_source_spans(
    pipeline_config: MagicMock,
) -> None:
    handoff = WorkerHandoffIR(
        handoff_id="handoff_bad_location",
        from_worker="worker_child",
        to_worker=None,
        api_ref="ChildApi",
        mode="api_call",
        condition_text=None,
        ordering="after",
        invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, "sequential"),
    )
    worker_plan = _worker_plan(handoff)

    source_spans = _extractor(pipeline_config)._get_invoke_source_spans(
        handoff,
        worker_plan,
    )

    assert source_spans == []


def test_child_worker_invalid_invoke_step_is_rewritten_to_command(
    pipeline_config: MagicMock,
) -> None:
    handoff = WorkerHandoffIR(
        handoff_id="handoff_parent_to_child",
        from_worker="worker_main",
        to_worker="worker_child",
        api_ref=None,
        mode="invoke",
        condition_text=None,
        ordering="after",
        input_bindings=[InputBindingIR("child_input", "child_input", True)],
        output_bindings=[OutputBindingIR("child_output", "child_output", True, "set")],
        invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, "sequential"),
    )
    worker_plan = _worker_plan(handoff)
    client = MagicMock()
    client.call_json.side_effect = [
        {"steps": [], "new_variables": []},
        {
            "steps": [
                {
                    "step_id": "st_child_bad_invoke",
                    "text": "Solicit quotes or equivalent offers according to policy.",
                    "source_span_ids": ["s2"],
                    "command_type": "INVOKE_WORKER",
                    "inputs": ["child_input"],
                    "outputs": ["child_output"],
                    "handoff_id": "not_a_real_child_handoff",
                }
            ],
            "new_variables": [],
        },
    ]

    worker_step_plan, _ = StepExtractor(
        pipeline_config,
        client,
    ).execute_worker_scoped(
        spans=[SpanIR("s1", "Main work"), SpanIR("s2", "Child work")],
        routes=FieldRouteIR(behavior=["s1", "s2"], integrations=[]),
        worker_flow_plan=_flow_plan(),
        worker_block_plan=_block_plan(),
        symbol_table=SymbolTable(),
        worker_plan=worker_plan,
    )

    child_steps = worker_step_plan.worker_steps["worker_child"]
    assert child_steps[0].step_id == "st_child_bad_invoke"
    assert child_steps[0].command_type == "GENERAL_COMMAND"
    assert child_steps[0].source_span_ids == ["s2"]
