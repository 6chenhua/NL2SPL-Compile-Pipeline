"""Base interface for input adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from nl2spl.canonical import AdapterDetectionResult, CanonicalCompileInput


class InputAdapter(ABC):
    """Common adapter interface."""

    name: str
    schema_version: str

    @abstractmethod
    def detect(self, raw_text: str) -> AdapterDetectionResult:
        """Return whether this adapter matches raw input."""

    @abstractmethod
    def adapt(self, raw_text: str) -> CanonicalCompileInput:
        """Convert raw input into canonical compile input."""
