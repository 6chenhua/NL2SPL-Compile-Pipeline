"""ExecutorMixin for Stage 3.5 WorkerBoundaryPlanner."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.compiler.irs_prompt_builder import irs_checklist_for_stage
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    WorkerBoundaryDecisionIR,
    WorkerPlanIR,
)
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
    WorkerPlanMaterializer,
)
from nl2spl.pipeline.worker_plan_validator import WorkerPlanValidator
from nl2spl.utils.persistence import save_intermediate_result

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

        if getattr(self.config, "enable_worker_boundary_planner_split", True):
            return self._execute_split(spans, routes, canonical_input)
        return self._execute_legacy_single_call(spans, routes, canonical_input)

    def _execute_split(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None,
    ) -> WorkerPlanIR:
        """Run Stage 3.5a/3.5b/3.5c as separate compiler sub-stages."""
        hard_inputs, hard_outputs = self._hard_fact_contracts(canonical_input)
        behavior_span_ids = set(routes.behavior)
        known_span_ids = {span.span_id for span in spans}

        try:
            candidates = self._run_candidate_extraction(spans, routes, canonical_input)
            self._save_substage_checkpoint(
                "stage3_5a_candidate_task_units",
                {"candidates": [asdict(candidate) for candidate in candidates]},
            )
            decisions = self._run_boundary_decisions(
                spans,
                routes,
                canonical_input,
                candidates,
            )
            self._save_substage_checkpoint(
                "stage3_5b_worker_boundary_decisions",
                {"decisions": [asdict(decision) for decision in decisions]},
            )
            materializer = WorkerPlanMaterializer()
            plan, materialize_warnings = materializer.materialize(
                candidates=candidates,
                decisions=decisions,
                hard_fact_inputs=hard_inputs,
                hard_fact_outputs=hard_outputs,
                behavior_span_ids=behavior_span_ids,
                behavior_span_order=list(routes.behavior),
            )
            plan.warnings.extend(materialize_warnings)
            self._save_substage_checkpoint(
                "stage3_5c_worker_plan_materializer",
                asdict(plan),
            )
        except Exception as e:
            if getattr(self.config, "enable_worker_boundary_single_call_fallback", False):
                self.logger.warning(
                    "Split worker boundary planning failed; falling back to "
                    "legacy single-call Stage 3.5: %s",
                    e,
                )
                return self._execute_legacy_single_call(spans, routes, canonical_input)
            if isinstance(e, StageError):
                raise
            raise StageError(
                message=f"Split worker boundary planning failed in {self.name}: {e}",
                stage=self.name,
            ) from e

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

    def _execute_legacy_single_call(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None,
    ) -> WorkerPlanIR:
        """Run the previous single-call WorkerPlanIR generation path."""
        system_prompt = load_prompt("stage3_5")
        if self.config.enable_irs_prompt_builder:
            system_prompt += "\n\n" + irs_checklist_for_stage("stage3_5")
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
            materializer = WorkerPlanMaterializer()
            hard_inputs, hard_outputs = self._hard_fact_contracts(canonical_input)

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
                behavior_span_order=list(routes.behavior),
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

    def _run_candidate_extraction(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None,
    ) -> list[CandidateTaskUnitIR]:
        system_prompt = load_prompt("stage3_5a")
        if self.config.enable_irs_prompt_builder:
            system_prompt += "\n\n" + irs_checklist_for_stage("stage3_5a")
        user_prompt = self._build_candidate_prompt(spans, routes, canonical_input)
        result = self.client.call_json(
            stage_name="stage3_5a_candidate_task_units",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        candidates = [
            self._parse_candidate(candidate)
            for candidate in result.get("candidates", [])
        ]
        return self._dedupe_candidates(candidates)

    def _run_boundary_decisions(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None,
        candidates: list[CandidateTaskUnitIR],
    ) -> list[WorkerBoundaryDecisionIR]:
        system_prompt = load_prompt("stage3_5b")
        if self.config.enable_irs_prompt_builder:
            system_prompt += "\n\n" + irs_checklist_for_stage("stage3_5b")
        user_prompt = self._build_decision_prompt(
            spans,
            routes,
            canonical_input,
            candidates,
        )
        result = self.client.call_json(
            stage_name="stage3_5b_worker_boundary_decisions",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        decisions = [
            self._parse_decision(decision)
            for decision in result.get("decisions", [])
        ]
        self._validate_split_decisions(candidates, decisions)
        return decisions

    def _validate_split_decisions(
        self,
        candidates: list[CandidateTaskUnitIR],
        decisions: list[WorkerBoundaryDecisionIR],
    ) -> None:
        candidate_ids = {candidate.candidate_id for candidate in candidates}
        decision_ids = [decision.candidate_id for decision in decisions]
        missing = candidate_ids - set(decision_ids)
        extra = set(decision_ids) - candidate_ids
        duplicate = {
            candidate_id for candidate_id in decision_ids
            if decision_ids.count(candidate_id) > 1
        }
        if missing or extra or duplicate:
            raise StageError(
                message=(
                    "Invalid Stage 3.5b decisions: "
                    f"missing={sorted(missing)}, extra={sorted(extra)}, "
                    f"duplicate={sorted(duplicate)}"
                ),
                stage=self.name,
            )
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            candidates=candidates,
            decisions=decisions,
        )
        self._validate_planner_decisions(plan)

    def _dedupe_candidates(
        self,
        candidates: list[CandidateTaskUnitIR],
    ) -> list[CandidateTaskUnitIR]:
        deduped: list[CandidateTaskUnitIR] = []
        seen: set[tuple[tuple[str, ...], str]] = set()
        for candidate in candidates:
            if not candidate.source_span_ids:
                continue
            signature = (
                tuple(candidate.source_span_ids),
                candidate.task_text.strip().lower(),
            )
            if signature in seen:
                continue
            seen.add(signature)
            deduped.append(candidate)
        return deduped

    def _hard_fact_contracts(
        self,
        canonical_input: CanonicalCompileInput | None,
    ) -> tuple[list[ContractFieldIR], list[ContractFieldIR]]:
        if canonical_input is None:
            return [], []
        hard_inputs = [
            ContractFieldIR(f.name, f.data_type, f.required, f.description, "input")
            for f in canonical_input.hard_facts.inputs
        ]
        hard_outputs = [
            ContractFieldIR(f.name, f.data_type, f.required, f.description, "output")
            for f in canonical_input.hard_facts.outputs
        ]
        return hard_inputs, hard_outputs

    def _save_substage_checkpoint(self, stage_name: str, result: dict[str, Any]) -> None:
        if self.config.save_intermediate:
            save_intermediate_result(
                stage_name=stage_name,
                result=result,
                output_dir=self.config.run_dir,
            )

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
