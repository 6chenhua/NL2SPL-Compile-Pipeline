"""PromptRenderer (Phase L3).

Renders an ``LLMRepairContext`` into a deterministic LLM prompt.
Fixed section order.  No construct_type if-else branching.
Internal ids only in selectable references / internal allowed ids section.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.spl_editing.llm_context.constants import (
    INTERNAL_IDS_SECTION_HEADER,
    JSON_ONLY_INSTRUCTION,
    LOW_CONFIDENCE_INSTRUCTION,
    PROMPT_SECTION_ORDER,
)
from nl2spl.compiler.spl_editing.llm_context.model import LLMRepairContext


class PromptRenderer:
    """Deterministic prompt renderer.

    Does NOT:
      - Branch on construct_type / diagnostic.kind
      - Call LLM
      - Decide repair availability
      - Parse rendered SPL
    """

    def __init__(self, section_renderer_registry: Any | None = None) -> None:
        self._section_registry = section_renderer_registry

    def render(self, context: LLMRepairContext) -> str:
        """Render the full prompt from an LLMRepairContext."""
        sections: list[str] = []

        for section_name in PROMPT_SECTION_ORDER:
            rendered = self._render_section(section_name, context)
            if rendered:
                sections.append(rendered)

        return "\n\n".join(sections)

    def render_system_prompt(self, base_system: str) -> str:
        """Return the system prompt unchanged — extension point for future."""
        return base_system

    # ------------------------------------------------------------------
    # Section dispatchers (no construct_type if-else)
    # ------------------------------------------------------------------

    def _render_section(self, name: str, ctx: LLMRepairContext) -> str:
        if name == "task":
            return self._render_task(ctx)
        if name == "issue_facts":
            return self._render_issue(ctx)
        if name == "source_facts":
            return self._render_source(ctx)
        if name == "target_construct_facts":
            return self._render_target(ctx)
        if name == "local_workflow_facts":
            return self._render_workflow(ctx)
        if name == "primary_extension":
            return self._render_primary_extension(ctx)
        if name == "auxiliary_extensions":
            return self._render_auxiliary_extensions(ctx)
        if name == "allowed_repair_action":
            return self._render_repair_action(ctx)
        if name == "payload_schema":
            return self._render_payload_schema(ctx)
        if name == "safety_rules":
            return self._render_safety(ctx)
        if name == "previous_suggestions":
            return self._render_previous(ctx)
        if name == "internal_allowed_ids":
            return self._render_internal_ids(ctx)
        if name == "json_only_output":
            return self._render_json_only()
        return ""

    # -- Individual section renderers ------------------------------------

    def _render_task(self, ctx: LLMRepairContext) -> str:
        lines = [
            "The SPL has a structural issue that requires a repair.",
            f"Issue: {ctx.issue_facts.what_was_detected}",
            "",
            "Generate a repair suggestion using the selected patch type.",
            f"Selected patch type: {ctx.repair_action_facts.selected_patch_type}",
        ]
        if ctx.generation_readiness.status == "ready_low_confidence":
            lines.append("")
            lines.append(LOW_CONFIDENCE_INSTRUCTION)
        return "\n".join(lines)

    def _render_issue(self, ctx: LLMRepairContext) -> str:
        f = ctx.issue_facts
        parts = ["## Issue", f"What was detected: {f.what_was_detected}"]
        if f.missing_items and f.missing_items[0]:
            parts.append(f"Missing: {', '.join(f.missing_items)}")
        if f.suggested_resolution:
            parts.append(f"Suggested resolution: {f.suggested_resolution}")
        return "\n".join(parts)

    def _render_source(self, ctx: LLMRepairContext) -> str:
        f = ctx.source_facts
        if not f.primary_source_excerpt and not f.user_repair_instruction:
            return ""
        lines = ["## Source Context"]
        if f.primary_source_excerpt:
            lines.append(f"Source excerpt: {f.primary_source_excerpt}")
        if f.user_repair_instruction:
            lines.append(f"User instruction: {f.user_repair_instruction}")
        return "\n".join(lines)

    def _render_target(self, ctx: LLMRepairContext) -> str:
        f = ctx.target_facts
        return "\n".join([
            "## Target Construct",
            f"Construct type: {f.construct_type}",
            f"Missing slot: {f.slot_name}",
            f"Summary: {f.human_readable_target_summary}",
        ])

    def _render_workflow(self, ctx: LLMRepairContext) -> str:
        f = ctx.workflow_facts
        lines = ["## Local Workflow"]
        if f.worker_name:
            lines.append(f"Worker: {f.worker_name}")
        if f.worker_purpose:
            lines.append(f"Purpose: {f.worker_purpose}")
        if f.nearby_steps:
            lines.append("Nearby steps:")
            for s in f.nearby_steps:
                io = f"  outputs: {', '.join(s.outputs)}" if s.outputs else ""
                lines.append(f"  - [{s.command_type}] {s.text}{io}")
        if f.available_variables:
            lines.append(f"Available variables: {', '.join(f.available_variables[:20])}")
        return "\n".join(lines)

    def _render_primary_extension(self, ctx: LLMRepairContext) -> str:
        ext = ctx.primary_extension
        if not ext.extension_id or not self._section_registry:
            return ""
        renderer = self._section_registry.get(
            renderer_id=ext.renderer_id,
            facts_schema_id=ext.facts_schema_id,
            facts_schema_version=ext.facts_schema_version,
        )
        if renderer is None:
            return ""
        return renderer.render(extension=ext)

    def _render_auxiliary_extensions(self, ctx: LLMRepairContext) -> str:
        parts: list[str] = []
        for ext in ctx.auxiliary_extensions:
            if not self._section_registry:
                continue
            renderer = self._section_registry.get(
                renderer_id=ext.renderer_id,
                facts_schema_id=ext.facts_schema_id,
                facts_schema_version=ext.facts_schema_version,
            )
            if renderer is not None:
                parts.append(renderer.render(extension=ext))
        return "\n\n".join(parts)

    def _render_repair_action(self, ctx: LLMRepairContext) -> str:
        f = ctx.repair_action_facts
        lines = [
            "## Allowed Repair Action",
            f"Patch type: {f.selected_patch_type}",
        ]
        if f.allowed_command_types:
            lines.append(f"Allowed command types: {', '.join(f.allowed_command_types)}")
        if f.forbidden_actions:
            lines.append(f"Forbidden actions: {', '.join(f.forbidden_actions)}")
        return "\n".join(lines)

    def _render_payload_schema(self, ctx: LLMRepairContext) -> str:
        f = ctx.repair_action_facts
        if not f.patch_payload_schema:
            return ""
        # Minimal schema rendering — PatchRegistry provides the schema
        schema_keys = list(f.patch_payload_schema.keys())
        required = (
            ", ".join(schema_keys)
            if schema_keys
            else "As defined by PatchRegistry"
        )
        return "\n".join([
            "## Payload Schema",
            f"Required keys: {required}",
        ])

    def _render_safety(self, ctx: LLMRepairContext) -> str:
        f = ctx.safety_facts
        rules = ["## Safety Rules"]
        if f.do_not_invent_facts:
            rules.append("- Do NOT invent facts not present in the context.")
        if f.no_direct_spl_modification:
            rules.append("- Do NOT suggest modifications that bypass typed patches.")
        if f.user_confirmed_repair_required:
            rules.append("- The repair will be user-confirmed before apply.")
        for r in f.additional_rules:
            rules.append(f"- {r}")
        return "\n".join(rules)

    def _render_previous(self, ctx: LLMRepairContext) -> str:
        f = ctx.previous_suggestion_facts
        if not f.previous_summaries:
            return ""
        lines = ["## Previous Suggestions (generate something DIFFERENT)"]
        for s in f.previous_summaries:
            lines.append(f"  - {s}")
        return "\n".join(lines)

    def _render_internal_ids(self, ctx: LLMRepairContext) -> str:
        refs = ctx.repair_action_facts.selectable_references
        routing = ctx.internal_routing
        has_ids = bool(refs) or bool(routing.allowed_ids)
        if not has_ids:
            return ""
        lines = [INTERNAL_IDS_SECTION_HEADER, ""]
        for ref in refs:
            lines.append(
                f"  id: {ref.id}  (use as: {ref.payload_field})\n"
                f"    {ref.summary}"
            )
        return "\n".join(lines)

    def _render_json_only(self) -> str:
        return JSON_ONLY_INSTRUCTION


def append_previous_suggestions(
    rendered_prompt: str,
    previous_summaries: tuple[str, ...],
) -> str:
    """Append retry diversity instructions to an already-rendered prompt.

    This helper is intentionally generic: it does not add issue facts,
    target facts, or repair capabilities.  Those remain owned by
    ``LLMRepairContextBuilder`` and ``PromptRenderer``.
    """
    if not previous_summaries:
        return rendered_prompt
    lines = [
        rendered_prompt,
        "",
        "Already suggested (generate something DIFFERENT):",
    ]
    lines.extend(f"  - {summary}" for summary in previous_summaries)
    return "\n".join(lines)
