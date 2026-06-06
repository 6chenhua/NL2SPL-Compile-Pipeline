"""Input adapter registry and selection."""

from __future__ import annotations

from nl2spl.adapters.base import InputAdapter
from nl2spl.adapters.generic_nl import GenericNLAdapter
from nl2spl.adapters.structural_nl import StructuralNLAdapter
from nl2spl.canonical import AdapterDetectionResult, CanonicalCompileInput


class InputAdapterRegistry:
    """Select and run the best available adapter for raw text."""

    def __init__(
        self,
        adapters: list[InputAdapter] | None = None,
    ) -> None:
        if adapters is not None:
            self.adapters = adapters
            return

        self.adapters = [
            StructuralNLAdapter(),
            GenericNLAdapter(),
        ]

    def detect_all(self, raw_text: str) -> list[AdapterDetectionResult]:
        """Run detection for every registered adapter."""
        return [adapter.detect(raw_text) for adapter in self.adapters]

    def select_adapter(self, raw_text: str) -> InputAdapter:
        """Return the first matching adapter in priority order."""
        for adapter in self.adapters:
            if adapter.detect(raw_text).matched:
                return adapter
        return self.adapters[-1]

    def adapt(self, raw_text: str) -> CanonicalCompileInput:
        """Adapt raw text with the selected adapter."""
        adapter = self.select_adapter(raw_text)
        return adapter.adapt(raw_text)
