"""CreateWorkerHandoffContract validator."""

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.base import PatchValidator


class CreateWorkerHandoffContractValidator(PatchValidator):
    def validate(self, patch: RepairPatch, snapshot: ArtifactSnapshot) -> None:
        p = patch.payload
        if not isinstance(p, dict):
            raise PatchValidationError("payload must be a dict")

        for field in ("worker_promotion_id", "parent_worker_id", "child_worker_id"):
            v = p.get(field)
            if not isinstance(v, str) or not v:
                raise PatchValidationError(f"payload.{field} required")

        if patch.patch_type != "CreateWorkerHandoffContract":
            raise PatchValidationError(f"Wrong patch_type '{patch.patch_type}'")
        if patch.affordance_id != "worker_promotion.resolve_contract":
            raise PatchValidationError("Wrong affordance")
        if patch.irs_ref.construct_type != "WORKER_PROMOTION":
            raise PatchValidationError(
                f"construct_type must be WORKER_PROMOTION, "
                f"got '{patch.irs_ref.construct_type}'")
        if not patch.evidence.related_diagnostic_id:
            raise PatchValidationError("related_diagnostic_id required")

        # Stale revision
        if patch.base_compile_run_id != snapshot.compile_run_id:
            raise PatchValidationError("compile_run_id mismatch")
        if patch.artifact_snapshot_id != snapshot.snapshot_id:
            raise PatchValidationError("snapshot_id mismatch")
        if patch.overlay_version != snapshot.overlay_version:
            raise PatchValidationError("overlay_version mismatch")

        if snapshot.worker_plan is None:
            raise PatchValidationError("worker_plan required")
        if snapshot.worker_step_plan is None:
            raise PatchValidationError("worker_step_plan required")

        # IRS boundary
        if patch.irs_ref.construct_type != "WORKER_PROMOTION":
            raise PatchValidationError(
                f"construct_type must be WORKER_PROMOTION, "
                f"got '{patch.irs_ref.construct_type}'")
        expected_ref = f"worker_promotion:{p['worker_promotion_id']}"
        if patch.target_ref != expected_ref:
            raise PatchValidationError(
                f"target_ref '{patch.target_ref}' != '{expected_ref}'")

        # Worker existence check
        plan = snapshot.worker_plan
        worker_ids = {w.worker_id for w in plan.workers}
        parent_id = p.get("parent_worker_id", "")
        child_id = p.get("child_worker_id", "")
        if parent_id not in worker_ids:
            raise PatchValidationError(
                f"parent_worker_id '{parent_id}' not in worker plan")
        if child_id not in worker_ids:
            raise PatchValidationError(
                f"child_worker_id '{child_id}' not in worker plan")

        # Binding status consistency
        valid_binding_status = frozenset({"known_present", "known_empty"})
        in_status = p.get("input_binding_status", "known_present")
        out_status = p.get("output_binding_status", "known_present")
        if in_status not in valid_binding_status:
            raise PatchValidationError(
                f"input_binding_status '{in_status}' is not a valid BindingSideStatus")
        if out_status not in valid_binding_status:
            raise PatchValidationError(
                f"output_binding_status '{out_status}' is not a valid BindingSideStatus")

        in_bindings = p.get("input_bindings", {}) or {}
        out_bindings = p.get("output_bindings", {}) or {}

        if in_status == "known_present" and not in_bindings:
            raise PatchValidationError(
                "input_binding_status='known_present' requires non-empty input_bindings")
        if out_status == "known_present" and not out_bindings:
            raise PatchValidationError(
                "output_binding_status='known_present' requires non-empty output_bindings")

        for side, status, bindings in [
            ("input", in_status, in_bindings),
            ("output", out_status, out_bindings),
        ]:
            if status == "known_empty":
                source = p.get(f"{side}_binding_status_source")
                if not isinstance(source, str) or not source.strip():
                    raise PatchValidationError(
                        f"{side}_binding_status='known_empty' requires "
                        f"non-empty {side}_binding_status_source")
                if bindings:
                    raise PatchValidationError(
                        f"{side}_binding_status='known_empty' requires "
                        f"empty {side}_bindings, got {len(bindings)} entries")
