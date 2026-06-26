"""ExceptionFlowHandler section renderer (Phase L3)."""

from __future__ import annotations

from typing import Any


class ExceptionFlowHandlerSectionRenderer:
    """Render the exception flow handler extension facts into a prompt section."""

    renderer_id = "exception_flow_handler_section"
    facts_schema_ids = ("exception_flow.handler_action.add_exception_handler_step.v1",)

    def render(self, *, extension: Any) -> str:
        facts = extension.facts
        condition = facts.get("exception_condition_text", "")
        excerpt = facts.get("exception_source_excerpt")
        allowed_cmds = facts.get("allowed_handler_command_types", [])

        lines = [
            "## Exception Flow Handler Context",
            f'Exception condition: "{condition}"',
        ]
        if excerpt:
            lines.append(f"Source excerpt: {excerpt}")

        if allowed_cmds:
            lines.append(f"Allowed handler command types: {', '.join(allowed_cmds)}")

        return "\n".join(lines)
