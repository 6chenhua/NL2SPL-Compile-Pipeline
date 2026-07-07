from __future__ import annotations

from nl2spl.compiler.producer_index import ProducerIndex
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
from nl2spl.pipeline.stages.stage9_5_normalizer import IRNormalizer


def _symbols_and_resources() -> tuple[SymbolTable, ResourceRegistryIR]:
    symbols = SymbolTable()
    resources = ResourceRegistryIR()
    for name, data_type in (
        ("request", "text"),
        ("assumptions_log", "List [text]"),
        ("completion_status", "text"),
    ):
        source = "input" if name == "request" else "output"
        symbols.declare(name, data_type, source, f"{name} variable")
        resources.variables.append(
            VariableSpec(
                name=name,
                data_type=data_type,
                required=True,
                description=f"{name} variable",
                source=source,
            )
        )
    return symbols, resources


def test_stage9_5_lowers_multi_output_step_to_composite_artifact() -> None:
    symbols, resources = _symbols_and_resources()
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
                output_contract=[],
            )
        ],
    )
    step_plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={"worker_main": [step, consumer]},
        step_variable_relation_plan=relation_plan,
    )

    _, _, normalized, normalized_symbols, errors, warnings = IRNormalizer().normalize_worker_scoped(
        WorkerFlowPlanIR({"worker_main": FlowStructureIR(["s20", "s21"])}),
        WorkerBlockPlanIR(
            {"worker_main": BlockStructureIR([BlockIR("b1", "SEQUENTIAL", spans=["s20", "s21"])])}
        ),
        step_plan,
        worker_plan,
        resources,
        symbols,
    )

    assert errors == []
    assert warnings
    lowered_step = normalized.worker_steps["worker_main"][0]
    composite_name = lowered_step.outputs[0]
    assert lowered_step.outputs == ["assumptions_log_completion_status"]
    assert normalized.worker_steps["worker_main"][1].inputs == [f"{composite_name}.assumptions_log"]
    assert len(normalized.composite_output_plans) == 1
    plan = normalized.composite_output_plans[0]
    assert plan.composite_variable_name == composite_name
    assert plan.composite_type_name == "AssumptionsLogCompletionStatus"
    assert [field.original_field_name for field in plan.field_mappings] == [
        "assumptions_log",
        "completion_status",
    ]
    assert {variable.name for variable in resources.variables} == {
        "request",
        composite_name,
    }
    assert "assumptions_log" not in normalized_symbols.variables
    assert "completion_status" not in normalized_symbols.variables
    assert composite_name in normalized_symbols.variables
    assert any(type_spec.type_name == plan.composite_type_name for type_spec in resources.types)
    assert normalized.step_variable_relation_plan is not None
    produced = {
        relation.variable_name
        for relation in normalized.step_variable_relation_plan.producing_relations()
    }
    assert produced == {composite_name}

    index = ProducerIndex(
        steps=normalized.get_all_steps(),
        step_variable_relation_plan=normalized.step_variable_relation_plan,
    )
    assert index.is_produced(composite_name)
    assert not index.is_produced("assumptions_log")
    assert not index.is_produced("completion_status")
