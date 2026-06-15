"""WorkerPlanIR assembly tests for Stage 10."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    InputBindingIR,
    OutputBindingIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler


def field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(name, "text", True, f"{name} field", source)  # type: ignore[arg-type]


def test_worker_assembler_uses_worker_plan_contracts() -> None:
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                "worker_main",
                "CoordinatorWorker",
                "main",
                "Coordinate request",
                owned_span_ids=["s1"],
                input_contract=[field("user_request")],
                output_contract=[field("draft", "output")],
                boundary_kind="main_worker",
            ),
            WorkerSpecIR(
                "worker_child",
                "SourceWorker",
                "child",
                "Gather sources",
                owned_span_ids=["s2"],
                input_contract=[field("source_request")],
                output_contract=[field("source_evidence", "output")],
                boundary_kind="bounded_subtask",
            ),
            WorkerSpecIR(
                "worker_unused",
                "UnusedWorker",
                "child",
                "Render from WorkerSpecIR even without a handoff",
                owned_span_ids=["s3"],
                input_contract=[field("unused_input")],
                output_contract=[field("unused_output", "output")],
                boundary_kind="bounded_subtask",
            ),
        ],
        handoffs=[
            WorkerHandoffIR(
                "h1",
                "worker_main",
                "worker_child",
                None,
                "invoke",
                None,
                "conditional",
                input_bindings=[InputBindingIR("user_request", "source_request", True)],
                output_bindings=[OutputBindingIR("source_evidence", "evidence", True, "set")],
            )
        ],
    )
    steps = [
        StepIR(
            "st1",
            "Gather source evidence",
            ["s1"],
            "INVOKE_WORKER",
            inputs=["user_request"],
            outputs=["evidence"],
            integration_ref="SourceWorker",
            kind="invoke",
        )
    ]

    worker = WorkerAssembler().assemble(
        FlowStructureIR(main_flow_spans=["s1"]),
        BlockStructureIR([BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
        steps,
        ResourceRegistryIR(),
        SymbolTable(),
        plan,
    )

    assert worker.worker_name == "CoordinatorWorker"
    assert worker.inputs[0].name == "user_request"
    assert worker.outputs[0].name == "draft"
    assert worker.child_worker_refs == ["SourceWorker", "UnusedWorker"]
    assert [child.worker_name for child in worker.child_workers] == [
        "SourceWorker",
        "UnusedWorker",
    ]

    source_child = worker.child_workers[0]
    unused_child = worker.child_workers[1]
    assert source_child.inputs[0].name == "source_request"
    assert source_child.outputs[0].name == "source_evidence"
    assert unused_child.inputs[0].name == "unused_input"
    assert unused_child.outputs[0].name == "unused_output"
