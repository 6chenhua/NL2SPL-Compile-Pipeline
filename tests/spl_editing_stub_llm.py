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

        previous_block = ""
        marker = "Already suggested (generate something DIFFERENT):"
        if marker in user_prompt:
            previous_block = user_prompt.split(marker, 1)[1]
        variant = previous_block.count("  - ") + 1

        if "Required output:" in user_prompt:
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
