"""ConvertDelegationIntentToRequestInput validator."""

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.base import PatchValidator

_PROMOTION_SLOTS = {
    "promotion_input_contract", "promotion_output_contract",
    "promotion_invocation_point", "promotion_result_handoff",
}


class ConvertDelegationToRequestInputValidator(PatchValidator):
    def validate(self, patch: RepairPatch, snapshot: ArtifactSnapshot) -> None:
        payload = patch.payload
        if not isinstance(payload, dict):
            raise PatchValidationError("payload must be a dict")

        wid = payload.get("worker_id")
        if not isinstance(wid, str) or not wid:
            raise PatchValidationError("payload.worker_id required")
        prompt = payload.get("prompt_text")
        if not isinstance(prompt, str) or not prompt.strip():
            raise PatchValidationError("payload.prompt_text required")
        target = payload.get("value_target")
        if not isinstance(target, str) or not target.strip():
            raise PatchValidationError("payload.value_target required")

        # MVP: only main_flow
        insertion = payload.get("insertion_target", "main_flow")
        if insertion != "main_flow":
            raise PatchValidationError(f"insertion_target '{insertion}' not supported")
        block_ref = payload.get("block_ref")
        if block_ref is not None:
            if not isinstance(block_ref, str):
                raise PatchValidationError("block_ref must be a string or None")
            if block_ref:
                raise PatchValidationError("block_ref not supported in MVP")

        # outputs schema
        for field in ("outputs",):
            val = payload.get(field)
            if val is not None:
                if not isinstance(val, (list, tuple)):
                    raise PatchValidationError(f"payload.{field} must be a list")
                for item in val:
                    if not isinstance(item, str) or not item.strip():
                        raise PatchValidationError(
                            f"payload.{field} items must be non-empty strings")

        if patch.patch_type != "ConvertDelegationIntentToRequestInput":
            raise PatchValidationError("Wrong patch_type")
        if patch.affordance_id != "worker_promotion.resolve_contract":
            raise PatchValidationError("Wrong affordance")
        if not patch.evidence.related_diagnostic_id:
            raise PatchValidationError("related_diagnostic_id required")

        # IRS boundary
        if patch.irs_ref.construct_type != "WORKER_PROMOTION":
            raise PatchValidationError(
                f"construct_type must be WORKER_PROMOTION, "
                f"got '{patch.irs_ref.construct_type}'")
        if patch.irs_ref.slot_name not in _PROMOTION_SLOTS:
            raise PatchValidationError(
                f"slot_name must be a WORKER_PROMOTION slot, "
                f"got '{patch.irs_ref.slot_name}'")

        # construct_id must identify a WORKER_PROMOTION candidate
        cid = patch.irs_ref.construct_id
        if not cid or not cid.startswith("worker_promotion:"):
            raise PatchValidationError(
                f"irs_ref.construct_id must be 'worker_promotion:{{id}}', "
                f"got '{cid}'")
        if patch.target_ref != cid:
            raise PatchValidationError(
                f"target_ref '{patch.target_ref}' does not match "
                f"construct_id '{cid}'")

        # Stale revision
        if patch.base_compile_run_id != snapshot.compile_run_id:
            raise PatchValidationError("compile_run_id mismatch")
        if patch.artifact_snapshot_id != snapshot.snapshot_id:
            raise PatchValidationError("snapshot_id mismatch")
        if patch.overlay_version != snapshot.overlay_version:
            raise PatchValidationError("overlay_version mismatch")

        sp = snapshot.worker_step_plan
        if sp is None:
            raise PatchValidationError("worker_step_plan required")
        if wid not in sp.worker_steps:
            raise PatchValidationError(f"Worker '{wid}' not found")

        gen_id = f"st_repair_{snapshot.overlay_version + 1}_{wid}"
        for s in sp.worker_steps[wid]:
            if s.step_id == gen_id:
                raise PatchValidationError(f"Step id '{gen_id}' already in use")
