"""Full pipeline worker-aware integration tests.

from Stage 1 through Stage 11, confirming child workers are rendered and
no validation errors occur.
"""

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
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    ControlComplexityRegionIR,
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
from nl2spl.pipeline.orchestrator import PipelineOrchestrator


def _make_enterprise_worker_plan() -> WorkerPlanIR:
    """Worker plan modelled after enterprise-procedure use case.

    1 main worker + 2 child workers (NormalizeRequestWorker, VendorPoolWorker).
    """
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Handle the end-to-end procurement process",
                owned_span_ids=["s1", "s4", "s5"],
                input_contract=[
                    ContractFieldIR(
                        name="purchase_request", data_type="text", required=True,
                        description="Purchase request", source="input",
                    ),
                ],
                output_contract=[
                    ContractFieldIR(
                        name="po_artifact", data_type="text", required=True,
                        description="PO issuance artifact", source="output",
                    ),
                ],
            ),
            WorkerSpecIR(
                worker_id="worker_normalize",
                worker_name="NormalizeRequestWorker",
                kind="child",
                purpose="Normalize the purchase request",
                owned_span_ids=["s2"],
                input_contract=[
                    ContractFieldIR(
                        name="purchase_request", data_type="text", required=True,
                        description="Purchase request", source="input",
                    ),
                ],
                output_contract=[
                    ContractFieldIR(
                        name="procurement_category", data_type="text", required=True,
                        description="Procurement category", source="output",
                    ),
                ],
            ),
            WorkerSpecIR(
                worker_id="worker_vendor",
                worker_name="VendorPoolWorker",
                kind="child",
                purpose="Identify eligible vendor pool",
                owned_span_ids=["s3"],
                input_contract=[
                    ContractFieldIR(
                        name="procurement_category", data_type="text", required=True,
                        description="Procurement category", source="input",
                    ),
                ],
                output_contract=[
                    ContractFieldIR(
                        name="eligible_vendor_pool", data_type="text", required=True,
                        description="Eligible vendor pool", source="output",
                    ),
                ],
            ),
        ],
        handoffs=[
            WorkerHandoffIR(
                handoff_id="handoff_normalize",
                from_worker="worker_main",
                to_worker="worker_normalize",
                api_ref=None,
                mode="invoke",
                condition_text=None,
                ordering="after",
                input_bindings=[
                    InputBindingIR("purchase_request", "purchase_request", True),
                ],
                output_bindings=[
                    OutputBindingIR("procurement_category", "procurement_category", True, "set"),
                ],
                invoke_location_hint=InvokeLocationHintIR(
                    flow_kind="main", flow_id=None,
                    after_span_id="s1", before_span_id="s4",
                    block_hint="sequential",
                ),
            ),
            WorkerHandoffIR(
                handoff_id="handoff_vendor",
                from_worker="worker_main",
                to_worker="worker_vendor",
                api_ref=None,
                mode="invoke",
                condition_text=None,
                ordering="after",
                input_bindings=[
                    InputBindingIR("procurement_category", "procurement_category", True),
                ],
                output_bindings=[
                    OutputBindingIR("eligible_vendor_pool", "eligible_vendor_pool", True, "set"),
                ],
                invoke_location_hint=InvokeLocationHintIR(
                    flow_kind="main", flow_id=None,
                    after_span_id="s4", before_span_id="s5",
                    block_hint="sequential",
                ),
            ),
        ],
    )


def _make_enterprise_flow_plan() -> WorkerFlowPlanIR:
    """Worker-scoped flow plan matching enterprise-procedure structure."""
    return WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(main_flow_spans=["s1", "s4", "s5"]),
            "worker_normalize": FlowStructureIR(main_flow_spans=["s2"]),
            "worker_vendor": FlowStructureIR(main_flow_spans=["s3"]),
        },
        warnings=[],
    )


def _make_enterprise_block_plan() -> WorkerBlockPlanIR:
    """Worker-scoped block plan matching enterprise-procedure structure."""
    return WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR("b1", "SEQUENTIAL", None, ["s1"]),
                    BlockIR("b2", "SEQUENTIAL", None, ["s4"]),
                    BlockIR("b3", "SEQUENTIAL", None, ["s5"]),
                ]
            ),
            "worker_normalize": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR("b_norm", "SEQUENTIAL", None, ["s2"]),
                ]
            ),
            "worker_vendor": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR("b_vendor", "SEQUENTIAL", None, ["s3"]),
                ]
            ),
        },
        control_complexity_regions=[],
        warnings=[],
    )


def _make_enterprise_spans() -> list[SpanIR]:
    return [
        SpanIR("s1", "Receive purchase request"),
        SpanIR("s2", "Normalize the request"),
        SpanIR("s3", "Find eligible vendors"),
        SpanIR("s4", "Prepare purchase order"),
        SpanIR("s5", "Finalize and issue PO"),
    ]


def _make_enterprise_routes() -> FieldRouteIR:
    return FieldRouteIR(behavior=["s1", "s2", "s3", "s4", "s5"])


def test_full_pipeline_worker_aware_enterprise_procedure(tmp_path: Path) -> None:
    """Run full pipeline with enterprise-procedure input, worker-aware path.

    Verifies:
    - Pipeline completes without validation errors
    - Child workers are rendered in SPL output
    - Worker-scoped intermediate results are stored
    """
    config = PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=tmp_path / "output",
        save_intermediate=False,
    )
    orchestrator = PipelineOrchestrator(config)

    spans = _make_enterprise_spans()
    routes = _make_enterprise_routes()
    plan = _make_enterprise_worker_plan()
    flow_plan = _make_enterprise_flow_plan()
    block_plan = _make_enterprise_block_plan()
    symbols = SymbolTable()

    # Declare some global variables that Stage 6 would normally extract
    symbols.declare("purchase_request", "text", "input", "Purchase request")
    symbols.declare("po_artifact", "text", "output", "PO artifact")
    symbols.declare("procurement_category", "text", "step", "Procurement category")
    symbols.declare("eligible_vendor_pool", "text", "step", "Eligible vendor pool")

    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("purchase_request", "text", True, "Purchase request", "input"),
            VariableSpec("po_artifact", "text", True, "PO artifact", "output"),
        ]
    )
    worker_scoped_resources = WorkerScopedResourceIR(
        global_resources=resources,
        worker_resources={
            "worker_normalize": ResourceRegistryIR(
                variables=[
                    VariableSpec("procurement_category", "text", True, "Procurement category", "output"),
                ]
            ),
            "worker_vendor": ResourceRegistryIR(
                variables=[
                    VariableSpec("eligible_vendor_pool", "text", True, "Eligible vendor pool", "output"),
                ]
            ),
        },
    )

    # Build invoke steps for main worker
    invoke_normalize = StepIR(
        step_id="st_invoke_handoff_normalize",
        text="Invoke worker: NormalizeRequestWorker",
        source_span_ids=["s1"],
        command_type="INVOKE_WORKER",
        inputs=["purchase_request"],
        outputs=["procurement_category"],
        integration_ref="NormalizeRequestWorker",
        kind="invoke",
        handoff_id="handoff_normalize",
    )
    invoke_vendor = StepIR(
        step_id="st_invoke_handoff_vendor",
        text="Invoke worker: VendorPoolWorker",
        source_span_ids=["s4"],
        command_type="INVOKE_WORKER",
        inputs=["procurement_category"],
        outputs=["eligible_vendor_pool"],
        integration_ref="VendorPoolWorker",
        kind="invoke",
        handoff_id="handoff_vendor",
    )

    worker_step_plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st1", text="Receive request",
                    source_span_ids=["s1"], command_type="GENERAL_COMMAND",
                    inputs=[], outputs=[],
                ),
                invoke_normalize,
                StepIR(
                    step_id="st3", text="Prepare PO",
                    source_span_ids=["s4"], command_type="GENERAL_COMMAND",
                    inputs=["procurement_category"], outputs=["po_draft"],
                ),
                invoke_vendor,
                StepIR(
                    step_id="st5", text="Finalize PO",
                    source_span_ids=["s5"], command_type="GENERAL_COMMAND",
                    inputs=["eligible_vendor_pool"], outputs=["po_artifact"],
                ),
            ],
            "worker_normalize": [
                StepIR(
                    step_id="st_norm_1", text="Normalize purchase request",
                    source_span_ids=["s2"], command_type="GENERAL_COMMAND",
                    inputs=["purchase_request"], outputs=["procurement_category"],
                ),
            ],
            "worker_vendor": [
                StepIR(
                    step_id="st_vendor_1", text="Identify eligible vendors",
                    source_span_ids=["s3"], command_type="GENERAL_COMMAND",
                    inputs=["procurement_category"], outputs=["eligible_vendor_pool"],
                ),
            ],
        },
        warnings=[],
    )

    with (
        patch.object(orchestrator, "_run_stage1", return_value=spans),
        patch.object(orchestrator, "_run_stage2", return_value=(routes, [])),
        patch.object(orchestrator, "_run_stage3", return_value=(spans, routes)),
        patch.object(orchestrator, "_run_stage3_5", return_value=plan),
        patch.object(orchestrator, "_run_stage4", return_value=flow_plan),
        patch.object(orchestrator, "_run_stage5", return_value=block_plan),
        patch.object(
            orchestrator, "_run_stage6_worker_scoped",
            return_value=(worker_scoped_resources, symbols, []),
        ),
        patch.object(
            orchestrator, "_run_stage7_worker_scoped",
            return_value=(worker_step_plan, symbols, []),
        ),
        patch.object(orchestrator, "_run_stage8", return_value=MagicMock()),
        patch.object(orchestrator, "_run_stage9", return_value=[]),
        patch.object(
            orchestrator, "_run_normalization_worker_scoped",
            return_value=(flow_plan, block_plan, worker_step_plan, symbols, [], []),
        ),
        patch.object(orchestrator, "_run_stage11", return_value=("", [], [])),
    ):
        result = orchestrator.run("Receive a purchase request, normalize it, find vendors, prepare and issue PO.")

    # Verify pipeline completed
    assert result is not None
    assert len(result.validation_errors) == 0

    # Verify worker-scoped intermediate results are stored
    intermediates = result.intermediate_results
    assert "stage4_worker_flows" in intermediates
    assert "stage5_worker_blocks" in intermediates
    assert "stage6_worker_scoped_resources" in intermediates
    assert "stage7_worker_step_plan" in intermediates

    # Verify the worker-scoped resource is correctly typed and populated
    stored_resources = intermediates["stage6_worker_scoped_resources"]
    assert isinstance(stored_resources, WorkerScopedResourceIR)
    assert len(stored_resources.worker_resources) == 2
    assert "worker_normalize" in stored_resources.worker_resources
    assert "worker_vendor" in stored_resources.worker_resources

    # Verify the stage6_resources is the global subset
    assert intermediates["stage6_resources"] is stored_resources.global_resources


def test_full_pipeline_worker_aware_renders_child_workers(tmp_path: Path) -> None:
    """Verify child workers appear in SPL output via the full worker-aware path.

    This test allows the real Stage 10 assembler and Stage 11 renderer to run,
    confirming the assembled WorkerIR produces SPL with DEFINE_WORKER blocks.
    """
    config = PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=tmp_path / "output",
        save_intermediate=False,
    )
    orchestrator = PipelineOrchestrator(config)

    spans = _make_enterprise_spans()
    routes = _make_enterprise_routes()
    plan = _make_enterprise_worker_plan()
    flow_plan = _make_enterprise_flow_plan()
    block_plan = _make_enterprise_block_plan()
    symbols = SymbolTable()

    symbols.declare("purchase_request", "text", "input", "Purchase request")
    symbols.declare("po_artifact", "text", "output", "PO artifact")
    symbols.declare("procurement_category", "text", "step", "Procurement category")
    symbols.declare("eligible_vendor_pool", "text", "step", "Eligible vendor pool")

    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("purchase_request", "text", True, "Purchase request", "input"),
            VariableSpec("po_artifact", "text", True, "PO artifact", "output"),
        ]
    )
    worker_scoped_resources = WorkerScopedResourceIR(
        global_resources=resources,
    )

    worker_step_plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st1", text="Receive request",
                    source_span_ids=["s1"], command_type="GENERAL_COMMAND",
                    inputs=[], outputs=[], flow_ref="main", block_ref="b1",
                ),
                StepIR(
                    step_id="st_invoke_handoff_normalize",
                    text="Invoke worker: NormalizeRequestWorker",
                    source_span_ids=["s1"], command_type="INVOKE_WORKER",
                    inputs=["purchase_request"], outputs=["procurement_category"],
                    integration_ref="NormalizeRequestWorker", kind="invoke",
                    handoff_id="handoff_normalize",
                ),
            ],
            "worker_normalize": [
                StepIR(
                    step_id="st_norm_1", text="Normalize purchase request",
                    source_span_ids=["s2"], command_type="GENERAL_COMMAND",
                    inputs=["purchase_request"], outputs=["procurement_category"],
                    flow_ref="main", block_ref="b_norm",
                ),
            ],
            "worker_vendor": [
                StepIR(
                    step_id="st_vendor_1", text="Identify eligible vendors",
                    source_span_ids=["s3"], command_type="GENERAL_COMMAND",
                    inputs=["procurement_category"], outputs=["eligible_vendor_pool"],
                    flow_ref="main", block_ref="b_vendor",
                ),
            ],
        },
    )

    with (
        patch.object(orchestrator, "_run_stage1", return_value=spans),
        patch.object(orchestrator, "_run_stage2", return_value=(routes, [])),
        patch.object(orchestrator, "_run_stage3", return_value=(spans, routes)),
        patch.object(orchestrator, "_run_stage3_5", return_value=plan),
        patch.object(orchestrator, "_run_stage4", return_value=flow_plan),
        patch.object(orchestrator, "_run_stage5", return_value=block_plan),
        patch.object(
            orchestrator, "_run_stage6_worker_scoped",
            return_value=(worker_scoped_resources, symbols, []),
        ),
        patch.object(
            orchestrator, "_run_stage7_worker_scoped",
            return_value=(worker_step_plan, symbols, []),
        ),
        patch.object(orchestrator, "_run_stage8", return_value=MagicMock()),
        patch.object(orchestrator, "_run_stage9", return_value=[]),
        patch.object(
            orchestrator, "_run_normalization_worker_scoped",
            return_value=(flow_plan, block_plan, worker_step_plan, symbols, [], []),
        ),
    ):
        result = orchestrator.run("Test enterprise procurement procedure.")

    # Verify child workers were assembled and rendered
    assert len(result.validation_errors) == 0
    # Stage 10/11 run unmocked, so SPL text is real
    assert "DEFINE_WORKER" in result.spl_text
    assert "NormalizeRequestWorker" in result.spl_text
    assert "VendorPoolWorker" in result.spl_text


def test_worker_aware_path_stores_all_intermediate_results(tmp_path: Path) -> None:
    """Verify worker-aware path stores complete intermediate result chain."""
    config = PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=tmp_path / "output",
        save_intermediate=False,
    )
    orchestrator = PipelineOrchestrator(config)

    spans = _make_enterprise_spans()
    routes = _make_enterprise_routes()
    plan = _make_enterprise_worker_plan()
    flow_plan = _make_enterprise_flow_plan()
    block_plan = _make_enterprise_block_plan()
    symbols = SymbolTable()

    worker_scoped_resources = WorkerScopedResourceIR(
        global_resources=ResourceRegistryIR(),
    )
    worker_step_plan = WorkerStepPlanIR(main_worker_id="worker_main")

    with (
        patch.object(orchestrator, "_run_stage1", return_value=spans),
        patch.object(orchestrator, "_run_stage2", return_value=(routes, [])),
        patch.object(orchestrator, "_run_stage3", return_value=(spans, routes)),
        patch.object(orchestrator, "_run_stage3_5", return_value=plan),
        patch.object(orchestrator, "_run_stage4", return_value=flow_plan),
        patch.object(orchestrator, "_run_stage5", return_value=block_plan),
        patch.object(
            orchestrator, "_run_stage6_worker_scoped",
            return_value=(worker_scoped_resources, symbols, []),
        ),
        patch.object(
            orchestrator, "_run_stage7_worker_scoped",
            return_value=(worker_step_plan, symbols, []),
        ),
        patch.object(orchestrator, "_run_stage8", return_value=MagicMock()),
        patch.object(orchestrator, "_run_stage9", return_value=[]),
        patch.object(
            orchestrator, "_run_normalization_worker_scoped",
            return_value=(flow_plan, block_plan, worker_step_plan, symbols, [], []),
        ),
        patch.object(orchestrator, "_run_stage10_worker_scoped", return_value=MagicMock()),
        patch.object(orchestrator, "_run_stage11", return_value=("SPL", [], [])),
    ):
        result = orchestrator.run("test")

    intermediates = result.intermediate_results

    # Verify complete chain of worker-aware intermediate results
    assert "stage3_5_worker_plan" in intermediates
    assert "stage4_worker_flows" in intermediates
    assert "stage5_worker_blocks" in intermediates
    assert "stage6_worker_scoped_resources" in intermediates
    assert "stage7_worker_step_plan" in intermediates
    assert "stage9_5_normalization" in intermediates
    assert "stage10_worker" in intermediates

    # T3: Worker-aware 路径不再产生 adapter intermediate records。
    # D6 保留 adapter 代码和 legacy path，但 worker-aware path 独立运作。

    # Verify types
    assert isinstance(intermediates["stage3_5_worker_plan"], WorkerPlanIR)
    assert isinstance(intermediates["stage4_worker_flows"], WorkerFlowPlanIR)
    assert isinstance(intermediates["stage5_worker_blocks"], WorkerBlockPlanIR)
    assert isinstance(intermediates["stage6_worker_scoped_resources"], WorkerScopedResourceIR)
    assert isinstance(intermediates["stage7_worker_step_plan"], WorkerStepPlanIR)

