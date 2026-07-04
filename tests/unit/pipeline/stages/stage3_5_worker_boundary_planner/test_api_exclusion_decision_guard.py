"""APW3 prompt, validator, and materializer guards for API-owned spans."""

from __future__ import annotations

import pytest

from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    WorkerBoundaryDecisionIR,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner import (
    WorkerBoundaryPlanner,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.api_exclusion import (
    WorkerBoundaryExclusionView,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
    WorkerPlanMaterializer,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.prompt_builder import (
    PromptBuilderMixin,
)


@pytest.fixture
def planner(pipeline_config, mock_client) -> WorkerBoundaryPlanner:
    return WorkerBoundaryPlanner(pipeline_config, mock_client)


def _view() -> WorkerBoundaryExclusionView:
    return WorkerBoundaryExclusionView(
        api_consumed_span_ids=frozenset({"s16"}),
        api_residual_span_ids=frozenset(),
        api_call_demand_ids_by_span={"s16": ("api_call_19e71fc8b204a57a",)},
        audit_payload={"authority": "external_capability_intent_plan"},
    )


def _field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(
        name=name,
        data_type="text",
        required=True,
        description=name,
        source=source,
    )


def _candidate(spans: list[str]) -> CandidateTaskUnitIR:
    return CandidateTaskUnitIR(
        candidate_id="candidate_retrieve_approved_sources",
        source_span_ids=spans,
        task_text="Retrieve approved sources.",
        purpose="Retrieve approved sources.",
        candidate_kind="integration_wrapper",
        possible_inputs=[_field("approved_source_recipes")],
        possible_outputs=[_field("sourced_facts_with_provenance", "output")],
        signals=["external_integration", "bounded_io"],
        risks=[],
    )


def _extract_decision(*, boundary_kind: str = "integration_wrapper") -> WorkerBoundaryDecisionIR:
    return WorkerBoundaryDecisionIR(
        candidate_id="candidate_retrieve_approved_sources",
        decision="extract_child_worker",
        boundary_strength="strong",
        boundary_kind=boundary_kind,
        rejection_reason=None,
        reason="Stale accepted child worker.",
        evidence=["external_integration"],
    )


def test_prompt_includes_api_consumed_section() -> None:
    spans = [
        SpanIR("s16", "retrieve them using approved source recipes"),
        SpanIR("s23", "maintain provenance"),
    ]
    routes = FieldRouteIR(behavior=["s16", "s23"])
    prompt_builder = PromptBuilderMixin()

    candidate_prompt = prompt_builder._build_candidate_prompt(
        spans,
        routes,
        None,
        exclusion_view=_view(),
    )
    decision_prompt = prompt_builder._build_decision_prompt(
        spans,
        routes,
        None,
        [_candidate(["s16", "s23"])],
        exclusion_view=_view(),
    )

    for prompt in (candidate_prompt, decision_prompt):
        assert "API-consumed spans" in prompt
        assert "s16 -> api_call_19e71fc8b204a57a" in prompt
        assert "NOT child-worker evidence" in prompt
        assert "independently re-evaluated residual spans" in prompt


def test_validator_rejects_stale_integration_call_enum(
    planner: WorkerBoundaryPlanner,
) -> None:
    with pytest.raises(ValueError, match="Unsupported boundary_kind"):
        planner._validate_split_decisions(
            [_candidate(["s23"])],
            [_extract_decision(boundary_kind="integration_call")],
            _view(),
            [],
        )


def test_validator_rejects_extract_child_worker_consuming_api_span(
    planner: WorkerBoundaryPlanner,
) -> None:
    with pytest.raises(ValueError, match="API-owned spans"):
        planner._validate_split_decisions(
            [_candidate(["s16"])],
            [_extract_decision()],
            _view(),
            [],
        )


def test_validator_rejects_mixed_child_decision_without_residual_re_evaluation(
    planner: WorkerBoundaryPlanner,
) -> None:
    with pytest.raises(ValueError, match="API-owned spans"):
        planner._validate_split_decisions(
            [_candidate(["s16", "s23"])],
            [_extract_decision()],
            _view(),
            [],
        )


def test_materializer_does_not_create_api_owned_child_worker() -> None:
    candidate = _candidate(["s16"])
    decision = _extract_decision()

    plan, warnings = WorkerPlanMaterializer().materialize(
        candidates=[candidate],
        decisions=[decision],
        hard_fact_inputs=[_field("approved_source_recipes")],
        hard_fact_outputs=[_field("sourced_facts_with_provenance", "output")],
        behavior_span_ids={"s16"},
        behavior_span_order=["s16"],
        api_consumed_span_ids={"s16"},
    )

    assert [worker.kind for worker in plan.workers] == ["main"]
    assert plan.decisions[0].decision == "keep_in_main_worker"
    assert plan.decisions[0].rejection_reason == "single_api_call"
    assert any("API-owned spans" in warning for warning in warnings)
