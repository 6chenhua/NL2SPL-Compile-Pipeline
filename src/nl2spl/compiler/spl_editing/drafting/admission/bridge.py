"""Bridge typed inferred drafts into existing repair directives."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.admission.errors import NewFactAdmissionError
from nl2spl.compiler.spl_editing.admission.output_declaration import NewFactAdmissionService
from nl2spl.compiler.spl_editing.drafting.admission.errors import DraftAdmissionError
from nl2spl.compiler.spl_editing.drafting.admission.validators import (
    require_draft_acceptance,
    require_strategy_option_identity,
)
from nl2spl.compiler.spl_editing.drafting.model import StoredRepairDraft, UserRepairInput
from nl2spl.compiler.spl_editing.drafting.staleness import (
    DraftIdentity,
    require_fresh_draft,
)
from nl2spl.compiler.spl_editing.drafting.values import (
    BusinessLogicValue,
    ExplicitNoneValue,
    NewOutputDraftValue,
    PlacementIntentValue,
    ResponsibilityValue,
    ResultBindingValue,
    SelectedInputRefsValue,
    assert_provider_scope,
)
from nl2spl.compiler.spl_editing.interaction.model import (
    RepairInputValidationError,
    SubmitRepairDirectiveDraftRequest,
)
from nl2spl.compiler.spl_editing.interaction.normalization import (
    normalize_worker_delegation_directive,
)
from nl2spl.compiler.spl_editing.interaction.validation import (
    parse_worker_delegation_draft,
    validate_worker_delegation_draft,
)


@dataclass(frozen=True)
class DraftAdmissionResult:
    input_readiness: str
    directive_id: str | None
    directive: object | None = None
    errors: tuple[RepairInputValidationError, ...] = ()


class DraftAdmissionBridge:
    def __init__(self, *, output_admission: NewFactAdmissionService | None = None) -> None:
        self._output_admission = output_admission or NewFactAdmissionService()

    def admit_worker_delegation(
        self,
        *,
        stored: StoredRepairDraft,
        user_input: UserRepairInput,
        current: DraftIdentity,
        option,
        target,
        snapshot,
        refset,
        provider_id: str,
        contract_id: str,
        contract_version: str,
        revision_token: str,
    ) -> DraftAdmissionResult:
        try:
            require_fresh_draft(stored, current=current)
            require_draft_acceptance(user_input)
            self._require_confirmed_semantic_fields(stored=stored, user_input=user_input)
            require_strategy_option_identity(stored, option=option)
            request = self._to_worker_delegation_request(
                stored=stored,
                user_input=user_input,
                provider_id=provider_id,
                contract_id=contract_id,
                contract_version=contract_version,
                revision_token=revision_token,
            )
            draft = parse_worker_delegation_draft(request)
            errors = validate_worker_delegation_draft(draft, option=option, refset=refset)
            if errors:
                readiness = (
                    "input_required"
                    if all(error.code == "required_field_missing" for error in errors)
                    else "input_invalid"
                )
                return DraftAdmissionResult(readiness, None, None, errors)
            admitted = self._output_admission.admit_child_outputs(
                declarations=draft.returned_results,
                snapshot=snapshot,
                directive_id=draft.draft_id,
            )
            directive = normalize_worker_delegation_directive(
                draft,
                target_ref=target.target_ref,
                refset=refset,
                admitted_outputs=admitted,
            )
            return DraftAdmissionResult("input_complete", directive.directive_id, directive, ())
        except (DraftAdmissionError, NewFactAdmissionError, ValueError, TypeError) as exc:
            return DraftAdmissionResult(
                "input_invalid",
                None,
                None,
                (RepairInputValidationError(type(exc).__name__, None, str(exc)),),
            )

    @staticmethod
    def _to_worker_delegation_request(
        *,
        stored: StoredRepairDraft,
        user_input: UserRepairInput,
        provider_id: str,
        contract_id: str,
        contract_version: str,
        revision_token: str,
    ) -> SubmitRepairDirectiveDraftRequest:
        field_values: dict[str, object] = {}
        selected_ref_ids: dict[str, tuple[str, ...]] = {}
        new_fact_declarations: list[dict[str, object]] = []
        result_usage: list[dict[str, object]] = []
        semantic_field_ids = {field.field_id for field in stored.draft.fields}

        for field in stored.draft.fields:
            if _is_legacy_alias_shadowed(field.field_id, semantic_field_ids):
                continue
            value = field.value
            if value is None:
                continue
            assert_provider_scope(value, provider_id)
            if isinstance(value, ResponsibilityValue):
                field_values["delegated_responsibility"] = value.text
            elif isinstance(value, BusinessLogicValue):
                field_values["child_business_logic"] = value.text
            elif isinstance(value, SelectedInputRefsValue):
                selected_ref_ids["input_refs"] = value.ref_ids
            elif isinstance(value, ExplicitNoneValue):
                field_values["input_empty_semantics"] = "explicit_none"
            elif isinstance(value, NewOutputDraftValue):
                new_fact_declarations.append(
                    {
                        "local_id": value.local_id,
                        "display_name": value.display_name,
                        "semantic_description": value.semantic_description,
                        "data_type_hint": value.data_type_hint,
                    }
                )
            elif isinstance(value, PlacementIntentValue):
                field_values["invocation_timing"] = value.mode
                if value.ref_id is not None:
                    selected_ref_ids["placement_ref"] = (value.ref_id,)
            elif isinstance(value, ResultBindingValue):
                result_usage.append(
                    {
                        "output_local_id": value.output_local_id,
                        "parent_ref_id": value.parent_ref_id,
                        "create_parent_local_temporary": value.create_parent_local_temporary,
                    }
                )
            else:
                raise DraftAdmissionError(f"Unsupported field value: {type(value).__name__}")
        _apply_confirmed_semantic_fields(
            field_values=field_values,
            selected_ref_ids=selected_ref_ids,
            new_fact_declarations=new_fact_declarations,
            result_usage=result_usage,
            stored=stored,
            user_input=user_input,
        )
        if result_usage:
            field_values["result_usage"] = tuple(result_usage)
        return SubmitRepairDirectiveDraftRequest(
            run_id="",
            issue_id=stored.issue_id,
            strategy_id=stored.draft.strategy_id,
            option_id=stored.option_id,
            contract_id=contract_id,
            contract_version=contract_version,
            revision_token=revision_token,
            field_values=field_values,
            selected_ref_ids=selected_ref_ids,
            new_fact_declarations=tuple(new_fact_declarations),
        )

    @staticmethod
    def _require_confirmed_semantic_fields(
        *,
        stored: StoredRepairDraft,
        user_input: UserRepairInput,
    ) -> None:
        if stored.option_id != "define_child_worker":
            return
        confirmed = {
            item.field_id: item
            for item in user_input.field_values
            if item.source in {"accepted_default", "user", "ui_selection"}
        }
        required = {
            "child_task",
            "child_inputs",
            "child_output",
            "child_business_logic",
        }
        missing = sorted(required - set(confirmed))
        if missing:
            raise DraftAdmissionError(
                "confirmed semantic fields required before materialized preview: "
                + ", ".join(missing)
            )


def require_materialized_preview_acceptance(user_input: UserRepairInput) -> None:
    if not user_input.materialized_preview_accepted:
        raise DraftAdmissionError("materialized_preview_accepted is required before apply")


def _apply_confirmed_semantic_fields(
    *,
    field_values: dict[str, object],
    selected_ref_ids: dict[str, tuple[str, ...]],
    new_fact_declarations: list[dict[str, object]],
    result_usage: list[dict[str, object]],
    stored: StoredRepairDraft,
    user_input: UserRepairInput,
) -> None:
    confirmed = {item.field_id: item for item in user_input.field_values}

    child_task = _required_text(confirmed, "child_task")
    field_values["child_task"] = child_task
    field_values["delegated_responsibility"] = child_task

    child_business_logic = _required_text(confirmed, "child_business_logic")
    field_values["child_business_logic"] = child_business_logic

    child_inputs = _required_tuple(confirmed, "child_inputs")
    if child_inputs:
        selected_ref_ids["input_refs"] = child_inputs
        field_values.pop("input_empty_semantics", None)
    else:
        selected_ref_ids.pop("input_refs", None)
        field_values["input_empty_semantics"] = "explicit_none"

    child_output = _required_text(confirmed, "child_output")
    output_index = _first_output_index(new_fact_declarations)
    if output_index is None:
        local_id = _output_local_id_from_stored(stored)
        new_fact_declarations.append(
            {
                "local_id": local_id,
                "display_name": child_output,
                "semantic_description": f"Result returned by child worker: {child_output}",
                "data_type_hint": "text",
            }
        )
    else:
        original = dict(new_fact_declarations[output_index])
        original["display_name"] = child_output
        original["semantic_description"] = (
            original.get("semantic_description")
            or f"Result returned by child worker: {child_output}"
        )
        new_fact_declarations[output_index] = original

    output_local_id = str(new_fact_declarations[0]["local_id"])
    for index, usage in enumerate(result_usage):
        if usage.get("output_local_id"):
            result_usage[index] = {**usage, "output_local_id": output_local_id}


def _required_text(values: dict[str, object], field_id: str) -> str:
    item = values[field_id]
    if not isinstance(item.value, str) or not item.value.strip():
        raise DraftAdmissionError(f"{field_id} confirmation must be non-empty text")
    return item.value.strip()


def _required_tuple(values: dict[str, object], field_id: str) -> tuple[str, ...]:
    item = values[field_id]
    value = item.value
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple) and all(isinstance(child, str) for child in value):
        return value
    raise DraftAdmissionError(f"{field_id} confirmation must be a tuple of ref ids")


def _first_output_index(items: list[dict[str, object]]) -> int | None:
    return 0 if items else None


def _output_local_id_from_stored(stored: StoredRepairDraft) -> str:
    for field in stored.draft.fields:
        if isinstance(field.value, NewOutputDraftValue):
            return field.value.local_id
    return "delegated_result"


def _is_legacy_alias_shadowed(field_id: str, semantic_field_ids: set[str]) -> bool:
    shadowed = {
        "responsibility": "child_task",
        "input_refs": "child_inputs",
        "input_empty_semantics": "child_inputs",
        "output_draft": "child_output",
    }
    semantic = shadowed.get(field_id)
    return semantic is not None and semantic in semantic_field_ids
