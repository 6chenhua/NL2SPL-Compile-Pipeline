from nl2spl.compiler.construct_registry import (
    ConstructSatisfactionReport,
    SlotSatisfaction,
)
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR
from nl2spl.pipeline.resource_declaration_gate import ResourceDeclarationGate


def _api_report(
    *,
    api_name: str = "SearchAPI",
    api_id: str = "api:SearchAPI",
    api_name_status: str = "satisfied",
    source_status: str = "satisfied",
    completeness: str = "partial",
    renderable: bool = True,
    grammar_status: str = "grammar_minimal_partial",
    grammar_valid: bool = True,
    authority: str = "post_normalize_irs",
) -> ConstructSatisfactionReport:
    return ConstructSatisfactionReport(
        construct_id=f"api_declaration:{api_id}",
        construct_type="API_DECLARATION",
        slots=[
            SlotSatisfaction("api_name", api_name_status),
            SlotSatisfaction("source_evidence", source_status),
            SlotSatisfaction("authentication", "assumed"),
            SlotSatisfaction("openapi_schema", "missing"),
            SlotSatisfaction("functions", "missing"),
        ],
        completeness=completeness,
        renderable=renderable,
        construct_path=("resources", "apis", api_id),
        source_span_ids=["s_api"],
        frontier_status="cutline_partial",
        cutline_reason="incomplete_api_declaration_contract",
        metadata={
            "api_id": api_id,
            "api_name": api_name,
            "grammar_validation_status": grammar_status,
            "grammar_valid": grammar_valid,
            "authority": authority,
        },
    )


def test_expected_correct_post_normalize_report_allows_approved_grammar_minimal_partial() -> None:
    api = APISpec(
        api_name="SearchAPI",
        auth="none",
        description="Search API",
        source_span_ids=["s_api"],
        declaration_status="grammar_minimal_partial",
        schema_status="unknown_placeholder",
        functions_status="unknown_placeholder",
    )
    resources = ResourceRegistryIR(apis=[api])

    view = ResourceDeclarationGate().apply(resources, [_api_report()])

    assert view.apis == [api]
    assert view.api_names == {"SearchAPI"}
    assert view.incomplete_api_names == {"SearchAPI"}
    assert view.blocked_api_names == set()
    assert resources.apis == [api]


def test_expected_correct_unapproved_partial_blocked_even_if_renderable() -> None:
    api = APISpec(
        api_name="SearchAPI",
        auth="none",
        description="Search API",
        source_span_ids=["s_api"],
        declaration_status="partial_blocked",
    )

    view = ResourceDeclarationGate().apply(
        ResourceRegistryIR(apis=[api]),
        [_api_report(grammar_status="partial_blocked")],
    )

    assert view.apis == []
    assert view.blocked_api_names == {"SearchAPI"}


def test_expected_correct_stage_local_report_cannot_render_api() -> None:
    api = APISpec(
        api_name="SearchAPI",
        auth="none",
        description="Search API",
        source_span_ids=["s_api"],
    )
    resources = ResourceRegistryIR(apis=[api])

    view = ResourceDeclarationGate().apply(
        resources,
        [_api_report(authority="stage_local_irs")],
        authority="stage_local_irs",
    )

    assert view.apis == []
    assert view.api_names == set()
    assert "SearchAPI" not in view.to_payload()["api_names"]


def test_expected_correct_default_call_rejects_report_with_stage_local_provenance() -> None:
    resources = ResourceRegistryIR(
        apis=[
            APISpec(
                api_name="SearchAPI",
                auth="none",
                description="Search API",
                source_span_ids=["s_api"],
                declaration_status="grammar_minimal_partial",
            )
        ]
    )

    view = ResourceDeclarationGate().apply(
        resources,
        [_api_report(authority="stage_local_irs")],
    )

    assert view.apis == []
    assert view.blocked_api_names == {"SearchAPI"}


def test_expected_correct_missing_api_name_or_source_evidence_blocks_render() -> None:
    api = APISpec(
        api_name="SearchAPI",
        auth="none",
        description="Search API",
        source_span_ids=[],
    )
    resources = ResourceRegistryIR(apis=[api])

    missing_source = ResourceDeclarationGate().apply(
        resources,
        [_api_report(source_status="missing", renderable=False)],
    )
    missing_name = ResourceDeclarationGate().apply(
        resources,
        [_api_report(api_name_status="missing", renderable=False)],
    )

    assert missing_source.apis == []
    assert missing_source.blocked_api_names == {"SearchAPI"}
    assert missing_name.apis == []
    assert missing_name.blocked_api_names == {"SearchAPI"}
