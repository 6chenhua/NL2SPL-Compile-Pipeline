"""Pure ConstructIRS checklist renderer."""

from __future__ import annotations

from nl2spl.compiler.constructs.spec import ConstructIRS, SlotSpec


class ConstructPromptBuilder:
    """Render construct IRS definitions as prompt checklist text."""

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

