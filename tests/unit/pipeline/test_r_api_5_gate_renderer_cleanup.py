from __future__ import annotations

import pytest

from nl2spl.compiler.construct_registry import ConstructSatisfactionReport, SlotSatisfaction
from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.structured_text_ir import StructuredTextIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.pipeline.resource_declaration_gate import ResourceDeclarationGate
from nl2spl.pipeline.stages.stage11_spl_renderer.block_renderer import BlockRendererMixin
from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import SPLRenderer


def test_renderer_does_not_fallback_call_api_to_api_name() -> None:
    renderer = BlockRendererMixin()
    renderer._next_command = lambda: "1."  # type: ignore[attr-defined]
    renderer._canonical_command_text = lambda text, condition: text  # type: ignore[attr-defined]
    renderer._description_with_refs = lambda text, inputs: f'"{text}"'  # type: ignore[attr-defined]
    renderer._with_clause = lambda inputs: ""  # type: ignore[attr-defined]
    renderer._result_clause = lambda label, outputs: ""  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="has no integration_ref"):
        renderer._render_step(
            StepIR(
                step_id="st_api_missing",
                text="Call an API.",
                source_span_ids=["s1"],
                command_type="CALL_API",
            )
        )


def test_executable_gate_requires_declared_api_binding_for_source_backed_call_api() -> None:
    worker = WorkerIR(
        worker_name="Agent",
        description="test",
        steps=[
            StepIR(
                step_id="st_raw_call",
                text="Retrieve approved sources using SearchAPI.",
                source_span_ids=["s1"],
                command_type="CALL_API",
                integration_ref="SearchAPI",
            )
        ],
    )

    filtered, render_info, diagnostics = ExecutableElementGate().apply(
        worker,
        renderable_resource_registry_view=_allowed_search_api_view(),
    )

    assert filtered.steps == []
    assert render_info[0].renderable is False
    assert "declared API binding metadata" in (render_info[0].render_block_reason or "")
    assert diagnostics == []


def test_executable_gate_allows_stage7_declared_api_call_metadata() -> None:
    worker = WorkerIR(
        worker_name="Agent",
        description="test",
        steps=[
            StepIR(
                step_id="st_api_call",
                text="Retrieve approved sources using SearchAPI.",
                source_span_ids=["s1"],
                command_type="CALL_API",
                integration_ref="SearchAPI",
                metadata={
                    "origin": "source_backed",
                    "api_id": "api:SearchAPI",
                    "declaration_demand_id": "api_decl_SearchAPI",
                    "api_binding_id": "api_binding:api_decl_SearchAPI",
                    "placement_ref": "api_call_placement:api_call_search",
                },
            )
        ],
    )

    filtered, render_info, diagnostics = ExecutableElementGate().apply(
        worker,
        renderable_resource_registry_view=_allowed_search_api_view(),
    )

    assert [step.step_id for step in filtered.steps] == ["st_api_call"]
    assert render_info[0].renderable is True
    assert diagnostics == []


def test_executable_gate_blocks_call_api_without_gate_approved_declaration() -> None:
    worker = WorkerIR(
        worker_name="Agent",
        description="test",
        steps=[
            StepIR(
                step_id="st_api_call",
                text="Retrieve approved sources using SearchAPI.",
                source_span_ids=["s1"],
                command_type="CALL_API",
                integration_ref="SearchAPI",
                metadata={
                    "origin": "source_backed",
                    "api_id": "api:SearchAPI",
                    "declaration_demand_id": "api_decl_SearchAPI",
                    "api_binding_id": "api_binding:api_decl_SearchAPI",
                    "placement_ref": "api_call_placement:api_call_search",
                },
            )
        ],
    )

    filtered, render_info, diagnostics = ExecutableElementGate().apply(worker)

    assert filtered.steps == []
    assert render_info[0].renderable is False
    assert "ResourceDeclarationGate-approved" in (render_info[0].render_block_reason or "")
    assert diagnostics == []


def test_define_apis_only_renders_gate_approved_apis() -> None:
    raw_resources = ResourceRegistryIR(
        apis=[
            APISpec(
                api_name="SearchAPI",
                auth="none",
                description="Search API",
                source_span_ids=["s_api"],
            )
        ]
    )
    blocked_view = ResourceDeclarationGate().apply(
        raw_resources, [], authority="post_normalize_irs"
    )
    allowed_view = ResourceDeclarationGate().apply(
        raw_resources,
        [
            ConstructSatisfactionReport(
                construct_id="api_declaration:SearchAPI",
                construct_type="API_DECLARATION",
                slots=[
                    SlotSatisfaction("api_name", "satisfied"),
                    SlotSatisfaction("source_evidence", "satisfied"),
                ],
                completeness="partial",
                renderable=True,
                metadata={
                    "api_name": "SearchAPI",
                    "grammar_validation_status": "grammar_minimal_partial",
                    "grammar_valid": True,
                    "authority": "post_normalize_irs",
                },
            )
        ],
        authority="post_normalize_irs",
    )

    worker = WorkerIR(worker_name="Agent", description="test")
    renderer = SPLRenderer()

    blocked_spl, _, _ = renderer.render(
        worker,
        AgentProfileIR(),
        blocked_view,
        SymbolTable(),
        [],
        [],
    )
    allowed_spl, _, _ = renderer.render(
        worker,
        AgentProfileIR(),
        allowed_view,
        SymbolTable(),
        [],
        [],
    )

    assert "[DEFINE_APIS:]" not in blocked_spl
    assert "[DEFINE_APIS:]" in allowed_spl
    assert "SearchAPI" in allowed_spl


def test_renderer_consumes_apispec_schema_without_fabricating_placeholder() -> None:
    resources = ResourceRegistryIR(
        apis=[
            APISpec(
                api_id="api:SearchAPI",
                api_name="SearchAPI",
                auth="oauth2",
                description="Search API",
                openapi_schema=StructuredTextIR(
                    format="json_object",
                    canonical_text='{"openapi":"3.0.0","paths":{"/search":{}}}',
                ),
            )
        ]
    )

    spl, errors, _warnings = SPLRenderer().render(
        WorkerIR(worker_name="Agent", description="test"),
        AgentProfileIR(),
        resources,
        SymbolTable(),
        [],
        [],
    )

    assert errors == []
    assert "SearchAPI <oauth2>" in spl
    assert '{"openapi":"3.0.0","paths":{"/search":{}}}' in spl


def _allowed_search_api_view():
    raw_resources = ResourceRegistryIR(
        apis=[
            APISpec(
                api_id="api:SearchAPI",
                api_name="SearchAPI",
                auth="none",
                description="Search API",
                source_span_ids=["s_api"],
                declaration_status="grammar_minimal_partial",
            )
        ]
    )
    return ResourceDeclarationGate().apply(
        raw_resources,
        [
            ConstructSatisfactionReport(
                construct_id="api_declaration:SearchAPI",
                construct_type="API_DECLARATION",
                slots=[
                    SlotSatisfaction("api_name", "satisfied"),
                    SlotSatisfaction("source_evidence", "satisfied"),
                ],
                completeness="partial",
                renderable=True,
                metadata={
                    "api_id": "api:SearchAPI",
                    "api_name": "SearchAPI",
                    "grammar_validation_status": "grammar_minimal_partial",
                    "grammar_valid": True,
                    "authority": "post_normalize_irs",
                },
            )
        ],
        authority="post_normalize_irs",
    )
