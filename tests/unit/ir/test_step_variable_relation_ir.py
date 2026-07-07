from __future__ import annotations

import pytest

from nl2spl.ir.step_variable_relation_ir import (
    RequiredOutputFulfillmentState,
    StepVariableRelation,
    StepVariableRelationPlan,
)


def test_step_variable_relation_plan_round_trips_evidence_fields() -> None:
    plan = StepVariableRelationPlan(
        relations=(
            StepVariableRelation(
                step_id="st_api",
                variable_name="source_evidence_set",
                relation="produces",
                source_span_ids=("s18",),
                evidence_kind="api_contract",
                evidence_source="api_contract",
                evidence_text="return source evidence",
                confidence="high",
            ),
        ),
        diagnostics=("step_variable_relation_ambiguous:st:out",),
    )

    payload = plan.to_payload()
    assert StepVariableRelationPlan.from_payload(payload).to_payload() == payload
    assert plan.producing_relations()[0].variable_name == "source_evidence_set"


def test_required_output_fulfillment_rejects_empty_produced_state() -> None:
    with pytest.raises(ValueError):
        RequiredOutputFulfillmentState(
            output_name="source_evidence_set",
            status="produced",
        )


def test_required_output_fulfillment_rejects_empty_deferred_state() -> None:
    with pytest.raises(ValueError):
        RequiredOutputFulfillmentState(
            output_name="source_evidence_set",
            status="deferred",
        )


def test_required_output_fulfillment_rejects_missing_with_refs() -> None:
    with pytest.raises(ValueError):
        RequiredOutputFulfillmentState(
            output_name="source_evidence_set",
            status="missing",
            deferred_refs=("st_api",),
        )
    with pytest.raises(ValueError):
        RequiredOutputFulfillmentState(
            output_name="source_evidence_set",
            status="missing",
            producer_step_ids=("st_1",),
        )


def test_required_output_fulfillment_round_trips_deferred_state() -> None:
    state = RequiredOutputFulfillmentState(
        output_name="source_evidence_set",
        status="deferred",
        deferred_refs=("st_api",),
        reason="api_return_contract_unknown",
    )

    payload = state.to_payload()
    assert RequiredOutputFulfillmentState.from_payload(payload).to_payload() == payload
