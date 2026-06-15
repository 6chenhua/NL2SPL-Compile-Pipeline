"""LLMRepairContextBuilder (Phase L2).

Orchestrates the construction of an ``LLMRepairContext`` from structured
backend state.  Does NOT parse raw diagnostic.message, target_ref, or
final SPL text.  Does NOT call LLM.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.spl_editing.llm_context.common_facts import (
    build_internal_routing,
    build_issue_facts,
    build_previous_facts,
    build_repair_action_facts,
    build_safety_facts,
    build_source_facts,
    build_target_facts,
    build_workflow_facts,
)
from nl2spl.compiler.spl_editing.llm_context.model import (
    LLMRepairContext,
    LLMRepairContextExtension,
)
from nl2spl.compiler.spl_editing.llm_context.quality import evaluate_quality
from nl2spl.compiler.spl_editing.llm_context.readiness import evaluate_readiness
from nl2spl.compiler.spl_editing.llm_context.schema import validate_facts


class LLMRepairContextBuilder:
    """Build an ``LLMRepairContext`` from structured backend inputs.

    Inputs come from the service layer — this builder does NOT import
    handlers, patches, or LLM clients.
    """

    def __init__(
        self,
        *,
        provider_registry: Any | None = None,  # LLMRepairContextExtensionRegistry
    ) -> None:
        self._provider_registry = provider_registry

    def build(
        self,
        *,
        session_id: str,
        issue: Any,  # EditableIssue
        target: Any,  # RepairTarget
        repair_context: Any,  # RepairContext
        artifact_snapshot: Any,  # ArtifactSnapshot
        selected_patch_type: str,
        affordance_id: str = "",
        user_instruction: str | None = None,
        previous_summaries: tuple[str, ...] = (),
        presentation_view: Any | None = None,  # IssuePresentationView
        source_spans: tuple[Any, ...] = (),
        catalog_entry: Any | None = None,  # RepairCatalogEntry
        patch_registry: Any | None = None,  # PatchRegistry
    ) -> LLMRepairContext:
        """Build the complete LLMRepairContext."""

        issue_facts = build_issue_facts(issue, presentation_view)
        source_facts = build_source_facts(issue, source_spans, user_instruction)
        target_facts = build_target_facts(issue, target, artifact_snapshot)
        workflow_facts = build_workflow_facts(artifact_snapshot, target)
        repair_action_facts = build_repair_action_facts(
            affordance_id=affordance_id,
            selected_patch_type=selected_patch_type,
            patch_registry=patch_registry,
            catalog_entry=catalog_entry,
        )
        safety_facts = build_safety_facts()
        previous_facts = build_previous_facts(previous_summaries)
        routing = build_internal_routing(issue, target)

        # Primary extension via provider registry
        primary_ext = self._resolve_primary_extension(
            issue=issue,
            target=target,
            repair_context=repair_context,
            artifact_snapshot=artifact_snapshot,
            affordance_id=affordance_id,
            selected_patch_type=selected_patch_type,
            presentation_view=presentation_view,
        )

        # Quality
        quality = evaluate_quality(
            has_primary_business_fact=bool(
                primary_ext.facts.get("exception_condition_text")
                if primary_ext.extension_id
                else issue_facts.what_was_detected
            ),
            has_source_excerpt=bool(source_facts.primary_source_excerpt),
            has_workflow_context=bool(workflow_facts.nearby_steps),
        )

        # Readiness
        readiness = evaluate_readiness(
            repair_available=bool(selected_patch_type),
            required_facts_present=tuple(
                k for k in primary_ext.required_fact_keys
                if k in primary_ext.facts and primary_ext.facts[k]
            ),
            required_facts_missing=tuple(
                k for k in primary_ext.required_fact_keys
                if k not in primary_ext.facts or not primary_ext.facts[k]
            ),
            quality=quality,
        )

        return LLMRepairContext(
            context_id=f"ctx_{session_id}_{selected_patch_type}",
            session_id=session_id,
            issue_facts=issue_facts,
            source_facts=source_facts,
            target_facts=target_facts,
            workflow_facts=workflow_facts,
            repair_action_facts=repair_action_facts,
            safety_facts=safety_facts,
            previous_suggestion_facts=previous_facts,
            internal_routing=routing,
            primary_extension=primary_ext,
            quality=quality,
            generation_readiness=readiness,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_primary_extension(
        self,
        issue: Any,
        target: Any,
        repair_context: Any,
        artifact_snapshot: Any,
        affordance_id: str,
        selected_patch_type: str,
        presentation_view: Any | None = None,
    ) -> LLMRepairContextExtension:
        """Resolve and collect the primary extension."""
        if self._provider_registry is None:
            return _empty_primary_extension()

        construct_type = ""
        slot_name = ""
        diag_kind = getattr(issue, "kind", "") or ""
        if target is not None:
            irs_ref = getattr(target, "irs_ref", None)
            if irs_ref is not None:
                construct_type = getattr(irs_ref, "construct_type", "") or ""
                slot_name = getattr(irs_ref, "slot_name", "") or ""

        provider = self._provider_registry.resolve_primary(
            affordance_id=affordance_id,
            construct_type=construct_type,
            slot_name=slot_name,
            diagnostic_kind=diag_kind,
            patch_type=selected_patch_type,
        )
        if provider is None:
            return _empty_primary_extension()

        extension = provider.collect_facts(
            issue=issue,
            target=target,
            repair_context=repair_context,
            artifact_snapshot=artifact_snapshot,
            presentation_view=presentation_view,
        )
        validate_facts(
            facts=extension.facts,
            required_keys=extension.required_fact_keys,
            optional_keys=extension.optional_fact_keys,
            facts_schema_id=extension.facts_schema_id,
        )
        return extension


def _empty_primary_extension() -> LLMRepairContextExtension:
    return LLMRepairContextExtension(
        extension_id="", provider_id="",
        role="primary",
        affordance_id="", construct_type="", slot_name="",
        diagnostic_kind="", patch_type="",
        facts_schema_id="", facts_schema_version="",
    )
