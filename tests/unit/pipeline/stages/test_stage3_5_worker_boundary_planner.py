"""Unit tests for Stage 3.5 WorkerBoundaryPlanner."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from nl2spl.canonical import (
    CanonicalCompileInput,
    CompileHint,
    CompileHints,
    HardFacts,
    RawSection,
    VariableFact,
)
from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    WorkerBoundaryDecisionIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner import (
    WorkerBoundaryPlanner,
)

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
        "source_gathering",
    ]
    assert plan.handoffs[0].to_worker == "source_gathering"
    assert plan.handoffs[0].output_bindings[0].child_output == "evidence_set"
    assert plan.handoffs[0].invoke_location_hint.after_span_id == "s1"
    assert plan.handoffs[0].invoke_location_hint.before_span_id == "s3"


def test_split_materializer_rejects_accepted_candidate_without_output_contract(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR("s1", "Normalize the request."),
        SpanIR("s2", "Delegate a vague follow-up subtask."),
        SpanIR("s3", "Continue main evaluation."),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2", "s3"])
    candidate = {
        "candidate_id": "candidate_vague_subtask",
        "source_span_ids": ["s2"],
        "task_text": "Delegate a vague follow-up subtask.",
        "purpose": "Do unclear child work.",
        "candidate_kind": "bounded_subtask",
        "possible_inputs": [field("request_context")],
        "possible_outputs": [],
        "signals": ["explicit_delegation"],
        "risks": [],
    }
    decision = {
        "candidate_id": "candidate_vague_subtask",
        "decision": "extract_child_worker",
        "boundary_strength": "moderate",
        "boundary_kind": "bounded_subtask",
        "rejection_reason": None,
        "reason": "Accepted by model, but output contract is missing.",
        "evidence": ["explicit_delegation"],
    }
    mock_client.call_json.return_value = {
        "candidates": [candidate],
        "decisions": [decision],
    }

    plan = planner.execute((spans, routes))

    assert [worker.kind for worker in plan.workers] == ["main"]
    assert plan.handoffs == []
    assert plan.decisions[0].decision == "keep_in_main_worker"
    assert plan.decisions[0].rejection_reason == "no_clear_output_contract"
    assert all(
        field.name != "output"
        for worker in plan.workers
        for field in worker.output_contract
    )


def test_split_materializer_recovers_contract_from_hard_fact_name_match(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR("s1", "Normalize the request."),
        SpanIR("s2", "Collect normalized quote artifacts."),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    canonical_input = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Inputs for each run: normalized request.",
        raw_sections=[
            RawSection(
                section_id="sec_inputs",
                canonical_title="Inputs for each run",
                original_title="Inputs for each run",
                text="normalized request",
                order=1,
            )
        ],
        hard_facts=HardFacts(
            inputs=[
                VariableFact(
                    name="normalized_request",
                    description="Normalized request",
                    data_type="text",
                    required=True,
                    source_section_id="sec_inputs",
                )
            ],
            outputs=[
                VariableFact(
                    name="normalized_quote_artifacts",
                    description="Normalized quote artifacts",
                    data_type="text",
                    required=True,
                    source_section_id="sec_inputs",
                )
            ],
        ),
    )
    candidate = {
        "candidate_id": "candidate_quote_artifacts",
        "source_span_ids": ["s2"],
        "task_text": "Collect normalized quote artifacts from normalized request.",
        "purpose": "Return normalized quote artifacts.",
        "candidate_kind": "bounded_subtask",
        "possible_inputs": [],
        "possible_outputs": [],
        "signals": ["bounded_io"],
        "risks": [],
    }
    decision = {
        "candidate_id": "candidate_quote_artifacts",
        "decision": "extract_child_worker",
        "boundary_strength": "strong",
        "boundary_kind": "bounded_subtask",
        "rejection_reason": None,
        "reason": "Clear hard-fact contract names in candidate text.",
        "evidence": ["bounded_io"],
    }
    mock_client.call_json.return_value = {
        "candidates": [candidate],
        "decisions": [decision],
    }

    plan = planner.execute((spans, routes, canonical_input))

    child = next(worker for worker in plan.workers if worker.kind == "child")
    assert [field.name for field in child.input_contract] == ["normalized_request"]
    assert [field.name for field in child.output_contract] == [
        "normalized_quote_artifacts"
    ]


def test_split_materializer_places_handoff_around_first_child_span_cluster(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR("s16", "Determine procurement category."),
        SpanIR("s17", "Identify eligible vendor pool."),
        SpanIR("s18", "Solicit quotes or equivalent offers according to policy."),
        SpanIR("s19", "Evaluate budget and compliance."),
        SpanIR("s37", "Delegation policy permits bounded sourcing."),
    ]
    routes = FieldRouteIR(behavior=["s16", "s17", "s18", "s19", "s37"])
    candidate = {
        "candidate_id": "candidate_sourcing_quote_collection",
        "source_span_ids": ["s17", "s18", "s37"],
        "task_text": "Bounded sourcing and quote collection.",
        "purpose": "Collect sourcing artifacts for evaluation.",
        "candidate_kind": "bounded_subtask",
        "possible_inputs": [field("normalized_request")],
        "possible_outputs": [field("normalized_quote_artifacts", "output")],
        "signals": ["explicit_delegation", "bounded_io"],
        "risks": [],
    }
    decision = {
        "candidate_id": "candidate_sourcing_quote_collection",
        "decision": "extract_child_worker",
        "boundary_strength": "strong",
        "boundary_kind": "bounded_subtask",
        "rejection_reason": None,
        "reason": "Clear bounded sourcing handoff.",
        "evidence": ["explicit_delegation", "bounded_io"],
    }
    mock_client.call_json.return_value = {
        "candidates": [candidate],
        "decisions": [decision],
    }

    plan = planner.execute((spans, routes))

    hint = plan.handoffs[0].invoke_location_hint
    assert hint.after_span_id == "s16"
    assert hint.before_span_id == "s19"
    assert "s17" not in {hint.after_span_id, hint.before_span_id}
    assert "s18" not in {hint.after_span_id, hint.before_span_id}


def test_split_materializer_does_not_anchor_on_other_child_or_exception_spans(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR("s16", "Normalize request."),
        SpanIR("s17", "Identify eligible vendor pool."),
        SpanIR("s18", "Solicit quotes."),
        SpanIR("s19", "Evaluate sourcing responses."),
        SpanIR("s20", "If over budget, recover."),
        SpanIR("s21", "If non-compliance occurs, remediate."),
        SpanIR("s22", "Route approval."),
        SpanIR("s23", "Issue PO."),
    ]
    routes = FieldRouteIR(
        behavior=["s16", "s17", "s18", "s19", "s20", "s21", "s22", "s23"]
    )
    candidates = [
        {
            "candidate_id": "candidate_normalize",
            "source_span_ids": ["s16"],
            "task_text": "Normalize request.",
            "purpose": "Normalize request.",
            "candidate_kind": "bounded_subtask",
            "possible_inputs": [field("purchase_request")],
            "possible_outputs": [field("normalized_request", "output")],
            "signals": ["bounded_io"],
            "risks": [],
        },
        {
            "candidate_id": "candidate_vendor_pool",
            "source_span_ids": ["s17"],
            "task_text": "Identify eligible vendor pool.",
            "purpose": "Identify eligible vendor pool.",
            "candidate_kind": "bounded_subtask",
            "possible_inputs": [field("normalized_request")],
            "possible_outputs": [field("eligible_vendor_pool", "output")],
            "signals": ["bounded_io"],
            "risks": [],
        },
        {
            "candidate_id": "candidate_evaluate",
            "source_span_ids": ["s19"],
            "task_text": "Evaluate sourcing responses.",
            "purpose": "Evaluate sourcing responses.",
            "candidate_kind": "bounded_subtask",
            "possible_inputs": [field("vendor_quotes")],
            "possible_outputs": [field("sourcing_evaluation_record", "output")],
            "signals": ["bounded_io"],
            "risks": [],
        },
        {
            "candidate_id": "candidate_over_budget",
            "source_span_ids": ["s20"],
            "task_text": "If over budget, recover.",
            "purpose": "Over budget recovery.",
            "candidate_kind": "not_a_worker",
            "possible_inputs": [],
            "possible_outputs": [],
            "signals": [],
            "risks": ["alternative_flow"],
        },
        {
            "candidate_id": "candidate_non_compliance",
            "source_span_ids": ["s21"],
            "task_text": "If non-compliance occurs, remediate.",
            "purpose": "Non-compliance handling.",
            "candidate_kind": "not_a_worker",
            "possible_inputs": [],
            "possible_outputs": [],
            "signals": [],
            "risks": ["exception_flow"],
        },
        {
            "candidate_id": "candidate_approval",
            "source_span_ids": ["s22"],
            "task_text": "Route approval.",
            "purpose": "Route approval.",
            "candidate_kind": "bounded_subtask",
            "possible_inputs": [field("sourcing_evaluation_record")],
            "possible_outputs": [field("approval_record", "output")],
            "signals": ["bounded_io"],
            "risks": [],
        },
    ]
    decisions = [
        {
            "candidate_id": "candidate_normalize",
            "decision": "extract_child_worker",
            "boundary_strength": "strong",
            "boundary_kind": "bounded_subtask",
            "rejection_reason": None,
            "reason": "Clear child.",
            "evidence": ["bounded_io"],
        },
        {
            "candidate_id": "candidate_vendor_pool",
            "decision": "extract_child_worker",
            "boundary_strength": "strong",
            "boundary_kind": "bounded_subtask",
            "rejection_reason": None,
            "reason": "Clear child.",
            "evidence": ["bounded_io"],
        },
        {
            "candidate_id": "candidate_evaluate",
            "decision": "extract_child_worker",
            "boundary_strength": "strong",
            "boundary_kind": "bounded_subtask",
            "rejection_reason": None,
            "reason": "Clear child.",
            "evidence": ["bounded_io"],
        },
        {
            "candidate_id": "candidate_over_budget",
            "decision": "compile_as_alternative_flow",
            "boundary_strength": "weak",
            "boundary_kind": "not_a_worker",
            "rejection_reason": "alternative_flow",
            "reason": "Main flow branch.",
            "evidence": [],
        },
        {
            "candidate_id": "candidate_non_compliance",
            "decision": "compile_as_exception_flow",
            "boundary_strength": "weak",
            "boundary_kind": "not_a_worker",
            "rejection_reason": "exception_flow",
            "reason": "Exception path.",
            "evidence": [],
        },
        {
            "candidate_id": "candidate_approval",
            "decision": "extract_child_worker",
            "boundary_strength": "strong",
            "boundary_kind": "bounded_subtask",
            "rejection_reason": None,
            "reason": "Clear child.",
            "evidence": ["bounded_io"],
        },
    ]
    # Split path: 3.5a returns all candidates, 3.5b returns decisions
    # for eligible candidates only (those without blocking risks).
    eligible_candidates = [c for c in candidates if not c["risks"]]
    eligible_decision_ids = {c["candidate_id"] for c in eligible_candidates}
    eligible_decisions = [d for d in decisions if d["candidate_id"] in eligible_decision_ids]
    mock_client.call_json.side_effect = [
        {"candidates": candidates},
        {"decisions": eligible_decisions},
    ]

    plan = planner.execute((spans, routes))
    hints = {
        handoff.handoff_id: handoff.invoke_location_hint
        for handoff in plan.handoffs
    }

    assert hints["handoff_normalize"].after_span_id is None
    assert hints["handoff_normalize"].before_span_id == "s18"
    assert hints["handoff_vendor_pool"].after_span_id is None
    assert hints["handoff_vendor_pool"].before_span_id == "s18"
    assert hints["handoff_evaluate"].after_span_id == "s18"
    assert hints["handoff_evaluate"].before_span_id == "s23"
    assert hints["handoff_approval"].after_span_id == "s18"
    assert hints["handoff_approval"].before_span_id == "s23"


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


def test_prompt_uses_compact_text_not_full_raw_ir(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
    sample_spans: list[SpanIR],
    sample_field_route: FieldRouteIR,
) -> None:
    mock_client.call_json.return_value = base_plan(workers=[main_worker(["s2", "s5"])])

    planner.execute((sample_spans, sample_field_route))

    user_prompt = mock_client.call_json.call_args_list[0].kwargs["user_prompt"]
    assert "s2: First determine what kind of communication is requested." in user_prompt
    assert "Behavior spans available for candidate source_span_ids:" in user_prompt
    assert '"span_id"' not in user_prompt
    assert "ambiguity" not in user_prompt


def test_adapter_metadata_prompt_omits_full_raw_section_text(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
) -> None:
    spans = [
        SpanIR(
            "s1",
            "Delegate bounded source gathering when evidence is needed.",
            source_section_id="sec_process",
        )
    ]
    routes = FieldRouteIR(behavior=["s1"])
    canonical_input = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Task family:\nInternal communications\n",
        raw_sections=[
            RawSection(
                section_id="sec_process",
                canonical_title="Reusable process",
                original_title="Reusable process",
                text=(
                    "This full reusable process body is intentionally long and "
                    "should not be repeated in the worker boundary planner prompt."
                ),
                order=1,
            )
        ],
        hard_facts=HardFacts(
            inputs=[
                VariableFact(
                    name="user_request",
                    description="The runtime request.",
                    data_type="text",
                    required=True,
                    source_section_id="sec_process",
                )
            ],
            outputs=[
                VariableFact(
                    name="draft_artifact",
                    description="The produced draft.",
                    data_type="text",
                    required=True,
                    source_section_id="sec_process",
                )
            ],
        ),
        compile_hints=CompileHints(
            delegation_hints=[
                CompileHint(
                    source_section_id="sec_process",
                    text=(
                        "Delegated source gathering can be used when bounded "
                        "evidence requirements exist."
                    ),
                    target="worker.candidate",
                    suggested_kind="bounded_subtask",
                    suggested_worker_name="SourceGatheringWorker",
                )
            ]
        ),
    )
    mock_client.call_json.return_value = base_plan(workers=[main_worker(["s1"])])

    planner.execute((spans, routes, canonical_input))

    user_prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
    assert "section index:" in user_prompt
    assert "- sec_process: Reusable process" in user_prompt
    assert "This full reusable process body" not in user_prompt
    assert "user_request: text" in user_prompt
    assert "draft_artifact: text" in user_prompt
    assert "worker=SourceGatheringWorker" in user_prompt


def test_sequential_handoff_ordering_is_normalized_to_after(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
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
        "ordering": "sequential",
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
        "invoke_location_hint": {"block_hint": "sequential"},
    }
    mock_client.call_json.return_value = base_plan(
        workers=[main_worker(["s1"]), child],
        handoffs=[handoff],
        candidates=[candidate],
        decisions=[decision],
    )

    plan = planner.execute((spans, routes))

    assert plan.handoffs[0].ordering == "after"
    assert plan.handoffs[0].invoke_location_hint.block_hint == "sequential"


def test_parser_moves_risk_values_out_of_candidate_signals(
    planner: WorkerBoundaryPlanner,
) -> None:
    candidate = planner._parse_candidate(
        {
            "candidate_id": "candidate_policy",
            "source_span_ids": ["s1"],
            "task_text": "Maintain provenance as a policy.",
            "purpose": "Keep provenance.",
            "candidate_kind": "bounded_subtask",
            "signals": ["bounded_io", "policy_or_constraint"],
            "risks": [],
        }
    )

    assert candidate.signals == ["bounded_io"]
    assert candidate.risks == ["policy_or_constraint"]


def test_parser_drops_boundary_kind_values_from_decision_evidence(
    planner: WorkerBoundaryPlanner,
) -> None:
    decision = planner._parse_decision(
        {
            "candidate_id": "candidate_finalize",
            "decision": "extract_child_worker",
            "boundary_strength": "moderate",
            "boundary_kind": "bounded_subtask",
            "rejection_reason": None,
            "reason": "Has bounded IO.",
            "evidence": ["bounded_io", "failure_recovery_protocol"],
        }
    )

    assert decision.evidence == ["bounded_io"]


def test_parser_drops_invalid_worker_decision_evidence(
    planner: WorkerBoundaryPlanner,
) -> None:
    worker = planner._parse_worker(
        {
            "worker_id": "worker_finalize",
            "worker_name": "FinalizeWorker",
            "kind": "child",
            "purpose": "Finalize the draft.",
            "owned_span_ids": ["s1"],
            "input_contract": [field("draft")],
            "output_contract": [field("completion_status", "output")],
            "depends_on": [],
            "constraints": [],
            "boundary_kind": "bounded_subtask",
            "decision_evidence": ["bounded_io", "failure_recovery_protocol"],
            "reason": "Has bounded IO.",
        }
    )

    assert worker.decision_evidence == ["bounded_io"]


# ---------------------------------------------------------------------------
# Prompt injection: Stage 3.5 executor call-site
# ---------------------------------------------------------------------------

def _make_valid_plan() -> WorkerPlanIR:
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[WorkerSpecIR("worker_main", "Main", "main", "Main", ["s1"],
                              [], [], [], [], "main_worker", [], "")],
        candidates=[], decisions=[], handoffs=[],
    )


class TestStage35PromptInjection:
    def _make_config(self, flag_enabled: bool) -> PipelineConfig:
        return PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
        )

    def test_flag_on_stage3_5a_no_construct_injected(self):
        """Stage 3.5a uses prompt file only — IRS not injected."""
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.executor import (
            ExecutorMixin,
        )

        class TestExecutor(ExecutorMixin):
            pass

        executor = TestExecutor()
        executor.config = self._make_config(flag_enabled=True)
        executor.client = MagicMock()
        executor.logger = MagicMock()
        executor.name = "test"
        executor._build_candidate_prompt = lambda s, r, c, rcp=None: "test prompt"

        spans = [SpanIR("s1", "Determine type")]
        routes = FieldRouteIR(behavior=["s1"])

        captured_prompt: list[str] = []

        def capture(**kw):
            captured_prompt.append(kw["system_prompt"])
            return {"candidates": []}

        executor.client.call_json = capture
        executor._run_candidate_extraction(spans, routes, None)

        assert len(captured_prompt) == 1
        # Stage 3.5a/b use prompt file only — no IRS checklist injected
        assert "CONSTRUCT:" not in captured_prompt[0]

    def test_flag_on_stage3_5b_no_construct_injected(self):
        """Stage 3.5b uses prompt file only — IRS not injected."""
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.decision_validator import (
            DecisionValidatorMixin,
        )
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.executor import (
            ExecutorMixin,
        )

        class TestExecutor(DecisionValidatorMixin, ExecutorMixin):
            pass

        executor = TestExecutor()
        executor.config = self._make_config(flag_enabled=True)
        executor.client = MagicMock()
        executor.logger = MagicMock()
        executor.name = "test"
        executor._build_decision_prompt = lambda s, r, c, cands, rcp=None: "test prompt"

        spans = [SpanIR("s1", "Determine type")]
        routes = FieldRouteIR(behavior=["s1"])

        captured_prompt: list[str] = []

        def capture(**kw):
            captured_prompt.append(kw["system_prompt"])
            return {"decisions": []}

        executor.client.call_json = capture
        executor._run_boundary_decisions(spans, routes, None, [])

        assert len(captured_prompt) == 1
        assert "CONSTRUCT:" not in captured_prompt[0]

    def test_flag_off_stage3_5b_no_irs_in_prompt(self):
        """Flag off: no IRS checklist in split-path prompts."""
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.decision_validator import (
            DecisionValidatorMixin,
        )
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.executor import (
            ExecutorMixin,
        )

        class TestExecutor(DecisionValidatorMixin, ExecutorMixin):
            pass

        executor = TestExecutor()
        executor.config = self._make_config(flag_enabled=False)
        executor.client = MagicMock()
        executor.logger = MagicMock()
        executor.name = "test"
        executor._build_decision_prompt = lambda s, r, c, cands, rcp=None: "test prompt"

        spans = [SpanIR("s1", "Determine type")]
        routes = FieldRouteIR(behavior=["s1"])

        captured_prompt: list[str] = []

        def capture(**kw):
            captured_prompt.append(kw["system_prompt"])
            return {"decisions": []}

        executor.client.call_json = capture
        executor._run_boundary_decisions(spans, routes, None, [])

        assert len(captured_prompt) == 1
        assert "CONSTRUCT:" not in captured_prompt[0]

    def test_guard_mixed_unbacked_input_rejected(self) -> None:
        """One backed + one invented input with hard_inputs -> rejected."""
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
            WorkerPlanMaterializer,
        )
        mat = WorkerPlanMaterializer()
        candidate = CandidateTaskUnitIR(
            candidate_id="c_mixed",
            source_span_ids=["s1"],
            task_text="Match template to request.",
            purpose="Apply a formatting template.",
            candidate_kind="bounded_subtask",
            possible_inputs=[
                ContractFieldIR("user_request", "text", True, "User request", "input"),
                ContractFieldIR("template_id", "text", True, "Template ID", "input"),  # invented
            ],
            possible_outputs=[ContractFieldIR("draft", "text", True, "Draft", "output")],
            signals=[],
            risks=[],
        )
        decision = WorkerBoundaryDecisionIR(
            candidate_id="c_mixed",
            decision="extract_child_worker",
            boundary_strength="strong",
            boundary_kind="bounded_subtask",
            rejection_reason=None,
            reason="Should be rejected.",
            evidence=["bounded_io"],
        )
        hard_inputs = [ContractFieldIR("user_request", "text", True, "User request", "input")]
        hard_outputs = [ContractFieldIR("draft", "text", True, "Draft", "output")]
        worker = mat._candidate_to_worker(candidate, decision, hard_inputs, hard_outputs)
        assert worker is not None
        backed = mat._contract_fields_backed(worker, candidate, hard_inputs, hard_outputs)
        assert backed is False  # template_id is invented

    def test_guard_all_backed_passes(self) -> None:
        """All inputs match hard_inputs, all outputs match hard_outputs -> pass."""
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
            WorkerPlanMaterializer,
        )
        mat = WorkerPlanMaterializer()
        candidate = CandidateTaskUnitIR(
            candidate_id="c_good",
            source_span_ids=["s2"],
            task_text="Retrieve sources.",
            purpose="Gather source evidence.",
            candidate_kind="bounded_subtask",
            possible_inputs=[ContractFieldIR("connectors", "text", True, "Connectors", "input")],
            possible_outputs=[ContractFieldIR("evidence_set", "text", True, "Evidence", "output")],
            signals=["explicit_delegation"],
            risks=[],
        )
        decision = WorkerBoundaryDecisionIR(
            candidate_id="c_good",
            decision="extract_child_worker",
            boundary_strength="strong",
            boundary_kind="bounded_subtask",
            rejection_reason=None,
            reason="Source-backed.",
            evidence=["explicit_delegation"],
        )
        hard_inputs = [ContractFieldIR("connectors", "text", True, "Available connectors", "input")]
        hard_outputs = [ContractFieldIR("evidence_set", "text", True, "Evidence", "output")]
        worker = mat._candidate_to_worker(candidate, decision, hard_inputs, hard_outputs)
        assert worker is not None
        backed = mat._contract_fields_backed(worker, candidate, hard_inputs, hard_outputs)
        assert backed is True

    def test_guard_passes_without_hard_facts(self) -> None:
        """No hard facts -> pass."""
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
            WorkerPlanMaterializer,
        )
        mat = WorkerPlanMaterializer()
        candidate = CandidateTaskUnitIR(
            candidate_id="c_any",
            source_span_ids=["s3"],
            task_text="Normalize request.",
            purpose="Normalize procurement request.",
            candidate_kind="bounded_subtask",
            possible_inputs=[ContractFieldIR("purchase_request", "text", True, "Request", "input")],
            possible_outputs=[ContractFieldIR("normalized_request", "text", True, "Result", "output")],
            signals=["bounded_io"],
            risks=[],
        )
        decision = WorkerBoundaryDecisionIR(
            candidate_id="c_any",
            decision="extract_child_worker",
            boundary_strength="moderate",
            boundary_kind="bounded_subtask",
            rejection_reason=None,
            reason="Pass-through.",
            evidence=["bounded_io"],
        )
        worker = mat._candidate_to_worker(candidate, decision, [], [])
        assert worker is not None
        backed = mat._contract_fields_backed(worker, candidate, [], [])
        assert backed is True

    def test_guard_mixed_unbacked_materialize_rejected(self) -> None:
        """materialize() rejects candidate with mixed backed+unbacked fields."""
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
            WorkerPlanMaterializer,
        )
        mat = WorkerPlanMaterializer()
        candidate = CandidateTaskUnitIR(
            candidate_id="c_mixed",
            source_span_ids=["s1"],
            task_text="Apply template.",
            purpose="Template matching.",
            candidate_kind="bounded_subtask",
            possible_inputs=[
                ContractFieldIR("user_request", "text", True, "User request", "input"),
                ContractFieldIR("template_id", "text", True, "Template ID", "input"),
            ],
            possible_outputs=[ContractFieldIR("draft", "text", True, "Draft", "output")],
            signals=[],
            risks=[],
        )
        decision = WorkerBoundaryDecisionIR(
            candidate_id="c_mixed",
            decision="extract_child_worker",
            boundary_strength="strong",
            boundary_kind="bounded_subtask",
            rejection_reason=None,
            reason="Should be rejected by guard.",
            evidence=["bounded_io"],
        )
        hard_inputs = [ContractFieldIR("user_request", "text", True, "User request", "input")]
        hard_outputs = [ContractFieldIR("draft", "text", True, "Draft", "output")]
        plan, warnings = mat.materialize(
            candidates=[candidate],
            decisions=[decision],
            hard_fact_inputs=hard_inputs,
            hard_fact_outputs=hard_outputs,
            behavior_span_ids={"s1"},
        )
        # Only main worker, no child workers
        assert len(plan.workers) == 1
        assert plan.handoffs == []
        assert any("not source-backed" in w for w in warnings)

    def test_guard_all_backed_materialize_passes(self) -> None:
        """materialize() passes candidate with all-backed fields."""
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
            WorkerPlanMaterializer,
        )
        mat = WorkerPlanMaterializer()
        candidate = CandidateTaskUnitIR(
            candidate_id="c_good",
            source_span_ids=["s2"],
            task_text="Retrieve sources.",
            purpose="Gather source evidence.",
            candidate_kind="bounded_subtask",
            possible_inputs=[ContractFieldIR("connectors", "text", True, "Connectors", "input")],
            possible_outputs=[ContractFieldIR("evidence_set", "text", True, "Evidence", "output")],
            signals=["explicit_delegation"],
            risks=[],
        )
        decision = WorkerBoundaryDecisionIR(
            candidate_id="c_good",
            decision="extract_child_worker",
            boundary_strength="strong",
            boundary_kind="bounded_subtask",
            rejection_reason=None,
            reason="Source-backed.",
            evidence=["explicit_delegation"],
        )
        hard_inputs = [ContractFieldIR("connectors", "text", True, "Available connectors", "input")]
        hard_outputs = [ContractFieldIR("evidence_set", "text", True, "Evidence", "output")]
        plan, warnings = mat.materialize(
            candidates=[candidate],
            decisions=[decision],
            hard_fact_inputs=hard_inputs,
            hard_fact_outputs=hard_outputs,
            behavior_span_ids={"s2"},
        )
        # Main + child worker
        assert len(plan.workers) == 2
        assert len(plan.handoffs) == 1


# ===========================================================================
# D0: Worker planner baseline — annotations don't crash
# ===========================================================================


def test_d0_worker_planner_tolerates_annotation_bearing_routes(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
    sample_spans: list[SpanIR],
) -> None:
    """D0: WorkerBoundaryPlanner.execute() handles annotation-bearing FieldRouteIR."""
    mock_client.call_json.return_value = base_plan(
        workers=[main_worker(["s2", "s5"])],
    )

    routes = FieldRouteIR(
        behavior=["s2", "s5"],
        annotations=[
            RouteAnnotation(
                span_id="s2", field="behavior",
                semantic_role="failure_mode",
                construct_target="EXCEPTION_FLOW",
                slot_target="condition",
                executable=False,
            ),
            RouteAnnotation(
                span_id="s5", field="behavior",
                semantic_role="process_step",
                executable=True,
            ),
        ],
    )

    plan = planner.execute((sample_spans, routes))

    assert isinstance(plan, WorkerPlanIR)
    assert plan.main_worker_id == "worker_main"
    assert len(plan.workers) == 1


# ===========================================================================
# D1: Annotation-aware candidate extraction and materializer guards
# ===========================================================================


def _make_candidate(
    cid: str, span_ids: list[str], purpose: str = "Test candidate",
) -> CandidateTaskUnitIR:
    return CandidateTaskUnitIR(
        candidate_id=cid,
        source_span_ids=span_ids,
        task_text=purpose,
        purpose=purpose,
        candidate_kind="bounded_subtask",
        possible_inputs=[
            ContractFieldIR(name="input_var", data_type="text", required=True,
                            description="input variable", source="input"),
        ],
        possible_outputs=[ContractFieldIR(
            name="result", data_type="text", required=True, description="result",
            source="output",
        )],
        signals=["test"],
        risks=[],
    )


def _make_hard_fact_input() -> ContractFieldIR:
    return ContractFieldIR(
        name="input_var", data_type="text", required=True,
        description="input variable", source="input",
    )


def _make_decision(cid: str) -> WorkerBoundaryDecisionIR:
    return WorkerBoundaryDecisionIR(
        candidate_id=cid,
        decision="extract_child_worker",
        boundary_strength="strong",
        boundary_kind="bounded_subtask",
        rejection_reason=None,
        reason="Test decision.",
        evidence=["test"],
    )


class TestD1MaterializerGuard:
    """D1: materializer rejects pure non-executable child workers."""

    @staticmethod
    def _materialize(**kwargs: Any) -> tuple[WorkerPlanIR, list[str]]:
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
            WorkerPlanMaterializer,
        )
        return WorkerPlanMaterializer().materialize(**kwargs)

    def test_pure_failure_mode_child_worker_rejected(self) -> None:
        anns = [
            RouteAnnotation(span_id="s1", field="behavior",
                            semantic_role="failure_mode", executable=False),
        ]
        plan, warnings = self._materialize(
            candidates=[_make_candidate("c1", ["s1"])],
            decisions=[_make_decision("c1")],
            hard_fact_inputs=[_make_hard_fact_input()],
            behavior_span_ids={"s1"},
            behavior_span_order=["s1"],
            annotations=anns,
        )
        # No child worker for pure failure_mode
        assert len(plan.workers) == 1  # main only
        assert any("non-executable" in w.lower() for w in warnings), warnings
        # Decision must be downgraded, not extract_child_worker
        decision_for_c1 = [d for d in plan.decisions if d.candidate_id == "c1"]
        assert len(decision_for_c1) == 1
        assert decision_for_c1[0].decision == "keep_in_main_worker"
        assert decision_for_c1[0].rejection_reason == "insufficient_semantic_boundary"

    def test_pure_delegation_child_worker_rejected(self) -> None:
        anns = [
            RouteAnnotation(span_id="s2", field="behavior",
                            semantic_role="delegation_intent",
                            route_family="delegation_boundary",
                            executable=False),
        ]
        plan, warnings = self._materialize(
            candidates=[_make_candidate("c1", ["s2"])],
            decisions=[_make_decision("c1")],
            behavior_span_ids={"s2"},
            behavior_span_order=["s2"],
            annotations=anns,
        )
        assert len(plan.workers) == 1
        # Decision downgraded
        decision_for_c1 = [d for d in plan.decisions if d.candidate_id == "c1"]
        assert decision_for_c1[0].decision == "keep_in_main_worker"
        # No duplicate rejected entries
        rejected_c1 = [r for r in plan.rejected_candidates if r.candidate_id == "c1"]
        assert len(rejected_c1) == 1, f"Expected 1 rejected for c1, got {len(rejected_c1)}"

    def test_mixed_candidate_with_executable_span_passes(self) -> None:
        anns = [
            RouteAnnotation(span_id="s1", field="behavior",
                            semantic_role="failure_mode", executable=False),
            RouteAnnotation(span_id="s2", field="behavior",
                            semantic_role="process_step", executable=True),
        ]
        plan, warnings = self._materialize(
            candidates=[_make_candidate("c1", ["s1", "s2"])],
            decisions=[_make_decision("c1")],
            behavior_span_ids={"s1", "s2"},
            behavior_span_order=["s1", "s2"],
            annotations=anns,
        )
        # Mixed candidate passes because it has at least one executable span
        assert len(plan.workers) >= 2  # main + child

    def test_fallback_without_annotations_preserves_old_behavior(self) -> None:
        plan, warnings = self._materialize(
            candidates=[_make_candidate("c1", ["s1"])],
            decisions=[_make_decision("c1")],
            behavior_span_ids={"s1"},
            behavior_span_order=["s1"],
            annotations=None,  # no annotations → old behavior
        )
        assert len(plan.workers) == 2  # main + child (no guard applied)
        assert not any("non-executable" in w.lower() for w in warnings)


def test_d1_pure_failure_candidate_rejected_in_split_path(
    planner: WorkerBoundaryPlanner,
    mock_client: MagicMock,
) -> None:
    """D1: full split path rejects pure failure candidate and plan validates."""
    spans = [
        SpanIR("s1", "Determine communication type."),
        SpanIR("s2", "Missing timeframe — handle gracefully."),
    ]
    routes = FieldRouteIR(
        behavior=["s1", "s2"],
        annotations=[
            RouteAnnotation(span_id="s1", field="behavior",
                            semantic_role="process_step", executable=True),
            RouteAnnotation(span_id="s2", field="behavior",
                            semantic_role="failure_mode",
                            construct_target="EXCEPTION_FLOW",
                            slot_target="condition",
                            executable=False),
        ],
    )
    # LLM incorrectly accepts failure span as child worker candidate
    failure_candidate = {
        "candidate_id": "c_failure",
        "source_span_ids": ["s2"],
        "task_text": "Missing timeframe",
        "purpose": "Handle missing timeframe gracefully.",
        "candidate_kind": "bounded_subtask",
        "possible_inputs": [field("input_var")],
        "possible_outputs": [field("result", "output")],
        "signals": ["explicit_delegation"],
        "risks": [],
    }
    failure_decision = {
        "candidate_id": "c_failure",
        "decision": "extract_child_worker",
        "boundary_strength": "strong",
        "boundary_kind": "bounded_subtask",
        "rejection_reason": None,
        "reason": "LLM incorrectly accepted failure as child worker.",
        "evidence": ["explicit_delegation"],
    }
    mock_client.call_json.return_value = base_plan(
        workers=[main_worker(["s1"])],
        candidates=[failure_candidate],
        decisions=[failure_decision],
    )
    plan = planner.execute((spans, routes))
    assert isinstance(plan, WorkerPlanIR)
    # The failure candidate should be rejected by D1 guard
    failure_decisions = [d for d in plan.decisions if d.candidate_id == "c_failure"]
    assert len(failure_decisions) == 1
    assert failure_decisions[0].decision == "keep_in_main_worker"


def test_d1_candidate_prompt_separates_all_non_executable() -> None:
    """D1: candidate prompt partitions failure_mode + delegation from executable."""
    from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.prompt_builder import (
        PromptBuilderMixin,
    )

    spans = [
        SpanIR("s1", "Determine communication type."),
        SpanIR("s2", "Missing timeframe."),
        SpanIR("s3", "Optional source gathering if bounded."),
    ]
    routes = FieldRouteIR(
        behavior=["s1", "s2", "s3"],
        annotations=[
            RouteAnnotation(span_id="s1", field="behavior",
                            semantic_role="process_step", executable=True),
            RouteAnnotation(span_id="s2", field="behavior",
                            semantic_role="failure_mode",
                            construct_target="EXCEPTION_FLOW",
                            slot_target="condition", executable=False),
            RouteAnnotation(span_id="s3", field="behavior",
                            semantic_role="delegation_intent",
                            route_family="delegation_boundary",
                            executable=False),
        ],
    )

    pb = PromptBuilderMixin()
    prompt = pb._build_candidate_prompt(spans, routes, None)

    assert "Executable behavior spans (candidate source_span_ids)" in prompt
    assert "Non-executable context" in prompt
    assert "NOT task unit candidates" in prompt

    exec_start = prompt.index("Executable behavior spans (candidate source_span_ids)")
    non_exec_start = prompt.index("Non-executable context")
    exec_section = prompt[exec_start:non_exec_start]
    ctx_section = prompt[non_exec_start:]

    # Only process_step in executable; failure + delegation excluded
    assert "s1:" in exec_section
    assert "s2:" not in exec_section
    assert "s3:" not in exec_section

    # Both failure and delegation in non-executable context
    assert "s2:" in ctx_section
    assert "s3:" in ctx_section
    assert "failure" in ctx_section.lower()
    assert "delegation" in ctx_section.lower()


def test_d1_decision_prompt_separates_context() -> None:
    """D1: decision prompt partitions failure + delegation from executable."""
    from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.prompt_builder import (
        PromptBuilderMixin,
    )

    spans = [
        SpanIR("s1", "Determine communication type."),
        SpanIR("s2", "Missing timeframe."),
        SpanIR("s3", "Optional source gathering if bounded."),
    ]
    routes = FieldRouteIR(
        behavior=["s1", "s2", "s3"],
        annotations=[
            RouteAnnotation(span_id="s1", field="behavior",
                            semantic_role="process_step", executable=True),
            RouteAnnotation(span_id="s2", field="behavior",
                            semantic_role="failure_mode",
                            construct_target="EXCEPTION_FLOW",
                            slot_target="condition", executable=False),
            RouteAnnotation(span_id="s3", field="behavior",
                            semantic_role="delegation_intent",
                            route_family="delegation_boundary",
                            executable=False),
        ],
    )

    pb = PromptBuilderMixin()
    prompt = pb._build_decision_prompt(spans, routes, None, [])

    assert "Executable behavior span context:" in prompt
    assert "Non-executable context" in prompt
    assert "failure" in prompt.lower()
    assert "delegation" in prompt.lower()

    exec_start = prompt.index("Executable behavior span context:")
    non_exec_start = prompt.index("Non-executable context")
    exec_section = prompt[exec_start:non_exec_start]
    ctx_section = prompt[non_exec_start:]

    assert "s1:" in exec_section
    assert "s2:" not in exec_section
    assert "s3:" not in exec_section
    assert "s2:" in ctx_section
    assert "s3:" in ctx_section
