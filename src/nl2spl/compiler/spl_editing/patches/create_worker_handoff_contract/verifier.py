"""CreateWorkerHandoffContract verifier."""

from nl2spl.compiler.spl_editing.intent.model import (
    ConstructRepairIntent,
    CreateWorkerHandoffContractIntentPayload,
)
from nl2spl.compiler.spl_editing.patches.base import PatchVerifier


class CreateWorkerHandoffContractVerifier(PatchVerifier):
    def verify(self, patch, base_snapshot, patched_snapshot, artifacts) -> tuple[str, ...]:
        failures: list[str] = []
        payload = patch.payload
        expected_handoff_id = ""
        if isinstance(payload, ConstructRepairIntent) and isinstance(
            payload.payload,
            CreateWorkerHandoffContractIntentPayload,
        ):
            hp = payload.payload
            parent_worker_id = hp.parent_worker_id
            child_worker_id = hp.child_worker_id
            exp_in = hp.input_binding_status
            exp_out = hp.output_binding_status
            exp_in_src = "user_confirmed_repair"
            exp_out_src = "user_confirmed_repair"
        else:
            promotion_id = str(payload.get("worker_promotion_id", ""))
            expected_handoff_id = f"handoff_repair_{promotion_id}"
            parent_worker_id = str(payload.get("parent_worker_id", ""))
            child_worker_id = str(payload.get("child_worker_id", ""))
            exp_in = str(payload.get("input_binding_status", "known_present"))
            exp_out = str(payload.get("output_binding_status", "known_present"))
            exp_in_src = payload.get("input_binding_status_source") or "user_confirmed_repair"
            exp_out_src = payload.get("output_binding_status_source") or "user_confirmed_repair"

        patched_plan = patched_snapshot.worker_plan
        if patched_plan is None:
            failures.append("patched snapshot has no worker_plan")
            return tuple(failures)

        handoffs = getattr(patched_plan, "handoffs", [])
        found = None
        for handoff in handoffs:
            if expected_handoff_id:
                if getattr(handoff, "handoff_id", None) == expected_handoff_id:
                    found = handoff
                    break
            elif (
                getattr(handoff, "from_worker", "") == parent_worker_id
                and getattr(handoff, "to_worker", "") == child_worker_id
            ):
                found = handoff
                break

        if found is None:
            failures.append("Expected worker handoff not found in patched worker plan")
        else:
            if getattr(found, "from_worker", "") != parent_worker_id:
                failures.append("handoff from_worker mismatch")
            if getattr(found, "to_worker", "") != child_worker_id:
                failures.append("handoff to_worker mismatch")

            found_in = getattr(found, "input_binding_status", "unknown")
            found_out = getattr(found, "output_binding_status", "unknown")
            found_in_src = getattr(found, "input_binding_status_source", None)
            found_out_src = getattr(found, "output_binding_status_source", None)
            found_in_b = getattr(found, "input_bindings", [])
            found_out_b = getattr(found, "output_bindings", [])
            found_mat = getattr(found, "materialization_status", "unknown")

            if found_in != exp_in:
                failures.append(
                    f"input_binding_status mismatch: expected '{exp_in}', got '{found_in}'"
                )
            if found_out != exp_out:
                failures.append(
                    f"output_binding_status mismatch: expected '{exp_out}', got '{found_out}'"
                )
            if found_in_src != exp_in_src:
                failures.append(
                    f"input_binding_status_source mismatch: expected '{exp_in_src}', got '{found_in_src}'"  # noqa: E501
                )
            if found_out_src != exp_out_src:
                failures.append(
                    f"output_binding_status_source mismatch: expected '{exp_out_src}', got '{found_out_src}'"  # noqa: E501
                )
            if found_in == "known_present" and not found_in_b:
                failures.append("input_binding_status='known_present' but input_bindings is empty")
            if found_out == "known_present" and not found_out_b:
                failures.append(
                    "output_binding_status='known_present' but output_bindings is empty"
                )
            if found_in == "known_empty" and found_in_b:
                failures.append(
                    "input_binding_status='known_empty' but input_bindings is non-empty"
                )
            if found_out == "known_empty" and found_out_b:
                failures.append(
                    "output_binding_status='known_empty' but output_bindings is non-empty"
                )

            from nl2spl.ir.worker_contract_status import derive_handoff_materialization_status

            expected_mat = derive_handoff_materialization_status(
                input_bindings=found_in_b,
                output_bindings=found_out_b,
                input_status=found_in,
                output_status=found_out,
            )
            if found_mat != expected_mat:
                failures.append(
                    f"materialization_status mismatch: expected '{expected_mat}', got '{found_mat}'"
                )

        gated = getattr(artifacts, "gated_worker", None)
        if gated is None:
            failures.append("gated_worker missing from verification artifacts")

        return tuple(failures)
