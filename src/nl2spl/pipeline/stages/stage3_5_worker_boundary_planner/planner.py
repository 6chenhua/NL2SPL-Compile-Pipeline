"""Stage 3.5: WorkerBoundaryPlanner - propose worker boundaries before flow assembly."""

from __future__ import annotations

from nl2spl.ir.worker_plan_ir import WorkerPlanIR
from nl2spl.pipeline.stages.base import PipelineStage
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.decision_validator import (
    DecisionValidatorMixin,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.executor import (
    ExecutorMixin,
    PlannerInput,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.plan_parser import (
    PlanParserMixin,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.prompt_builder import (
    PromptBuilderMixin,
)


class WorkerBoundaryPlanner(
    ExecutorMixin,
    PromptBuilderMixin,
    PlanParserMixin,
    DecisionValidatorMixin,
    PipelineStage[PlannerInput, WorkerPlanIR],
):
    """Plan first-class worker boundaries using compact span and adapter context."""

    _CANDIDATE_BLOCKING_RISKS: set[str] = {
        "insufficient_semantic_boundary",
        "over_fragmentation",
        "ordinary_sequential_step",
        "simple_control_flow",
        "policy_or_constraint",
        "alternative_flow",
        "exception_flow",
        "failure_recovery_protocol",
        "single_api_call",
    }
    _PROMOTION_INCOMPLETENESS_RISKS: set[str] = {
        "no_clear_input_contract",
        "no_clear_output_contract",
        "no_parent_invocation_point",
        "unclear_result_handoff",
    }
    _REJECTION_REASONS: set[str] = _CANDIDATE_BLOCKING_RISKS | _PROMOTION_INCOMPLETENESS_RISKS
    _BLOCKING_RISKS = _CANDIDATE_BLOCKING_RISKS

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage3_5_worker_boundary_planner"
