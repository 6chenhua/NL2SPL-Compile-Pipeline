"""Unit tests for WorkerPlanIR contracts."""

from __future__ import annotations

from dataclasses import asdict

from nl2spl.ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    HandoffFailurePolicyIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerBoundaryDecisionIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.worker_plan_adapter import (
    adapt_worker_plan_to_delegation_candidates,
)


def field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(
        name=name,
        data_type="text",
        required=True,
        description=f"{name} field",
        source=source,  # type: ignore[arg-type]
    )


def main_worker() -> WorkerSpecIR:
    return WorkerSpecIR(
        worker_id="worker_main",
        worker_name="MainWorker",
        kind="main",
        purpose="Coordinate the request",
        owned_span_ids=["s1"],
        input_contract=[field("request")],
        output_contract=[field("draft", "output")],
        boundary_kind="main_worker",
    )


def child_worker() -> WorkerSpecIR:
    return WorkerSpecIR(
        worker_id="worker_child",
        worker_name="SourceWorker",
        kind="child",
        purpose="Gather sources",
        owned_span_ids=["s2"],
        input_contract=[field("source_request")],
        output_contract=[field("evidence", "output")],
        boundary_kind="bounded_subtask",
    )


def api_adapter_worker() -> WorkerSpecIR:
    return WorkerSpecIR(
        worker_id="worker_api_adapter",
        worker_name="SourceApiAdapter",
        kind="api_adapter",
        purpose="Normalize source API responses",
        owned_span_ids=["s3"],
        input_contract=[field("source_request")],
        output_contract=[field("normalized_evidence", "output")],
        boundary_kind="integration_wrapper",
    )


def handoff() -> WorkerHandoffIR:
    return WorkerHandoffIR(
        handoff_id="h1",
        from_worker="worker_main",
        to_worker="worker_child",
        api_ref=None,
        mode="invoke",
        condition_text="sources are needed",
        ordering="conditional",
        input_bindings=[InputBindingIR("request", "source_request", True)],
        output_bindings=[OutputBindingIR("evidence", "evidence", True, "set")],
        invoke_location_hint=InvokeLocationHintIR(
            "main",
            None,
            "s1",
            None,
            "if",
        ),
        failure_policy=HandoffFailurePolicyIR(
            "block_finalization",
            "Block finalization if evidence cannot be gathered.",
            ["s2"],
        ),
    )


def accepted_decision(candidate_id: str = "candidate_source") -> WorkerBoundaryDecisionIR:
    return WorkerBoundaryDecisionIR(
        candidate_id=candidate_id,
        decision="extract_child_worker",
        boundary_strength="strong",
        boundary_kind="bounded_subtask",
        rejection_reason=None,
        reason="Bounded source gathering with clear IO.",
        evidence=["bounded_io"],
    )


def accepted_api_adapter_decision() -> WorkerBoundaryDecisionIR:
    return WorkerBoundaryDecisionIR(
        candidate_id="worker_api_adapter",
        decision="extract_child_worker",
        boundary_strength="strong",
        boundary_kind="integration_wrapper",
        rejection_reason=None,
        reason="API response normalization is a bounded adapter worker.",
        evidence=["external_integration", "evidence_normalization"],
    )


def rejected_decision(candidate_id: str = "candidate_weak") -> WorkerBoundaryDecisionIR:
    return WorkerBoundaryDecisionIR(
        candidate_id=candidate_id,
        decision="keep_in_main_worker",
        boundary_strength="weak",
        boundary_kind="not_a_worker",
        rejection_reason="insufficient_semantic_boundary",
        reason="Not independently callable.",
        evidence=[],
    )


def test_construct_minimal_one_worker_plan() -> None:
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker()],
    )

    assert plan.main_worker_id == "worker_main"
    assert plan.workers[0].worker_name == "MainWorker"
    assert plan.main_worker == plan.workers[0]
    assert plan.handoffs == []


def test_main_worker_returns_none_when_missing() -> None:
    plan = WorkerPlanIR(
        main_worker_id="worker_missing",
        workers=[main_worker()],
    )

    assert plan.main_worker is None


def test_construct_main_child_plan_with_handoff() -> None:
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(), child_worker()],
        handoffs=[handoff()],
        decisions=[accepted_decision()],
    )

    assert plan.handoffs[0].to_worker == "worker_child"
    assert plan.handoffs[0].input_bindings[0].child_input == "source_request"
    assert asdict(plan)["workers"][1]["output_contract"][0]["name"] == "evidence"


def test_preserve_rejected_candidate() -> None:
    decision = rejected_decision()
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker()],
        decisions=[decision],
        rejected_candidates=[decision],
    )

    assert plan.rejected_candidates == [decision]


def test_adapter_converts_accepted_worker_only() -> None:
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(), child_worker()],
        candidates=[
            CandidateTaskUnitIR(
                "candidate_source",
                ["s2"],
                "Gather sources",
                "Gather sources",
                "bounded_subtask",
                [field("source_request")],
                [field("evidence", "output")],
            )
        ],
        decisions=[accepted_decision()],
        handoffs=[handoff()],
    )

    candidates = adapt_worker_plan_to_delegation_candidates(plan)

    assert len(candidates) == 1
    assert candidates[0].candidate_id == "candidate_source"
    assert candidates[0].spans == ["s2"]
    assert candidates[0].suggested_type == "child_worker"
    assert candidates[0].input_variables == ["source_request"]
    assert candidates[0].output_variables == ["evidence"]


def test_adapter_preserves_api_adapter_as_child_worker() -> None:
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(), api_adapter_worker()],
        candidates=[
            CandidateTaskUnitIR(
                "worker_api_adapter",
                ["s3"],
                "Normalize source API responses",
                "Normalize source API responses",
                "integration_wrapper",
                [field("source_request")],
                [field("normalized_evidence", "output")],
            )
        ],
        decisions=[accepted_api_adapter_decision()],
    )

    candidates = adapt_worker_plan_to_delegation_candidates(plan)

    assert len(candidates) == 1
    assert candidates[0].candidate_id == "worker_api_adapter"
    assert candidates[0].suggested_type == "child_worker"
    assert candidates[0].input_variables == ["source_request"]
    assert candidates[0].output_variables == ["normalized_evidence"]


def test_adapter_ignores_rejected_candidate() -> None:
    rejected = rejected_decision("candidate_source")
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(), child_worker()],
        candidates=[
            CandidateTaskUnitIR(
                "candidate_source",
                ["s2"],
                "Gather sources",
                "Gather sources",
                "bounded_subtask",
            )
        ],
        decisions=[accepted_decision(), rejected],
        rejected_candidates=[rejected],
        handoffs=[handoff()],
    )

    assert adapt_worker_plan_to_delegation_candidates(plan) == []
