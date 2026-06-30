from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    build_default_registry,
)
from nl2spl.compiler.capability_intent.model import (
    CapabilityEvidenceIR,
    ExternalCapabilityIntentIR,
    ExternalCapabilityIntentPlanIR,
)
from nl2spl.compiler.construct_plan import (
    APICallDemand,
    APIDeclarationDemand,
    ConstructPlanner,
    ConstructPlan,
    OperationCoverageIR,
)
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR


def test_route_marked_search_api_does_not_produce_declaration_or_call_demands() -> None:
    spans = [
        SpanIR("s1", "SearchAPI"),
        SpanIR("s2", "Retrieve approved sources using SearchAPI."),
    ]
    routes = FieldRouteIR(
        integrations=["s1"],
        behavior=["s2"],
        annotations=[
            RouteAnnotation(
                span_id="s1",
                field="integrations",
                semantic_role="api_candidate",
                route_family="integration_candidate",
                construct_target="API_DECLARATION",
                slot_target="source_evidence",
                executable=False,
                metadata={"explicit_api_name": "SearchAPI"},
            ),
            RouteAnnotation(
                span_id="s2",
                field="behavior",
                semantic_role="process_step",
                route_family="flow_relevant",
                construct_target="CALL_API",
                slot_target="call_action",
                executable=True,
                metadata={"api_action": True},
            ),
        ],
    )

    plan = ConstructPlanner().plan(spans, routes, source_schema="generic_nl")

    assert plan.api_declaration_demands() == []
    assert plan.api_call_demands() == []
    assert plan.metadata["api_demand_authority"] == "external_capability_intent_plan"


def test_confirmed_capability_intent_produces_declaration_and_call_demands() -> None:
    span = SpanIR("s1", "Retrieve approved sources using SearchAPI.")
    plan = ConstructPlanner().plan(
        [span],
        FieldRouteIR(behavior=["s1"], integrations=[]),
        source_schema="generic_nl",
        capability_intent_plan=_intent_plan(span.text),
    )

    declarations = plan.api_declaration_demands()
    calls = plan.api_call_demands()
    assert len(declarations) == 1
    assert len(calls) == 1

    declaration = declarations[0]
    assert isinstance(declaration, APIDeclarationDemand)
    assert declaration.construct_type == "API_DECLARATION"
    assert declaration.explicit_name_candidates == ["SearchAPI"]
    assert declaration.integration_admission == "confirmed"
    assert declaration.mechanism_status == "explicit"
    assert declaration.inferred_name_allowed is False
    assert declaration.api_group_id == "cap_intent_search"
    assert declaration.capability_intent_id == "cap_intent_search"

    call = calls[0]
    assert isinstance(call, APICallDemand)
    assert call.construct_type == "CALL_API"
    assert call.api_group_id == "cap_intent_search"
    assert call.declaration_demand_id == declaration.demand_id
    assert call.pairing_status == "paired"
    assert call.action_text == span.text
    assert call.operation_coverage[0].operation_surface == span.text
    assert call.behavior_lowering_policy == "api_call_replaces_behavior"


def test_ordinary_process_step_does_not_generate_api_call_demand() -> None:
    spans = [SpanIR("s1", "Retrieve approved sources.")]
    routes = FieldRouteIR(
        behavior=["s1"],
        annotations=[
            RouteAnnotation(
                span_id="s1",
                field="behavior",
                semantic_role="process_step",
                route_family="flow_relevant",
                executable=True,
            )
        ],
    )

    plan = ConstructPlanner().plan(spans, routes, source_schema="generic_nl")

    assert plan.api_declaration_demands() == []
    assert plan.api_call_demands() == []


def test_plain_search_or_retrieve_text_does_not_generate_api_demands() -> None:
    spans = [
        SpanIR("s1", "Search approved sources."),
        SpanIR("s2", "Retrieve approved sources."),
    ]
    routes = FieldRouteIR(
        behavior=["s1", "s2"],
        annotations=[
            RouteAnnotation(
                span_id="s1",
                field="behavior",
                semantic_role="process_step",
                route_family="flow_relevant",
                executable=True,
            ),
            RouteAnnotation(
                span_id="s2",
                field="behavior",
                semantic_role="process_step",
                route_family="flow_relevant",
                executable=True,
            ),
        ],
    )

    plan = ConstructPlanner().plan(spans, routes, source_schema="generic_nl")

    assert plan.api_declaration_demands() == []
    assert plan.api_call_demands() == []


def test_construct_plan_serializer_preserves_api_demand_types() -> None:
    plan = ConstructPlan(
        plan_id="cp",
        demands=[
            APIDeclarationDemand(
                demand_id="api_decl_SearchAPI",
                explicit_name_candidates=["SearchAPI"],
                integration_admission="confirmed",
                mechanism_status="explicit",
                source_span_ids=["s1"],
                capability_intent_id="cap_intent_search",
                capability_surface="SearchAPI",
            ),
            APICallDemand(
                demand_id="api_call_search",
                declaration_demand_id="api_decl_SearchAPI",
                action_text="Retrieve approved sources using SearchAPI.",
                source_span_ids=["s1"],
                capability_intent_id="cap_intent_search",
                operation_coverage=[
                    OperationCoverageIR(
                        coverage_id="cov_search",
                        source_span_id="s1",
                        operation_surface="Retrieve approved sources using SearchAPI.",
                        char_start=0,
                        char_end=len("Retrieve approved sources using SearchAPI."),
                    )
                ],
                consumes_behavior_span_ids=["s1"],
                behavior_lowering_policy="api_call_replaces_behavior",
            ),
        ],
    )
    registry = build_default_registry()

    payload = registry.serialize(plan)
    restored = registry.deserialize(payload)

    assert isinstance(restored, ConstructPlan)
    declaration = restored.api_declaration_demands()[0]
    call = restored.api_call_demands()[0]
    assert isinstance(declaration, APIDeclarationDemand)
    assert isinstance(call, APICallDemand)
    assert declaration.explicit_name_candidates == ["SearchAPI"]
    assert declaration.capability_intent_id == "cap_intent_search"
    assert call.operation_coverage[0].operation_surface == "Retrieve approved sources using SearchAPI."
    assert call.behavior_lowering_policy == "api_call_replaces_behavior"


def _intent_plan(operation: str) -> ExternalCapabilityIntentPlanIR:
    evidence = (
        CapabilityEvidenceIR(
            evidence_id="ev_operation",
            source_span_id="s1",
            claim="operation",
            surface_text=operation,
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_boundary",
            source_span_id="s1",
            claim="boundary",
            surface_text="SearchAPI",
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_identity",
            source_span_id="s1",
            claim="identity",
            surface_text="SearchAPI",
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_invocation",
            source_span_id="s1",
            claim="invocation",
            surface_text=operation,
            relation="direct",
        ),
    )
    intent = ExternalCapabilityIntentIR(
        intent_id="cap_intent_search",
        source_candidate_ids=("candidate_search",),
        source_span_ids=("s1",),
        operation_text=operation,
        capability_surface="SearchAPI",
        capability_ref="SearchAPI",
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
        candidate_resolution_map={"candidate_search": "cap_intent_search"},
    )