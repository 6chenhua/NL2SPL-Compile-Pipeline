"""IRSDrivenPromptBuilder compatibility wrapper.

Pure construct checklist rendering lives in ``nl2spl.compiler.constructs``.
Stage-local prompt policy lives in ``nl2spl.pipeline.prompt_profiles``.
"""

from __future__ import annotations

from nl2spl.compiler.constructs import SPLConstructRegistry
from nl2spl.compiler.constructs.prompt_builder import ConstructPromptBuilder
from nl2spl.pipeline.prompt_profiles import STAGE_CONSTRUCT_MAP, STAGE_NOTES


class IRSDrivenPromptBuilder:
    """Builds IRS-backed prompt checklist text for a pipeline stage."""

    def __init__(self, registry: SPLConstructRegistry) -> None:
        self._registry = registry
        self._stage_constructs = dict(STAGE_CONSTRUCT_MAP)
        self._construct_builder = ConstructPromptBuilder()

    def render_for_stage(self, stage_name: str) -> str:
        """Return the full checklist text for *stage_name*."""
        construct_types = self._stage_constructs.get(stage_name, [])
        if not construct_types:
            return ""

        sections: list[str] = []
        sections.append(
            f"## IRS-Driven Construct Checklist \u2014 {stage_name}\n"
        )
        for ct in construct_types:
            irs = self._registry.get(ct)
            sections.append(self.render_construct_checklist(irs))

        note = STAGE_NOTES.get(stage_name)
        if note:
            sections.append(note)

        return "\n\n".join(sections)

    def render_construct_checklist(self, irs):
        return self._construct_builder.render_construct_checklist(irs)

    @property
    def stage_constructs(self) -> dict[str, list[str]]:
        """Return a copy of the stage -> construct-type mapping."""
        return dict(self._stage_constructs)


def irs_checklist_for_stage(stage_name: str) -> str:
    """Convenience function using the default registry."""
    return IRSDrivenPromptBuilder(SPLConstructRegistry.default()).render_for_stage(
        stage_name
    )
