"""WorkerPlanIR handoff tests for Stage 7."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import DelegationCandidate, FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor


def field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(name, "text", True, f"{name} field", source)  # type: ignore[arg-type]


def worker_plan() -> WorkerPlanIR:
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "MainWorker",
                "main",
                "Coordinate request",
                owned_span_ids=["s1"],
                input_contract=[field("user_request")],
                output_contract=[field("evidence", "output")],
                boundary_kind="main_worker",
            ),
            WorkerSpecIR(
                "worker_child",
                "SourceWorker",
                "child",
                "Gather source evidence",
                owned_span_ids=["s2"],
                input_contract=[field("source_request")],
                output_contract=[field("source_evidence", "output")],
                boundary_kind="bounded_subtask",
            ),
        ],
        handoffs=[
            WorkerHandoffIR(
                "h1",
                "worker_main",
                "worker_child",
                None,
                "invoke",
                "sources are needed",
                "conditional",
                input_bindings=[InputBindingIR("user_request", "source_request", True)],
                output_bindings=[OutputBindingIR("source_evidence", "evidence", True, "set")],
                invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, "if"),
                input_binding_status="known_present",
                output_binding_status="known_present",
                materialization_status="complete",
            )
        ],
    )


def test_handoff_produces_concrete_invoke_worker(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR("s1", "Decide whether sources are needed."),
        SpanIR("s2", "Gather source evidence."),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    flow = FlowStructureIR(
        main_flow_spans=["s1"],
        delegation_candidates=[
            DelegationCandidate(
                "dc_child",
                ["s2"],
                "Legacy child candidate must not reach Stage 7 prompt.",
                "child_worker",
            )
        ],
    )
    blocks = BlockStructureIR([BlockIR("b1", "IF", "sources are needed", ["s1"])])
    symbols = SymbolTable()
    symbols.declare("user_request", "text", "input", "User request")
    mock_client.call_json.return_value = {"steps": [], "new_variables": []}

    steps, updated_symbols = StepExtractor(pipeline_config, mock_client).execute(
        (spans, routes, flow, blocks, symbols, worker_plan())
    )

    assert len(steps) == 1
    assert steps[0].command_type == "INVOKE_WORKER"
    assert steps[0].integration_ref == "SourceWorker"
    assert steps[0].inputs == ["user_request"]
    assert steps[0].outputs == ["evidence"]
    assert steps[0].handoff_id == "h1"
    assert updated_symbols.variables["evidence"].producer_step == steps[0].step_id

    user_prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
    assert "s1" in user_prompt
    assert "s2" not in user_prompt
    assert "delegation_candidates" in user_prompt
    assert "dc_child" not in user_prompt


def test_partial_unknown_handoff_does_not_produce_legacy_invoke_worker(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR("s1", "Decide whether sources are needed."),
        SpanIR("s2", "Gather source evidence."),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    flow = FlowStructureIR(main_flow_spans=["s1"])
    blocks = BlockStructureIR([BlockIR("b1", "IF", "sources are needed", ["s1"])])
    symbols = SymbolTable()
    symbols.declare("user_request", "text", "input", "User request")
    mock_client.call_json.return_value = {"steps": [], "new_variables": []}
    plan = worker_plan()
    handoff = plan.handoffs[0]
    handoff.input_bindings = []
    handoff.output_bindings = []
    handoff.input_binding_status = "unknown"
    handoff.output_binding_status = "unknown"
    handoff.materialization_status = "partial_contract_unknown"

    steps, updated_symbols = StepExtractor(pipeline_config, mock_client).execute(
        (spans, routes, flow, blocks, symbols, plan)
    )

    assert steps == []
    assert "evidence" not in updated_symbols.variables


def test_stage7_rejects_legacy_main_view_with_child_owned_span(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR("s1", "Decide whether sources are needed."),
        SpanIR("s2", "Gather source evidence."),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
    blocks = BlockStructureIR([BlockIR("b1", "SEQUENTIAL", None, ["s1", "s2"])])
    symbols = SymbolTable()
    symbols.declare("user_request", "text", "input", "User request")
    mock_client.call_json.return_value = {"steps": [], "new_variables": []}

    with pytest.raises(StageError, match="leaked child-owned span"):
        StepExtractor(pipeline_config, mock_client).execute(
            (spans, routes, flow, blocks, symbols, worker_plan())
        )

    mock_client.call_json.assert_not_called()


def test_stage7_rejects_llm_child_owned_step_from_main_view(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR("s1", "Decide whether sources are needed."),
        SpanIR("s2", "Gather source evidence."),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    flow = FlowStructureIR(main_flow_spans=["s1"])
    blocks = BlockStructureIR([BlockIR("b1", "IF", "sources are needed", ["s1"])])
    symbols = SymbolTable()
    symbols.declare("user_request", "text", "input", "User request")
    mock_client.call_json.return_value = {
        "steps": [
            {
                "step_id": "st1",
                "text": "Gather source evidence",
                "source_span_ids": ["s2"],
                "command_type": "GENERAL_COMMAND",
            }
        ],
        "new_variables": [],
    }

    with pytest.raises(StageError, match="generated step"):
        StepExtractor(pipeline_config, mock_client).execute(
            (spans, routes, flow, blocks, symbols, worker_plan())
        )


def test_two_handoffs_to_same_worker_produce_two_invoke_steps(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR("s1", "Gather sources for the main path."),
        SpanIR("s2", "Gather source evidence."),
        SpanIR("s3", "Gather sources during recovery."),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2", "s3"])
    flow = FlowStructureIR(main_flow_spans=["s1", "s3"])
    blocks = BlockStructureIR(
        [
            BlockIR("b1", "IF", "sources are needed", ["s1"]),
            BlockIR("b2", "IF", "recovery needs sources", ["s3"]),
        ]
    )
    symbols = SymbolTable()
    symbols.declare("user_request", "text", "input", "User request")
    mock_client.call_json.return_value = {"steps": [], "new_variables": []}

    plan = worker_plan()
    plan.handoffs = [
        WorkerHandoffIR(
            "h_main",
            "worker_main",
            "worker_child",
            None,
            "invoke",
            "sources are needed",
            "conditional",
            input_bindings=[InputBindingIR("user_request", "source_request", True)],
            output_bindings=[
                OutputBindingIR("source_evidence", "main_evidence", True, "set")
            ],
            invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, "if"),
            input_binding_status="known_present",
            output_binding_status="known_present",
            materialization_status="complete",
        ),
        WorkerHandoffIR(
            "h_recovery",
            "worker_main",
            "worker_child",
            None,
            "invoke",
            "recovery needs sources",
            "conditional",
            input_bindings=[InputBindingIR("user_request", "source_request", True)],
            output_bindings=[
                OutputBindingIR("source_evidence", "recovery_evidence", True, "set")
            ],
            invoke_location_hint=InvokeLocationHintIR("main", None, "s3", None, "if"),
            input_binding_status="known_present",
            output_binding_status="known_present",
            materialization_status="complete",
        ),
    ]

    steps, _ = StepExtractor(pipeline_config, mock_client).execute(
        (spans, routes, flow, blocks, symbols, plan)
    )

    invoke_steps = [step for step in steps if step.command_type == "INVOKE_WORKER"]
    assert len(invoke_steps) == 2
    assert [step.integration_ref for step in invoke_steps] == [
        "SourceWorker",
        "SourceWorker",
    ]
    assert {step.handoff_id for step in invoke_steps} == {"h_main", "h_recovery"}
    assert {tuple(step.outputs) for step in invoke_steps} == {
        ("main_evidence",),
        ("recovery_evidence",),
    }
