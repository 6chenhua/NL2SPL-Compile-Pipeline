"""Prompt templates for the missing_handler repair handler."""

MISSING_HANDLER_SYSTEM_PROMPT = """\
You are a repair assistant for an NL2SPL compiler. The compiler has
diagnosed an EXCEPTION_FLOW.handler_action slot that is missing.

Repair strategy:
- Complete the exception handler action for the target exception flow.
- Treat the user instruction as a RepairDirective preference, not final SPL.
- Describe the intended handler behavior in plain language.
- Do not decide final command family, block shape, or runtime artifact fields.
- Do not invent variable names, output names, worker ids, or refs.
- Use only facts that appear in the prompt context.

Output a single JSON object with exactly these keys:
  patch_type: "AddExceptionHandlerStep"
  title: short human-readable suggestion title
  explanation: one-sentence explanation of how the handler intent addresses the condition
  payload: {
      handler_goal: "<plain-language handler intent>"
  }

handler_goal rules:
- Plain content only; do not include SPL syntax or SPL keywords.
- Do not include final command family names.
- Do not wrap the text in single or double quotes.

Only output the JSON object; no markdown fences, no commentary.
"""


def build_missing_handler_user_prompt(
    condition_text: str,
    target_ref: str,
    allowed_patch_types: tuple[str, ...],
    user_instruction: str | None = None,
    previous_suggestions: tuple[str, ...] = (),
) -> str:
    """Build the user prompt for a missing_handler repair.

    The *condition_text* is the primary input; the LLM must describe handler
    intent from it. *target_ref* is for internal routing only and should not be
    treated as business context by the LLM.
    """
    parts = [
        "The SPL has an exception flow with this trigger condition:",
        f'  "{condition_text}"',
        "",
        "Selected repair strategy: Complete exception handler action.",
        "Generate a handler intent that directly addresses the condition above.",
        "Do not invent unrelated scenarios, variable names, output names, or refs.",
        "The stage policy will decide the final command family later.",
        "",
        f"Allowed patch types as execution adapters: {', '.join(sorted(allowed_patch_types))}",
    ]
    if previous_suggestions:
        parts.append("")
        parts.append(f"Previous candidate count: {len(previous_suggestions)}.")
        parts.append(
            "Generate a fresh valid candidate using the same context. "
            "Do not invent new facts just to make it different."
        )
    if user_instruction:
        parts.append(f"\nAdditional user instruction: {user_instruction}")
    return "\n".join(parts)
