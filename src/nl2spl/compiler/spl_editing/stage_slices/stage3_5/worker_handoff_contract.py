"""Stage 3.5 repair slice for worker handoff contract materialization."""

from __future__ import annotations

from dataclasses import replace

from nl2spl.compiler.spl_editing.intent.model import CreateWorkerHandoffContractIntentPayload
from nl2spl.compiler.spl_editing.stage_slices.errors import (
    StageAuthorityMismatchError,
    StageSliceValidationError,
)
from nl2spl.compiler.spl_editing.stage_slices.model import StageSliceInput
from nl2spl.compiler.spl_editing.stage_slices.result import StageSliceResult
from nl2spl.ir.worker_contract_status import derive_handoff_materialization_status
from nl2spl.ir.worker_plan_ir import (
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerHandoffIR,
)

_SLICE_ID = "stage3_5.worker_handoff_contract_repair.v1"
_STAGE_AUTHORITY = "stage3_5.worker_boundary"
_POLICY_ID = "worker_delegation.handoff_contract.v1"


class Stage35WorkerHandoffContractRepairSlice:
    """Materialize a WorkerHandoffIR contract for an existing child worker."""

    @property
    def slice_id(self) -> str:
        return _SLICE_ID

    @property
    def stage_authority(self) -> str:
        return _STAGE_AUTHORITY

    @property
    def policy_id(self) -> str:
        return _POLICY_ID

    @property
    def output_artifacts(self) -> tuple[str, ...]:
        return ("WorkerPlanIR", "WorkerHandoffIR")

    @property
    def write_layers(self) -> tuple[str, ...]:
        return ("worker_boundary_pre_normalize",)

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        if input_data.stage_authority != self.stage_authority:
            raise StageAuthorityMismatchError(
                f"Stage3.5 handoff slice requires authority '{self.stage_authority}'."
            )
        if input_data.slice_id != self.slice_id:
            raise StageSliceValidationError(
                f"StageSliceInput slice_id mismatch: '{input_data.slice_id}' != '{self.slice_id}'."
            )
        payload = input_data.intent.payload
        if not isinstance(payload, CreateWorkerHandoffContractIntentPayload):
            raise StageSliceValidationError(
                "Stage3.5 handoff slice requires CreateWorkerHandoffContractIntentPayload."
            )
        if input_data.snapshot.worker_plan is None:
            raise StageSliceValidationError("worker_plan is required.")
        if input_data.id_allocator is None:
            raise StageSliceValidationError("Stage3.5 handoff slice requires id_allocator.")

        worker_plan = input_data.snapshot.worker_plan
        worker_ids = {w.worker_id for w in worker_plan.workers}
        parent_id = payload.parent_worker_id
        child_id = payload.child_worker_id
        if parent_id not in worker_ids:
            raise StageSliceValidationError(f"Parent worker '{parent_id}' not found.")
        if child_id not in worker_ids:
            raise StageSliceValidationError(f"Child worker '{child_id}' not found.")
        if payload.invocation_point not in ("main", "alternative", "exception"):
            raise StageSliceValidationError(
                f"Invalid invocation_point '{payload.invocation_point}'."
            )

        valid_status = {"known_present", "known_empty"}
        if payload.input_binding_status not in valid_status:
            raise StageSliceValidationError(
                f"Invalid input_binding_status '{payload.input_binding_status}'."
            )
        if payload.output_binding_status not in valid_status:
            raise StageSliceValidationError(
                f"Invalid output_binding_status '{payload.output_binding_status}'."
            )
        if payload.input_binding_status == "known_present" and not payload.input_bindings:
            raise StageSliceValidationError(
                "known_present input bindings require at least one binding."
            )
        if payload.output_binding_status == "known_present" and not payload.output_bindings:
            raise StageSliceValidationError(
                "known_present output bindings require at least one binding."
            )
        if payload.input_binding_status == "known_empty" and payload.input_bindings:
            raise StageSliceValidationError("known_empty input bindings must be empty.")
        if payload.output_binding_status == "known_empty" and payload.output_bindings:
            raise StageSliceValidationError("known_empty output bindings must be empty.")

        existing_handoff = self._matching_handoff(worker_plan.handoffs, parent_id, child_id)
        if existing_handoff is None:
            handoff_id = input_data.id_allocator.allocate_handoff_id()
            allocated_ids = (handoff_id,)
            action = "materialize"
        else:
            handoff_id = existing_handoff.handoff_id
            allocated_ids = ()
            action = "bind_existing"
        input_irs = tuple(
            InputBindingIR(parent, child, True) for parent, child in payload.input_bindings
        )
        output_irs = tuple(
            OutputBindingIR(child, parent, True, "set") for child, parent in payload.output_bindings
        )
        mat_status = derive_handoff_materialization_status(
            input_bindings=list(input_irs),
            output_bindings=list(output_irs),
            input_status=payload.input_binding_status,
            output_status=payload.output_binding_status,
        )
        flow = InvokeLocationHintIR(
            flow_kind=payload.invocation_point,
            flow_id=None,
            after_span_id=None,
            before_span_id=None,
            block_hint="sequential",
        )
        if existing_handoff is None:
            handoff = WorkerHandoffIR(
                handoff_id=handoff_id,
                from_worker=parent_id,
                to_worker=child_id,
                api_ref=None,
                mode="invoke",
                condition_text=None,
                ordering="after",
                input_bindings=list(input_irs),
                output_bindings=list(output_irs),
                input_binding_status=payload.input_binding_status,
                output_binding_status=payload.output_binding_status,
                input_binding_status_source="user_confirmed_repair",
                output_binding_status_source="user_confirmed_repair",
                materialization_status=mat_status,
                invoke_location_hint=flow,
            )
        else:
            handoff = replace(
                existing_handoff,
                from_worker=parent_id,
                to_worker=child_id,
                api_ref=None,
                mode="invoke",
                input_bindings=list(input_irs),
                output_bindings=list(output_irs),
                input_binding_status=payload.input_binding_status,
                output_binding_status=payload.output_binding_status,
                input_binding_status_source="user_confirmed_repair",
                output_binding_status_source="user_confirmed_repair",
                materialization_status=mat_status,
                invoke_location_hint=flow,
            )

        existing_handoffs = [h for h in worker_plan.handoffs if h.handoff_id != handoff_id]
        workers = []
        for worker in worker_plan.workers:
            if worker.worker_id == child_id:
                worker = replace(
                    worker,
                    input_contract_status=payload.input_binding_status,
                    output_contract_status=payload.output_binding_status,
                    input_contract_status_source="user_confirmed_repair",
                    output_contract_status_source="user_confirmed_repair",
                )
            workers.append(worker)
        new_worker_plan = replace(
            worker_plan,
            workers=workers,
            handoffs=existing_handoffs + [handoff],
        )
        consumed_ref_ids = tuple(input_data.selected_ref_ids)

        return StageSliceResult(
            slice_id=self.slice_id,
            stage_authority=self.stage_authority,
            policy_id=input_data.stage_policy.policy_id,
            changed_artifact_refs=("worker_plan", "worker_handoff"),
            generated_construct_refs=(f"handoff:{handoff_id}",),
            consumed_selected_ref_ids=consumed_ref_ids,
            consumed_directive_id=input_data.directive.directive_id,
            allocated_ids=allocated_ids,
            trace={
                "action": action,
                "handoff_id": handoff_id,
                "parent_worker_id": parent_id,
                "child_worker_id": child_id,
                "invocation_point": payload.invocation_point,
                "input_bindings": tuple(payload.input_bindings),
                "output_bindings": tuple(payload.output_bindings),
            },
            artifact_updates={"worker_plan": new_worker_plan},
        )

    @staticmethod
    def _matching_handoff(
        handoffs: list[WorkerHandoffIR],
        parent_id: str,
        child_id: str,
    ) -> WorkerHandoffIR | None:
        for handoff in handoffs:
            if handoff.mode != "invoke":
                continue
            if handoff.from_worker != parent_id:
                continue
            if handoff.to_worker != child_id:
                continue
            return handoff
        return None

