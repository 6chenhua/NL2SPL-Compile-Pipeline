from __future__ import annotations

from nl2spl.compiler.capability_intent.model import (
    CapabilityEvidenceIR,
    ExternalCapabilityIntentIR,
    ExternalCapabilityIntentPlanIR,
)
from nl2spl.compiler.construct_plan import ConstructPlanner
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR


def test_route_api_group_id_no_longer_pairs_call_to_declaration() -> None:
    routes = FieldRouteIR(
        integrations=["s1", "s2"],
        behavior=["s3"],
        annotations=[
            _declaration("s1", "SearchAPI", "search"),
            _declaration("s2", "LookupAPI", "lookup"),
            _call("s3", "search"),
        ],
    )

    plan = ConstructPlanner().plan(_spans(), routes, source_schema="generic_nl")

    assert plan.api_declaration_demands() == []
    assert plan.api_call_demands() == []


def test_final_intent_id_pairs_call_to_matching_declaration() -> None:
    plan = ConstructPlanner().plan(
        _spans(),
        FieldRouteIR(behavior=["s3"], integrations=[]),
        source_schema="generic_nl",
        capability_intent_plan=_intent_plan(
            intent_id="cap_intent_search",
            capability_ref="SearchAPI",
            source_span_id="s3",
        ),
    )

    declaration = plan.api_declaration_demands()[0]
    call = plan.api_call_demands()[0]
    assert declaration.api_group_id == "cap_intent_search"
    assert call.api_group_id == "cap_intent_search"
    assert call.declaration_demand_id == declaration.demand_id
    assert call.pairing_status == "paired"


def test_multi_api_route_ambiguity_does_not_select_first_declaration() -> None:
    routes = FieldRouteIR(
        integrations=["s1", "s2"],
        behavior=["s3"],
        annotations=[
            _declaration("s1", "SearchAPI", "search"),
            _declaration("s2", "SearchBackupAPI", "search"),
            _call("s3", "search"),
        ],
    )

    plan = ConstructPlanner().plan(_spans(), routes, source_schema="generic_nl")

    assert plan.api_declaration_demands() == []
    assert plan.api_call_demands() == []


def test_integration_hint_without_final_intent_is_not_candidate_declaration() -> None:
    routes = FieldRouteIR(
        integrations=["s1"],
        annotations=[
            RouteAnnotation(
                span_id="s1",
                field="integrations",
                semantic_role="integration_hint",
                route_family="integration_candidate",
                construct_target="API_DECLARATION",
                slot_target="source_evidence",
                executable=False,
                metadata={"api_group_id": "approved-sources"},
            )
        ],
    )

    plan = ConstructPlanner().plan(_spans(), routes, source_schema="generic_nl")

    assert plan.api_declaration_demands() == []
    assert plan.api_call_demands() == []


def _spans() -> list[SpanIR]:
    return [
        SpanIR("s1", "SearchAPI"),
        SpanIR("s2", "SearchBackupAPI"),
        SpanIR("s3", "Retrieve approved sources using SearchAPI."),
    ]


def _declaration(span_id: str, name: str, group_id: str) -> RouteAnnotation:
    return RouteAnnotation(
        span_id=span_id,
        field="integrations",
        semantic_role="api_candidate",
        route_family="integration_candidate",
        construct_target="API_DECLARATION",
        slot_target="source_evidence",
        executable=False,
        metadata={
            "annotation_id": f"ann_decl_{span_id}",
            "api_group_id": group_id,
            "explicit_api_name": name,
        },
    )


def _call(span_id: str, group_id: str) -> RouteAnnotation:
    return RouteAnnotation(
        span_id=span_id,
        field="behavior",
        semantic_role="process_step",
        route_family="flow_relevant",
        construct_target="CALL_API",
        slot_target="call_action",
        executable=True,
        metadata={
            "annotation_id": f"ann_call_{span_id}",
            "api_action": True,
            "api_group_id": group_id,
        },
    )


def _intent_plan(
    *,
    intent_id: str,
    capability_ref: str,
    source_span_id: str,
) -> ExternalCapabilityIntentPlanIR:
    operation = "Retrieve approved sources using SearchAPI."
    evidence = (
        CapabilityEvidenceIR(
            evidence_id="ev_operation",
            source_span_id=source_span_id,
            claim="operation",
            surface_text=operation,
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_boundary",
            source_span_id=source_span_id,
            claim="boundary",
            surface_text=capability_ref,
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_identity",
            source_span_id=source_span_id,
            claim="identity",
            surface_text=capability_ref,
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_invocation",
            source_span_id=source_span_id,
            claim="invocation",
            surface_text=operation,
            relation="direct",
        ),
    )
    intent = ExternalCapabilityIntentIR(
        intent_id=intent_id,
        source_candidate_ids=("candidate_search",),
        source_span_ids=(source_span_id,),
        operation_text=operation,
        capability_surface=capability_ref,
        capability_ref=capability_ref,
        boundary_status="confirmed_external",
        identity_status="explicit_name",
        invocation_status="executable",
        capability_admission_status="confirmed_capability",
        invocation_admission_status="confirmed_invocation",
        evidence=evidence,
    )
    return ExternalCapabilityIntentPlanIR(
        plan_id="cap_plan",
        intents=(intent,),
        candidate_resolution_map={"candidate_search": intent_id},
    )
