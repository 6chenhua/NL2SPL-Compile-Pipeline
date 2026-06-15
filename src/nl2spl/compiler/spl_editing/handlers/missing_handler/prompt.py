"""Prompt templates for the missing_handler repair handler."""

MISSING_HANDLER_SYSTEM_PROMPT = """\
You are a repair assistant for an NL2SPL compiler.  The compiler has
diagnosed an exception flow that has a condition but no handler action.

Your task is to suggest a concrete handler step that the user can
confirm and apply.

Rules:
- The handler MUST directly address the exception condition provided
  in the user prompt.  Do NOT generate generic templates unrelated to
  the specific condition.
- Choose one of: GENERAL_COMMAND, REQUEST_INPUT, DISPLAY_MESSAGE.

Example — if the condition is "Missing timeframe":
  REQUEST_INPUT: "Ask the user to provide the missing timeframe"
    outputs: ["timeframe"]
  GENERAL_COMMAND: "Use a default timeframe of 7 days"
    outputs: ["timeframe"]
  DISPLAY_MESSAGE: "Notify the user that a timeframe is required to proceed"

Example — if the condition is "insufficient source access":
  REQUEST_INPUT: "Ask the user for alternative data sources"
    outputs: ["alternative_sources"]
  DISPLAY_MESSAGE: "Inform the user that source access failed and manual data may be needed"

Command-type rules (matching the SPL grammar):
- GENERAL_COMMAND: performs an action.  May have inputs and outputs.
- REQUEST_INPUT: asks the user for missing information.
  * Must have at least one output (the variable storing the user's answer).
  * Must NOT have inputs (it prompts the user, not consumes existing data).
- DISPLAY_MESSAGE: notifies the user with a message.
  * Must NOT have inputs.
  * Must NOT have outputs.

Output a single JSON object with exactly these keys:
  patch_type: "AddExceptionHandlerStep"
  title: short human-readable suggestion title
  explanation: one-sentence explanation of what this fix does
  payload: {
      handler_text: "<step description>",
      command_type: "GENERAL_COMMAND" | "REQUEST_INPUT" | "DISPLAY_MESSAGE",
      inputs: [<variable names>],   // only for GENERAL_COMMAND
      outputs: [<variable names>],  // for GENERAL_COMMAND or REQUEST_INPUT
  }

handler_text rules — the renderer will produce correct SPL syntax from
command_type automatically.  handler_text must be plain content only:
  - Write natural-language text describing the action or message.
  - Do NOT include SPL keywords: DISPLAY_MESSAGE, DISPLAY, COMMAND,
    GENERAL_COMMAND, REQUEST_INPUT, INPUT, CALL, INVOKE.
  - Do NOT wrap the text in single or double quotes.
  - Do NOT prefix with the command type name.

Only output the JSON object — no markdown fences, no commentary.
"""


def build_missing_handler_user_prompt(
    condition_text: str,
    target_ref: str,
    allowed_patch_types: tuple[str, ...],
    user_instruction: str | None = None,
    previous_suggestions: tuple[str, ...] = (),
) -> str:
    """Build the user prompt for a missing_handler repair.

    The *condition_text* is the primary input — the LLM MUST derive
    handler content from it.  *target_ref* is for internal routing only
    and should NOT be treated as business context by the LLM.
    """
    parts = [
        "The SPL has an exception flow with this trigger condition:",
        f'  "{condition_text}"',
        "",
        "Your task: generate handler step text that DIRECTLY addresses this",
        "condition.  Every suggestion MUST reference or respond to the",
        "condition above.  Do NOT invent unrelated scenarios.",
        "",
        f"Allowed patch types: {', '.join(sorted(allowed_patch_types))}",
        "",
        "Generate a handler step suggestion.",
        "You MUST use one of the allowed patch types listed above.",
    ]
    if previous_suggestions:
        parts.append("")
        parts.append("Already suggested (generate something DIFFERENT):")
        for prev in previous_suggestions:
            parts.append(f"  - {prev}")
    if user_instruction:
        parts.append(f"\nAdditional user instruction: {user_instruction}")
    return "\n".join(parts)
