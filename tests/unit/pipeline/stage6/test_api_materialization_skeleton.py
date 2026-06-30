from __future__ import annotations

from nl2spl.compiler.construct_plan import (
    APICallDemand,
    APIDeclarationDemand,
    ConstructPlan,
    ConstructSlotDemand,
)
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR
from nl2spl.pipeline.stages.stage6_resource_extractor.api_contract_extraction import (
    AUTH_EVIDENCE_AUTHORITY,
    api_spec_from_extracted_contract,
)
from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
    APIMaterializationPlanIR,
    materialize_api_declaration_skeletons,
)


def test_expected_correct_search_api_declaration_materializes_partial_api_spec_skeleton() -> None:
    declaration = _declaration("SearchAPI")
    call = APICallDemand(
        demand_id="api_call_1",
        declaration_demand_id=declaration.demand_id,
        api_group_id="search",
        slots={
            "call_action": ConstructSlotDemand(
                slot_name="call_action",
                source_span_ids=["s2"],
            )
        },
        source_span_ids=["s2"],
    )
    plan = ConstructPlan(plan_id="cp", demands=[declaration, call])
    resources = ResourceRegistryIR()

    materialization = materialize_api_declaration_skeletons(resources, plan)

    assert isinstance(materialization, APIMaterializationPlanIR)
    assert len(resources.apis) == 1
    api = resources.apis[0]
    assert api.api_id == "api:SearchAPI"
    assert api.api_name == "SearchAPI"
    assert api.auth == "none"
    assert api.auth_status == "compiler_default_none"
    assert api.openapi_schema.format == "empty_placeholder"
    assert api.openapi_schema.canonical_text == "{}"
    assert api.schema_status == "unknown_placeholder"
    assert api.functions == []
    assert api.functions_status == "unknown_placeholder"
    assert api.declaration_status == "grammar_minimal_partial"
    assert api.source_span_ids == ["s1"]
    assert api.source_annotation_ids == ["ann_decl_SearchAPI"]
    assert api.declaration_demand_ids == ["api_decl_SearchAPI"]
    assert materialization.bindings[0].api_id == "api:SearchAPI"
    assert materialization.bindings[0].declaration_demand_id == "api_decl_SearchAPI"
    assert materialization.bindings[0].call_demand_ids == ["api_call_1"]
    assert materialization.records[0].declaration_demand_id == "api_decl_SearchAPI"
    assert materialization.records[0].auth_status == "defaulted_none"
    assert materialization.records[0].renderability_status == "requires_post_normalize_gate"


def test_expected_correct_materialization_payload_is_deterministic_and_stage_local_only() -> None:
    plan = ConstructPlan(plan_id="cp", demands=[_declaration("SearchAPI")])
    materialization = materialize_api_declaration_skeletons(
        ResourceRegistryIR(),
        plan,
    )

    payload = materialization.to_payload()

    assert payload["plan_id"] == "api_materialization_plan_00"
    assert payload["metadata"] == {
        "authority": "api_declaration_materializer",
        "name_resolver": "CapabilityNameResolverV1",
        "stage": "stage6_resource_extractor",
        "identity_diagnostics": [],
    }
    assert payload["api_specs"][0]["declaration_status"] == "grammar_minimal_partial"
    assert payload["api_specs"][0]["auth_status"] == "compiler_default_none"
    assert payload["api_specs"][0]["schema_status"] == "unknown_placeholder"
    assert payload["api_specs"][0]["functions_status"] == "unknown_placeholder"


def test_expected_correct_non_search_explicit_declaration_materializes_partial_api_spec() -> None:
    resources = ResourceRegistryIR()
    declaration = _declaration("WeatherAPI")
    plan = ConstructPlan(plan_id="cp", demands=[declaration])

    materialization = materialize_api_declaration_skeletons(resources, plan)

    assert resources.apis[0].api_id == "api:WeatherAPI"
    assert resources.apis[0].api_name == "WeatherAPI"
    assert resources.apis[0].declaration_status == "grammar_minimal_partial"
    assert materialization.bindings[0].api_name == "WeatherAPI"
    assert materialization.unsupported_declaration_demand_ids == []


def test_expected_correct_explicit_auth_requirement_with_unknown_type_stays_unresolved() -> None:
    declaration = _declaration("SecureAPI")
    extracted = api_spec_from_extracted_contract(
        {
            "api_name": "SecureAPI",
            "auth": "unresolved",
            "authentication_status": "unresolved",
            "source_span_ids": ["s1"],
            "authentication_source_span_ids": ["s1"],
        },
        valid_source_span_ids={"s1"},
    )
    resources = ResourceRegistryIR(apis=[extracted])

    materialization = materialize_api_declaration_skeletons(
        resources,
        ConstructPlan(plan_id="cp", demands=[declaration]),
    )

    api = resources.apis[0]
    assert api.auth == "unresolved"
    assert api.auth_status == "unresolved"
    assert api.auth_evidence_authority == AUTH_EVIDENCE_AUTHORITY
    assert api.source_span_ids == ["s1"]
    assert api.auth_source_span_ids == ["s1"]
    assert api.declaration_status == "partial_blocked"
    assert materialization.records[0].auth_status == "unresolved"


def test_expected_correct_existing_legacy_id_is_canonicalized_and_not_duplicated_by_name() -> None:
    existing = APISpec(
        api_id="SearchAPI",
        api_name="SearchAPI",
        auth="none",
        description="Existing contract",
        source_span_ids=["legacy_span"],
    )
    resources = ResourceRegistryIR(apis=[existing])

    materialization = materialize_api_declaration_skeletons(
        resources,
        ConstructPlan(plan_id="cp", demands=[_declaration("SearchAPI")]),
    )

    assert resources.apis == [existing]
    assert existing.api_id == "api:SearchAPI"
    assert existing.source_span_ids == ["legacy_span", "s1"]
    assert materialization.bindings[0].api_id == "api:SearchAPI"
    assert materialization.metadata["identity_diagnostics"] == [
        "normalized_api_id:SearchAPI->api:SearchAPI"
    ]


def test_expected_correct_described_unnamed_declaration_materializes_inferred_api_name() -> None:
    resources = ResourceRegistryIR()
    declaration = APIDeclarationDemand(
        demand_id="api_decl_capability",
        source_span_ids=["s1"],
        declaration_annotation_ids=["ann_decl_capability"],
        explicit_name_candidates=[],
        integration_admission="confirmed",
        mechanism_status="concrete_unnamed",
        inferred_name_allowed=True,
        capability_intent_id="cap_intent_lookup",
        capability_surface="approved source lookup",
    )
    plan = ConstructPlan(plan_id="cp", demands=[declaration])

    materialization = materialize_api_declaration_skeletons(resources, plan)

    assert resources.apis[0].api_name == "ApprovedSourceLookupAPI"
    assert resources.apis[0].name_status == "inferred_from_source"
    assert materialization.bindings[0].api_name == "ApprovedSourceLookupAPI"
    assert materialization.records[0].name_status == "inferred_from_source"
    assert materialization.unsupported_declaration_demand_ids == []


def test_expected_correct_non_explicit_or_invalid_declaration_does_not_create_api_spec() -> None:
    resources = ResourceRegistryIR()
    invalid = _declaration("approved-source-recipes")
    candidate = _declaration("SearchAPI")
    candidate.integration_admission = "candidate"
    candidate.mechanism_status = "unknown"
    plan = ConstructPlan(plan_id="cp", demands=[invalid, candidate])

    materialization = materialize_api_declaration_skeletons(resources, plan)

    assert resources.apis == []
    assert materialization.bindings == []
    assert materialization.unsupported_declaration_demand_ids == [
        "api_decl_approved-source-recipes",
        "api_decl_SearchAPI",
    ]


def _declaration(name: str) -> APIDeclarationDemand:
    return APIDeclarationDemand(
        demand_id=f"api_decl_{name}",
        slots={
            "source_evidence": ConstructSlotDemand(
                slot_name="source_evidence",
                source_span_ids=["s1"],
            )
        },
        source_span_ids=["s1"],
        declaration_annotation_ids=[f"ann_decl_{name}"],
        explicit_name_candidates=[name],
        integration_admission="confirmed",
        mechanism_status="explicit",
        api_group_id="search",
    )
