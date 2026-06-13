"""ConvertDelegationToRequestInput applier."""

from dataclasses import replace
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot, OverlayEvent, RevisionToken
from nl2spl.compiler.spl_editing.patches.base import PatchApplier
from nl2spl.ir.step_ir import StepIR


class ConvertDelegationToRequestInputApplier(PatchApplier):
    def apply(self, patch: RepairPatch, snapshot: ArtifactSnapshot) -> tuple[
        ArtifactSnapshot, OverlayEvent,
    ]:
        payload = patch.payload
        wid = str(payload.get("worker_id", ""))
        prompt = str(payload.get("prompt_text", ""))
        target = str(payload.get("value_target", ""))
        outputs = list(payload.get("outputs", [target]))
        if target not in outputs:
            outputs.append(target)

        step_id = f"st_repair_{snapshot.overlay_version + 1}_{wid}"
        new_step = StepIR(
            step_id=step_id, text=prompt, source_span_ids=[],
            command_type="REQUEST_INPUT", outputs=outputs,
            flow_ref="main",
            metadata={
                "origin": "user_confirmed_repair",
                "repair_patch_id": patch.patch_id,
                "related_diagnostic_id": patch.evidence.related_diagnostic_id,
                "resolution_kind": "converted_to_request_input",
                "value_target": target,
            },
        )

        sp = snapshot.require_worker_step_plan()
        from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
        if wid not in sp.worker_steps:
            raise PatchValidationError(f"Worker '{wid}' not found")
        worker_steps = {w: list(s) for w, s in sp.worker_steps.items()}
        worker_steps[wid].append(new_step)
        new_sp = replace(sp, worker_steps=worker_steps)

        next_token = RevisionToken(snapshot.compile_run_id, snapshot.snapshot_id,
                                    snapshot.overlay_version + 1)
        patched = snapshot.derive(next_token, worker_step_plan=new_sp,
                                   final_spl=None, final_worker=None)

        event = OverlayEvent(
            overlay_id=f"ov_{snapshot.snapshot_id}_{next_token.overlay_version}",
            base_compile_run_id=snapshot.compile_run_id,
            base_artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=next_token.overlay_version,
            patch_type=patch.patch_type, affordance_id=patch.affordance_id,
            patch_id=patch.patch_id, accepted=True,
        )
        return patched, event
