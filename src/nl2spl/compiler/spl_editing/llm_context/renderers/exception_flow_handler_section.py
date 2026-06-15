"""ExceptionFlowHandler section renderer (Phase L3)."""

from __future__ import annotations

from typing import Any


class ExceptionFlowHandlerSectionRenderer:
    """Render the exception flow handler extension facts into a prompt section."""

    renderer_id = "exception_flow_handler_section"
    facts_schema_ids = (
        "exception_flow.handler_action.add_exception_handler_step.v1",
    )

    def render(self, *, extension: Any) -> str:
        facts = extension.facts
        condition = facts.get("exception_condition_text", "")
        excerpt = facts.get("exception_source_excerpt")
        purpose = facts.get("parent_worker_purpose")
        nearby = facts.get("nearby_main_flow_steps", [])
        vars_list = facts.get("available_variables_relevant_to_condition", [])
        allowed_cmds = facts.get("allowed_handler_command_types", [])

        lines = [
            "## Exception Flow Handler Context",
            f"Exception condition: \"{condition}\"",
        ]
        if excerpt:
            lines.append(f"Source excerpt: {excerpt}")
        if purpose:
            lines.append(f"Parent worker purpose: {purpose}")

        if nearby:
            lines.append("Nearby main-flow steps:")
            for step in nearby:
                if isinstance(step, dict):
                    outputs = step.get("outputs", [])
                    io = f"  outputs: {', '.join(outputs)}" if outputs else ""
                    lines.append(
                        f"  - [{step.get('command_type', '?')}] "
                        f"{step.get('text', '')}{io}"
                    )

        if vars_list:
            vars_str = ", ".join(str(v) for v in vars_list[:10])
            lines.append(f"Available variables: {vars_str}")

        if allowed_cmds:
            lines.append(
                f"Allowed handler command types: {', '.join(allowed_cmds)}"
            )

        return "\n".join(lines)
