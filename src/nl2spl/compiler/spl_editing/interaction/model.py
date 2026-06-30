"""Backend-owned repair interaction contracts and presentation DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from nl2spl.compiler.spl_editing.admission.model import (
    AdmittedOutputDeclaration,
    NewOutputDeclarationDraft,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import ResolvedSelectableRef

RepairInputReadiness = Literal[
    "not_required", "input_required", "input_complete", "input_invalid", "not_evaluated"
]


@dataclass(frozen=True)
class RepairInputOptionView:
    option_id: str
    label: str
    value: str
    description: str | None = None


@dataclass(frozen=True)
class RepairInputFieldView:
    field_id: str
    label: str
    input_type: Literal[
        "short_text",
        "long_text",
        "single_choice",
        "multi_choice",
        "reference_select",
        "structured_object",
        "new_fact_list",
    ]
    required: bool
    description: str | None = None
    value: Any | None = None
    options: tuple[RepairInputOptionView, ...] = ()
    ref_role: str | None = None
    object_schema_id: str | None = None
    fact_schema_id: str | None = None

    def __post_init__(self) -> None:
        if self.input_type == "structured_object" and not self.object_schema_id:
            raise ValueError("structured_object fields require object_schema_id")
        if self.input_type == "new_fact_list" and not self.fact_schema_id:
            raise ValueError("new_fact_list fields require fact_schema_id")


@dataclass(frozen=True)
class RepairInputSchemaView:
    schema_id: str
    schema_version: str
    fields: tuple[RepairInputFieldView, ...]


@dataclass(frozen=True)
class RepairInputValidationError:
    code: str
    field_id: str | None
    message: str


@dataclass(frozen=True)
class RepairInteractionView:
    issue_id: str
    strategy_id: str
    option_id: str
    contract_id: str
    contract_version: str
    revision_token: str
    interaction_kind: Literal["none", "natural_language", "structured", "structured_with_notes"]
    availability: str
    input_readiness: RepairInputReadiness
    fields: tuple[RepairInputFieldView, ...] = ()
    schemas: tuple[RepairInputSchemaView, ...] = ()
    validation_errors: tuple[RepairInputValidationError, ...] = ()

    def __post_init__(self) -> None:
        ids = [schema.schema_id for schema in self.schemas]
        if len(ids) != len(set(ids)):
            raise ValueError("schema refs must resolve exactly once in one interaction view")
        known = set(ids)
        for field in self.fields:
            if field.object_schema_id and field.object_schema_id not in known:
                raise ValueError(f"Unknown object schema '{field.object_schema_id}'")
            if field.fact_schema_id and field.fact_schema_id not in known:
                raise ValueError(f"Unknown fact schema '{field.fact_schema_id}'")


@dataclass(frozen=True)
class RepairInteractionContractSpec:
    contract_id: str
    contract_version: str
    interaction_kind: str
    field_ids: tuple[str, ...]
    additional_instruction_policy: str
    provider_id: str
    normalizer_id: str


def revision_token_string(token) -> str:
    return f"{token.compile_run_id}:{token.artifact_snapshot_id}:{token.overlay_version}"


@dataclass(frozen=True)
class SubmitRepairDirectiveDraftRequest:
    run_id: str
    issue_id: str
    strategy_id: str
    option_id: str
    contract_id: str
    contract_version: str
    revision_token: str
    field_values: dict[str, Any]
    selected_ref_ids: dict[str, tuple[str, ...]]
    new_fact_declarations: tuple[dict[str, Any], ...]
    additional_instruction: str | None = None


@dataclass(frozen=True)
class DelegatedResponsibilityDraft:
    text: str


@dataclass(frozen=True)
class InvocationTimingDraft:
    placement_mode: Literal["append", "before", "after"]
    placement_ref_id: str | None = None


@dataclass(frozen=True)
class ResultUsageDraft:
    output_local_id: str
    parent_ref_id: str | None = None
    create_parent_local_temporary: bool = False


@dataclass(frozen=True)
class WorkerDelegationDirectiveDraft:
    draft_id: str
    issue_id: str
    strategy_id: str
    option_id: str
    contract_id: str
    contract_version: str
    base_revision: str
    delegated_responsibility: DelegatedResponsibilityDraft | None
    selected_input_ref_ids: tuple[str, ...]
    input_empty_semantics: str | None
    returned_results: tuple[NewOutputDeclarationDraft, ...]
    invocation_timing: InvocationTimingDraft | None
    result_usage: tuple[ResultUsageDraft, ...]
    additional_instruction: str | None


@dataclass(frozen=True)
class NormalizedResultUsage:
    output_id: str
    parent_ref: ResolvedSelectableRef | None
    parent_temporary_name: str | None


@dataclass(frozen=True)
class NormalizedWorkerDelegationDirective:
    directive_id: str
    strategy_id: str
    option_id: str
    target_ref: str
    base_revision: str
    delegated_responsibility: str
    selected_input_refs: tuple[ResolvedSelectableRef, ...]
    admitted_outputs: tuple[AdmittedOutputDeclaration, ...]
    invocation_timing: InvocationTimingDraft
    placement_ref: ResolvedSelectableRef | None
    result_usage: tuple[NormalizedResultUsage, ...]
    additional_instruction: str | None
    input_contract_hash: str
    verification_lane: Literal["B"] = "B"


@dataclass(frozen=True)
class RepairDirectiveValidationResult:
    input_readiness: RepairInputReadiness
    normalized_directive_id: str | None
    errors: tuple[RepairInputValidationError, ...]


__all__ = [name for name in globals() if name.startswith("Repair")]
