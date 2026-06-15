"""Errors for the LLM repair context layer (Phase L0)."""

from __future__ import annotations


class LLMContextError(Exception):
    """Base error for LLM context module."""


class SchemaValidationError(LLMContextError):
    """Extension facts failed schema validation."""


class ProviderNotRegisteredError(LLMContextError):
    """No provider registered for the given affordance / patch type combination."""


class RendererNotRegisteredError(LLMContextError):
    """No section renderer registered for the given renderer_id + facts_schema_id."""


class GenerationBlockedError(LLMContextError):
    """LLM generation is blocked due to missing required facts."""
