"""ExecutorMixin for Stage 3.5 WorkerBoundaryPlanner."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import ContractFieldIR, WorkerPlanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.worker_plan_validator import WorkerPlanValidator

PlannerInput = (
    tuple[list[SpanIR], FieldRouteIR]
    | tuple[list[SpanIR], FieldRouteIR, CanonicalCompileInput | None]
)


class ExecutorMixin:
    """Mixin providing execute() and input utility methods."""

    def execute(self, input_data: PlannerInput) -> WorkerPlanIR:
        """Execute worker boundary planning.

        Args:
            input_data: Tuple of (spans, routes) or (spans, routes, canonical_input)

        Returns:
            Validated WorkerPlanIR.

        Raises:
            StageError: If the planner call or WorkerPlanIR validation fails.
        """
        spans, routes, canonical_input = self._unpack_input(input_data)
        self.logger.info("Starting worker boundary planning for %d spans", len(spans))

        system_prompt = load_prompt("stage3_5")
        user_prompt = self._build_user_prompt(spans, routes, canonical_input)

        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed: %s", e)
            raise StageError(
                message=f"LLM call failed in {self.name}: {e}",
                stage=self.name,
            ) from e

        try:
            plan = self._parse_worker_plan(result)
            self._validate_planner_decisions(plan)
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            raise StageError(
                message=f"Invalid WorkerPlanIR output in {self.name}: {e}",
                stage=self.name,
            ) from e

        known_span_ids = {span.span_id for span in spans}
        validation = WorkerPlanValidator().validate(plan, known_span_ids)

        # Deterministic repair pass: when the LLM produces inconsistent
        # output (e.g. accepted decision without matching worker), rebuild
        # workers + handoffs from decisions + candidates.
        if not validation.is_valid and self._has_decision_worker_mismatch(
            validation.errors
        ):
            self.logger.warning(
                "LLM output has decision/worker mismatches; "
                "running deterministic materialization repair."
            )
            from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
                WorkerPlanMaterializer,
            )

            materializer = WorkerPlanMaterializer()
            hard_inputs = [
                ContractFieldIR(f.name, f.data_type, f.required, f.description, "input")
                for f in canonical_input.hard_facts.inputs
            ] if canonical_input is not None else []
            hard_outputs = [
                ContractFieldIR(f.name, f.data_type, f.required, f.description, "output")
                for f in canonical_input.hard_facts.outputs
            ] if canonical_input is not None else []

            behavior_span_ids = {s.span_id for s in spans if s.span_id in routes.behavior}
            plan, materialize_warnings = materializer.materialize(
                candidates=plan.candidates,
                decisions=plan.decisions,
                hard_fact_inputs=hard_inputs,
                hard_fact_outputs=hard_outputs,
                behavior_span_ids=behavior_span_ids,
                existing_workers=None,
                existing_handoffs=None,
                main_worker_id=plan.main_worker_id,
            )
            plan.warnings.extend(materialize_warnings)
            validation = WorkerPlanValidator().validate(plan, known_span_ids)

        if not validation.is_valid:
            raise StageError(
                message="WorkerPlanIR validation failed: " + "; ".join(validation.errors),
                stage=self.name,
                details={"errors": validation.errors, "warnings": validation.warnings},
            )

        self.logger.info(
            "Worker boundary planning complete: %d workers, %d handoffs, %d rejected candidates",
            len(plan.workers),
            len(plan.handoffs),
            len(plan.rejected_candidates),
        )
        self.save_checkpoint(asdict(plan))
        return plan

    @staticmethod
    def _has_decision_worker_mismatch(errors: list[str]) -> bool:
        """Check whether errors include decision→worker consistency failures."""
        return any(
            "must match exactly one" in e or "has no matching" in e
            for e in errors
        )

    def _unpack_input(
        self,
        input_data: PlannerInput,
    ) -> tuple[list[SpanIR], FieldRouteIR, CanonicalCompileInput | None]:
        if len(input_data) == 2:
            spans, routes = input_data
            return spans, routes, None
        spans, routes, canonical_input = input_data
        return spans, routes, canonical_input

    def _str_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"Expected list, got {type(value).__name__}")
        return [str(item) for item in value]

    def _optional_dict(self, value: Any, field_name: str) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(
                f"Expected object or null for {field_name}, got {type(value).__name__}"
            )
        return value
