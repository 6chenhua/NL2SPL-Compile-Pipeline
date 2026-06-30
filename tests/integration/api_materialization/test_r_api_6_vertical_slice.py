from __future__ import annotations

from nl2spl.compiler.construct_plan import (
    APICallArgumentBindingIR,
    APICallDemand,
    APICallPlacementIR,
    APIDeclarationDemand,
    ConstructPlan,
    OperationCoverageIR,
)
from nl2spl.compiler.irs.factory import build_irs_subsystem
from nl2spl.compiler.irs.policy import IRSRuntimeConfig
from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import FlowRef, WorkerIR
from nl2spl.ir.worker_plan_ir import WorkerHandoffIR, WorkerPlanIR, WorkerStepPlanIR
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.pipeline.provenance import ProvenanceAggregator
from nl2spl.pipeline.resource_declaration_gate import ResourceDeclarationGate
from nl2spl.pipeline.stages.stage6_resource_extractor.api_contract_extraction import (
    api_spec_from_extracted_contract,
)
from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
    materialize_api_declaration_skeletons,
)
from nl2spl.pipeline.stages.stage7_step_extractor.api_call_materializer import (
    materialize_direct_api_calls,
)
from nl2spl.pipeline.stages.stage11_spl_renderer import SPLRenderer


def test_expected_correct_search_api_vertical_slice_renders_approved_placeholder_and_call() -> None:
    """AP-1 Baseline: Verify that approved placeholders are rendered in SPL
    together with CALL statements.
    """
    construct_plan = _construct_plan()
    resources = ResourceRegistryIR()
    api_plan = materialize_api_declaration_skeletons(resources, construct_plan)
    worker_steps = WorkerStepPlanIR(main_worker_id="worker_main")

    stage7_warnings = materialize_direct_api_calls(
        worker_steps,
        construct_plan,
        api_plan,
        [_placement()],
        resources,
    )
    worker = _worker(worker_steps.worker_steps["worker_main"][0])

    irs = build_irs_subsystem(IRSRuntimeConfig())
    api_decl_result = irs.run_post_normalize_result(
        worker=None,
        resources=resources,
    )
    renderable_resources = ResourceDeclarationGate().apply(
        resources,
        api_decl_result.reports,
    )
    worker, _render_info, gate_diags = ExecutableElementGate().apply(
        worker,
        renderable_resource_registry_view=renderable_resources,
    )
    worker.scoped_steps = True
    _ = irs.run_post_normalize_result(
        worker=worker,
        resources=renderable_resources,
        renderable_resource_registry_view=renderable_resources,
    )
    spl, errors, _warnings = SPLRenderer().render(
        worker,
        AgentProfileIR(),
        renderable_resources,
        SymbolTable(),
        worker.steps,
        [],
    )
    traces, provenance_diags = ProvenanceAggregator().aggregate(
        worker=worker,
        steps=list(worker.steps),
        constraints=[],
        resources=renderable_resources,
        symbol_table=SymbolTable(),
        spans=[
            SpanIR("s1", "SearchAPI", source_section_id="sec_api"),
            SpanIR(
                "s2",
                "Retrieve approved sources using SearchAPI.",
                source_section_id="sec_steps",
            ),
        ],
        declared_apis=renderable_resources.api_names,
    )

    assert stage7_warnings == []
    assert gate_diags == []
    assert errors == []
    assert "[DEFINE_APIS:]" in spl
    assert "[CALL SearchAPI]" in spl
    assert "{}" in spl
    assert '{"functions":[]}' in spl
    assert len(renderable_resources.apis) == 1
    api = resources.apis[0]
    assert api.declaration_status == "grammar_minimal_partial"
    assert api.schema_status == "unknown_placeholder"
    assert api.functions_status == "unknown_placeholder"


def test_expected_correct_search_api_vertical_slice_blocks_unapproved_partial_contract() -> None:
    """AP-1 Baseline: Verify that unapproved (partial_blocked) API contracts
    are rejected and not rendered.
    """
    construct_plan = _construct_plan()
    worker_steps = WorkerStepPlanIR(main_worker_id="worker_main")

    # Use production extractor to generate an API spec with default
    # declaration_status="partial_blocked"
    extracted_api = api_spec_from_extracted_contract(
        {
            "api_name": "SearchAPI",
            "auth": "none",
            "description": "Partial API declaration skeleton for SearchAPI.",
            "source_span_ids": ["s1"],
            "functions": [],
            "openapi_schema": {"format": "empty_placeholder", "canonical_text": "{}"},
        },
        valid_source_span_ids=["s1"],
    )
    resources = ResourceRegistryIR(apis=[extracted_api])

    # Materialize bindings/skeletons normally
    api_plan = materialize_api_declaration_skeletons(resources, construct_plan)

    stage7_warnings = materialize_direct_api_calls(
        worker_steps,
        construct_plan,
        api_plan,
        [_placement()],
        resources,
    )
    worker = _worker(worker_steps.worker_steps["worker_main"][0])

    irs = build_irs_subsystem(IRSRuntimeConfig())
    api_decl_result = irs.run_post_normalize_result(
        worker=None,
        resources=resources,
    )
    renderable_resources = ResourceDeclarationGate().apply(
        resources,
        api_decl_result.reports,
    )
    worker, _render_info, gate_diags = ExecutableElementGate().apply(
        worker,
        renderable_resource_registry_view=renderable_resources,
    )
    worker.scoped_steps = True
    post_result = irs.run_post_normalize_result(
        worker=worker,
        resources=renderable_resources,
        renderable_resource_registry_view=renderable_resources,
    )
    spl, errors, _warnings = SPLRenderer().render(
        worker,
        AgentProfileIR(),
        renderable_resources,
        SymbolTable(),
        worker.steps,
        [],
    )
    traces, provenance_diags = ProvenanceAggregator().aggregate(
        worker=worker,
        steps=list(worker.steps),
        constraints=[],
        resources=renderable_resources,
        symbol_table=SymbolTable(),
        spans=[
            SpanIR("s1", "SearchAPI", source_section_id="sec_api"),
            SpanIR(
                "s2",
                "Retrieve approved sources using SearchAPI.",
                source_section_id="sec_steps",
            ),
        ],
        declared_apis=renderable_resources.api_names,
    )

    assert stage7_warnings == []
    assert gate_diags == []
    assert errors == []
    assert "[DEFINE_APIS:]" not in spl
    assert "[CALL SearchAPI]" not in spl
    assert renderable_resources.apis == []
    api = resources.apis[0]
    assert api.declaration_status == "partial_blocked"
    assert api.schema_status == "unknown_placeholder"
    assert api.functions_status == "unknown_placeholder"

    api_diags = [
        diagnostic
        for diagnostic in api_decl_result.diagnostics
        if diagnostic.target_ref == "api_declaration:api:SearchAPI"
    ]
    assert {d.missing_slot.slot_name for d in api_diags if d.missing_slot} == {
        "openapi_schema",
        "functions",
    }
    assert all(d.blocks_rendering is True for d in api_diags)
    assert all(d.blocks_completion is True for d in api_diags)
    assert all(d.metadata["irs_ref"]["source_authority"] == "post_normalize_irs" for d in api_diags)
    assert not [
        diagnostic
        for diagnostic in post_result.diagnostics
        if diagnostic.missing_slot and diagnostic.missing_slot.slot_name == "api_name"
    ]

    assert not [
        trace
        for trace in traces
        if trace.target_ref.startswith("api:") or trace.metadata.get("api_id") == "api:SearchAPI"
    ]
    assert provenance_diags == []


def test_expected_correct_weather_api_blocked_without_placeholder_approval() -> None:
    """AP-1 Baseline: Verify that another unapproved (partial_blocked) API
    is also blocked.
    """
    construct_plan = _construct_plan(api_name="WeatherAPI", api_group_id="weather")
    worker_steps = WorkerStepPlanIR(main_worker_id="worker_main")

    extracted_api = api_spec_from_extracted_contract(
        {
            "api_name": "WeatherAPI",
            "auth": "none",
            "description": "Weather API",
            "source_span_ids": ["s1"],
            "functions": [],
            "openapi_schema": {"format": "empty_placeholder", "canonical_text": "{}"},
        },
        valid_source_span_ids=["s1"],
    )
    resources = ResourceRegistryIR(apis=[extracted_api])
    api_plan = materialize_api_declaration_skeletons(resources, construct_plan)

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        construct_plan,
        api_plan,
        [_placement(call_demand_id="api_call_weather")],
        resources,
    )
    worker = _worker(worker_steps.worker_steps["worker_main"][0])
    irs = build_irs_subsystem(IRSRuntimeConfig())
    api_decl_result = irs.run_post_normalize_result(worker=None, resources=resources)
    renderable_resources = ResourceDeclarationGate().apply(
        resources,
        api_decl_result.reports,
    )
    worker, _render_info, gate_diags = ExecutableElementGate().apply(
        worker,
        renderable_resource_registry_view=renderable_resources,
    )
    worker.scoped_steps = True
    spl, errors, _warnings = SPLRenderer().render(
        worker,
        AgentProfileIR(),
        renderable_resources,
        SymbolTable(),
        worker.steps,
        [],
    )

    assert diagnostics == []
    assert gate_diags == []
    assert errors == []
    assert resources.apis[0].api_name == "WeatherAPI"
    assert resources.apis[0].declaration_status == "partial_blocked"
    assert "[DEFINE_APIS:]" not in spl
    assert "[CALL WeatherAPI]" not in spl


def test_expected_correct_undeclared_call_api_reports_context_diagnostic() -> None:
    worker = _worker(
        StepIR(
            step_id="st_ghost_api",
            text="Call GhostAPI.",
            source_span_ids=["s2"],
            command_type="CALL_API",
            integration_ref="GhostAPI",
            flow_ref="main",
            block_ref="block_main",
            metadata={
                "origin": "source_backed",
                "api_id": "api:GhostAPI",
                "declaration_demand_id": "api_decl_GhostAPI",
                "api_binding_id": "api_binding:api_decl_GhostAPI",
                "placement_ref": "api_call_placement:api_call_ghost",
            },
        )
    )

    result = build_irs_subsystem(IRSRuntimeConfig()).run_post_normalize_result(
        worker=worker,
        resources=ResourceRegistryIR(),
    )

    api_name_diags = [
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.target_ref == "step:st_ghost_api"
        and diagnostic.missing_slot
        and diagnostic.missing_slot.slot_name == "api_name"
    ]
    assert len(api_name_diags) == 1
    assert api_name_diags[0].kind == "type_or_contract_ambiguity"
    assert "undeclared API 'GhostAPI'" in api_name_diags[0].message
    assert api_name_diags[0].metadata["irs_ref"]["source_authority"] == "post_normalize_irs"


def test_expected_correct_raw_registry_api_without_gate_view_does_not_satisfy_call_api() -> None:
    worker = _worker(
        StepIR(
            step_id="st_raw_registry_api",
            text="Call SearchAPI.",
            source_span_ids=["s2"],
            command_type="CALL_API",
            integration_ref="SearchAPI",
            flow_ref="main",
            block_ref="block_main",
            metadata={
                "origin": "source_backed",
                "api_id": "api:SearchAPI",
                "declaration_demand_id": "api_decl_SearchAPI",
                "api_binding_id": "api_binding:api_decl_SearchAPI",
                "placement_ref": "api_call_placement:api_call_search",
            },
        )
    )
    raw_resources = ResourceRegistryIR(
        apis=[
            materialize_api_declaration_skeletons(
                ResourceRegistryIR(),
                _construct_plan(),
            ).api_specs[0]
        ]
    )

    result = build_irs_subsystem(IRSRuntimeConfig()).run_post_normalize_result(
        worker=worker,
        resources=raw_resources,
    )

    assert [
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.target_ref == "step:st_raw_registry_api"
        and diagnostic.missing_slot
        and diagnostic.missing_slot.slot_name == "api_name"
    ]


def test_expected_correct_direct_call_api_is_not_declared_by_handoff_extra_api_name() -> None:
    worker = _worker(
        StepIR(
            step_id="st_direct_search_api",
            text="Call SearchAPI.",
            source_span_ids=["s2"],
            command_type="CALL_API",
            integration_ref="SearchAPI",
            flow_ref="main",
            block_ref="block_main",
            metadata={
                "origin": "source_backed",
                "api_id": "api:SearchAPI",
                "declaration_demand_id": "api_decl_SearchAPI",
                "api_binding_id": "api_binding:api_decl_SearchAPI",
                "placement_ref": "api_call_placement:api_call_search",
            },
        )
    )
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        handoffs=[
            WorkerHandoffIR(
                handoff_id="h_api",
                from_worker="worker_main",
                to_worker=None,
                api_ref="SearchAPI",
                mode="api_call",
                condition_text=None,
                ordering="after",
            )
        ],
    )

    result = build_irs_subsystem(IRSRuntimeConfig()).run_post_normalize_result(
        worker=worker,
        worker_plan=worker_plan,
        resources=ResourceRegistryIR(),
    )

    assert [
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.target_ref
        and diagnostic.target_ref.endswith("step:st_direct_search_api")
        and diagnostic.missing_slot
        and diagnostic.missing_slot.slot_name == "api_name"
    ]


def _construct_plan(
    *,
    api_name: str = "SearchAPI",
    api_group_id: str = "search",
) -> ConstructPlan:
    declaration_id = f"api_decl_{api_name}"
    call_id = f"api_call_{api_group_id}"
    return ConstructPlan(
        plan_id="cp",
        api_call_argument_bindings=[
            APICallArgumentBindingIR(
                call_demand_id=call_id,
                binding_status="not_required",
                source_span_ids=("s2",),
            )
        ],
        demands=[
            APIDeclarationDemand(
                demand_id=declaration_id,
                source_span_ids=["s1"],
                declaration_annotation_ids=["ann_api_decl"],
                explicit_name_candidates=[api_name],
                integration_admission="confirmed",
                mechanism_status="explicit",
                api_group_id=api_group_id,
            ),
            APICallDemand(
                demand_id=call_id,
                source_span_ids=["s2"],
                call_annotation_ids=["ann_api_call"],
                declaration_demand_id=declaration_id,
                api_group_id=api_group_id,
                action_text=f"Retrieve approved sources using {api_name}.",
                operation_coverage=[
                    OperationCoverageIR(
                        coverage_id=f"cov_{api_group_id}",
                        source_span_id="s2",
                        operation_surface=f"Retrieve approved sources using {api_name}.",
                        char_start=0,
                        char_end=len(f"Retrieve approved sources using {api_name}."),
                    )
                ],
                consumes_behavior_span_ids=["s2"],
                behavior_lowering_policy="api_call_replaces_behavior",
            ),
        ],
    )


def _placement(call_demand_id: str = "api_call_search") -> APICallPlacementIR:
    return APICallPlacementIR(
        call_demand_id=call_demand_id,
        owner_worker_id="worker_main",
        flow_ref="main",
        block_ref="block_main",
        status="placed",
        source_span_ids=["s2"],
    )


def _worker(step: StepIR) -> WorkerIR:
    return WorkerIR(
        worker_name="worker_main",
        description="test worker",
        steps=[step],
        main_flow=FlowRef(blocks=[BlockIR("block_main", "SEQUENTIAL", spans=["s2"])]),
        scoped_steps=True,
    )
