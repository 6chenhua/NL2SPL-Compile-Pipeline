from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import AlternativeFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler


def test_alternative_flow_blocks_can_be_keyed_by_control_region() -> None:
    worker_plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[
            WorkerSpecIR(
                worker_id="w_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker",
            ),
        ],
    )
    step_plan = WorkerStepPlanIR(
        main_worker_id="w_main",
        worker_steps={
            "w_main": [
                StepIR(
                    step_id="st_alt",
                    text="Revise draft",
                    source_span_ids=["s21"],
                    command_type="GENERAL_COMMAND",
                    flow_ref="alt_1",
                    block_ref="b_cr_top_alt_s21",
                ),
            ],
        },
    )
    flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "w_main": FlowStructureIR(
                alternative_flows=[
                    AlternativeFlow(
                        flow_id="alt_1",
                        condition_text="the user asks for revision",
                        spans=["s21"],
                    )
                ],
            )
        }
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "w_main": BlockStructureIR(
                alternative_flow_blocks={
                    "cr_top_alt_s21": [
                        BlockIR(
                            block_id="b_cr_top_alt_s21",
                            block_type="IF",
                            condition_text="the user asks for revision",
                            spans=["s21"],
                        )
                    ]
                }
            )
        }
    )

    result = WorkerAssembler().assemble_from_worker_scoped(
        step_plan,
        ResourceRegistryIR(),
        SymbolTable(),
        worker_plan,
        flow_plan,
        block_plan,
    )

    assert len(result.alternative_flows) == 1
    assert result.alternative_flows[0].flow_id == "alt_1"
    assert result.alternative_flows[0].blocks[0].block_id == "b_cr_top_alt_s21"
