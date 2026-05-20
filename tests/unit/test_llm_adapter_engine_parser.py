"""Unit tests for LLM adapter engine parser (Phase 2).

All tests use fake JSON responses -- no network or real LLM dependency.
"""

from __future__ import annotations

import json

import pytest

from nl2spl.adapters.llm_engine import AdapterFactExtraction, parse_llm_fact_json


# -- helpers -------------------------------------------------------------


def _valid_json_facts() -> dict:
    return {
        "inputs": [
            {
                "name": "user_request",
                "description": "The user's question.",
                "data_type": "text",
                "required": True,
                "source_section_id": "sec_inputs_for_each_run",
                "source_packet_id": "p_runtime_input_1",
            }
        ],
        "outputs": [
            {
                "name": "final_report",
                "description": "A compiled report.",
                "data_type": "text",
                "required": True,
                "source_section_id": "sec_required_outputs",
            }
        ],
        "failure_modes": [
            {
                "name": "missing_timeframe",
                "text": "Missing timeframe: The user did not provide a timeframe.",
                "source_section_id": "sec_failure_handling",
            }
        ],
        "delegation_intents": [
            {
                "name": "source_gathering",
                "text": "Delegate source gathering to a specialized agent.",
                "source_section_id": "sec_delegation_policy",
                "suggested_worker_name": None,
                "input_names": ["user_request"],
                "output_names": ["gathered_sources"],
            }
        ],
    }


def _known_context():
    section_ids = {
        "sec_inputs_for_each_run",
        "sec_required_outputs",
        "sec_failure_handling",
        "sec_delegation_policy",
    }
    packets = {
        "p_runtime_input_1": _fake_packet("p_runtime_input_1", "sec_inputs_for_each_run"),
    }
    return section_ids, packets


class _FakePacket:
    def __init__(self, pid, sid):
        self.packet_id = pid
        self.source_section_id = sid


def _fake_packet(pid, sid):
    return _FakePacket(pid, sid)


# -- Tests ----------------------------------------------------------------


class TestParseValidJson:
    def test_all_fact_kinds_parsed(self) -> None:
        sids, pkts = _known_context()
        raw = json.dumps(_valid_json_facts())
        result = parse_llm_fact_json(raw, sids, pkts)

        assert len(result.inputs) == 1
        assert result.inputs[0].name == "user_request"
        assert len(result.inputs[0].evidence) == 1
        assert result.inputs[0].evidence[0].source_section_id == "sec_inputs_for_each_run"
        assert result.inputs[0].evidence[0].source_packet_id == "p_runtime_input_1"

        assert len(result.outputs) == 1
        assert result.outputs[0].name == "final_report"
        assert result.outputs[0].evidence[0].source_section_id == "sec_required_outputs"

        assert len(result.failure_modes) == 1
        assert result.failure_modes[0].text == "Missing timeframe: The user did not provide a timeframe."

        assert len(result.delegation_intents) == 1
        assert result.delegation_intents[0].name == "source_gathering"

    def test_empty_json_produces_empty_extraction(self) -> None:
        sids, pkts = _known_context()
        result = parse_llm_fact_json("{}", sids, pkts)
        assert result.inputs == []
        assert result.outputs == []
        assert result.failure_modes == []
        assert result.delegation_intents == []
        assert result.warnings == []

    def test_empty_lists_produces_empty_extraction(self) -> None:
        sids, pkts = _known_context()
        raw = json.dumps({
            "inputs": [], "outputs": [],
            "failure_modes": [], "delegation_intents": [],
        })
        result = parse_llm_fact_json(raw, sids, pkts)
        assert result.inputs == []
        assert result.outputs == []
        assert len(result.warnings) == 0


class TestRejectsMalformed:
    def test_invalid_json_produces_error_warning(self) -> None:
        sids, _ = _known_context()
        result = parse_llm_fact_json("not json", sids)
        assert any(w.code == "LLM_JSON_PARSE_ERROR" for w in result.warnings)
        assert result.inputs == []

    def test_non_object_json_produces_error_warning(self) -> None:
        sids, _ = _known_context()
        result = parse_llm_fact_json('"just a string"', sids)
        assert any(w.code == "LLM_JSON_NOT_OBJECT" for w in result.warnings)


class TestRejectsUncitedFacts:
    def test_fact_without_source_section_id_is_skipped(self) -> None:
        sids, _ = _known_context()
        raw = json.dumps({
            "inputs": [{"name": "orphan", "description": "No section"}],
        })
        result = parse_llm_fact_json(raw, sids)
        assert result.inputs == []
        assert any("no valid evidence" in w.message.lower() for w in result.warnings)

    def test_fact_with_unknown_section_id_is_skipped(self) -> None:
        sids, _ = _known_context()
        raw = json.dumps({
            "inputs": [{
                "name": "ghost",
                "description": "Bad section",
                "source_section_id": "sec_does_not_exist",
            }],
        })
        result = parse_llm_fact_json(raw, sids)
        assert result.inputs == []
        assert any("unknown" in w.message.lower() for w in result.warnings)

    def test_fact_without_name_is_skipped(self) -> None:
        sids, _ = _known_context()
        raw = json.dumps({
            "inputs": [{
                "description": "No name",
                "source_section_id": "sec_inputs_for_each_run",
            }],
        })
        result = parse_llm_fact_json(raw, sids)
        assert result.inputs == []

    def test_fact_missing_text_uses_name(self) -> None:
        sids, _ = _known_context()
        raw = json.dumps({
            "failure_modes": [{
                "name": "missing_timeframe",
                "source_section_id": "sec_failure_handling",
            }],
        })
        result = parse_llm_fact_json(raw, sids)
        assert len(result.failure_modes) == 1
        assert result.failure_modes[0].text == "missing_timeframe"


class TestValidatesPacketReferences:
    def test_packet_belongs_to_wrong_section_rejects_fact(self) -> None:
        sids, pkts = _known_context()
        # p_runtime_input_1 belongs to sec_inputs_for_each_run
        # but we claim sec_required_outputs -> fact rejected
        raw = json.dumps({
            "inputs": [{
                "name": "bad_ref",
                "description": "Test",
                "source_section_id": "sec_required_outputs",
                "source_packet_id": "p_runtime_input_1",
            }],
        })
        result = parse_llm_fact_json(raw, sids, pkts)
        # Strict: fact skipped entirely
        assert result.inputs == []
        assert any("belongs" in w.message.lower() for w in result.warnings)

    def test_unknown_packet_id_rejects_fact(self) -> None:
        sids, pkts = _known_context()
        raw = json.dumps({
            "inputs": [{
                "name": "ok",
                "description": "Test",
                "source_section_id": "sec_inputs_for_each_run",
                "source_packet_id": "p_does_not_exist",
            }],
        })
        result = parse_llm_fact_json(raw, sids, pkts)
        # Strict: fact rejected
        assert result.inputs == []
        assert any("unknown" in w.message.lower() for w in result.warnings)

    def test_valid_section_without_packet_still_accepted(self) -> None:
        sids, pkts = _known_context()
        raw = json.dumps({
            "inputs": [{
                "name": "ok",
                "description": "Test",
                "source_section_id": "sec_inputs_for_each_run",
            }],
        })
        result = parse_llm_fact_json(raw, sids, pkts)
        assert len(result.inputs) == 1
        assert result.inputs[0].name == "ok"


class TestEvidenceListField:
    def test_explicit_evidence_list_used(self) -> None:
        sids, pkts = _known_context()
        raw = json.dumps({
            "inputs": [{
                "name": "v1",
                "description": "Test",
                "evidence": [
                    {"source_section_id": "sec_inputs_for_each_run"},
                ],
            }],
        })
        result = parse_llm_fact_json(raw, sids, pkts)
        assert len(result.inputs) == 1
        assert len(result.inputs[0].evidence) == 1

    def test_evidence_list_unknown_section_rejected(self) -> None:
        sids, pkts = _known_context()
        raw = json.dumps({
            "inputs": [{
                "name": "v1",
                "description": "Test",
                "evidence": [
                    {"source_section_id": "sec_unknown"},
                ],
            }],
        })
        result = parse_llm_fact_json(raw, sids, pkts)
        assert result.inputs == []


class TestLLMWarningsPreserved:
    def test_warnings_from_llm_are_kept(self) -> None:
        sids, _ = _known_context()
        raw = json.dumps({
            "warnings": [
                {"code": "LLM_UNCERTAIN", "message": "Could not determine scope."},
            ],
        })
        result = parse_llm_fact_json(raw, sids)
        assert any("Could not determine scope" in w.message for w in result.warnings)

    def test_empty_warning_dict_ignored(self) -> None:
        sids, _ = _known_context()
        raw = json.dumps({
            "warnings": [{"code": "LLM_UNCERTAIN"}],
        })
        result = parse_llm_fact_json(raw, sids)
        # Warning with no message is silently skipped
        assert len(result.warnings) == 0


class TestProtocolSmoke:
    def test_extraction_dto_defaults(self) -> None:
        ext = AdapterFactExtraction()
        assert ext.inputs == []
        assert ext.outputs == []
        assert ext.failure_modes == []
        assert ext.delegation_intents == []
        assert ext.warnings == []

    def test_extraction_default_lists_not_shared(self) -> None:
        e1 = AdapterFactExtraction()
        e2 = AdapterFactExtraction()
        e1.inputs.append("x")  # type: ignore[arg-type]
        assert e2.inputs == []
