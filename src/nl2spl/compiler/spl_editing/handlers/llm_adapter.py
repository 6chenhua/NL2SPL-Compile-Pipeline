"""LLM adapter for SPL Editing suggestion generation.

Wraps the existing project ``LLMClient`` — does NOT create a parallel
LLM stack.  All calls use JSON/schema-constrained output with
temperature 0 (deterministic).
"""

from __future__ import annotations

from typing import Any, Protocol


class SuggestionLLM(Protocol):
    """Protocol for the LLM backend used by repair handlers.

    Keeps the handler code decoupled from the concrete ``LLMClient``
    so tests can substitute a stub.

    ``generate_json()`` returns a JSON string — the handler parses it
    through ``parse_suggestion_payload()``.
    """

    def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        """Send a prompt and return the JSON response as a string."""
        ...


class LiveSuggestionLLM:
    """Production adapter wrapping the project ``LLMClient``.

    Construct with an existing ``LLMClient`` instance.  Calls
    ``call_json(stage_name="spl_editing_suggestion", system_prompt=...,
    user_prompt=..., temperature=0)`` for deterministic output and
    serializes the result to a JSON string.
    """

    def __init__(self, client: Any) -> None:
        """*client* must expose
        ``call_json(stage_name, system_prompt, user_prompt, temperature=...)``.
        """
        self._client = client

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        import json as _json

        result = self._client.call_json(
            stage_name="spl_editing_suggestion",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0,
        )
        return _json.dumps(result)
