"""Unit tests for Stage 7 worker-scoped step extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
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


def test_child_worker_invalid_invoke_step_fails_fast(
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

    with pytest.raises(StageError) as exc_info:
        StepExtractor(
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

    message = str(exc_info.value)
    assert "LLM emitted invalid handoff command(s)" in message
    assert "st_child_bad_invoke:INVOKE_WORKER" in message


def _d6_flow_plan() -> WorkerFlowPlanIR:
    mf = FlowStructureIR(main_flow_spans=["s1", "s2"])
    return WorkerFlowPlanIR(worker_flows={"worker_main": mf})


def _d6_block_plan() -> WorkerBlockPlanIR:
    bs = BlockStructureIR(
        main_flow_blocks=[
            BlockIR("b1", "SEQUENTIAL", None, ["s1"]),
            BlockIR("b2", "SEQUENTIAL", None, ["s2"]),
        ]
    )
    return WorkerBlockPlanIR(worker_blocks={"worker_main": bs})


def test_d6_worker_scoped_filters_non_executable_spans(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D6: worker-scoped Stage 7 excludes non-executable owned spans from steps."""
    handoff = WorkerHandoffIR(
        handoff_id="h_main_child",
        from_worker="worker_main",
        to_worker="worker_child",
        api_ref=None,
        mode="invoke",
        condition_text=None,
        ordering="after",
        input_bindings=[
            InputBindingIR("request_context", "child_input", True),
        ],
        output_bindings=[
            OutputBindingIR("child_output", "evidence_set", True, "set"),
        ],
        invoke_location_hint=InvokeLocationHintIR(
            flow_kind="main", flow_id=None,
            after_span_id="s1", before_span_id=None,
            block_hint="unknown",
        ),
    )
    worker_plan = _worker_plan(handoff)
    # Main worker owns both executable process span and non-executable failure span
    worker_plan.workers[0].owned_span_ids = ["s1", "s2"]

    mock_client.call_json.side_effect = [
        # Main worker LLM: returns bad failure command + good process command
        {
            "steps": [
                {
                    "step_id": "st_bad", "text": "Handle missing timeframe",
                    "source_span_ids": ["s1"], "command_type": "GENERAL_COMMAND",
                    "inputs": [], "outputs": [],
                    "integration_ref": None, "flow_ref": "main",
                    "block_ref": "b1", "kind": "normal",
                },
                {
                    "step_id": "st_good", "text": "Determine type",
                    "source_span_ids": ["s2"], "command_type": "GENERAL_COMMAND",
                    "inputs": [], "outputs": ["communication_type"],
                    "integration_ref": None, "flow_ref": "main",
                    "block_ref": "b2", "kind": "normal",
                },
            ],
            "new_variables": [],
        },
        # Child worker LLM: returns simple step
        {
            "steps": [
                {
                    "step_id": "st_child", "text": "Gather sources",
                    "source_span_ids": ["s2"], "command_type": "GENERAL_COMMAND",
                    "inputs": ["child_input"], "outputs": ["child_output"],
                    "integration_ref": None, "flow_ref": "main",
                    "block_ref": "b2", "kind": "normal",
                },
            ],
            "new_variables": [],
        },
    ]

    worker_step_plan, _ = StepExtractor(
        pipeline_config,
        mock_client,
    ).execute_worker_scoped(
        spans=[
            SpanIR("s1", "Missing timeframe."),
            SpanIR("s2", "Determine type."),
        ],
        routes=FieldRouteIR(
            behavior=["s1", "s2"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s2", field="behavior",
                    semantic_role="process_step", executable=True,
                ),
            ],
        ),
        worker_flow_plan=_d6_flow_plan(),
        worker_block_plan=_d6_block_plan(),
        symbol_table=SymbolTable(),
        worker_plan=worker_plan,
    )

    main_steps = worker_step_plan.worker_steps["worker_main"]
    # Good process step + generated handoff step survive; failure command is filtered
    step_ids = [s.step_id for s in main_steps]
    assert "st_good" in step_ids, f"Good step missing from {step_ids}"
    assert "st_bad" not in step_ids, f"Bad failure step should be filtered, got {step_ids}"
    # Contract-backed handoff step still generated
    handoff_steps = [s for s in main_steps if s.command_type == "INVOKE_WORKER"]
    assert len(handoff_steps) >= 1, "Contract-backed handoff step must survive D6 filter"
    assert handoff_steps[0].handoff_id == "h_main_child"

    # Prompt separation: executable section excludes failure span
    main_worker_prompt = mock_client.call_json.call_args_list[0].kwargs["user_prompt"]
    assert "behavior spans" in main_worker_prompt
    beh_start = main_worker_prompt.index("behavior spans")
    non_exec_idx = main_worker_prompt.index("Non-executable context only")
    beh_section = main_worker_prompt[beh_start:non_exec_idx]
    non_exec_section = main_worker_prompt[non_exec_idx:]

    assert "Determine type" in beh_section
    assert "Missing timeframe" not in beh_section, (
        "Failure span must not appear in executable behavior section"
    )
    assert "Missing timeframe" in non_exec_section, (
        "Failure span must appear in non-executable context section"
    )
    assert "do NOT create COMMAND" in non_exec_section
