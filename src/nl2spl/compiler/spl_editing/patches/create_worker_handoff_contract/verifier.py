"""CreateWorkerHandoffContract verifier."""

from nl2spl.compiler.spl_editing.patches.base import PatchVerifier


class CreateWorkerHandoffContractVerifier(PatchVerifier):
    def verify(self, patch, base_snapshot, patched_snapshot, artifacts) -> tuple[str, ...]:
        failures: list[str] = []
        p = patch.payload
        promotion_id = str(p.get("worker_promotion_id", ""))
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
            if getattr(found, "from_worker", "") != str(p.get("parent_worker_id", "")):
                failures.append("handoff from_worker mismatch")
            if getattr(found, "to_worker", "") != str(p.get("child_worker_id", "")):
                failures.append("handoff to_worker mismatch")

            # Status consistency
            exp_in = str(p.get("input_binding_status", "known_present"))
            exp_out = str(p.get("output_binding_status", "known_present"))
            exp_in_src = p.get("input_binding_status_source") or "user_confirmed_repair"
            exp_out_src = p.get("output_binding_status_source") or "user_confirmed_repair"
            found_in = getattr(found, "input_binding_status", "unknown")
            found_out = getattr(found, "output_binding_status", "unknown")
            found_in_src = getattr(found, "input_binding_status_source", None)
            found_out_src = getattr(found, "output_binding_status_source", None)
            found_in_b = getattr(found, "input_bindings", [])
            found_out_b = getattr(found, "output_bindings", [])
            found_mat = getattr(found, "materialization_status", "unknown")

            if found_in != exp_in:
                failures.append(
                    f"input_binding_status mismatch: expected '{exp_in}', "
                    f"got '{found_in}'")
            if found_out != exp_out:
                failures.append(
                    f"output_binding_status mismatch: expected '{exp_out}', "
                    f"got '{found_out}'")

            if found_in_src != exp_in_src:
                failures.append(
                    f"input_binding_status_source mismatch: "
                    f"expected '{exp_in_src}', got '{found_in_src}'")
            if found_out_src != exp_out_src:
                failures.append(
                    f"output_binding_status_source mismatch: "
                    f"expected '{exp_out_src}', got '{found_out_src}'")

            if found_in == "known_present" and not found_in_b:
                failures.append(
                    "input_binding_status='known_present' but input_bindings is empty")
            if found_out == "known_present" and not found_out_b:
                failures.append(
                    "output_binding_status='known_present' but output_bindings is empty")

            if found_in == "known_empty" and found_in_b:
                failures.append(
                    "input_binding_status='known_empty' but input_bindings is non-empty")
            if found_out == "known_empty" and found_out_b:
                failures.append(
                    "output_binding_status='known_empty' but output_bindings is non-empty")

            # materialization_status must equal derived expectation
            from nl2spl.ir.worker_contract_status import (
                derive_handoff_materialization_status,
            )
            expected_mat = derive_handoff_materialization_status(
                input_bindings=found_in_b,
                output_bindings=found_out_b,
                input_status=found_in,
                output_status=found_out,
            )
            if found_mat != expected_mat:
                failures.append(
                    f"materialization_status mismatch: expected "
                    f"'{expected_mat}', got '{found_mat}'")

        # Check gated worker exists (Lane B should produce it)
        gated = getattr(artifacts, "gated_worker", None)
        if gated is None:
            failures.append("gated_worker missing from verification artifacts")

        return tuple(failures)
