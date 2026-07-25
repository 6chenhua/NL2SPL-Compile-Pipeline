"""Resource contract integration tests for Stage 3.5 materialization."""

from __future__ import annotations

from nl2spl.ir.worker_plan_ir import ContractFieldIR
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
    WorkerPlanMaterializer,
)


def test_main_worker_contract_keeps_resource_contract_demands_without_hard_facts() -> None:
    """Phase 3 gate: ResourceContractPlan demands populate main worker contract."""
    demand_input = ContractFieldIR(
        name="",
        data_type="",
        required=True,
        description="Topic summary",
        source="input",
        contract_demand_id="rcd_input_s8",
        source_span_ids=["s8"],
    )
    demand_output = ContractFieldIR(
        name="",
        data_type="",
        required=True,
        description="Finished draft (Word or Google Doc)",
        source="output",
        contract_demand_id="rcd_output_s11",
        source_span_ids=["s11"],
    )

    plan, warnings = WorkerPlanMaterializer().materialize(
        candidates=[],
        decisions=[],
        hard_fact_inputs=[],
        hard_fact_outputs=[],
        demand_inputs=[demand_input],
        demand_outputs=[demand_output],
    )

    assert warnings == []
    assert [f.contract_demand_id for f in plan.main_worker.input_contract] == [
        "rcd_input_s8",
    ]
    assert [f.contract_demand_id for f in plan.main_worker.output_contract] == [
        "rcd_output_s11",
    ]


def test_main_worker_contract_deduplicates_same_named_output_evidence() -> None:
    explicit_output = ContractFieldIR(
        name="final_response",
        data_type="text",
        required=True,
        description="Required final response",
        source="output",
        contract_demand_id="rcd_output_required",
        source_span_ids=["s10"],
        requiredness="required",
    )
    process_output = ContractFieldIR(
        name="final_response",
        data_type="text",
        required=False,
        description="Output the final response",
        source="output",
        contract_demand_id="rcd_output_process",
        source_span_ids=["s20"],
        requiredness="optional",
    )

    plan, warnings = WorkerPlanMaterializer().materialize(
        candidates=[],
        decisions=[],
        demand_outputs=[explicit_output, process_output],
    )

    assert warnings == []
    assert len(plan.main_worker.output_contract) == 1
    field = plan.main_worker.output_contract[0]
    assert field.name == "final_response"
    assert field.required is True
    assert field.requiredness == "required"
    assert field.contract_demand_id == "rcd_output_required"
    assert field.source_span_ids == ["s10", "s20"]
