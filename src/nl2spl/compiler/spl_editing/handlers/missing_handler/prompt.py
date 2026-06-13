"""Prompt templates for the missing_handler repair handler."""

MISSING_HANDLER_SYSTEM_PROMPT = """\
You are a repair assistant for an NL2SPL compiler.  The compiler has
diagnosed an exception flow that has a condition but no handler action.

Your task is to suggest a concrete handler step that the user can
confirm and apply.

Rules:
- The handler must address the exception condition described.
- Choose one of: GENERAL_COMMAND, REQUEST_INPUT, DISPLAY_MESSAGE.
- If the handler asks the user for missing information, use REQUEST_INPUT.
- If the handler notifies the user, use DISPLAY_MESSAGE.
- If the handler performs a fallback action, use GENERAL_COMMAND.
- Output valid JSON matching the required schema.
- Only output the JSON object — no markdown fences, no commentary.
"""


def build_missing_handler_user_prompt(
    condition_text: str,
    target_ref: str,
    allowed_patch_types: tuple[str, ...],
    user_instruction: str | None = None,
) -> str:
    """Build the user prompt for a missing_handler repair."""
    parts = [
        "Exception flow condition:",
        f"  {condition_text}",
        "",
        f"Target: {target_ref}",
        "",
        f"Allowed patch types: {', '.join(sorted(allowed_patch_types))}",
        "",
        "Generate a handler step suggestion.",
        "You MUST use one of the allowed patch types listed above.",
    ]
    if user_instruction:
        parts.append(f"\nAdditional user instruction: {user_instruction}")
    return "\n".join(parts)
