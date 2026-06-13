"""CreateWorkerHandoffContract verifier."""

from nl2spl.compiler.spl_editing.core.model import RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.base import PatchVerifier


class CreateWorkerHandoffContractVerifier(PatchVerifier):
    def verify(self, patch, base_snapshot, patched_snapshot, artifacts) -> tuple[str, ...]:
        failures: list[str] = []
        promotion_id = str(patch.payload.get("worker_promotion_id", ""))
        expected_handoff_id = f"handoff_repair_{promotion_id}"

        # Check handoff exists in patched worker plan
        patched_plan = patched_snapshot.worker_plan
        if patched_plan is None:
            failures.append("patched snapshot has no worker_plan")
            return tuple(failures)

        handoffs = getattr(patched_plan, "handoffs", [])
        found = None
        for h in handoffs:
            if getattr(h, "handoff_id", None) == expected_handoff_id:
                found = h
                break
        if found is None:
            failures.append(
                f"Handoff '{expected_handoff_id}' not found in patched worker plan")
        else:
            if getattr(found, "from_worker", "") != str(patch.payload.get("parent_worker_id", "")):
                failures.append("handoff from_worker mismatch")
            if getattr(found, "to_worker", "") != str(patch.payload.get("child_worker_id", "")):
                failures.append("handoff to_worker mismatch")

        # Check gated worker exists (Lane B should produce it)
        gated = getattr(artifacts, "gated_worker", None)
        if gated is None:
            failures.append("gated_worker missing from verification artifacts")

        return tuple(failures)
