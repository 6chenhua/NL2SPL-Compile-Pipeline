"""Default ConstructIRS registry assembly."""

from __future__ import annotations

from nl2spl.compiler.constructs.definitions import (
    api,
    command,
    exception_flow,
    output,
    resource_contract_demand,
    worker,
)
from nl2spl.compiler.constructs.registry import SPLConstructRegistry
from nl2spl.compiler.repair_contracts import (
    ActionabilityDecisionStatus,
    NonEditableDisposition,
    SlotActionabilityDecision,
)


def _editable_decision(
    rationale_code: str,
    source_ref: str,
    *,
    status: ActionabilityDecisionStatus = "confirmed",
) -> SlotActionabilityDecision:
    return SlotActionabilityDecision(
        actionability="editable",
        non_editable_disposition=None,
        rationale_code=rationale_code,
        decision_source_ref=source_ref,
        decision_status=status,
    )


def _non_editable_decision(
    disposition: NonEditableDisposition,
    rationale_code: str,
    source_ref: str,
) -> SlotActionabilityDecision:
    return SlotActionabilityDecision(
        actionability="non_editable",
        non_editable_disposition=disposition,
        rationale_code=rationale_code,
        decision_source_ref=source_ref,
    )


_IRS_SOURCE = ".agents/skills/irs-knowledge/SKILL.md"
_R12_SOURCE = "architecture:r12-construct-level-repair-strategy"
_API_SOURCE = "docs/design/api_definition_full_materialization_and_irs_design_zh.md"


_DEFAULT_SLOT_ACTIONABILITY: dict[
    tuple[str, str],
    SlotActionabilityDecision,
] = {
    ("API_DECLARATION", "api_name"): _non_editable_decision(
        "deferred_validation", "api_identity_owned_by_nl2spl", _API_SOURCE
    ),
    ("API_DECLARATION", "source_evidence"): _non_editable_decision(
        "deferred_validation", "api_evidence_owned_by_nl2spl", _API_SOURCE
    ),
    ("API_DECLARATION", "authentication"): _non_editable_decision(
        "deferred_validation", "api_validation_deferred", _API_SOURCE
    ),
    ("API_DECLARATION", "openapi_schema"): _non_editable_decision(
        "deferred_validation", "api_validation_deferred", _API_SOURCE
    ),
    ("API_DECLARATION", "functions"): _non_editable_decision(
        "deferred_validation", "api_validation_deferred", _API_SOURCE
    ),
    ("CALL_API", "api_name"): _non_editable_decision(
        "deferred_validation", "call_api_materialization_owned_by_nl2spl", _API_SOURCE
    ),
    ("CALL_API", "declared_api_ref"): _non_editable_decision(
        "deferred_validation", "call_api_binding_owned_by_nl2spl", _API_SOURCE
    ),
    ("CALL_API", "call_action"): _non_editable_decision(
        "deferred_validation", "call_api_action_owned_by_nl2spl", _API_SOURCE
    ),
    ("CALL_API", "integration_evidence"): _editable_decision(
        "legacy_affordance_requires_runtime_closure",
        _API_SOURCE,
        status="unresolved",
    ),
    ("CHILD_WORKER", "responsibility"): _non_editable_decision(
        "review_only", "worker_boundary_source_fact", _IRS_SOURCE
    ),
    ("CHILD_WORKER", "input_contract"): _non_editable_decision(
        "developer_only", "grouped_repair_owned_by_worker_promotion", _R12_SOURCE
    ),
    ("CHILD_WORKER", "output_contract"): _non_editable_decision(
        "developer_only", "grouped_repair_owned_by_worker_promotion", _R12_SOURCE
    ),
    ("CHILD_WORKER", "invocation_point"): _non_editable_decision(
        "developer_only", "grouped_repair_owned_by_worker_promotion", _R12_SOURCE
    ),
    ("CHILD_WORKER", "result_handoff"): _non_editable_decision(
        "developer_only", "grouped_repair_owned_by_worker_promotion", _R12_SOURCE
    ),
    ("EXCEPTION_FLOW", "condition"): _non_editable_decision(
        "non_repairable", "source_defined_exception_condition", _IRS_SOURCE
    ),
    ("EXCEPTION_FLOW", "handler_action"): _editable_decision(
        "construct_strategy_runtime_complete", _R12_SOURCE
    ),
    ("GENERAL_COMMAND", "action_text"): _non_editable_decision(
        "review_only", "source_defined_command_semantics", _IRS_SOURCE
    ),
    ("GENERAL_COMMAND", "source_evidence"): _non_editable_decision(
        "non_repairable", "source_evidence_cannot_be_invented", _IRS_SOURCE
    ),
    ("INVOKE_WORKER", "target_worker"): _editable_decision(
        "legacy_affordance_requires_runtime_closure", _IRS_SOURCE, status="unresolved"
    ),
    ("INVOKE_WORKER", "handoff_id"): _editable_decision(
        "legacy_affordance_requires_runtime_closure", _IRS_SOURCE, status="unresolved"
    ),
    ("INVOKE_WORKER", "input_bindings"): _editable_decision(
        "legacy_affordance_requires_runtime_closure", _IRS_SOURCE, status="unresolved"
    ),
    ("INVOKE_WORKER", "output_bindings"): _editable_decision(
        "legacy_affordance_requires_runtime_closure", _IRS_SOURCE, status="unresolved"
    ),
    ("REQUEST_INPUT", "prompt_text"): _non_editable_decision(
        "review_only", "source_defined_user_prompt", _IRS_SOURCE
    ),
    ("REQUEST_INPUT", "value_target"): _editable_decision(
        "legacy_affordance_requires_runtime_closure", _IRS_SOURCE, status="unresolved"
    ),
    ("REQUIRED_OUTPUT", "output_name"): _non_editable_decision(
        "non_repairable", "source_defined_output_contract", _IRS_SOURCE
    ),
    ("REQUIRED_OUTPUT", "producer"): _editable_decision(
        "construct_strategy_runtime_complete", _R12_SOURCE
    ),
    ("RESOURCE_CONTRACT_DEMAND", "materialization"): _non_editable_decision(
        "developer_only", "compiler_materialization_gap", _IRS_SOURCE
    ),
    ("RESOURCE_CONTRACT_DEMAND", "resource_registry"): _non_editable_decision(
        "developer_only", "compiler_registry_consistency_gap", _IRS_SOURCE
    ),
    ("RESOURCE_CONTRACT_DEMAND", "producer"): _non_editable_decision(
        "developer_only", "alias_repair_owned_by_required_output", _IRS_SOURCE
    ),
    ("WORKER_CANDIDATE", "responsibility"): _non_editable_decision(
        "review_only", "worker_candidate_source_fact", _IRS_SOURCE
    ),
    ("WORKER_CANDIDATE", "delegation_signal"): _non_editable_decision(
        "non_repairable", "delegation_signal_is_source_evidence", _IRS_SOURCE
    ),
    ("WORKER_CANDIDATE", "source_evidence"): _non_editable_decision(
        "non_repairable", "source_evidence_cannot_be_invented", _IRS_SOURCE
    ),
    ("WORKER_HANDOFF", "from_worker"): _non_editable_decision(
        "developer_only", "grouped_repair_owned_by_worker_promotion", _R12_SOURCE
    ),
    ("WORKER_HANDOFF", "target"): _editable_decision(
        "legacy_affordance_requires_runtime_closure", _IRS_SOURCE, status="unresolved"
    ),
    ("WORKER_HANDOFF", "input_bindings"): _editable_decision(
        "legacy_affordance_requires_runtime_closure", _IRS_SOURCE, status="unresolved"
    ),
    ("WORKER_HANDOFF", "output_bindings"): _editable_decision(
        "legacy_affordance_requires_runtime_closure", _IRS_SOURCE, status="unresolved"
    ),
    ("WORKER_HANDOFF", "invocation_site"): _editable_decision(
        "legacy_affordance_requires_runtime_closure", _IRS_SOURCE, status="unresolved"
    ),
    ("WORKER_PROMOTION", "promotion_input_contract"): _editable_decision(
        "construct_strategy_runtime_complete", _R12_SOURCE
    ),
    ("WORKER_PROMOTION", "promotion_output_contract"): _editable_decision(
        "construct_strategy_runtime_complete", _R12_SOURCE
    ),
    ("WORKER_PROMOTION", "promotion_invocation_point"): _editable_decision(
        "construct_strategy_runtime_complete", _R12_SOURCE
    ),
    ("WORKER_PROMOTION", "promotion_result_handoff"): _editable_decision(
        "construct_strategy_runtime_complete", _R12_SOURCE
    ),
}


def _apply_default_actionability_decisions(registry: SPLConstructRegistry) -> None:
    for (construct_type, slot_name), decision in _DEFAULT_SLOT_ACTIONABILITY.items():
        slot = registry.get(construct_type).get_slot(slot_name)
        if slot is None:
            raise ValueError(
                f"Actionability decision references unknown slot {construct_type}.{slot_name}"
            )
        slot.actionability_decision = decision


def build_default_construct_registry() -> SPLConstructRegistry:
    """Build the default registry with all current constructs."""
    registry = SPLConstructRegistry()
    exception_flow.register(registry)
    output.register(registry)
    command.register(registry)
    api.register(registry)
    worker.register(registry)
    resource_contract_demand.register(registry)
    _apply_default_actionability_decisions(registry)
    return registry
