"""BindExistingProducerStep verifier."""

from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.base import PatchVerifier
from nl2spl.compiler.producer_index import ProducerIndex


class BindExistingProducerStepVerifier(PatchVerifier):
    def verify(self, patch, base_snapshot, patched_snapshot, artifacts) -> tuple[str, ...]:
        payload = patch.payload
        output_name = str(payload.get("output_name", ""))
        step_id = str(payload.get("step_id", ""))
        failures: list[str] = []

        gated = getattr(artifacts, "gated_worker", None)
        if gated is None:
            failures.append("gated_worker missing")
            return tuple(failures)

        gated_steps = list(getattr(gated, "steps", []))
        index = ProducerIndex(steps=gated_steps)
        if not index.is_produced(output_name):
            failures.append(
                f"ProducerIndex does not recognize '{output_name}' as produced")

        bound = next((s for s in gated_steps if s.step_id == step_id), None)
        if bound is None:
            failures.append(f"Bound step '{step_id}' not found in gated worker")
        else:
            # Verify binding provenance exists
            bindings = bound.metadata.get("repair_output_bindings", {})
            entry = bindings.get(output_name, {})
            if not entry:
                failures.append(
                    f"Step '{step_id}' has no repair_output_bindings for "
                    f"'{output_name}'")
            else:
                if entry.get("repair_patch_id") != patch.patch_id:
                    failures.append(
                        f"repair_patch_id mismatch: "
                        f"'{entry.get('repair_patch_id')}' != '{patch.patch_id}'")
                if entry.get("related_diagnostic_id") != patch.evidence.related_diagnostic_id:
                    failures.append(
                        f"related_diagnostic_id mismatch: "
                        f"'{entry.get('related_diagnostic_id')}' "
                        f"!= '{patch.evidence.related_diagnostic_id}'")

        return tuple(failures)


