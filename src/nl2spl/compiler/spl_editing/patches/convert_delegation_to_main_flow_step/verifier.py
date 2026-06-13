"""ConvertDelegationToMainFlowStep verifier."""

from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.base import PatchVerifier


class ConvertDelegationToMainFlowStepVerifier(PatchVerifier):
    def verify(self, patch, base_snapshot, patched_snapshot, artifacts) -> tuple[str, ...]:
        failures: list[str] = []
        gated = getattr(artifacts, "gated_worker", None)
        if gated is None:
            return ("gated_worker missing",)

        # Find the conversion step
        conv_step = next(
            (s for s in getattr(gated, "steps", [])
             if s.metadata.get("resolution_kind") == "converted_to_main_flow_step"
             and s.metadata.get("repair_patch_id") == patch.patch_id),
            None,
        )
        if conv_step is None:
            failures.append(
                "Converted main-flow step not found in gated worker")
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
                f"diag={conv_step.metadata.get('related_diagnostic_id')}")
        return tuple(failures)
