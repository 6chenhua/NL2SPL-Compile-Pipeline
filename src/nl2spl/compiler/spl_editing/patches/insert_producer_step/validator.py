"""InsertProducerStep preconditions validator."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.base import PatchValidator


class InsertProducerStepValidator(PatchValidator):
    def validate(self, patch: RepairPatch, snapshot: ArtifactSnapshot) -> None:
        payload = patch.payload
        if not isinstance(payload, dict):
            raise PatchValidationError("payload must be a dict")

        worker_id = payload.get("worker_id")
        if not isinstance(worker_id, str) or not worker_id:
            raise PatchValidationError("payload.worker_id is required")

        output_name = payload.get("output_name")
        if not isinstance(output_name, str) or not output_name.strip():
            raise PatchValidationError("payload.output_name is required")

        producer_text = payload.get("producer_text")
        if not isinstance(producer_text, str) or not producer_text.strip():
            raise PatchValidationError("payload.producer_text is required")

        command_type = payload.get("command_type", "GENERAL_COMMAND")
        if command_type not in ("GENERAL_COMMAND", "REQUEST_INPUT"):
            raise PatchValidationError(
                f"command_type must be GENERAL_COMMAND or REQUEST_INPUT, "
                f"got {command_type!r}")

        # REQUEST_INPUT must have output_name in outputs
        if command_type == "REQUEST_INPUT":
            outputs = payload.get("outputs", [])
            if output_name not in list(outputs):
                raise PatchValidationError(
                    "REQUEST_INPUT producer must include output_name in outputs")

        # Stale revision
        if patch.base_compile_run_id != snapshot.compile_run_id:
            raise PatchValidationError("compile_run_id mismatch")
        if patch.artifact_snapshot_id != snapshot.snapshot_id:
            raise PatchValidationError("snapshot_id mismatch")
        if patch.overlay_version != snapshot.overlay_version:
            raise PatchValidationError("overlay_version mismatch")

        if patch.patch_type != "InsertProducerStep":
            raise PatchValidationError(
                f"Patch type '{patch.patch_type}' != 'InsertProducerStep'")
        if patch.affordance_id != "required_output.insert_or_bind_producer":
            raise PatchValidationError(
                f"Wrong affordance '{patch.affordance_id}'")
        if not patch.evidence.related_diagnostic_id:
            raise PatchValidationError("related_diagnostic_id required")

        # target_ref and irs_ref must match
        expected_ref = f"worker:{worker_id}.output:{output_name}"
        if patch.target_ref != expected_ref:
            raise PatchValidationError(
                f"target_ref '{patch.target_ref}' != '{expected_ref}'")
        if patch.irs_ref.construct_type != "REQUIRED_OUTPUT":
            raise PatchValidationError(
                f"irs_ref.construct_type must be REQUIRED_OUTPUT, "
                f"got '{patch.irs_ref.construct_type}'")
        if patch.irs_ref.slot_name != "producer":
            raise PatchValidationError(
                f"irs_ref.slot_name must be producer, "
                f"got '{patch.irs_ref.slot_name}'")

        # MVP: only main_flow insertion is supported
        insertion = payload.get("insertion_target", "main_flow")
        if insertion != "main_flow":
            raise PatchValidationError(
                f"insertion_target '{insertion}' not supported in MVP; "
                f"only 'main_flow' is allowed")
        block_ref = payload.get("block_ref")
        if block_ref is not None:
            if not isinstance(block_ref, str):
                raise PatchValidationError(
                    f"payload.block_ref must be a string or None, "
                    f"got {type(block_ref).__name__}")
            if block_ref:
                raise PatchValidationError(
                    "block_ref not supported in MVP; only main_flow insertion")

        # inputs/outputs items must be non-empty strings
        for field in ("inputs", "outputs"):
            val = payload.get(field)
            if val is not None:
                if not isinstance(val, (list, tuple)):
                    raise PatchValidationError(
                        f"payload.{field} must be a list")
                for item in val:
                    if not isinstance(item, str) or not item.strip():
                        raise PatchValidationError(
                            f"payload.{field} items must be non-empty strings")

        # Snapshot requires step plan with worker_id present
        step_plan = snapshot.worker_step_plan
        if step_plan is None:
            raise PatchValidationError("worker_step_plan required")
        if worker_id not in step_plan.worker_steps:
            raise PatchValidationError(
                f"Worker '{worker_id}' not found in worker_step_plan")

        # Check exact generated step_id uniqueness
        gen_id = f"st_repair_{snapshot.overlay_version + 1}_{worker_id}"
        for steps in step_plan.worker_steps.values():
            for s in steps:
                if s.step_id == gen_id:
                    raise PatchValidationError(f"Step id '{gen_id}' already in use")
