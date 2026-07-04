"""Typed parsing and validation for Worker Delegation repair drafts."""

from __future__ import annotations

import hashlib
import json

from nl2spl.compiler.spl_editing.admission.model import NewOutputDeclarationDraft
from nl2spl.compiler.spl_editing.interaction.model import (
    DelegatedResponsibilityDraft,
    InvocationTimingDraft,
    RepairInputValidationError,
    ResultUsageDraft,
    SubmitRepairDirectiveDraftRequest,
    WorkerDelegationDirectiveDraft,
)


def parse_worker_delegation_draft(
    request: SubmitRepairDirectiveDraftRequest,
) -> WorkerDelegationDirectiveDraft:
    values = request.field_values
    responsibility = values.get("delegated_responsibility") or values.get("task_selection")
    responsibility_draft = (
        DelegatedResponsibilityDraft(str(responsibility).strip())
        if isinstance(responsibility, str) and responsibility.strip()
        else None
    )
    timing_value = values.get("invocation_timing", "append")
    placement_ref_ids = tuple(request.selected_ref_ids.get("placement_ref", ()))
    if len(placement_ref_ids) > 1:
        raise ValueError("placement_ref accepts exactly one reference")
    legacy_placement_ref = values.get("placement_ref")
    placement_ref = placement_ref_ids[0] if placement_ref_ids else legacy_placement_ref
    if (
        placement_ref_ids
        and legacy_placement_ref is not None
        and legacy_placement_ref != placement_ref_ids[0]
    ):
        raise ValueError("placement_ref differs between reference and field channels")
    timing = InvocationTimingDraft(
        placement_mode=timing_value,
        placement_ref_id=placement_ref if isinstance(placement_ref, str) else None,
    )
    declarations = tuple(
        NewOutputDeclarationDraft(
            local_id=str(item.get("local_id", "")),
            display_name=str(item.get("display_name", "")),
            semantic_description=str(item.get("semantic_description", "")),
            data_type_hint=(
                str(item["data_type_hint"]) if item.get("data_type_hint") is not None else None
            ),
        )
        for item in request.new_fact_declarations
    )
    raw_usage = values.get("result_usage", ())
    if isinstance(raw_usage, dict):
        raw_usage = (raw_usage,)
    usage = tuple(
        ResultUsageDraft(
            output_local_id=str(item.get("output_local_id", "")),
            parent_ref_id=(str(item["parent_ref_id"]) if item.get("parent_ref_id") else None),
            create_parent_local_temporary=(
                item.get("create_parent_local_temporary") is True
                or item.get("create_parent_local_temporary") == "yes"
            ),
        )
        for item in raw_usage
        if isinstance(item, dict)
    )
    digest = hashlib.sha256(
        json.dumps(
            {
                "issue": request.issue_id,
                "option": request.option_id,
                "revision": request.revision_token,
                "fields": request.field_values,
                "refs": request.selected_ref_ids,
                "facts": request.new_fact_declarations,
                "instruction": request.additional_instruction,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()[:20]
    return WorkerDelegationDirectiveDraft(
        draft_id=f"draft_{digest}",
        issue_id=request.issue_id,
        strategy_id=request.strategy_id,
        option_id=request.option_id,
        contract_id=request.contract_id,
        contract_version=request.contract_version,
        base_revision=request.revision_token,
        delegated_responsibility=responsibility_draft,
        selected_input_ref_ids=tuple(request.selected_ref_ids.get("input_refs", ())),
        input_empty_semantics=(
            str(values["input_empty_semantics"])
            if values.get("input_empty_semantics") is not None
            else None
        ),
        returned_results=declarations,
        invocation_timing=timing,
        result_usage=usage,
        additional_instruction=request.additional_instruction,
    )


def validate_worker_delegation_draft(
    draft, *, option, refset
) -> tuple[RepairInputValidationError, ...]:
    errors: list[RepairInputValidationError] = []
    if draft.delegated_responsibility is None:
        errors.append(
            _error(
                "required_field_missing", "delegated_responsibility", "Responsibility is required"
            )
        )
    if draft.option_id == "define_child_worker":
        if not draft.returned_results:
            errors.append(
                _error(
                    "required_field_missing",
                    "returned_results",
                    "At least one child result is required",
                )
            )
        if len(draft.result_usage) != len(draft.returned_results):
            errors.append(
                _error(
                    "missing_result_usage",
                    "result_usage",
                    "Every child result requires result usage",
                )
            )
        if not draft.selected_input_ref_ids and draft.input_empty_semantics != "explicit_none":
            errors.append(
                _error(
                    "required_field_missing",
                    "input_empty_semantics",
                    "Confirm that the child requires no parent input",
                )
            )
        if draft.selected_input_ref_ids and draft.input_empty_semantics is not None:
            errors.append(
                _error(
                    "conflicting_input_semantics",
                    "input_empty_semantics",
                    "No-input confirmation cannot be combined with selected inputs",
                )
            )
    if draft.invocation_timing is None or draft.invocation_timing.placement_mode not in {
        "append",
        "before",
        "after",
    }:
        errors.append(
            _error(
                "invalid_invocation_timing",
                "invocation_timing",
                "Only append/before/after are supported",
            )
        )
    elif (
        draft.invocation_timing.placement_mode in {"before", "after"}
        and not draft.invocation_timing.placement_ref_id
    ):
        errors.append(
            _error("required_field_missing", "placement_ref", "Placement anchor is required")
        )
    local_ids = {item.local_id for item in draft.returned_results}
    declarations_by_id = {item.local_id: item for item in draft.returned_results}
    for usage in draft.result_usage:
        if usage.output_local_id not in local_ids:
            errors.append(_error("unknown_output_local_id", "result_usage", usage.output_local_id))
        if bool(usage.parent_ref_id) == bool(usage.create_parent_local_temporary):
            errors.append(
                _error("invalid_result_usage", "result_usage", "Choose one parent target mode")
            )
        if usage.parent_ref_id:
            ref = refset.get_ref(usage.parent_ref_id) if refset is not None else None
            if ref is None:
                errors.append(_error("invalid_ref_id", "result_usage", usage.parent_ref_id))
            elif ref.ref_role != "binding_target":
                errors.append(_error("invalid_ref_role", "result_usage", usage.parent_ref_id))
            elif ref.scope not in {"global", "worker"}:
                errors.append(_error("invalid_ref_scope", "result_usage", usage.parent_ref_id))
            else:
                declared_type = (
                    declarations_by_id.get(usage.output_local_id).data_type_hint
                    if usage.output_local_id in declarations_by_id
                    else None
                )
                if (
                    declared_type
                    and ref.type_hint
                    and declared_type.strip().casefold() != ref.type_hint.strip().casefold()
                ):
                    errors.append(
                        _error(
                            "result_binding_type_mismatch",
                            "result_usage",
                            f"{declared_type} cannot bind to {ref.type_hint}",
                        )
                    )
    for ref_id in draft.selected_input_ref_ids:
        ref = refset.get_ref(ref_id) if refset is not None else None
        if ref is None:
            errors.append(_error("invalid_ref_id", "input_refs", ref_id))
        elif ref.ref_role != "selectable_input":
            errors.append(_error("invalid_ref_role", "input_refs", ref_id))
    if draft.invocation_timing and draft.invocation_timing.placement_ref_id:
        ref = (
            refset.get_ref(draft.invocation_timing.placement_ref_id) if refset is not None else None
        )
        if ref is None:
            errors.append(
                _error("invalid_ref_id", "placement_ref", draft.invocation_timing.placement_ref_id)
            )
        elif ref.ref_role != "placement_anchor":
            errors.append(
                _error(
                    "invalid_ref_role", "placement_ref", draft.invocation_timing.placement_ref_id
                )
            )
    forbidden = ("patch_type", "verification_lane", "selected_ref_ids", "create required output")
    instruction = (draft.additional_instruction or "").lower()
    if any(token in instruction for token in forbidden):
        errors.append(
            _error(
                "instruction_conflicts_with_structured_input",
                "additional_instruction",
                "Instruction attempts to override structured authority",
            )
        )
    return tuple(errors)


def _error(code: str, field_id: str | None, message: str) -> RepairInputValidationError:
    return RepairInputValidationError(code=code, field_id=field_id, message=message)
