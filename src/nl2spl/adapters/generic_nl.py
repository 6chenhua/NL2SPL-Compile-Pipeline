"""Generic fallback adapter that preserves legacy freeform behavior.

When an LLM client is available, the adapter optionally extracts
evidence-bound canonical facts from the raw text via the LLM engine.
Facts without valid evidence are rejected by the verifier.
"""

from __future__ import annotations

from nl2spl.adapters.base import InputAdapter
from nl2spl.adapters.fact_verifier import FactVerifier
from nl2spl.adapters.llm_engine import (
    AdapterFactExtraction,
    build_freeform_context,
    parse_llm_fact_json,
)
from nl2spl.canonical import (
    AdapterDetectionResult,
    AdapterWarning,
    CanonicalCompileInput,
    CompileHints,
    HardFacts,
    RawSection,
    SemanticPacket,
)
from nl2spl.llm.prompts import load_prompt


class GenericNLAdapter(InputAdapter):
    """Fallback adapter for freeform text.

    If an LLM client is provided (via *llm_client*), the adapter
    attempts to extract evidence-bound facts from the raw text.  On
    failure or if no client is available, the adapter falls back to
    the legacy behavior: raw text passthrough with no hard facts.
    """

    name = "generic_nl"
    schema_version = "1.0"

    def __init__(self, llm_client: object | None = None) -> None:
        self._llm_client = llm_client

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

        if self._llm_client is not None:
            try:
                sections, packets = build_freeform_context(raw_text)
                extraction = self._run_llm_extraction(raw_text, sections, packets)
                verifier = FactVerifier()
                hard_facts, llm_warnings = verifier.verify_and_merge(
                    HardFacts(), extraction,
                )
                warnings.extend(llm_warnings)
            except Exception as exc:
                warnings.append(
                    AdapterWarning(
                        code="LLM_EXTRACTION_FAILED",
                        message=(
                            f"LLM fact extraction failed: {exc}. "
                            f"Falling back to generic passthrough."
                        ),
                        severity="warning",
                    )
                )

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

    def _run_llm_extraction(
        self,
        raw_text: str,
        sections: list[RawSection],
        packets: list[SemanticPacket],
    ) -> AdapterFactExtraction:
        """Call the LLM with the fact extraction prompt and parse the response."""
        import json as _json

        section_ids = {s.section_id for s in sections}
        packet_by_id = {p.packet_id: p for p in packets}

        # Build prompt context with section/packet info
        packet_lines = []
        for p in packets:
            packet_lines.append(f"  {p.packet_id} ({p.packet_type}): {p.text}")

        user_prompt = (
            "Extract facts from the following freeform text. "
            "Cite source_section_id='sec_freeform_input' and the "
            "appropriate source_packet_id for every fact.\n\n"
            "Available packets:\n" + "\n".join(packet_lines) + "\n\n"
            f"Raw text:\n{raw_text}"
        )

        system_prompt = load_prompt("input_adapter_fact_extractor")
        result_dict = self._llm_client.call_json(  # type: ignore[union-attr]
            stage_name="generic_nl_fact_extract",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=4096,
        )

        return parse_llm_fact_json(
            _json.dumps(result_dict), section_ids, packet_by_id,
        )

