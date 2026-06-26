"""Data models for ConstructRepairIntent and RepairEvidencePacket."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class InsertProducerStepIntentPayload:
    """Intended payload for inserting a step producing required output."""

    target_output_ref_id: str
    selected_input_ref_ids: tuple[str, ...] = ()
    producer_goal: str = ""
    placement_hint_ref_id: str | None = None
    notes_for_user: str | None = None


@dataclass(frozen=True)
class AddExceptionHandlerStepIntentPayload:
    """Intended payload for adding an exception-flow handler step."""

    target_exception_flow_ref_id: str
    selected_input_ref_ids: tuple[str, ...] = ()
    handler_goal: str = ""
    notes_for_user: str | None = None


@dataclass(frozen=True)
class CreateWorkerHandoffContractIntentPayload:
    """Intent payload for materializing a worker handoff contract."""

    target_worker_promotion_ref_id: str
    parent_worker_id: str
    child_worker_id: str
    input_bindings: tuple[tuple[str, str], ...] = ()
    output_bindings: tuple[tuple[str, str], ...] = ()
    invocation_point: str = "main"
    input_binding_status: str = "known_present"
    output_binding_status: str = "known_present"


@dataclass(frozen=True)
class ConvertDelegationToMainFlowStepIntentPayload:
    """Intent payload for keeping a delegation in the parent main flow."""

    target_worker_promotion_ref_id: str
    worker_id: str
    action_text: str
    outputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConvertDelegationToRequestInputIntentPayload:
    """Intent payload for asking the user to satisfy delegation details."""

    target_worker_promotion_ref_id: str
    worker_id: str
    prompt_text: str
    value_target: str
    outputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConstructRepairIntent:
    """An abstract construct-scoped intent representing user repair goals."""

    intent_id: str
    issue_id: str
    patch_type: str
    affordance_id: str
    target_construct_type: str
    target_construct_id: str
    target_slot_name: str
    target_ref_id: str
    selected_ref_ids: tuple[str, ...] = ()
    intent_summary: str = ""
    repair_goal: str = ""
    materialization_plan_id: str | None = None
    constraints: tuple[str, ...] = ()
    payload: Any = None


@dataclass(frozen=True)
class RepairEvidencePacket:
    """Packet sealing user confirmation context and audit links."""

    evidence_packet_id: str
    confirmed_intent_id: str
    repair_patch_id: str
    related_diagnostic_id: str
    user_text: str
    confirmed_selected_ref_ids: tuple[str, ...] = ()
    confirmed_at: str | None = None
    evidence_kind: Literal["user_confirmed_repair"] = "user_confirmed_repair"


@dataclass(frozen=True)
class IntentParseResult:
    """Result returned by the intent parser."""

    intent: ConstructRepairIntent | None = None
    errors: tuple[str, ...] = ()
    is_success: bool = True


@dataclass(frozen=True)
class IntentValidationResult:
    """Result returned by the intent validator."""

    errors: tuple[str, ...] = ()
    is_success: bool = True
