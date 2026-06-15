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

Output a single JSON object with exactly these keys:
  patch_type: "InsertProducerStep" or "BindExistingProducerStep"
  title: short human-readable suggestion title
  explanation: one-sentence explanation of what this fix does
  payload: {producer_text: "<step description>",
            command_type: "GENERAL_COMMAND"|"REQUEST_INPUT",
            inputs: [<variable names>], outputs: [<variable names>]}
         OR {step_id: "<existing step id>"} for BindExistingProducerStep

Only output the JSON object — no markdown fences, no commentary.
"""


def build_missing_output_user_prompt(
    output_name: str,
    target_ref: str,
    allowed_patch_types: tuple[str, ...],
    user_instruction: str | None = None,
    previous_suggestions: tuple[str, ...] = (),
    bindable_step_ids: tuple[str, ...] = (),
) -> str:
    parts = [
        f"Required output: {output_name}",
        f"Target: {target_ref}",
        f"Allowed patch types: {', '.join(sorted(allowed_patch_types))}",
        "",
        "Generate a producer step suggestion.",
        "You MUST use one of the allowed patch types listed above.",
    ]
    if bindable_step_ids:
        parts.append("")
        parts.append("Bindable existing step ids:")
        for step_id in bindable_step_ids:
            parts.append(f"  - {step_id}")
    if previous_suggestions:
        parts.append("")
        parts.append("Already suggested (generate something DIFFERENT):")
        for prev in previous_suggestions:
            parts.append(f"  - {prev}")
    if user_instruction:
        parts.append(f"\nAdditional user instruction: {user_instruction}")
    return "\n".join(parts)
