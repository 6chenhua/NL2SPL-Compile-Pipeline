"""SPL Construct Registry — IRS data model for construct-level information requirements.

Defines the v5 IRS types (SlotSpec, ConstructIRS, SlotSatisfaction,
ConstructSatisfactionReport) and the SPLConstructRegistry that holds
the default construct definitions.

This module is pure data — no prompt wiring and no pipeline behaviour changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from nl2spl.compiler.irs.frontier import CutlineReason, FrontierStatus
from nl2spl.compiler.irs.graph import ConstructEdge

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


@dataclass(frozen=True)
class RepairAffordanceSpec:
    """Machine-readable repair capability declared by an IRS slot.

    Pure metadata — no callables, no class references, no LLM integration.
    SPL Editing reads these at runtime to derive the ``RepairCatalog``.

    Attributes:
        affordance_id: Globally unique ID for this repair capability.
            Naming convention: ``{construct_type_lower}.{descriptive_suffix}``
            (e.g. ``exception_flow.add_handler_step``,
            ``worker_promotion.resolve_contract``).
            Used as a stable key in logs, overlays, API payloads, and
            ``RepairCatalogEntry`` derivation — must never be reused
            across different construct+slot combinations.
        description: Human-readable summary of the repair.
        supported_patch_types: Allowed ``patch_type`` values the LLM may
            propose for this slot.
        default_patch_type: Default patch type when the user doesn't choose.
        handler_id: Identifies the ``IssueRepairHandler`` to invoke.
        context_id: Identifies the ``RepairContextBuilder``.
        target_resolver_id: Identifies the ``IssueTargetResolver``.
        default_verification_lane: ``"A"`` (Assembler Replay) or ``"B"``
            (Normalizer Replay).
        editable_artifacts: Stage-level IR artifact class names the patch
            applier may modify.
        required_evidence_kind: Evidence kind required for apply
            (always ``"user_confirmed_repair"`` in MVP).
        user_facing: Whether this affordance is exposed in the Diagnostics
            Console UI.
        notes: Internal design notes — not used by the runtime.
    """

    affordance_id: str
    description: str
    supported_patch_types: tuple[str, ...] = ()
    default_patch_type: str | None = None
    handler_id: str | None = None
    context_id: str | None = None
    target_resolver_id: str | None = None
    default_verification_lane: str = "A"
    editable_artifacts: tuple[str, ...] = ()
    required_evidence_kind: str = "user_confirmed_repair"
    user_facing: bool = True
    notes: str | None = None


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
    repair_affordances: tuple[RepairAffordanceSpec, ...] = ()
    """Repair capabilities for SPL Editing.  Default empty — slots without
    affordances are non-repairable in the MVP Diagnostics Console."""


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
    diagnostic_target_ref: str | None = None
    diagnostic_required_for: str | None = None
    diagnostic_blocks_rendering: bool | None = None
    suggested_resolution: str | None = None


@dataclass
class ConstructSatisfactionReport:
    """Slot-level satisfaction report for one materialised construct.

    IRS v6 extensions:
        primary_parent_id: Main containment parent construct ID
        child_construct_ids: Direct child construct IDs
        related_edges: Non-tree relationships (produces, invokes, etc.)
        construct_path: Hierarchical path for reporting
        source_span_ids: Source spans supporting this construct
        source_section_id: Source section ID
        source_packet_id: Source packet ID
        cutline_reason: Why recursive checking stopped
        frontier_status: Traversal control for future recursive checking
        metadata: Additional construct metadata
    """

    construct_id: str
    construct_type: str
    slots: list[SlotSatisfaction]
    completeness: ConstructCompleteness
    renderable: bool
    diagnostics: list = field(default_factory=list)
    # IRS v6 extensions - all have defaults for backward compatibility
    primary_parent_id: str | None = None
    child_construct_ids: list[str] = field(default_factory=list)
    related_edges: list[ConstructEdge] = field(default_factory=list)
    construct_path: tuple[str, ...] = ()
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    cutline_reason: CutlineReason | None = None
    frontier_status: FrontierStatus = "leaf"
    metadata: dict[str, Any] = field(default_factory=dict)


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
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="exception_flow.add_handler_step",
                            description="Add a handler step to an exception flow that has a condition but no handler action.",
                            supported_patch_types=("AddExceptionHandlerStep",),
                            default_patch_type="AddExceptionHandlerStep",
                            handler_id="missing_handler",
                            context_id="exception_flow_context",
                            target_resolver_id="exception_flow_target",
                            default_verification_lane="A",
                            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
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
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="required_output.insert_or_bind_producer",
                            description="Insert a new producer step or bind an existing step as the producer for a required output.",
                            supported_patch_types=("InsertProducerStep", "BindExistingProducerStep"),
                            default_patch_type="InsertProducerStep",
                            handler_id="missing_output_producer",
                            context_id="required_output_context",
                            target_resolver_id="required_output_target",
                            default_verification_lane="A",
                            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
                        ),
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
                    notes=(
                        "May be satisfied by one or more StepIR.outputs rendered "
                        "as a COMMAND_RESULTS list."
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
                        "May target one or more StepIR.outputs rendered as a "
                        "VALUE COMMAND_RESULTS list."
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
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="call_api.specify_integration_evidence",
                            description="Provide integration evidence (API/tool/connector ref) for a CALL_API step.",
                            supported_patch_types=("SpecifyAPIIntegration",),
                            default_patch_type="SpecifyAPIIntegration",
                            handler_id="type_or_contract_ambiguity",
                            context_id="call_api_context",
                            target_resolver_id="step_target",
                            default_verification_lane="A",
                            editable_artifacts=("WorkerStepPlanIR",),
                        ),
                    ),
                ),
                SlotSpec(
                    slot_name="response_binding",
                    required_for_complete=False,
                    evidence_kinds=["response", "output_variable"],
                    notes=(
                        "May be satisfied by one or more StepIR.outputs rendered "
                        "as a RESPONSE COMMAND_RESULTS list."
                    ),
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
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="invoke_worker.specify_target_worker",
                            description="Specify the target worker for an INVOKE_WORKER step.",
                            supported_patch_types=("SpecifyInvokeTarget",),
                            default_patch_type="SpecifyInvokeTarget",
                            handler_id="type_or_contract_ambiguity",
                            context_id="invoke_worker_context",
                            target_resolver_id="step_target",
                            default_verification_lane="A",
                            editable_artifacts=("WorkerStepPlanIR",),
                        ),
                    ),
                ),
                SlotSpec(
                    slot_name="handoff_id",
                    required_for_complete=True,
                    evidence_kinds=["worker_handoff"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="invoke_worker.create_or_bind_handoff",
                            description="Create a new worker handoff contract or bind an existing one for an INVOKE_WORKER step.",
                            supported_patch_types=("CreateWorkerHandoffContract", "BindExistingHandoff"),
                            default_patch_type="CreateWorkerHandoffContract",
                            handler_id="type_or_contract_ambiguity",
                            context_id="invoke_worker_context",
                            target_resolver_id="step_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerPlanIR", "WorkerHandoffIR"),
                        ),
                    ),
                ),
                SlotSpec(
                    slot_name="input_bindings",
                    required_for_complete=True,
                    evidence_kinds=["input_binding"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="invoke_worker.specify_input_bindings",
                            description="Specify input bindings for a worker handoff.",
                            supported_patch_types=("UpdateHandoffContract",),
                            default_patch_type="UpdateHandoffContract",
                            handler_id="type_or_contract_ambiguity",
                            context_id="handoff_context",
                            target_resolver_id="handoff_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerHandoffIR",),
                        ),
                    ),
                ),
                SlotSpec(
                    slot_name="output_bindings",
                    required_for_complete=True,
                    evidence_kinds=["output_binding"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="invoke_worker.specify_output_bindings",
                            description="Specify output bindings for a worker handoff.",
                            supported_patch_types=("UpdateHandoffContract",),
                            default_patch_type="UpdateHandoffContract",
                            handler_id="type_or_contract_ambiguity",
                            context_id="handoff_context",
                            target_resolver_id="handoff_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerHandoffIR",),
                        ),
                    ),
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
                    required_for_partial=True,
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["input_contract", "parent_binding"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="output_contract",
                    required_for_partial=True,
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
                "A delegation mention identified as a candidate task boundary. "
                "Represents that a candidate boundary exists, not whether it can "
                "be promoted to a child worker. Stays as a report / provenance trace; "
                "not rendered as SPL."
            ),
            slots=[
                SlotSpec(
                    slot_name="responsibility",
                    required_for_partial=True,
                    required_for_complete=True,
                    evidence_kinds=["subtask_purpose", "delegation_mention"],
                ),
                SlotSpec(
                    slot_name="delegation_signal",
                    required_for_complete=True,
                    evidence_kinds=["delegation_signal", "candidate_kind"],
                ),
                SlotSpec(
                    slot_name="source_evidence",
                    required_for_complete=True,
                    evidence_kinds=["source_span", "candidate_source"],
                ),
            ],
        ))

        # -- WORKER_PROMOTION ------------------------------------------------
        registry.register(ConstructIRS(
            construct_type="WORKER_PROMOTION",
            existence_policy="source_signal_required",
            source_signals=[
                "delegation",
                "subtask",
                "explicit_delegation",
            ],
            partial_rendering_allowed=False,
            no_demand_behavior="do_not_generate",
            description=(
                "Promotion readiness assessment for a worker candidate. "
                "Expresses whether a candidate has the necessary conditions "
                "(contract, invocation point, handoff) to be promoted to a child worker. "
                "This is an analysis construct, not a renderable SPL construct."
            ),
            slots=[
                SlotSpec(
                    slot_name="promotion_input_contract",
                    required_for_partial=True,
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["input_contract", "possible_inputs"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes=(
                        "Satisfied when possible_inputs is non-empty and risks "
                        "does not contain no_clear_input_contract."
                    ),
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="worker_promotion.resolve_contract",
                            description=(
                                "Resolve a delegation-intent-sourced WORKER_PROMOTION gap. "
                                "User can confirm delegation (create handoff contract), "
                                "convert to a main-flow step, or convert to a user-prompt step."
                            ),
                            supported_patch_types=(
                                "CreateWorkerHandoffContract",
                                "ConvertDelegationIntentToMainFlowStep",
                                "ConvertDelegationIntentToRequestInput",
                            ),
                            default_patch_type="CreateWorkerHandoffContract",
                            handler_id="type_or_contract_ambiguity",
                            context_id="worker_promotion_context",
                            target_resolver_id="worker_promotion_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerPlanIR", "WorkerHandoffIR", "WorkerStepPlanIR"),
                            notes=(
                                "delegation-intent-sourced WORKER_PROMOTION gap. "
                                "All four promotion slots share the same repair "
                                "strategy set; the specific missing slots control "
                                "what the patch payload must provide."
                            ),
                        ),
                    ),
                ),
                SlotSpec(
                    slot_name="promotion_output_contract",
                    required_for_partial=True,
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["output_contract", "possible_outputs"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes=(
                        "Satisfied when possible_outputs is non-empty and risks "
                        "does not contain no_clear_output_contract."
                    ),
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="worker_promotion.resolve_contract",
                            description=(
                                "Resolve a delegation-intent-sourced WORKER_PROMOTION gap. "
                                "User can confirm delegation (create handoff contract), "
                                "convert to a main-flow step, or convert to a user-prompt step."
                            ),
                            supported_patch_types=(
                                "CreateWorkerHandoffContract",
                                "ConvertDelegationIntentToMainFlowStep",
                                "ConvertDelegationIntentToRequestInput",
                            ),
                            default_patch_type="CreateWorkerHandoffContract",
                            handler_id="type_or_contract_ambiguity",
                            context_id="worker_promotion_context",
                            target_resolver_id="worker_promotion_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerPlanIR", "WorkerHandoffIR", "WorkerStepPlanIR"),
                        ),
                    ),
                ),
                SlotSpec(
                    slot_name="promotion_invocation_point",
                    required_for_partial=True,
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["invocation_point", "handoff_point"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes=(
                        "Satisfied when risks does not contain no_parent_invocation_point "
                        "and there is evidence of where to invoke the worker."
                    ),
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="worker_promotion.resolve_contract",
                            description=(
                                "Resolve a delegation-intent-sourced WORKER_PROMOTION gap. "
                                "User can confirm delegation (create handoff contract), "
                                "convert to a main-flow step, or convert to a user-prompt step."
                            ),
                            supported_patch_types=(
                                "CreateWorkerHandoffContract",
                                "ConvertDelegationIntentToMainFlowStep",
                                "ConvertDelegationIntentToRequestInput",
                            ),
                            default_patch_type="CreateWorkerHandoffContract",
                            handler_id="type_or_contract_ambiguity",
                            context_id="worker_promotion_context",
                            target_resolver_id="worker_promotion_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerPlanIR", "WorkerHandoffIR", "WorkerStepPlanIR"),
                        ),
                    ),
                ),
                SlotSpec(
                    slot_name="promotion_result_handoff",
                    required_for_partial=True,
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["result_handoff", "output_binding"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes=(
                        "Satisfied when risks does not contain unclear_result_handoff "
                        "and there is a matching handoff with output_bindings."
                    ),
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="worker_promotion.resolve_contract",
                            description=(
                                "Resolve a delegation-intent-sourced WORKER_PROMOTION gap. "
                                "User can confirm delegation (create handoff contract), "
                                "convert to a main-flow step, or convert to a user-prompt step."
                            ),
                            supported_patch_types=(
                                "CreateWorkerHandoffContract",
                                "ConvertDelegationIntentToMainFlowStep",
                                "ConvertDelegationIntentToRequestInput",
                            ),
                            default_patch_type="CreateWorkerHandoffContract",
                            handler_id="type_or_contract_ambiguity",
                            context_id="worker_promotion_context",
                            target_resolver_id="worker_promotion_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerPlanIR", "WorkerHandoffIR", "WorkerStepPlanIR"),
                        ),
                    ),
                ),
            ],
        ))

        # -- WORKER_HANDOFF --------------------------------------------------
        registry.register(ConstructIRS(
            construct_type="WORKER_HANDOFF",
            existence_policy="source_signal_required",
            source_signals=[
                "worker_handoff",
                "worker_invocation",
                "api_call",
            ],
            partial_rendering_allowed=False,
            no_demand_behavior="do_not_generate",
            description=(
                "A materialized worker handoff representing data flow and invocation "
                "between workers or from worker to API. Expresses whether the handoff "
                "has complete contract bindings."
            ),
            slots=[
                SlotSpec(
                    slot_name="from_worker",
                    required_for_complete=True,
                    evidence_kinds=["from_worker"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="target",
                    required_for_complete=True,
                    evidence_kinds=["to_worker", "api_ref"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes=(
                        "For mode='invoke', uses to_worker. "
                        "For mode='api_call', uses api_ref."
                    ),
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="worker_handoff.specify_target",
                            description="Specify the target (to_worker or api_ref) for an incomplete worker handoff.",
                            supported_patch_types=("UpdateHandoffContract",),
                            default_patch_type="UpdateHandoffContract",
                            handler_id="type_or_contract_ambiguity",
                            context_id="handoff_context",
                            target_resolver_id="handoff_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerHandoffIR",),
                        ),
                    ),
                ),
                SlotSpec(
                    slot_name="input_bindings",
                    required_for_complete=True,
                    evidence_kinds=["input_binding"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="worker_handoff.specify_input_bindings",
                            description="Specify input bindings for an incomplete worker handoff.",
                            supported_patch_types=("UpdateHandoffContract",),
                            default_patch_type="UpdateHandoffContract",
                            handler_id="type_or_contract_ambiguity",
                            context_id="handoff_context",
                            target_resolver_id="handoff_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerHandoffIR",),
                        ),
                    ),
                ),
                SlotSpec(
                    slot_name="output_bindings",
                    required_for_complete=True,
                    evidence_kinds=["output_binding"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="worker_handoff.specify_output_bindings",
                            description="Specify output bindings for an incomplete worker handoff.",
                            supported_patch_types=("UpdateHandoffContract",),
                            default_patch_type="UpdateHandoffContract",
                            handler_id="type_or_contract_ambiguity",
                            context_id="handoff_context",
                            target_resolver_id="handoff_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerHandoffIR",),
                        ),
                    ),
                ),
                SlotSpec(
                    slot_name="invocation_site",
                    required_for_complete=True,
                    evidence_kinds=["invoke_location_hint"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes=(
                        "Uses invoke_location_hint structured fields: "
                        "after_span_id, before_span_id, block_hint (non-unknown), "
                        "or handoff-level condition_text. "
                        "Does NOT use ordering (required Literal) as evidence."
                    ),
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="worker_handoff.specify_invocation_site",
                            description="Specify the invocation site for an incomplete worker handoff.",
                            supported_patch_types=("UpdateHandoffContract",),
                            default_patch_type="UpdateHandoffContract",
                            handler_id="type_or_contract_ambiguity",
                            context_id="handoff_context",
                            target_resolver_id="handoff_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerHandoffIR",),
                        ),
                    ),
                ),
            ],
        ))

        # R10: DELEGATION_INTENT removed — delegation_intent is a source
        # signal / evidence routed through WORKER_CANDIDATE / WORKER_PROMOTION.

        # -- RESOURCE_CONTRACT_DEMAND -----------------------------------------
        registry.register(ConstructIRS(
            construct_type="RESOURCE_CONTRACT_DEMAND",
            existence_policy="source_signal_required",
            source_signals=["input_contract", "output_contract", "resource_contract"],
            partial_rendering_allowed=True,
            description=(
                "A source-demanded resource contract (input or output). "
                "The demand itself is satisfied when a Stage 6 resource_contracts "
                "entry materializes it with a matching demand_id."
            ),
            slots=[
                SlotSpec(
                    slot_name="materialization",
                    syntax_required=True,
                    required_for_partial=True,
                    required_for_complete=True,
                    evidence_kinds=["resource_contract_binding"],
                    missing_diagnostic="missing_resource_contract",
                    notes=(
                        "The demand must have at least one "
                        "ResourceContractBindingIR with a matching demand_id."
                    ),
                ),
                SlotSpec(
                    slot_name="resource_registry",
                    syntax_required=False,
                    required_for_partial=False,
                    required_for_complete=True,
                    evidence_kinds=["resource_contract_field"],
                    missing_diagnostic="resource_kind_mismatch",
                    notes=(
                        "Every ResourceContractBindingIR must point to a "
                        "materialized resource in the matching registry "
                        "collection (variables/files/apis/types)."
                    ),
                ),
                SlotSpec(
                    slot_name="producer",
                    syntax_required=False,
                    required_for_partial=False,
                    required_for_complete=True,
                    evidence_kinds=["producer_index"],
                    missing_diagnostic="missing_output_producer",
                    notes=(
                        "Required output demands need a renderable producer "
                        "of the same resource name and resource kind. "
                        "Declarations alone do not count as producers."
                    ),
                ),
            ],
        ))

        return registry
