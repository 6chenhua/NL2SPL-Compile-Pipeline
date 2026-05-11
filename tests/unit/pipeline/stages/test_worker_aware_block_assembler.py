"""Unit tests for worker-aware Stage 5 block assembly."""

from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR
from nl2spl.pipeline.stages.stage5_block_assembler import BlockAssembler


def spans() -> list[SpanIR]:
    return [
        SpanIR("s1", "Prepare the request context."),
        SpanIR("s2", "If sources are needed, gather approved sources."),
        SpanIR("s3", "Produce the final answer."),
    ]


def routes() -> FieldRouteIR:
    return FieldRouteIR(behavior=["s1", "s2", "s3"])


def worker_flows() -> WorkerFlowPlanIR:
    return WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(main_flow_spans=["s1", "s2", "s3"])
        }
    )


def test_one_worker_flow_produces_one_worker_block_structure(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    mock_client.call_json.return_value = {
        "main_flow_blocks": [
            {
                "block_id": "b1",
                "block_type": "SEQUENTIAL",
                "condition_text": None,
                "spans": ["s1", "s3"],
            }
        ],
        "alternative_flow_blocks": {},
        "exception_flow_blocks": {},
    }

    result = BlockAssembler(pipeline_config, mock_client).execute(
        (spans(), routes(), worker_flows())
    )

    assert isinstance(result, WorkerBlockPlanIR)
    assert list(result.worker_blocks) == ["worker_main"]
    assert result.worker_blocks["worker_main"].main_flow_blocks[0].spans == ["s1", "s3"]


def test_flattenable_nested_sequence_is_split_into_top_level_blocks(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    mock_client.call_json.return_value = {
        "main_flow_blocks": [
            {
                "block_id": "b1",
                "block_type": "SEQUENTIAL",
                "condition_text": None,
                "spans": ["s1"],
                "child_blocks": [
                    {
                        "block_id": "b2",
                        "block_type": "IF",
                        "condition_text": "sources are needed",
                        "spans": ["s2"],
                    },
                    {
                        "block_id": "b3",
                        "block_type": "SEQUENTIAL",
                        "condition_text": None,
                        "spans": ["s3"],
                    },
                ],
            }
        ],
        "alternative_flow_blocks": {},
        "exception_flow_blocks": {},
    }

    result = BlockAssembler(pipeline_config, mock_client).execute(
        (spans(), routes(), worker_flows())
    )

    assert isinstance(result, WorkerBlockPlanIR)
    blocks = result.worker_blocks["worker_main"].main_flow_blocks
    assert [(block.block_id, block.block_type, block.spans) for block in blocks] == [
        ("b1", "SEQUENTIAL", ["s1"]),
        ("b2", "IF", ["s2"]),
        ("b3", "SEQUENTIAL", ["s3"]),
    ]
    assert result.control_complexity_regions[0].discovery_phase == "confirmed"
    assert result.control_complexity_regions[0].severity == "info"


def test_nested_if_inside_for_emits_confirmed_control_complexity_region(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    mock_client.call_json.return_value = {
        "main_flow_blocks": [
            {
                "block_id": "b1",
                "block_type": "FOR",
                "condition_text": "each topic",
                "spans": ["s1"],
                "body_blocks": [
                    {
                        "block_id": "b2",
                        "block_type": "IF",
                        "condition_text": "evidence is missing",
                        "spans": ["s2"],
                    }
                ],
            }
        ],
        "alternative_flow_blocks": {},
        "exception_flow_blocks": {},
    }

    result = BlockAssembler(pipeline_config, mock_client).execute(
        (spans(), routes(), worker_flows())
    )

    assert isinstance(result, WorkerBlockPlanIR)
    blocks = result.worker_blocks["worker_main"].main_flow_blocks
    assert len(blocks) == 1
    assert blocks[0].block_type == "FOR"
    assert blocks[0].spans == ["s1", "s2"]
    region = result.control_complexity_regions[0]
    assert region.discovery_phase == "confirmed"
    assert region.outer_control == "FOR"
    assert region.inner_control == "IF"
    assert region.severity in {"warning", "error"}


def test_stage5_worker_mode_does_not_include_delegation_candidate_context(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(
                main_flow_spans=["s1"],
            )
        }
    )
    mock_client.call_json.return_value = {
        "main_flow_blocks": [
            {
                "block_id": "b1",
                "block_type": "SEQUENTIAL",
                "condition_text": None,
                "spans": ["s1"],
            }
        ],
        "alternative_flow_blocks": {},
        "exception_flow_blocks": {},
        "delegation_candidates": [{"candidate_id": "dc_1"}],
    }

    result = BlockAssembler(pipeline_config, mock_client).execute(
        (spans(), routes(), flow_plan)
    )

    assert isinstance(result, WorkerBlockPlanIR)
    user_prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
    assert "delegation_candidates" not in user_prompt
    assert not hasattr(result, "delegation_candidates")


def test_worker_mode_discards_block_spans_outside_worker_local_flow(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(main_flow_spans=["s1", "s3"])
        }
    )
    mock_client.call_json.return_value = {
        "main_flow_blocks": [
            {
                "block_id": "b1",
                "block_type": "SEQUENTIAL",
                "condition_text": None,
                "spans": ["s1", "s2", "s3"],
            },
            {
                "block_id": "b2",
                "block_type": "IF",
                "condition_text": "sources are needed",
                "spans": ["s2"],
            },
        ],
        "alternative_flow_blocks": {},
        "exception_flow_blocks": {},
    }

    result = BlockAssembler(pipeline_config, mock_client).execute(
        (spans(), routes(), flow_plan)
    )

    assert isinstance(result, WorkerBlockPlanIR)
    blocks = result.worker_blocks["worker_main"].main_flow_blocks
    assert [(block.block_id, block.spans) for block in blocks] == [
        ("b1", ["s1", "s3"])
    ]
    assert all("s2" not in block.spans for block in blocks)
    assert any("outside its worker-local flow" in warning for warning in result.warnings)
    assert any("block b2 was dropped" in warning for warning in result.warnings)


def test_worker_mode_control_complexity_regions_do_not_suggest_child_extraction(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    mock_client.call_json.return_value = {
        "main_flow_blocks": [
            {
                "block_id": "b1",
                "block_type": "SEQUENTIAL",
                "condition_text": None,
                "spans": ["s1"],
            }
        ],
        "alternative_flow_blocks": {},
        "exception_flow_blocks": {},
        "control_complexity_regions": [
            {
                "region_id": "ccr_1",
                "source_span_ids": ["s1"],
                "outer_control": "FOR",
                "inner_control": "IF",
                "description": "Nested IF in loop.",
                "discovery_phase": "predicted",
                "severity": "warning",
                "can_flatten": False,
                "can_merge_condition": False,
                "can_lift_guard": True,
                "suggested_repairs": ["guard_variable", "extract_child_worker"],
            }
        ],
    }

    result = BlockAssembler(pipeline_config, mock_client).execute(
        (spans(), routes(), worker_flows())
    )

    assert isinstance(result, WorkerBlockPlanIR)
    region = result.control_complexity_regions[0]
    assert region.discovery_phase == "confirmed"
    assert "extract_child_worker" not in region.suggested_repairs
