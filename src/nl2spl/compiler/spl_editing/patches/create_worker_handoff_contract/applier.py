"""CreateWorkerHandoffContract applier — creates WorkerHandoffIR."""

from dataclasses import replace

from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import (
    ArtifactSnapshot, OverlayEvent, RevisionToken,
)
from nl2spl.compiler.spl_editing.patches.base import PatchApplier
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
        result = str(p.get("result_handoff", ""))

        handoff_id = f"handoff_repair_{promotion_id}"
        input_irs = [
            InputBindingIR(pv, ci, True)
            for pv, ci in in_bindings.items()
        ]
        output_irs = [
            OutputBindingIR(co, pv, True, "set")
            for co, pv in out_bindings.items()
        ]

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
            invoke_location_hint=InvokeLocationHintIR(
                flow_kind=inv_point if inv_point in ("main", "alternative", "exception") else "main",
                flow_id=None,
                after_span_id=None,
                before_span_id=None,
                block_hint="sequential",
            ),
        )

        # Update WorkerPlanIR
        plan = snapshot.require_worker_plan()
        new_handoffs = list(plan.handoffs) + [handoff]
        new_plan = replace(plan, handoffs=new_handoffs)

        next_token = RevisionToken(
            snapshot.compile_run_id, snapshot.snapshot_id,
            snapshot.overlay_version + 1,
        )
        patched = snapshot.derive(next_token, worker_plan=new_plan,
                                   final_spl=None, final_worker=None)

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
