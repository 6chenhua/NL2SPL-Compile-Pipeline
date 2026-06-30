from __future__ import annotations

from dataclasses import replace

from nl2spl.compiler.capability_intent.model import (
    CapabilityEvidenceIR,
    ExternalCapabilityIntentIR,
    ExternalCapabilityIntentPlanIR,
)
from nl2spl.compiler.construct_plan import ConstructPlanner
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
    materialize_api_declaration_skeletons,
)


def _intent_plan(*, operation_surface: str, operation_text: str) -> ExternalCapabilityIntentPlanIR:
    evidence = (
        CapabilityEvidenceIR(
            evidence_id="ev_operation",
            source_span_id="s1",
            claim="operation",
            surface_text=operation_surface,
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_boundary",
            source_span_id="s1",
            claim="boundary",
            surface_text="RecordsAPI",
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_identity",
            source_span_id="s1",
            claim="identity",
            surface_text="RecordsAPI",
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_invocation",
            source_span_id="s1",
            claim="invocation",
            surface_text=operation_surface,
            relation="direct",
        ),
    )
    intent = ExternalCapabilityIntentIR(
        intent_id="cap_intent_1",
        source_candidate_ids=("candidate_1",),
        source_span_ids=("s1",),
        operation_text=operation_text,
        capability_surface="RecordsAPI",
        capability_ref="RecordsAPI",
        boundary_status="confirmed_external",
        identity_status="explicit_name",
        invocation_status="executable",
        capability_admission_status="confirmed_capability",
        invocation_admission_status="confirmed_invocation",
        evidence=evidence,
    )
    return ExternalCapabilityIntentPlanIR(
        plan_id="cap_plan_1",
        intents=(intent,),
        candidate_resolution_map={"candidate_1": "cap_intent_1"},
    )


def test_routes_are_not_api_demand_authority() -> None:
    routes = FieldRouteIR(
        integrations=["s1"],
        annotations=[
            RouteAnnotation(
                span_id="s1",
                field="integrations",
                semantic_role="api_candidate",
                construct_target="API_DECLARATION",
                slot_target="source_evidence",
                executable=False,
                metadata={"explicit_api_name": "LegacyAPI"},
            )
        ],
    )

    plan = ConstructPlanner().plan(
        [SpanIR(span_id="s1", text="LegacyAPI")],
        routes,
        source_schema="generic_nl",
    )

    assert plan.api_declaration_demands() == []
    assert plan.api_call_demands() == []
    assert plan.metadata["api_demand_authority"] == "external_capability_intent_plan"


def test_confirmed_final_intent_creates_paired_declaration_and_call() -> None:
    span = SpanIR(span_id="s1", text="retrieve via RecordsAPI")

    plan = ConstructPlanner().plan(
        [span],
        FieldRouteIR(behavior=["s1"], integrations=[]),
        source_schema="generic_nl",
        capability_intent_plan=_intent_plan(
            operation_surface=span.text,
            operation_text=span.text,
        ),
    )

    declaration = plan.api_declaration_demands()[0]
    call = plan.api_call_demands()[0]
    assert declaration.capability_intent_id == "cap_intent_1"
    assert call.capability_intent_id == "cap_intent_1"
    assert call.declaration_demand_id == declaration.demand_id
    assert call.behavior_lowering_policy == "api_call_replaces_behavior"
    assert call.operation_coverage[0].char_start == 0
    assert call.operation_coverage[0].char_end == len(span.text)
    argument_binding = plan.api_call_argument_bindings[0]
    assert argument_binding.call_demand_id == call.demand_id
    assert argument_binding.binding_status == "not_required"


def test_final_intent_bindings_are_projected_one_to_one_to_call_demand() -> None:
    span = SpanIR(span_id="s1", text="retrieve via RecordsAPI")
    base_plan = _intent_plan(operation_surface=span.text, operation_text=span.text)
    bound_intent = replace(
        base_plan.intents[0],
        input_refs=("query",),
        output_refs=("records",),
        binding_status="fully_bound",
    )

    plan = ConstructPlanner().plan(
        [span],
        FieldRouteIR(behavior=["s1"]),
        source_schema="generic_nl",
        capability_intent_plan=replace(base_plan, intents=(bound_intent,)),
    )

    call = plan.api_call_demands()[0]
    assert len(plan.api_call_argument_bindings) == 1
    binding = plan.api_call_argument_bindings[0]
    assert binding.call_demand_id == call.demand_id
    assert binding.input_bindings == {"input_00": "query"}
    assert binding.output_bindings == {"output_00": "records"}
    assert binding.binding_status == "fully_bound"


def test_described_unnamed_final_intent_lowers_to_stage6_bindable_declaration() -> None:
    span = SpanIR(span_id="s1", text="retrieve them using approved source recipes")

    plan = ConstructPlanner().plan(
        [span],
        FieldRouteIR(behavior=["s1"], integrations=[]),
        source_schema="generic_nl",
        capability_intent_plan=_described_unnamed_intent_plan(
            operation_surface=span.text,
            operation_text=span.text,
            capability_surface="approved source recipes",
        ),
    )

    declaration = plan.api_declaration_demands()[0]
    call = plan.api_call_demands()[0]
    assert declaration.explicit_name_candidates == []
    assert declaration.integration_admission == "confirmed"
    assert declaration.mechanism_status == "concrete_unnamed"
    assert declaration.inferred_name_allowed is True
    assert declaration.metadata["operation_text"] == span.text
    assert call.declaration_demand_id == declaration.demand_id

    resources = ResourceRegistryIR()
    materialization = materialize_api_declaration_skeletons(resources, plan)

    assert materialization.unsupported_declaration_demand_ids == []
    assert resources.apis[0].api_name == "ApprovedSourceRecipesAPI"
    assert materialization.bindings[0].declaration_demand_id == declaration.demand_id
    assert materialization.bindings[0].call_demand_ids == [call.demand_id]


def test_same_span_residual_is_explicitly_preserved() -> None:
    span = SpanIR(
        span_id="s1",
        text="retrieve via RecordsAPI and normalize locally",
    )
    plan = ConstructPlanner().plan(
        [span],
        FieldRouteIR(behavior=["s1"]),
        capability_intent_plan=_intent_plan(
            operation_surface="retrieve via RecordsAPI",
            operation_text="retrieve via RecordsAPI",
        ),
    )

    call = plan.api_call_demands()[0]
    assert call.behavior_lowering_policy == "api_call_augments_behavior"
    assert call.consumes_behavior_span_ids == ["s1"]
    assert call.residual_behavior_span_ids == ["s1"]


def test_operation_coverage_allows_whitespace_normalized_source_surface() -> None:
    span = SpanIR(
        span_id="s1",
        text="retrieve them using approved source\nrecipes. Maintain provenance.",
    )
    plan = ConstructPlanner().plan(
        [span],
        FieldRouteIR(behavior=["s1"]),
        capability_intent_plan=_described_unnamed_intent_plan(
            operation_surface="retrieve them using approved source recipes",
            operation_text="retrieve them using approved source recipes",
            capability_surface="approved source recipes",
        ),
    )

    call = plan.api_call_demands()[0]
    assert call.operation_coverage[0].relation == "normalized_whitespace"
    assert call.operation_coverage[0].char_start == 0
    assert call.operation_coverage[0].char_end == len(
        "retrieve them using approved source\nrecipes"
    )
    assert call.behavior_lowering_policy == "api_call_augments_behavior"


def _described_unnamed_intent_plan(
    *,
    operation_surface: str,
    operation_text: str,
    capability_surface: str,
) -> ExternalCapabilityIntentPlanIR:
    evidence = (
        CapabilityEvidenceIR(
            evidence_id="ev_operation",
            source_span_id="s1",
            claim="operation",
            surface_text=operation_surface,
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_boundary",
            source_span_id="s1",
            claim="boundary",
            surface_text=operation_surface,
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_identity",
            source_span_id="s1",
            claim="identity",
            surface_text=capability_surface,
            relation="direct",
        ),
        CapabilityEvidenceIR(
            evidence_id="ev_invocation",
            source_span_id="s1",
            claim="invocation",
            surface_text=operation_surface,
            relation="direct",
        ),
    )
    intent = ExternalCapabilityIntentIR(
        intent_id="cap_intent_unnamed",
        source_candidate_ids=("candidate_unnamed",),
        source_span_ids=("s1",),
        operation_text=operation_text,
        capability_surface=capability_surface,
        capability_ref=None,
        boundary_status="confirmed_external",
        identity_status="described_unnamed",
        invocation_status="executable",
        capability_admission_status="confirmed_capability",
        invocation_admission_status="confirmed_invocation",
        evidence=evidence,
    )
    return ExternalCapabilityIntentPlanIR(
        plan_id="cap_plan_unnamed",
        intents=(intent,),
        candidate_resolution_map={"candidate_unnamed": "cap_intent_unnamed"},
    )
