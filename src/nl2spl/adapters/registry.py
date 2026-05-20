"""Input adapter registry and selection."""

from __future__ import annotations

from nl2spl.adapters.base import InputAdapter
from nl2spl.adapters.generic_nl import GenericNLAdapter
from nl2spl.adapters.structural_nl import StructuralNLAdapter
from nl2spl.canonical import AdapterDetectionResult, CanonicalCompileInput


class InputAdapterRegistry:
    """Select and run the best available adapter for raw text."""

    VALID_ENGINE_MODES = {"off", "generic_only", "structural_enrich", "all"}

    def __init__(
        self,
        adapters: list[InputAdapter] | None = None,
        llm_client: object | None = None,
        adapter_llm_engine: str = "off",
    ) -> None:
        if adapters is not None:
            self.adapters = adapters
            return

        if adapter_llm_engine not in self.VALID_ENGINE_MODES:
            raise ValueError(
                "adapter_llm_engine must be one of: "
                + ", ".join(sorted(self.VALID_ENGINE_MODES))
            )

        structural_client = (
            llm_client if adapter_llm_engine in {"structural_enrich", "all"} else None
        )
        generic_client = (
            llm_client if adapter_llm_engine in {"generic_only", "all"} else None
        )
        self.adapters = [
            StructuralNLAdapter(llm_client=structural_client),
            GenericNLAdapter(llm_client=generic_client),
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
