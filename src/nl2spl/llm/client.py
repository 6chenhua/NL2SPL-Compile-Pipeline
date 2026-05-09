"""LLM client wrapper for NL2SPL pipeline."""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from nl2spl.config import LLMConfig
from nl2spl.errors.exceptions import LLMError

logger = logging.getLogger(__name__)


class LLMClient:
    """Wrapper for OpenAI-compatible LLM API.

    Provides structured JSON output with retry logic.
    """

    def __init__(self, config: LLMConfig) -> None:
        """Initialize LLM client.

        Args:
            config: LLM configuration
        """
        self.config = config
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )

    def call_json(
        self,
        stage_name: str,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Call LLM and parse JSON response.

        Args:
            stage_name: Name of the calling stage
            system_prompt: System prompt
            user_prompt: User prompt
            model: Model override
            max_tokens: Max tokens override
            temperature: Temperature override

        Returns:
            Parsed JSON response

        Raises:
            LLMError: If API call fails or response is not valid JSON
        """
        model = model or self.config.model
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                raise LLMError(
                    "Empty response from LLM",
                    stage=stage_name,
                )

            try:
                result: dict[str, Any] = json.loads(content)
                return result
            except json.JSONDecodeError as e:
                raise LLMError(
                    f"Invalid JSON response: {e}",
                    stage=stage_name,
                    details={"content": content[:500]},
                ) from e

        except LLMError:
            raise
        except Exception as e:
            raise LLMError(
                f"LLM API error: {e}",
                stage=stage_name,
            ) from e

    def call_text(
        self,
        stage_name: str,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Call LLM and return text response.

        Args:
            stage_name: Name of the calling stage
            system_prompt: System prompt
            user_prompt: User prompt
            model: Model override
            max_tokens: Max tokens override
            temperature: Temperature override

        Returns:
            Text response

        Raises:
            LLMError: If API call fails
        """
        model = model or self.config.model
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            content = response.choices[0].message.content
            if not content:
                raise LLMError(
                    "Empty response from LLM",
                    stage=stage_name,
                )

            return content

        except LLMError:
            raise
        except Exception as e:
            raise LLMError(
                f"LLM API error: {e}",
                stage=stage_name,
            ) from e
