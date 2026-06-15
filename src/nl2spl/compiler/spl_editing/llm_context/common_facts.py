"""Common facts builders (Phase L2).

Each builder extracts from structured backend state — NEVER from:
  - raw diagnostic.message regex
  - target_ref string parsing
  - feedback_report.md / compile_report.txt / final_spl.txt
  - stage*.json debug artifacts
"""

from __future__ import annotations

from typing import Any, Mapping

from nl2spl.compiler.spl_editing.llm_context.model import (
    ArtifactFacts,
    InternalRoutingFacts,
    IssueFacts,
    PreviousSuggestionFacts,
    RepairActionFacts,
    SafetyFacts,
    SelectableReference,
    SourceFacts,
    StepSummary,
    TargetFacts,
    WorkflowFacts,
    StepEvidenceStatus,
)
from nl2spl.compiler.spl_editing.llm_context.selectable import (
    build_step_reference,
)


# =============================================================================
# IssueFacts
# =============================================================================


def build_issue_facts(
    issue: Any,  # EditableIssue
    presentation_view: Any | None = None,  # IssuePresentationView
) -> IssueFacts:
    """Build IssueFacts from the editable issue and optional presentation."""
    user_facing_title = ""
    what_detected = ""
    if presentation_view is not None:
        user_facing_title = getattr(presentation_view, "user_facing_title", "") or ""
        what_detected = getattr(presentation_view, "what_was_detected", "") or ""
    if not user_facing_title:
        user_facing_title = getattr(issue, "kind", "unknown") or "unknown"
    if not what_detected:
        # Use structured fields only — never raw diagnostic.message
        what_detected = getattr(issue, "suggested_resolution", "") or ""

    return IssueFacts(
        issue_category=getattr(issue, "kind", "unknown") or "unknown",
        user_facing_title=user_facing_title,
        what_was_detected=what_detected,
        missing_items=(getattr(issue, "missing_slot", "") or "",),
        suggested_resolution=getattr(issue, "suggested_resolution", None) or None,
        repairability=(
            "editable" if getattr(issue, "repairable", False) else "non_repairable"
        ),
    )


# =============================================================================
# SourceFacts
# =============================================================================


def build_source_facts(
    issue: Any,
    source_spans: tuple[Any, ...] = (),
    user_instruction: str | None = None,
) -> SourceFacts:
    """Build SourceFacts from source spans and user instruction."""
    span_ids = tuple(
        getattr(s, "span_id", "") or getattr(s, "id", "") or ""
        for s in source_spans
        if s is not None
    )
    # Source excerpt from spans
    excerpts: list[str] = []
    for s in source_spans[:3]:  # limit to 3 spans
        if s is not None:
            text = getattr(s, "text", "") or ""
            if text:
                excerpts.append(str(text))

    return SourceFacts(
        primary_source_excerpt=excerpts[0] if excerpts else None,
        related_source_excerpts=tuple(excerpts[1:]) if len(excerpts) > 1 else (),
        source_section_label=None,
        user_repair_instruction=user_instruction,
        source_span_ids_internal=span_ids,
    )


# =============================================================================
# TargetFacts
# =============================================================================


def build_target_facts(
    issue: Any,
    target: Any,  # RepairTarget
    artifact_snapshot: Any | None = None,
) -> TargetFacts:
    """Build TargetFacts from the repair target and snapshot."""
    construct_type = ""
    slot_name = ""
    if target is not None:
        irs_ref = getattr(target, "irs_ref", None)
        if irs_ref is not None:
            construct_type = getattr(irs_ref, "construct_type", "") or ""
            slot_name = getattr(irs_ref, "slot_name", "") or ""

    # Human-readable summary — never use target_ref or raw message as business text
    summary = (
        getattr(issue, "suggested_resolution", "")
        or f"{construct_type} missing {slot_name}"
    )

    return TargetFacts(
        construct_type=construct_type,
        slot_name=slot_name,
        construct_role=None,
        human_readable_target_summary=str(summary),
        parent_construct_summary=None,
    )


# =============================================================================
# WorkflowFacts
# =============================================================================


def build_workflow_facts(
    artifact_snapshot: Any | None = None,
    target: Any | None = None,
) -> WorkflowFacts:
    """Build WorkflowFacts from snapshot and target."""
    worker_name = None
    worker_purpose = None
    nearby_steps: list[StepSummary] = []
    available_outputs: list[str] = []
    available_inputs: list[str] = []

    if artifact_snapshot is not None:
        # Worker info from plan
        worker_plan = getattr(artifact_snapshot, "worker_plan", None)
        parent_wid = getattr(target, "worker_id", None) if target else None
        if worker_plan is not None and parent_wid:
            for w in getattr(worker_plan, "workers", []):
                if getattr(w, "worker_id", None) == parent_wid:
                    worker_name = getattr(w, "worker_name", None)
                    worker_purpose = getattr(w, "purpose", None)
                    break

        # Nearby steps from step plan
        step_plan = getattr(artifact_snapshot, "worker_step_plan", None)
        if step_plan is not None:
            wid = parent_wid or "worker_main"
            steps = getattr(step_plan, "worker_steps", {}).get(wid, [])
            for s in steps[:5]:
                evidence: StepEvidenceStatus = (
                    "source_backed" if getattr(s, "source_span_ids", None)
                    else "assumed"
                )
                nearby_steps.append(StepSummary(
                    step_id_internal=getattr(s, "step_id", ""),
                    text=getattr(s, "text", ""),
                    command_type=getattr(s, "command_type", "GENERAL_COMMAND"),
                    outputs=tuple(getattr(s, "outputs", [])),
                    inputs=tuple(getattr(s, "inputs", [])),
                    evidence_status=evidence,
                ))
                for o in getattr(s, "outputs", []):
                    if o and o not in available_outputs:
                        available_outputs.append(o)
                for i in getattr(s, "inputs", []):
                    if i and i not in available_inputs:
                        available_inputs.append(i)

    # Available variables = inputs + outputs
    available_vars = list(dict.fromkeys(available_inputs + available_outputs))

    return WorkflowFacts(
        worker_name=worker_name,
        worker_purpose=worker_purpose,
        nearby_steps=tuple(nearby_steps),
        available_inputs=tuple(available_inputs),
        available_outputs=tuple(available_outputs),
        available_variables=tuple(available_vars),
    )


# =============================================================================
# RepairActionFacts
# =============================================================================


def build_repair_action_facts(
    *,
    affordance_id: str,
    selected_patch_type: str,
    patch_registry: Any | None = None,
    catalog_entry: Any | None = None,
    verification_lane: str = "A",
) -> RepairActionFacts:
    """Build RepairActionFacts from RepairCatalog / PatchRegistry.

    Allowed command types and other constraints are derived from the
    catalog entry and patch registry when available.
    """
    # Derive from catalog entry — NO hardcoded defaults
    allowed_cmd_types: tuple[str, ...] = ()
    if catalog_entry is not None:
        allowed_cmd_types = tuple(
            getattr(catalog_entry, "supported_command_types", ()) or ()
        )
    # When catalog entry provides no command types, leave empty.
    # The renderer will omit the "allowed command types" section
    # and the LLM must rely on the system prompt for this guidance.

    # Derive payload schema from patch registry
    patch_schema: dict = {}
    if patch_registry is not None and hasattr(patch_registry, "get"):
        bundle = patch_registry.get(selected_patch_type) if hasattr(patch_registry, "get") else None
        if bundle is not None:
            validator = getattr(bundle, "validator", None)
            if validator is not None and hasattr(validator, "payload_schema"):
                patch_schema = dict(getattr(validator, "payload_schema", {}) or {})

    lane = verification_lane
    if catalog_entry is not None:
        lane = getattr(catalog_entry, "default_verification_lane", None) or lane

    return RepairActionFacts(
        affordance_id=affordance_id,
        selected_patch_type=selected_patch_type,
        patch_payload_schema=patch_schema,
        allowed_command_types=allowed_cmd_types,
        verification_lane=lane,
    )


# =============================================================================
# InternalRoutingFacts
# =============================================================================


def build_internal_routing(
    issue: Any,
    target: Any | None = None,
) -> InternalRoutingFacts:
    return InternalRoutingFacts(
        diagnostic_id=getattr(issue, "primary_diagnostic_id", "") or "",
        target_ref=getattr(issue, "target_ref", "") or "",
        worker_id=getattr(target, "worker_id", None),
        construct_id=getattr(target, "construct_id", None) if target else None,
    )


# =============================================================================
# SafetyFacts, PreviousSuggestionFacts
# =============================================================================


def build_safety_facts() -> SafetyFacts:
    return SafetyFacts()


def build_previous_facts(
    previous_summaries: tuple[str, ...] = (),
) -> PreviousSuggestionFacts:
    return PreviousSuggestionFacts(previous_summaries=previous_summaries)
