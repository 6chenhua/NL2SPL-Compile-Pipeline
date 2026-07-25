"""Independently registered stage slices for Worker Delegation v2."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass

from nl2spl.compiler.spl_editing.interaction.model import (
    NormalizedWorkerDelegationDirective,
)
from nl2spl.compiler.spl_editing.stage_slices.errors import (
    StageAuthorityMismatchError,
    StageSliceValidationError,
)
from nl2spl.compiler.spl_editing.stage_slices.model import StageSliceInput
from nl2spl.compiler.spl_editing.stage_slices.registry import StageSliceRegistry
from nl2spl.compiler.spl_editing.stage_slices.result import StageSliceResult
from nl2spl.compiler.spl_editing.stage_slices.worker_delegation_plans import (
    ChildWorkerBlockPlan,
    ChildWorkerCommandPlan,
    ChildWorkerFlowPlan,
    DefineChildWorkerBoundaryPlan,
    KeepInMainFlowPlan,
    ParentInvokePlan,
    WorkerHandoffBindingPlan,
    WorkerSymbolBindingPlan,
)
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.step_variable_relation_ir import (
    StepVariableRelation,
    StepVariableRelationPlan,
)
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerHandoffIR,
    WorkerSpecIR,
)

_PLAN_ID = "worker_delegation.complete_closure.v2"
_AUTHORITY = (
    "stage3_5.worker_boundary + stage4.worker_flow_plan + "
    "stage5.worker_block_plan + stage7.worker_step_plan"
)


def _directive(input_data: StageSliceInput) -> NormalizedWorkerDelegationDirective:
    value = input_data.intent.payload
    if not isinstance(value, NormalizedWorkerDelegationDirective):
        raise StageSliceValidationError(
            "Worker Delegation slices require NormalizedWorkerDelegationDirective."
        )
    return value


def _metadata(input_data: StageSliceInput, *, closure_role: str) -> dict[str, str]:
    directive = _directive(input_data)
    packet = input_data.evidence_packet
    values = {
        "origin": "user_confirmed_repair" if packet else "preview_repair",
        "normalized_directive_id": directive.directive_id,
        "materialization_plan_id": _PLAN_ID,
        "materialization_authority": _AUTHORITY,
        "closure_role": closure_role,
        "target_worker_promotion_ref_id": input_data.target.target_ref,
        "consumed_selected_ref_ids": json.dumps(
            [item.ref.ref_id for item in directive.selected_input_refs]
        ),
        "selected_ref_canonical_names": json.dumps(
            [item.ref.canonical_name for item in directive.selected_input_refs]
        ),
    }
    if packet is not None:
        values.update(
            repair_patch_id=packet.repair_patch_id,
            related_diagnostic_id=packet.related_diagnostic_id,
            evidence_packet_id=packet.evidence_packet_id,
            user_text=packet.user_text,
        )
    return values


def _ensure_step_produces_relations(
    step_plan,
    command: StepIR,
    output_names: tuple[str, ...],
) -> tuple[bool, tuple[str, ...]]:
    existing_plan = step_plan.step_variable_relation_plan
    relations = list(existing_plan.relations) if existing_plan is not None else []
    diagnostics = existing_plan.diagnostics if existing_plan is not None else ()
    existing_keys = {
        (relation.step_id, relation.variable_name, relation.relation)
        for relation in relations
    }
    generated_refs: list[str] = []
    for output_name in output_names:
        key = (command.step_id, output_name, "produces")
        if key in existing_keys:
            continue
        relations.append(
            StepVariableRelation(
                step_id=command.step_id,
                variable_name=output_name,
                relation="produces",
                source_span_ids=tuple(command.source_span_ids),
                evidence_kind="user_confirmed_repair",
                evidence_source="user_confirmed_repair",
                evidence_text=command.text,
                reason="worker_delegation_child_command_output",
                confidence="high",
            )
        )
        generated_refs.append(f"step_variable_relation:{command.step_id}:{output_name}")
    if not generated_refs:
        return False, ()
    step_plan.step_variable_relation_plan = StepVariableRelationPlan(
        relations=tuple(relations),
        diagnostics=diagnostics,
    )
    return True, tuple(generated_refs)


@dataclass(frozen=True)
class _SliceSpec:
    slice_id: str
    stage_authority: str
    policy_id: str
    output_artifact: str
    write_layer: str
    snapshot_field: str
    plan_type: type


class _WorkerDelegationSlice:
    spec: _SliceSpec

    @property
    def slice_id(self) -> str:
        return self.spec.slice_id

    @property
    def stage_authority(self) -> str:
        return self.spec.stage_authority

    @property
    def policy_id(self) -> str:
        return self.spec.policy_id

    @property
    def output_artifacts(self) -> tuple[str, ...]:
        return (self.spec.output_artifact,)

    @property
    def write_layers(self) -> tuple[str, ...]:
        return (self.spec.write_layer,)

    def _validate(self, input_data: StageSliceInput):
        if input_data.slice_id != self.slice_id:
            raise StageSliceValidationError("Stage slice id does not match registration.")
        if input_data.stage_authority != self.stage_authority:
            raise StageAuthorityMismatchError(
                f"{self.slice_id} requires authority '{self.stage_authority}'."
            )
        if not isinstance(input_data.typed_plan, self.spec.plan_type):
            raise StageSliceValidationError(
                f"{self.slice_id} requires {self.spec.plan_type.__name__}."
            )
        if getattr(input_data.snapshot, self.spec.snapshot_field) is None:
            raise StageSliceValidationError(
                f"{self.spec.snapshot_field} is required by {self.slice_id}."
            )
        return input_data.typed_plan

    def _result(
        self,
        input_data: StageSliceInput,
        *,
        update,
        changed_refs: tuple[str, ...] = (),
        generated_refs: tuple[str, ...] = (),
        allocated_ids: tuple[str, ...] = (),
        action: str,
        trace: dict | None = None,
    ) -> StageSliceResult:
        directive = _directive(input_data)
        return StageSliceResult(
            slice_id=self.slice_id,
            stage_authority=self.stage_authority,
            policy_id=self.policy_id,
            changed_artifact_refs=changed_refs,
            generated_construct_refs=generated_refs,
            consumed_selected_ref_ids=tuple(
                item.ref.ref_id for item in directive.selected_input_refs
            ),
            consumed_directive_id=directive.directive_id,
            allocated_ids=allocated_ids,
            trace={"action": action, **(trace or {})},
            artifact_updates={self.spec.snapshot_field: update},
        )


class Stage35DefineChildWorkerSlice(_WorkerDelegationSlice):
    spec = _SliceSpec(
        "stage3_5.define_child_worker.v2",
        "stage3_5.worker_boundary",
        "worker_delegation.define_child_worker.v2",
        "WorkerPlanIR",
        "worker_plan_pre_normalize",
        "worker_plan",
        DefineChildWorkerBoundaryPlan,
    )

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        plan = self._validate(input_data)
        worker_plan = copy.deepcopy(input_data.snapshot.worker_plan)
        matches = [w for w in worker_plan.workers if w.worker_id == plan.worker_id]
        if matches:
            worker = matches[0]
            expected_inputs = tuple(field.name for field in plan.input_contract)
            expected_outputs = tuple(field.name for field in plan.output_contract)
            if (
                worker.kind != "child"
                or worker.purpose != plan.purpose
                or tuple(field.name for field in worker.input_contract) != expected_inputs
                or tuple(field.name for field in worker.output_contract) != expected_outputs
            ):
                raise StageSliceValidationError("Existing child boundary does not match plan.")
            return self._result(input_data, update=worker_plan, action="bind_existing")
        spans = list(input_data.issue.source_span_ids)
        worker_plan.workers.append(
            WorkerSpecIR(
                worker_id=plan.worker_id,
                worker_name=plan.worker_name,
                kind="child",
                purpose=plan.purpose,
                owned_span_ids=spans,
                input_contract=[
                    ContractFieldIR(
                        name=field.name,
                        data_type=field.data_type,
                        required=True,
                        description=field.description,
                        source="derived",
                        source_span_ids=spans,
                    )
                    for field in plan.input_contract
                ],
                output_contract=[
                    ContractFieldIR(
                        name=field.name,
                        data_type=field.data_type,
                        required=True,
                        description=field.description,
                        source="derived",
                        source_span_ids=spans,
                    )
                    for field in plan.output_contract
                ],
                boundary_kind="child_worker",
                reason="User-confirmed worker delegation repair",
                input_contract_status="known_present" if plan.input_contract else "known_empty",
                output_contract_status="known_present",
                input_contract_status_source="user_confirmed_repair",
                output_contract_status_source="user_confirmed_repair",
            )
        )
        ref = f"worker:{plan.worker_id}"
        return self._result(
            input_data,
            update=worker_plan,
            changed_refs=(ref,),
            generated_refs=(ref,),
            allocated_ids=(plan.worker_id,),
            action="materialize",
        )


class Stage4ChildWorkerFlowSlice(_WorkerDelegationSlice):
    spec = _SliceSpec(
        "stage4.child_worker_flow.v2",
        "stage4.worker_flow_plan",
        "worker_delegation.child_flow.v2",
        "WorkerFlowPlanIR",
        "worker_flow_plan_pre_normalize",
        "worker_flow_plan",
        ChildWorkerFlowPlan,
    )

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        plan = self._validate(input_data)
        flow_plan = copy.deepcopy(input_data.snapshot.worker_flow_plan)
        if plan.worker_id in flow_plan.worker_flows:
            return self._result(input_data, update=flow_plan, action="bind_existing")
        flow_plan.worker_flows[plan.worker_id] = FlowStructureIR(
            main_flow_spans=list(input_data.issue.source_span_ids)
        )
        ref = f"flow:{plan.worker_id}:main"
        return self._result(
            input_data,
            update=flow_plan,
            changed_refs=(ref,),
            generated_refs=(ref,),
            action="materialize",
        )


class Stage5WorkerDelegationBlockSlice(_WorkerDelegationSlice):
    spec = _SliceSpec(
        "stage5.worker_delegation_blocks.v2",
        "stage5.worker_block_plan",
        "worker_delegation.blocks.v2",
        "WorkerBlockPlanIR",
        "worker_block_plan_pre_normalize",
        "worker_block_plan",
        ChildWorkerBlockPlan,
    )

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        plan = self._validate(input_data)
        block_plan = copy.deepcopy(input_data.snapshot.worker_block_plan)
        changed: list[str] = []
        generated: list[str] = []
        allocated: list[str] = []
        existing = block_plan.worker_blocks.get(plan.worker_id)
        if existing is None:
            block_plan.worker_blocks[plan.worker_id] = BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(
                        plan.block_id,
                        plan.block_type,
                        spans=list(input_data.issue.source_span_ids),
                    )
                ]
            )
            ref = f"block:{plan.worker_id}:{plan.block_id}"
            changed.append(ref)
            generated.append(ref)
            allocated.append(plan.block_id)
        elif (
            len(existing.main_flow_blocks) != 1
            or existing.main_flow_blocks[0].block_id != plan.block_id
            or existing.main_flow_blocks[0].block_type != plan.block_type
        ):
            raise StageSliceValidationError("Existing child block does not match plan.")

        parent_id = plan.parent_worker_id
        parent_structure = block_plan.worker_blocks.get(parent_id)
        if parent_structure is None:
            parent_structure = BlockStructureIR()
            block_plan.worker_blocks[parent_id] = parent_structure
        parent_block_id = plan.parent_block_id
        if not parent_structure.main_flow_blocks:
            parent_structure.main_flow_blocks.append(
                BlockIR(parent_block_id, "SEQUENTIAL", spans=[])
            )
            ref = f"block:{parent_id}:{parent_block_id}"
            changed.append(ref)
            generated.append(ref)
            allocated.append(parent_block_id)
        return self._result(
            input_data,
            update=block_plan,
            changed_refs=tuple(changed),
            generated_refs=tuple(generated),
            allocated_ids=tuple(allocated),
            action="materialize" if changed else "bind_existing",
        )


class Stage7ChildWorkerCommandSlice(_WorkerDelegationSlice):
    spec = _SliceSpec(
        "stage7.child_worker_command.v2",
        "stage7.worker_step_plan",
        "worker_delegation.child_command.v2",
        "WorkerStepPlanIR",
        "worker_step_plan_pre_normalize",
        "worker_step_plan",
        ChildWorkerCommandPlan,
    )

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        plan = self._validate(input_data)
        if not plan.output_names:
            raise StageSliceValidationError("Child command cannot be side-effect-only.")
        step_plan = copy.deepcopy(input_data.snapshot.worker_step_plan)
        existing = step_plan.worker_steps.get(plan.worker_id, [])
        if existing:
            if len(existing) != 1:
                raise StageSliceValidationError("Child closure requires exactly one command.")
            command = existing[0]
            if (
                command.step_id != plan.command_id
                or command.command_type != "GENERAL_COMMAND"
                or command.text != plan.action_text
                or tuple(command.inputs) != plan.input_names
                or tuple(command.outputs) != plan.output_names
                or command.block_ref != plan.block_id
            ):
                raise StageSliceValidationError("Existing child command does not match plan.")
            relation_changed, relation_refs = _ensure_step_produces_relations(
                step_plan,
                command,
                plan.output_names,
            )
            return self._result(
                input_data,
                update=step_plan,
                changed_refs=relation_refs,
                generated_refs=relation_refs,
                action="materialize" if relation_changed else "bind_existing",
            )
        command = StepIR(
            step_id=plan.command_id,
            text=plan.action_text,
            source_span_ids=list(input_data.issue.source_span_ids),
            command_type="GENERAL_COMMAND",
            inputs=list(plan.input_names),
            outputs=list(plan.output_names),
            flow_ref="main",
            block_ref=plan.block_id,
            metadata=_metadata(input_data, closure_role="child_command"),
        )
        step_plan.worker_steps[plan.worker_id] = [command]
        _relation_changed, relation_refs = _ensure_step_produces_relations(
            step_plan,
            command,
            plan.output_names,
        )
        ref = f"step:{plan.worker_id}:{plan.command_id}"
        return self._result(
            input_data,
            update=step_plan,
            changed_refs=(ref, *relation_refs),
            generated_refs=(ref, *relation_refs),
            allocated_ids=(plan.command_id,),
            action="materialize",
        )


class Stage35WorkerDelegationHandoffSlice(_WorkerDelegationSlice):
    spec = _SliceSpec(
        "stage3_5.worker_handoff_contract.v2",
        "stage3_5.worker_boundary",
        "worker_delegation.handoff.v2",
        "WorkerPlanIR",
        "worker_plan_pre_normalize",
        "worker_plan",
        WorkerHandoffBindingPlan,
    )

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        plan = self._validate(input_data)
        worker_plan = copy.deepcopy(input_data.snapshot.worker_plan)
        matches = [h for h in worker_plan.handoffs if h.handoff_id == plan.handoff_id]
        if matches:
            handoff = matches[0]
            actual_inputs = tuple(
                (item.parent_variable, item.child_input) for item in handoff.input_bindings
            )
            actual_outputs = tuple(
                (item.child_output, item.parent_variable) for item in handoff.output_bindings
            )
            expected_outputs = tuple(
                (item.child_output_name, item.parent_target_name) for item in plan.output_bindings
            )
            if (
                handoff.from_worker != plan.parent_worker_id
                or handoff.to_worker != plan.child_worker_id
                or actual_inputs != plan.input_bindings
                or actual_outputs != expected_outputs
            ):
                raise StageSliceValidationError("Existing handoff does not match plan.")
            return self._result(input_data, update=worker_plan, action="bind_existing")
        directive = _directive(input_data)
        placement_span = (
            input_data.issue.source_span_ids[0] if input_data.issue.source_span_ids else None
        )
        ordering = "before" if directive.invocation_timing.placement_mode == "before" else "after"
        worker_plan.handoffs.append(
            WorkerHandoffIR(
                handoff_id=plan.handoff_id,
                from_worker=plan.parent_worker_id,
                to_worker=plan.child_worker_id,
                api_ref=None,
                mode="invoke",
                condition_text=None,
                ordering=ordering,
                input_bindings=[
                    InputBindingIR(parent, child, True) for parent, child in plan.input_bindings
                ],
                output_bindings=[
                    OutputBindingIR(item.child_output_name, item.parent_target_name, True, "set")
                    for item in plan.output_bindings
                ],
                invoke_location_hint=InvokeLocationHintIR(
                    flow_kind="main",
                    flow_id="main",
                    after_span_id=placement_span if ordering == "after" else None,
                    before_span_id=placement_span if ordering == "before" else None,
                    block_hint="sequential",
                ),
                input_binding_status="known_present" if plan.input_bindings else "known_empty",
                output_binding_status="known_present",
                input_binding_status_source="user_confirmed_repair",
                output_binding_status_source="user_confirmed_repair",
                materialization_status="materialized",
            )
        )
        ref = f"handoff:{plan.handoff_id}"
        return self._result(
            input_data,
            update=worker_plan,
            changed_refs=(ref,),
            generated_refs=(ref,),
            allocated_ids=(plan.handoff_id,),
            action="materialize",
        )


class Stage7WorkerDelegationInvokeSlice(_WorkerDelegationSlice):
    spec = _SliceSpec(
        "stage7.worker_invoke.v2",
        "stage7.worker_step_plan",
        "worker_delegation.parent_invoke.v2",
        "WorkerStepPlanIR",
        "worker_step_plan_pre_normalize",
        "worker_step_plan",
        ParentInvokePlan,
    )

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        plan = self._validate(input_data)
        step_plan = copy.deepcopy(input_data.snapshot.worker_step_plan)
        parent_steps = step_plan.worker_steps.setdefault(plan.parent_worker_id, [])
        matches = [step for step in parent_steps if step.handoff_id == plan.handoff_id]
        if matches:
            if len(matches) != 1:
                raise StageSliceValidationError("Handoff has multiple parent invokes.")
            step = matches[0]
            if (
                step.step_id != plan.command_id
                or step.command_type != "INVOKE_WORKER"
                or tuple(step.inputs) != plan.input_names
                or tuple(step.outputs) != plan.output_names
                or step.integration_ref not in {plan.child_worker_id, plan.child_worker_name}
                or step.block_ref != plan.parent_block_id
            ):
                raise StageSliceValidationError("Existing parent invoke does not match plan.")
            return self._result(input_data, update=step_plan, action="bind_existing")
        parent_steps.append(
            StepIR(
                step_id=plan.command_id,
                text=f"Invoke {plan.child_worker_name}",
                source_span_ids=[],
                command_type="INVOKE_WORKER",
                inputs=list(plan.input_names),
                outputs=list(plan.output_names),
                integration_ref=plan.child_worker_name,
                flow_ref="main",
                block_ref=plan.parent_block_id,
                kind="invoke",
                handoff_id=plan.handoff_id,
                metadata=_metadata(input_data, closure_role="parent_invoke"),
            )
        )
        ref = f"step:{plan.parent_worker_id}:{plan.command_id}"
        return self._result(
            input_data,
            update=step_plan,
            changed_refs=(ref,),
            generated_refs=(ref,),
            allocated_ids=(plan.command_id,),
            action="materialize",
        )


class Stage35WorkerSymbolBindingsSlice(_WorkerDelegationSlice):
    spec = _SliceSpec(
        "stage3_5.worker_symbol_bindings.v2",
        "stage3_5.worker_boundary",
        "worker_delegation.symbol_bindings.v2",
        "SymbolTable",
        "symbol_table_pre_normalize",
        "symbol_table",
        WorkerSymbolBindingPlan,
    )

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        plan = self._validate(input_data)
        symbols = copy.deepcopy(input_data.snapshot.symbol_table)
        changed: list[str] = []
        for field in plan.child_inputs:
            if symbols.lookup(field.name) is None:
                raise StageSliceValidationError(f"Selected input '{field.name}' is undefined.")
            changed.extend(
                _declare_if_missing(
                    symbols, plan.child_worker_id, plan.child_block_id, field, declared=True
                )
            )
        for field in plan.child_outputs:
            changed.extend(
                _declare_if_missing(
                    symbols, plan.child_worker_id, plan.child_block_id, field, declared=True
                )
            )
        for field in plan.parent_temporaries:
            changed.extend(
                _declare_if_missing(
                    symbols, plan.parent_worker_id, plan.parent_block_id, field, declared=False
                )
            )
            symbols._variables[
                ("worker", plan.parent_worker_id, field.name)
            ].producer_step = plan.parent_invoke_command_id
        return self._result(
            input_data,
            update=symbols,
            changed_refs=tuple(changed),
            generated_refs=tuple(changed),
            action="materialize" if changed else "bind_existing",
        )


class Stage35KeepMainBoundarySlice(_WorkerDelegationSlice):
    spec = _SliceSpec(
        "stage3_5.keep_main_boundary.v2",
        "stage3_5.worker_boundary",
        "worker_delegation.keep_main_boundary.v2",
        "WorkerPlanIR",
        "worker_plan_pre_normalize",
        "worker_plan",
        KeepInMainFlowPlan,
    )

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        plan = self._validate(input_data)
        worker_plan = copy.deepcopy(input_data.snapshot.worker_plan)
        handoff_ids = set(plan.owned_handoff_ids)
        child_ids = set(plan.owned_child_worker_ids)
        removed_handoffs = [
            h.handoff_id for h in worker_plan.handoffs if h.handoff_id in handoff_ids
        ]
        removed_workers = [w.worker_id for w in worker_plan.workers if w.worker_id in child_ids]
        worker_plan.handoffs = [h for h in worker_plan.handoffs if h.handoff_id not in handoff_ids]
        worker_plan.workers = [w for w in worker_plan.workers if w.worker_id not in child_ids]
        changed = tuple(
            [
                *(f"removed:handoff:{value}" for value in removed_handoffs),
                *(f"removed:worker:{value}" for value in removed_workers),
            ]
        )
        return self._result(
            input_data,
            update=worker_plan,
            changed_refs=changed,
            action="materialize" if changed else "no_op",
        )


class Stage4KeepMainFlowSlice(_WorkerDelegationSlice):
    spec = _SliceSpec(
        "stage4.keep_main_flow_cleanup.v2",
        "stage4.worker_flow_plan",
        "worker_delegation.keep_main_flow_cleanup.v2",
        "WorkerFlowPlanIR",
        "worker_flow_plan_pre_normalize",
        "worker_flow_plan",
        KeepInMainFlowPlan,
    )

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        plan = self._validate(input_data)
        flow_plan = copy.deepcopy(input_data.snapshot.worker_flow_plan)
        removed = tuple(
            worker_id
            for worker_id in plan.owned_child_worker_ids
            if flow_plan.worker_flows.pop(worker_id, None) is not None
        )
        refs = tuple(f"removed:flow:{worker_id}:main" for worker_id in removed)
        return self._result(
            input_data,
            update=flow_plan,
            changed_refs=refs,
            action="materialize" if refs else "no_op",
        )


class Stage5KeepMainBlockSlice(_WorkerDelegationSlice):
    spec = _SliceSpec(
        "stage5.keep_main_placement.v2",
        "stage5.worker_block_plan",
        "worker_delegation.keep_main_placement.v2",
        "WorkerBlockPlanIR",
        "worker_block_plan_pre_normalize",
        "worker_block_plan",
        KeepInMainFlowPlan,
    )

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        plan = self._validate(input_data)
        block_plan = copy.deepcopy(input_data.snapshot.worker_block_plan)
        changed = [
            f"removed:block:{worker_id}"
            for worker_id in plan.owned_child_worker_ids
            if block_plan.worker_blocks.pop(worker_id, None) is not None
        ]
        structure = block_plan.worker_blocks.get(plan.parent_worker_id)
        if structure is None:
            structure = BlockStructureIR()
            block_plan.worker_blocks[plan.parent_worker_id] = structure
        generated: list[str] = []
        allocated: list[str] = []
        if not structure.main_flow_blocks:
            structure.main_flow_blocks.append(BlockIR(plan.parent_block_id, "SEQUENTIAL", spans=[]))
            ref = f"block:{plan.parent_worker_id}:{plan.parent_block_id}"
            changed.append(ref)
            generated.append(ref)
            allocated.append(plan.parent_block_id)
        return self._result(
            input_data,
            update=block_plan,
            changed_refs=tuple(changed),
            generated_refs=tuple(generated),
            allocated_ids=tuple(allocated),
            action="materialize" if changed else "bind_existing",
        )


class Stage7KeepMainCommandSlice(_WorkerDelegationSlice):
    spec = _SliceSpec(
        "stage7.keep_main_command.v2",
        "stage7.worker_step_plan",
        "worker_delegation.keep_main_command.v2",
        "WorkerStepPlanIR",
        "worker_step_plan_pre_normalize",
        "worker_step_plan",
        KeepInMainFlowPlan,
    )

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        plan = self._validate(input_data)
        step_plan = copy.deepcopy(input_data.snapshot.worker_step_plan)
        handoff_ids = set(plan.owned_handoff_ids)
        child_ids = set(plan.owned_child_worker_ids)
        removed_steps: list[str] = []
        for worker_id, steps in tuple(step_plan.worker_steps.items()):
            kept = []
            for step in steps:
                if worker_id in child_ids or step.handoff_id in handoff_ids:
                    removed_steps.append(step.step_id)
                else:
                    kept.append(step)
            if worker_id in child_ids:
                step_plan.worker_steps.pop(worker_id, None)
            else:
                step_plan.worker_steps[worker_id] = kept
        parent_steps = step_plan.worker_steps.setdefault(plan.parent_worker_id, [])
        directive = _directive(input_data)
        if any(
            step.metadata.get("normalized_directive_id") == directive.directive_id
            for step in parent_steps
        ):
            raise StageSliceValidationError("Directive already materialized.")
        parent_steps.append(
            StepIR(
                step_id=plan.command_id,
                text=plan.action_text,
                source_span_ids=[],
                command_type="GENERAL_COMMAND",
                inputs=[item.ref.canonical_name for item in directive.selected_input_refs],
                outputs=[],
                flow_ref="main",
                block_ref=plan.parent_block_id,
                metadata={
                    **_metadata(input_data, closure_role="main_flow_command"),
                    "resolution_kind": "kept_in_main_flow",
                },
            )
        )
        command_ref = f"step:{plan.parent_worker_id}:{plan.command_id}"
        changed = tuple([*(f"removed:step:{step_id}" for step_id in removed_steps), command_ref])
        return self._result(
            input_data,
            update=step_plan,
            changed_refs=changed,
            generated_refs=(command_ref,),
            allocated_ids=(plan.command_id,),
            action="materialize",
            trace={"removed_candidate_step_ids": removed_steps},
        )


def _declare_if_missing(symbols, worker_id, block_id, field, *, declared: bool) -> list[str]:
    key = ("worker", worker_id, field.name)
    existing = symbols._variables.get(key)
    if existing is not None:
        if declared and not existing.declared:
            existing.data_type = field.data_type
            existing.declared = True
            return [f"symbol:worker:{worker_id}:{field.name}"]
        if _canonical_type(existing.data_type) != _canonical_type(field.data_type):
            if existing.source == "user_confirmed_repair":
                existing.data_type = field.data_type
                existing.description = field.description
                existing.block_ref = block_id
                return [f"symbol:worker:{worker_id}:{field.name}"]
            raise StageSliceValidationError(
                f"Existing worker-local symbol '{field.name}' conflicts with the plan "
                f"({existing.data_type!r} vs {field.data_type!r})."
            )
        if existing.declared != declared:
            if declared and not existing.declared:
                existing.declared = True
                return [f"symbol:worker:{worker_id}:{field.name}"]
            raise StageSliceValidationError(
                f"Existing worker-local symbol '{field.name}' conflicts with the plan "
                f"(declared={existing.declared!r} vs {declared!r})."
            )
        return []
    symbols.declare_scoped(
        field.name,
        field.data_type,
        "user_confirmed_repair",
        field.description,
        scope_kind="worker",
        scope_id=worker_id,
        block_ref=block_id,
    )
    symbols._variables[key].declared = declared
    return [f"symbol:worker:{worker_id}:{field.name}"]


def _canonical_type(data_type: str) -> str:
    return "".join(data_type.split()).lower()


def build_worker_delegation_stage_slice_registry() -> StageSliceRegistry:
    registry = StageSliceRegistry()
    for stage_slice in (
        Stage35DefineChildWorkerSlice(),
        Stage4ChildWorkerFlowSlice(),
        Stage5WorkerDelegationBlockSlice(),
        Stage7ChildWorkerCommandSlice(),
        Stage35WorkerDelegationHandoffSlice(),
        Stage7WorkerDelegationInvokeSlice(),
        Stage35WorkerSymbolBindingsSlice(),
        Stage35KeepMainBoundarySlice(),
        Stage4KeepMainFlowSlice(),
        Stage5KeepMainBlockSlice(),
        Stage7KeepMainCommandSlice(),
    ):
        registry.register(stage_slice, expected_stage_authority=stage_slice.stage_authority)
    return registry


__all__ = [name for name in globals() if name.startswith("Stage") or name.startswith("build_")]
