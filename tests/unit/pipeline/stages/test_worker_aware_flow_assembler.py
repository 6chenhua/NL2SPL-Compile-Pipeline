"""Unit tests for worker-aware Stage 4 flow assembly."""

from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerPlanIR, WorkerSpecIR
from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler


def spans() -> list[SpanIR]:
    return [
        SpanIR("s1", "Prepare the request context."),
        SpanIR("s2", "Gather approved sources."),
        SpanIR("s3", "Produce the final answer."),
    ]


def routes() -> FieldRouteIR:
    return FieldRouteIR(behavior=["s1", "s2", "s3"])


def worker(
    worker_id: str,
    kind: str,
    owned_span_ids: list[str],
) -> WorkerSpecIR:
    return WorkerSpecIR(
        worker_id=worker_id,
        worker_name="MainWorker" if kind == "main" else "SourceWorker",
        kind=kind,  # type: ignore[arg-type]
        purpose="Test worker",
        owned_span_ids=owned_span_ids,
        boundary_kind="main_worker" if kind == "main" else "bounded_subtask",
    )


def test_one_worker_plan_produces_one_worker_flow(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    mock_client.call_json.return_value = {
        "main_flow_spans": ["s1", "s3"],
        "alternative_flows": [],
        "exception_flows": [],
        "delegation_candidates": [
            {
                "candidate_id": "dc_1",
                "spans": ["s2"],
                "reason": "legacy field should be ignored",
                "suggested_type": "child_worker",
            }
        ],
    }
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[worker("worker_main", "main", ["s1", "s3"])],
    )

    result = FlowAssembler(pipeline_config, mock_client).execute((spans(), routes(), plan))

    assert isinstance(result, WorkerFlowPlanIR)
    assert list(result.worker_flows) == ["worker_main"]
    assert result.worker_flows["worker_main"].main_flow_spans == ["s1", "s3"]
    assert result.worker_flows["worker_main"].delegation_candidates == []


def test_main_and_child_plan_produces_separate_worker_flows(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    mock_client.call_json.side_effect = [
        {
            "main_flow_spans": ["s1", "s3"],
            "alternative_flows": [],
            "exception_flows": [],
        },
        {
            "main_flow_spans": ["s2"],
            "alternative_flows": [],
            "exception_flows": [],
        },
    ]
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            worker("worker_main", "main", ["s1", "s3"]),
            worker("worker_source", "child", ["s2"]),
        ],
    )

    result = FlowAssembler(pipeline_config, mock_client).execute((spans(), routes(), plan))

    assert isinstance(result, WorkerFlowPlanIR)
    assert set(result.worker_flows) == {"worker_main", "worker_source"}
    assert result.worker_flows["worker_main"].main_flow_spans == ["s1", "s3"]
    assert result.worker_flows["worker_source"].main_flow_spans == ["s2"]
    assert mock_client.call_json.call_count == 2


def test_child_owned_spans_do_not_appear_in_main_worker_flow(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    mock_client.call_json.side_effect = [
        {
            "main_flow_spans": ["s1", "s2", "s3"],
            "alternative_flows": [],
            "exception_flows": [],
        },
        {
            "main_flow_spans": ["s2"],
            "alternative_flows": [],
            "exception_flows": [],
        },
    ]
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            worker("worker_main", "main", ["s1", "s3"]),
            worker("worker_source", "child", ["s2"]),
        ],
    )

    result = FlowAssembler(pipeline_config, mock_client).execute((spans(), routes(), plan))

    assert isinstance(result, WorkerFlowPlanIR)
    assert result.worker_flows["worker_main"].main_flow_spans == ["s1", "s3"]
    assert "s2" not in result.worker_flows["worker_main"].get_all_flow_spans()
