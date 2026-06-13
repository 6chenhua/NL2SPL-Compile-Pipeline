"""InsertProducerStep verifier."""

from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.base import PatchVerifier
from nl2spl.compiler.producer_index import ProducerIndex


class InsertProducerStepVerifier(PatchVerifier):
    def verify(self, patch, base_snapshot, patched_snapshot, artifacts) -> tuple[str, ...]:
        payload = patch.payload
        output_name = str(payload.get("output_name", ""))
        failures: list[str] = []

        gated = getattr(artifacts, "gated_worker", None)
        if gated is None:
            failures.append("gated_worker missing")
            return tuple(failures)

        # Build ProducerIndex from gated worker steps
        gated_steps = list(getattr(gated, "steps", []))
        index = ProducerIndex(steps=gated_steps)
        if not index.is_produced(output_name):
            failures.append(
                f"ProducerIndex does not recognize '{output_name}' as produced")

        spl = getattr(artifacts, "rendered_spl", "")
        if output_name and output_name not in spl:
            failures.append(f"Output '{output_name}' not found in rendered SPL")

        return tuple(failures)

