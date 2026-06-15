from __future__ import annotations

from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR
from nl2spl.pipeline.stages.stage10_worker_assembler.assembler import WorkerAssembler
from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import SPLRenderer


def test_partial_child_worker_skeleton_renders_without_executable_invoke() -> None:
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Coordinate the workflow.",
                owned_span_ids=["s1"],
                input_contract=[],
                output_contract=[],
                boundary_kind="main_worker",
            ),
            WorkerSpecIR(
                worker_id="worker_child",
                worker_name="PartialChild",
                kind="child",
                purpose="Perform the delegated subtask.",
                owned_span_ids=["s2"],
                input_contract=[],
                output_contract=[],
                input_contract_status="unknown",
                output_contract_status="unknown",
                boundary_kind="bounded_subtask",
                reason="Accepted child worker with unresolved contract.",
                partial_reason="partial_contract_unknown",
            ),
        ],
        handoffs=[],
    )

    worker_ir = WorkerAssembler().assemble(
        flow=FlowStructureIR(main_flow_spans=["s1"]),
        blocks=BlockStructureIR(),
        steps=[],
        resources=ResourceRegistryIR(),
        symbol_table=SymbolTable(),
        worker_plan=worker_plan,
    )
    spl_text, errors, _warnings = SPLRenderer().render(
        worker_ir,
        AgentProfileIR(persona=PersonaIR(role="Test agent")),
        ResourceRegistryIR(),
        SymbolTable(),
        [],
        [],
    )

    assert errors == []
    assert "PartialChild" in worker_ir.child_worker_refs
    assert len(worker_ir.child_workers) == 1
    assert worker_ir.child_workers[0].inputs == []
    assert worker_ir.child_workers[0].outputs == []
    assert '[DEFINE_WORKER: "Perform the delegated subtask." PartialChild]' in spl_text
    assert "[INPUTS]\n        [END_INPUTS]" in spl_text
    assert "[OUTPUTS]\n        [END_OUTPUTS]" in spl_text
    assert "[INVOKE" not in spl_text
    assert "COMMAND-" not in spl_text
