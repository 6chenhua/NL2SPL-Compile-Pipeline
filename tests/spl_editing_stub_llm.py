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

        if "Required output:" in user_prompt:
            if "Allowed patch types: BindExistingProducerStep" in user_prompt:
                return json.dumps({
                    "patch_type": "BindExistingProducerStep",
                    "title": "Bind existing producer step",
                    "explanation": (
                        "Bind an existing renderable step as the output producer."
                    ),
                    "payload": {},
                })
            return json.dumps({
                "patch_type": "InsertProducerStep",
                "title": "Add producer step",
                "explanation": "Create a step that produces the required output.",
                "payload": {
                    "producer_text": "Produce the required output.",
                    "command_type": "GENERAL_COMMAND",
                    "inputs": [],
                    "outputs": [],
                },
            })

        if "Construct type: WORKER_PROMOTION" in user_prompt:
            if "Allowed patch types: CreateWorkerHandoffContract" in user_prompt:
                return json.dumps({
                    "patch_type": "CreateWorkerHandoffContract",
                    "title": "Create worker handoff contract",
                    "explanation": "Create a handoff contract for the delegated worker.",
                    "payload": {
                        "input_bindings": {"request": "request"},
                        "output_bindings": {"result": "result"},
                        "invocation_point": "main",
                    },
                })
            if "Allowed patch types: ConvertDelegationIntentToMainFlowStep" in user_prompt:
                return json.dumps({
                    "patch_type": "ConvertDelegationIntentToMainFlowStep",
                    "title": "Convert delegation to main-flow step",
                    "explanation": "Keep the task inside the parent worker.",
                    "payload": {
                        "action_text": "Perform the delegated task in the main flow.",
                        "outputs": [],
                    },
                })
            if "Allowed patch types: ConvertDelegationIntentToRequestInput" in user_prompt:
                return json.dumps({
                    "patch_type": "ConvertDelegationIntentToRequestInput",
                    "title": "Ask the user for delegation details",
                    "explanation": "Request the missing contract information at runtime.",
                    "payload": {
                        "prompt_text": "Provide the missing delegation details.",
                        "value_target": "delegation_details",
                    },
                })

        return json.dumps({
            "patch_type": "AddExceptionHandlerStep",
            "title": "Stub suggestion",
            "explanation": "This is a stub.",
            "payload": {
                "handler_text": "Stub handler action",
                "command_type": "GENERAL_COMMAND",
            },
        })
