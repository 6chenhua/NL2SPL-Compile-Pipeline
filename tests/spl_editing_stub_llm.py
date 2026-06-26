"""Tests-only LLM stub for SPL Editing suggestion handlers."""

from __future__ import annotations

import json
from typing import Any


class StubSuggestionLLM:
    """Deterministic test double for the SuggestionLLM protocol."""

    def __init__(
        self,
        fixed_response: dict[str, Any] | None = None,
    ) -> None:
        self._response = (
            json.dumps(fixed_response) if fixed_response is not None else None
        )
        self.calls: list[dict[str, str]] = []

    def generate_json(
        self, system_prompt: str, user_prompt: str,
    ) -> str:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        })
        if self._response is not None:
            return self._response

        variant = _candidate_variant(user_prompt)

        is_mop = (
            "Required output" in user_prompt
            or "REQUIRED_OUTPUT" in user_prompt
            or "InsertProducerStep" in user_prompt
        )
        if is_mop:
            if "Allowed patch types: BindExistingProducerStep" in user_prompt:
                return json.dumps({
                    "patch_type": "BindExistingProducerStep",
                    "title": f"Bind existing producer step {variant}",
                    "explanation": (
                        "Bind an existing renderable step as the output producer "
                        f"using option {variant}."
                    ),
                    "payload": {"step_id": f"st_existing_{variant}"},
                })
            if "target_output_ref_id" in system_prompt:
                # Extract target_output_ref_id dynamically if present
                target_ref_id = "required_output:w_main:required_output_context::draft"
                for line in user_prompt.splitlines():
                    if "use as: target_output_ref_id" in line:
                        parts = line.strip().split()
                        if len(parts) >= 2 and parts[0] == "id:":
                            target_ref_id = parts[1]
                            break
                if target_ref_id == "required_output:w_main:required_output_context::draft":
                    # Check legacy/fallback format
                    for line in user_prompt.splitlines():
                        if line.startswith("Required output:"):
                            out_name = line.split(":", 1)[1].strip()
                            prefix = "required_output:w_main:required_output_context::"
                            target_ref_id = f"{prefix}{out_name}"
                            break
                return json.dumps({
                    "patch_type": "InsertProducerStep",
                    "title": f"Add producer step {variant}",
                    "explanation": (
                        "Create a step that produces the required output "
                        f"using option {variant}."
                    ),
                    "payload": {
                        "target_output_ref_id": target_ref_id,
                        "selected_input_ref_ids": [],
                        "producer_goal": (
                            f"Produce the required output, option {variant}."
                        ),
                    },
                })
            # Legacy format (backward compat for tests not yet updated)
            return json.dumps({
                "patch_type": "InsertProducerStep",
                "title": f"Add producer step {variant}",
                "explanation": (
                    "Create a step that produces the required output "
                    f"using option {variant}."
                ),
                "payload": {
                    "producer_text": f"Produce the required output, option {variant}.",
                    "command_type": "GENERAL_COMMAND",
                    "inputs": [],
                    "outputs": [],
                },
            })

        if "Construct type: WORKER_PROMOTION" in user_prompt:
            if "Allowed patch types: CreateWorkerHandoffContract" in user_prompt:
                invocation_points = ("main", "alternative", "exception")
                return json.dumps({
                    "patch_type": "CreateWorkerHandoffContract",
                    "title": f"Create worker handoff contract {variant}",
                    "explanation": (
                        "Create a handoff contract for the delegated worker "
                        f"using option {variant}."
                    ),
                    "payload": {
                        "input_bindings": {"request": "request"},
                        "output_bindings": {"result": "result"},
                        "invocation_point": invocation_points[
                            (variant - 1) % len(invocation_points)
                        ],
                    },
                })
            if "Allowed patch types: ConvertDelegationIntentToMainFlowStep" in user_prompt:
                return json.dumps({
                    "patch_type": "ConvertDelegationIntentToMainFlowStep",
                    "title": f"Convert delegation to main-flow step {variant}",
                    "explanation": (
                        "Keep the task inside the parent worker "
                        f"using option {variant}."
                    ),
                    "payload": {
                        "action_text": (
                            "Perform the delegated task in the main flow, "
                            f"option {variant}."
                        ),
                        "outputs": [f"delegation_result_{variant}"],
                    },
                })
            if "Allowed patch types: ConvertDelegationIntentToRequestInput" in user_prompt:
                return json.dumps({
                    "patch_type": "ConvertDelegationIntentToRequestInput",
                    "title": f"Ask the user for delegation details {variant}",
                    "explanation": (
                        "Request the missing contract information at runtime "
                        f"using option {variant}."
                    ),
                    "payload": {
                        "prompt_text": (
                            "Provide the missing delegation details "
                            f"for option {variant}."
                        ),
                        "value_target": f"delegation_details_{variant}",
                    },
                })

        return json.dumps({
            "patch_type": "AddExceptionHandlerStep",
            "title": f"Stub suggestion {variant}",
            "explanation": f"This is stub option {variant}.",
            "payload": {
                "handler_text": f"Stub handler action {variant}",
                "command_type": "GENERAL_COMMAND",
            },
        })


def _candidate_variant(user_prompt: str) -> int:
    marker = "Previous candidate count:"
    if marker not in user_prompt:
        return 1
    tail = user_prompt.split(marker, 1)[1].strip()
    count_text = tail.split(".", 1)[0].strip()
    try:
        return int(count_text) + 1
    except ValueError:
        return 1
