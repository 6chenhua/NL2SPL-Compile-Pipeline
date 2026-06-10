"""ExecutorMixin for Stage 3.5 WorkerBoundaryPlanner."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.compiler.resource_contract_demand_view.model import DemandViewDemand
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.resource_contract_ir import ResourceContractPlanIR
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
    | tuple[
        list[SpanIR],
        FieldRouteIR,
        CanonicalCompileInput | None,
        ResourceContractPlanIR | None,
    ]
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
        spans, routes, canonical_input, resource_contract_plan = self._unpack_input(
            input_data
        )
        self.logger.info("Starting worker boundary planning for %d spans", len(spans))

        return self._execute_split(spans, routes, canonical_input, resource_contract_plan)

    def _execute_split(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None,
        resource_contract_plan: ResourceContractPlanIR | object | None = None,
    ) -> WorkerPlanIR:
        """Run Stage 3.5a/3.5b/3.5c as separate compiler sub-stages."""
        hard_inputs, hard_outputs = self._hard_fact_contracts(canonical_input)
        behavior_span_ids = set(routes.behavior)
        known_span_ids = {span.span_id for span in spans}

        try:
            candidates = self._run_candidate_extraction(
                spans, routes, canonical_input, resource_contract_plan,
            )
            self._save_substage_checkpoint(
                "stage3_5a_candidate_task_units",
                {"candidates": [asdict(candidate) for candidate in candidates]},
            )

            # Filter out candidates with blocking risks — auto-reject them
            # instead of passing to 3.5b where the LLM might contradict itself.
            eligible, auto_rejected = self._split_by_blocking_risks(candidates)

            if eligible:
                decisions = self._run_boundary_decisions(
                    spans,
                    routes,
                    canonical_input,
                    eligible,
                    resource_contract_plan,
                )
                decisions.extend(auto_rejected)
            else:
                self.logger.info(
                    "No eligible candidates after blocking-risk filter; "
                    "skipping Stage 3.5b boundary decisions"
                )
                decisions = auto_rejected
            self._save_substage_checkpoint(
                "stage3_5b_worker_boundary_decisions",
                {"decisions": [asdict(decision) for decision in decisions]},
            )
            # Phase D: extract demands from DemandView (production) or
            # ResourceContractPlanIR (legacy compat).
            demand_view_demands: list[DemandViewDemand] = []
            if resource_contract_plan is not None:
                if hasattr(resource_contract_plan, "valid_demands"):
                    demand_view_demands = list(
                        getattr(resource_contract_plan, "valid_demands")()
                    )
                else:
                    # legacy compat path — intentionally kept for ResourceContractPlanIR callers
                    for d in resource_contract_plan.demands:
                        demand_view_demands.append(DemandViewDemand(
                            demand_id=d.demand_id,
                            direction=d.direction,
                            requiredness=d.requiredness,
                            required=d.required,
                            evidence_text=d.evidence_text,
                            source_span_ids=tuple(d.source_span_ids),
                            source_section_id=d.source_section_id,
                            source_packet_id=d.source_packet_id,
                            evidence_source="stage2_annotation",
                            view_status="valid",
                        ))
            demand_inputs, demand_outputs = self._demand_view_contracts(
                demand_view_demands,
            )
            materializer = WorkerPlanMaterializer()
            plan, materialize_warnings = materializer.materialize(
                candidates=candidates,
                decisions=decisions,
                hard_fact_inputs=hard_inputs,
                hard_fact_outputs=hard_outputs,
                behavior_span_ids=behavior_span_ids,
                behavior_span_order=list(routes.behavior),
                annotations=routes.annotations if routes.annotations else None,
                demand_inputs=demand_inputs,
                demand_outputs=demand_outputs,
            )
            plan.warnings.extend(materialize_warnings)
            self._save_substage_checkpoint(
                "stage3_5c_worker_plan_materializer",
                asdict(plan),
            )
        except Exception as e:
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

    def _run_candidate_extraction(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None,
        resource_contract_plan: ResourceContractPlanIR | None = None,
    ) -> list[CandidateTaskUnitIR]:
        system_prompt = load_prompt("stage3_5a")
        user_prompt = self._build_candidate_prompt(
            spans, routes, canonical_input, resource_contract_plan,
        )
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
        resource_contract_plan: ResourceContractPlanIR | None = None,
    ) -> list[WorkerBoundaryDecisionIR]:
        system_prompt = load_prompt("stage3_5b")
        user_prompt = self._build_decision_prompt(
            spans,
            routes,
            canonical_input,
            candidates,
            resource_contract_plan,
        )
        result = self.client.call_json(
            stage_name="stage3_5b_worker_boundary_decisions",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        candidate_ids = {c.candidate_id for c in candidates}
        decisions = [
            self._parse_decision(decision)
            for decision in result.get("decisions", [])
            if decision.get("candidate_id") in candidate_ids
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

    # Map risk types to the decision the materializer expects for that
    # category.  Using the correct decision type preserves the materializer's
    # blocked-anchor and ownership semantics.
    _RISK_TO_DECISION: dict[str, str] = {
        "alternative_flow": "compile_as_alternative_flow",
        "exception_flow": "compile_as_exception_flow",
        "policy_or_constraint": "compile_as_constraint",
        "single_api_call": "compile_as_call_api",
    }

    def _split_by_blocking_risks(
        self,
        candidates: list[CandidateTaskUnitIR],
    ) -> tuple[list[CandidateTaskUnitIR], list[WorkerBoundaryDecisionIR]]:
        """Split candidates into eligible and auto-rejected.

        Candidates whose ``risks`` overlap with ``_BLOCKING_RISKS`` are
        automatically rejected instead of being sent to Stage 3.5b where
        the LLM might contradict itself by accepting them.

        Returns:
            (eligible, auto_rejected_decisions)
        """
        eligible: list[CandidateTaskUnitIR] = []
        auto_rejected: list[WorkerBoundaryDecisionIR] = []
        for candidate in candidates:
            blocking = set(candidate.risks) & self._BLOCKING_RISKS
            if blocking:
                risk = next(iter(blocking))
                self.logger.info(
                    "Auto-rejecting candidate %s due to blocking risk: %s",
                    candidate.candidate_id,
                    risk,
                )
                decision = self._RISK_TO_DECISION.get(risk, "keep_in_main_worker")
                auto_rejected.append(
                    WorkerBoundaryDecisionIR(
                        candidate_id=candidate.candidate_id,
                        decision=decision,
                        boundary_strength="weak",
                        boundary_kind=candidate.candidate_kind,
                        rejection_reason=risk,
                        reason=f"Auto-rejected: blocking risk {risk}",
                    )
                )
            else:
                eligible.append(candidate)
        return eligible, auto_rejected

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

    @staticmethod
    def _demand_view_contracts(
        demands: list[DemandViewDemand],
    ) -> tuple[list[ContractFieldIR], list[ContractFieldIR]]:
        """Build ContractFieldIR entries from DemandView demands (B3).

        Only demands with ``view_status == "valid"`` are materialized.
        Invalid demands (e.g. ``invalid_requiredness``) are silently
        excluded — the corresponding diagnostic has already been emitted
        by DemandView builder.
        """
        demand_inputs: list[ContractFieldIR] = []
        demand_outputs: list[ContractFieldIR] = []
        for demand in demands:
            if demand.view_status != "valid":
                continue
            field = ContractFieldIR(
                name="",
                data_type="",
                requiredness=demand.requiredness,
                required=demand.required,
                description=demand.evidence_text,
                source="input" if demand.direction == "input" else "output",
                contract_demand_id=demand.demand_id,
                source_span_ids=list(demand.source_span_ids),
                source_section_id=demand.source_section_id,
                source_packet_id=demand.source_packet_id,
                resource_kind=None,
            )
            if demand.direction == "input":
                demand_inputs.append(field)
            else:
                demand_outputs.append(field)
        return demand_inputs, demand_outputs


    def _save_substage_checkpoint(self, stage_name: str, result: dict[str, Any]) -> None:
        if self.config.save_intermediate:
            save_intermediate_result(
                stage_name=stage_name,
                result=result,
                output_dir=self.config.run_dir,
            )

    def _unpack_input(
        self,
        input_data: PlannerInput,
    ) -> tuple[
        list[SpanIR],
        FieldRouteIR,
        CanonicalCompileInput | None,
        ResourceContractPlanIR | None,
    ]:
        if len(input_data) == 2:
            spans, routes = input_data
            return spans, routes, None, None
        if len(input_data) == 3:
            spans, routes, canonical_input = input_data
            return spans, routes, canonical_input, None
        spans, routes, canonical_input, resource_contract_plan = input_data
        return spans, routes, canonical_input, resource_contract_plan

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
