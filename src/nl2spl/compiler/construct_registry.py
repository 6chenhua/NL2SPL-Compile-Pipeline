"""SPL Construct Registry — IRS data model for construct-level information requirements.

Defines the v5 IRS types (SlotSpec, ConstructIRS, SlotSatisfaction,
ConstructSatisfactionReport) and the SPLConstructRegistry that holds
the default construct definitions.

This module is pure data — no prompt wiring and no pipeline behaviour changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ExistencePolicy = Literal[
    "source_signal_required",
    "compiler_default_allowed",
    "grammar_required_if_parent_exists",
]

NoDemandBehavior = Literal[
    "do_not_generate",
    "generate_default",
    "report_ambiguity",
]

SlotStatus = Literal["satisfied", "missing", "inferred", "assumed", "not_applicable"]

ConstructCompleteness = Literal["complete", "partial", "blocked"]


@dataclass
class SlotSpec:
    """A single information slot within a SPL construct."""

    slot_name: str
    syntax_required: bool = False
    required_for_partial: bool = False
    required_for_complete: bool = False
    renderable_without: bool = False
    evidence_kinds: list[str] = field(default_factory=list)
    missing_diagnostic: str | None = None
    can_be_inferred: bool = False
    can_be_suggested: bool = True
    notes: str | None = None


@dataclass
class ConstructIRS:
    """Information Requirements Spec for one SPL construct type."""

    construct_type: str
    existence_policy: ExistencePolicy
    source_signals: list[str]
    slots: list[SlotSpec]
    no_demand_behavior: NoDemandBehavior = "do_not_generate"
    partial_rendering_allowed: bool = False
    description: str | None = None

    # ------------------------------------------------------------------
    # Read-only helpers (no evaluator logic — Phase 1 data model only)
    # ------------------------------------------------------------------

    def get_slot(self, name: str) -> SlotSpec | None:
        """Return the SlotSpec with *name*, or None."""
        for slot in self.slots:
            if slot.slot_name == name:
                return slot
        return None

    def required_slots_for_partial(self) -> list[SlotSpec]:
        """Slots that must be satisfied to produce even a partial construct."""
        return [s for s in self.slots if s.required_for_partial]

    def required_slots_for_complete(self) -> list[SlotSpec]:
        """Slots that must be satisfied to produce a semantically complete construct."""
        return [s for s in self.slots if s.required_for_complete]


@dataclass
class SlotSatisfaction:
    """Evidence-backed assessment of a single slot."""

    slot_name: str
    status: SlotStatus
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    relation: Literal["direct", "normalized", "inferred", "assumed"] | None = None
    diagnostic_kind: str | None = None
    explanation: str | None = None


@dataclass
class ConstructSatisfactionReport:
    """Slot-level satisfaction report for one materialised construct."""

    construct_id: str
    construct_type: str
    slots: list[SlotSatisfaction]
    completeness: ConstructCompleteness
    renderable: bool
    diagnostics: list = field(default_factory=list)


class SPLConstructRegistry:
    """Registry of ConstructIRS definitions keyed by construct type."""

    def __init__(self) -> None:
        self._constructs: dict[str, ConstructIRS] = {}

    # -- mutation -----------------------------------------------------------

    def register(self, irs: ConstructIRS) -> None:
        self._constructs[irs.construct_type] = irs

    # -- query --------------------------------------------------------------

    def get(self, construct_type: str) -> ConstructIRS:
        if construct_type not in self._constructs:
            raise KeyError(f"Unknown construct type: {construct_type}")
        return self._constructs[construct_type]

    def has(self, construct_type: str) -> bool:
        return construct_type in self._constructs

    def list_constructs(self) -> list[str]:
        return sorted(self._constructs)

    # -- factory ------------------------------------------------------------

    @staticmethod
    def default() -> SPLConstructRegistry:
        """Build the default registry with all v5 initial constructs."""
        registry = SPLConstructRegistry()

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

        # -- REQUIRED_OUTPUT -------------------------------------------------
        registry.register(ConstructIRS(
            construct_type="REQUIRED_OUTPUT",
            existence_policy="source_signal_required",
            source_signals=["required_output", "output_contract"],
            partial_rendering_allowed=True,
            description=(
                "A named output the process is expected to produce. "
                "The output declaration can be rendered even when the producer "
                "is unknown."
            ),
            slots=[
                SlotSpec(
                    slot_name="output_name",
                    syntax_required=True,
                    required_for_partial=True,
                    required_for_complete=True,
                    evidence_kinds=["output_name", "output_contract"],
                ),
                SlotSpec(
                    slot_name="output_type",
                    syntax_required=False,
                    required_for_partial=False,
                    required_for_complete=False,
                    renderable_without=True,
                    evidence_kinds=["output_type", "output_description"],
                    can_be_inferred=True,
                ),
                SlotSpec(
                    slot_name="producer",
                    syntax_required=False,
                    required_for_complete=True,
                    renderable_without=True,
                    evidence_kinds=["producer_step", "handoff_output", "api_response"],
                    missing_diagnostic="missing_output_producer",
                    notes=(
                        "Must have a source-backed producer step, handoff, or API. "
                        "Missing producer is a completion diagnostic, not a reason "
                        "to synthesise a producer command."
                    ),
                ),
            ],
        ))

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
                ),
            ],
        ))

        # -- CALL_API --------------------------------------------------------
        registry.register(ConstructIRS(
            construct_type="CALL_API",
            existence_policy="source_signal_required",
            source_signals=["api_call_action", "tool_call_action", "connector_action"],
            partial_rendering_allowed=False,
            description=(
                "An executable API / tool / connector call.  Requires a named "
                "integration reference and explicit call-action evidence, not "
                "just a mention that an API exists."
            ),
            slots=[
                SlotSpec(
                    slot_name="api_name",
                    syntax_required=True,
                    required_for_complete=True,
                    evidence_kinds=["api_ref", "integration_ref"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="call_action",
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["call_action", "invoke_action"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes=(
                        "Distinguishes an integration *mention* from executable "
                        "call evidence.  Without an explicit call action the "
                        "construct should not become a rendered CALL_API."
                    ),
                ),
                SlotSpec(
                    slot_name="integration_evidence",
                    required_for_complete=True,
                    evidence_kinds=[
                        "api_ref",
                        "tool_ref",
                        "connector_ref",
                        "integration_ref",
                    ],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes=(
                        "Source context alone is not integration evidence. "
                        "A context-only mention must remain a resource "
                        "candidate, not a rendered CALL_API."
                    ),
                ),
                SlotSpec(
                    slot_name="response_binding",
                    required_for_complete=False,
                    evidence_kinds=["response", "output_variable"],
                ),
            ],
        ))

        # -- INVOKE_WORKER ---------------------------------------------------
        registry.register(ConstructIRS(
            construct_type="INVOKE_WORKER",
            existence_policy="source_signal_required",
            source_signals=["accepted_handoff", "delegated_subtask", "invoke_worker"],
            partial_rendering_allowed=False,
            description=(
                "A cross-worker invocation step.  Only materialised when a "
                "complete handoff (target worker + input/output bindings) exists."
            ),
            slots=[
                SlotSpec(
                    slot_name="target_worker",
                    syntax_required=True,
                    required_for_complete=True,
                    evidence_kinds=["worker_spec", "accepted_worker_boundary"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="handoff_id",
                    required_for_complete=True,
                    evidence_kinds=["worker_handoff"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="input_bindings",
                    required_for_complete=True,
                    evidence_kinds=["input_binding"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="output_bindings",
                    required_for_complete=True,
                    evidence_kinds=["output_binding"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
            ],
        ))

        # -- CHILD_WORKER ----------------------------------------------------
        registry.register(ConstructIRS(
            construct_type="CHILD_WORKER",
            existence_policy="source_signal_required",
            source_signals=["delegation", "subtask", "bounded_task", "worker_boundary"],
            partial_rendering_allowed=False,
            description=(
                "An independently callable sub-worker with a clear responsibility, "
                "input/output contract, invocation point, and result handoff."
            ),
            slots=[
                SlotSpec(
                    slot_name="responsibility",
                    required_for_partial=True,
                    required_for_complete=True,
                    evidence_kinds=["subtask_purpose", "delegated_responsibility"],
                ),
                SlotSpec(
                    slot_name="input_contract",
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["input_contract", "parent_binding"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="output_contract",
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["output_contract", "returned_result"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="invocation_point",
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["condition", "handoff_point"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="result_handoff",
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["output_binding", "result_binding"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
            ],
        ))

        # -- WORKER_CANDIDATE ------------------------------------------------
        registry.register(ConstructIRS(
            construct_type="WORKER_CANDIDATE",
            existence_policy="source_signal_required",
            source_signals=[
                "delegation",
                "subtask",
                "optional_subtask",
                "template_matching",
                "source_gathering",
            ],
            partial_rendering_allowed=False,
            no_demand_behavior="do_not_generate",
            description=(
                "A delegation mention that may warrant a child worker but lacks "
                "the full promotion criteria (contract, invocation point, handoff). "
                "Stays as a report / provenance trace; not rendered as SPL."
            ),
            slots=[
                SlotSpec(
                    slot_name="responsibility",
                    required_for_partial=True,
                    required_for_complete=True,
                    evidence_kinds=["subtask_purpose", "delegation_mention"],
                ),
                SlotSpec(
                    slot_name="promotion_input_contract",
                    required_for_complete=True,
                    renderable_without=True,
                    evidence_kinds=["input_contract"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes=(
                        "Emit type_or_contract_ambiguity only when source implies "
                        "executable delegation but the contract is incomplete."
                    ),
                ),
                SlotSpec(
                    slot_name="promotion_output_contract",
                    required_for_complete=True,
                    renderable_without=True,
                    evidence_kinds=["output_contract", "returned_result"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="promotion_invocation_point",
                    required_for_complete=True,
                    renderable_without=True,
                    evidence_kinds=["condition", "handoff_point"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
            ],
        ))

        return registry
