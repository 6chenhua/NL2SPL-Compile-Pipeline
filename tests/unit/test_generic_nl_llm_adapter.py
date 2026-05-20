"""Unit tests for GenericNLAdapter LLM extraction (Phase 6)."""

from __future__ import annotations

import json

from nl2spl.adapters.generic_nl import GenericNLAdapter
from nl2spl.adapters.llm_engine import build_freeform_context
from nl2spl.canonical import CanonicalCompileInputValidator


# -- fake LLM client ----------------------------------------------------


class _FakeLLM:
    """Fake LLM that returns controlled JSON for testing."""

    def __init__(self, response_dict: dict) -> None:
        self._response_dict = response_dict
        self.calls: list[dict] = []

    def call_json(
        self, stage_name: str = "",
        system_prompt: str = "", user_prompt: str = "",
        model: str | None = None, max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict:
        self.calls.append({"stage_name": stage_name, "user_prompt": user_prompt})
        return dict(self._response_dict)


def _valid_response() -> dict:
    return {
        "inputs": [{
            "name": "user_request",
            "description": "The user request.",
            "data_type": "text",
            "required": True,
            "source_section_id": "sec_freeform_input",
            "source_packet_id": "p_freeform_000",
        }],
        "outputs": [{
            "name": "report",
            "description": "A report.",
            "data_type": "text",
            "required": True,
            "source_section_id": "sec_freeform_input",
        }],
        "failure_modes": [{
            "name": "missing_data",
            "text": "Missing data: required data not provided.",
            "source_section_id": "sec_freeform_input",
        }],
        "delegation_intents": [{
            "name": "delegate_task",
            "text": "Delegate task to a worker.",
            "source_section_id": "sec_freeform_input",
            "suggested_worker_name": None,
            "input_names": [],
            "output_names": [],
        }],
    }


# -- tests ---------------------------------------------------------------


class TestFreeformContext:
    def test_builds_single_section(self) -> None:
        sections, packets = build_freeform_context("Hello world.")
        assert len(sections) == 1
        assert sections[0].section_id == "sec_freeform_input"

    def test_splits_into_packets(self) -> None:
        text = "First sentence. Second sentence. Third sentence."
        _sections, packets = build_freeform_context(text)
        assert len(packets) >= 3


class TestGenericAdapterFallback:
    def test_no_llm_client_falls_back_to_passthrough(self) -> None:
        adapter = GenericNLAdapter(llm_client=None)
        result = adapter.adapt("Some freeform text.")
        assert result.hard_facts.inputs == []
        assert result.hard_facts.outputs == []
        assert result.hard_facts.failure_modes == []
        assert result.source_schema == "generic_nl"

    def test_llm_extracts_facts_when_available(self) -> None:
        fake_llm = _FakeLLM(_valid_response())
        adapter = GenericNLAdapter(llm_client=fake_llm)
        result = adapter.adapt("Do work and produce a report.")

        assert result.raw_sections[0].section_id == "sec_freeform_input"
        assert result.semantic_packets[0].packet_id == "p_freeform_000"
        assert CanonicalCompileInputValidator.validate(result) == []
        assert len(result.hard_facts.inputs) == 1
        assert result.hard_facts.inputs[0].name == "user_request"
        assert len(result.hard_facts.outputs) == 1
        assert len(result.hard_facts.failure_modes) == 1
        assert len(result.hard_facts.delegation_intents) == 1

    def test_llm_extracts_facts_with_evidence(self) -> None:
        fake_llm = _FakeLLM(_valid_response())
        adapter = GenericNLAdapter(llm_client=fake_llm)
        result = adapter.adapt("Text.")
        fact = result.hard_facts.inputs[0]
        assert len(fact.evidence) == 1
        assert fact.evidence[0].source_section_id == "sec_freeform_input"

    def test_llm_failure_falls_back_with_warning(self) -> None:
        class _FailingLLM:
            def call_json(self, **kw: object) -> dict:
                raise RuntimeError("LLM unavailable")

        adapter = GenericNLAdapter(llm_client=_FailingLLM())
        result = adapter.adapt("Text.")

        assert result.hard_facts.inputs == []
        assert any("LLM_EXTRACTION_FAILED" in w.code for w in result.warnings)

    def test_llm_warnings_not_duplicated(self) -> None:
        fake_llm = _FakeLLM({
            "warnings": [
                {"code": "LLM_UNCERTAIN", "message": "Ambiguous output."},
            ],
        })
        adapter = GenericNLAdapter(llm_client=fake_llm)

        result = adapter.adapt("Text.")

        matching = [w for w in result.warnings if w.message == "Ambiguous output."]
        assert len(matching) == 1


class TestAdapterDetection:
    def test_always_matches(self) -> None:
        adapter = GenericNLAdapter()
        detection = adapter.detect("anything")
        assert detection.matched is True
        assert detection.schema_name == "generic_nl"
