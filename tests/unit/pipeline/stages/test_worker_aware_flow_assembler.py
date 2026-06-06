"""Unit tests for worker-aware Stage 4 flow assembly."""

from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
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


# ===========================================================================
# D3: Worker-aware exception flow materialization
# ===========================================================================


def _d3_spans() -> list[SpanIR]:
    return [
        SpanIR("s1", "Determine communication type."),
        SpanIR("s2", "Missing timeframe."),
        SpanIR("s3", "Produce final answer."),
    ]


def _d3_routes() -> FieldRouteIR:
    return FieldRouteIR(
        behavior=["s1", "s2", "s3"],
        annotations=[
            RouteAnnotation(
                span_id="s2", field="behavior",
                semantic_role="failure_mode",
                construct_target="EXCEPTION_FLOW",
                slot_target="condition",
                executable=False,
            ),
        ],
    )


def test_d3_main_worker_materializes_owned_failure_condition(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D3: main worker that owns failure span gets ExceptionFlow."""
    mock_client.call_json.return_value = {
        "main_flow_spans": ["s1", "s3"],
        "alternative_flows": [],
        "exception_flows": [],
    }
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[worker("worker_main", "main", ["s1", "s2", "s3"])],
    )

    result = FlowAssembler(pipeline_config, mock_client).execute(
        (_d3_spans(), _d3_routes(), plan)
    )

    main_flow = result.worker_flows["worker_main"]
    failure_exceptions = [
        e for e in main_flow.exception_flows
        if "timeframe" in e.condition_text.lower()
    ]
    assert len(failure_exceptions) >= 1, (
        "Worker-aware Stage 4 must materialize route-derived failure exception"
    )
    assert failure_exceptions[0].condition_text == "Missing timeframe."
    assert "s2" in failure_exceptions[0].spans


def test_d3_child_worker_materializes_owned_failure_condition(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D3: child worker that owns failure span gets ExceptionFlow."""
    mock_client.call_json.side_effect = [
        {"main_flow_spans": ["s1", "s3"], "alternative_flows": [],
         "exception_flows": []},
        {"main_flow_spans": ["s2"], "alternative_flows": [],
         "exception_flows": []},
    ]
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            worker("worker_main", "main", ["s1", "s3"]),
            worker("worker_child", "child", ["s2"]),
        ],
    )

    result = FlowAssembler(pipeline_config, mock_client).execute(
        (_d3_spans(), _d3_routes(), plan)
    )

    child_flow = result.worker_flows["worker_child"]
    failure_exceptions = [
        e for e in child_flow.exception_flows
        if "timeframe" in e.condition_text.lower()
    ]
    assert len(failure_exceptions) >= 1, (
        "Child worker must receive route-derived failure exception"
    )
    # Main worker must NOT duplicate
    main_flow = result.worker_flows["worker_main"]
    main_failures = [
        e for e in main_flow.exception_flows
        if "timeframe" in e.condition_text.lower()
    ]
    assert len(main_failures) == 0, (
        f"Main worker must not duplicate child-owned failure: {main_failures}"
    )


def test_d3_unowned_failure_falls_back_to_main_worker(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D3: failure span owned by no worker 鈫?main worker with warning."""
    mock_client.call_json.return_value = {
        "main_flow_spans": ["s1", "s3"],
        "alternative_flows": [],
        "exception_flows": [],
    }
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[worker("worker_main", "main", ["s1", "s3"])],
    )

    result = FlowAssembler(pipeline_config, mock_client).execute(
        (_d3_spans(), _d3_routes(), plan)
    )

    # s2 not owned 鈫?falls back to main worker
    main_flow = result.worker_flows["worker_main"]
    failure_exceptions = [
        e for e in main_flow.exception_flows
        if "timeframe" in e.condition_text.lower()
    ]
    assert len(failure_exceptions) >= 1, (
        "Unowned failure must fall back to main worker"
    )
    # Warning recorded
    warning_texts = " ".join(result.warnings).lower()
    assert "unowned" in warning_texts or "fallback" in warning_texts or "main worker" in warning_texts, (
        f"Expected ownership fallback warning, got: {result.warnings}"
    )


def test_d3_ambiguous_ownership_falls_back_to_main(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D3: span owned by multiple workers 鈫?main worker with ambiguous warning."""
    mock_client.call_json.side_effect = [
        {"main_flow_spans": ["s1", "s3"], "alternative_flows": [],
         "exception_flows": []},
        {"main_flow_spans": ["s2"], "alternative_flows": [],
         "exception_flows": []},
    ]
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            worker("worker_main", "main", ["s1", "s2", "s3"]),
            worker("worker_child", "child", ["s2"]),
        ],
    )

    result = FlowAssembler(pipeline_config, mock_client).execute(
        (_d3_spans(), _d3_routes(), plan)
    )

    # Condition goes to main worker only (not duplicated in child)
    main_flow = result.worker_flows["worker_main"]
    main_failures = [
        e for e in main_flow.exception_flows
        if "timeframe" in e.condition_text.lower()
    ]
    assert len(main_failures) == 1

    child_flow = result.worker_flows["worker_child"]
    child_failures = [
        e for e in child_flow.exception_flows
        if "timeframe" in e.condition_text.lower()
    ]
    assert len(child_failures) == 0, "Ambiguous span must not duplicate in child"

    # Warning mentions ambiguous/multiple
    warning_texts = " ".join(result.warnings).lower()
    assert "multiple" in warning_texts or "ambiguous" in warning_texts, (
        f"Expected ambiguous ownership warning, got: {result.warnings}"
    )


def test_worker_aware_handler_exception_flow_filtered(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """Worker-aware: LLM handler-sourced exception flow is filtered."""
    # Main worker owns condition span; child worker owns handler+process
    mock_client.call_json.side_effect = [
        {  # Main worker
            "main_flow_spans": ["s_cond"],
            "alternative_flows": [],
            "exception_flows": [],
        },
        {  # Child worker 鈥?LLM fabricates handler-backed exception
            "main_flow_spans": ["s_handler", "s_process"],
            "alternative_flows": [],
            "exception_flows": [
                {
                    "flow_id": "exc_bad",
                    "condition_text": "ask one clarifying question",
                    "spans": ["s_handler", "s_process"],
                    "flow_type": "exception",
                },
            ],
        },
    ]

    s_cond = SpanIR("s_cond", "Missing timeframe.")
    s_handler = SpanIR("s_handler", "ask one clarifying question.")
    s_process = SpanIR("s_process", "Determine communication type.")
    all_spans = [s_cond, s_handler, s_process]

    routes = FieldRouteIR(
        behavior=["s_cond", "s_handler", "s_process"],
        annotations=[
            RouteAnnotation(span_id="s_cond", field="behavior",
                            semantic_role="failure_mode",
                            construct_target="EXCEPTION_FLOW",
                            slot_target="condition", executable=False),
            RouteAnnotation(span_id="s_handler", field="behavior",
                            semantic_role="exception_handler_action",
                            construct_target="EXCEPTION_FLOW",
                            slot_target="handler", executable=True),
            RouteAnnotation(span_id="s_process", field="behavior",
                            semantic_role="process_step", executable=True),
        ],
    )

    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main", worker_name="Main",
                kind="main", purpose="Main worker",
                owned_span_ids=["s_cond"],
                boundary_kind="main_worker",
            ),
            WorkerSpecIR(
                worker_id="worker_child", worker_name="Child",
                kind="child", purpose="Child worker",
                owned_span_ids=["s_handler", "s_process"],
                boundary_kind="bounded_subtask",
            ),
        ],
    )

    result = FlowAssembler(pipeline_config, mock_client).execute(
        (all_spans, routes, plan)
    )

    # Child worker: LLM handler exception must be filtered
    child_flow = result.worker_flows["worker_child"]
    bad = [
        exc for exc in child_flow.exception_flows
        if "s_handler" in exc.spans
    ]
    assert len(bad) == 0, (
        f"Worker-aware: handler-sourced exception flow must be filtered, "
        f"got {len(bad)}"
    )
    # Main worker: route-derived condition must be materialized
    main_flow = result.worker_flows["worker_main"]
    cond_exc = [
        exc for exc in main_flow.exception_flows
        if "s_cond" in exc.spans
    ]
    assert len(cond_exc) >= 1, (
        "Worker-aware: route-derived condition must survive in main worker"
    )
