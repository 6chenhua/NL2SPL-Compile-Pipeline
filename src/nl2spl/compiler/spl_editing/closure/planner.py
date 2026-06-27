"""Planner for ConstructClosurePlan."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nl2spl.compiler.spl_editing.closure.defaults import get_default_nodes_for_strategy
from nl2spl.compiler.spl_editing.closure.errors import ClosurePlanError
from nl2spl.compiler.spl_editing.closure.model import ConstructClosurePlan
from nl2spl.compiler.spl_editing.closure.validators import (
    resolve_target_affordance,
    validate_closure_plan,
)
from nl2spl.compiler.spl_editing.core.model import RepairTarget
from nl2spl.compiler.spl_editing.strategy.model import RepairDirective, RepairStrategySpec


def _selected_ref_exists(selectable_refs: Any, ref_id: str) -> bool:
    if hasattr(selectable_refs, "get_ref"):
        return selectable_refs.get_ref(ref_id) is not None
    if isinstance(selectable_refs, Mapping):
        return ref_id in selectable_refs
    try:
        return ref_id in selectable_refs
    except TypeError as exc:
        raise ClosurePlanError(
            "selectable_refs must support get_ref(ref_id), mapping lookup, or membership."
        ) from exc


class ClosurePlanner:
    """Orchestrates generation of instance-level ConstructClosurePlan."""

    @staticmethod
    def generate_closure_plan(
        closure_plan_id: str,
        strategy: RepairStrategySpec,
        target: RepairTarget,
        directive: RepairDirective,
        selectable_refs: Any = None,
    ) -> ConstructClosurePlan:
        """Generate a ConstructClosurePlan based on strategy, target, directive, and references.

        Performs full validation before returning the plan.
        """
        if not target.target_ref or not target.target_ref.strip():
            raise ClosurePlanError("Target construct reference must not be empty.")
        if target.irs_ref.construct_type != strategy.target_construct_type:
            raise ClosurePlanError(
                "Target construct type "
                f"'{target.irs_ref.construct_type}' does not match strategy "
                f"target_construct_type '{strategy.target_construct_type}'."
            )
        if directive.target_construct_type != target.irs_ref.construct_type:
            raise ClosurePlanError(
                "Directive target_construct_type "
                f"'{directive.target_construct_type}' does not match target "
                f"construct_type '{target.irs_ref.construct_type}'."
            )
        if directive.target_slot_name != target.irs_ref.slot_name:
            raise ClosurePlanError(
                "Directive target_slot_name "
                f"'{directive.target_slot_name}' does not match target slot "
                f"'{target.irs_ref.slot_name}'."
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

        if strategy.selectable_ref_policy_id and directive.selected_ref_hints:
            if selectable_refs is None:
                raise ClosurePlanError(
                    "selectable_refs are required when directive selected_ref_hints are present."
                )
            for hint in directive.selected_ref_hints:
                if not _selected_ref_exists(selectable_refs, hint):
                    raise ClosurePlanError(
                        f"Required selected reference '{hint}' not found in selectable refs."
                    )

        nodes = get_default_nodes_for_strategy(strategy.strategy_id)
        write_layers = tuple(
            slice_id.split(".")[0] for slice_id in strategy.stage_slice_chain if slice_id
        )

        default_or_directive_driven = "default"
        if directive.source == "user" or directive.requested_behavior:
            default_or_directive_driven = "directive_driven"

        plan = ConstructClosurePlan(
            closure_plan_id=closure_plan_id,
            strategy_id=strategy.strategy_id,
            materialization_plan_id=affordance.materialization_plan_id,
            target_construct_ref=target.target_ref,
            closure_nodes=nodes,
            stage_slice_chain=strategy.stage_slice_chain,
            write_layers=write_layers,
            dependency_closure=(),
            default_or_directive_driven=default_or_directive_driven,
        )

        validate_closure_plan(plan, strategy, target)
        return plan
