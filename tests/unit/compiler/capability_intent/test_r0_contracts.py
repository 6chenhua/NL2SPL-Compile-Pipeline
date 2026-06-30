from __future__ import annotations

import pytest

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
    ConstructPlanSerializer,
)
from nl2spl.compiler.capability_intent.evidence_collector import (
    EarlyCapabilityEvidenceCollector,
)
from nl2spl.compiler.capability_intent.model import (
    CapabilityEvidenceIR,
    ExternalCapabilityIntentIR,
    ExternalCapabilityIntentPlanIR,
)
from nl2spl.compiler.construct_plan import (
    APICallDemand,
    ConstructPlan,
    OperationCoverageIR,
)
from nl2spl.compiler.resource_contract_demand_view.model import DemandViewDemand
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR


def test_demand_view_resource_ref_defaults_to_none_without_slugification() -> None:
    demand = DemandViewDemand(
        demand_id="rcd_input_s1",
        direction="input",
        requiredness="required",
        required=True,
        evidence_text="Customer source records",
    )

    assert demand.resource_ref is None
    assert demand.to_payload()["resource_ref"] is None


def test_candidate_resolution_map_is_total_and_bidirectional() -> None:
    evidence = CapabilityEvidenceIR(
        evidence_id="ev1",
        source_span_id="s1",
        claim="boundary",
        surface_text="approved retrieval service",
        relation="direct",
    )
    intent = ExternalCapabilityIntentIR(
        intent_id="cap_intent_1",
        source_candidate_ids=("candidate_1",),
        source_span_ids=("s1",),
        operation_text="retrieve records",
        capability_surface="approved retrieval service",
        capability_ref=None,
        boundary_status="confirmed_external",
        identity_status="described_unnamed",
        invocation_status="executable",
        capability_admission_status="confirmed_capability",
        invocation_admission_status="confirmed_invocation",
        evidence=(evidence,),
    )

    plan = ExternalCapabilityIntentPlanIR(
        plan_id="capability_plan_1",
        intents=(intent,),
        candidate_resolution_map={"candidate_1": "cap_intent_1"},
    )
    assert plan.to_payload()["candidate_resolution_map"] == {
        "candidate_1": "cap_intent_1"
    }

    with pytest.raises(ValueError, match="not bidirectional"):
        ExternalCapabilityIntentPlanIR(
            plan_id="invalid",
            intents=(intent,),
            candidate_resolution_map={
                "candidate_1": "cap_intent_1",
                "candidate_2": "cap_intent_1",
            },
        )


def test_operation_coverage_construct_plan_roundtrip() -> None:
    coverage = OperationCoverageIR(
        coverage_id="coverage_1",
        source_span_id="s1",
        operation_surface="retrieve records",
        char_start=0,
        char_end=16,
    )
    call = APICallDemand(
        demand_id="call_1",
        source_span_ids=["s1"],
        capability_intent_id="cap_intent_1",
        operation_coverage=[coverage],
        consumes_behavior_span_ids=["s1"],
        residual_behavior_span_ids=["s2"],
        behavior_lowering_policy="api_call_augments_behavior",
    )
    original = ConstructPlan(plan_id="plan", demands=[call])

    serializer = ConstructPlanSerializer()
    restored = serializer.from_canonical(serializer.to_canonical(original))
    restored_call = restored.api_call_demands()[0]

    assert restored_call.capability_intent_id == "cap_intent_1"
    assert restored_call.operation_coverage == [coverage]
    assert restored_call.residual_behavior_span_ids == ["s2"]
    assert restored_call.behavior_lowering_policy == "api_call_augments_behavior"


def test_early_collector_uses_structured_clues_not_keywords() -> None:
    canonical = CanonicalCompileInput(
        source_schema="generic_nl",
        schema_version="1",
        raw_text="Use SearchAPI to retrieve records.",
    )
    span = SpanIR(span_id="s1", text=canonical.raw_text)
    collector = EarlyCapabilityEvidenceCollector()

    keyword_only = collector.collect(canonical, [span], FieldRouteIR(behavior=["s1"]))
    assert keyword_only.candidates == ()

    routes = FieldRouteIR(
        behavior=["s1"],
        annotations=[
            RouteAnnotation(
                span_id="s1",
                field="behavior",
                semantic_role="process_step",
                route_family="external_capability",
                construct_target="CALL_API",
                slot_target="call_action",
                executable=True,
            )
        ],
    )
    structured = collector.collect(canonical, [span], routes)

    assert len(structured.candidates) == 1
    assert structured.candidates[0].claim_hint == "possible_invocation"
    assert structured.metadata["authority"] == "non_authoritative"
