"""Unit tests for Stage 3.5 WorkerBoundaryPlanner."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner import (
    WorkerBoundaryPlanner,
)


_MISSING = object()


def field(name: str, source: str = "input") -> dict[str, Any]:
    return {
        "name": name,
        "data_type": "text",
        "required": True,
        "description": f"{name} field",
        "source": source,
    }


def main_worker(spans: list[str] | None = None) -> dict[str, Any]:
    return {
        "worker_id": "worker_main",
        "worker_name": "MainWorker",
        "kind": "main",
        "purpose": "Coordinate the complete request.",
        "owned_span_ids": spans or ["s1", "s2"],
        "input_contract": [field("request")],
        "output_contract": [field("final_response", "output")],
        "depends_on": [],
        "constraints": [],
        "boundary_kind": "main_worker",
        "decision_evidence": [],
        "reason": "Main worker owns the end-to-end process.",
    }


def base_plan(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "main_worker_id": "worker_main",
        "workers": [main_worker()],
        "handoffs": [],
        "candidates": [],
        "decisions": [],
        "rejected_candidates": [],
        "control_complexity_regions": [],
        "unassigned_span_ids": [],
        "warnings": [],
    }
    data.update(overrides)
    return data


def rejected_candidate(
    candidate_id: str,
    span_id: str,
    rejection_reason: str,
    task_text: str = "Rejected candidate",
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = {
        "candidate_id": candidate_id,
        "source_span_ids": [span_id],
        "task_text": task_text,
        "purpose": task_text,
        "candidate_kind": "not_a_worker",
        "possible_inputs": [],
        "possible_outputs": [],
        "signals": [],
        "risks": [rejection_reason],
    }
    decision = {
        "candidate_id": candidate_id,
        "decision": {
            "alternative_flow": "compile_as_alternative_flow",
            "exception_flow": "compile_as_exception_flow",
            "single_api_call": "compile_as_call_api",
            "policy_or_constraint": "compile_as_constraint",
        }.get(rejection_reason, "keep_in_main_worker"),
        "boundary_strength": "weak",
        "boundary_kind": "not_a_worker",
        "rejection_reason": rejection_reason,
        "reason": f"Rejected as {rejection_reason}.",
        "evidence": [],
    }
    return candidate, decision


@pytest.fixture
def planner(pipeline_config: MagicMock, mock_client: MagicMock) -> WorkerBoundaryPlanner:
    return WorkerBoundaryPlanner(pipeline_config, mock_client)


def test_simple_process_produces_only_main_worker(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
    sample_spans: list[SpanIR],
    sample_field_route: FieldRouteIR,
) -> None:
    mock_client.call_json.return_value = base_plan(
        workers=[main_worker(["s2", "s5"])],
    )

    plan = planner.execute((sample_spans, sample_field_route))

    assert isinstance(plan, WorkerPlanIR)
    assert plan.main_worker_id == "worker_main"
    assert [worker.kind for worker in plan.workers] == ["main"]
    assert plan.handoffs == []


def test_explicit_source_gathering_with_io_produces_child_worker_and_handoff(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR("s1", "Determine the communication type."),
        SpanIR("s2", "Delegate bounded source gathering when evidence is needed."),
        SpanIR("s3", "Produce the final draft with cited evidence."),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2", "s3"])
    source_candidate = {
        "candidate_id": "candidate_source_gathering",
        "source_span_ids": ["s2"],
        "task_text": "Delegate bounded source gathering when evidence is needed.",
        "purpose": "Gather approved evidence and provenance.",
        "candidate_kind": "bounded_subtask",
        "possible_inputs": [field("request_context")],
        "possible_outputs": [
            field("evidence_set", "output"),
            field("provenance_log", "output"),
        ],
        "signals": ["explicit_delegation", "bounded_io", "evidence_normalization"],
        "risks": [],
    }
    source_decision = {
        "candidate_id": "candidate_source_gathering",
        "decision": "extract_child_worker",
        "boundary_strength": "strong",
        "boundary_kind": "bounded_subtask",
        "rejection_reason": None,
        "reason": "Clear bounded IO and explicit delegation.",
        "evidence": ["explicit_delegation", "bounded_io"],
    }
    child_worker = {
        "worker_id": "worker_source_gathering",
        "worker_name": "SourceGatheringWorker",
        "kind": "child",
        "purpose": "Gather approved evidence and provenance.",
        "owned_span_ids": ["s2"],
        "input_contract": [field("request_context")],
        "output_contract": [
            field("evidence_set", "output"),
            field("provenance_log", "output"),
        ],
        "depends_on": [],
        "constraints": [],
        "boundary_kind": "bounded_subtask",
        "decision_evidence": ["explicit_delegation", "bounded_io"],
        "reason": "Accepted source-gathering worker.",
    }
    handoff = {
        "handoff_id": "handoff_source_gathering",
        "from_worker": "worker_main",
        "to_worker": "worker_source_gathering",
        "api_ref": None,
        "mode": "invoke",
        "condition_text": "when evidence is needed",
        "ordering": "conditional",
        "input_bindings": [
            {
                "parent_variable": "request_context",
                "child_input": "request_context",
                "required": True,
            }
        ],
        "output_bindings": [
            {
                "child_output": "evidence_set",
                "parent_variable": "evidence_set",
                "required": True,
                "merge_strategy": "set",
            },
            {
                "child_output": "provenance_log",
                "parent_variable": "provenance_log",
                "required": True,
                "merge_strategy": "set",
            },
        ],
        "invoke_location_hint": {
            "flow_kind": "main",
            "flow_id": None,
            "after_span_id": "s1",
            "before_span_id": "s3",
            "block_hint": "sequential",
        },
        "failure_policy": {
            "policy_kind": "block_finalization",
            "description": "Block finalization if evidence cannot be gathered.",
            "source_span_ids": ["s2"],
        },
    }
    mock_client.call_json.return_value = base_plan(
        workers=[main_worker(["s1", "s3"]), child_worker],
        handoffs=[handoff],
        candidates=[source_candidate],
        decisions=[source_decision],
    )

    plan = planner.execute((spans, routes))

    assert [worker.worker_id for worker in plan.workers] == [
        "worker_main",
        "worker_source_gathering",
    ]
    assert plan.handoffs[0].to_worker == "worker_source_gathering"
    assert plan.handoffs[0].output_bindings[0].child_output == "evidence_set"


@pytest.mark.parametrize(
    ("candidate_id", "span_id", "rejection_reason"),
    [
        ("candidate_subtask_no_output", "s2", "no_clear_output_contract"),
        ("candidate_revision", "s3", "alternative_flow"),
        ("candidate_missing_timeframe", "s3", "exception_flow"),
        ("candidate_send_api", "s4", "single_api_call"),
    ],
)
def test_rejected_boundary_candidates_preserve_rejection_category(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
    sample_spans: list[SpanIR],
    sample_field_route: FieldRouteIR,
    candidate_id: str,
    span_id: str,
    rejection_reason: str,
) -> None:
    candidate, decision = rejected_candidate(candidate_id, span_id, rejection_reason)
    mock_client.call_json.return_value = base_plan(
        workers=[main_worker(["s2", "s4", "s5"])],
        candidates=[candidate],
        decisions=[decision],
        rejected_candidates=[decision],
    )

    plan = planner.execute((sample_spans, sample_field_route))

    assert plan.rejected_candidates[0].candidate_id == candidate_id
    assert plan.rejected_candidates[0].rejection_reason == rejection_reason
    assert all(worker.worker_id != candidate_id for worker in plan.workers)


def test_planner_output_with_missing_main_worker_fails_validation(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
    sample_spans: list[SpanIR],
    sample_field_route: FieldRouteIR,
) -> None:
    mock_client.call_json.return_value = base_plan(
        main_worker_id="worker_main",
        workers=[],
    )

    with pytest.raises(StageError, match="WorkerPlanIR validation failed"):
        planner.execute((sample_spans, sample_field_route))


def test_prompt_uses_compact_text_not_full_raw_ir(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
    sample_spans: list[SpanIR],
    sample_field_route: FieldRouteIR,
) -> None:
    mock_client.call_json.return_value = base_plan(workers=[main_worker(["s2", "s5"])])

    planner.execute((sample_spans, sample_field_route))

    user_prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
    assert "s2: First determine what kind of communication is requested." in user_prompt
    assert "behavior: s2, s5" in user_prompt
    assert '"span_id"' not in user_prompt
    assert "ambiguity" not in user_prompt


@pytest.mark.parametrize(
    ("hint_value", "policy_value"),
    [
        (None, None),
        ({}, {}),
        (_MISSING, _MISSING),
    ],
)
def test_null_empty_or_missing_handoff_nested_objects_use_defaults(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
    hint_value: object,
    policy_value: object,
) -> None:
    spans = [
        SpanIR("s1", "Plan the main response."),
        SpanIR("s2", "Delegate bounded source gathering."),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    candidate = {
        "candidate_id": "candidate_source_gathering",
        "source_span_ids": ["s2"],
        "task_text": "Delegate bounded source gathering.",
        "purpose": "Gather sources.",
        "candidate_kind": "bounded_subtask",
        "possible_inputs": [field("request_context")],
        "possible_outputs": [field("evidence_set", "output")],
        "signals": ["explicit_delegation", "bounded_io"],
        "risks": [],
    }
    decision = {
        "candidate_id": "candidate_source_gathering",
        "decision": "extract_child_worker",
        "boundary_strength": "strong",
        "boundary_kind": "bounded_subtask",
        "rejection_reason": None,
        "reason": "Clear bounded source-gathering handoff.",
        "evidence": ["explicit_delegation", "bounded_io"],
    }
    child = {
        "worker_id": "worker_source_gathering",
        "worker_name": "SourceGatheringWorker",
        "kind": "child",
        "purpose": "Gather sources.",
        "owned_span_ids": ["s2"],
        "input_contract": [field("request_context")],
        "output_contract": [field("evidence_set", "output")],
        "depends_on": [],
        "constraints": [],
        "boundary_kind": "bounded_subtask",
        "decision_evidence": ["explicit_delegation", "bounded_io"],
        "reason": "Accepted bounded source gathering.",
    }
    handoff = {
        "handoff_id": "handoff_source_gathering",
        "from_worker": "worker_main",
        "to_worker": "worker_source_gathering",
        "api_ref": None,
        "mode": "invoke",
        "condition_text": None,
        "ordering": "conditional",
        "input_bindings": [
            {
                "parent_variable": "request_context",
                "child_input": "request_context",
                "required": True,
            }
        ],
        "output_bindings": [
            {
                "child_output": "evidence_set",
                "parent_variable": "evidence_set",
                "required": True,
                "merge_strategy": "set",
            }
        ],
    }
    if hint_value is not _MISSING:
        handoff["invoke_location_hint"] = hint_value
    if policy_value is not _MISSING:
        handoff["failure_policy"] = policy_value
    mock_client.call_json.return_value = base_plan(
        workers=[main_worker(["s1"]), child],
        handoffs=[handoff],
        candidates=[candidate],
        decisions=[decision],
    )

    plan = planner.execute((spans, routes))

    assert plan.handoffs[0].invoke_location_hint.flow_kind == "main"
    assert plan.handoffs[0].invoke_location_hint.block_hint == "unknown"
    assert plan.handoffs[0].failure_policy.policy_kind == "propagate_exception"


def test_invalid_nested_handoff_object_raises_stage_error(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR("s1", "Plan the main response."),
        SpanIR("s2", "Delegate bounded source gathering."),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    handoff = {
        "handoff_id": "handoff_source_gathering",
        "from_worker": "worker_main",
        "to_worker": "worker_source_gathering",
        "api_ref": None,
        "mode": "invoke",
        "condition_text": None,
        "ordering": "conditional",
        "input_bindings": [
            {
                "parent_variable": "request_context",
                "child_input": "request_context",
                "required": True,
            }
        ],
        "output_bindings": [
            {
                "child_output": "evidence_set",
                "parent_variable": "evidence_set",
                "required": True,
                "merge_strategy": "set",
            }
        ],
        "invoke_location_hint": "not an object",
    }
    mock_client.call_json.return_value = base_plan(
        workers=[
            main_worker(["s1"]),
            {
                "worker_id": "worker_source_gathering",
                "worker_name": "SourceGatheringWorker",
                "kind": "child",
                "purpose": "Gather sources.",
                "owned_span_ids": ["s2"],
                "input_contract": [field("request_context")],
                "output_contract": [field("evidence_set", "output")],
                "depends_on": [],
                "constraints": [],
                "boundary_kind": "bounded_subtask",
                "decision_evidence": ["explicit_delegation", "bounded_io"],
                "reason": "Accepted bounded source gathering.",
            },
        ],
        handoffs=[handoff],
        candidates=[
            {
                "candidate_id": "candidate_source_gathering",
                "source_span_ids": ["s2"],
                "task_text": "Delegate bounded source gathering.",
                "purpose": "Gather sources.",
                "candidate_kind": "bounded_subtask",
                "signals": ["explicit_delegation", "bounded_io"],
                "risks": [],
            }
        ],
        decisions=[
            {
                "candidate_id": "candidate_source_gathering",
                "decision": "extract_child_worker",
                "boundary_strength": "strong",
                "boundary_kind": "bounded_subtask",
                "rejection_reason": None,
                "reason": "Clear bounded source-gathering handoff.",
                "evidence": ["explicit_delegation", "bounded_io"],
            }
        ],
    )

    with pytest.raises(StageError, match="Invalid WorkerPlanIR output"):
        planner.execute((spans, routes))
