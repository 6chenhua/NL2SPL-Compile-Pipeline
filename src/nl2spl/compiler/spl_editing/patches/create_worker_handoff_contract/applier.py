"""CreateWorkerHandoffContract applier — creates WorkerHandoffIR."""

from dataclasses import replace

from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import (
    ArtifactSnapshot,
    OverlayEvent,
    RevisionToken,
)
from nl2spl.compiler.spl_editing.patches.base import PatchApplier
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import (
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerHandoffIR,
)


class CreateWorkerHandoffContractApplier(PatchApplier):
    def apply(self, patch: RepairPatch, snapshot: ArtifactSnapshot) -> tuple[
        ArtifactSnapshot, OverlayEvent,
    ]:
        p = patch.payload
        parent_id = str(p.get("parent_worker_id", ""))
        child_id = str(p.get("child_worker_id", ""))
        promotion_id = str(p.get("worker_promotion_id", ""))
        in_bindings = p.get("input_bindings", {}) or {}
        out_bindings = p.get("output_bindings", {}) or {}
        inv_point = str(p.get("invocation_point", "main"))

        handoff_id = f"handoff_repair_{promotion_id}"
        input_irs = [
            InputBindingIR(pv, ci, True)
            for pv, ci in in_bindings.items()
        ]
        output_irs = [
            OutputBindingIR(co, pv, True, "set")
            for co, pv in out_bindings.items()
        ]

        in_status = str(p.get("input_binding_status", "known_present"))
        out_status = str(p.get("output_binding_status", "known_present"))
        in_source = p.get("input_binding_status_source") or "user_confirmed_repair"
        out_source = p.get("output_binding_status_source") or "user_confirmed_repair"

        from nl2spl.ir.worker_contract_status import (
            derive_handoff_materialization_status,
        )

        mat_status = derive_handoff_materialization_status(
            input_bindings=input_irs,
            output_bindings=output_irs,
            input_status=in_status,
            output_status=out_status,
        )

        valid_flow = inv_point in ("main", "alternative", "exception")
        flow = InvokeLocationHintIR(
            flow_kind=inv_point if valid_flow else "main",
            flow_id=None,
            after_span_id=None,
            before_span_id=None,
            block_hint="sequential",
        )

        handoff = WorkerHandoffIR(
            handoff_id=handoff_id,
            from_worker=parent_id,
            to_worker=child_id,
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=input_irs,
            output_bindings=output_irs,
            input_binding_status=in_status,
            output_binding_status=out_status,
            input_binding_status_source=in_source,
            output_binding_status_source=out_source,
            materialization_status=mat_status,
            invoke_location_hint=flow,
        )

        # Update WorkerPlanIR
        plan = snapshot.require_worker_plan()
        new_handoffs = list(plan.handoffs) + [handoff]
        new_plan = replace(plan, handoffs=new_handoffs)

        # Lane B requires every complete handoff to have exactly one
        # corresponding executable step in the parent worker.
        step_plan = snapshot.require_worker_step_plan()
        worker_steps = {w: list(s) for w, s in step_plan.worker_steps.items()}
        if parent_id not in worker_steps:
            from nl2spl.compiler.spl_editing.core.errors import PatchValidationError

            raise PatchValidationError(
                f"parent worker '{parent_id}' not found in worker_step_plan"
            )
        matching_steps = [
            step
            for steps in worker_steps.values()
            for step in steps
            if step.handoff_id == handoff_id
        ]
        if not matching_steps:
            child_name = child_id
            for worker in plan.workers:
                if worker.worker_id == child_id:
                    child_name = worker.worker_name
                    break
            invoke_step = StepIR(
                step_id=f"st_invoke_{handoff_id}",
                text=f"Invoke worker: {child_name}",
                source_span_ids=[],
                command_type="INVOKE_WORKER",
                inputs=[binding.parent_variable for binding in input_irs],
                outputs=[binding.parent_variable for binding in output_irs],
                integration_ref=child_name,
                flow_ref=flow.flow_kind or "main",
                block_ref="b_main_fallback",
                handoff_id=handoff_id,
                metadata={
                    "origin": "user_confirmed_repair",
                    "repair_patch_id": patch.patch_id,
                    "related_diagnostic_id": patch.evidence.related_diagnostic_id,
                    "user_text": patch.evidence.user_text,
                    "worker_promotion_id": promotion_id,
                },
            )
            worker_steps[parent_id].append(invoke_step)
        new_step_plan = replace(step_plan, worker_steps=worker_steps)

        next_token = RevisionToken(
            snapshot.compile_run_id, snapshot.snapshot_id,
            snapshot.overlay_version + 1,
        )
        patched = snapshot.derive(
            next_token,
            worker_plan=new_plan,
            worker_step_plan=new_step_plan,
            final_spl=None,
            final_worker=None,
        )

        event = OverlayEvent(
            overlay_id=f"ov_{snapshot.snapshot_id}_{next_token.overlay_version}",
            base_compile_run_id=snapshot.compile_run_id,
            base_artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=next_token.overlay_version,
            patch_type=patch.patch_type,
            affordance_id=patch.affordance_id,
            patch_id=patch.patch_id, accepted=True,
        )
        return patched, event
