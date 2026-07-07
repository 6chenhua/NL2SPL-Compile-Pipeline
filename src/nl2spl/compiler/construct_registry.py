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
from nl2spl.compiler.irs.patch_type_meta import PatchTypeMeta

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

SlotActionability = Literal["editable", "non_editable", "optional_enrichment"]

NonEditableDisposition = Literal[
    "review_only",
    "deferred_validation",
    "developer_only",
    "non_repairable",
]

ActionabilityDecisionStatus = Literal["confirmed", "unresolved"]


@dataclass(frozen=True)
class SlotActionabilityDecision:
    """Explicit product decision for a slot that can produce a completion gap.

    This contract records whether the slot is user-actionable. It does not
    declare repair capability; editable slots still require a coherent
    RepairAffordanceSpec and runtime closure.
    """

    actionability: SlotActionability
    non_editable_disposition: NonEditableDisposition | None
    rationale_code: str
    decision_source_ref: str
    decision_status: ActionabilityDecisionStatus = "confirmed"

    def __post_init__(self) -> None:
        if self.actionability not in {
            "editable",
            "non_editable",
            "optional_enrichment",
        }:
            raise ValueError(f"Unknown actionability: {self.actionability}")
        if self.decision_status not in {"confirmed", "unresolved"}:
            raise ValueError(f"Unknown decision_status: {self.decision_status}")
        valid_dispositions = {
            "review_only",
            "deferred_validation",
            "developer_only",
            "non_repairable",
        }
        if (
            self.non_editable_disposition is not None
            and self.non_editable_disposition not in valid_dispositions
        ):
            raise ValueError(
                "Unknown non_editable_disposition: "
                f"{self.non_editable_disposition}"
            )
        if self.actionability == "non_editable":
            if self.non_editable_disposition is None:
                raise ValueError(
                    "non_editable actionability requires a non_editable_disposition"
                )
        elif self.non_editable_disposition is not None:
            raise ValueError(
                f"{self.actionability} actionability forbids non_editable_disposition"
            )
        if not isinstance(self.rationale_code, str) or not self.rationale_code.strip():
            raise ValueError("rationale_code cannot be blank")
        if not isinstance(self.decision_source_ref, str) or not self.decision_source_ref.strip():
            raise ValueError("decision_source_ref cannot be blank")


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
    materialization_plan_id: str | None = None
    selectable_ref_policy_id: str | None = None
    intent_schema_id: str | None = None
    required_context_facts: tuple[str, ...] = ()
    stage_authority: str | None = None
    notes: str | None = None
    patch_type_metadata: tuple[PatchTypeMeta, ...] = ()
    """Per-patch-type labels, descriptions, and verification lanes.
    When non-empty, the presentation layer derives individual strategy
    options from this tuple instead of combining ``supported_patch_types``
    into a single composite label."""
    repair_strategy_id: str | None = None


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
    actionability_decision: SlotActionabilityDecision | None = None
    """Repair capabilities for SPL Editing.  Default empty — slots without
    affordances are non-repairable in the MVP Diagnostics Console."""



    def requires_actionability_decision(self) -> bool:
        """Return whether this slot is in the mandatory audit scope."""
        return bool(
            self.required_for_partial
            or self.required_for_complete
            or self.missing_diagnostic is not None
            or self.repair_affordances
        )

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
                            description=(
                                "Insert a new producer step or bind an existing step "
                                "as the producer for a required output."
                            ),
                            supported_patch_types=("InsertProducerStep",),
                            default_patch_type="InsertProducerStep",
                            handler_id="missing_output_producer",
                            context_id="required_output_context",
                            target_resolver_id="required_output_target",
                            default_verification_lane="B",
                            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
                            materialization_plan_id="stage7.step_producer_repair.v1",
                            selectable_ref_policy_id="required_output.producer.selectable_refs.v1",
                            intent_schema_id="intent.insert_producer_step.v1",
                            required_context_facts=(
                                "target_output_name",
                                "worker_id",
                                "available_variables",
                                "nearby_steps",
                                "symbol_table",
                            ),
                            stage_authority="stage7.worker_step_plan",
                            repair_strategy_id="required_output.materialize_producer.v1",
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

        # -- API_DECLARATION --------------------------------------------------
        registry.register(ConstructIRS(
            construct_type="API_DECLARATION",
            existence_policy="source_signal_required",
            source_signals=[
                "api_candidate",
                "integration_hint",
                "configured_api",
                "api_resource_contract",
            ],
            no_demand_behavior="do_not_generate",
            partial_rendering_allowed=True,
            description="Declaration of an external API specification.",
            slots=[
                SlotSpec(
                    slot_name="api_name",
                    syntax_required=True,
                    required_for_partial=True,
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["api_name", "api_ref"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    repair_affordances=(),
                ),
                SlotSpec(
                    slot_name="source_evidence",
                    syntax_required=False,
                    required_for_partial=True,
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=[
                        "source_span",
                        "integration_hint",
                        "configured_resource",
                        "user_confirmed_repair",
                    ],
                    missing_diagnostic="type_or_contract_ambiguity",
                    repair_affordances=(),
                ),
                SlotSpec(
                    slot_name="authentication",
                    syntax_required=True,
                    required_for_partial=False,
                    required_for_complete=True,
                    renderable_without=True,
                    evidence_kinds=["auth_config", "explicit_auth"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    repair_affordances=(),
                ),
                SlotSpec(
                    slot_name="openapi_schema",
                    syntax_required=True,
                    required_for_partial=False,
                    required_for_complete=True,
                    renderable_without=True,
                    evidence_kinds=["openapi_schema", "schema_definition"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    repair_affordances=(),
                ),
                SlotSpec(
                    slot_name="functions",
                    syntax_required=True,
                    required_for_partial=False,
                    required_for_complete=True,
                    renderable_without=True,
                    evidence_kinds=["api_function", "function_definition"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    repair_affordances=(),
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
                "An executable API / tool / connector call. Requires a named "
                "integration reference, declared API reference, and explicit call-action evidence."
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
                    slot_name="declared_api_ref",
                    syntax_required=False,
                    required_for_complete=True,
                    evidence_kinds=["api_ref", "declared_api_ref"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes="Resolves to a gate-approved APISpec.",
                ),
                SlotSpec(
                    slot_name="call_action",
                    required_for_complete=True,
                    renderable_without=False,
                    evidence_kinds=["call_action", "invoke_action"],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes=(
                        "Distinguishes an integration *mention* from executable "
                        "call evidence. Without an explicit call action the "
                        "construct should not become a rendered CALL_API."
                    ),
                ),
                SlotSpec(
                    slot_name="request_bindings",
                    required_for_complete=False,
                    evidence_kinds=["request_binding", "input_binding"],
                ),
                SlotSpec(
                    slot_name="response_binding",
                    required_for_complete=False,
                    evidence_kinds=["response", "output_variable"],
                    notes=(
                        "May be satisfied by a single StepIR.outputs rendered "
                        "as a single structured RESPONSE COMMAND_RESULT."
                    ),
                ),
                SlotSpec(
                    slot_name="integration_evidence",
                    # Compatibility alias: does not participate in completion authority.
                    required_for_complete=False,
                    evidence_kinds=[
                        "api_ref",
                        "tool_ref",
                        "connector_ref",
                        "integration_ref",
                    ],
                    missing_diagnostic="type_or_contract_ambiguity",
                    notes=(
                        "Compatibility alias slot for snapshot/diagnostic tracing. "
                        "Source context alone is not integration evidence."
                    ),
                    repair_affordances=(
                        RepairAffordanceSpec(
                            affordance_id="call_api.specify_integration_evidence",
                            description=(
                                "Provide integration evidence (API/tool/connector ref) "
                                "for a CALL_API step."
                            ),
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
                            description=(
                                "Create a new worker handoff contract or bind an "
                                "existing one for an INVOKE_WORKER step."
                            ),
                            supported_patch_types=(
                                "CreateWorkerHandoffContract",
                                "BindExistingHandoff",
                            ),
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
            partial_rendering_allowed=True,
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
                    required_for_partial=False,
                    required_for_complete=True,
                    renderable_without=True,
                    evidence_kinds=["input_contract", "parent_binding"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="output_contract",
                    required_for_partial=False,
                    required_for_complete=True,
                    renderable_without=True,
                    evidence_kinds=["output_contract", "returned_result"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="invocation_point",
                    required_for_complete=True,
                    renderable_without=True,
                    evidence_kinds=["condition", "handoff_point"],
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="result_handoff",
                    required_for_complete=True,
                    renderable_without=True,
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
                                "User can define a complete child-worker closure or keep an "
                                "explicitly selected task in the main flow."
                            ),
                            supported_patch_types=(
                                "DefineChildWorkerClosure",
                                "ConvertDelegationIntentToMainFlowStep",
                            ),
                            default_patch_type="DefineChildWorkerClosure",
                            handler_id="type_or_contract_ambiguity",
                            context_id="worker_promotion_context",
                            target_resolver_id="worker_promotion_target",
                            default_verification_lane="B",
                            editable_artifacts=(
                                "WorkerPlanIR",
                                "WorkerFlowPlanIR",
                                "WorkerBlockPlanIR",
                                "WorkerStepPlanIR",
                                "SymbolTable",
                            ),
                            materialization_plan_id="worker_delegation.complete_closure.v2",
                            selectable_ref_policy_id="worker_promotion.handoff.selectable_refs.v1",
                            intent_schema_id="intent.worker_promotion_resolution.v1",
                            required_context_facts=(
                                "delegation_intent",
                                "worker_id",
                                "candidate_name",
                                "possible_inputs",
                                "possible_outputs",
                                "hierarchy_graph",
                            ),
                            stage_authority=(
                                "stage3_5.worker_boundary + stage4.worker_flow_plan + "
                                "stage5.worker_block_plan + stage7.worker_step_plan"
                            ),
                            repair_strategy_id="worker_delegation.complete_closure.v2",
                            patch_type_metadata=(),
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
                                "User can define a complete child-worker closure or keep an "
                                "explicitly selected task in the main flow."
                            ),
                            supported_patch_types=(
                                "DefineChildWorkerClosure",
                                "ConvertDelegationIntentToMainFlowStep",
                            ),
                            default_patch_type="DefineChildWorkerClosure",
                            handler_id="type_or_contract_ambiguity",
                            context_id="worker_promotion_context",
                            target_resolver_id="worker_promotion_target",
                            default_verification_lane="B",
                            editable_artifacts=(
                                "WorkerPlanIR",
                                "WorkerFlowPlanIR",
                                "WorkerBlockPlanIR",
                                "WorkerStepPlanIR",
                                "SymbolTable",
                            ),
                            materialization_plan_id="worker_delegation.complete_closure.v2",
                            selectable_ref_policy_id="worker_promotion.handoff.selectable_refs.v1",
                            intent_schema_id="intent.worker_promotion_resolution.v1",
                            required_context_facts=(
                                "delegation_intent",
                                "worker_id",
                                "candidate_name",
                                "possible_inputs",
                                "possible_outputs",
                                "hierarchy_graph",
                            ),
                            stage_authority=(
                                "stage3_5.worker_boundary + stage4.worker_flow_plan + "
                                "stage5.worker_block_plan + stage7.worker_step_plan"
                            ),
                            repair_strategy_id="worker_delegation.complete_closure.v2",
                            patch_type_metadata=(),
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
                                "User can define a complete child-worker closure or keep an "
                                "explicitly selected task in the main flow."
                            ),
                            supported_patch_types=(
                                "DefineChildWorkerClosure",
                                "ConvertDelegationIntentToMainFlowStep",
                            ),
                            default_patch_type="DefineChildWorkerClosure",
                            handler_id="type_or_contract_ambiguity",
                            context_id="worker_promotion_context",
                            target_resolver_id="worker_promotion_target",
                            default_verification_lane="B",
                            editable_artifacts=(
                                "WorkerPlanIR",
                                "WorkerFlowPlanIR",
                                "WorkerBlockPlanIR",
                                "WorkerStepPlanIR",
                                "SymbolTable",
                            ),
                            materialization_plan_id="worker_delegation.complete_closure.v2",
                            selectable_ref_policy_id="worker_promotion.handoff.selectable_refs.v1",
                            intent_schema_id="intent.worker_promotion_resolution.v1",
                            required_context_facts=(
                                "delegation_intent",
                                "worker_id",
                                "candidate_name",
                                "possible_inputs",
                                "possible_outputs",
                                "hierarchy_graph",
                            ),
                            stage_authority=(
                                "stage3_5.worker_boundary + stage4.worker_flow_plan + "
                                "stage5.worker_block_plan + stage7.worker_step_plan"
                            ),
                            repair_strategy_id="worker_delegation.complete_closure.v2",
                            patch_type_metadata=(),
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
                                "User can define a complete child-worker closure or keep an "
                                "explicitly selected task in the main flow."
                            ),
                            supported_patch_types=(
                                "DefineChildWorkerClosure",
                                "ConvertDelegationIntentToMainFlowStep",
                            ),
                            default_patch_type="DefineChildWorkerClosure",
                            handler_id="type_or_contract_ambiguity",
                            context_id="worker_promotion_context",
                            target_resolver_id="worker_promotion_target",
                            default_verification_lane="B",
                            editable_artifacts=(
                                "WorkerPlanIR",
                                "WorkerFlowPlanIR",
                                "WorkerBlockPlanIR",
                                "WorkerStepPlanIR",
                                "SymbolTable",
                            ),
                            materialization_plan_id="worker_delegation.complete_closure.v2",
                            selectable_ref_policy_id="worker_promotion.handoff.selectable_refs.v1",
                            intent_schema_id="intent.worker_promotion_resolution.v1",
                            required_context_facts=(
                                "delegation_intent",
                                "worker_id",
                                "candidate_name",
                                "possible_inputs",
                                "possible_outputs",
                                "hierarchy_graph",
                            ),
                            stage_authority=(
                                "stage3_5.worker_boundary + stage4.worker_flow_plan + "
                                "stage5.worker_block_plan + stage7.worker_step_plan"
                            ),
                            repair_strategy_id="worker_delegation.complete_closure.v2",
                            patch_type_metadata=(),
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
                            description=(
                                "Specify the target (to_worker or api_ref) for an "
                                "incomplete worker handoff."
                            ),
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
                            description=(
                                "Specify the invocation site for an incomplete "
                                "worker handoff."
                            ),
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

        _apply_default_actionability_decisions(registry)
        return registry
