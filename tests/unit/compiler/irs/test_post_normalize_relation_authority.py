from __future__ import annotations

from nl2spl.compiler.irs.factory import build_irs_subsystem
from nl2spl.compiler.irs.policy import IRSRuntimeConfig
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.step_variable_relation_ir import (
    StepVariableRelation,
    StepVariableRelationPlan,
)
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)


def test_post_normalize_required_output_uses_relation_plan_authority() -> None:
    worker = WorkerIR(worker_name="MainWorker", description="Main worker")
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker",
                owned_span_ids=["s1"],
                output_contract=[
                    ContractFieldIR(
                        name="required_result",
                        data_type="text",
                        required=True,
                        description="Required result.",
                        source="output",
                    )
                ],
            )
        ],
    )
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_1",
                    text="Produce a required result.",
                    source_span_ids=["s1"],
                    command_type="GENERAL_COMMAND",
                    outputs=["required_result"],
                )
            ]
        },
        step_variable_relation_plan=StepVariableRelationPlan(
            relations=(
                StepVariableRelation(
                    step_id="st_1",
                    variable_name="different_result",
                    relation="produces",
                    source_span_ids=("s1",),
                    evidence_kind="source_text",
                ),
            )
        ),
    )

    result = build_irs_subsystem(IRSRuntimeConfig()).run_post_normalize_result(
        worker=worker,
        worker_plan=worker_plan,
        worker_steps=worker_steps,
    )

    diagnostics = [diag for diag in result.diagnostics if diag.target_ref]
    assert any(
        diag.kind == "missing_output_producer"
        and diag.target_ref == "worker:worker_main.output:required_result"
        for diag in diagnostics
    )
