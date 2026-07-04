"""ConvertDelegationToMainFlowStep verifier."""

from nl2spl.compiler.spl_editing.patches.base import PatchVerifier
from nl2spl.compiler.spl_editing.resolution import validate_promotion_resolution_marker


class ConvertDelegationToMainFlowStepVerifier(PatchVerifier):
    def verify(self, patch, base_snapshot, patched_snapshot, artifacts) -> tuple[str, ...]:
        failures: list[str] = []
        directive = getattr(getattr(patch, "payload", None), "payload", None)
        if getattr(directive, "option_id", None) == "keep_in_main_flow":
            markers = [
                marker
                for marker in patched_snapshot.promotion_resolution_markers
                if marker.normalized_directive_id == directive.directive_id
            ]
            if len(markers) != 1 or markers[0].resolution_kind != "kept_in_main_flow":
                return ("Missing kept_in_main_flow resolution marker",)
            marker_validity = validate_promotion_resolution_marker(
                markers[0],
                patch.target_ref,
                expected_repair_patch_id=patch.patch_id,
            )
            if not marker_validity.valid:
                return (
                    "Invalid kept_in_main_flow resolution marker: "
                    + ",".join(marker_validity.reasons),
                )
            matching = [
                step
                for step in patched_snapshot.worker_step_plan.main_worker_steps
                if step.metadata.get("normalized_directive_id") == directive.directive_id
            ]
            if len(matching) != 1:
                return ("Keep-main closure requires exactly one matching command",)
            step = matching[0]
            if (
                step.command_type != "GENERAL_COMMAND"
                or step.text != directive.delegated_responsibility
                or step.metadata.get("origin") != "user_confirmed_repair"
            ):
                failures.append("Keep-main command does not match normalized responsibility")
            base_children = {
                worker.worker_id
                for worker in base_snapshot.worker_plan.workers
                if worker.kind == "child"
            }
            after_children = {
                worker.worker_id
                for worker in patched_snapshot.worker_plan.workers
                if worker.kind == "child"
            }
            if not after_children.issubset(base_children):
                failures.append("Keep-main closure introduced a child worker")
            base_handoffs = {item.handoff_id for item in base_snapshot.worker_plan.handoffs}
            after_handoffs = {item.handoff_id for item in patched_snapshot.worker_plan.handoffs}
            if not after_handoffs.issubset(base_handoffs):
                failures.append("Keep-main closure introduced a handoff")
            base_special_steps = {
                item.step_id
                for values in base_snapshot.worker_step_plan.worker_steps.values()
                for item in values
                if item.command_type in {"INVOKE_WORKER", "REQUEST_INPUT"}
            }
            new_special_steps = [
                item
                for values in patched_snapshot.worker_step_plan.worker_steps.values()
                for item in values
                if item.step_id not in base_special_steps
                and item.step_id != step.step_id
                and item.command_type in {"INVOKE_WORKER", "REQUEST_INPUT"}
            ]
            if new_special_steps:
                failures.append("Keep-main closure introduced invoke/request-input behavior")
            command_ref = f"step:{patched_snapshot.worker_plan.main_worker_id}:{step.step_id}"
            marker_refs = markers[0].materialized_construct_refs
            if len(marker_refs) != len(set(marker_refs)):
                failures.append("Keep-main marker contains duplicate construct refs")
            if marker_refs != (command_ref,):
                failures.append("Keep-main marker refs must exactly match its command")
            rendered = artifacts.rendered_spl or ""
            if directive.delegated_responsibility.casefold() not in rendered.casefold():
                failures.append("Rendered SPL does not contain the main-flow command")
            return tuple(failures)
        gated = getattr(artifacts, "gated_worker", None)
        if gated is None:
            return ("gated_worker missing",)

        # Find the conversion step
        conv_step = next(
            (
                s
                for s in getattr(gated, "steps", [])
                if s.metadata.get("resolution_kind") == "converted_to_main_flow_step"
                and s.metadata.get("repair_patch_id") == patch.patch_id
            ),
            None,
        )
        if conv_step is None:
            failures.append("Converted main-flow step not found in gated worker")
        elif (
            conv_step.command_type != "GENERAL_COMMAND"
            or conv_step.metadata.get("origin") != "user_confirmed_repair"
            or conv_step.metadata.get("related_diagnostic_id")
            != patch.evidence.related_diagnostic_id
        ):
            failures.append(
                f"Conversion step has wrong command_type/origin/diagnostic_id: "
                f"cmd={conv_step.command_type}, "
                f"origin={conv_step.metadata.get('origin')}, "
                f"diag={conv_step.metadata.get('related_diagnostic_id')}"
            )
        return tuple(failures)
