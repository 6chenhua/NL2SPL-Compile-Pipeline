"""LLM Repair Context core DTOs (Phase L0).

All DTOs are frozen dataclasses.  No construct-specific union types.
Extension facts are schema-validated at the boundary (not loose dicts).

Design rule: this module MUST NOT import handler, patch, LLM client,
or verification modules.  It is pure data projection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

# ---------------------------------------------------------------------------
# Scalar value types
# ---------------------------------------------------------------------------

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

# ---------------------------------------------------------------------------
# Generation readiness states
# ---------------------------------------------------------------------------

GenerationStatus = Literal[
    "ready",
    "ready_low_confidence",
    "generation_blocked",
    "repair_unavailable",
]

BlockingAuthority = Literal[
    "repair_catalog",
    "patch_registry",
    "target_resolver",
    "context_provider",
    "patch_precondition",
] | None

ContextConfidence = Literal["high", "medium", "low"]

ExtensionRole = Literal["primary", "auxiliary"]

# ---------------------------------------------------------------------------
# Evidence / renderability status for StepSummary
# ---------------------------------------------------------------------------

StepEvidenceStatus = Literal[
    "source_backed",
    "user_confirmed_repair",
    "handoff_backed",
    "compiler_synthetic",
    "assumed",
]

SelectableKind = Literal[
    "worker",
    "step",
    "flow",
    "block",
    "output",
    "variable",
    "invocation_location",
    "resource",
    "handoff",
]


# =============================================================================
# Core facts DTOs — stable common context
# =============================================================================


@dataclass(frozen=True)
class IssueFacts:
    """User-facing issue summary — never raw diagnostic.message."""

    issue_category: str
    user_facing_title: str
    what_was_detected: str
    missing_items: tuple[str, ...]
    why_it_matters: str | None = None
    suggested_resolution: str | None = None
    repairability: str = "editable"


@dataclass(frozen=True)
class SourceFacts:
    """Source excerpt and metadata.

    ``source_span_ids_internal`` MUST NOT appear in business prompt sections.
    """

    primary_source_excerpt: str | None = None
    related_source_excerpts: tuple[str, ...] = ()
    source_section_label: str | None = None
    user_repair_instruction: str | None = None
    source_span_ids_internal: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetFacts:
    """Structured target construct facts."""

    construct_type: str
    slot_name: str
    construct_role: str | None = None
    human_readable_target_summary: str = ""
    current_construct_state: Mapping[str, JsonValue] = field(default_factory=dict)
    parent_construct_summary: str | None = None


@dataclass(frozen=True)
class StepSummary:
    """Lightweight summary of one workflow step."""

    step_id_internal: str
    text: str
    command_type: str
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    flow_ref_internal: str | None = None
    block_ref_internal: str | None = None
    evidence_status: StepEvidenceStatus = "assumed"
    renderability_status: str | None = None


@dataclass(frozen=True)
class WorkflowFacts:
    """Local workflow context around the repair target."""

    worker_name: str | None = None
    worker_purpose: str | None = None
    flow_kind: str | None = None
    nearby_steps: tuple[StepSummary, ...] = ()
    available_inputs: tuple[str, ...] = ()
    available_outputs: tuple[str, ...] = ()
    available_variables: tuple[str, ...] = ()
    already_produced_variables: tuple[str, ...] = ()
    required_outputs_still_missing: tuple[str, ...] = ()
    relevant_constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArtifactFacts:
    """Artifact-level compilation context."""

    worker_count: int = 0
    child_worker_names: tuple[str, ...] = ()
    declared_apis: tuple[str, ...] = ()
    available_handoff_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepairActionFacts:
    """Facts about the selected repair action.

    Entirely derived from RepairCatalog / PatchRegistry / TargetResolver.
    Must NOT declare new patch capabilities.
    """

    affordance_id: str
    selected_patch_type: str
    patch_payload_schema: Mapping[str, JsonValue] = field(default_factory=dict)
    allowed_command_types: tuple[str, ...] = ()
    allowed_variable_names: tuple[str, ...] = ()
    allowed_worker_ids: tuple[str, ...] = ()
    allowed_step_ids: tuple[str, ...] = ()
    allowed_output_names: tuple[str, ...] = ()
    selectable_references: tuple["SelectableReference", ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    verification_lane: str = "A"


@dataclass(frozen=True)
class SafetyFacts:
    """Safety rules injected into every LLM prompt."""

    do_not_invent_facts: bool = True
    do_not_use_internal_ids_in_text: bool = True
    user_confirmed_repair_required: bool = True
    typed_patch_only: bool = True
    no_direct_spl_modification: bool = True
    additional_rules: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreviousSuggestionFacts:
    """Summaries of previously generated suggestions to avoid duplicates."""

    previous_summaries: tuple[str, ...] = ()
    max_previous_to_show: int = 10


@dataclass(frozen=True)
class InternalRoutingFacts:
    """Routing ids for backend — MUST NOT enter business prompt sections."""

    diagnostic_id: str = ""
    target_ref: str = ""
    irs_ref: Mapping[str, JsonValue] = field(default_factory=dict)
    worker_id: str | None = None
    flow_id: str | None = None
    block_id: str | None = None
    step_id: str | None = None
    construct_id: str | None = None
    allowed_ids: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


# =============================================================================
# SelectableReference — id + business summary
# =============================================================================


@dataclass(frozen=True)
class SelectableReference:
    """An internal id that the LLM may use in a JSON payload field.

    The ``id`` may appear in the "internal allowed ids" section of the
    prompt, but MUST NOT appear in title / explanation / handler_text /
    producer_text / user-visible preview.
    """

    id: str
    label: str
    summary: str
    kind: SelectableKind
    payload_field: str
    business_summary: Mapping[str, JsonValue] = field(default_factory=dict)


# =============================================================================
# Context quality and generation readiness
# =============================================================================


@dataclass(frozen=True)
class ContextQuality:
    """Quality assessment of the gathered repair context."""

    confidence: ContextConfidence
    has_primary_business_fact: bool = False
    has_source_excerpt: bool = False
    has_workflow_context: bool = False
    has_selectable_references: bool = False
    missing_context_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class GenerationReadiness:
    """Gate control for whether to invoke the LLM."""

    status: GenerationStatus
    reasons: tuple[str, ...] = ()
    missing_required_facts: tuple[str, ...] = ()
    blocking_authority: BlockingAuthority = None


# =============================================================================
# LLMRepairContextExtension — affordance-scoped extension
# =============================================================================


@dataclass(frozen=True)
class LLMRepairContextExtension:
    """Affordance-scoped extension carrying schema-validated facts.

    One primary extension per repair, plus zero or more auxiliary extensions.
    """

    extension_id: str
    provider_id: str

    role: ExtensionRole

    affordance_id: str
    construct_type: str
    slot_name: str
    diagnostic_kind: str
    patch_type: str

    facts_schema_id: str
    facts_schema_version: str
    facts_schema: Mapping[str, JsonValue] = field(default_factory=dict)
    facts: Mapping[str, JsonValue] = field(default_factory=dict)

    required_fact_keys: tuple[str, ...] = ()
    optional_fact_keys: tuple[str, ...] = ()

    renderer_id: str = ""
    quality: ContextQuality = field(
        default_factory=lambda: ContextQuality(confidence="low"),
    )


# =============================================================================
# LLMRepairContext — top-level projection
# =============================================================================


@dataclass(frozen=True)
class LLMRepairContext:
    """Top-level runtime projection of backend state for LLM consumption.

    Does NOT contain:
      - Construct-specific union (ExceptionFlowFacts | RequiredOutputFacts | ...)
      - RepairCatalog mutable reference
      - PatchBundle mutable reference
      - CompileDiagnostic raw object
      - RepairPatch raw object
      - LLM client reference
    """

    context_id: str
    session_id: str

    issue_facts: IssueFacts
    source_facts: SourceFacts
    target_facts: TargetFacts
    workflow_facts: WorkflowFacts
    artifact_facts: ArtifactFacts = field(default_factory=ArtifactFacts)
    repair_action_facts: RepairActionFacts = field(
        default_factory=lambda: RepairActionFacts(
            affordance_id="", selected_patch_type="",
        ),
    )
    safety_facts: SafetyFacts = field(default_factory=SafetyFacts)
    previous_suggestion_facts: PreviousSuggestionFacts = field(
        default_factory=PreviousSuggestionFacts,
    )

    internal_routing: InternalRoutingFacts = field(
        default_factory=InternalRoutingFacts,
    )

    primary_extension: LLMRepairContextExtension = field(
        default_factory=lambda: LLMRepairContextExtension(
            extension_id="", provider_id="",
            role="primary",
            affordance_id="", construct_type="", slot_name="",
            diagnostic_kind="", patch_type="",
            facts_schema_id="", facts_schema_version="",
        ),
    )
    auxiliary_extensions: tuple[LLMRepairContextExtension, ...] = ()

    quality: ContextQuality = field(
        default_factory=lambda: ContextQuality(confidence="low"),
    )
    generation_readiness: GenerationReadiness = field(
        default_factory=lambda: GenerationReadiness(status="repair_unavailable"),
    )
