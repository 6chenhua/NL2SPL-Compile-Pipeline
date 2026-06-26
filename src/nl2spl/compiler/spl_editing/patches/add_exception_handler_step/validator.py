"""AddExceptionHandlerStep preconditions validator."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.base import PatchValidator

_VALID_COMMAND_TYPES = frozenset({"GENERAL_COMMAND", "REQUEST_INPUT", "DISPLAY_MESSAGE"})


class AddExceptionHandlerStepValidator(PatchValidator):
    """Validate preconditions for AddExceptionHandlerStep."""

    def validate(
        self,
        patch: RepairPatch,
        snapshot: ArtifactSnapshot,
    ) -> None:
        payload = patch.payload
        if not isinstance(payload, dict):
            raise PatchValidationError("payload must be a dict")

        # --- payload fields ---
        worker_id = payload.get("worker_id")
        if not isinstance(worker_id, str) or not worker_id:
            raise PatchValidationError("payload.worker_id is required")

        flow_id = payload.get("exception_flow_id")
        if not isinstance(flow_id, str) or not flow_id:
            raise PatchValidationError("payload.exception_flow_id is required")

        handler_text = payload.get("handler_text")
        if not isinstance(handler_text, str) or not handler_text.strip():
            raise PatchValidationError("payload.handler_text is required")

        command_type = payload.get("command_type", "GENERAL_COMMAND")
        if command_type not in _VALID_COMMAND_TYPES:
            raise PatchValidationError(
                f"payload.command_type must be one of "
                f"{sorted(_VALID_COMMAND_TYPES)}, got {command_type!r}"
            )

        # REQUEST_INPUT must have at least one output
        if command_type == "REQUEST_INPUT":
            outputs = payload.get("outputs", [])
            if not outputs:
                raise PatchValidationError("REQUEST_INPUT handler must have at least one output")

        # DISPLAY_MESSAGE must not have outputs
        if command_type == "DISPLAY_MESSAGE":
            outputs = payload.get("outputs", [])
            if outputs:
                raise PatchValidationError("DISPLAY_MESSAGE handler must not have outputs")

        # inputs/outputs must be lists of non-empty strings
        for field in ("inputs", "outputs"):
            val = payload.get(field)
            if val is not None:
                if not isinstance(val, (list, tuple)):
                    raise PatchValidationError(f"payload.{field} must be a list")
                for item in val:
                    if not isinstance(item, str) or not item.strip():
                        raise PatchValidationError(
                            f"payload.{field} items must be non-empty strings"
                        )

        # --- stale revision check ---
        if patch.base_compile_run_id != snapshot.compile_run_id:
            raise PatchValidationError(
                f"compile_run_id mismatch: patch "
                f"'{patch.base_compile_run_id}' vs snapshot "
                f"'{snapshot.compile_run_id}'"
            )
        if patch.artifact_snapshot_id != snapshot.snapshot_id:
            raise PatchValidationError(
                f"snapshot_id mismatch: patch "
                f"'{patch.artifact_snapshot_id}' vs snapshot "
                f"'{snapshot.snapshot_id}'"
            )
        if patch.overlay_version != snapshot.overlay_version:
            raise PatchValidationError(
                f"overlay_version mismatch: patch "
                f"{patch.overlay_version} vs snapshot "
                f"{snapshot.overlay_version}"
            )

        # --- patch metadata ---
        if patch.patch_type != "AddExceptionHandlerStep":
            raise PatchValidationError(
                f"Patch type '{patch.patch_type}' != 'AddExceptionHandlerStep'"
            )
        if patch.affordance_id != "exception_flow.add_handler_step":
            raise PatchValidationError(
                f"Affordance '{patch.affordance_id}' != 'exception_flow.add_handler_step'"
            )
        if not patch.evidence.related_diagnostic_id:
            raise PatchValidationError("related_diagnostic_id is required in patch evidence")

        # --- snapshot preconditions ---
        step_plan = snapshot.worker_step_plan
        if step_plan is None:
            raise PatchValidationError("worker_step_plan is required in snapshot")

        # Target exception flow must exist in WorkerFlowPlanIR
        flow_plan = snapshot.worker_flow_plan
        if flow_plan is None:
            raise PatchValidationError("worker_flow_plan is required in snapshot")
        worker_flows = getattr(flow_plan, "worker_flows", {})
        fs = worker_flows.get(worker_id)
        if fs is None:
            raise PatchValidationError(f"Worker '{worker_id}' not found in worker_flow_plan")
        exc_flows = getattr(fs, "exception_flows", [])
        if not any(getattr(ef, "flow_id", None) == flow_id for ef in exc_flows):
            raise PatchValidationError(
                f"Exception flow '{flow_id}' not found in worker '{worker_id}'"
            )

        # Target ref must exactly match payload worker/flow
        expected_ref = f"worker:{worker_id}.exception_flow:{flow_id}"
        if patch.target_ref != expected_ref:
            raise PatchValidationError(
                f"target_ref '{patch.target_ref}' does not match expected '{expected_ref}'"
            )

        # irs_ref construct_type and slot_name must match
        if patch.irs_ref.construct_type != "EXCEPTION_FLOW":
            raise PatchValidationError(
                f"irs_ref.construct_type must be EXCEPTION_FLOW, "
                f"got '{patch.irs_ref.construct_type}'"
            )
        if patch.irs_ref.slot_name != "handler_action":
            raise PatchValidationError(
                f"irs_ref.slot_name must be handler_action, got '{patch.irs_ref.slot_name}'"
            )

        # Check that a handler for this flow doesn't already exist
        existing_steps = step_plan.worker_steps.get(worker_id, [])
        for step in existing_steps:
            if step.flow_ref == flow_id:
                raise PatchValidationError(
                    f"Exception flow '{flow_id}' already has a handler step ({step.step_id})"
                )

        # Check exact step_id uniqueness
        generated_step_id = f"st_repair_{snapshot.overlay_version + 1}_{worker_id}"
        for step in existing_steps:
            if step.step_id == generated_step_id:
                raise PatchValidationError(f"Step id '{generated_step_id}' already in use")
