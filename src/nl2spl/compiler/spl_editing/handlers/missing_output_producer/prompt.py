"""Prompt templates for missing_output_producer repair handler.

R6: Insert and Bind use independent prompts/schemas.
The LLM context renderer (not the handler) is responsible for
displaying selectable references in the rendered prompt.
"""

# ---------------------------------------------------------------------------
# InsertProducerStep (R6 — intent path)
# ---------------------------------------------------------------------------

INSERT_PRODUCER_SYSTEM_PROMPT = """\
You are a repair assistant for an NL2SPL compiler.  The compiler has
diagnosed a required output that has no source-backed producer step.

Your task is to suggest a concrete producer step that the user can
confirm and apply.

Rules:
- Select inputs ONLY from the provided Selectable References section.
- Reference inputs by their exact ref_id values.
- NEVER invent variable names — the compiler decides what variables exist.
- NEVER output command_type, step_id, flow_ref, block_ref, or handoff_id.
- The compiler decides the command type and step placement.

Output a single JSON object with exactly these keys:
  patch_type: "InsertProducerStep"
  title: short human-readable suggestion title
  explanation: one-sentence explanation of what this fix does
  payload: {
    target_output_ref_id: "<ref_id of the required output>",
    selected_input_ref_ids: ["<ref_id>", ...],
    producer_goal: "<what this step does, in plain English>",
    notes_for_user: "<optional notes>"
  }

Forbidden keys anywhere in the output: inputs, outputs, command_type,
step_id, flow_ref, block_ref, handoff_id.

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
    """Build the user prompt for the missing output producer handler.

    The LLM context renderer injects selectable references into the
    rendered prompt — the handler does NOT splice them in manually.
    """
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
        parts.append(f"Previous candidate count: {len(previous_suggestions)}.")
        parts.append(
            "Generate a fresh valid candidate using the same structured "
            "context. Do not invent new facts just to make it different."
        )
    if user_instruction:
        parts.append(f"\nAdditional user instruction: {user_instruction}")
    return "\n".join(parts)
