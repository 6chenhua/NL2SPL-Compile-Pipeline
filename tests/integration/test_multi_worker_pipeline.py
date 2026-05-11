"""Multi-worker rollout and golden SPL integration tests."""

from __future__ import annotations

import pytest

from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import InputBindingIR, OutputBindingIR
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner import WorkerBoundaryPlanner
from nl2spl.pipeline.stages.stage9_5_normalizer import IRNormalizer
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler
from nl2spl.pipeline.stages.stage11_spl_renderer import SPLRenderer
from nl2spl.pipeline.worker_plan_validator import WorkerPlanValidator
from tests.fixtures.multi_worker import (
    MultiWorkerScenario,
    api_adapter_with_provenance,
    api_call_vs_api_adapter,
    duplicate_behavior_span_ownership,
    duplicate_handoff_id,
    explicit_subtask_without_io,
    flattenable_nested_control,
    internal_comms_source_gathering,
    loop_body_child_worker,
    revision_not_worker,
    same_child_multiple_handoffs,
    simple_single_worker,
    single_api_call_not_worker,
    unused_child_worker_error,
    unresolved_invoke_worker_error,
    worker_plan_validator_errors,
)


def normalize(scenario: MultiWorkerScenario):
    return IRNormalizer().normalize(
        scenario.flow,
        scenario.blocks,
        scenario.resources,
        scenario.symbols,
        list(scenario.steps),
        list(scenario.constraints),
        scenario.worker_plan,
    )


def render_scenario(scenario: MultiWorkerScenario) -> tuple[str, list[str], list[str]]:
    (
        flow,
        blocks,
        steps,
        constraints,
        symbols,
        normalization_errors,
        normalization_warnings,
    ) = normalize(scenario)
    worker = WorkerAssembler().assemble(
        flow,
        blocks,
        steps,
        scenario.resources,
        symbols,
        scenario.worker_plan,
    )
    spl, render_errors, render_warnings = SPLRenderer().render(
        worker,
        scenario.profile,
        scenario.resources,
        symbols,
        steps,
        constraints,
    )
    return spl, normalization_errors + render_errors, normalization_warnings + render_warnings


def assert_no_nested_blocks(spl: str) -> None:
    control_depth = 0
    for raw_line in spl.splitlines():
        line = raw_line.strip()
        if line.startswith(("DECISION-",)):
            control_depth += 1
            continue
        if line in {"[END_IF]", "[END_FOR]", "[END_WHILE]"}:
            control_depth = max(0, control_depth - 1)
            continue
        if control_depth:
            assert not line.startswith("[SEQUENTIAL_BLOCK]"), raw_line
            assert not line.startswith(("DECISION-",)), raw_line


def assert_child_before_main(spl: str, child_name: str, main_name: str = "MainWorker") -> None:
    child_index = spl.index(f" {child_name}]")
    main_index = spl.rindex(f" {main_name}]")
    assert child_index < main_index


def stage35_field(name: str, source: str = "input") -> dict[str, object]:
    return {
        "name": name,
        "data_type": "text",
        "required": True,
        "description": f"{name} field",
        "source": source,
    }


def stage35_plan_with_handoff(
    invoke_location_hint: object,
    failure_policy: object,
) -> dict[str, object]:
    handoff: dict[str, object] = {
        "handoff_id": "handoff_source",
        "from_worker": "worker_main",
        "to_worker": "worker_source",
        "api_ref": None,
        "mode": "invoke",
        "condition_text": "sources are needed",
        "ordering": "conditional",
        "input_bindings": [
            {
                "parent_variable": "request",
                "child_input": "request",
                "required": True,
            }
        ],
        "output_bindings": [
            {
                "child_output": "evidence",
                "parent_variable": "evidence",
                "required": True,
                "merge_strategy": "set",
            }
        ],
        "invoke_location_hint": invoke_location_hint,
        "failure_policy": failure_policy,
    }
    return {
        "main_worker_id": "worker_main",
        "workers": [
            {
                "worker_id": "worker_main",
                "worker_name": "MainWorker",
                "kind": "main",
                "purpose": "Coordinate request.",
                "owned_span_ids": ["s1"],
                "input_contract": [stage35_field("request")],
                "output_contract": [stage35_field("evidence", "output")],
                "depends_on": [],
                "constraints": [],
                "boundary_kind": "main_worker",
                "decision_evidence": [],
                "reason": "Main worker.",
            },
            {
                "worker_id": "worker_source",
                "worker_name": "SourceWorker",
                "kind": "child",
                "purpose": "Gather sources.",
                "owned_span_ids": ["s2"],
                "input_contract": [stage35_field("request")],
                "output_contract": [stage35_field("evidence", "output")],
                "depends_on": [],
                "constraints": [],
                "boundary_kind": "bounded_subtask",
                "decision_evidence": ["explicit_delegation", "bounded_io"],
                "reason": "Accepted source worker.",
            },
        ],
        "handoffs": [handoff],
        "candidates": [
            {
                "candidate_id": "candidate_source",
                "source_span_ids": ["s2"],
                "task_text": "Gather sources.",
                "purpose": "Gather sources.",
                "candidate_kind": "bounded_subtask",
                "possible_inputs": [stage35_field("request")],
                "possible_outputs": [stage35_field("evidence", "output")],
                "signals": ["explicit_delegation", "bounded_io"],
                "risks": [],
            }
        ],
        "decisions": [
            {
                "candidate_id": "candidate_source",
                "decision": "extract_child_worker",
                "boundary_strength": "strong",
                "boundary_kind": "bounded_subtask",
                "rejection_reason": None,
                "reason": "Clear bounded IO.",
                "evidence": ["explicit_delegation", "bounded_io"],
            }
        ],
        "rejected_candidates": [],
        "control_complexity_regions": [],
        "unassigned_span_ids": [],
        "warnings": [],
    }


@pytest.mark.parametrize(
    "scenario_factory",
    [
        simple_single_worker,
        internal_comms_source_gathering,
        explicit_subtask_without_io,
        revision_not_worker,
        single_api_call_not_worker,
        api_adapter_with_provenance,
        flattenable_nested_control,
        loop_body_child_worker,
        same_child_multiple_handoffs,
    ],
)
def test_rollout_fixture_worker_plans_validate(scenario_factory) -> None:
    scenario = scenario_factory()

    result = WorkerPlanValidator().validate(
        scenario.worker_plan,
        scenario.known_span_ids,
    )

    assert result.errors == []


@pytest.mark.parametrize(
    "scenario_factory",
    [
        unused_child_worker_error,
        worker_plan_validator_errors,
        duplicate_behavior_span_ownership,
        duplicate_handoff_id,
    ],
)
def test_rollout_negative_worker_plans_fail_validation(scenario_factory) -> None:
    scenario = scenario_factory()

    result = WorkerPlanValidator().validate(
        scenario.worker_plan,
        scenario.known_span_ids,
    )

    assert not result.is_valid
    for expected in scenario.expected_validator_errors:
        assert any(expected in error for error in result.errors)


@pytest.mark.parametrize(
    ("invoke_location_hint", "failure_policy"),
    [
        (None, None),
        ({}, {}),
    ],
)
def test_stage35_null_handoff_nested_objects_use_defaults(
    pipeline_config,
    mock_client,
    invoke_location_hint: object,
    failure_policy: object,
) -> None:
    mock_client.call_json.return_value = stage35_plan_with_handoff(
        invoke_location_hint,
        failure_policy,
    )

    planner = WorkerBoundaryPlanner(pipeline_config, mock_client)
    plan = planner.execute(
        (
            [
                SpanIR("s1", "Prepare the request."),
                SpanIR("s2", "Gather sources."),
            ],
            FieldRouteIR(behavior=["s1", "s2"]),
        )
    )

    assert plan.handoffs[0].invoke_location_hint.flow_kind == "main"
    assert plan.handoffs[0].invoke_location_hint.block_hint == "unknown"
    assert plan.handoffs[0].failure_policy.policy_kind == "propagate_exception"


def test_internal_comms_source_gathering_golden_spl() -> None:
    scenario = internal_comms_source_gathering()

    spl, errors, _warnings = render_scenario(scenario)

    assert errors == []
    assert "[DEFINE_TYPES:]" in spl
    assert "SourcePackage = { retrieved_sources: List [text], provenance_log: text }" in spl
    assert_child_before_main(spl, "SourceGatheringWorker")
    assert spl.count("[DEFINE_WORKER:") == 2
    assert spl.count("[INVOKE SourceGatheringWorker") == 1
    assert "RESPONSE source_evidence_set: SourcePackage SET" in spl
    assert "[ALTERNATIVE_FLOW: user asks for revision]" in spl
    assert "[EXCEPTION_FLOW: sources are needed and available]" not in spl
    assert "INVOKE Worker" not in spl
    assert "INVOKE child_worker" not in spl
    assert_no_nested_blocks(spl)


def test_simple_single_worker_has_no_child_worker_or_types() -> None:
    scenario = simple_single_worker()

    spl, errors, _warnings = render_scenario(scenario)

    assert errors == []
    assert spl.count("[DEFINE_WORKER:") == 1
    assert "[INVOKE" not in spl
    assert "[DEFINE_TYPES:]" not in spl


def test_api_call_vs_api_adapter_render_different_commands() -> None:
    api_call, api_adapter = api_call_vs_api_adapter()

    api_spl, api_errors, _ = render_scenario(api_call)
    adapter_spl, adapter_errors, _ = render_scenario(api_adapter)

    assert api_errors == []
    assert adapter_errors == []
    assert "[CALL SearchAPI" in api_spl
    assert "[INVOKE" not in api_spl
    assert "[CALL SearchAPI" not in adapter_spl
    assert "[INVOKE EvidenceAdapterWorker" in adapter_spl
    assert_child_before_main(adapter_spl, "EvidenceAdapterWorker")


def test_flattenable_nested_control_stays_single_worker() -> None:
    scenario = flattenable_nested_control()

    spl, errors, _warnings = render_scenario(scenario)

    assert errors == []
    assert spl.count("[DEFINE_WORKER:") == 1
    assert "[IF sources are needed and available]" in spl
    assert "[INVOKE" not in spl
    assert_no_nested_blocks(spl)


def test_loop_body_child_worker_invoked_inside_for_block() -> None:
    scenario = loop_body_child_worker()

    spl, errors, _warnings = render_scenario(scenario)

    assert errors == []
    assert_child_before_main(spl, "TopicEvidenceWorker")
    assert "[FOR each requested topic]" in spl
    assert "[INVOKE TopicEvidenceWorker" in spl
    assert "RESPONSE topic_evidence: List [text] SET" in spl
    assert_no_nested_blocks(spl)


def test_same_child_worker_can_be_invoked_by_multiple_handoffs() -> None:
    scenario = same_child_multiple_handoffs()

    (
        flow,
        blocks,
        steps,
        constraints,
        symbols,
        normalization_errors,
        _normalization_warnings,
    ) = normalize(scenario)
    worker = WorkerAssembler().assemble(
        flow,
        blocks,
        steps,
        scenario.resources,
        symbols,
        scenario.worker_plan,
    )
    spl, render_errors, _render_warnings = SPLRenderer().render(
        worker,
        scenario.profile,
        scenario.resources,
        symbols,
        steps,
        constraints,
    )

    invoke_steps = [step for step in steps if step.command_type == "INVOKE_WORKER"]
    assert normalization_errors + render_errors == []
    assert len(invoke_steps) == 2
    assert {step.handoff_id for step in invoke_steps} == {
        "handoff_primary_sources",
        "handoff_recovery_sources",
    }
    assert {tuple(step.outputs) for step in invoke_steps} == {
        ("primary_source_evidence",),
        ("recovery_source_evidence",),
    }
    assert worker.child_worker_refs == ["SourceGatheringWorker"]
    assert [child.worker_name for child in worker.child_workers] == [
        "SourceGatheringWorker"
    ]
    assert spl.count("[DEFINE_WORKER:") == 2
    assert spl.count("[INVOKE SourceGatheringWorker") == 2
    assert "RESPONSE primary_source_evidence: SourcePackage SET" in spl
    assert "RESPONSE recovery_source_evidence: SourcePackage SET" in spl
    assert_no_nested_blocks(spl)


def test_unresolved_invoke_worker_fails_fast() -> None:
    scenario = unresolved_invoke_worker_error()

    _flow, _blocks, _steps, _constraints, _symbols, errors, _warnings = normalize(scenario)

    assert any("no concrete child worker" in error for error in errors)


def test_api_call_required_input_must_be_declared() -> None:
    scenario = single_api_call_not_worker()
    handoff = scenario.worker_plan.handoffs[0]
    handoff.input_bindings = [InputBindingIR("missing_api_query", "query", True)]

    _flow, _blocks, _steps, _constraints, _symbols, errors, _warnings = normalize(scenario)

    assert any(
        "required input missing_api_query is not declared" in error
        for error in errors
    )


def test_api_call_required_output_must_be_in_call_api_step_outputs() -> None:
    scenario = single_api_call_not_worker()
    normalizer = IRNormalizer()
    handoff = scenario.worker_plan.handoffs[0]
    bad_step = StepIR(
        "st_bad_api",
        "Call SearchAPI without capturing the required result",
        ["s1"],
        "CALL_API",
        inputs=["api_query"],
        outputs=[],
        integration_ref="SearchAPI",
        handoff_id=handoff.handoff_id,
    )

    errors = normalizer._validate_api_handoff_step_bindings(  # noqa: SLF001
        handoff,
        bad_step,
        {"api_result"},
        scenario.symbols,
    )

    assert any(
        "required output api_result is missing from step st_bad_api" in error
        for error in errors
    )


def test_api_call_required_output_must_be_consumed_or_final() -> None:
    scenario = single_api_call_not_worker()
    handoff = scenario.worker_plan.handoffs[0]
    handoff.output_bindings = [
        OutputBindingIR("result", "intermediate_api_result", True, "set")
    ]
    scenario.resources.variables = [
        variable
        for variable in scenario.resources.variables
        if variable.name != "api_result"
    ]
    scenario.symbols = scenario.symbols.__class__()
    for variable in scenario.resources.variables:
        scenario.symbols.declare(
            variable.name,
            variable.data_type,
            variable.source,
            variable.description,
        )

    _flow, _blocks, _steps, _constraints, _symbols, errors, _warnings = normalize(scenario)

    assert any(
        "required output intermediate_api_result is not consumed or declared as a final output"
        in error
        for error in errors
    )


def test_api_call_handoff_without_call_api_step_fails() -> None:
    scenario = single_api_call_not_worker()
    scenario.worker_plan.handoffs[0].api_ref = None

    _flow, _blocks, _steps, _constraints, _symbols, errors, _warnings = normalize(scenario)

    assert any("has no CALL_API step" in error for error in errors)


def test_required_child_output_binding_mismatch_fails_validation() -> None:
    scenario = internal_comms_source_gathering()
    handoff = scenario.worker_plan.handoffs[0]
    handoff.output_bindings = [
        OutputBindingIR("missing_child_output", "source_evidence_set", True, "set")
    ]

    result = WorkerPlanValidator().validate(scenario.worker_plan, scenario.known_span_ids)

    assert any(
        "output binding references unknown contract field" in error
        for error in result.errors
    )
