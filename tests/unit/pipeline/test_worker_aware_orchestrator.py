"""Worker-aware orchestrator path tests for Stage 4/5 migration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import (
    ResourceRegistryIR,
    VariableSpec,
    WorkerScopedResourceIR,
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    ControlComplexityRegionIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerBlockPlanIR,
    WorkerBoundaryDecisionIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.orchestrator import PipelineOrchestrator


def spans() -> list[SpanIR]:
    return [
        SpanIR("s1", "Prepare the request context."),
        SpanIR("s2", "Gather approved sources."),
        SpanIR("s3", "Produce the final answer."),
    ]


def routes() -> FieldRouteIR:
    return FieldRouteIR(behavior=["s1", "s2", "s3"])


def field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(
        name=name,
        data_type="text",
        required=True,
        description=f"{name} field",
        source=source,  # type: ignore[arg-type]
    )


def worker_plan() -> WorkerPlanIR:
    main_worker = WorkerSpecIR(
        worker_id="worker_main",
        worker_name="MainWorker",
        kind="main",
        purpose="Coordinate the request.",
        owned_span_ids=["s1", "s3"],
        input_contract=[field("request")],
        output_contract=[field("draft", "output")],
        boundary_kind="main_worker",
    )
    child_worker = WorkerSpecIR(
        worker_id="worker_source",
        worker_name="SourceWorker",
        kind="child",
        purpose="Gather source evidence.",
        owned_span_ids=["s2"],
        input_contract=[field("request")],
        output_contract=[field("evidence", "output")],
        boundary_kind="bounded_subtask",
    )
    candidate = CandidateTaskUnitIR(
        candidate_id="worker_source",
        source_span_ids=["s2"],
        task_text="Gather approved sources.",
        purpose="Gather source evidence.",
        candidate_kind="bounded_subtask",
        possible_inputs=[field("request")],
        possible_outputs=[field("evidence", "output")],
    )
    decision = WorkerBoundaryDecisionIR(
        candidate_id="worker_source",
        decision="extract_child_worker",
        boundary_strength="strong",
        boundary_kind="bounded_subtask",
        rejection_reason=None,
        reason="Clear source gathering handoff.",
        evidence=["bounded_io"],
    )
    handoff = WorkerHandoffIR(
        handoff_id="handoff_source",
        from_worker="worker_main",
        to_worker="worker_source",
        api_ref=None,
        mode="invoke",
        condition_text="when source evidence is needed",
        ordering="conditional",
        input_bindings=[InputBindingIR("request", "request", True)],
        output_bindings=[OutputBindingIR("evidence", "evidence", True, "set")],
        invoke_location_hint=InvokeLocationHintIR(
            flow_kind="main",
            flow_id=None,
            after_span_id="s1",
            before_span_id="s3",
            block_hint="sequential",
        ),
    )
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main_worker, child_worker],
        candidates=[candidate],
        decisions=[decision],
        handoffs=[handoff],
    )


def worker_flow_plan() -> WorkerFlowPlanIR:
    return WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(main_flow_spans=["s1", "s3"]),
            "worker_source": FlowStructureIR(main_flow_spans=["s2"]),
        }
    )


def worker_block_plan() -> WorkerBlockPlanIR:
    return WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR("b1", "SEQUENTIAL", None, ["s1", "s3"]),
                ]
            ),
            "worker_source": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR("b_child", "SEQUENTIAL", None, ["s2"]),
                ]
            ),
        },
        control_complexity_regions=[
            ControlComplexityRegionIR(
                "ccr_1",
                ["s1"],
                "SEQUENTIAL",
                "IF",
                "Flattenable local branch.",
                "confirmed",
                "info",
                True,
                False,
                False,
                ["split_blocks"],
            )
        ],
    )


def test_orchestrator_worker_aware_stage4_stage5_path_uses_wrappers(
    tmp_path: Path,
) -> None:
    config = PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=tmp_path / "output",
        save_intermediate=False,
        enable_worker_boundary_planner=True,
    )
    orchestrator = PipelineOrchestrator(config)
    plan = worker_plan()
    span_list = spans()
    route_ir = routes()
    flow_plan = worker_flow_plan()
    block_plan = worker_block_plan()
    symbols = SymbolTable()

    worker_scoped_resources = WorkerScopedResourceIR(
        global_resources=ResourceRegistryIR()
    )
    with (
        patch.object(orchestrator, "_run_stage1", return_value=span_list),
        patch.object(orchestrator, "_run_stage2", return_value=(route_ir, [])),
        patch.object(orchestrator, "_run_stage3", return_value=(span_list, route_ir)),
        patch.object(orchestrator, "_run_stage3_5", return_value=plan),
        patch.object(orchestrator, "_run_stage4", return_value=flow_plan) as stage4,
        patch.object(orchestrator, "_run_stage5", return_value=block_plan) as stage5,
        patch.object(
            orchestrator,
            "_run_stage6_worker_scoped",
            return_value=(worker_scoped_resources, symbols),
        ) as stage6_ws,
        patch.object(orchestrator, "_run_stage7", return_value=([], symbols, [])),
        patch.object(orchestrator, "_run_stage7_worker_scoped", return_value=(MagicMock(), symbols, [])),
        patch.object(orchestrator, "_run_stage8", return_value=MagicMock()),
        patch.object(orchestrator, "_run_stage9", return_value=[]),
        patch.object(
            orchestrator,
            "_run_normalization_worker_scoped",
            return_value=(
                flow_plan,
                block_plan,
                MagicMock(),
                symbols,
                [],
                [],
                [],
            ),
        ),
        patch.object(orchestrator, "_run_stage10_worker_scoped", return_value=MagicMock()),
        patch.object(orchestrator, "_run_stage11", return_value=("SPL", [], [])),
    ):
        result = orchestrator.run("test")

    stage4.assert_called_once_with(span_list, route_ir, plan)
    stage5.assert_called_once_with(span_list, route_ir, flow_plan)
    assert stage6_ws.call_args.args[0] == span_list
    assert stage6_ws.call_args.args[1] == route_ir
    assert stage6_ws.call_args.args[2] is flow_plan
    assert stage6_ws.call_args.args[3] is block_plan
    assert stage6_ws.call_args.args[4] is plan

    assert result.intermediate_results["stage4_worker_flows"] is flow_plan
    assert result.intermediate_results["stage5_worker_blocks"] is block_plan
    # T3: Worker-aware 路径不再产生 adapter intermediate records
    # (stage4_flow/stage5_blocks 保留空结构用于 Stage 9 接口兼容)
    assert result.intermediate_results["stage6_worker_scoped_resources"] is worker_scoped_resources
    assert result.intermediate_results["stage6_resources"] is worker_scoped_resources.global_resources


def test_orchestrator_stage_helpers_call_worker_aware_assembler_inputs(
    pipeline_config: PipelineConfig,
) -> None:
    orchestrator = PipelineOrchestrator(pipeline_config)
    plan = worker_plan()
    flow_plan = worker_flow_plan()
    block_plan = worker_block_plan()

    with patch("nl2spl.pipeline.orchestrator.FlowAssembler") as flow_cls:
        flow_cls.return_value.execute.return_value = flow_plan
        result = orchestrator._run_stage4(spans(), routes(), plan)

    flow_cls.return_value.execute.assert_called_once()
    assert flow_cls.return_value.execute.call_args.args[0][2] is plan
    assert result is flow_plan

    with patch("nl2spl.pipeline.orchestrator.BlockAssembler") as block_cls:
        block_cls.return_value.execute.return_value = block_plan
        result = orchestrator._run_stage5(spans(), routes(), flow_plan)

    block_cls.return_value.execute.assert_called_once()
    assert block_cls.return_value.execute.call_args.args[0][2] is flow_plan
    assert result is block_plan


def test_worker_aware_stage45_context_feeds_downstream_workerplan_path(
    tmp_path: Path,
) -> None:
    config = PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=tmp_path / "output",
        save_intermediate=False,
        enable_worker_boundary_planner=True,
    )
    orchestrator = PipelineOrchestrator(config)
    orchestrator.client = MagicMock()
    orchestrator.client.call_json.return_value = {
        "steps": [
            {
                "step_id": "st_draft",
                "text": "Produce the draft from gathered evidence.",
                "source_span_ids": ["s3"],
                "command_type": "GENERAL_COMMAND",
                "inputs": ["evidence"],
                "outputs": ["draft"],
                "flow_ref": "main",
                "block_ref": "b1",
            }
        ],
        "new_variables": [],
    }
    plan = worker_plan()
    span_list = spans()
    route_ir = routes()
    flow_plan = worker_flow_plan()
    block_plan = worker_block_plan()
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("request", "text", True, "Request", "input"),
            VariableSpec("evidence", "text", True, "Evidence", "step"),
            VariableSpec("draft", "text", True, "Draft", "output"),
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

    # 创建 mock 的 WorkerStepPlanIR
    from nl2spl.ir.step_ir import StepIR
    from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

    invoke_step = StepIR(
        step_id="st_invoke_handoff_source",
        text="Invoke worker: SourceWorker",
        source_span_ids=["s1"],
        command_type="INVOKE_WORKER",
        inputs=["request"],
        outputs=["evidence"],
        integration_ref="SourceWorker",
        kind="invoke",
        handoff_id="handoff_source",
    )
    mock_worker_step_plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [invoke_step],
            "worker_source": [],
        },
    )

    mock_worker = MagicMock()
    mock_worker.child_worker_refs = ["SourceWorker"]
    mock_worker.child_workers = [MagicMock(worker_name="SourceWorker")]

    with (
        patch.object(orchestrator, "_run_stage1", return_value=span_list),
        patch.object(orchestrator, "_run_stage2", return_value=(route_ir, [])),
        patch.object(orchestrator, "_run_stage3", return_value=(span_list, route_ir)),
        patch.object(orchestrator, "_run_stage3_5", return_value=plan),
        patch.object(orchestrator, "_run_stage4", return_value=flow_plan) as stage4,
        patch.object(orchestrator, "_run_stage5", return_value=block_plan) as stage5,
        patch.object(
            orchestrator,
            "_run_stage6_worker_scoped",
            return_value=(WorkerScopedResourceIR(global_resources=resources), symbols),
        ),
        patch.object(orchestrator, "_run_stage7", return_value=([], symbols, [])),
        patch.object(
            orchestrator,
            "_run_stage7_worker_scoped",
            return_value=(mock_worker_step_plan, symbols, []),
        ),
        patch.object(orchestrator, "_run_stage8", return_value=MagicMock()),
        patch.object(orchestrator, "_run_stage9", return_value=[]),
        patch.object(
            orchestrator,
            "_run_normalization",
            return_value=(
                FlowStructureIR(main_flow_spans=["s1", "s3"]),
                BlockStructureIR(
                    main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1", "s3"])]
                ),
                [],
                [],
                symbols,
                [],
                [],
                [],
            ),
        ),
        patch.object(
            orchestrator,
            "_run_normalization_worker_scoped",
            return_value=(
                flow_plan,
                block_plan,
                mock_worker_step_plan,
                symbols,
                [],
                [],
                [],
            ),
        ),
        patch.object(orchestrator, "_run_stage10_worker_scoped", return_value=mock_worker),
        patch.object(orchestrator, "_run_stage11", return_value=("SPL", [], [])) as stage11,
    ):
        result = orchestrator.run("test")

    stage4.assert_called_once_with(span_list, route_ir, plan)
    stage5.assert_called_once_with(span_list, route_ir, flow_plan)
    worker = result.intermediate_results["stage10_worker"]
    steps = stage11.call_args.args[4]

    assert "stage4_worker_flows" in result.intermediate_results
    assert "stage5_worker_blocks" in result.intermediate_results
    assert worker.child_worker_refs == ["SourceWorker"]
    assert [child.worker_name for child in worker.child_workers] == ["SourceWorker"]
    assert any(
        step.command_type == "INVOKE_WORKER"
        and step.integration_ref == "SourceWorker"
        and step.handoff_id == "handoff_source"
        for step in steps
    )
    assert not any("s2" in step.source_span_ids for step in steps)
