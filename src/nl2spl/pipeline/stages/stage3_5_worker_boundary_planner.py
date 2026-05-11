"""Stage 3.5: WorkerBoundaryPlanner - propose worker boundaries before flow assembly."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, cast

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    ControlComplexityRegionIR,
    HandoffFailurePolicyIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    Risk,
    Signal,
    WorkerBoundaryDecisionIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage
from nl2spl.pipeline.worker_plan_validator import WorkerPlanValidator


PlannerInput = (
    tuple[list[SpanIR], FieldRouteIR]
    | tuple[list[SpanIR], FieldRouteIR, CanonicalCompileInput | None]
)


class WorkerBoundaryPlanner(PipelineStage[PlannerInput, WorkerPlanIR]):
    """Plan first-class worker boundaries using compact span and adapter context."""

    _REJECTION_REASONS: set[str] = {
        "no_clear_input_contract",
        "no_clear_output_contract",
        "no_parent_invocation_point",
        "simple_control_flow",
        "ordinary_sequential_step",
        "policy_or_constraint",
        "alternative_flow",
        "exception_flow",
        "single_api_call",
        "insufficient_semantic_boundary",
        "over_fragmentation",
        "unclear_result_handoff",
    }
    _BLOCKING_RISKS = _REJECTION_REASONS

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage3_5_worker_boundary_planner"

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

    def _unpack_input(
        self,
        input_data: PlannerInput,
    ) -> tuple[list[SpanIR], FieldRouteIR, CanonicalCompileInput | None]:
        if len(input_data) == 2:
            spans, routes = input_data
            return spans, routes, None
        spans, routes, canonical_input = input_data
        return spans, routes, canonical_input

    def _build_user_prompt(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None,
    ) -> str:
        return f"""Plan worker boundaries before flow assembly.

Resolved spans:
---
{self._format_spans(spans)}
---

Field routes:
---
{self._format_routes(routes)}
---

Adapter metadata:
---
{self._format_adapter_metadata(canonical_input)}
---

Return JSON only. Use span_id values in source_span_ids and owned_span_ids."""

    def _format_spans(self, spans: list[SpanIR]) -> str:
        if not spans:
            return "(none)"
        lines = []
        for span in spans:
            provenance = []
            if span.source_section_id:
                provenance.append(f"section={span.source_section_id}")
            if span.source_packet_id:
                provenance.append(f"packet={span.source_packet_id}")
            suffix = f" ({', '.join(provenance)})" if provenance else ""
            lines.append(f"{span.span_id}: {span.text}{suffix}")
        return "\n".join(lines)

    def _format_routes(self, routes: FieldRouteIR) -> str:
        route_names = ["identity", "audience", "rules", "domain", "integrations", "behavior"]
        return "\n".join(
            f"{name}: {', '.join(getattr(routes, name)) or '(none)'}" for name in route_names
        )

    def _format_adapter_metadata(self, canonical_input: CanonicalCompileInput | None) -> str:
        if canonical_input is None:
            return "(none)"

        lines: list[str] = [
            f"schema: {canonical_input.source_schema} {canonical_input.schema_version}",
        ]
        if canonical_input.raw_sections:
            lines.append("sections:")
            lines.extend(
                f"- {section.section_id}: {section.canonical_title} | {section.text}"
                for section in canonical_input.raw_sections
            )
        if canonical_input.hard_facts.inputs:
            lines.append("hard inputs:")
            lines.extend(
                f"- {fact.name}: {fact.data_type}, required={fact.required}, "
                f"section={fact.source_section_id}, {fact.description}"
                for fact in canonical_input.hard_facts.inputs
            )
        if canonical_input.hard_facts.outputs:
            lines.append("hard outputs:")
            lines.extend(
                f"- {fact.name}: {fact.data_type}, required={fact.required}, "
                f"section={fact.source_section_id}, {fact.description}"
                for fact in canonical_input.hard_facts.outputs
            )
        if canonical_input.hard_facts.failure_modes:
            lines.append("failure modes:")
            lines.extend(
                f"- {fact.name}: section={fact.source_section_id}, {fact.text}"
                for fact in canonical_input.hard_facts.failure_modes
            )
        self._append_hints(
            lines,
            "process hints",
            canonical_input.compile_hints.process_hints,
        )
        self._append_hints(
            lines,
            "constraint hints",
            canonical_input.compile_hints.constraint_hints,
        )
        self._append_hints(
            lines,
            "flow hints",
            canonical_input.compile_hints.flow_hints,
        )
        self._append_hints(
            lines,
            "delegation hints",
            canonical_input.compile_hints.delegation_hints,
        )
        return "\n".join(lines) if lines else "(none)"

    def _append_hints(self, lines: list[str], label: str, hints: list[Any]) -> None:
        if not hints:
            return
        lines.append(f"{label}:")
        lines.extend(
            f"- section={hint.source_section_id}, target={hint.target}, "
            f"kind={hint.suggested_kind}, flow={hint.suggested_flow}, "
            f"condition={hint.suggested_condition}, worker={hint.suggested_worker_name}, "
            f"text={hint.text}"
            for hint in hints
        )

    def _parse_worker_plan(self, data: dict[str, Any]) -> WorkerPlanIR:
        return WorkerPlanIR(
            main_worker_id=data["main_worker_id"],
            workers=[self._parse_worker(worker) for worker in data.get("workers", [])],
            handoffs=[self._parse_handoff(handoff) for handoff in data.get("handoffs", [])],
            candidates=[
                self._parse_candidate(candidate) for candidate in data.get("candidates", [])
            ],
            decisions=[
                self._parse_decision(decision) for decision in data.get("decisions", [])
            ],
            rejected_candidates=[
                self._parse_decision(decision)
                for decision in data.get("rejected_candidates", [])
            ],
            control_complexity_regions=[
                self._parse_control_region(region)
                for region in data.get("control_complexity_regions", [])
            ],
            unassigned_span_ids=self._str_list(data.get("unassigned_span_ids", [])),
            warnings=self._str_list(data.get("warnings", [])),
        )

    def _parse_contract_field(self, data: dict[str, Any]) -> ContractFieldIR:
        return ContractFieldIR(
            name=data["name"],
            data_type=data.get("data_type", "text"),
            required=bool(data.get("required", True)),
            description=data.get("description", ""),
            source=data.get("source", "input"),
        )

    def _parse_candidate(self, data: dict[str, Any]) -> CandidateTaskUnitIR:
        return CandidateTaskUnitIR(
            candidate_id=data["candidate_id"],
            source_span_ids=self._str_list(data.get("source_span_ids", [])),
            task_text=data.get("task_text", ""),
            purpose=data.get("purpose", ""),
            candidate_kind=data.get("candidate_kind", "not_a_worker"),
            possible_inputs=[
                self._parse_contract_field(field)
                for field in data.get("possible_inputs", [])
            ],
            possible_outputs=[
                self._parse_contract_field(field)
                for field in data.get("possible_outputs", [])
            ],
            signals=cast(list[Signal], self._str_list(data.get("signals", []))),
            risks=cast(list[Risk], self._str_list(data.get("risks", []))),
        )

    def _parse_decision(self, data: dict[str, Any]) -> WorkerBoundaryDecisionIR:
        rejection_reason = data.get("rejection_reason")
        return WorkerBoundaryDecisionIR(
            candidate_id=data["candidate_id"],
            decision=data["decision"],
            boundary_strength=data.get("boundary_strength", "weak"),
            boundary_kind=data.get("boundary_kind", "not_a_worker"),
            rejection_reason=rejection_reason,
            reason=data.get("reason", ""),
            evidence=cast(list[Signal], self._str_list(data.get("evidence", []))),
        )

    def _parse_worker(self, data: dict[str, Any]) -> WorkerSpecIR:
        return WorkerSpecIR(
            worker_id=data["worker_id"],
            worker_name=data["worker_name"],
            kind=data["kind"],
            purpose=data.get("purpose", ""),
            owned_span_ids=self._str_list(data.get("owned_span_ids", [])),
            input_contract=[
                self._parse_contract_field(field)
                for field in data.get("input_contract", [])
            ],
            output_contract=[
                self._parse_contract_field(field)
                for field in data.get("output_contract", [])
            ],
            depends_on=self._str_list(data.get("depends_on", [])),
            constraints=self._str_list(data.get("constraints", [])),
            boundary_kind=data.get("boundary_kind", "main_worker"),
            decision_evidence=cast(
                list[Signal],
                self._str_list(data.get("decision_evidence", [])),
            ),
            reason=data.get("reason", ""),
        )

    def _parse_handoff(self, data: dict[str, Any]) -> WorkerHandoffIR:
        return WorkerHandoffIR(
            handoff_id=data["handoff_id"],
            from_worker=data["from_worker"],
            to_worker=data.get("to_worker"),
            api_ref=data.get("api_ref"),
            mode=data["mode"],
            condition_text=data.get("condition_text"),
            ordering=data.get("ordering", "after"),
            input_bindings=[
                InputBindingIR(
                    parent_variable=binding["parent_variable"],
                    child_input=binding["child_input"],
                    required=bool(binding.get("required", True)),
                    default_value=binding.get("default_value"),
                )
                for binding in data.get("input_bindings", [])
            ],
            output_bindings=[
                OutputBindingIR(
                    child_output=binding["child_output"],
                    parent_variable=binding["parent_variable"],
                    required=bool(binding.get("required", True)),
                    merge_strategy=binding.get("merge_strategy", "set"),
                )
                for binding in data.get("output_bindings", [])
            ],
            invoke_location_hint=self._parse_invoke_location_hint(
                data.get("invoke_location_hint", {})
            ),
            failure_policy=self._parse_failure_policy(data.get("failure_policy", {})),
        )

    def _parse_invoke_location_hint(
        self,
        data: dict[str, Any] | None,
    ) -> InvokeLocationHintIR:
        data = self._optional_dict(data, "invoke_location_hint")
        return InvokeLocationHintIR(
            flow_kind=data.get("flow_kind", "main"),
            flow_id=data.get("flow_id"),
            after_span_id=data.get("after_span_id"),
            before_span_id=data.get("before_span_id"),
            block_hint=data.get("block_hint", "unknown"),
        )

    def _parse_failure_policy(self, data: dict[str, Any] | None) -> HandoffFailurePolicyIR:
        data = self._optional_dict(data, "failure_policy")
        return HandoffFailurePolicyIR(
            policy_kind=data.get("policy_kind", "propagate_exception"),
            description=data.get(
                "description",
                "Propagate handoff failure to the parent worker.",
            ),
            source_span_ids=self._str_list(data.get("source_span_ids", [])),
        )

    def _parse_control_region(self, data: dict[str, Any]) -> ControlComplexityRegionIR:
        return ControlComplexityRegionIR(
            region_id=data["region_id"],
            source_span_ids=self._str_list(data.get("source_span_ids", [])),
            outer_control=data.get("outer_control", "unknown"),
            inner_control=data.get("inner_control", "unknown"),
            description=data.get("description", ""),
            discovery_phase=data.get("discovery_phase", "predicted"),
            severity=data.get("severity", "info"),
            can_flatten=bool(data.get("can_flatten", False)),
            can_merge_condition=bool(data.get("can_merge_condition", False)),
            can_lift_guard=bool(data.get("can_lift_guard", False)),
            suggested_repairs=self._str_list(data.get("suggested_repairs", [])),
        )

    def _validate_planner_decisions(self, plan: WorkerPlanIR) -> None:
        candidates_by_id = {
            candidate.candidate_id: candidate for candidate in plan.candidates
        }
        for decision in plan.decisions:
            if decision.decision == "extract_child_worker":
                if decision.rejection_reason is not None:
                    raise ValueError(
                        f"Accepted candidate has rejection_reason: {decision.candidate_id}"
                    )
                if not decision.evidence:
                    raise ValueError(
                        f"Accepted candidate has no positive signal evidence: "
                        f"{decision.candidate_id}"
                    )
                candidate = candidates_by_id.get(decision.candidate_id)
                if candidate and set(candidate.risks) & self._BLOCKING_RISKS:
                    raise ValueError(
                        f"Accepted candidate has blocking risks: {decision.candidate_id}"
                    )
                continue

            if decision.rejection_reason is None:
                raise ValueError(
                    f"Rejected candidate is missing rejection_reason: {decision.candidate_id}"
                )
            if decision.rejection_reason not in self._REJECTION_REASONS:
                raise ValueError(
                    f"Unsupported rejection_reason for {decision.candidate_id}: "
                    f"{decision.rejection_reason}"
                )

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
