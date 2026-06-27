"""Default MVP repair strategies and registry builder.

Excludes module-level side-effects.
"""

from __future__ import annotations

from typing import Iterable

from nl2spl.compiler.spl_editing.strategy.model import RepairStrategySpec
from nl2spl.compiler.spl_editing.strategy.registry import RepairStrategyRegistry


def iter_default_strategy_specs() -> Iterable[RepairStrategySpec]:
    """Iterate over all default RepairStrategySpecs."""
    yield RepairStrategySpec(
        strategy_id="exception_flow.complete_handler_action.v1",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        diagnostic_kind="missing_handler",
        missing_construct_closure=("BLOCK", "COMMAND"),
        default_policy_id="exception_handler.minimal_block.v1",
        directive_policy_id="exception_handler.directive_driven_block.v1",
        stage_slice_chain=(
            "stage5.exception_handler_block_repair.v1",
            "stage7.exception_handler_command_repair.v1",
        ),
        verification_lane="B",
        supported_patch_types=("AddExceptionHandlerStep",),
        selectable_ref_policy_id="exception_flow.handler.selectable_refs.v1",
        required_context_facts=(
            "exception_condition",
            "worker_id",
            "available_variables",
            "nearby_steps",
            "symbol_table",
        ),
        display_label="Complete Exception Handler Action",
        closure_summary="Ensure handler block and materialize handler command",
        preview_required=True,
    )
    yield RepairStrategySpec(
        strategy_id="required_output.materialize_producer.v1",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        diagnostic_kind="missing_output_producer",
        missing_construct_closure=("COMMAND",),
        default_policy_id="required_output.minimal_producer.v1",
        directive_policy_id="required_output.directive_driven_producer.v1",
        stage_slice_chain=("stage7.required_output_producer_command_repair.v1",),
        verification_lane="B",
        supported_patch_types=("InsertProducerStep",),
        selectable_ref_policy_id="required_output.producer.selectable_refs.v1",
        required_context_facts=(
            "target_output_name",
            "worker_id",
            "available_variables",
            "nearby_steps",
            "symbol_table",
        ),
        display_label="Materialize Producer for Required Output",
        closure_summary="Materialize producer step",
        preview_required=True,
    )
    yield RepairStrategySpec(
        strategy_id="worker_delegation.complete_closure.v1",
        target_construct_type="WORKER_PROMOTION",
        target_slot_name="promotion_input_contract",
        diagnostic_kind="type_or_contract_ambiguity",
        missing_construct_closure=("WORKER_HANDOFF", "INVOKE_WORKER", "CHILD_WORKER"),
        default_policy_id="worker_delegation.minimal_contract.v1",
        directive_policy_id="worker_delegation.directive_driven_contract.v1",
        stage_slice_chain=("stage3_5.worker_boundary", "stage7.worker_step_plan"),
        verification_lane="B",
        supported_patch_types=(
            "CreateWorkerHandoffContract",
            "ConvertDelegationIntentToMainFlowStep",
            "ConvertDelegationIntentToRequestInput",
        ),
        selectable_ref_policy_id="worker_promotion.handoff.selectable_refs.v1",
        required_context_facts=(
            "delegation_intent",
            "worker_id",
            "candidate_name",
            "possible_inputs",
            "possible_outputs",
            "hierarchy_graph",
        ),
        display_label="Complete Worker Delegation Handoff Contract",
        closure_summary="Materialize worker handoff, invoke worker command, parent binding, and optional placement block",
        preview_required=True,
    )


def build_default_strategy_registry() -> RepairStrategyRegistry:
    """Build and return a populated RepairStrategyRegistry."""
    registry = RepairStrategyRegistry()
    for spec in iter_default_strategy_specs():
        registry.register(spec)
    return registry
