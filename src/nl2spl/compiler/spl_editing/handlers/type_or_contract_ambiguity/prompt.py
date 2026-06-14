"""Prompt templates for type_or_contract_ambiguity repair handler."""

TYPE_OR_CONTRACT_SYSTEM_PROMPT = """\
You are a repair assistant for an NL2SPL compiler. The compiler has
diagnosed a worker delegation or handoff contract ambiguity.

Your task is to suggest one concrete repair patch that the user can
confirm and apply.

Rules:
- Use only one of the allowed patch types.
- Do not invent worker ids, promotion ids, or compiler ids.
- For CreateWorkerHandoffContract, provide input_bindings and
  output_bindings as JSON objects mapping parent variable names to child
  variable names.
- For ConvertDelegationIntentToMainFlowStep, provide action_text and
  optional outputs.
- For ConvertDelegationIntentToRequestInput, provide prompt_text and
  value_target.
- Output valid JSON only. No markdown fences, no commentary.
"""


def build_type_or_contract_user_prompt(
    *,
    issue_message: str,
    target_ref: str,
    construct_type: str,
    slot_name: str,
    allowed_patch_types: tuple[str, ...],
    parent_worker_id: str | None,
    child_worker_id: str | None,
    child_input_fields: tuple[str, ...],
    child_output_fields: tuple[str, ...],
    user_instruction: str | None = None,
) -> str:
    parts = [
        f"Issue: {issue_message}",
        f"Target: {target_ref}",
        f"Construct type: {construct_type}",
        f"Missing slot: {slot_name}",
        f"Allowed patch types: {', '.join(sorted(allowed_patch_types))}",
        "",
        f"Parent worker id: {parent_worker_id or 'unavailable'}",
        f"Child worker id: {child_worker_id or 'unavailable'}",
        f"Child input fields: {', '.join(child_input_fields) or 'none'}",
        f"Child output fields: {', '.join(child_output_fields) or 'none'}",
        "",
        "Generate one repair suggestion using an allowed patch type.",
    ]
    if user_instruction:
        parts.append(f"\nAdditional user instruction: {user_instruction}")
    return "\n".join(parts)
