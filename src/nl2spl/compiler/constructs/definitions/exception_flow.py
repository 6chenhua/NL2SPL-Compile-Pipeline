"""Default ConstructIRS definitions for exception flow."""

from __future__ import annotations

from nl2spl.compiler.constructs.registry import SPLConstructRegistry
from nl2spl.compiler.constructs.spec import ConstructIRS, SlotSpec
from nl2spl.compiler.repair_contracts import RepairAffordanceSpec


def register(registry: SPLConstructRegistry) -> None:

# -- EXCEPTION_FLOW -------------------------------------------------
    registry.register(ConstructIRS(
        construct_type="EXCEPTION_FLOW",
        existence_policy="source_signal_required",
        source_signals=[
            "failure_mode",
            "exception_condition",
            "error_condition",
            "missing_state",
            "invalid_state",
            "refusal",
            "unavailable_resource",
            "provenance_failure",
        ],
        partial_rendering_allowed=True,
        description=(
            "An exceptional path triggered by a concrete failure condition. "
            "Can be rendered as a partial skeleton when only the condition "
            "is known."
        ),
        slots=[
            SlotSpec(
                slot_name="condition",
                syntax_required=True,
                required_for_partial=True,
                required_for_complete=True,
                evidence_kinds=["failure_mode", "exception_condition"],
            ),
            SlotSpec(
                slot_name="handler_action",
                syntax_required=False,
                required_for_complete=True,
                renderable_without=True,
                evidence_kinds=["handler_action", "recovery_step"],
                missing_diagnostic="missing_handler",
                can_be_suggested=True,
                notes=(
                    "Do not invent handler actions. "
                    "If missing, keep partial EXCEPTION_FLOW and emit missing_handler."
                ),
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="exception_flow.add_handler_step",
                        description=(
                            "Add a handler step to an exception flow that has "
                            "a condition but no handler action."
                        ),
                        supported_patch_types=("AddExceptionHandlerStep",),
                        default_patch_type="AddExceptionHandlerStep",
                        handler_id="missing_handler",
                        context_id="exception_flow_context",
                        target_resolver_id="exception_flow_target",
                        default_verification_lane="B",
                        editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
                        materialization_plan_id="stage7.exception_handler_step_repair.v1",
                        selectable_ref_policy_id="exception_flow.handler.selectable_refs.v1",
                        intent_schema_id="intent.add_exception_handler_step.v1",
                        required_context_facts=(
                            "exception_condition",
                            "worker_id",
                            "available_variables",
                            "nearby_steps",
                            "symbol_table",
                        ),
                        stage_authority="stage7.worker_step_plan",
                        repair_strategy_id="exception_flow.complete_handler_action.v1",
                    ),
                ),
            ),
            SlotSpec(
                slot_name="trigger_step",
                syntax_required=False,
                required_for_complete=False,
                renderable_without=True,
                evidence_kinds=["trigger_step"],
                notes="Post-MVP. Trigger association may be handled by global analysis.",
            ),
        ],
    ))
