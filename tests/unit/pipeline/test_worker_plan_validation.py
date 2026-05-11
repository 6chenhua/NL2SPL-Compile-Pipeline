"""Unit tests for WorkerPlanValidator."""

from __future__ import annotations

from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    ControlComplexityRegionIR,
    InputBindingIR,
    OutputBindingIR,
    WorkerBoundaryDecisionIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.worker_plan_validator import WorkerPlanValidator


def field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(name, "text", True, f"{name} field", source)  # type: ignore[arg-type]


def main_worker(
    worker_id: str = "worker_main",
    worker_name: str = "MainWorker",
    spans: list[str] | None = None,
) -> WorkerSpecIR:
    return WorkerSpecIR(
        worker_id=worker_id,
        worker_name=worker_name,
        kind="main",
        purpose="Coordinate request",
        owned_span_ids=spans or ["s1"],
        input_contract=[field("request")],
        output_contract=[field("draft", "output")],
        boundary_kind="main_worker",
    )


def child_worker(
    worker_id: str = "worker_child",
    worker_name: str = "ChildWorker",
    spans: list[str] | None = None,
    inputs: list[ContractFieldIR] | None = None,
    outputs: list[ContractFieldIR] | None = None,
) -> WorkerSpecIR:
    return WorkerSpecIR(
        worker_id=worker_id,
        worker_name=worker_name,
        kind="child",
        purpose="Gather sources",
        owned_span_ids=spans or ["s2"],
        input_contract=inputs if inputs is not None else [field("child_input")],
        output_contract=outputs if outputs is not None else [field("child_output", "output")],
        boundary_kind="bounded_subtask",
    )


def invoke_handoff(
    to_worker: str | None = "worker_child",
    input_child: str = "child_input",
    output_child: str = "child_output",
) -> WorkerHandoffIR:
    return WorkerHandoffIR(
        handoff_id="h1",
        from_worker="worker_main",
        to_worker=to_worker,
        api_ref=None,
        mode="invoke",
        condition_text=None,
        ordering="conditional",
        input_bindings=[InputBindingIR("request", input_child, True)],
        output_bindings=[OutputBindingIR(output_child, "evidence", True, "set")],
    )


def api_handoff(api_ref: str | None = "SearchAPI", to_worker: str | None = None) -> WorkerHandoffIR:
    return WorkerHandoffIR(
        handoff_id="h_api",
        from_worker="worker_main",
        to_worker=to_worker,
        api_ref=api_ref,
        mode="api_call",
        condition_text=None,
        ordering="conditional",
    )


def plan_with_child(
    child: WorkerSpecIR | None = None,
    handoffs: list[WorkerHandoffIR] | None = None,
) -> WorkerPlanIR:
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(), child or child_worker()],
        handoffs=handoffs if handoffs is not None else [invoke_handoff()],
    )


def rejected_decision(candidate_id: str = "candidate_weak") -> WorkerBoundaryDecisionIR:
    return WorkerBoundaryDecisionIR(
        candidate_id,
        "keep_in_main_worker",
        "weak",
        "not_a_worker",
        "insufficient_semantic_boundary",
        "Not independently callable.",
        [],
    )


def accepted_decision(candidate_id: str = "candidate_child") -> WorkerBoundaryDecisionIR:
    return WorkerBoundaryDecisionIR(
        candidate_id,
        "extract_child_worker",
        "strong",
        "bounded_subtask",
        None,
        "Clear IO and invocation.",
        ["bounded_io"],
    )


def validate(plan: WorkerPlanIR, known_span_ids: set[str] | None = None) -> list[str]:
    return WorkerPlanValidator().validate(plan, known_span_ids).errors


def test_valid_main_child_plan_with_handoff() -> None:
    errors = validate(plan_with_child(), {"s1", "s2"})

    assert errors == []


def test_valid_accepted_decision_materialized_by_span_match() -> None:
    accepted = accepted_decision("candidate_child")
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(spans=["s1"]), child_worker(worker_id="worker_source")],
        handoffs=[invoke_handoff(to_worker="worker_source")],
        candidates=[
            CandidateTaskUnitIR(
                "candidate_child",
                ["s2"],
                "Gather sources",
                "Gather sources",
                "bounded_subtask",
            )
        ],
        decisions=[accepted],
    )

    assert validate(plan, {"s1", "s2"}) == []


def test_reject_child_without_handoff() -> None:
    errors = validate(plan_with_child(handoffs=[]))

    assert any("Non-main worker has no handoff" in error for error in errors)


def test_reject_accepted_decision_without_concrete_worker() -> None:
    accepted = accepted_decision("candidate_child")
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker()],
        candidates=[
            CandidateTaskUnitIR(
                "candidate_child",
                ["s2"],
                "Gather sources",
                "Gather sources",
                "bounded_subtask",
            )
        ],
        decisions=[accepted],
    )

    errors = validate(plan, {"s1", "s2"})

    assert any("must match exactly one non-main worker" in error for error in errors)


def test_reject_accepted_decision_without_invoke_handoff() -> None:
    accepted = accepted_decision("candidate_child")
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(), child_worker()],
        candidates=[
            CandidateTaskUnitIR(
                "candidate_child",
                ["s2"],
                "Gather sources",
                "Gather sources",
                "bounded_subtask",
            )
        ],
        decisions=[accepted],
        handoffs=[],
    )

    errors = validate(plan, {"s1", "s2"})

    assert any("has no invoke handoff" in error for error in errors)


def test_reject_accepted_handoff_without_bindings() -> None:
    accepted = accepted_decision("candidate_child")
    handoff = invoke_handoff()
    handoff.input_bindings = []
    handoff.output_bindings = []
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(), child_worker()],
        candidates=[
            CandidateTaskUnitIR(
                "candidate_child",
                ["s2"],
                "Gather sources",
                "Gather sources",
                "bounded_subtask",
            )
        ],
        decisions=[accepted],
        handoffs=[handoff],
    )

    errors = validate(plan, {"s1", "s2"})

    assert any("empty input bindings" in error for error in errors)
    assert any("empty output bindings" in error for error in errors)


def test_reject_handoff_with_missing_target() -> None:
    errors = validate(plan_with_child(handoffs=[invoke_handoff("worker_missing")]))

    assert any("unknown target worker" in error for error in errors)


def test_reject_duplicate_handoff_ids() -> None:
    first_handoff = invoke_handoff()
    second_handoff = invoke_handoff()

    errors = validate(plan_with_child(handoffs=[first_handoff, second_handoff]))

    assert any("Duplicate handoff_id: h1" in error for error in errors)


def test_reject_none_handoff_nested_contracts_without_throwing() -> None:
    handoff = invoke_handoff()
    handoff.invoke_location_hint = None  # type: ignore[assignment]
    handoff.failure_policy = None  # type: ignore[assignment]

    errors = validate(plan_with_child(handoffs=[handoff]))

    assert any("missing invoke_location_hint" in error for error in errors)
    assert any("missing failure_policy" in error for error in errors)


def test_reject_invalid_runtime_enum_values() -> None:
    worker = child_worker()
    worker.kind = "banana"  # type: ignore[assignment]
    worker.boundary_kind = "banana"  # type: ignore[assignment]
    worker.decision_evidence = ["banana"]  # type: ignore[list-item]
    handoff = invoke_handoff()
    handoff.mode = "banana"  # type: ignore[assignment]
    handoff.ordering = "banana"  # type: ignore[assignment]
    handoff.output_bindings = [
        OutputBindingIR("child_output", "evidence", True, "banana")  # type: ignore[arg-type]
    ]
    handoff.invoke_location_hint.flow_kind = "banana"  # type: ignore[assignment]
    handoff.invoke_location_hint.block_hint = "banana"  # type: ignore[assignment]
    handoff.failure_policy.policy_kind = "banana"  # type: ignore[assignment]
    candidate = CandidateTaskUnitIR(
        "candidate_bad",
        ["s2"],
        "Bad candidate",
        "Bad candidate",
        "banana",  # type: ignore[arg-type]
        signals=["banana"],  # type: ignore[list-item]
        risks=["banana"],  # type: ignore[list-item]
    )
    decision = WorkerBoundaryDecisionIR(
        "candidate_bad",
        "banana",  # type: ignore[arg-type]
        "banana",  # type: ignore[arg-type]
        "banana",  # type: ignore[arg-type]
        "banana",  # type: ignore[arg-type]
        "Bad decision",
        ["banana"],  # type: ignore[list-item]
    )
    region = ControlComplexityRegionIR(
        "region_bad",
        ["s2"],
        "banana",  # type: ignore[arg-type]
        "banana",  # type: ignore[arg-type]
        "Bad region",
        "banana",  # type: ignore[arg-type]
        "banana",  # type: ignore[arg-type]
        False,
        False,
        False,
        ["banana"],  # type: ignore[list-item]
    )
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(), worker],
        handoffs=[handoff],
        candidates=[candidate],
        decisions=[decision],
        rejected_candidates=[decision],
        control_complexity_regions=[region],
    )

    errors = validate(plan, {"s1", "s2"})

    assert any("Worker.kind has invalid value" in error for error in errors)
    assert any("Handoff.mode has invalid value" in error for error in errors)
    assert any("Candidate.candidate_kind has invalid value" in error for error in errors)
    assert any("Decision.decision has invalid value" in error for error in errors)
    assert any("OutputBinding.merge_strategy has invalid value" in error for error in errors)
    assert any("ControlRegion.severity has invalid value" in error for error in errors)


def test_reject_duplicate_worker_names() -> None:
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(worker_name="SameName"), child_worker(worker_name="SameName")],
        handoffs=[invoke_handoff()],
    )

    assert any("Duplicate worker_name" in error for error in validate(plan))


def test_reject_unsafe_worker_names() -> None:
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(worker_name="Main Worker"), child_worker()],
        handoffs=[invoke_handoff()],
    )

    assert any("not SPL-safe" in error for error in validate(plan))


def test_validate_binding_mismatch() -> None:
    errors = validate(plan_with_child(handoffs=[invoke_handoff(input_child="missing_input")]))

    assert any("input binding references unknown" in error for error in errors)


def test_validate_invoke_vs_api_call_mode_constraints() -> None:
    invoke_missing_target = plan_with_child(handoffs=[invoke_handoff(to_worker=None)])
    api_missing_ref = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker()],
        handoffs=[api_handoff(api_ref=None)],
    )
    api_with_worker_target = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(), child_worker()],
        handoffs=[api_handoff(to_worker="worker_child")],
    )

    assert any("missing to_worker" in error for error in validate(invoke_missing_target))
    assert any("must set api_ref" in error for error in validate(api_missing_ref))
    assert any("must not set to_worker" in error for error in validate(api_with_worker_target))


def test_reject_invoke_handoff_targeting_main_worker() -> None:
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(), child_worker()],
        handoffs=[invoke_handoff(to_worker="worker_main")],
    )

    assert any("must target a non-main worker" in error for error in validate(plan))


def test_validate_duplicate_behavior_span_ownership() -> None:
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(spans=["s1", "s2"]), child_worker(spans=["s2"])],
        handoffs=[invoke_handoff()],
    )

    assert any("Duplicate behavior-span ownership" in error for error in validate(plan))


def test_validate_unknown_owned_span() -> None:
    errors = validate(plan_with_child(), {"s1"})

    assert any("owns unknown span_id" in error for error in errors)


def test_validate_rejected_candidate_consistency() -> None:
    rejected = rejected_decision("candidate_weak")
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker()],
        candidates=[
            CandidateTaskUnitIR(
                "candidate_weak",
                ["s2"],
                "Weak task",
                "Weak task",
                "not_a_worker",
            )
        ],
        decisions=[],
        rejected_candidates=[rejected],
    )

    assert any("missing from decisions" in error for error in validate(plan))


def test_rejected_candidate_can_remain_owned_by_main_worker() -> None:
    rejected = rejected_decision("candidate_weak")
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(spans=["s2"])],
        candidates=[
            CandidateTaskUnitIR(
                "candidate_weak",
                ["s2"],
                "Weak task",
                "Weak task",
                "not_a_worker",
            )
        ],
        decisions=[rejected],
        rejected_candidates=[rejected],
    )

    assert validate(plan, {"s2"}) == []


def test_reject_concrete_worker_for_rejected_candidate() -> None:
    rejected = rejected_decision("candidate_weak")
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker(), child_worker(worker_id="candidate_weak")],
        decisions=[rejected],
        rejected_candidates=[rejected],
        handoffs=[invoke_handoff(to_worker="candidate_weak")],
    )

    assert any(
        "Rejected candidate is present as concrete worker" in error
        for error in validate(plan)
    )


def test_reject_accepted_decision_in_rejected_candidates() -> None:
    accepted = accepted_decision()
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker()],
        decisions=[accepted],
        rejected_candidates=[accepted],
    )

    assert any(
        "Accepted decision appears in rejected_candidates" in error
        for error in validate(plan)
    )
