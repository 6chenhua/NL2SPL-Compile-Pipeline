"""Verify selected-reference lineage on materialized SPL Editing repairs."""

from __future__ import annotations

import json
from typing import Any

from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairPatch
from nl2spl.compiler.spl_editing.intent.model import (
    ConstructRepairIntent,
    InsertProducerStepIntentPayload,
)


def _json_tuple(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    return tuple(str(v) for v in parsed)


class SelectedRefVerifier:
    """Check that materialized StepIR inputs are derived from selected refs."""

    def verify(
        self,
        patch: RepairPatch,
        apply_result: PatchApplyResult,
    ) -> tuple[str, ...]:
        audit = apply_result.audit_metadata
        if "materialization_plan_id" not in audit:
            return ()

        payload = patch.payload
        if not isinstance(payload, ConstructRepairIntent):
            if apply_result.changed_step_ids:
                return (
                    "Materialized patch payload must be ConstructRepairIntent "
                    "to verify selected-ref lineage.",
                )
            return ()

        intent = payload
        selected = set(intent.selected_ref_ids)
        consumed = set(_json_tuple(audit.get("consumed_selected_ref_ids")) or ())
        failures: list[str] = []

        if not consumed.issubset(selected):
            failures.append(
                "Consumed selected refs are not a subset of intent.selected_ref_ids: "
                f"unexpected={sorted(consumed - selected)!r}."
            )

        if not apply_result.changed_step_ids:
            return tuple(failures)

        step_plan = apply_result.patched_snapshot.worker_step_plan
        if step_plan is None:
            failures.append(
                "Cannot verify selected refs because patched snapshot has no worker_step_plan."
            )
            return tuple(failures)

        step_ids = set(apply_result.changed_step_ids)
        for worker_id, steps in step_plan.worker_steps.items():
            for step in steps:
                if step.step_id not in step_ids:
                    continue
                metadata = getattr(step, "metadata", {}) or {}
                step_consumed = _json_tuple(metadata.get("consumed_selected_ref_ids"))
                if step_consumed is None:
                    failures.append(
                        f"Changed step '{step.step_id}' (worker '{worker_id}') "
                        "has invalid or missing consumed_selected_ref_ids metadata."
                    )
                    continue

                step_consumed_set = set(step_consumed)
                if step_consumed_set != consumed:
                    failures.append(
                        f"Changed step '{step.step_id}' consumed refs "
                        f"{sorted(step_consumed_set)!r} do not match apply audit "
                        f"{sorted(consumed)!r}."
                    )
                if not step_consumed_set.issubset(selected):
                    failures.append(
                        f"Changed step '{step.step_id}' consumed refs include refs "
                        "not declared in intent.selected_ref_ids."
                    )

                plan_id = metadata.get("materialization_plan_id")
                if plan_id == "worker_handoff.contract_repair.v1":
                    if getattr(step, "command_type", "") == "INVOKE_WORKER" and not metadata.get(
                        "handoff_id"
                    ):
                        failures.append(
                            f"Changed step '{step.step_id}' is missing handoff_id metadata."
                        )
                else:
                    selected_names = _json_tuple(metadata.get("selected_ref_canonical_names"))
                    if selected_names is None:
                        failures.append(
                            f"Changed step '{step.step_id}' is missing "
                            "selected_ref_canonical_names metadata."
                        )
                    elif tuple(step.inputs) != selected_names:
                        failures.append(
                            f"Changed step '{step.step_id}' inputs {tuple(step.inputs)!r} "
                            f"do not match selected ref canonical names {selected_names!r}."
                        )
                    elif len(selected_names) != len(step_consumed):
                        failures.append(
                            f"Changed step '{step.step_id}' selected ref names count "
                            "does not match consumed ref id count."
                        )

                if isinstance(intent.payload, InsertProducerStepIntentPayload):
                    target_ref_id = intent.payload.target_output_ref_id
                    if metadata.get("target_output_ref_id") != target_ref_id:
                        failures.append(
                            f"Changed step '{step.step_id}' target_output_ref_id="
                            f"{metadata.get('target_output_ref_id')!r}, expected "
                            f"{target_ref_id!r}."
                        )
                    target_output_name = metadata.get("target_output_name")
                    if not target_output_name:
                        failures.append(
                            f"Changed step '{step.step_id}' is missing target_output_name metadata."
                        )
                    elif tuple(step.outputs) != (target_output_name,):
                        failures.append(
                            f"Changed step '{step.step_id}' outputs "
                            f"{tuple(step.outputs)!r} do not match target output "
                            f"{target_output_name!r}."
                        )

        return tuple(failures)
