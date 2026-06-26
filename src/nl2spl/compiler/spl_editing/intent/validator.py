"""Validator for ConstructRepairIntent against SelectableRefSet and RepairCatalogEntry."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.intent.model import (
    ConstructRepairIntent,
    IntentValidationResult,
)
from nl2spl.compiler.spl_editing.selectable_refs import (
    SelectableRefSet,
    resolve_ref_ids_to_result,
)


class IntentValidator:
    """Validator for ConstructRepairIntent to verify references and matching catalog metadata."""

    @staticmethod
    def validate(
        intent: ConstructRepairIntent,
        refset: SelectableRefSet,
        catalog_entry: RepairCatalogEntry,
    ) -> IntentValidationResult:
        """Validate the intent structure, types, plans, and reference resolution."""
        errors: list[str] = []

        # 1. Validate patch_type is supported
        if intent.patch_type not in catalog_entry.supported_patch_types:
            errors.append(
                f"Patch type '{intent.patch_type}' is not supported by catalog entry (supported: {catalog_entry.supported_patch_types})"  # noqa: E501
            )

        # 1.1 Validate affordance_id matches catalog entry
        if intent.affordance_id != catalog_entry.affordance_id:
            errors.append(
                f"Intent affordance_id '{intent.affordance_id}' does not match catalog entry affordance_id '{catalog_entry.affordance_id}'"  # noqa: E501
            )

        # 1.2 Validate target_construct_type matches catalog entry construct_type
        if intent.target_construct_type != catalog_entry.construct_type:
            errors.append(
                f"Intent target_construct_type '{intent.target_construct_type}' does not match catalog entry construct_type '{catalog_entry.construct_type}'"  # noqa: E501
            )

        # 1.3 Validate target_slot_name matches catalog entry slot_name
        if intent.target_slot_name != catalog_entry.slot_name:
            errors.append(
                f"Intent target_slot_name '{intent.target_slot_name}' does not match catalog entry slot_name '{catalog_entry.slot_name}'"  # noqa: E501
            )

        # 2. Validate materialization_plan_id matches catalog expected plan
        expected_plan = getattr(catalog_entry, "materialization_plan_id", None)
        if expected_plan is None:
            errors.append(
                "Catalog metadata missing: materialization_plan_id is not defined on the catalog entry."  # noqa: E501
            )
        elif intent.materialization_plan_id != expected_plan:
            errors.append(
                f"Materialization plan ID '{intent.materialization_plan_id}' does not match catalog expected '{expected_plan}'"  # noqa: E501
            )

        # 3. Validate target_ref_id resolves under the construct-specific target role.
        target_role = "target_output"
        if intent.patch_type == "AddExceptionHandlerStep":
            target_role = "target_exception_flow"
        elif intent.patch_type == "CreateWorkerHandoffContract":
            target_role = "target_worker"

        target_ref_ids_to_check = set()
        if intent.target_ref_id:
            target_ref_ids_to_check.add(intent.target_ref_id)
        else:
            errors.append("Missing target_ref_id in intent validation.")

        if hasattr(intent.payload, "target_output_ref_id") and intent.payload.target_output_ref_id:
            target_ref_ids_to_check.add(intent.payload.target_output_ref_id)
            if intent.target_ref_id != intent.payload.target_output_ref_id:
                errors.append("Intent target_ref_id does not match payload target_output_ref_id.")
        if (
            hasattr(intent.payload, "target_exception_flow_ref_id")
            and intent.payload.target_exception_flow_ref_id
        ):
            target_ref_ids_to_check.add(intent.payload.target_exception_flow_ref_id)
            if intent.target_ref_id != intent.payload.target_exception_flow_ref_id:
                errors.append(
                    "Intent target_ref_id does not match payload target_exception_flow_ref_id."
                )

        for ref_id in sorted(target_ref_ids_to_check):
            res_target = resolve_ref_ids_to_result(refset, (ref_id,), target_role)
            if not res_target.is_success:
                errors.extend(res_target.errors)

        # 4. Validate selected_ref_ids resolve as selectable_input
        # We only validate explicitly selected input refs.
        # Producer goal text itself is never parsed for refs; we only validate what is in selected_ref_ids.  # noqa: E501
        input_ref_ids_to_check = set()
        if intent.selected_ref_ids:
            input_ref_ids_to_check.update(intent.selected_ref_ids)

        if (
            hasattr(intent.payload, "selected_input_ref_ids")
            and intent.payload.selected_input_ref_ids
        ):
            input_ref_ids_to_check.update(intent.payload.selected_input_ref_ids)
            if tuple(intent.selected_ref_ids) != tuple(intent.payload.selected_input_ref_ids):
                errors.append(
                    "Intent selected_ref_ids do not match payload selected_input_ref_ids."
                )

        if input_ref_ids_to_check:
            res_inputs = resolve_ref_ids_to_result(
                refset, tuple(sorted(input_ref_ids_to_check)), "selectable_input"
            )
            if not res_inputs.is_success:
                errors.extend(res_inputs.errors)

        is_success = len(errors) == 0
        return IntentValidationResult(errors=tuple(errors), is_success=is_success)
