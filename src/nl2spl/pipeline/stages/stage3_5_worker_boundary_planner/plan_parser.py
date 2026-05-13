"""PlanParserMixin for Stage 3.5 WorkerBoundaryPlanner."""

from __future__ import annotations

from typing import Any, cast

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


class PlanParserMixin:
    """Mixin providing LLM output parsing methods."""

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
            ordering=self._normalize_handoff_ordering(data.get("ordering", "after")),
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

    def _normalize_handoff_ordering(self, ordering: object) -> str:
        if ordering == "sequential":
            return "after"
        return str(ordering or "after")

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
