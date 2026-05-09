"""Custom exceptions for NL2SPL pipeline."""

from __future__ import annotations

from typing import Any


class NL2SPLError(Exception):
    """Base exception for NL2SPL pipeline."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class PipelineError(NL2SPLError):
    """Pipeline orchestration error."""

    def __init__(
        self,
        message: str,
        stage: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.stage = stage


class StageError(NL2SPLError):
    """Individual stage execution error."""

    def __init__(
        self,
        message: str,
        stage: str,
        span_ids: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.stage = stage
        self.span_ids = span_ids or []


class LLMError(NL2SPLError):
    """LLM API error."""

    def __init__(
        self,
        message: str,
        stage: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.stage = stage
        self.status_code = status_code


class IRValidationError(NL2SPLError):
    """IR validation error."""

    def __init__(
        self,
        message: str,
        ir_type: str,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.ir_type = ir_type
        self.field = field


class SpanError(NL2SPLError):
    """Span processing error."""

    def __init__(
        self,
        message: str,
        span_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.span_id = span_id
