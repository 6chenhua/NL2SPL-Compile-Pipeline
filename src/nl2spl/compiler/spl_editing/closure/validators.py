"""Validators for ConstructClosurePlan."""

from __future__ import annotations

from nl2spl.compiler.constructs import RepairAffordanceSpec, SPLConstructRegistry
from nl2spl.compiler.spl_editing.closure.defaults import get_default_nodes_for_strategy
from nl2spl.compiler.spl_editing.closure.errors import ClosurePlanError
from nl2spl.compiler.spl_editing.closure.model import ConstructClosurePlan
from nl2spl.compiler.spl_editing.core.model import RepairTarget
from nl2spl.compiler.spl_editing.strategy.model import RepairStrategySpec


def resolve_target_affordance(target: RepairTarget) -> RepairAffordanceSpec:
    """Resolve the IRS repair affordance referenced by a RepairTarget."""
    try:
        irs = SPLConstructRegistry.default().get(target.irs_ref.construct_type)
    except KeyError as exc:
        raise ClosurePlanError(
            f"Unknown target construct type: {target.irs_ref.construct_type}"
        ) from exc

    slot = irs.get_slot(target.irs_ref.slot_name)
    if slot is None:
        raise ClosurePlanError(
            "Unknown target slot "
            f"'{target.irs_ref.slot_name}' for construct "
            f"'{target.irs_ref.construct_type}'."
        )

    for affordance in slot.repair_affordances:
        if affordance.affordance_id == target.affordance_id:
            return affordance

    raise ClosurePlanError(
        "Repair affordance "
        f"'{target.affordance_id}' is not declared for "
        f"{target.irs_ref.construct_type}.{target.irs_ref.slot_name}."
    )


def validate_closure_plan(
    plan: ConstructClosurePlan,
    strategy: RepairStrategySpec,
    target: RepairTarget,
) -> None:
    """Validate a ConstructClosurePlan against its strategy and target constraints.

    Checks:
    - Required target refs exist and target affordance matches the strategy.
    - Node actions are legal for the strategy template.
    - stage_slice_id exists in the strategy stage chain.
    - Closure plan references the correct materialization_plan_id from the affordance.
    """
    if not plan.target_construct_ref or not plan.target_construct_ref.strip():
        raise ClosurePlanError("Target construct reference must not be empty.")
    if plan.strategy_id != strategy.strategy_id:
        raise ClosurePlanError(
            f"Closure plan strategy_id '{plan.strategy_id}' does not match "
            f"strategy '{strategy.strategy_id}'."
        )
    if not set(plan.stage_slice_chain).issubset(set(strategy.stage_slice_chain)):
        raise ClosurePlanError(
            "Closure plan stage_slice_chain does not match the strategy "
            "stage_slice_chain."
        )

    affordance = resolve_target_affordance(target)
    if affordance.repair_strategy_id != strategy.strategy_id:
        raise ClosurePlanError(
            "Target affordance repair_strategy_id "
            f"'{affordance.repair_strategy_id}' does not match strategy "
            f"'{strategy.strategy_id}'."
        )
    if affordance.materialization_plan_id is None:
        raise ClosurePlanError(
            f"Target affordance '{target.affordance_id}' does not declare a "
            "materialization_plan_id."
        )
    if plan.materialization_plan_id != affordance.materialization_plan_id:
        raise ClosurePlanError(
            f"Closure plan materialization_plan_id '{plan.materialization_plan_id}' "
            "does not match affordance materialization_plan_id "
            f"'{affordance.materialization_plan_id}'"
        )

    target_slot = SPLConstructRegistry.default().get(
        target.irs_ref.construct_type
    ).get_slot(target.irs_ref.slot_name)
    if target_slot and target_slot.missing_diagnostic != strategy.diagnostic_kind:
        raise ClosurePlanError(
            "Strategy diagnostic_kind "
            f"'{strategy.diagnostic_kind}' does not match target slot "
            f"diagnostic '{target_slot.missing_diagnostic}'."
        )

    canonical_nodes = get_default_nodes_for_strategy(strategy.strategy_id, plan.option_id)
    if not canonical_nodes:
        raise ClosurePlanError(
            f"No closure node template is registered for strategy '{strategy.strategy_id}'."
        )
    if len(plan.closure_nodes) != len(canonical_nodes):
        raise ClosurePlanError(
            "Closure plan node count does not match the strategy closure template."
        )

    for node in plan.closure_nodes:
        if node.action not in {"ensure", "bind_existing", "materialize"}:
            raise ClosurePlanError(
                f"Illegal ConstructClosureNode action '{node.action}'. "
                "Must be 'ensure', 'bind_existing', or 'materialize'."
            )

        if strategy.strategy_id == "exception_flow.complete_handler_action.v1":
            if node.construct_type not in {"BLOCK", "COMMAND"}:
                raise ClosurePlanError(
                    f"Illegal construct type '{node.construct_type}' "
                    "for complete_handler_action strategy."
                )
        elif strategy.strategy_id == "required_output.materialize_producer.v1":
            if node.construct_type not in {"BLOCK", "COMMAND"}:
                raise ClosurePlanError(
                    f"Illegal construct type '{node.construct_type}' "
                    "for materialize_producer strategy."
                )
        elif strategy.strategy_id in {
            "worker_delegation.complete_closure.v1",
            "worker_delegation.complete_closure.v2",
        }:
            if node.construct_type not in {
                "WORKER_HANDOFF",
                "INVOKE_WORKER",
                "CHILD_WORKER",
                "BLOCK",
                "COMMAND",
                "FLOW",
            }:
                raise ClosurePlanError(
                    f"Illegal construct type '{node.construct_type}' "
                    "for complete_closure strategy."
                )

    for node, expected in zip(plan.closure_nodes, canonical_nodes, strict=True):
        if (
            node.role != expected.role
            or node.construct_type != expected.construct_type
            or node.action != expected.action
            or node.required is not expected.required
            or node.stage_slice_id != expected.stage_slice_id
        ):
            raise ClosurePlanError(
                "Closure node does not match the strategy closure template "
                f"for role '{expected.role}'."
            )

    for node in plan.closure_nodes:
        if node.stage_slice_id and node.stage_slice_id not in strategy.stage_slice_chain:
            raise ClosurePlanError(
                f"stage_slice_id '{node.stage_slice_id}' does not exist "
                f"in strategy stage chain {strategy.stage_slice_chain}"
            )
