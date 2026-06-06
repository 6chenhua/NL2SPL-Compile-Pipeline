"""Unit tests for GenericNLAdapter passthrough behavior."""

from __future__ import annotations

from nl2spl.adapters.generic_nl import GenericNLAdapter
from nl2spl.canonical import CanonicalCompileInputValidator


class _FailingLLM:
    def __init__(self) -> None:
        self.calls = 0

    def call_json(self, **_kwargs: object) -> dict:
        self.calls += 1
        raise RuntimeError("LLM must not be called by GenericNLAdapter")


class TestGenericAdapterPassthrough:
    def test_no_llm_client_returns_passthrough(self) -> None:
        adapter = GenericNLAdapter(llm_client=None)
        result = adapter.adapt("Some freeform text.")

        assert result.source_schema == "generic_nl"
        assert result.raw_text == "Some freeform text."
        assert result.raw_sections == []
        assert result.semantic_packets == []
        assert result.hard_facts.inputs == []
        assert result.hard_facts.outputs == []
        assert result.hard_facts.delegation_intents == []
        assert result.warnings == []
        assert CanonicalCompileInputValidator.validate(result) == []

    def test_llm_client_is_ignored_and_not_called(self) -> None:
        fake_llm = _FailingLLM()
        adapter = GenericNLAdapter(llm_client=fake_llm)

        result = adapter.adapt("Do work and produce a report.")

        assert fake_llm.calls == 0
        assert result.source_schema == "generic_nl"
        assert result.hard_facts.inputs == []
        assert result.hard_facts.outputs == []
        assert result.hard_facts.delegation_intents == []
        assert not any(w.code == "LLM_EXTRACTION_FAILED" for w in result.warnings)


class TestAdapterDetection:
    def test_always_matches(self) -> None:
        adapter = GenericNLAdapter()
        detection = adapter.detect("anything")
        assert detection.matched is True
        assert detection.schema_name == "generic_nl"
