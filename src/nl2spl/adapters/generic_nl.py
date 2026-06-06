"""Generic adapter for freeform input.

This adapter preserves raw freeform text without making semantic claims.
Semantic extraction and routing happen in later LLM-backed pipeline stages.
"""

from __future__ import annotations

from nl2spl.adapters.base import InputAdapter
from nl2spl.canonical import (
    AdapterDetectionResult,
    AdapterWarning,
    CanonicalCompileInput,
    CompileHints,
    HardFacts,
    RawSection,
    SemanticPacket,
)


class GenericNLAdapter(InputAdapter):
    """Adapter for freeform text.

    The adapter only preserves raw text and does not call an LLM.  The
    optional ``llm_client`` parameter is accepted for compatibility with older
    callers but is intentionally ignored.
    """

    name = "generic_nl"
    schema_version = "1.0"

    def __init__(self, llm_client: object | None = None) -> None:
        _ = llm_client

    def detect(self, raw_text: str) -> AdapterDetectionResult:
        return AdapterDetectionResult(
            matched=True,
            schema_name=self.name,
            schema_version=self.schema_version,
        )

    def adapt(self, raw_text: str) -> CanonicalCompileInput:
        detection = self.detect(raw_text)
        warnings: list[AdapterWarning] = []
        sections: list[RawSection] = []
        packets: list[SemanticPacket] = []

        hard_facts = HardFacts()
        compile_hints = CompileHints()

        return CanonicalCompileInput(
            source_schema=self.name,
            schema_version=self.schema_version,
            raw_text=raw_text,
            raw_sections=sections,
            semantic_packets=packets,
            hard_facts=hard_facts,
            compile_hints=compile_hints,
            warnings=warnings,
            detection=detection,
        )
