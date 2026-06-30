from __future__ import annotations

from nl2spl.compiler.construct_plan import (
    APICallArgumentBindingIR,
    APICallDemand,
    APICallPlacementIR,
    APIDeclarationDemand,
    ConstructPlan,
    OperationCoverageIR,
)
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR
from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
    APICallBindingIR,
    APIMaterializationPlanIR,
)
from nl2spl.pipeline.stages.stage7_step_extractor.api_call_materializer import (
    materialize_direct_api_calls,
)


def test_expected_correct_bound_placed_declared_api_materializes_direct_call_api_step() -> None:
    worker_steps = WorkerStepPlanIR(main_worker_id="worker_main")
    diagnostics = materialize_direct_api_calls(
        worker_steps,
        _construct_plan(),
        _api_plan(),
        [_placement("placed")],
        _resources(),
    )

    assert diagnostics == []
    step = worker_steps.worker_steps["worker_main"][0]
    assert step.command_type == "CALL_API"
    assert step.integration_ref == "SearchAPI"
    assert step.inputs == []
    assert step.outputs == []
    assert step.flow_ref == "main"
    assert step.block_ref == "block_main"
    assert step.metadata["origin"] == "source_backed"
    assert step.metadata["construct_demand_ids"] == ["api_call_search"]
    assert step.metadata["api_id"] == "api:SearchAPI"
    assert step.metadata["declaration_demand_id"] == "api_decl_SearchAPI"
    assert step.metadata["api_binding_id"] == "api_binding:api_decl_SearchAPI"
    assert step.metadata["placement_ref"] == "api_call_placement:api_call_search"


def test_expected_correct_unresolved_binding_or_placement_generates_no_call_api_step() -> None:
    worker_steps = WorkerStepPlanIR(main_worker_id="worker_main")
    binding_diags = materialize_direct_api_calls(
        worker_steps,
        _construct_plan(declaration_demand_id=None),
        _api_plan(),
        [_placement("placed")],
        _resources(),
    )
    placement_diags = materialize_direct_api_calls(
        worker_steps,
        _construct_plan(),
        _api_plan(),
        [_placement("unresolved")],
        _resources(),
    )

    assert worker_steps.worker_steps == {}
    assert binding_diags[0].kind == "stage7_unresolved_api_call_materialization"
    assert binding_diags[0].metadata["reason"] == "binding_not_resolved"
    assert placement_diags[0].kind == "stage7_unresolved_api_call_materialization"
    assert placement_diags[0].metadata["reason"] == "placement_unresolved"


def test_expected_correct_missing_argument_binding_artifact_blocks_call_api_step() -> None:
    worker_steps = WorkerStepPlanIR(main_worker_id="worker_main")
    plan = _construct_plan()
    plan.api_call_argument_bindings = []

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        plan,
        _api_plan(),
        [_placement("placed")],
        _resources(),
    )

    assert worker_steps.worker_steps == {}
    assert diagnostics[0].metadata["reason"] == "argument_binding_missing"


def test_expected_correct_incomplete_placed_record_does_not_fallback_to_main_worker() -> None:
    worker_steps = WorkerStepPlanIR(main_worker_id="worker_main")
    incomplete = APICallPlacementIR(
        call_demand_id="api_call_search",
        status="placed",
        source_span_ids=["s2"],
    )

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        _construct_plan(),
        _api_plan(),
        [incomplete],
        _resources(),
    )

    assert worker_steps.worker_steps == {}
    assert diagnostics[0].metadata["reason"] == "placement_incomplete"
    assert diagnostics[0].metadata["detail"] == "owner_worker_id, flow_ref, block_ref"


def test_expected_correct_missing_coverage_offsets_preserves_command_and_blocks_call() -> None:
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_mixed",
                    text="Retrieve via SearchAPI and preserve provenance.",
                    source_span_ids=["s2"],
                    command_type="GENERAL_COMMAND",
                )
            ]
        },
    )
    plan = _construct_plan()
    call = plan.api_call_demands()[0]
    call.operation_coverage = [
        OperationCoverageIR(
            coverage_id="cov_missing_offsets",
            source_span_id="s2",
            operation_surface="Retrieve via SearchAPI",
        )
    ]
    call.behavior_lowering_policy = "api_call_augments_behavior"

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        plan,
        _api_plan(),
        [_placement("placed")],
        _resources(),
    )

    assert [step.step_id for step in worker_steps.worker_steps["worker_main"]] == ["st_mixed"]
    assert worker_steps.worker_steps["worker_main"][0].text == (
        "Retrieve via SearchAPI and preserve provenance."
    )
    assert diagnostics[0].metadata["reason"] == "operation_coverage_ambiguous"
    assert diagnostics[0].metadata["detail"] == ("coverage_offsets_missing:cov_missing_offsets")


def test_expected_correct_same_demand_general_command_fallback_is_removed_with_warning() -> None:
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_llm_fallback",
                    text="Retrieve approved sources using SearchAPI.",
                    source_span_ids=["s2"],
                    command_type="GENERAL_COMMAND",
                    metadata={"construct_demand_ids": ["api_call_search"]},
                )
            ]
        },
    )

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        _construct_plan(),
        _api_plan(),
        [_placement("placed")],
        _resources(),
    )

    steps = worker_steps.worker_steps["worker_main"]
    assert [step.command_type for step in steps] == ["CALL_API"]
    assert len(diagnostics) == 1
    warning = diagnostics[0]
    assert warning.kind == "stage7_sanitized_general_command_fallback"
    assert warning.target_ref == "api_call_demand:api_call_search"
    assert warning.blocks_rendering is False
    assert warning.blocks_completion is False


def test_expected_correct_same_span_non_api_general_command_is_preserved() -> None:
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_preserve_provenance",
                    text="Preserve provenance.",
                    source_span_ids=["s2"],
                    command_type="GENERAL_COMMAND",
                )
            ]
        },
    )

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        _construct_plan(),
        _api_plan(),
        [_placement("placed")],
        _resources(),
    )

    steps = worker_steps.worker_steps["worker_main"]
    assert diagnostics == []
    assert [step.step_id for step in steps] == [
        "st_preserve_provenance",
        "st_api_bfb7b2b753",
    ]
    assert [step.command_type for step in steps] == [
        "GENERAL_COMMAND",
        "CALL_API",
    ]


def test_expected_correct_same_span_residual_general_command_is_trimmed() -> None:
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_residual",
                    text="Retrieve approved sources using SearchAPI and preserve provenance.",
                    source_span_ids=["s2"],
                    command_type="GENERAL_COMMAND",
                )
            ]
        },
    )
    plan = _construct_plan()
    call = plan.api_call_demands()[0]
    call.operation_coverage = [
        OperationCoverageIR(
            coverage_id="cov_search",
            source_span_id="s2",
            operation_surface="Retrieve approved sources using SearchAPI",
            char_start=0,
            char_end=len("Retrieve approved sources using SearchAPI"),
        )
    ]
    call.behavior_lowering_policy = "api_call_augments_behavior"
    call.residual_behavior_span_ids = ["s2"]

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        plan,
        _api_plan(),
        [_placement("placed")],
        _resources(),
    )

    steps = worker_steps.worker_steps["worker_main"]
    assert [step.command_type for step in steps] == ["GENERAL_COMMAND", "CALL_API"]
    assert steps[0].text == "preserve provenance."
    assert diagnostics[0].metadata["reason"] == "general_command_trimmed_to_residual_behavior"


def test_expected_correct_inexact_step_text_is_not_trimmed_without_exact_coverage_match() -> None:
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_retrieve",
                    text=(
                        "Retrieve needed sources using approved source recipes "
                        "based on <REF>needed_sources</REF>."
                    ),
                    source_span_ids=["s2"],
                    command_type="GENERAL_COMMAND",
                    inputs=["needed_sources"],
                    outputs=["source_evidence_set"],
                ),
                StepIR(
                    step_id="st_provenance",
                    text="Maintain provenance for externally sourced facts.",
                    source_span_ids=["s2"],
                    command_type="GENERAL_COMMAND",
                    inputs=["source_evidence_set"],
                    outputs=["source_evidence_set"],
                ),
            ]
        },
    )
    plan = _construct_plan()
    call = plan.api_call_demands()[0]
    call.metadata["capability_surface"] = "approved source recipes"
    call.operation_coverage = [
        OperationCoverageIR(
            coverage_id="cov_search",
            source_span_id="s2",
            operation_surface="retrieve them using approved source recipes",
            char_start=0,
            char_end=len("retrieve them using approved source recipes"),
            relation="normalized_whitespace",
        )
    ]
    call.behavior_lowering_policy = "api_call_augments_behavior"
    call.residual_behavior_span_ids = ["s2"]

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        plan,
        _api_plan(),
        [_placement("placed")],
        _resources(),
    )

    steps = worker_steps.worker_steps["worker_main"]
    assert [step.step_id for step in steps] == [
        "st_retrieve",
        "st_provenance",
        "st_api_bfb7b2b753",
    ]
    assert diagnostics == []


def test_expected_correct_call_api_inputs_outputs_come_from_argument_binding_ir() -> None:
    worker_steps = WorkerStepPlanIR(main_worker_id="worker_main")
    plan = _construct_plan()
    plan.api_call_argument_bindings = [
        APICallArgumentBindingIR(
            call_demand_id="api_call_search",
            input_bindings={"query": "needed_sources"},
            output_bindings={"response": "source_evidence_set"},
            binding_status="fully_bound",
            source_span_ids=("s2",),
        )
    ]

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        plan,
        _api_plan(),
        [_placement("placed")],
        _resources(),
    )

    step = worker_steps.worker_steps["worker_main"][0]
    assert diagnostics == []
    assert step.command_type == "CALL_API"
    assert step.inputs == ["needed_sources"]
    assert step.outputs == ["source_evidence_set"]
    assert step.metadata["argument_binding_status"] == "fully_bound"


def test_expected_correct_ambiguous_operation_coverage_blocks_call_api_materialization() -> None:
    worker_steps = WorkerStepPlanIR(main_worker_id="worker_main")
    plan = _construct_plan()
    call = plan.api_call_demands()[0]
    call.behavior_lowering_policy = "ambiguous"

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        plan,
        _api_plan(),
        [_placement("placed")],
        _resources(),
    )

    assert worker_steps.worker_steps == {}
    assert diagnostics[0].kind == "stage7_unresolved_api_call_materialization"
    assert diagnostics[0].metadata["reason"] == "ambiguous_operation_coverage"


def _construct_plan(
    *,
    declaration_demand_id: str | None = "api_decl_SearchAPI",
) -> ConstructPlan:
    return ConstructPlan(
        plan_id="cp",
        api_call_argument_bindings=[
            APICallArgumentBindingIR(
                call_demand_id="api_call_search",
                binding_status="not_required",
                source_span_ids=("s2",),
            )
        ],
        demands=[
            APIDeclarationDemand(
                demand_id="api_decl_SearchAPI",
                explicit_name_candidates=["SearchAPI"],
                integration_admission="confirmed",
                mechanism_status="explicit",
                source_span_ids=["s1"],
            ),
            APICallDemand(
                demand_id="api_call_search",
                declaration_demand_id=declaration_demand_id,
                api_group_id="search",
                action_text="Retrieve approved sources using SearchAPI.",
                source_span_ids=["s2"],
                operation_coverage=[
                    OperationCoverageIR(
                        coverage_id="cov_search",
                        source_span_id="s2",
                        operation_surface="Retrieve approved sources using SearchAPI.",
                        char_start=0,
                        char_end=len("Retrieve approved sources using SearchAPI."),
                    )
                ],
                consumes_behavior_span_ids=["s2"],
                behavior_lowering_policy="api_call_replaces_behavior",
            ),
        ],
    )


def _api_plan() -> APIMaterializationPlanIR:
    return APIMaterializationPlanIR(
        bindings=[
            APICallBindingIR(
                api_binding_id="api_binding:api_decl_SearchAPI",
                declaration_demand_id="api_decl_SearchAPI",
                api_id="api:SearchAPI",
                api_name="SearchAPI",
                call_demand_ids=["api_call_search"],
                source_span_ids=["s1"],
            )
        ]
    )


def _placement(status: str) -> APICallPlacementIR:
    return APICallPlacementIR(
        call_demand_id="api_call_search",
        owner_worker_id="worker_main",
        flow_ref="main" if status == "placed" else None,
        block_ref="block_main" if status == "placed" else None,
        status=status,  # type: ignore[arg-type]
        source_span_ids=["s2"],
        reason=None if status == "placed" else "block_not_resolved",
    )


def _resources() -> ResourceRegistryIR:
    return ResourceRegistryIR(
        apis=[
            APISpec(
                api_id="api:SearchAPI",
                api_name="SearchAPI",
                auth="none",
                description="Partial API declaration skeleton for SearchAPI.",
                declaration_status="partial_blocked",
                schema_status="unknown_placeholder",
                functions_status="unknown_placeholder",
                functions=[],
            )
        ]
    )
