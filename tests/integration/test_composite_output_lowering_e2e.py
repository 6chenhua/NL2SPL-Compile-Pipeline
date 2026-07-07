"""
Integration test for the entire composite output lowering end-to-end pipeline.
"""

from __future__ import annotations

from nl2spl.ir import (
    BlockIR,
    BlockStructureIR,
    FlowStructureIR,
    ResourceRegistryIR,
    StepIR,
    StepVariableRelation,
    StepVariableRelationPlan,
    SymbolTable,
    VariableSpec,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.worker_ir import FlowRef, WorkerIR
from nl2spl.pipeline.stages.stage9_5_normalizer.normalizer import IRNormalizer
from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import SPLRenderer
from nl2spl.validator.static_validator import StaticValidator


def test_composite_output_lowering_e2e_pipeline() -> None:
    # 1. Setup initial IR state prior to Stage 9.5
    symbols = SymbolTable()
    symbols.declare("request", "text", "input", "The request")
    symbols.declare("assumptions_log", "text", "output", "Assumptions log")
    symbols.declare("completion_status", "text", "output", "Completion status")

    resources = ResourceRegistryIR()
    resources.variables.extend(
        [
            VariableSpec(
                name="request",
                data_type="text",
                required=True,
                source="input",
                description="The request",
            ),
            VariableSpec(
                name="assumptions_log",
                data_type="text",
                required=True,
                source="output",
                description="Assumptions log",
            ),
            VariableSpec(
                name="completion_status",
                data_type="text",
                required=True,
                source="output",
                description="Completion status",
            ),
        ]
    )

    step = StepIR(
        step_id="st7",
        text="Record assumptions and completion status",
        source_span_ids=["s20"],
        command_type="GENERAL_COMMAND",
        inputs=["request"],
        outputs=["assumptions_log", "completion_status"],
        block_ref="b1",
    )
    consumer = StepIR(
        step_id="st8",
        text="Review assumptions",
        source_span_ids=["s21"],
        command_type="GENERAL_COMMAND",
        inputs=["assumptions_log"],
        outputs=[],
        block_ref="b1",
    )

    relation_plan = StepVariableRelationPlan(
        relations=(
            StepVariableRelation(
                step_id="st7",
                variable_name="assumptions_log",
                relation="produces",
                source_span_ids=("s20",),
                evidence_kind="source_text",
            ),
            StepVariableRelation(
                step_id="st7",
                variable_name="completion_status",
                relation="produces",
                source_span_ids=("s20",),
                evidence_kind="source_text",
            ),
            StepVariableRelation(
                step_id="st8",
                variable_name="assumptions_log",
                relation="consumes",
                source_span_ids=("s21",),
                evidence_kind="source_text",
            ),
        )
    )

    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker",
                owned_span_ids=["s20", "s21"],
                output_contract=["assumptions_log", "completion_status"],
            )
        ],
    )

    step_plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step, consumer]},
        step_variable_relation_plan=relation_plan,
    )

    flow_plan = WorkerFlowPlanIR({"worker_main": FlowStructureIR(["s20", "s21"])})
    block_plan = WorkerBlockPlanIR(
        {"worker_main": BlockStructureIR([BlockIR("b1", "SEQUENTIAL", spans=["s20", "s21"])])}
    )

    # 2. Execute Stage 9.5 Normalizer
    _, _, normalized_step_plan, normalized_symbols, errors, warnings = (
        IRNormalizer().normalize_worker_scoped(
            flow_plan,
            block_plan,
            step_plan,
            worker_plan,
            resources,
            symbols,
        )
    )

    assert not errors
    assert len(normalized_step_plan.composite_output_plans) == 1
    plan = normalized_step_plan.composite_output_plans[0]
    assert plan.composite_variable_name == "assumptions_log_completion_status"

    # 3. Assemble WorkerIR (equivalent to Stage 10)
    worker_ir = WorkerIR(
        worker_name="MainWorker",
        description="Main worker description",
        inputs=[var for var in resources.variables if var.source == "input"],
        outputs=[var for var in resources.variables if var.source == "output"],
        steps=normalized_step_plan.worker_steps["worker_main"],
        main_flow=FlowRef(
            blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s20", "s21"])]
        )
        if hasattr(normalized_step_plan, "worker_steps")
        else FlowRef(),
    )
    worker_ir.main_flow = FlowRef(
        blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s20", "s21"])]
    )

    profile = AgentProfileIR(
        persona=PersonaIR(role="Assistant", aspects=[]),
        audience_aspects=[],
        concepts=[],
    )

    # 4. Execute Stage 11 Renderer
    spl_text, render_errors, render_warnings = SPLRenderer().render(
        worker_ir,
        profile,
        resources,
        normalized_symbols,
        normalized_step_plan.worker_steps["worker_main"],
        [],
    )

    assert not render_errors

    # 5. Verify rendered SPL structural constraints
    assert "[DEFINE_TYPES:]" in spl_text
    assert (
        "AssumptionsLogCompletionStatus = { assumptions_log: text, completion_status: text }"
    ) in spl_text
    assert "[DEFINE_VARIABLES:]" in spl_text

    types_pos = spl_text.index("[DEFINE_TYPES:]")
    vars_pos = spl_text.index("[DEFINE_VARIABLES:]")
    assert types_pos < vars_pos

    assert (
        "RESULT assumptions_log_completion_status: AssumptionsLogCompletionStatus SET"
    ) in spl_text
    assert (
        "Review assumptions based on <REF>assumptions_log_completion_status.assumptions_log</REF>"
    ) in spl_text

    # 6. Run StaticValidator on the generated SPL text
    validation_res = StaticValidator().validate(spl_text)
    assert validation_res.is_valid
    assert not validation_res.errors
