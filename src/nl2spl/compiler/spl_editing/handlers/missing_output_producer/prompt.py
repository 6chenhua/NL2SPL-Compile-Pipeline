"""Prompt templates for missing_output_producer repair handler."""

MISSING_OUTPUT_SYSTEM_PROMPT = """\
You are a repair assistant for an NL2SPL compiler.  The compiler has
diagnosed a required output that has no source-backed producer step.

Your task is to suggest a concrete producer step that the user can
confirm and apply.

Rules:
- Choose InsertProducerStep to create a new producer step.
- Choose BindExistingProducerStep to bind an existing renderable step.
- For new steps: use GENERAL_COMMAND or REQUEST_INPUT.
- Output valid JSON matching the required schema.
"""


def build_missing_output_user_prompt(
    output_name: str,
    target_ref: str,
    allowed_patch_types: tuple[str, ...],
    user_instruction: str | None = None,
) -> str:
    parts = [
        f"Required output: {output_name}",
        f"Target: {target_ref}",
        f"Allowed patch types: {', '.join(sorted(allowed_patch_types))}",
        "",
        "Generate a producer step suggestion.",
        "You MUST use one of the allowed patch types listed above.",
    ]
    if user_instruction:
        parts.append(f"\nAdditional user instruction: {user_instruction}")
    return "\n".join(parts)
