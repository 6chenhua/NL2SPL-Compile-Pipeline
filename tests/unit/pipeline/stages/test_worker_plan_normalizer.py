"""WorkerPlanIR validation tests for Stage 9.5."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR, VariableSpec
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


def plan_with_handoff(handoffs: list[WorkerHandoffIR] | None = None) -> WorkerPlanIR:
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "MainWorker",
                "main",
                "Coordinate request",
                owned_span_ids=["s1"],
                input_contract=[field("user_request")],
                output_contract=[field("evidence", "output")],
                boundary_kind="main_worker",
            ),
            WorkerSpecIR(
                "worker_child",
                "SourceWorker",
                "child",
                "Gather evidence",
                owned_span_ids=["s2"],
                input_contract=[field("source_request")],
                output_contract=[field("source_evidence", "output")],
                boundary_kind="bounded_subtask",
            ),
        ],
        handoffs=handoffs if handoffs is not None else [handoff()],
    )


def handoff() -> WorkerHandoffIR:
    return WorkerHandoffIR(
        "h1",
        "worker_main",
        "worker_child",
        None,
        "invoke",
        "sources are needed",
        "conditional",
        input_bindings=[InputBindingIR("user_request", "source_request", True)],
        output_bindings=[OutputBindingIR("source_evidence", "evidence", True, "set")],
        invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, "if"),
    )


def resources_and_symbols() -> tuple[ResourceRegistryIR, SymbolTable]:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("user_request", "text", True, "User request", "input"),
            VariableSpec("evidence", "text", True, "Evidence", "output"),
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
    return resources, symbols


def test_worker_plan_materializes_missing_handoff_step() -> None:
    resources, symbols = resources_and_symbols()

    _, _, steps, _, _, errors, _ = IRNormalizer().normalize(
        FlowStructureIR(main_flow_spans=["s1"]),
        BlockStructureIR([BlockIR("b1", "IF", "sources are needed", ["s1"])]),
        resources,
        symbols,
        [],
        [],
        plan_with_handoff(),
    )

    assert errors == []
    assert steps[0].command_type == "INVOKE_WORKER"
    assert steps[0].integration_ref == "SourceWorker"
    assert steps[0].outputs == ["evidence"]
    assert steps[0].handoff_id == "h1"


def test_worker_plan_rejects_unresolved_invoke_worker() -> None:
    resources, symbols = resources_and_symbols()
    steps = [
        StepIR(
            "st1",
            "Invoke a worker",
            ["s99"],
            "INVOKE_WORKER",
            inputs=["user_request"],
            outputs=["evidence"],
            integration_ref="Worker",
            kind="invoke",
        )
    ]

    _, _, _, _, _, errors, _ = IRNormalizer().normalize(
        FlowStructureIR(main_flow_spans=["s1"]),
        BlockStructureIR([BlockIR("b1", "IF", "sources are needed", ["s1"])]),
        resources,
        symbols,
        steps,
        [],
        plan_with_handoff(),
    )

    assert any("no concrete child worker" in error for error in errors)


def test_worker_plan_rejects_child_without_invocation() -> None:
    resources, symbols = resources_and_symbols()

    _, _, _, _, _, errors, _ = IRNormalizer().normalize(
        FlowStructureIR(main_flow_spans=["s1"]),
        BlockStructureIR([BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
        resources,
        symbols,
        [],
        [],
        plan_with_handoff(handoffs=[]),
    )

    assert any("Non-main worker has no handoff" in error for error in errors)


def test_two_handoffs_to_same_child_worker_are_not_merged() -> None:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("user_request", "text", True, "User request", "input"),
            VariableSpec("main_evidence", "text", True, "Main evidence", "output"),
            VariableSpec("recovery_evidence", "text", True, "Recovery evidence", "output"),
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
    plan = plan_with_handoff(
        handoffs=[
            WorkerHandoffIR(
                "h_main",
                "worker_main",
                "worker_child",
                None,
                "invoke",
                "sources are needed",
                "conditional",
                input_bindings=[InputBindingIR("user_request", "source_request", True)],
                output_bindings=[
                    OutputBindingIR("source_evidence", "main_evidence", True, "set")
                ],
                invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, "if"),
            ),
            WorkerHandoffIR(
                "h_recovery",
                "worker_main",
                "worker_child",
                None,
                "invoke",
                "recovery needs sources",
                "conditional",
                input_bindings=[InputBindingIR("user_request", "source_request", True)],
                output_bindings=[
                    OutputBindingIR("source_evidence", "recovery_evidence", True, "set")
                ],
                invoke_location_hint=InvokeLocationHintIR("main", None, "s3", None, "if"),
            ),
        ]
    )

    _, _, steps, _, _, errors, _ = IRNormalizer().normalize(
        FlowStructureIR(main_flow_spans=["s1", "s3"]),
        BlockStructureIR(
            [
                BlockIR("b1", "IF", "sources are needed", ["s1"]),
                BlockIR("b2", "IF", "recovery needs sources", ["s3"]),
            ]
        ),
        resources,
        symbols,
        [],
        [],
        plan,
    )

    assert errors == []
    invoke_steps = [step for step in steps if step.command_type == "INVOKE_WORKER"]
    assert len(invoke_steps) == 2
    assert {step.handoff_id for step in invoke_steps} == {"h_main", "h_recovery"}
    assert {tuple(step.outputs) for step in invoke_steps} == {
        ("main_evidence",),
        ("recovery_evidence",),
    }


def api_handoff(
    output_name: str = "api_result",
    input_name: str = "api_query",
    api_ref: str | None = "SearchAPI",
) -> WorkerHandoffIR:
    return WorkerHandoffIR(
        "h_api",
        "worker_main",
        None,
        api_ref,
        "api_call",
        "search is needed",
        "conditional",
        input_bindings=[InputBindingIR(input_name, "query", True)],
        output_bindings=[OutputBindingIR("result", output_name, True, "set")],
        invoke_location_hint=InvokeLocationHintIR("main", None, "s1", None, "if"),
    )


def main_only_plan(handoffs: list[WorkerHandoffIR]) -> WorkerPlanIR:
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "MainWorker",
                "main",
                "Coordinate request",
                owned_span_ids=["s1"],
                input_contract=[field("api_query")],
                output_contract=[field("api_result", "output")],
                boundary_kind="main_worker",
            )
        ],
        handoffs=handoffs,
    )


def test_api_call_handoff_materializes_and_validates_bindings() -> None:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("api_query", "text", True, "API query", "input"),
            VariableSpec("api_result", "text", True, "API result", "output"),
        ],
        apis=[APISpec("SearchAPI", "none", "Search API")],
    )
    symbols = SymbolTable()
    for variable in resources.variables:
        symbols.declare(
            variable.name,
            variable.data_type,
            variable.source,
            variable.description,
        )

    _, _, steps, _, _, errors, _ = IRNormalizer().normalize(
        FlowStructureIR(main_flow_spans=["s1"]),
        BlockStructureIR([BlockIR("b1", "IF", "search is needed", ["s1"])]),
        resources,
        symbols,
        [],
        [],
        main_only_plan([api_handoff()]),
    )

    assert errors == []
    assert steps[0].command_type == "CALL_API"
    assert steps[0].integration_ref == "SearchAPI"
    assert steps[0].handoff_id == "h_api"


def test_api_call_handoff_rejects_missing_call_api_step() -> None:
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("api_query", "text", True, "API query", "input"),
            VariableSpec("api_result", "text", True, "API result", "output"),
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

    _, _, _, _, _, errors, _ = IRNormalizer().normalize(
        FlowStructureIR(main_flow_spans=["s1"]),
        BlockStructureIR([BlockIR("b1", "IF", "search is needed", ["s1"])]),
        resources,
        symbols,
        [],
        [],
        main_only_plan([api_handoff(api_ref=None)]),
    )

    assert any("has no CALL_API step" in error for error in errors)


def test_api_call_handoff_rejects_undeclared_required_input() -> None:
    resources = ResourceRegistryIR(
        variables=[VariableSpec("api_result", "text", True, "API result", "output")],
        apis=[APISpec("SearchAPI", "none", "Search API")],
    )
    symbols = SymbolTable()
    symbols.declare("api_result", "text", "output", "API result")

    _, _, _, _, _, errors, _ = IRNormalizer().normalize(
        FlowStructureIR(main_flow_spans=["s1"]),
        BlockStructureIR([BlockIR("b1", "IF", "search is needed", ["s1"])]),
        resources,
        symbols,
        [],
        [],
        main_only_plan([api_handoff(input_name="missing_query")]),
    )

    assert any("required input missing_query is not declared" in error for error in errors)


def test_api_call_handoff_rejects_unused_required_output() -> None:
    resources = ResourceRegistryIR(
        variables=[VariableSpec("api_query", "text", True, "API query", "input")],
        apis=[APISpec("SearchAPI", "none", "Search API")],
    )
    symbols = SymbolTable()
    symbols.declare("api_query", "text", "input", "API query")

    _, _, _, _, _, errors, _ = IRNormalizer().normalize(
        FlowStructureIR(main_flow_spans=["s1"]),
        BlockStructureIR([BlockIR("b1", "IF", "search is needed", ["s1"])]),
        resources,
        symbols,
        [],
        [],
        main_only_plan([api_handoff(output_name="intermediate_api_result")]),
    )

    assert any(
        "required output intermediate_api_result is not consumed or declared as a final output"
        in error
        for error in errors
    )


def test_worker_scoped_normalizes_multi_output_handoff_step() -> None:
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
    assert main_steps[0].outputs == ["out_one_structured"]
    assert [step.outputs for step in main_steps[1:]] == [["out_one"], ["out_two"]]
    assert any(t.type_name == "out_one_structured_type" for t in resources.types)
    assert any("Aggregated multi-output step st_handoff" in warning for warning in warnings)


def test_worker_scoped_adds_required_main_output_producers() -> None:
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
    _, _, normalized_steps, _, errors, warnings = normalizer.normalize_worker_scoped(
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

    # Structured finding is recorded instead of CompileDiagnostic
    # (final diagnostics are produced by PostNormalizeIRSChecker)
    findings = getattr(normalizer, "construct_findings", {})
    mop_findings = findings.get("missing_output_producer", [])
    assert len(mop_findings) == 1
    assert mop_findings[0]["output"] == "required_output"
    assert mop_findings[0]["worker_id"] == "worker_main"
