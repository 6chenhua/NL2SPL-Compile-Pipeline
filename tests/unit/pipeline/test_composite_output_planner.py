"""
Unit tests for CompositeOutputPlanner.
"""

from __future__ import annotations

from nl2spl.ir import (
    StepIR,
    SymbolTable,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.stages.stage9_5_normalizer.composite_output_planner import (
    CompositeOutputPlanner,
)


def _setup_planner_context() -> tuple[SymbolTable, WorkerPlanIR]:
    symbols = SymbolTable()
    symbols.declare("assumptions_log", "text", "output", "assumptions log")
    symbols.declare("completion_status", "text", "output", "completion status")
    symbols.declare("request", "text", "input", "request")

    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker",
                owned_span_ids=["s20"],
                output_contract=["assumptions_log", "completion_status"],
            )
        ],
    )
    return symbols, worker_plan


def test_planner_single_output_no_plan() -> None:
    symbols, worker_plan = _setup_planner_context()
    step = StepIR(
        step_id="st7",
        text="Record assumptions",
        source_span_ids=["s20"],
        command_type="GENERAL_COMMAND",
        inputs=["request"],
        outputs=["assumptions_log"],
        block_ref="b1",
    )
    planner = CompositeOutputPlanner()
    result = planner.build_plans(
        steps=[step],
        symbol_table=symbols,
        relation_plan=None,
        worker_id="worker_main",
        worker_plan=worker_plan,
    )
    assert len(result.plans) == 0
    assert len(result.diagnostics) == 0


def test_planner_double_output_plan_generation() -> None:
    symbols, worker_plan = _setup_planner_context()
    step = StepIR(
        step_id="st7",
        text="Record assumptions and completion status",
        source_span_ids=["s20"],
        command_type="GENERAL_COMMAND",
        inputs=["request"],
        outputs=["assumptions_log", "completion_status"],
        block_ref="b1",
    )
    planner = CompositeOutputPlanner()
    result = planner.build_plans(
        steps=[step],
        symbol_table=symbols,
        relation_plan=None,
        worker_id="worker_main",
        worker_plan=worker_plan,
    )
    assert len(result.plans) == 1
    assert len(result.diagnostics) == 0

    plan = result.plans[0]
    assert plan.composite_variable_name == "assumptions_log_completion_status"
    assert plan.composite_type_name == "AssumptionsLogCompletionStatus"
    assert plan.projection_relations == ()


def test_planner_mechanical_name_rejected() -> None:
    symbols, worker_plan = _setup_planner_context()
    step = StepIR(
        step_id="st7",
        text="Record assumptions and completion status",
        source_span_ids=["s20"],
        command_type="GENERAL_COMMAND",
        inputs=["request"],
        outputs=["a", "b"],  # mechanical name should be rejected by policy
        block_ref="b1",
        metadata={
            "composite_output_debug": {
                "result_name": "main_st_7_result_structured",
                "type_name": "MainSt7ResultStructured",
            }
        },
    )
    planner = CompositeOutputPlanner()
    result = planner.build_plans(
        steps=[step],
        symbol_table=symbols,
        relation_plan=None,
        worker_id="worker_main",
        worker_plan=worker_plan,
    )
    assert len(result.plans) == 0
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].kind == "composite_name_policy_violation"


def test_planner_ignores_legacy_metadata_name_authority() -> None:
    symbols, worker_plan = _setup_planner_context()
    step = StepIR(
        step_id="st7",
        text="Record assumptions and completion status",
        source_span_ids=["s20"],
        command_type="GENERAL_COMMAND",
        inputs=["request"],
        outputs=["assumptions_log", "completion_status"],
        block_ref="b1",
        metadata={
            "structured_aggregation": {
                "result_name": "custom_record",
                "type_name": "CustomRecord",
            }
        },
    )
    planner = CompositeOutputPlanner()
    result = planner.build_plans(
        steps=[step],
        symbol_table=symbols,
        relation_plan=None,
        worker_id="worker_main",
        worker_plan=worker_plan,
    )
    assert len(result.plans) == 1
    assert result.plans[0].composite_variable_name == ("assumptions_log_completion_status")
    assert result.plans[0].composite_type_name == "AssumptionsLogCompletionStatus"
