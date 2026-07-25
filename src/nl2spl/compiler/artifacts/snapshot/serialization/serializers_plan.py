"""Serializers for plan-layer artifacts: WorkerPlanIR family, flow/block/step.

Field names match actual IR dataclass definitions.  Nested types within
this file use inline serialization to avoid circular imports.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.artifacts.snapshot.serialization.protocol import ArtifactSerializer
from nl2spl.compiler.artifacts.snapshot.serialization.registry import SerializerRegistry
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.condition_variable_reference_ir import (
    ConditionVariableReferencePlan,
)
from nl2spl.ir.flow_structure_ir import DelegationCandidate, FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    ControlComplexityRegionIR,
    HandoffContractIR,
    HandoffFailurePolicyIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerBlockPlanIR,
    WorkerBoundaryDecisionIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)

# ===================================================================
# Contract field
# ===================================================================


class ContractFieldIRSerializer(ArtifactSerializer):
    type_id = "ContractFieldIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        f: ContractFieldIR = obj
        return {
            "$type": self.type_id,
            "name": f.name,
            "data_type": f.data_type,
            "required": f.required,
            "description": f.description,
            "source": f.source,
            "contract_demand_id": f.contract_demand_id,
            "source_span_ids": f.source_span_ids,
            "source_section_id": f.source_section_id,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return ContractFieldIR(
            name=data["name"],
            data_type=data["data_type"],
            required=data.get("required"),
            description=data.get("description", ""),
            source=data.get("source", ""),
            contract_demand_id=data.get("contract_demand_id"),
            source_span_ids=data.get("source_span_ids", []),
            source_section_id=data.get("source_section_id"),
        )


# ===================================================================
# Bindings and hints
# ===================================================================


class InputBindingIRSerializer(ArtifactSerializer):
    type_id = "InputBindingIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        b: InputBindingIR = obj
        return {
            "$type": self.type_id,
            "parent_variable": b.parent_variable,
            "child_input": b.child_input,
            "required": b.required,
            "default_value": b.default_value,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return InputBindingIR(
            parent_variable=data["parent_variable"],
            child_input=data["child_input"],
            required=data["required"],
            default_value=data.get("default_value"),
        )


class OutputBindingIRSerializer(ArtifactSerializer):
    type_id = "OutputBindingIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        b: OutputBindingIR = obj
        return {
            "$type": self.type_id,
            "child_output": b.child_output,
            "parent_variable": b.parent_variable,
            "required": b.required,
            "merge_strategy": b.merge_strategy,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return OutputBindingIR(
            child_output=data["child_output"],
            parent_variable=data["parent_variable"],
            required=data["required"],
            merge_strategy=data.get("merge_strategy", "set"),
        )


class InvokeLocationHintIRSerializer(ArtifactSerializer):
    type_id = "InvokeLocationHintIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        h: InvokeLocationHintIR = obj
        return {
            "$type": self.type_id,
            "flow_kind": h.flow_kind,
            "flow_id": h.flow_id,
            "after_span_id": h.after_span_id,
            "before_span_id": h.before_span_id,
            "block_hint": h.block_hint,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return InvokeLocationHintIR(
            flow_kind=data.get("flow_kind", "main"),
            flow_id=data.get("flow_id"),
            after_span_id=data.get("after_span_id"),
            before_span_id=data.get("before_span_id"),
            block_hint=data.get("block_hint", "sequential"),
        )


class HandoffFailurePolicyIRSerializer(ArtifactSerializer):
    type_id = "HandoffFailurePolicyIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        p: HandoffFailurePolicyIR = obj
        return {
            "$type": self.type_id,
            "policy_kind": p.policy_kind,
            "description": p.description,
            "source_span_ids": p.source_span_ids,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return HandoffFailurePolicyIR(
            policy_kind=data.get("policy_kind", "block_finalization"),
            description=data.get("description", ""),
            source_span_ids=data.get("source_span_ids", []),
        )


class HandoffContractIRSerializer(ArtifactSerializer):
    type_id = "HandoffContractIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        h: HandoffContractIR = obj
        cf_ser = ContractFieldIRSerializer()
        return {
            "$type": self.type_id,
            "handoff_id": h.handoff_id,
            "parent_worker_id": h.parent_worker_id,
            "child_worker_id": h.child_worker_id,
            "input_variables": [cf_ser.to_canonical(v) for v in h.input_variables],
            "output_variables": [cf_ser.to_canonical(v) for v in h.output_variables],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        cf_ser = ContractFieldIRSerializer()
        return HandoffContractIR(
            handoff_id=data["handoff_id"],
            parent_worker_id=data["parent_worker_id"],
            child_worker_id=data["child_worker_id"],
            input_variables=[cf_ser.from_canonical(v) for v in data.get("input_variables", [])],
            output_variables=[cf_ser.from_canonical(v) for v in data.get("output_variables", [])],
        )


# ===================================================================
# Worker spec, handoff, candidates, decisions
# ===================================================================


class WorkerSpecIRSerializer(ArtifactSerializer):
    type_id = "WorkerSpecIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        w: WorkerSpecIR = obj
        cf_ser = ContractFieldIRSerializer()
        return {
            "$type": self.type_id,
            "worker_id": w.worker_id,
            "worker_name": w.worker_name,
            "kind": w.kind,
            "purpose": w.purpose,
            "owned_span_ids": w.owned_span_ids,
            "input_contract": [cf_ser.to_canonical(c) for c in w.input_contract],
            "output_contract": [cf_ser.to_canonical(c) for c in w.output_contract],
            "depends_on": w.depends_on,
            "constraints": w.constraints,
            "boundary_kind": w.boundary_kind,
            "input_contract_status": w.input_contract_status,
            "output_contract_status": w.output_contract_status,
            "input_contract_status_source": w.input_contract_status_source,
            "output_contract_status_source": w.output_contract_status_source,
            "partial_reason": w.partial_reason,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        cf_ser = ContractFieldIRSerializer()
        return WorkerSpecIR(
            worker_id=data["worker_id"],
            worker_name=data["worker_name"],
            kind=data.get("kind", "child"),
            purpose=data.get("purpose", ""),
            owned_span_ids=data.get("owned_span_ids", []),
            input_contract=[cf_ser.from_canonical(c) for c in data.get("input_contract", [])],
            output_contract=[cf_ser.from_canonical(c) for c in data.get("output_contract", [])],
            depends_on=data.get("depends_on", []),
            constraints=data.get("constraints", []),
            boundary_kind=data.get("boundary_kind", "main_worker"),
            input_contract_status=data.get("input_contract_status", "unknown"),
            output_contract_status=data.get("output_contract_status", "unknown"),
            input_contract_status_source=data.get("input_contract_status_source"),
            output_contract_status_source=data.get("output_contract_status_source"),
            partial_reason=data.get("partial_reason"),
        )


class WorkerHandoffIRSerializer(ArtifactSerializer):
    type_id = "WorkerHandoffIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        h: WorkerHandoffIR = obj
        ib_ser = InputBindingIRSerializer()
        ob_ser = OutputBindingIRSerializer()
        hint_ser = InvokeLocationHintIRSerializer()
        pol_ser = HandoffFailurePolicyIRSerializer()
        return {
            "$type": self.type_id,
            "handoff_id": h.handoff_id,
            "from_worker": h.from_worker,
            "to_worker": h.to_worker,
            "api_ref": h.api_ref,
            "mode": h.mode,
            "condition_text": h.condition_text,
            "ordering": h.ordering,
            "input_bindings": [ib_ser.to_canonical(b) for b in h.input_bindings],
            "output_bindings": [ob_ser.to_canonical(b) for b in h.output_bindings],
            "invoke_location_hint": (
                hint_ser.to_canonical(h.invoke_location_hint)
                if h.invoke_location_hint else None
            ),
            "failure_policy": (
                pol_ser.to_canonical(h.failure_policy) if h.failure_policy else None
            ),
            "input_binding_status": h.input_binding_status,
            "output_binding_status": h.output_binding_status,
            "input_binding_status_source": h.input_binding_status_source,
            "output_binding_status_source": h.output_binding_status_source,
            "materialization_status": h.materialization_status,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        ib_ser = InputBindingIRSerializer()
        ob_ser = OutputBindingIRSerializer()
        hint_ser = InvokeLocationHintIRSerializer()
        pol_ser = HandoffFailurePolicyIRSerializer()
        hint_data = data.get("invoke_location_hint")
        pol_data = data.get("failure_policy")
        return WorkerHandoffIR(
            handoff_id=data["handoff_id"],
            from_worker=data["from_worker"],
            to_worker=data.get("to_worker"),
            api_ref=data.get("api_ref"),
            mode=data.get("mode", "invoke"),
            condition_text=data.get("condition_text"),
            ordering=data.get("ordering", "after"),
            input_bindings=[ib_ser.from_canonical(b) for b in data.get("input_bindings", [])],
            output_bindings=[ob_ser.from_canonical(b) for b in data.get("output_bindings", [])],
            invoke_location_hint=(
                hint_ser.from_canonical(hint_data) if hint_data else None
            ),
            input_binding_status=data.get("input_binding_status", "unknown"),
            output_binding_status=data.get("output_binding_status", "unknown"),
            input_binding_status_source=data.get("input_binding_status_source"),
            output_binding_status_source=data.get("output_binding_status_source"),
            materialization_status=data.get(
                "materialization_status", "partial_contract_unknown",
            ),
            failure_policy=(
                pol_ser.from_canonical(pol_data) if pol_data else None
            ),
        )


class CandidateTaskUnitIRSerializer(ArtifactSerializer):
    type_id = "CandidateTaskUnitIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        c: CandidateTaskUnitIR = obj
        cf_ser = ContractFieldIRSerializer()
        return {
            "$type": self.type_id,
            "candidate_id": c.candidate_id,
            "source_span_ids": c.source_span_ids,
            "task_text": c.task_text,
            "purpose": c.purpose,
            "candidate_kind": c.candidate_kind,
            "possible_inputs": [cf_ser.to_canonical(v) for v in c.possible_inputs],
            "possible_outputs": [cf_ser.to_canonical(v) for v in c.possible_outputs],
            "signals": c.signals,
            "risks": c.risks,
            "input_contract_status": c.input_contract_status,
            "output_contract_status": c.output_contract_status,
            "input_contract_status_source": c.input_contract_status_source,
            "output_contract_status_source": c.output_contract_status_source,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        cf_ser = ContractFieldIRSerializer()
        return CandidateTaskUnitIR(
            candidate_id=data["candidate_id"],
            source_span_ids=data.get("source_span_ids", []),
            task_text=data["task_text"],
            purpose=data.get("purpose", ""),
            candidate_kind=data.get("candidate_kind", "unknown"),
            possible_inputs=[cf_ser.from_canonical(v) for v in data.get("possible_inputs", [])],
            possible_outputs=[cf_ser.from_canonical(v) for v in data.get("possible_outputs", [])],
            signals=data.get("signals", []),
            risks=data.get("risks", []),
            input_contract_status=data.get("input_contract_status", "unknown"),
            output_contract_status=data.get("output_contract_status", "unknown"),
            input_contract_status_source=data.get("input_contract_status_source"),
            output_contract_status_source=data.get("output_contract_status_source"),
        )


class WorkerBoundaryDecisionIRSerializer(ArtifactSerializer):
    type_id = "WorkerBoundaryDecisionIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        d: WorkerBoundaryDecisionIR = obj
        return {
            "$type": self.type_id,
            "candidate_id": d.candidate_id,
            "decision": d.decision,
            "boundary_strength": d.boundary_strength,
            "boundary_kind": d.boundary_kind,
            "rejection_reason": d.rejection_reason,
            "reason": d.reason,
            "evidence": d.evidence,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return WorkerBoundaryDecisionIR(
            candidate_id=data["candidate_id"],
            decision=data["decision"],
            boundary_strength=data.get("boundary_strength", "moderate"),
            boundary_kind=data.get("boundary_kind", "task_boundary"),
            rejection_reason=data.get("rejection_reason"),
            reason=data.get("reason", ""),
            evidence=data.get("evidence", []),
        )


class ControlComplexityRegionIRSerializer(ArtifactSerializer):
    type_id = "ControlComplexityRegionIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        r: ControlComplexityRegionIR = obj
        return {
            "$type": self.type_id,
            "region_id": r.region_id,
            "source_span_ids": r.source_span_ids,
            "outer_control": r.outer_control,
            "inner_control": r.inner_control,
            "description": r.description,
            "discovery_phase": r.discovery_phase,
            "severity": r.severity,
            "can_flatten": r.can_flatten,
            "can_merge_condition": r.can_merge_condition,
            "can_lift_guard": r.can_lift_guard,
            "suggested_repairs": r.suggested_repairs,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return ControlComplexityRegionIR(
            region_id=data["region_id"],
            source_span_ids=data.get("source_span_ids", []),
            outer_control=data.get("outer_control", "unknown"),
            inner_control=data.get("inner_control", "unknown"),
            description=data.get("description", ""),
            discovery_phase=data.get("discovery_phase", "predicted"),
            severity=data.get("severity", "warning"),
            can_flatten=data.get("can_flatten", False),
            can_merge_condition=data.get("can_merge_condition", False),
            can_lift_guard=data.get("can_lift_guard", False),
            suggested_repairs=data.get("suggested_repairs", []),
        )


# ===================================================================
# Flow / Block / Step
# ===================================================================


class StepIRSerializer(ArtifactSerializer):
    type_id = "StepIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        s: StepIR = obj
        return {
            "$type": self.type_id,
            "step_id": s.step_id,
            "text": s.text,
            "source_span_ids": s.source_span_ids,
            "command_type": s.command_type,
            "inputs": s.inputs,
            "outputs": s.outputs,
            "integration_ref": s.integration_ref,
            "flow_ref": s.flow_ref,
            "block_ref": s.block_ref,
            "kind": s.kind,
            "handoff_id": s.handoff_id,
            "metadata": s.metadata,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return StepIR(
            step_id=data["step_id"],
            text=data["text"],
            source_span_ids=data["source_span_ids"],
            command_type=data["command_type"],
            inputs=data.get("inputs", []),
            outputs=data.get("outputs", []),
            integration_ref=data.get("integration_ref"),
            flow_ref=data.get("flow_ref", "main"),
            block_ref=data.get("block_ref", ""),
            kind=data.get("kind", "normal"),
            handoff_id=data.get("handoff_id"),
            metadata=data.get("metadata", {}),
        )


class BlockIRSerializer(ArtifactSerializer):
    type_id = "BlockIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        b: BlockIR = obj
        return {
            "$type": self.type_id,
            "block_id": b.block_id,
            "block_type": b.block_type,
            "condition_text": b.condition_text,
            "spans": b.spans,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return BlockIR(
            block_id=data["block_id"],
            block_type=data["block_type"],
            condition_text=data.get("condition_text"),
            spans=data.get("spans", []),
        )


class DelegationCandidateSerializer(ArtifactSerializer):
    type_id = "DelegationCandidate"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        d: DelegationCandidate = obj
        return {
            "$type": self.type_id,
            "candidate_id": d.candidate_id,
            "spans": d.spans,
            "reason": d.reason,
            "suggested_type": d.suggested_type,
            "input_variables": d.input_variables,
            "output_variables": d.output_variables,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return DelegationCandidate(
            candidate_id=data["candidate_id"],
            spans=data.get("spans", []),
            reason=data.get("reason", ""),
            suggested_type=data["suggested_type"],
            input_variables=data.get("input_variables", []),
            output_variables=data.get("output_variables", []),
        )


class FlowStructureIRSerializer(ArtifactSerializer):
    type_id = "FlowStructureIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        f: FlowStructureIR = obj
        dc_ser = DelegationCandidateSerializer()
        return {
            "$type": self.type_id,
            "main_flow_spans": f.main_flow_spans,
            "alternative_flows": [
                {"flow_id": af.flow_id, "condition_text": af.condition_text, "spans": af.spans}
                for af in f.alternative_flows
            ],
            "exception_flows": [
                {"flow_id": ef.flow_id, "condition_text": ef.condition_text, "spans": ef.spans}
                for ef in f.exception_flows
            ],
            "delegation_candidates": [dc_ser.to_canonical(d) for d in f.delegation_candidates],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        dc_ser = DelegationCandidateSerializer()
        from nl2spl.ir.flow_structure_ir import AlternativeFlow, ExceptionFlow

        return FlowStructureIR(
            main_flow_spans=data.get("main_flow_spans", []),
            alternative_flows=[
                AlternativeFlow(
                    flow_id=af["flow_id"],
                    condition_text=af.get("condition_text", ""),
                    spans=af.get("spans", []),
                )
                for af in data.get("alternative_flows", [])
            ],
            exception_flows=[
                ExceptionFlow(
                    flow_id=ef["flow_id"],
                    condition_text=ef.get("condition_text", ""),
                    spans=ef.get("spans", []),
                )
                for ef in data.get("exception_flows", [])
            ],
            delegation_candidates=[
                dc_ser.from_canonical(d) for d in data.get("delegation_candidates", [])
            ],
        )


class BlockStructureIRSerializer(ArtifactSerializer):
    type_id = "BlockStructureIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        b: BlockStructureIR = obj
        blk_ser = BlockIRSerializer()
        return {
            "$type": self.type_id,
            "main_flow_blocks": [blk_ser.to_canonical(blk) for blk in b.main_flow_blocks],
            "alternative_flow_blocks": {
                fid: [blk_ser.to_canonical(blk) for blk in blks]
                for fid, blks in b.alternative_flow_blocks.items()
            },
            "exception_flow_blocks": {
                fid: [blk_ser.to_canonical(blk) for blk in blks]
                for fid, blks in b.exception_flow_blocks.items()
            },
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        blk_ser = BlockIRSerializer()
        return BlockStructureIR(
            main_flow_blocks=[
                blk_ser.from_canonical(blk) for blk in data.get("main_flow_blocks", [])
            ],
            alternative_flow_blocks={
                fid: [blk_ser.from_canonical(blk) for blk in blks]
                for fid, blks in data.get("alternative_flow_blocks", {}).items()
            },
            exception_flow_blocks={
                fid: [blk_ser.from_canonical(blk) for blk in blks]
                for fid, blks in data.get("exception_flow_blocks", {}).items()
            },
        )


# ===================================================================
# Top-level plan types
# ===================================================================


class WorkerPlanIRSerializer(ArtifactSerializer):
    type_id = "WorkerPlanIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        p: WorkerPlanIR = obj
        w_ser = WorkerSpecIRSerializer()
        h_ser = WorkerHandoffIRSerializer()
        c_ser = CandidateTaskUnitIRSerializer()
        d_ser = WorkerBoundaryDecisionIRSerializer()
        r_ser = ControlComplexityRegionIRSerializer()
        return {
            "$type": self.type_id,
            "main_worker_id": p.main_worker_id,
            "workers": [w_ser.to_canonical(w) for w in p.workers],
            "handoffs": [h_ser.to_canonical(h) for h in p.handoffs],
            "candidates": [c_ser.to_canonical(c) for c in p.candidates],
            "decisions": [d_ser.to_canonical(d) for d in p.decisions],
            "rejected_candidates": [d_ser.to_canonical(d) for d in p.rejected_candidates],
            "control_complexity_regions": [
                r_ser.to_canonical(r) for r in p.control_complexity_regions
            ],
            "unassigned_span_ids": p.unassigned_span_ids,
            "warnings": p.warnings,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        w_ser = WorkerSpecIRSerializer()
        h_ser = WorkerHandoffIRSerializer()
        c_ser = CandidateTaskUnitIRSerializer()
        d_ser = WorkerBoundaryDecisionIRSerializer()
        r_ser = ControlComplexityRegionIRSerializer()
        return WorkerPlanIR(
            main_worker_id=data["main_worker_id"],
            workers=[w_ser.from_canonical(w) for w in data.get("workers", [])],
            handoffs=[h_ser.from_canonical(h) for h in data.get("handoffs", [])],
            candidates=[c_ser.from_canonical(c) for c in data.get("candidates", [])],
            decisions=[d_ser.from_canonical(d) for d in data.get("decisions", [])],
            rejected_candidates=[
                d_ser.from_canonical(d) for d in data.get("rejected_candidates", [])
            ],
            control_complexity_regions=[
                r_ser.from_canonical(r) for r in data.get("control_complexity_regions", [])
            ],
            unassigned_span_ids=data.get("unassigned_span_ids", []),
            warnings=data.get("warnings", []),
        )


class WorkerFlowPlanIRSerializer(ArtifactSerializer):
    type_id = "WorkerFlowPlanIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        p: WorkerFlowPlanIR = obj
        flow_ser = FlowStructureIRSerializer()
        return {
            "$type": self.type_id,
            "worker_flows": {
                wid: flow_ser.to_canonical(f) for wid, f in p.worker_flows.items()
            },
            "warnings": p.warnings,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        flow_ser = FlowStructureIRSerializer()
        return WorkerFlowPlanIR(
            worker_flows={
                wid: flow_ser.from_canonical(f)
                for wid, f in data.get("worker_flows", {}).items()
            },
            warnings=data.get("warnings", []),
        )


class WorkerBlockPlanIRSerializer(ArtifactSerializer):
    type_id = "WorkerBlockPlanIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        p: WorkerBlockPlanIR = obj
        bs_ser = BlockStructureIRSerializer()
        r_ser = ControlComplexityRegionIRSerializer()
        return {
            "$type": self.type_id,
            "worker_blocks": {
                wid: bs_ser.to_canonical(b) for wid, b in p.worker_blocks.items()
            },
            "control_complexity_regions": [
                r_ser.to_canonical(r) for r in p.control_complexity_regions
            ],
            "warnings": p.warnings,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        bs_ser = BlockStructureIRSerializer()
        r_ser = ControlComplexityRegionIRSerializer()
        return WorkerBlockPlanIR(
            worker_blocks={
                wid: bs_ser.from_canonical(b)
                for wid, b in data.get("worker_blocks", {}).items()
            },
            control_complexity_regions=[
                r_ser.from_canonical(r) for r in data.get("control_complexity_regions", [])
            ],
            warnings=data.get("warnings", []),
        )


class WorkerStepPlanIRSerializer(ArtifactSerializer):
    type_id = "WorkerStepPlanIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        p: WorkerStepPlanIR = obj
        step_ser = StepIRSerializer()
        return {
            "$type": self.type_id,
            "main_worker_id": p.main_worker_id,
            "worker_steps": {
                wid: [step_ser.to_canonical(s) for s in steps]
                for wid, steps in p.worker_steps.items()
            },
            "warnings": p.warnings,
            "step_variable_relation_plan": (
                p.step_variable_relation_plan.to_payload()
                if p.step_variable_relation_plan is not None
                else None
            ),
            "composite_output_plans": [plan.to_payload() for plan in p.composite_output_plans],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        from nl2spl.ir.composite_output_plan_ir import CompositeOutputPlan
        from nl2spl.ir.step_variable_relation_ir import StepVariableRelationPlan

        step_ser = StepIRSerializer()

        step_var_rel_data = data.get("step_variable_relation_plan")
        step_variable_relation_plan = (
            StepVariableRelationPlan.from_payload(step_var_rel_data)
            if step_var_rel_data is not None
            else None
        )

        composite_output_plans = tuple(
            CompositeOutputPlan.from_payload(plan_data)
            for plan_data in data.get("composite_output_plans", [])
        )

        return WorkerStepPlanIR(
            main_worker_id=data["main_worker_id"],
            worker_steps={
                wid: [step_ser.from_canonical(s) for s in steps]
                for wid, steps in data.get("worker_steps", {}).items()
            },
            warnings=data.get("warnings", []),
            step_variable_relation_plan=step_variable_relation_plan,
            composite_output_plans=composite_output_plans,
        )


# ===================================================================
# ConstructPlan
# ===================================================================


class ConstructPlanSerializer(ArtifactSerializer):
    type_id = "ConstructPlan"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_diagnostics import (
            CompileDiagnosticSerializer,
        )
        from nl2spl.compiler.construct_plan.model import ConstructPlan

        p: ConstructPlan = obj
        diag_ser = CompileDiagnosticSerializer()
        return {
            "$type": self.type_id,
            "plan_id": p.plan_id,
            "source_schema": p.source_schema,
            "demands": [
                self._demand_to_canonical(demand)
                for demand in p.demands
            ],
            "api_call_argument_bindings": [
                binding.to_payload()
                for binding in p.api_call_argument_bindings
            ],
            "reserved_span_ids": sorted(p.reserved_span_ids) if p.reserved_span_ids else [],
            "dual_role_span_ids": sorted(p.dual_role_span_ids) if p.dual_role_span_ids else [],
            "diagnostics": [
                diag_ser.to_canonical(diagnostic)
                for diagnostic in p.diagnostics
            ],
            "warnings": p.warnings,
            "metadata": p.metadata,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_diagnostics import (
            CompileDiagnosticSerializer,
        )
        from nl2spl.compiler.construct_plan.model import ConstructPlan

        diag_ser = CompileDiagnosticSerializer()

        return ConstructPlan(
            plan_id=data["plan_id"],
            source_schema=data.get("source_schema"),
            demands=[
                self._demand_from_canonical(demand)
                for demand in data.get("demands", [])
            ],
            api_call_argument_bindings=[
                self._argument_binding_from_canonical(binding)
                for binding in data.get("api_call_argument_bindings", [])
            ],
            reserved_span_ids=set(data.get("reserved_span_ids", [])),
            dual_role_span_ids=set(data.get("dual_role_span_ids", [])),
            diagnostics=[
                diag_ser.from_canonical(diagnostic)
                for diagnostic in data.get("diagnostics", [])
            ],
            warnings=data.get("warnings", []),
            metadata=data.get("metadata", {}),
        )

    @staticmethod
    def _slot_to_canonical(slot: Any) -> dict[str, Any]:
        return slot.to_payload()

    @staticmethod
    def _slot_from_canonical(data: dict[str, Any]) -> Any:
        from nl2spl.compiler.construct_plan.model import ConstructSlotDemand

        return ConstructSlotDemand(
            slot_name=data["slot_name"],
            source_span_ids=list(data.get("source_span_ids", [])),
            semantic_roles=list(data.get("semantic_roles", [])),
            executable_values=list(data.get("executable_values", [])),
            source_section_id=data.get("source_section_id"),
            source_packet_id=data.get("source_packet_id"),
            evidence_relation=data.get("evidence_relation", "direct"),
            status=data.get("status", "present"),
            metadata=dict(data.get("metadata", {})),
        )

    @classmethod
    def _demand_to_canonical(cls, demand: Any) -> dict[str, Any]:
        payload = demand.to_payload()
        payload["$demand_type"] = type(demand).__name__
        return payload

    @staticmethod
    def _argument_binding_from_canonical(data: dict[str, Any]) -> Any:
        from nl2spl.compiler.construct_plan.model import APICallArgumentBindingIR

        return APICallArgumentBindingIR(
            call_demand_id=data["call_demand_id"],
            input_bindings=dict(data.get("input_bindings", {})),
            output_bindings=dict(data.get("output_bindings", {})),
            binding_status=data.get("binding_status", "not_required"),
            unresolved_binding_claims=tuple(
                data.get("unresolved_binding_claims", [])
            ),
            source_span_ids=tuple(data.get("source_span_ids", [])),
        )

    @classmethod
    def _demand_from_canonical(cls, data: dict[str, Any]) -> Any:
        from nl2spl.compiler.construct_plan.model import (
            APICallDemand,
            APIDeclarationDemand,
            ConstructDemand,
            ExceptionFlowDemand,
            OperationCoverageIR,
        )
        from nl2spl.compiler.constructs.graph import ConstructEdge

        slots = {
            name: cls._slot_from_canonical(slot_data)
            for name, slot_data in data.get("slots", {}).items()
        }
        related_edges = [
            ConstructEdge(
                from_id=edge["from_id"],
                to_id=edge["to_id"],
                edge_type=edge["edge_type"],
                source_span_ids=list(edge.get("source_span_ids", [])),
                metadata=dict(edge.get("metadata", {})),
            )
            for edge in data.get("related_edges", [])
        ]
        common: dict[str, Any] = {
            "demand_id": data["demand_id"],
            "construct_type": data.get("construct_type", "EXCEPTION_FLOW"),
            "slots": slots,
            "pairing_status": data.get("pairing_status", "unknown"),
            "materialization_policy": data.get(
                "materialization_policy", "source_backed_only"
            ),
            "owner_policy": data.get("owner_policy", "unspecified"),
            "owner_worker_id": data.get("owner_worker_id"),
            "reserved_span_ids": set(data.get("reserved_span_ids", [])),
            "dual_role_span_ids": set(data.get("dual_role_span_ids", [])),
            "source_span_ids": list(data.get("source_span_ids", [])),
            "source_section_id": data.get("source_section_id"),
            "source_packet_id": data.get("source_packet_id"),
            "construct_path": tuple(data.get("construct_path", [])),
            "related_edges": related_edges,
            "metadata": dict(data.get("metadata", {})),
        }
        if (
            data.get("$demand_type") == "ExceptionFlowDemand"
            or common["construct_type"] == "EXCEPTION_FLOW"
        ):
            return ExceptionFlowDemand(
                **common,
                condition_span_ids=list(data.get("condition_span_ids", [])),
                handler_span_ids=list(data.get("handler_span_ids", [])),
                condition_text=data.get("condition_text"),
            )
        if (
            data.get("$demand_type") == "APIDeclarationDemand"
            or common["construct_type"] == "API_DECLARATION"
        ):
            return APIDeclarationDemand(
                **common,
                declaration_annotation_ids=list(
                    data.get("declaration_annotation_ids", [])
                ),
                explicit_name_candidates=list(
                    data.get("explicit_name_candidates", [])
                ),
                integration_admission=data.get(
                    "integration_admission", "candidate"
                ),
                mechanism_status=data.get("mechanism_status", "unknown"),
                inferred_name_allowed=data.get("inferred_name_allowed", False),
                api_group_id=data.get("api_group_id"),
                owner_scope=data.get("owner_scope", "agent_global"),
                capability_intent_id=data.get("capability_intent_id"),
                capability_surface=data.get("capability_surface"),
            )
        if (
            data.get("$demand_type") == "APICallDemand"
            or common["construct_type"] == "CALL_API"
        ):
            return APICallDemand(
                **common,
                call_annotation_ids=list(data.get("call_annotation_ids", [])),
                declaration_demand_id=data.get("declaration_demand_id"),
                api_group_id=data.get("api_group_id"),
                action_text=data.get("action_text"),
                worker_candidate_id=data.get("worker_candidate_id"),
                capability_intent_id=data.get("capability_intent_id"),
                operation_coverage=[
                    OperationCoverageIR(
                        coverage_id=item["coverage_id"],
                        source_span_id=item["source_span_id"],
                        operation_surface=item["operation_surface"],
                        char_start=item.get("char_start"),
                        char_end=item.get("char_end"),
                        relation=item.get("relation", "direct"),
                    )
                    for item in data.get("operation_coverage", [])
                ],
                consumes_behavior_span_ids=list(
                    data.get("consumes_behavior_span_ids", [])
                ),
                residual_behavior_span_ids=list(
                    data.get("residual_behavior_span_ids", [])
                ),
                behavior_lowering_policy=data.get(
                    "behavior_lowering_policy", "ambiguous"
                ),
            )
        return ConstructDemand(**common)


class APICallPlacementIRSerializer(ArtifactSerializer):
    type_id = "APICallPlacementIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        return {"$type": self.type_id, **obj.to_payload()}

    def from_canonical(self, data: dict[str, Any]) -> Any:
        from nl2spl.compiler.construct_plan.model import APICallPlacementIR

        return APICallPlacementIR(
            call_demand_id=data["call_demand_id"],
            owner_worker_id=data.get("owner_worker_id"),
            flow_ref=data.get("flow_ref"),
            block_ref=data.get("block_ref"),
            status=data.get("status", "unresolved"),
            source_span_ids=list(data.get("source_span_ids", [])),
            reason=data.get("reason"),
        )


class APICallBindingIRSerializer(ArtifactSerializer):
    type_id = "APICallBindingIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        return {"$type": self.type_id, **obj.to_payload()}

    def from_canonical(self, data: dict[str, Any]) -> Any:
        from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
            APICallBindingIR,
        )

        return APICallBindingIR(
            api_binding_id=data["api_binding_id"],
            declaration_demand_id=data["declaration_demand_id"],
            api_id=data["api_id"],
            api_name=data["api_name"],
            call_demand_ids=list(data.get("call_demand_ids", [])),
            binding_status=data.get("binding_status", "bound"),
            source_span_ids=list(data.get("source_span_ids", [])),
        )

class APIMaterializationRecordIRSerializer(ArtifactSerializer):
    type_id = "APIMaterializationRecordIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        return {"$type": self.type_id, **obj.to_payload()}

    def from_canonical(self, data: dict[str, Any]) -> Any:
        from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
            APIMaterializationRecordIR,
        )

        return APIMaterializationRecordIR(
            declaration_demand_id=data["declaration_demand_id"],
            capability_intent_id=data.get("capability_intent_id"),
            api_id=data.get("api_id"),
            api_name=data.get("api_name"),
            materialization_status=data.get("materialization_status", "unsupported"),
            renderability_status=data.get("renderability_status", "blocked"),
            name_status=data.get("name_status", "missing"),
            auth_status=data.get("auth_status", "defaulted_none"),
            schema_status=data.get("schema_status", "unknown_placeholder"),
            functions_status=data.get("functions_status", "unknown_placeholder"),
            reasons=list(data.get("reasons", [])),
            source_span_ids=list(data.get("source_span_ids", [])),
        )

class APIMaterializationPlanIRSerializer(ArtifactSerializer):
    type_id = "APIMaterializationPlanIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_resource import (
            APISpecSerializer,
        )

        api_ser = APISpecSerializer()
        binding_ser = APICallBindingIRSerializer()
        record_ser = APIMaterializationRecordIRSerializer()
        return {
            "$type": self.type_id,
            "plan_id": obj.plan_id,
            "api_specs": [api_ser.to_canonical(api) for api in obj.api_specs],
            "bindings": [
                binding_ser.to_canonical(binding)
                for binding in obj.bindings
            ],
            "records": [
                record_ser.to_canonical(record)
                for record in obj.records
            ],
            "unsupported_declaration_demand_ids": list(
                obj.unsupported_declaration_demand_ids
            ),
            "metadata": dict(obj.metadata),
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_resource import (
            APISpecSerializer,
        )
        from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
            APIMaterializationPlanIR,
        )

        api_ser = APISpecSerializer()
        binding_ser = APICallBindingIRSerializer()
        record_ser = APIMaterializationRecordIRSerializer()
        return APIMaterializationPlanIR(
            plan_id=data.get("plan_id", "api_materialization_plan_00"),
            api_specs=[
                api_ser.from_canonical(api)
                for api in data.get("api_specs", [])
            ],
            bindings=[
                binding_ser.from_canonical(binding)
                for binding in data.get("bindings", [])
            ],
            records=[
                record_ser.from_canonical(record)
                for record in data.get("records", [])
            ],
            unsupported_declaration_demand_ids=list(
                data.get("unsupported_declaration_demand_ids", [])
            ),
            metadata=dict(data.get("metadata", {})),
        )


class ConditionVariableReferencePlanSerializer(ArtifactSerializer):
    type_id = "ConditionVariableReferencePlan"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        return {"$type": self.type_id, **obj.to_payload()}

    def from_canonical(self, data: dict[str, Any]) -> Any:
        payload = dict(data)
        payload.pop("$type", None)
        return ConditionVariableReferencePlan.from_payload(payload)


# ===================================================================
# Registration
# ===================================================================


def register_all(registry: SerializerRegistry) -> None:
    _reg = registry.register
    _cls = registry.register_for_class

    serializers: list[ArtifactSerializer] = [
        ContractFieldIRSerializer(),
        InputBindingIRSerializer(),
        OutputBindingIRSerializer(),
        InvokeLocationHintIRSerializer(),
        HandoffFailurePolicyIRSerializer(),
        HandoffContractIRSerializer(),
        WorkerSpecIRSerializer(),
        WorkerHandoffIRSerializer(),
        CandidateTaskUnitIRSerializer(),
        WorkerBoundaryDecisionIRSerializer(),
        ControlComplexityRegionIRSerializer(),
        StepIRSerializer(),
        BlockIRSerializer(),
        DelegationCandidateSerializer(),
        FlowStructureIRSerializer(),
        BlockStructureIRSerializer(),
        WorkerPlanIRSerializer(),
        WorkerFlowPlanIRSerializer(),
        WorkerBlockPlanIRSerializer(),
        WorkerStepPlanIRSerializer(),
        ConstructPlanSerializer(),
        APICallPlacementIRSerializer(),
        APICallBindingIRSerializer(),
        APIMaterializationRecordIRSerializer(),
        APIMaterializationPlanIRSerializer(),
        ConditionVariableReferencePlanSerializer(),
    ]
    for s in serializers:
        _reg(s)

    _cls(ContractFieldIR, serializers[0])
    _cls(InputBindingIR, serializers[1])
    _cls(OutputBindingIR, serializers[2])
    _cls(InvokeLocationHintIR, serializers[3])
    _cls(HandoffFailurePolicyIR, serializers[4])
    _cls(HandoffContractIR, serializers[5])
    _cls(WorkerSpecIR, serializers[6])
    _cls(WorkerHandoffIR, serializers[7])
    _cls(CandidateTaskUnitIR, serializers[8])
    _cls(WorkerBoundaryDecisionIR, serializers[9])
    _cls(ControlComplexityRegionIR, serializers[10])
    _cls(StepIR, serializers[11])
    _cls(BlockIR, serializers[12])
    _cls(DelegationCandidate, serializers[13])
    _cls(FlowStructureIR, serializers[14])
    _cls(BlockStructureIR, serializers[15])
    _cls(WorkerPlanIR, serializers[16])
    _cls(WorkerFlowPlanIR, serializers[17])
    _cls(WorkerBlockPlanIR, serializers[18])
    _cls(WorkerStepPlanIR, serializers[19])
    from nl2spl.compiler.construct_plan.model import ConstructPlan

    _cls(ConstructPlan, serializers[20])
    from nl2spl.compiler.construct_plan.model import APICallPlacementIR

    _cls(APICallPlacementIR, serializers[21])
    from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
        APICallBindingIR,
        APIMaterializationPlanIR,
        APIMaterializationRecordIR,
    )

    _cls(APICallBindingIR, serializers[22])
    _cls(APIMaterializationRecordIR, serializers[23])
    _cls(APIMaterializationPlanIR, serializers[24])
    _cls(ConditionVariableReferencePlan, serializers[25])
