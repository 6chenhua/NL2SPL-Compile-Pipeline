"""Serializers for plan-layer artifacts: WorkerPlanIR family, flow/block/step.

Field names match actual IR dataclass definitions.  Nested types within
this file use inline serialization to avoid circular imports.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.artifacts.snapshot.serialization.protocol import ArtifactSerializer
from nl2spl.compiler.artifacts.snapshot.serialization.registry import SerializerRegistry
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
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
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        step_ser = StepIRSerializer()
        return WorkerStepPlanIR(
            main_worker_id=data["main_worker_id"],
            worker_steps={
                wid: [step_ser.from_canonical(s) for s in steps]
                for wid, steps in data.get("worker_steps", {}).items()
            },
            warnings=data.get("warnings", []),
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

    @classmethod
    def _demand_from_canonical(cls, data: dict[str, Any]) -> Any:
        from nl2spl.compiler.construct_plan.model import (
            ConstructDemand,
            ExceptionFlowDemand,
        )
        from nl2spl.compiler.irs.graph import ConstructEdge

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
        return ConstructDemand(**common)


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
