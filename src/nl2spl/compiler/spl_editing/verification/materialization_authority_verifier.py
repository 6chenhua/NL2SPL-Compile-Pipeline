"""Verify materialized changes carry stage authority lineage."""

from __future__ import annotations

import json
from typing import Any

from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairPatch


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return (value,)
        return _as_tuple(parsed)
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    return (str(value),)


class MaterializationAuthorityVerifier:
    """Check changed artifacts against materialization result metadata.

    Non-materialized patches are ignored here. Materialized patches must prove
    plan, authority, evidence, and consumed-ref lineage on every changed StepIR.
    """

    def verify(
        self,
        patch: RepairPatch,
        apply_result: PatchApplyResult,
    ) -> tuple[str, ...]:
        audit = apply_result.audit_metadata
        if "materialization_plan_id" not in audit:
            return ()

        required = (
            "materialization_plan_id",
            "materializer_id",
            "materialization_authority",
            "evidence_packet_id",
            "consumed_selected_ref_ids",
        )
        failures: list[str] = []
        for key in required:
            if key not in audit or audit[key] is None or audit[key] == "":
                failures.append(f"Materialization audit metadata missing '{key}'.")

        if failures:
            return tuple(failures)

        expected_plan = str(audit["materialization_plan_id"])
        expected_authority = str(audit["materialization_authority"])
        expected_evidence_packet = str(audit["evidence_packet_id"])
        expected_consumed = set(_as_tuple(audit["consumed_selected_ref_ids"]))

        if not apply_result.changed_step_ids:
            return ()

        step_plan = apply_result.patched_snapshot.worker_step_plan
        if step_plan is None:
            return (
                "PatchApplyResult declares changed_step_ids but patched snapshot "
                "has no worker_step_plan.",
            )

        step_ids = set(apply_result.changed_step_ids)
        found_steps: set[str] = set()
        for worker_id, steps in step_plan.worker_steps.items():
            for step in steps:
                if step.step_id not in step_ids:
                    continue
                found_steps.add(step.step_id)
                metadata = getattr(step, "metadata", {}) or {}
                if metadata.get("origin") != "user_confirmed_repair":
                    failures.append(
                        f"Changed step '{step.step_id}' (worker '{worker_id}') "
                        "is missing origin=user_confirmed_repair."
                    )
                if metadata.get("repair_patch_id") != patch.patch_id:
                    failures.append(
                        f"Changed step '{step.step_id}' has repair_patch_id="
                        f"{metadata.get('repair_patch_id')!r}, expected "
                        f"{patch.patch_id!r}."
                    )
                if metadata.get("related_diagnostic_id") != patch.evidence.related_diagnostic_id:
                    failures.append(
                        f"Changed step '{step.step_id}' has related_diagnostic_id="
                        f"{metadata.get('related_diagnostic_id')!r}, expected "
                        f"{patch.evidence.related_diagnostic_id!r}."
                    )
                if metadata.get("materialization_plan_id") != expected_plan:
                    failures.append(
                        f"Changed step '{step.step_id}' has materialization_plan_id="
                        f"{metadata.get('materialization_plan_id')!r}, expected "
                        f"{expected_plan!r}."
                    )
                if metadata.get("materialization_authority") != expected_authority:
                    failures.append(
                        f"Changed step '{step.step_id}' has materialization_authority="
                        f"{metadata.get('materialization_authority')!r}, expected "
                        f"{expected_authority!r}."
                    )
                if metadata.get("evidence_packet_id") != expected_evidence_packet:
                    failures.append(
                        f"Changed step '{step.step_id}' has evidence_packet_id="
                        f"{metadata.get('evidence_packet_id')!r}, expected "
                        f"{expected_evidence_packet!r}."
                    )
                actual_consumed = set(_as_tuple(metadata.get("consumed_selected_ref_ids")))
                if actual_consumed != expected_consumed:
                    failures.append(
                        f"Changed step '{step.step_id}' consumed refs "
                        f"{sorted(actual_consumed)!r} do not match audit "
                        f"{sorted(expected_consumed)!r}."
                    )

        for step_id in sorted(step_ids - found_steps):
            failures.append(
                f"PatchApplyResult changed_step_ids includes '{step_id}' but "
                "the step was not found in patched snapshot."
            )

        return tuple(failures)
