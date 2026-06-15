"""WorkerPlanIR validation tests for Stage 9.5."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.stages.stage9_5_normalizer import IRNormalizer


def field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(name, "text", True, f"{name} field", source)  # type: ignore[arg-type]


def test_worker_scoped_preserves_multi_output_handoff_step() -> None:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("request", "text", True, "Request", "input"),
            VariableSpec("out_one", "text", True, "Output one", "output"),
            VariableSpec("out_two", "text", True, "Output two", "output"),
            VariableSpec("child_one", "text", True, "Child one", "output"),
            VariableSpec("child_two", "text", True, "Child two", "output"),
        ]
    )
    symbols = SymbolTable()
    for variable in resources.variables:
        symbols.declare(
            variable.name,
            variable.data_type,
            variable.source,
            variable.description,
        )
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "MainWorker",
                "main",
                "Main",
                owned_span_ids=["s1"],
                input_contract=[field("request")],
                output_contract=[field("out_one", "output"), field("out_two", "output")],
                boundary_kind="main_worker",
            ),
            WorkerSpecIR(
                "worker_child",
                "ChildWorker",
                "child",
                "Child",
                owned_span_ids=["s2"],
                input_contract=[field("request")],
                output_contract=[
                    field("child_one", "output"),
                    field("child_two", "output"),
                ],
                boundary_kind="bounded_subtask",
            ),
        ],
        handoffs=[
            WorkerHandoffIR(
                "h_multi",
                "worker_main",
                "worker_child",
                None,
                "invoke",
                None,
                "after",
                input_bindings=[InputBindingIR("request", "request", True)],
                output_bindings=[
                    OutputBindingIR("child_one", "out_one", True, "set"),
                    OutputBindingIR("child_two", "out_two", True, "set"),
                ],
                invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, None),
                input_binding_status="known_present",
                output_binding_status="known_present",
                materialization_status="complete",
            )
        ],
    )
    step_plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    "st_handoff",
                    "Invoke child",
                    ["s1"],
                    "INVOKE_WORKER",
                    inputs=["request"],
                    outputs=["out_one", "out_two"],
                    integration_ref="ChildWorker",
                    handoff_id="h_multi",
                )
            ],
            "worker_child": [
                StepIR(
                    "st_child",
                    "Produce child outputs",
                    ["s2"],
                    "GENERAL_COMMAND",
                    outputs=["child_one", "child_two"],
                )
            ],
        },
    )
    flow_plan = WorkerFlowPlanIR(
        {"worker_main": FlowStructureIR(["s1"]), "worker_child": FlowStructureIR(["s2"])}
    )
    block_plan = WorkerBlockPlanIR(
        {
            "worker_main": BlockStructureIR([BlockIR("b_main", "SEQUENTIAL", spans=["s1"])]),
            "worker_child": BlockStructureIR([BlockIR("b_child", "SEQUENTIAL", spans=["s2"])]),
        }
    )

    normalizer = IRNormalizer()
    _, _, normalized_steps, _, errors, warnings = normalizer.normalize_worker_scoped(
        flow_plan,
        block_plan,
        step_plan,
        plan,
        resources,
        symbols,
    )

    assert errors == []
    main_steps = normalized_steps.worker_steps["worker_main"]
    assert main_steps[0].outputs == ["out_one", "out_two"]
    assert len(main_steps) == 1
    assert [field.name for field in plan.workers[0].output_contract] == [
        "out_one",
        "out_two",
    ]
    assert resources.types == []
    assert not any("Aggregated multi-output step" in warning for warning in warnings)
    assert getattr(normalizer, "construct_findings", {}).get(
        "missing_output_producer"
    ) in (None, [])


def _normalizer_base_ir(
    handoff: WorkerHandoffIR,
    step_plan: WorkerStepPlanIR,
) -> tuple[
    WorkerPlanIR,
    WorkerFlowPlanIR,
    WorkerBlockPlanIR,
    ResourceRegistryIR,
    SymbolTable,
]:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("request", "text", True, "Request", "input"),
            VariableSpec("result", "text", True, "Result", "output"),
        ]
    )
    symbols = SymbolTable()
    for variable in resources.variables:
        symbols.declare(
            variable.name,
            variable.data_type,
            variable.source,
            variable.description,
        )
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "MainWorker",
                "main",
                "Main",
                owned_span_ids=["s1"],
                input_contract=[field("request")],
                output_contract=[field("result", "output")],
                boundary_kind="main_worker",
            ),
            WorkerSpecIR(
                "worker_child",
                "ChildWorker",
                "child",
                "Child",
                owned_span_ids=["s2"],
                input_contract=[],
                output_contract=[],
                input_contract_status="known_empty",
                output_contract_status="known_empty",
                input_contract_status_source="adapter_hard_fact",
                output_contract_status_source="adapter_hard_fact",
                boundary_kind="bounded_subtask",
            ),
        ],
        handoffs=[handoff],
    )
    flow_plan = WorkerFlowPlanIR(
        {"worker_main": FlowStructureIR(["s1"]), "worker_child": FlowStructureIR(["s2"])}
    )
    block_plan = WorkerBlockPlanIR(
        {
            "worker_main": BlockStructureIR([BlockIR("b_main", "SEQUENTIAL", spans=["s1"])]),
            "worker_child": BlockStructureIR([BlockIR("b_child", "SEQUENTIAL", spans=["s2"])]),
        }
    )
    return plan, flow_plan, block_plan, resources, symbols


def test_stage9_5_partial_unknown_handoff_without_step_is_not_error() -> None:
    handoff = WorkerHandoffIR(
        "h_partial",
        "worker_main",
        "worker_child",
        None,
        "invoke",
        None,
        "after",
        input_bindings=[],
        output_bindings=[],
        input_binding_status="unknown",
        output_binding_status="unknown",
        materialization_status="partial_contract_unknown",
    )
    step_plan = WorkerStepPlanIR("worker_main", {"worker_main": [], "worker_child": []})
    plan, flow_plan, block_plan, resources, symbols = _normalizer_base_ir(
        handoff,
        step_plan,
    )

    _, _, _, _, errors, warnings = IRNormalizer().normalize_worker_scoped(
        flow_plan, block_plan, step_plan, plan, resources, symbols,
    )

    assert errors == []
    assert any("partial_contract_unknown" in warning for warning in warnings)


def test_stage9_5_complete_handoff_without_step_is_error() -> None:
    handoff = WorkerHandoffIR(
        "h_complete",
        "worker_main",
        "worker_child",
        None,
        "invoke",
        None,
        "after",
        input_bindings=[],
        output_bindings=[],
        input_binding_status="known_empty",
        output_binding_status="known_empty",
        input_binding_status_source="adapter_hard_fact",
        output_binding_status_source="adapter_hard_fact",
        materialization_status="confirmed_empty_contract",
    )
    step_plan = WorkerStepPlanIR("worker_main", {"worker_main": [], "worker_child": []})
    plan, flow_plan, block_plan, resources, symbols = _normalizer_base_ir(
        handoff,
        step_plan,
    )

    _, _, _, _, errors, _warnings = IRNormalizer().normalize_worker_scoped(
        flow_plan, block_plan, step_plan, plan, resources, symbols,
    )

    assert any("has no corresponding step" in error for error in errors)


def test_stage9_5_confirmed_empty_handoff_validates_empty_step() -> None:
    handoff = WorkerHandoffIR(
        "h_empty",
        "worker_main",
        "worker_child",
        None,
        "invoke",
        None,
        "after",
        input_bindings=[],
        output_bindings=[],
        input_binding_status="known_empty",
        output_binding_status="known_empty",
        input_binding_status_source="adapter_hard_fact",
        output_binding_status_source="adapter_hard_fact",
        materialization_status="confirmed_empty_contract",
    )
    step_plan = WorkerStepPlanIR(
        "worker_main",
        {
            "worker_main": [
                StepIR(
                    "st_handoff",
                    "Invoke child",
                    ["s1"],
                    "INVOKE_WORKER",
                    inputs=[],
                    outputs=[],
                    integration_ref="ChildWorker",
                    handoff_id="h_empty",
                )
            ],
            "worker_child": [],
        },
    )
    plan, flow_plan, block_plan, resources, symbols = _normalizer_base_ir(
        handoff,
        step_plan,
    )

    _, _, _, _, errors, warnings = IRNormalizer().normalize_worker_scoped(
        flow_plan, block_plan, step_plan, plan, resources, symbols,
    )

    assert errors == []
    assert not any("no input_bindings" in warning for warning in warnings)
    assert not any("no output_bindings" in warning for warning in warnings)


def test_worker_scoped_multi_output_cleans_self_inputs_only() -> None:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("request", "text", True, "Request", "input"),
            VariableSpec("polished_draft", "text", True, "Draft", "output"),
            VariableSpec("revision_history", "text", True, "History", "output"),
            VariableSpec("readiness_status", "text", True, "Status", "output"),
        ]
    )
    symbols = SymbolTable()
    for variable in resources.variables:
        symbols.declare(
            variable.name,
            variable.data_type,
            variable.source,
            variable.description,
        )

    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "MainWorker",
                "main",
                "Main",
                owned_span_ids=["s1", "s2"],
                input_contract=[field("request")],
                output_contract=[
                    field("polished_draft", "output"),
                    field("revision_history", "output"),
                    field("readiness_status", "output"),
                ],
                boundary_kind="main_worker",
            )
        ],
    )
    step_plan = WorkerStepPlanIR(
        "worker_main",
        {
            "worker_main": [
                StepIR(
                    "st_finalize",
                    "Finalize package",
                    ["s1"],
                    "GENERAL_COMMAND",
                    inputs=["request", "revision_history", "readiness_status"],
                    outputs=["revision_history", "readiness_status"],
                ),
                StepIR(
                    "st_display",
                    "Deliver artifacts",
                    ["s2"],
                    "DISPLAY_MESSAGE",
                    inputs=["polished_draft", "revision_history", "readiness_status"],
                ),
            ]
        },
    )
    flow_plan = WorkerFlowPlanIR({"worker_main": FlowStructureIR(["s1", "s2"])})
    block_plan = WorkerBlockPlanIR(
        {"worker_main": BlockStructureIR([BlockIR("b_main", "SEQUENTIAL", spans=["s1", "s2"])])}
    )

    _, _, normalized_steps, _, errors, warnings = IRNormalizer().normalize_worker_scoped(
        flow_plan,
        block_plan,
        step_plan,
        plan,
        resources,
        symbols,
    )

    assert errors == []
    main_steps = normalized_steps.worker_steps["worker_main"]
    assert main_steps[0].outputs == ["revision_history", "readiness_status"]
    assert main_steps[0].inputs == ["request"]
    assert main_steps[1].inputs == [
        "polished_draft",
        "revision_history",
        "readiness_status",
    ]
    assert [field.name for field in plan.workers[0].output_contract] == [
        "polished_draft",
        "revision_history",
        "readiness_status",
    ]
    assert not any("revision_history' consumed but not produced" in warning for warning in warnings)
    assert not any("readiness_status' consumed but not produced" in warning for warning in warnings)


def test_worker_scoped_does_not_reclassify_display_by_text() -> None:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("request", "text", True, "Request", "input"),
        ]
    )
    symbols = SymbolTable()
    for variable in resources.variables:
        symbols.declare(
            variable.name,
            variable.data_type,
            variable.source,
            variable.description,
        )

    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "MainWorker",
                "main",
                "Main",
                owned_span_ids=["s1", "s2", "s3"],
                input_contract=[field("request")],
                output_contract=[],
                boundary_kind="main_worker",
            )
        ],
    )
    step_plan = WorkerStepPlanIR(
        "worker_main",
        {
            "worker_main": [
                StepIR(
                    "st_ask",
                    "Ask clarifying questions for missing inputs",
                    ["s1"],
                    "DISPLAY_MESSAGE",
                ),
                StepIR(
                    "st_iterate",
                    "Iterate on specific sections with the user",
                    ["s2"],
                    "DISPLAY_MESSAGE",
                    inputs=["request"],
                ),
                StepIR(
                    "st_deliver",
                    "Deliver final artifacts",
                    ["s3"],
                    "DISPLAY_MESSAGE",
                    inputs=["request"],
                ),
            ]
        },
    )
    flow_plan = WorkerFlowPlanIR({"worker_main": FlowStructureIR(["s1", "s2", "s3"])})
    block_plan = WorkerBlockPlanIR(
        {
            "worker_main": BlockStructureIR(
                [BlockIR("b_main", "SEQUENTIAL", spans=["s1", "s2", "s3"])]
            )
        }
    )

    _, _, normalized_steps, _, errors, warnings = IRNormalizer().normalize_worker_scoped(
        flow_plan,
        block_plan,
        step_plan,
        plan,
        resources,
        symbols,
    )

    assert errors == []
    main_steps = normalized_steps.worker_steps["worker_main"]
    assert main_steps[0].command_type == "DISPLAY_MESSAGE"
    assert main_steps[1].command_type == "DISPLAY_MESSAGE"
    assert main_steps[2].command_type == "DISPLAY_MESSAGE"
    assert not any("Reclassified" in warning for warning in warnings)


def test_worker_scoped_reports_display_with_outputs_as_invalid_shape() -> None:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("request", "text", True, "Request", "input"),
            VariableSpec("clarifying_questions", "List[text]", False, "Questions", "step"),
        ]
    )
    symbols = SymbolTable()
    for variable in resources.variables:
        symbols.declare(
            variable.name,
            variable.data_type,
            variable.source,
            variable.description,
        )

    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "MainWorker",
                "main",
                "Main",
                owned_span_ids=["s1"],
                input_contract=[field("request")],
                output_contract=[],
                boundary_kind="main_worker",
            )
        ],
    )
    step_plan = WorkerStepPlanIR(
        "worker_main",
        {
            "worker_main": [
                StepIR(
                    "st_ask",
                    "Ask clarifying questions for missing inputs",
                    ["s1"],
                    "DISPLAY_MESSAGE",
                    outputs=["clarifying_questions"],
                )
            ]
        },
    )
    flow_plan = WorkerFlowPlanIR({"worker_main": FlowStructureIR(["s1"])})
    block_plan = WorkerBlockPlanIR(
        {"worker_main": BlockStructureIR([BlockIR("b_main", "SEQUENTIAL", spans=["s1"])])}
    )

    _, _, normalized_steps, _, errors, warnings = IRNormalizer().normalize_worker_scoped(
        flow_plan,
        block_plan,
        step_plan,
        plan,
        resources,
        symbols,
    )

    assert normalized_steps.worker_steps["worker_main"][0].command_type == "DISPLAY_MESSAGE"
    assert any(
        "Worker worker_main step st_ask is DISPLAY_MESSAGE but declares outputs" in error
        for error in errors
    )
    assert not any("Reclassified" in warning for warning in warnings)


def test_worker_scoped_duplicate_producer_allows_ordered_update() -> None:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("request", "text", True, "Request", "input"),
            VariableSpec("status", "text", True, "Status", "output"),
        ]
    )
    symbols = SymbolTable()
    for variable in resources.variables:
        symbols.declare(
            variable.name,
            variable.data_type,
            variable.source,
            variable.description,
        )

    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "MainWorker",
                "main",
                "Main",
                owned_span_ids=["s1", "s2"],
                input_contract=[field("request")],
                output_contract=[field("status", "output")],
                boundary_kind="main_worker",
            )
        ],
    )
    step_plan = WorkerStepPlanIR(
        "worker_main",
        {
            "worker_main": [
                StepIR("st_create", "Create status", ["s1"], "GENERAL_COMMAND", outputs=["status"]),
                StepIR(
                    "st_update",
                    "Update status",
                    ["s2"],
                    "GENERAL_COMMAND",
                    inputs=["status"],
                    outputs=["status"],
                ),
            ]
        },
    )
    flow_plan = WorkerFlowPlanIR({"worker_main": FlowStructureIR(["s1", "s2"])})
    block_plan = WorkerBlockPlanIR(
        {"worker_main": BlockStructureIR([BlockIR("b_main", "SEQUENTIAL", spans=["s1", "s2"])])}
    )

    _, _, _, _, errors, warnings = IRNormalizer().normalize_worker_scoped(
        flow_plan,
        block_plan,
        step_plan,
        plan,
        resources,
        symbols,
    )

    assert errors == []
    assert not any(
        "variable 'status' produced by multiple steps" in warning
        for warning in warnings
    )


def test_worker_scoped_duplicate_producer_warns_for_overwrite() -> None:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("request", "text", True, "Request", "input"),
            VariableSpec("status", "text", True, "Status", "output"),
        ]
    )
    symbols = SymbolTable()
    for variable in resources.variables:
        symbols.declare(
            variable.name,
            variable.data_type,
            variable.source,
            variable.description,
        )

    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "MainWorker",
                "main",
                "Main",
                owned_span_ids=["s1", "s2"],
                input_contract=[field("request")],
                output_contract=[field("status", "output")],
                boundary_kind="main_worker",
            )
        ],
    )
    step_plan = WorkerStepPlanIR(
        "worker_main",
        {
            "worker_main": [
                StepIR("st_create", "Create status", ["s1"], "GENERAL_COMMAND", outputs=["status"]),
                StepIR(
                    "st_overwrite",
                    "Overwrite status",
                    ["s2"],
                    "GENERAL_COMMAND",
                    outputs=["status"],
                ),
            ]
        },
    )
    flow_plan = WorkerFlowPlanIR({"worker_main": FlowStructureIR(["s1", "s2"])})
    block_plan = WorkerBlockPlanIR(
        {"worker_main": BlockStructureIR([BlockIR("b_main", "SEQUENTIAL", spans=["s1", "s2"])])}
    )

    _, _, _, _, errors, warnings = IRNormalizer().normalize_worker_scoped(
        flow_plan,
        block_plan,
        step_plan,
        plan,
        resources,
        symbols,
    )

    assert errors == []
    assert any("variable 'status' produced by multiple steps" in warning for warning in warnings)


def test_worker_scoped_does_not_record_required_output_producer_findings() -> None:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("request", "text", True, "Request", "input"),
            VariableSpec("required_output", "text", True, "Required output", "output"),
        ]
    )
    symbols = SymbolTable()
    for variable in resources.variables:
        symbols.declare(
            variable.name,
            variable.data_type,
            variable.source,
            variable.description,
        )
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "MainWorker",
                "main",
                "Main",
                owned_span_ids=["s1"],
                input_contract=[field("request")],
                output_contract=[field("required_output", "output")],
                boundary_kind="main_worker",
            )
        ],
    )
    step_plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND", inputs=["request"])
            ]
        },
    )
    flow_plan = WorkerFlowPlanIR({"worker_main": FlowStructureIR(["s1"])})
    block_plan = WorkerBlockPlanIR(
        {"worker_main": BlockStructureIR([BlockIR("b1", "SEQUENTIAL", spans=["s1"])])}
    )

    normalizer = IRNormalizer()
    _, _, normalized_steps, _, errors, _ = normalizer.normalize_worker_scoped(
        flow_plan,
        block_plan,
        step_plan,
        plan,
        resources,
        symbols,
    )

    assert errors == []

    # No synthetic step is created
    main_steps = normalized_steps.worker_steps["worker_main"]
    assert len(main_steps) == 1
    assert main_steps[0].step_id == "st1"

    # Final diagnostics are produced by post-normalize IRS, not Stage 9.5.
    findings = getattr(normalizer, "construct_findings", {})
    assert findings.get("missing_output_producer") in (None, [])
