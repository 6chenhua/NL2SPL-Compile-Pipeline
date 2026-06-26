"""InsertProducerStep verifier for materialized ConstructRepairIntent payloads."""

from __future__ import annotations

from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent
from nl2spl.compiler.spl_editing.patches.base import PatchVerifier


class InsertProducerStepVerifier(PatchVerifier):
    def verify(self, patch, base_snapshot, patched_snapshot, artifacts) -> tuple[str, ...]:
        payload = patch.payload
        if not isinstance(payload, ConstructRepairIntent):
            return (
                "InsertProducerStep verifier requires ConstructRepairIntent payload; "
                f"got {type(payload).__name__}.",
            )

        output_name = _output_name_from_target_ref(patch.target_ref)
        failures: list[str] = []

        gated = getattr(artifacts, "gated_worker", None)
        if gated is None:
            failures.append("gated_worker missing")
            return tuple(failures)

        gated_steps = list(getattr(gated, "steps", []))
        index = ProducerIndex(steps=gated_steps)
        if not index.is_produced(output_name):
            failures.append(f"ProducerIndex does not recognize '{output_name}' as produced")

        spl = getattr(artifacts, "rendered_spl", "")
        if output_name and output_name not in spl:
            failures.append(f"Output '{output_name}' not found in rendered SPL")

        return tuple(failures)


def _output_name_from_target_ref(target_ref: str) -> str:
    """Extract output name from target_ref like worker:{id}.output:{name}."""
    marker = ".output:"
    idx = target_ref.find(marker)
    if idx > 0:
        return target_ref[idx + len(marker) :]
    return ""
