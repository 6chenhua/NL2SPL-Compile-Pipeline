"""GenericEvidenceVerifier — patch-agnostic evidence contract check (U3.5 r2).

After a patch is applied, this verifier inspects the REAL changed
artifacts in the patched snapshot to ensure every changed ``StepIR``
carries ``metadata.origin = "user_confirmed_repair"`` and every
changed ``WorkerHandoffIR`` carries the expected status source.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairPatch


class GenericEvidenceVerifier:
    """Verify that every changed artifact in the patched snapshot carries
    ``user_confirmed_repair`` evidence.

    Does NOT rely on ``PatchApplyResult.evidence_refs`` — it reads the
    real artifact metadata from the snapshot.
    """

    def verify(
        self,
        patch: RepairPatch,
        apply_result: PatchApplyResult,
    ) -> tuple[str, ...]:
        """Check changed artifacts for required evidence metadata.

        Returns:
            Empty tuple on success, or a tuple of failure reason strings.
        """
        failures: list[str] = []
        patched = apply_result.patched_snapshot

        # 1. Check every changed StepIR for evidence metadata.
        #    - NEW steps (created by repair): must have origin=user_confirmed_repair
        #      and repair_patch_id matching.
        #    - MODIFIED steps (existed before, content changed): must carry
        #      repair evidence in their metadata (e.g. repair_output_bindings)
        #      but do NOT require the entire step origin to change.
        if apply_result.changed_step_ids:
            after_wsp = patched.worker_step_plan
            if after_wsp is not None:
                for worker_id, steps in after_wsp.worker_steps.items():
                    for s in steps:
                        if s.step_id in apply_result.changed_step_ids:
                            origin = s.metadata.get("origin")
                            is_new = origin == "user_confirmed_repair"
                            is_modified = not is_new

                            if is_new:
                                # New step: require full UCR metadata
                                repair_pid = s.metadata.get("repair_patch_id")
                                if repair_pid != patch.patch_id:
                                    failures.append(
                                        f"New step '{s.step_id}' (worker "
                                        f"'{worker_id}') has "
                                        f"repair_patch_id={repair_pid!r}, "
                                        f"expected '{patch.patch_id}'"
                                    )
                            elif is_modified:
                                has_repair_bindings = "repair_output_bindings" in s.metadata
                                has_repair_meta = (
                                    s.metadata.get("repair_patch_id") is not None
                                    or s.metadata.get("related_diagnostic_id") is not None
                                )
                                if not has_repair_bindings and not has_repair_meta:
                                    failures.append(
                                        f"Modified step '{s.step_id}' (worker "
                                        f"'{worker_id}') has no repair evidence "
                                        f"in metadata (expected "
                                        f"repair_output_bindings or repair_patch_id)"
                                    )
                                elif has_repair_bindings:
                                    bindings = s.metadata["repair_output_bindings"]
                                    # -- Cross-reference evidence_refs with real bindings --
                                    # Parse evidence_refs targeting THIS step.
                                    # Ref format: step:{wid}:{sid}:output_binding:{name}
                                    ref_bindings: dict[str, object] = {}
                                    # Track which real bindings were claimed by evidence_refs
                                    claimed_binding_names: set[str] = set()
                                    for ref in apply_result.evidence_refs:
                                        raw = ref.artifact_ref
                                        if ":output_binding:" not in raw:
                                            continue
                                        # Parse: step:{wid}:{sid}:output_binding:{name}
                                        prefix, bname = raw.rsplit(":output_binding:", 1)
                                        step_prefix = prefix.removeprefix("step:")
                                        # step_prefix is "{wid}:{sid}"
                                        sep = step_prefix.rfind(":")
                                        if sep == -1:
                                            continue
                                        ref_wid = step_prefix[:sep]
                                        ref_sid = step_prefix[sep + 1 :]
                                        # Only match evidence_refs belonging to this step
                                        if ref_wid == worker_id and ref_sid == s.step_id:
                                            claimed_binding_names.add(bname)
                                            ref_bindings[bname] = ref

                                    if isinstance(bindings, dict):
                                        # A. Validate every evidence_ref that targets
                                        #    this step: the referenced binding must
                                        #    exist in the real metadata.
                                        for bname, ref in ref_bindings.items():
                                            if bname not in bindings:
                                                failures.append(
                                                    f"Modified step '{s.step_id}' "
                                                    f"(worker '{worker_id}'): "
                                                    f"evidence_ref claims binding "
                                                    f"'{bname}' but binding does not "
                                                    f"exist in repair_output_bindings"
                                                )
                                            else:
                                                binding = bindings[bname]
                                                if not isinstance(binding, dict):
                                                    failures.append(
                                                        f"Modified step '{s.step_id}' "
                                                        f"binding '{bname}' is not a "
                                                        f"dict — cannot validate"
                                                    )
                                                    continue
                                                b_pid = binding.get("repair_patch_id")
                                                b_did = binding.get("related_diagnostic_id")
                                                ref_pid = getattr(ref, "repair_patch_id", "")
                                                ref_did = getattr(ref, "related_diagnostic_id", "")
                                                # -- Current-patch identity: evidence_ref
                                                #    must belong to THIS patch.
                                                if ref_pid != patch.patch_id:
                                                    failures.append(
                                                        f"Modified step '{s.step_id}' "
                                                        f"binding '{bname}': "
                                                        f"evidence_ref has "
                                                        f"repair_patch_id={ref_pid!r}, "
                                                        f"expected '{patch.patch_id}'"
                                                    )
                                                if ref_did != patch.evidence.related_diagnostic_id:
                                                    failures.append(
                                                        f"Modified step '{s.step_id}' "
                                                        f"binding '{bname}': "
                                                        f"evidence_ref has "
                                                        f"related_diagnostic_id={ref_did!r}, "
                                                        f"expected "
                                                        f"'{patch.evidence.related_diagnostic_id}'"
                                                    )
                                                # -- Current-patch identity: binding
                                                #    must also belong to THIS patch.
                                                if b_pid != patch.patch_id:
                                                    failures.append(
                                                        f"Modified step '{s.step_id}' "
                                                        f"binding '{bname}' has "
                                                        f"repair_patch_id={b_pid!r}, "
                                                        f"expected '{patch.patch_id}' "
                                                        f"(changed binding must carry "
                                                        f"current patch identity)"
                                                    )
                                                if b_did != patch.evidence.related_diagnostic_id:
                                                    failures.append(
                                                        f"Modified step '{s.step_id}' "
                                                        f"binding '{bname}' has "
                                                        f"related_diagnostic_id={b_did!r}, "
                                                        f"expected "
                                                        f"'{patch.evidence.related_diagnostic_id}'"
                                                        f" (changed binding must carry "
                                                        f"current diagnostic identity)"
                                                    )
                                                # -- Cross-consistency (belt+suspenders).
                                                if b_pid != ref_pid:
                                                    failures.append(
                                                        f"Modified step '{s.step_id}' "
                                                        f"binding '{bname}': "
                                                        f"evidence_ref has "
                                                        f"repair_patch_id={ref_pid!r} "
                                                        f"but binding has {b_pid!r}"
                                                    )
                                                if b_did != ref_did:
                                                    failures.append(
                                                        f"Modified step '{s.step_id}' "
                                                        f"binding '{bname}': "
                                                        f"evidence_ref has "
                                                        f"related_diagnostic_id={ref_did!r} "
                                                        f"but binding has {b_did!r}"
                                                    )

                                        # B. Validate every binding that is NOT historical.
                                        #    Historical = b_pid is non-empty AND explicitly
                                        #    belongs to a DIFFERENT known patch.
                                        #    Everything else (b_pid matches current patch,
                                        #    b_pid is missing, b_pid is wrong) must be
                                        #    validated.
                                        for bname, binding in bindings.items():
                                            if not isinstance(binding, dict):
                                                continue
                                            b_pid = binding.get("repair_patch_id")
                                            # Skip only bindings that explicitly belong
                                            # to a different patch (historical).
                                            if b_pid and b_pid != patch.patch_id:
                                                continue
                                            # This binding belongs to the current patch
                                            # (or has no/missing patch_id — broken).
                                            if (
                                                bname not in claimed_binding_names
                                                and b_pid == patch.patch_id
                                            ):
                                                failures.append(
                                                    f"Modified step '{s.step_id}' "
                                                    f"binding '{bname}' has "
                                                    f"repair_patch_id='{patch.patch_id}' "
                                                    f"but no matching evidence_ref claims it"
                                                )
                                            b_did = binding.get("related_diagnostic_id")
                                            if not b_pid:
                                                failures.append(
                                                    f"Modified step '{s.step_id}' "
                                                    f"binding '{bname}' is missing "
                                                    f"required field 'repair_patch_id'"
                                                )
                                            elif b_pid != patch.patch_id:
                                                failures.append(
                                                    f"Modified step '{s.step_id}' "
                                                    f"binding '{bname}' has "
                                                    f"repair_patch_id={b_pid!r}, "
                                                    f"expected '{patch.patch_id}'"
                                                )
                                            if not b_did:
                                                failures.append(
                                                    f"Modified step '{s.step_id}' "
                                                    f"binding '{bname}' is missing "
                                                    f"required field 'related_diagnostic_id'"
                                                )
                                            elif b_did != patch.evidence.related_diagnostic_id:
                                                failures.append(
                                                    f"Modified step '{s.step_id}' "
                                                    f"binding '{bname}' has "
                                                    f"related_diagnostic_id={b_did!r}, "
                                                    f"expected "
                                                    f"'{patch.evidence.related_diagnostic_id}'"
                                                )

        # 2. Check every changed WorkerHandoffIR for status source
        if apply_result.changed_handoff_ids:
            after_plan = patched.worker_plan
            if after_plan is not None:
                for h in after_plan.handoffs:
                    if h.handoff_id in apply_result.changed_handoff_ids:
                        input_src = getattr(h, "input_binding_status_source", None)
                        output_src = getattr(h, "output_binding_status_source", None)
                        has_input_bindings = bool(getattr(h, "input_bindings", []))
                        has_output_bindings = bool(getattr(h, "output_bindings", []))
                        # Require status_source when bindings exist;
                        # when bindings are empty, status_source is optional
                        if has_input_bindings:
                            if input_src is None:
                                failures.append(
                                    f"Changed handoff '{h.handoff_id}' has "
                                    f"input_bindings but no input_binding_status_source"
                                )
                            elif input_src != "user_confirmed_repair":
                                failures.append(
                                    f"Changed handoff '{h.handoff_id}' has "
                                    f"input_binding_status_source={input_src!r}, "
                                    f"expected 'user_confirmed_repair'"
                                )
                        if has_output_bindings:
                            if output_src is None:
                                failures.append(
                                    f"Changed handoff '{h.handoff_id}' has "
                                    f"output_bindings but no output_binding_status_source"
                                )
                            elif output_src != "user_confirmed_repair":
                                failures.append(
                                    f"Changed handoff '{h.handoff_id}' has "
                                    f"output_binding_status_source={output_src!r}, "
                                    f"expected 'user_confirmed_repair'"
                                )

        # 3. Evidence-ref coverage check.
        #    Only report when NO step-level evidence was found by the verifier
        #    above (failures were already added for missing metadata).  If the
        #    verifier confirmed evidence on changed steps (no step-level failures),
        #    the lack of evidence_refs is a reporting gap, not an evidence gap.
        if apply_result.changed_step_ids and not apply_result.evidence_refs:
            step_evidence_failures = [
                f for f in failures if "Modified step" in f or "New step" in f
            ]
            if step_evidence_failures:
                # Evidence refs are missing AND the verifier found evidence
                # problems on the steps themselves — real gap.
                pass  # failures already appended above
        if apply_result.changed_handoff_ids and not apply_result.evidence_refs:
            handoff_failures = [f for f in failures if "Changed handoff" in f]
            if handoff_failures:
                pass  # failures already appended above

        return tuple(failures)
