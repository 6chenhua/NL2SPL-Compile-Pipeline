"""
Structural normalization methods for Stage 9.5 IRNormalizer.
This module is a thin adapter delegating to CompositeOutputPlanner and CompositeOutputPlanApplier.
"""

from __future__ import annotations

from nl2spl.ir import (
    ResourceRegistryIR,
    StepIR,
    StepVariableRelationPlan,
    SymbolTable,
    WorkerPlanIR,
)


class NormalizationMixin:
    """Deterministic structural normalization helpers for IRNormalizer (thin adapter)."""

    def _normalize_multi_output_steps(
        self,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
        worker_id: str | None = None,
        worker_plan: WorkerPlanIR | None = None,
        relation_plan: StepVariableRelationPlan | None = None,
    ) -> list[str]:
        from nl2spl.pipeline.stages.stage9_5_normalizer.composite_output_applier import (
            CompositeOutputPlanApplier,
        )
        from nl2spl.pipeline.stages.stage9_5_normalizer.composite_output_planner import (
            CompositeOutputPlanner,
        )

        warnings: list[str] = []
        planner = CompositeOutputPlanner()
        applier = CompositeOutputPlanApplier()

        planning_result = planner.build_plans(
            steps=steps,
            symbol_table=symbol_table,
            relation_plan=relation_plan,
            worker_id=worker_id or "",
            worker_plan=worker_plan or WorkerPlanIR(),
        )

        for diag in planning_result.diagnostics:
            if diag.severity != "error":
                warnings.append(diag.message)

        current_relation_plan = relation_plan
        composite_plans = []
        for plan in planning_result.plans:
            composite_plans.append(plan)
            apply_result = applier.apply(
                plan=plan,
                steps=steps,
                resources=resources,
                symbol_table=symbol_table,
                worker_plan=worker_plan or WorkerPlanIR(),
                relation_plan=current_relation_plan,
            )
            current_relation_plan = apply_result.relation_plan
            warnings.append(
                f"Aggregated multi-output step {plan.step_id} into "
                f"{plan.composite_variable_name} without unpack steps."
            )

        self._last_composite_output_plans = tuple(composite_plans)
        self._last_step_variable_relation_plan = current_relation_plan

        return warnings
