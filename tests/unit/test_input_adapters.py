"""Tests for canonical input adapters."""

from __future__ import annotations

from dataclasses import asdict

import pytest

from nl2spl.adapters import GenericNLAdapter, InputAdapterRegistry, StructuralNLAdapter
from nl2spl.canonical import (
    CanonicalCompileInput,
    CanonicalCompileInputValidator,
    HardFacts,
    RawSection,
    SemanticPacket,
    VariableFact,
)
from nl2spl.config import load_config


STRUCTURAL_TEXT = """Task family:
Internal newsletters and announcements.

Inputs for each run:
A user request, optional known topics, optional timeframe,
available connectors or source repositories, and optional format preferences.

Required outputs:
A draft communication artifact, a source/evidence set,
a short assumptions log for any unresolved items, and a completion status.

Reusable process:
First determine what kind of communication is requested.
If sources are needed and available, retrieve them using approved source recipes.

Policies:
Do not invent links or unseen facts. Require evidence for sourced claims.

Failure handling:
Missing timeframe, conflicting instructions, evidence shortage, and provenance failure.

Delegation policy:
Optional delegated subtasks such as source gathering or template matching may be used if bounded.
"""


def test_structural_adapter_detects_complete_input() -> None:
    adapter = StructuralNLAdapter()

    result = adapter.detect(STRUCTURAL_TEXT)

    assert result.matched is True
    assert result.schema_name == "structural_nl"
    assert "inputs_for_each_run" in result.matched_sections
    assert "required_outputs" in result.matched_sections
    assert not result.empty_sections
    assert "confidence" not in asdict(result)


def test_structural_adapter_records_missing_duplicate_and_empty_sections() -> None:
    raw_text = """Task family:
Example.

Policies:

Policies:
Do not invent facts.
"""
    adapter = StructuralNLAdapter()

    result = adapter.detect(raw_text)

    assert "required_outputs" in result.missing_sections
    assert "policies" in result.duplicate_sections
    assert "policies" in result.empty_sections


def test_structural_adapter_accepts_reordered_sections_and_chinese_colon() -> None:
    raw_text = """Required outputs：
A completion status.

Task family:
Example.

Inputs for each run:
A user request.
"""
    adapter = StructuralNLAdapter()

    result = adapter.detect(raw_text)
    canonical = adapter.adapt(raw_text)

    assert result.matched is True
    assert [section.canonical_title for section in canonical.raw_sections] == [
        "required_outputs",
        "task_family",
        "inputs_for_each_run",
    ]


def test_generic_freeform_uses_generic_adapter() -> None:
    registry = InputAdapterRegistry()

    canonical = registry.adapt("Please draft a concise update.")

    assert isinstance(registry.select_adapter("Please draft a concise update."), GenericNLAdapter)
    assert canonical.source_schema == "generic_nl"
    assert canonical.raw_text == "Please draft a concise update."
    assert canonical.raw_sections == []
    assert canonical.semantic_packets == []


def test_registry_adapter_llm_engine_off_passes_no_clients() -> None:
    registry = InputAdapterRegistry(llm_client=object(), adapter_llm_engine="off")

    structural, generic = registry.adapters

    assert isinstance(structural, StructuralNLAdapter)
    assert isinstance(generic, GenericNLAdapter)
    assert getattr(structural, "_llm_client") is None
    assert getattr(generic, "_llm_client") is None


def test_registry_adapter_llm_engine_generic_only() -> None:
    client = object()
    registry = InputAdapterRegistry(llm_client=client, adapter_llm_engine="generic_only")

    structural, generic = registry.adapters

    assert getattr(structural, "_llm_client") is None
    assert getattr(generic, "_llm_client") is client


def test_registry_adapter_llm_engine_structural_enrich() -> None:
    client = object()
    registry = InputAdapterRegistry(
        llm_client=client,
        adapter_llm_engine="structural_enrich",
    )

    structural, generic = registry.adapters

    assert getattr(structural, "_llm_client") is client
    assert getattr(generic, "_llm_client") is None


def test_registry_adapter_llm_engine_all() -> None:
    client = object()
    registry = InputAdapterRegistry(llm_client=client, adapter_llm_engine="all")

    structural, generic = registry.adapters

    assert getattr(structural, "_llm_client") is client
    assert getattr(generic, "_llm_client") is client


def test_load_config_reads_adapter_llm_engine_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NL2SPL_ADAPTER_LLM_ENGINE", "generic_only")

    config = load_config(output_dir=tmp_path)

    assert config.adapter_llm_engine == "generic_only"


def test_load_config_rejects_invalid_adapter_llm_engine(tmp_path) -> None:
    with pytest.raises(ValueError, match="adapter_llm_engine"):
        load_config(output_dir=tmp_path, adapter_llm_engine="invalid")


def test_structural_adapter_extracts_hard_facts_and_hints() -> None:
    canonical = StructuralNLAdapter().adapt(STRUCTURAL_TEXT)

    input_names = {fact.name for fact in canonical.hard_facts.inputs}
    output_names = {fact.name for fact in canonical.hard_facts.outputs}
    failure_names = {fact.name for fact in canonical.hard_facts.failure_modes}

    assert {"user_request", "known_topics", "timeframe"}.issubset(input_names)
    assert {
        "draft_communication_artifact",
        "source_evidence_set",
        "assumptions_log",
        "completion_status",
    }.issubset(output_names)
    assert {"missing_timeframe", "evidence_shortage", "provenance_failure"}.issubset(
        failure_names
    )
    assert canonical.compile_hints.constraint_hints
    assert canonical.compile_hints.delegation_hints


def test_canonical_validator_rejects_bad_section_reference() -> None:
    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Task family:\nExample.",
        raw_sections=[
            RawSection("sec_task_family", "task_family", "Task family", "Example.", 1)
        ],
        semantic_packets=[
            SemanticPacket(
                packet_id="p1",
                source_section_id="missing",
                packet_type="task_family",
                text="Example.",
                modality="hint",
            )
        ],
    )

    errors = CanonicalCompileInputValidator.validate(canonical)

    assert any("unknown source_section_id" in error for error in errors)


def test_canonical_validator_rejects_duplicate_packet_id() -> None:
    section = RawSection("sec_task_family", "task_family", "Task family", "Example.", 1)
    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Task family:\nExample.",
        raw_sections=[section],
        semantic_packets=[
            SemanticPacket("p1", section.section_id, "task_family", "A", "hint"),
            SemanticPacket("p1", section.section_id, "task_family", "B", "hint"),
        ],
    )

    errors = CanonicalCompileInputValidator.validate(canonical)

    assert any("SemanticPacket.packet_id" in error for error in errors)


def test_canonical_validator_rejects_duplicate_hard_fact_names() -> None:
    section = RawSection("sec_inputs", "inputs_for_each_run", "Inputs", "A.", 1)
    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Inputs for each run:\nA.",
        raw_sections=[section],
        hard_facts=HardFacts(
            inputs=[
                VariableFact("user_request", "A user request", "text", True, section.section_id),
                VariableFact("user_request", "User request", "text", True, section.section_id),
            ]
        ),
    )

    errors = CanonicalCompileInputValidator.validate(canonical)

    assert any("HardFacts.inputs.name" in error for error in errors)


def test_canonical_validator_rejects_confidence_field() -> None:
    canonical = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Task family:\nExample.",
        raw_sections=[
            RawSection("sec_task_family", "task_family", "Task family", "Example.", 1)
        ],
        semantic_packets=[
            SemanticPacket(
                "p1",
                "sec_task_family",
                "task_family",
                "Example.",
                "hint",
                metadata={"confidence": 0.9},
            )
        ],
    )

    errors = CanonicalCompileInputValidator.validate(canonical)

    assert any("confidence" in error for error in errors)


# ===========================================================================
# F0 Baseline: semantic_packets coverage
# ===========================================================================


F0_STRUCTURAL_TEXT = """Task family:
Internal newsletters and announcements.

Inputs for each run:
A user request, optional known topics, optional timeframe.

Required outputs:
A draft communication artifact, a source/evidence set, a short assumptions log, and a completion status.

Reusable process:
First determine what kind of communication is requested.
If sources are needed and available, retrieve them using approved source recipes.

Policies:
Do not invent links or unseen facts. Require evidence for sourced claims.

Failure handling:
Missing timeframe, conflicting instructions, evidence shortage, and provenance failure.

Delegation policy:
Optional delegated subtasks such as source gathering or template matching may be used if bounded.
"""


def test_structural_adapter_semantic_packets_cover_all_seven_types() -> None:
    """F0 Baseline: adapter produces all 7 canonical sections and semantic packet types."""
    canonical = StructuralNLAdapter().adapt(F0_STRUCTURAL_TEXT)

    section_titles = {section.canonical_title for section in canonical.raw_sections}
    expected_sections = {
        "task_family",
        "inputs_for_each_run",
        "required_outputs",
        "reusable_process",
        "policies",
        "failure_handling",
        "delegation_policy",
    }
    assert expected_sections.issubset(section_titles), (
        f"Missing sections: {expected_sections - section_titles}"
    )

    packet_types = {packet.packet_type for packet in canonical.semantic_packets}
    assert "task_family" in packet_types
    assert "runtime_input" in packet_types
    assert "required_output" in packet_types
    assert "process_step" in packet_types
    assert "policy" in packet_types
    assert "failure_mode" in packet_types
    assert "delegation_rule" in packet_types

    for packet in canonical.semantic_packets:
        assert packet.source_section_id, (
            f"Packet {packet.packet_id} ({packet.packet_type}) missing source_section_id"
        )


def test_structural_adapter_hard_facts_delegation_intents_populated() -> None:
    """F0 Baseline: delegation_policy section produces DelegationIntentFact in hard_facts."""
    canonical = StructuralNLAdapter().adapt(F0_STRUCTURAL_TEXT)

    intents = canonical.hard_facts.delegation_intents
    assert len(intents) >= 1, "Expected at least one delegation intent from delegation policy section"

    for intent in intents:
        assert intent.name
        assert intent.text
        assert intent.evidence
        has_section_evidence = any(
            ev.source_section_id == "sec_delegation_policy" for ev in intent.evidence
        )
        assert has_section_evidence, (
            f"Delegation intent '{intent.name}' missing evidence pointing to sec_delegation_policy"
        )


# ===========================================================================
# F1 Baseline: adapter hint and evidence strengthening
# ===========================================================================


def test_failure_hint_contract() -> None:
    """F1: failure handling CompileHint targets EXCEPTION_FLOW.condition with metadata."""
    canonical = StructuralNLAdapter().adapt(F0_STRUCTURAL_TEXT)

    failure_hints = [
        h for h in canonical.compile_hints.flow_hints
        if h.source_section_id == "sec_failure_handling"
    ]
    assert len(failure_hints) >= 1, "Expected at least one failure flow hint"

    for hint in failure_hints:
        assert hint.target == "EXCEPTION_FLOW", (
            f"Hint target should be EXCEPTION_FLOW, got {hint.target}"
        )
        assert hint.suggested_flow == "exception"
        assert hint.suggested_condition == hint.text, (
            f"suggested_condition ({hint.suggested_condition}) should match text ({hint.text})"
        )
        assert hint.metadata.get("route_family") == "flow_relevant"
        assert hint.metadata.get("slot_target") == "condition"
        assert hint.metadata.get("semantic_role") == "failure_mode"
        assert hint.metadata.get("executable") is False

        has_packet_evidence = any(
            ev.source_packet_id and ev.source_packet_id.startswith("p_failure_mode_")
            for ev in hint.evidence
        )
        assert has_packet_evidence, (
            f"Hint evidence missing source_packet_id: {hint.evidence}"
        )


def test_failure_packet_compile_target() -> None:
    """F1: failure_mode packets target flow.exception.condition, not bare flow.exception."""
    canonical = StructuralNLAdapter().adapt(F0_STRUCTURAL_TEXT)

    failure_packets = [
        p for p in canonical.semantic_packets
        if p.packet_type == "failure_mode"
    ]
    assert len(failure_packets) >= 1, "Expected at least one failure_mode packet"

    for packet in failure_packets:
        assert "flow.exception.condition" in packet.compile_targets, (
            f"failure_mode packet {packet.packet_id} missing flow.exception.condition "
            f"in compile_targets: {packet.compile_targets}"
        )


def test_hard_fact_packet_evidence() -> None:
    """F1: hard facts carry source_packet_id and quoted_text in evidence refs."""
    canonical = StructuralNLAdapter().adapt(F0_STRUCTURAL_TEXT)

    def _check_evidence(facts: list, label: str) -> None:
        assert len(facts) >= 1, f"Expected at least one {label} fact"
        found_packet_evidence = False
        for fact in facts:
            for ev in fact.evidence:
                if ev.source_packet_id and ev.quoted_text:
                    found_packet_evidence = True
                    break
        assert found_packet_evidence, (
            f"No {label} fact has evidence with both source_packet_id and quoted_text"
        )

    _check_evidence(canonical.hard_facts.inputs, "input")
    _check_evidence(canonical.hard_facts.outputs, "output")
    _check_evidence(canonical.hard_facts.failure_modes, "failure_mode")
    _check_evidence(canonical.hard_facts.delegation_intents, "delegation_intent")


def test_delegation_non_executable_contract() -> None:
    """F1: delegation hints declare non-executable, requires-contract semantics."""
    canonical = StructuralNLAdapter().adapt(F0_STRUCTURAL_TEXT)

    delegation_hints = canonical.compile_hints.delegation_hints
    assert len(delegation_hints) >= 1, "Expected at least one delegation hint"

    for hint in delegation_hints:
        assert hint.metadata.get("semantic_role") == "delegation_intent", (
            f"Unexpected semantic_role: {hint.metadata.get('semantic_role')}"
        )
        assert hint.metadata.get("route_family") == "delegation_boundary"
        assert hint.metadata.get("requires_contract") is True
        assert hint.metadata.get("executable") is False

        has_packet_evidence = any(
            ev.source_packet_id and ev.source_packet_id.startswith("p_delegation_rule_")
            for ev in hint.evidence
        )
        assert has_packet_evidence, (
            f"Delegation hint evidence missing source_packet_id: {hint.evidence}"
        )


def test_input_output_packets_non_executable_resource_contract() -> None:
    """F1: runtime_input / required_output packets declare non-executable resource contract."""
    canonical = StructuralNLAdapter().adapt(F0_STRUCTURAL_TEXT)

    input_packets = [p for p in canonical.semantic_packets if p.packet_type == "runtime_input"]
    output_packets = [p for p in canonical.semantic_packets if p.packet_type == "required_output"]

    assert len(input_packets) >= 1, "Expected at least one runtime_input packet"
    assert len(output_packets) >= 1, "Expected at least one required_output packet"

    for packet in input_packets:
        assert packet.metadata.get("route_family") == "resource_contract", (
            f"Input packet {packet.packet_id}: expected route_family=resource_contract"
        )
        assert packet.metadata.get("semantic_role") == "input_contract", (
            f"Input packet {packet.packet_id}: expected semantic_role=input_contract"
        )
        assert packet.metadata.get("executable") is False, (
            f"Input packet {packet.packet_id}: expected executable=False"
        )

    for packet in output_packets:
        assert packet.metadata.get("route_family") == "resource_contract", (
            f"Output packet {packet.packet_id}: expected route_family=resource_contract"
        )
        assert packet.metadata.get("semantic_role") == "output_contract", (
            f"Output packet {packet.packet_id}: expected semantic_role=output_contract"
        )
        assert packet.metadata.get("executable") is False, (
            f"Output packet {packet.packet_id}: expected executable=False"
        )
