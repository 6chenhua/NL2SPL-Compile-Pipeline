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
