"""ConvertDelegationToRequestInput verifier."""

from nl2spl.compiler.spl_editing.patches.base import PatchVerifier


class ConvertDelegationToRequestInputVerifier(PatchVerifier):
    def verify(self, patch, base_snapshot, patched_snapshot, artifacts) -> tuple[str, ...]:
        failures: list[str] = []
        gated = getattr(artifacts, "gated_worker", None)
        if gated is None:
            return ("gated_worker missing",)

        conv_step = next(
            (
                s
                for s in getattr(gated, "steps", [])
                if s.metadata.get("resolution_kind") == "converted_to_request_input"
                and s.metadata.get("repair_patch_id") == patch.patch_id
            ),
            None,
        )
        if conv_step is None:
            failures.append("Converted REQUEST_INPUT step not found in gated worker")
        elif (
            conv_step.command_type != "REQUEST_INPUT"
            or conv_step.metadata.get("origin") != "user_confirmed_repair"
            or conv_step.metadata.get("related_diagnostic_id")
            != patch.evidence.related_diagnostic_id
        ):
            failures.append(
                f"Conversion step wrong command_type/origin/diag: "
                f"cmd={conv_step.command_type}, "
                f"origin={conv_step.metadata.get('origin')}, "
                f"diag={conv_step.metadata.get('related_diagnostic_id')}"
            )
        else:
            target = conv_step.metadata.get("value_target", "")
            if not target:
                failures.append("REQUEST_INPUT step has no value_target")
            if target not in getattr(conv_step, "outputs", []):
                failures.append(f"value_target '{target}' not in step outputs")

        return tuple(failures)
