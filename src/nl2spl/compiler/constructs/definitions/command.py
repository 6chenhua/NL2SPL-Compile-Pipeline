"""Default ConstructIRS definitions for command."""

from __future__ import annotations

from nl2spl.compiler.constructs.registry import SPLConstructRegistry
from nl2spl.compiler.constructs.spec import ConstructIRS, SlotSpec
from nl2spl.compiler.repair_contracts import RepairAffordanceSpec


def register(registry: SPLConstructRegistry) -> None:

# -- GENERAL_COMMAND -------------------------------------------------
    registry.register(ConstructIRS(
        construct_type="GENERAL_COMMAND",
        existence_policy="source_signal_required",
        source_signals=["action", "operation", "process_step"],
        partial_rendering_allowed=False,
        description=(
            "A concrete executable step backed by source evidence. "
            "Must not be rendered from assumption alone."
        ),
        slots=[
            SlotSpec(
                slot_name="action_text",
                syntax_required=True,
                required_for_complete=True,
                evidence_kinds=["action", "operation"],
            ),
            SlotSpec(
                slot_name="source_evidence",
                required_for_complete=True,
                renderable_without=False,
                evidence_kinds=["source_span", "semantic_packet", "hard_fact"],
                missing_diagnostic="assumed_command_not_renderable",
            ),
            SlotSpec(
                slot_name="result_variable",
                syntax_required=False,
                required_for_complete=False,
                evidence_kinds=["result", "output", "derived_variable"],
                notes=(
                    "May be satisfied by a single StepIR.outputs rendered "
                    "as a single structured COMMAND_RESULT."
                ),
            ),
        ],
    ))

# -- REQUEST_INPUT ---------------------------------------------------
    registry.register(ConstructIRS(
        construct_type="REQUEST_INPUT",
        existence_policy="source_signal_required",
        source_signals=[
            "ask_user",
            "request_clarification",
            "prompt_user",
            "user_confirms",
            "obtain_user_input",
        ],
        partial_rendering_allowed=False,
        description=(
            "A user-facing interaction step.  Only allowed when the source "
            "explicitly describes asking, prompting, or confirming — not "
            "merely because some information is missing."
        ),
        slots=[
            SlotSpec(
                slot_name="prompt_text",
                syntax_required=True,
                required_for_complete=True,
                evidence_kinds=["ask_user", "clarification_request", "confirmation_request"],
                missing_diagnostic="assumed_command_not_renderable",
            ),
            SlotSpec(
                slot_name="value_target",
                syntax_required=True,
                required_for_complete=True,
                evidence_kinds=["input_variable", "confirmation_variable"],
                missing_diagnostic="type_or_contract_ambiguity",
                notes=(
                    "May target a single StepIR.outputs rendered as a "
                    "single structured VALUE COMMAND_RESULT."
                ),
                repair_affordances=(
                    RepairAffordanceSpec(
                        affordance_id="request_input.specify_value_target",
                        description="Specify the variable that receives the user's input.",
                        supported_patch_types=("SpecifyValueTarget",),
                        default_patch_type="SpecifyValueTarget",
                        handler_id="type_or_contract_ambiguity",
                        context_id="request_input_context",
                        target_resolver_id="step_target",
                        default_verification_lane="A",
                        editable_artifacts=("WorkerStepPlanIR",),
                    ),
                ),
            ),
        ],
    ))
