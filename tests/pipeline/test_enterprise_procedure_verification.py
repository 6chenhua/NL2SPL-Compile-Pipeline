"""Enterprise-procedure verification: child worker assembly + render end-to-end.

Covers the full _build_child_worker → ChildWorkerIR → _render_child_worker
chain using data modelled after the enterprise-procedure use case.
"""

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import AlternativeFlow, ExceptionFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler
from nl2spl.pipeline.stages.stage11_spl_renderer import SPLRenderer


def _make_enterprise_worker_plan() -> WorkerPlanIR:
    """Worker plan modelled after enterprise-procedure Stage 3.5 output.

    Mirrors the structure: 1 main worker + 2 child workers
    (NormalizeRequestWorker, VendorPoolWorker).
    """
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Handle the end-to-end procurement process",
                owned_span_ids=[f"s{i}" for i in range(1, 37)],
                input_contract=[
                    ContractFieldIR(name="purchase_request", data_type="text", required=True, description="Purchase request", source="input"),
                    ContractFieldIR(name="requested_item_or_service", data_type="text", required=True, description="Requested item or service", source="input"),
                ],
                output_contract=[
                    ContractFieldIR(name="po_or_equivalent_issuance_artifact", data_type="text", required=True, description="PO issuance artifact", source="output"),
                    ContractFieldIR(name="audit_evidence_bundle", data_type="text", required=True, description="Audit evidence bundle", source="output"),
                ],
            ),
            WorkerSpecIR(
                worker_id="worker_normalize_request",
                worker_name="NormalizeRequestWorker",
                kind="child",
                purpose="Normalize the purchase request and determine the procurement category",
                owned_span_ids=["s16"],
                input_contract=[
                    ContractFieldIR(name="purchase_request", data_type="text", required=True, description="Purchase request", source="input"),
                    ContractFieldIR(name="requested_item_or_service", data_type="text", required=True, description="Requested item or service", source="input"),
                ],
                output_contract=[
                    ContractFieldIR(name="procurement_category", data_type="text", required=True, description="Procurement category", source="output"),
                ],
            ),
            WorkerSpecIR(
                worker_id="worker_vendor_pool",
                worker_name="VendorPoolWorker",
                kind="child",
                purpose="Identify eligible vendor pool based on procurement category",
                owned_span_ids=["s17"],
                input_contract=[
                    ContractFieldIR(name="procurement_category", data_type="text", required=True, description="Procurement category", source="input"),
                    ContractFieldIR(name="vendor_eligibility_context", data_type="text", required=True, description="Vendor eligibility context", source="input"),
                ],
                output_contract=[
                    ContractFieldIR(name="eligible_vendor_pool", data_type="text", required=True, description="Eligible vendor pool", source="output"),
                ],
            ),
        ],
        handoffs=[
            WorkerHandoffIR(
                handoff_id="handoff_normalize_request",
                from_worker="worker_main",
                to_worker="worker_normalize_request",
                api_ref=None,
                mode="invoke",
                condition_text=None,
                ordering="after",
            ),
            WorkerHandoffIR(
                handoff_id="handoff_vendor_pool",
                from_worker="worker_main",
                to_worker="worker_vendor_pool",
                api_ref=None,
                mode="invoke",
                condition_text=None,
                ordering="after",
            ),
        ],
    )


def _make_enterprise_flow_plan() -> WorkerFlowPlanIR:
    """Worker flow plan modelled after enterprise-procedure Stage 4 output."""
    return WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(
                main_flow_spans=[],
                exception_flows=[
                    ExceptionFlow(flow_id="exc_1", condition_text="Insufficient quotes", spans=[]),
                    ExceptionFlow(flow_id="exc_2", condition_text="Over-budget proposals", spans=[]),
                ],
            ),
            "worker_normalize_request": FlowStructureIR(
                main_flow_spans=["s16"],
            ),
            "worker_vendor_pool": FlowStructureIR(
                main_flow_spans=["s17"],
            ),
        }
    )


def _make_enterprise_block_plan() -> WorkerBlockPlanIR:
    """Worker block plan modelled after enterprise-procedure Stage 5 output."""
    return WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[],
                exception_flow_blocks={
                    "exc_1": [BlockIR(block_id="b_exc_1", block_type="SEQUENTIAL", spans=["s_main_exc_1"])],
                    "exc_2": [BlockIR(block_id="b_exc_2", block_type="SEQUENTIAL", spans=["s_main_exc_2"])],
                },
            ),
            "worker_normalize_request": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(block_id="b_1", block_type="SEQUENTIAL", spans=["s16"]),
                ],
            ),
            "worker_vendor_pool": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(block_id="b_1", block_type="SEQUENTIAL", spans=["s17"]),
                ],
            ),
        }
    )


def _make_enterprise_step_plan() -> WorkerStepPlanIR:
    """Step plan with child worker steps + main worker invoke steps.

    Main worker steps include INVOKE_WORKER commands targeting each child.
    Child worker steps reflect their respective subtask logic.
    """
    return WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(step_id="st_main_1", text="Invoke normalize request", source_span_ids=["s16"], command_type="INVOKE_WORKER", integration_ref="NormalizeRequestWorker"),
                StepIR(step_id="st_main_2", text="Invoke vendor pool", source_span_ids=["s17"], command_type="INVOKE_WORKER", integration_ref="VendorPoolWorker"),
                StepIR(step_id="st_main_exc_1", text="Handle insufficient quotes", source_span_ids=["s_main_exc_1"], command_type="GENERAL_COMMAND"),
                StepIR(step_id="st_main_exc_2", text="Handle over-budget", source_span_ids=["s_main_exc_2"], command_type="GENERAL_COMMAND"),
            ],
            "worker_normalize_request": [
                StepIR(step_id="st_norm_1", text="Parse and normalize request fields", source_span_ids=["s16"], command_type="GENERAL_COMMAND", inputs=["purchase_request"], outputs=["procurement_category"]),
                StepIR(step_id="st_norm_2", text="Look up procurement category", source_span_ids=["s16"], command_type="CALL_API", integration_ref="catalog_api", inputs=["requested_item_or_service"], outputs=["procurement_category"]),
            ],
            "worker_vendor_pool": [
                StepIR(step_id="st_vp_1", text="Query approved vendor registry", source_span_ids=["s17"], command_type="CALL_API", integration_ref="vendor_registry_api", inputs=["procurement_category", "vendor_eligibility_context"], outputs=["eligible_vendor_pool"]),
                StepIR(step_id="st_vp_2", text="Filter by policy constraints", source_span_ids=["s17"], command_type="GENERAL_COMMAND", inputs=["eligible_vendor_pool"], outputs=["eligible_vendor_pool"]),
            ],
        },
    )


class TestEnterpriseProcedureAssembly:
    """Verify WorkerAssembler produces correct ChildWorkerIR objects."""

    def test_assemble_produces_two_child_workers(self):
        assembler = WorkerAssembler()
        result = assembler.assemble_from_worker_scoped(
            _make_enterprise_step_plan(),
            ResourceRegistryIR(),
            SymbolTable(),
            _make_enterprise_worker_plan(),
            _make_enterprise_flow_plan(),
            _make_enterprise_block_plan(),
        )

        assert result.worker_name == "MainWorker"
        assert len(result.child_workers) == 2

        child_names = {cw.worker_name for cw in result.child_workers}
        assert child_names == {"NormalizeRequestWorker", "VendorPoolWorker"}

    def test_child_worker_has_main_flow_blocks(self):
        assembler = WorkerAssembler()
        result = assembler.assemble_from_worker_scoped(
            _make_enterprise_step_plan(),
            ResourceRegistryIR(),
            SymbolTable(),
            _make_enterprise_worker_plan(),
            _make_enterprise_flow_plan(),
            _make_enterprise_block_plan(),
        )

        normalize = next(cw for cw in result.child_workers if cw.worker_name == "NormalizeRequestWorker")
        assert len(normalize.main_flow.blocks) == 1
        assert normalize.main_flow.blocks[0].block_id == "b_1"
        assert normalize.main_flow.blocks[0].block_type == "SEQUENTIAL"

        vendor = next(cw for cw in result.child_workers if cw.worker_name == "VendorPoolWorker")
        assert len(vendor.main_flow.blocks) == 1
        assert vendor.main_flow.blocks[0].block_id == "b_1"

    def test_child_worker_has_steps(self):
        assembler = WorkerAssembler()
        result = assembler.assemble_from_worker_scoped(
            _make_enterprise_step_plan(),
            ResourceRegistryIR(),
            SymbolTable(),
            _make_enterprise_worker_plan(),
            _make_enterprise_flow_plan(),
            _make_enterprise_block_plan(),
        )

        normalize = next(cw for cw in result.child_workers if cw.worker_name == "NormalizeRequestWorker")
        assert len(normalize.steps) == 2
        assert normalize.steps[0].step_id == "st_norm_1"
        assert normalize.steps[1].step_id == "st_norm_2"

        vendor = next(cw for cw in result.child_workers if cw.worker_name == "VendorPoolWorker")
        assert len(vendor.steps) == 2
        assert vendor.steps[0].command_type == "CALL_API"
        assert vendor.steps[1].command_type == "GENERAL_COMMAND"

    def test_child_worker_has_api_refs(self):
        assembler = WorkerAssembler()
        result = assembler.assemble_from_worker_scoped(
            _make_enterprise_step_plan(),
            ResourceRegistryIR(),
            SymbolTable(),
            _make_enterprise_worker_plan(),
            _make_enterprise_flow_plan(),
            _make_enterprise_block_plan(),
        )

        normalize = next(cw for cw in result.child_workers if cw.worker_name == "NormalizeRequestWorker")
        assert "catalog_api" in normalize.api_refs

        vendor = next(cw for cw in result.child_workers if cw.worker_name == "VendorPoolWorker")
        assert "vendor_registry_api" in vendor.api_refs

    def test_child_worker_has_inputs_outputs(self):
        assembler = WorkerAssembler()
        result = assembler.assemble_from_worker_scoped(
            _make_enterprise_step_plan(),
            ResourceRegistryIR(),
            SymbolTable(),
            _make_enterprise_worker_plan(),
            _make_enterprise_flow_plan(),
            _make_enterprise_block_plan(),
        )

        normalize = next(cw for cw in result.child_workers if cw.worker_name == "NormalizeRequestWorker")
        assert len(normalize.inputs) == 2
        assert normalize.inputs[0].name == "purchase_request"
        assert len(normalize.outputs) == 1
        assert normalize.outputs[0].name == "procurement_category"

    def test_main_worker_has_exception_flows(self):
        assembler = WorkerAssembler()
        result = assembler.assemble_from_worker_scoped(
            _make_enterprise_step_plan(),
            ResourceRegistryIR(),
            SymbolTable(),
            _make_enterprise_worker_plan(),
            _make_enterprise_flow_plan(),
            _make_enterprise_block_plan(),
        )

        # Main worker should have exception flows from enterprise data
        assert len(result.exception_flows) == 2
        exc_ids = {ef.flow_id for ef in result.exception_flows}
        assert exc_ids == {"exc_1", "exc_2"}


class TestEnterpriseProcedureRender:
    """Verify SPLRenderer renders child workers with full flow/steps."""

    def test_render_child_worker_normalize_request(self):
        """NormalizeRequestWorker should render with SEQUENTIAL block and actual steps."""
        assembler = WorkerAssembler()
        worker_ir = assembler.assemble_from_worker_scoped(
            _make_enterprise_step_plan(),
            ResourceRegistryIR(),
            SymbolTable(),
            _make_enterprise_worker_plan(),
            _make_enterprise_flow_plan(),
            _make_enterprise_block_plan(),
        )

        renderer = SPLRenderer()
        normalize = next(cw for cw in worker_ir.child_workers if cw.worker_name == "NormalizeRequestWorker")
        result = renderer._render_child_worker(normalize)
        text = "\n".join(result)

        # Worker header
        assert "[DEFINE_WORKER:" in text
        assert "NormalizeRequestWorker" in text

        # Inputs / Outputs
        assert "[INPUTS]" in text
        assert "purchase_request" in text

        # Main flow with actual blocks (NOT synthetic st_child fallback)
        assert "[MAIN_FLOW]" in text
        assert "[SEQUENTIAL_BLOCK]" in text
        assert "[END_SEQUENTIAL_BLOCK]" in text
        assert "[END_MAIN_FLOW]" in text

        # Actual step text should be present
        assert "Parse and normalize request fields" in text

        # CALL_API step
        assert "[CALL catalog_api" in text

        assert "[END_WORKER]" in text

    def test_render_child_worker_vendor_pool(self):
        """VendorPoolWorker should render with SEQUENTIAL block and CALL_API."""
        assembler = WorkerAssembler()
        worker_ir = assembler.assemble_from_worker_scoped(
            _make_enterprise_step_plan(),
            ResourceRegistryIR(),
            SymbolTable(),
            _make_enterprise_worker_plan(),
            _make_enterprise_flow_plan(),
            _make_enterprise_block_plan(),
        )

        renderer = SPLRenderer()
        vendor = next(cw for cw in worker_ir.child_workers if cw.worker_name == "VendorPoolWorker")
        result = renderer._render_child_worker(vendor)
        text = "\n".join(result)

        assert "[DEFINE_WORKER:" in text
        assert "VendorPoolWorker" in text
        assert "[MAIN_FLOW]" in text
        assert "[SEQUENTIAL_BLOCK]" in text

        # CALL_API step
        assert "[CALL vendor_registry_api" in text
        # GENERAL_COMMAND step
        assert "Filter by policy constraints" in text

        assert "[END_WORKER]" in text

    def test_render_child_worker_no_synthetic_st_child(self):
        """When blocks exist, synthetic st_child fallback must NOT be used."""
        assembler = WorkerAssembler()
        worker_ir = assembler.assemble_from_worker_scoped(
            _make_enterprise_step_plan(),
            ResourceRegistryIR(),
            SymbolTable(),
            _make_enterprise_worker_plan(),
            _make_enterprise_flow_plan(),
            _make_enterprise_block_plan(),
        )

        renderer = SPLRenderer()
        for child in worker_ir.child_workers:
            result = renderer._render_child_worker(child)
            text = "\n".join(result)
            # The synthetic st_child is a fallback for when blocks are empty.
            # Since both child workers have blocks, st_child should NOT appear.
            assert "st_child" not in text, f"{child.worker_name} should not use synthetic st_child"


class TestEnterpriseProcedureAlternativeExceptionFlows:
    """Verify alternative_flows and exception_flows rendering end-to-end."""

    def test_render_child_worker_with_alternative_flows(self):
        """Child worker with alternative_flows renders ALTERNATIVE_FLOW blocks."""
        worker_plan = WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(worker_id="w_main", worker_name="MainWorker", kind="main", purpose="Main"),
                WorkerSpecIR(worker_id="w_child", worker_name="ReviewWorker", kind="child", purpose="Review and approve requests"),
            ],
            handoffs=[
                WorkerHandoffIR(handoff_id="h1", from_worker="w_main", to_worker="w_child", api_ref=None, mode="invoke", condition_text=None, ordering="after"),
            ],
        )
        step_plan = WorkerStepPlanIR(
            main_worker_id="w_main",
            worker_steps={
                "w_main": [StepIR(step_id="st1", text="Invoke review", source_span_ids=["s1"], command_type="INVOKE_WORKER", integration_ref="ReviewWorker")],
                "w_child": [
                    StepIR(step_id="st_c1", text="Standard review", source_span_ids=["s_child_1"], command_type="GENERAL_COMMAND", inputs=["request"], outputs=["decision"]),
                    StepIR(step_id="st_c2", text="Escalated review", source_span_ids=["s_child_2"], command_type="GENERAL_COMMAND", inputs=["request"], outputs=["decision"]),
                ],
            },
        )
        flow_plan = WorkerFlowPlanIR(
            worker_flows={
                "w_child": FlowStructureIR(
                    main_flow_spans=["s_child_1"],
                    alternative_flows=[
                        AlternativeFlow(flow_id="alt_high_value", condition_text="high value request", spans=["s_child_2"]),
                    ],
                ),
            }
        )
        block_plan = WorkerBlockPlanIR(
            worker_blocks={
                "w_child": BlockStructureIR(
                    main_flow_blocks=[BlockIR(block_id="b_main", block_type="SEQUENTIAL", spans=["s_child_1"])],
                    alternative_flow_blocks={
                        "alt_high_value": [BlockIR(block_id="b_alt", block_type="IF", condition_text="high value request", spans=["s_child_2"])],
                    },
                ),
            }
        )

        assembler = WorkerAssembler()
        worker_ir = assembler.assemble_from_worker_scoped(
            step_plan, ResourceRegistryIR(), SymbolTable(), worker_plan, flow_plan, block_plan
        )

        renderer = SPLRenderer()
        child = worker_ir.child_workers[0]
        result = renderer._render_child_worker(child)
        text = "\n".join(result)

        assert "[ALTERNATIVE_FLOW:" in text
        assert "high value request" in text
        assert "[END_ALTERNATIVE_FLOW]" in text
        assert "Escalated review" in text
        assert "Standard review" in text

    def test_render_child_worker_with_exception_flows(self):
        """Child worker with exception_flows renders EXCEPTION_FLOW blocks."""
        worker_plan = WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(worker_id="w_main", worker_name="MainWorker", kind="main", purpose="Main"),
                WorkerSpecIR(worker_id="w_child", worker_name="PaymentWorker", kind="child", purpose="Process payment"),
            ],
            handoffs=[
                WorkerHandoffIR(handoff_id="h1", from_worker="w_main", to_worker="w_child", api_ref=None, mode="invoke", condition_text=None, ordering="after"),
            ],
        )
        step_plan = WorkerStepPlanIR(
            main_worker_id="w_main",
            worker_steps={
                "w_main": [StepIR(step_id="st1", text="Invoke payment", source_span_ids=["s1"], command_type="INVOKE_WORKER", integration_ref="PaymentWorker")],
                "w_child": [
                    StepIR(step_id="st_p1", text="Authorize payment", source_span_ids=["s_pay_1"], command_type="GENERAL_COMMAND", inputs=["amount"], outputs=["auth_code"]),
                    StepIR(step_id="st_p2", text="Handle payment timeout", source_span_ids=["s_pay_2"], command_type="GENERAL_COMMAND"),
                    StepIR(step_id="st_p3", text="Handle insufficient funds", source_span_ids=["s_pay_3"], command_type="GENERAL_COMMAND"),
                ],
            },
        )
        flow_plan = WorkerFlowPlanIR(
            worker_flows={
                "w_child": FlowStructureIR(
                    main_flow_spans=["s_pay_1"],
                    exception_flows=[
                        ExceptionFlow(flow_id="exc_timeout", condition_text="payment gateway timeout", spans=["s_pay_2"]),
                        ExceptionFlow(flow_id="exc_no_funds", condition_text="insufficient funds", spans=["s_pay_3"]),
                    ],
                ),
            }
        )
        block_plan = WorkerBlockPlanIR(
            worker_blocks={
                "w_child": BlockStructureIR(
                    main_flow_blocks=[BlockIR(block_id="b_main", block_type="SEQUENTIAL", spans=["s_pay_1"])],
                    exception_flow_blocks={
                        "exc_timeout": [BlockIR(block_id="b_exc_1", block_type="SEQUENTIAL", spans=["s_pay_2"])],
                        "exc_no_funds": [BlockIR(block_id="b_exc_2", block_type="SEQUENTIAL", spans=["s_pay_3"])],
                    },
                ),
            }
        )

        assembler = WorkerAssembler()
        worker_ir = assembler.assemble_from_worker_scoped(
            step_plan, ResourceRegistryIR(), SymbolTable(), worker_plan, flow_plan, block_plan
        )

        renderer = SPLRenderer()
        child = worker_ir.child_workers[0]
        result = renderer._render_child_worker(child)
        text = "\n".join(result)

        assert "[EXCEPTION_FLOW:" in text
        assert "[END_EXCEPTION_FLOW]" in text
        assert "payment gateway timeout" in text
        assert "insufficient funds" in text
        assert "Handle payment timeout" in text
        assert "Handle insufficient funds" in text

    def test_child_worker_fallback_when_no_blocks(self):
        """When blocks are absent, fallback to synthetic st_child (compatibility)."""
        worker_plan = WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(worker_id="w_main", worker_name="MainWorker", kind="main", purpose="Main"),
                WorkerSpecIR(worker_id="w_child", worker_name="LegacyWorker", kind="child", purpose="Legacy task"),
            ],
            handoffs=[
                WorkerHandoffIR(handoff_id="h1", from_worker="w_main", to_worker="w_child", api_ref=None, mode="invoke", condition_text=None, ordering="after"),
            ],
        )
        step_plan = WorkerStepPlanIR(
            main_worker_id="w_main",
            worker_steps={
                "w_main": [StepIR(step_id="st1", text="Invoke legacy", source_span_ids=["s1"], command_type="INVOKE_WORKER", integration_ref="LegacyWorker")],
                "w_child": [
                    StepIR(step_id="st_legacy_1", text="Do legacy work", source_span_ids=["s_legacy"], command_type="GENERAL_COMMAND"),
                ],
            },
        )

        assembler = WorkerAssembler()
        # No flow/block plan → blocks will be empty
        worker_ir = assembler.assemble_from_worker_scoped(
            step_plan, ResourceRegistryIR(), SymbolTable(), worker_plan
        )

        renderer = SPLRenderer()
        child = worker_ir.child_workers[0]
        result = renderer._render_child_worker(child)
        text = "\n".join(result)

        # Fallback: synthetic st_child in SEQUENTIAL_BLOCK
        assert "[MAIN_FLOW]" in text
        assert "[SEQUENTIAL_BLOCK]" in text
        assert "[END_SEQUENTIAL_BLOCK]" in text
        assert "[END_MAIN_FLOW]" in text
