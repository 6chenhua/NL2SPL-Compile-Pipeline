"""Generic fallback adapter that preserves legacy freeform behavior."""

from __future__ import annotations

from nl2spl.adapters.base import InputAdapter
from nl2spl.canonical import AdapterDetectionResult, CanonicalCompileInput


class GenericNLAdapter(InputAdapter):
    """Fallback adapter for freeform text."""

    name = "generic_nl"
    schema_version = "1.0"

    def detect(self, raw_text: str) -> AdapterDetectionResult:
        """Generic input always matches as fallback."""
        return AdapterDetectionResult(
            matched=True,
            schema_name=self.name,
            schema_version=self.schema_version,
        )

    def adapt(self, raw_text: str) -> CanonicalCompileInput:
        """Return raw text with no semantic additions."""
        detection = self.detect(raw_text)
        return CanonicalCompileInput(
            source_schema=self.name,
            schema_version=self.schema_version,
            raw_text=raw_text,
            detection=detection,
        )
