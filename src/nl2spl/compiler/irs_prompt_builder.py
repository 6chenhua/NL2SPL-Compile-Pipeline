"""IRSDrivenPromptBuilder — generate Stage prompt checklists from ConstructIRS data.

Reads ``SPLConstructRegistry`` and produces deterministic checklist text
that can be injected into LLM Stage prompts.  This removes the need to
hand-write construct-level rules inside each prompt file.

Phase 2: prompt infrastructure only — not yet wired into live stages.
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import (
    ConstructIRS,
    SlotSpec,
    SPLConstructRegistry,
)

# Mapping from stage name to construct types whose IRS should appear in prompts.
_STAGE_CONSTRUCT_MAP: dict[str, list[str]] = {
    "stage4": ["EXCEPTION_FLOW"],
    "stage7": [
        "GENERAL_COMMAND",
        "REQUEST_INPUT",
        "CALL_API",
        "INVOKE_WORKER",
    ],
    "stage9_5": [
        "REQUIRED_OUTPUT",
        "CHILD_WORKER",
        "WORKER_CANDIDATE",
    ],
}

# Extra prose that supplements the generated checklist for specific stages.
_STAGE_NOTES: dict[str, str] = {
    "stage3_5": (
        "### Critical Rules\n"
        "- Only ACCEPT when ALL of: source-backed responsibility, "
        "input contract, output contract, invocation point, "
        "result handoff, independent callable value.\n"
        "- The following are NEVER workers: 'determine the type', "
        "'identify missing fields', 'generate clarifying questions', "
        "'retrieve sources' (without delegation), 'maintain "
        "provenance', 'produce a draft', 'finalize the result'.\n"
    ),
    "stage3_5a": (
        "### Critical Rules\n"
        "- Identify candidates broadly; mark risks honestly.\n"
        "- Only list contract fields when EXPLICITLY named in source; "
        "leave empty otherwise.\n"
    ),
    "stage3_5b": (
        "### Critical Rules\n"
        "- If a candidate's possible_outputs are empty but the "
        "candidate has explicit_delegation or bounded_io, check "
        "adapter hard facts for the output contract.\n"
    ),
    "stage4": (
        "### Critical Rules\n"
        "- No failure signal → do NOT generate EXCEPTION_FLOW.\n"
        "- Concrete failure condition → output partial EXCEPTION_FLOW with "
        "condition_text and spans only.\n"
        "- Do NOT invent handler actions. missing_handler is diagnosed "
        "later by Stage 9.5.\n"
        "- Keep handler-related spans in the flow; Stage 7 will decide "
        "whether they become handler steps.\n"
        '- Vague "handle failures properly" → type_or_contract_ambiguity, '
        "no concrete flow.\n"
    ),
    "stage7": (
        "### Critical Rules\n"
        "- GENERAL_COMMAND requires source evidence.\n"
        "- REQUEST_INPUT requires explicit ask/request/prompt/confirm source.\n"
        "- CALL_API requires named API/tool/connector plus executable call action.\n"
        "- INVOKE_WORKER requires an accepted handoff.\n"
        "- If an action is only a suggested fix, emit assumption / report data, "
        "NOT an executable StepIR.\n"
    ),
}


class IRSDrivenPromptBuilder:
    """Builds IRS-backed prompt checklist text for a pipeline stage."""

    def __init__(self, registry: SPLConstructRegistry) -> None:
        self._registry = registry
        self._stage_constructs = dict(_STAGE_CONSTRUCT_MAP)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_for_stage(self, stage_name: str) -> str:
        """Return the full checklist text for *stage_name*.

        Returns an empty string for stages that have no registered constructs.
        """
        construct_types = self._stage_constructs.get(stage_name, [])
        if not construct_types:
            return ""

        sections: list[str] = []
        sections.append(
            f"## IRS-Driven Construct Checklist — {stage_name}\n"
        )
        for ct in construct_types:
            irs = self._registry.get(ct)
            sections.append(self.render_construct_checklist(irs))

        note = _STAGE_NOTES.get(stage_name)
        if note:
            sections.append(note)

        return "\n\n".join(sections)

    def render_construct_checklist(self, irs: ConstructIRS) -> str:
        """Render a single construct's IRS as a prompt checklist block."""
        lines: list[str] = []

        # -- header ----------------------------------------------------------
        lines.append(f"### CONSTRUCT: {irs.construct_type}")
        if irs.description:
            lines.append(f"*{irs.description}*")
        lines.append("")

        # -- policies --------------------------------------------------------
        lines.append(f"**Existence policy:** {irs.existence_policy}")
        partial = "ALLOWED" if irs.partial_rendering_allowed else "not allowed"
        lines.append(f"**Partial rendering:** {partial}")
        lines.append("")

        # -- source signals --------------------------------------------------
        lines.append(
            f"**Source signals:** {', '.join(irs.source_signals)}"
        )
        lines.append("")

        # -- slots -----------------------------------------------------------
        lines.append("**Slots:**")
        lines.append("")
        for slot in irs.slots:
            lines.append(self._render_slot(slot))
        lines.append("")

        # -- no-demand behaviour ---------------------------------------------
        lines.append(f"**When no demand:** {irs.no_demand_behavior}")
        if irs.partial_rendering_allowed:
            lines.append(
                "Partial constructs may be rendered when required-for-partial "
                "slots are satisfied; report missing required-for-complete "
                "slots as diagnostics."
            )
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _render_slot(slot: SlotSpec) -> str:
        """Render one SlotSpec as a single indented description line."""
        tags: list[str] = []

        if slot.syntax_required:
            tags.append("syntax_required")
        if slot.required_for_partial:
            tags.append("required_for_partial")
        if slot.required_for_complete:
            tags.append("required_for_complete")
        if slot.renderable_without:
            tags.append("renderable_without")
        if slot.can_be_inferred:
            tags.append("can_be_inferred")
        if slot.can_be_suggested:
            tags.append("can_be_suggested")

        tag_str = f" [{', '.join(tags)}]" if tags else ""

        parts = [f"- `{slot.slot_name}`{tag_str}"]

        if slot.evidence_kinds:
            parts.append(f"  Evidence: {', '.join(slot.evidence_kinds)}")
        if slot.missing_diagnostic:
            parts.append(f"  Missing diagnostic: {slot.missing_diagnostic}")
        if slot.notes:
            parts.append(f"  Note: {slot.notes}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    @property
    def stage_constructs(self) -> dict[str, list[str]]:
        """Return a copy of the stage → construct-type mapping."""
        return dict(self._stage_constructs)


def irs_checklist_for_stage(stage_name: str) -> str:
    """One-shot convenience: IRS checklist for *stage_name* from defaults."""
    registry = SPLConstructRegistry.default()
    builder = IRSDrivenPromptBuilder(registry)
    return builder.render_for_stage(stage_name)
