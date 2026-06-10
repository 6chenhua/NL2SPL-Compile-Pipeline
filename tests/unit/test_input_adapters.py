"""Tests for canonical input adapters."""

from __future__ import annotations

from dataclasses import asdict

import pytest

from nl2spl.adapters import GenericNLAdapter, InputAdapterRegistry, StructuralNLAdapter
from nl2spl.adapters.morphology import ShapeGrammar, StructuralShapeDetector
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


def test_structural_adapter_detects_complete_input(mock_client) -> None:
    adapter = StructuralNLAdapter(mock_client)

    result = adapter.detect(STRUCTURAL_TEXT)

    assert result.matched is True
    assert result.schema_name == "structural_nl"
    assert "Inputs for each run" in result.matched_sections
    assert "Required outputs" in result.matched_sections
    assert not result.empty_sections
    assert "confidence" not in asdict(result)


def test_structural_adapter_records_missing_duplicate_and_empty_sections(mock_client) -> None:
    raw_text = """Task family:
Example.

Policies:

Policies:
Do not invent facts.
"""
    adapter = StructuralNLAdapter(mock_client)

    result = adapter.detect(raw_text)

    assert "Policies" in result.duplicate_sections
    assert "Policies" in result.empty_sections


def test_structural_adapter_accepts_reordered_sections_and_chinese_colon(mock_client) -> None:
    raw_text = """Required outputs：
A completion status.

Task family:
Example.

Inputs for each run:
A user request.
"""
    adapter = StructuralNLAdapter(mock_client)

    result = adapter.detect(raw_text)
    canonical = adapter.adapt(raw_text)

    assert result.matched is True
    assert [section.canonical_title for section in canonical.raw_sections] == [
        "required outputs",
        "task family",
        "inputs for each run",
    ]


def test_generic_freeform_uses_generic_adapter() -> None:
    registry = InputAdapterRegistry()

    canonical = registry.adapt("Please draft a concise update.")

    assert isinstance(registry.select_adapter("Please draft a concise update."), GenericNLAdapter)
    assert canonical.source_schema == "generic_nl"
    assert canonical.raw_text == "Please draft a concise update."
    assert canonical.raw_sections == []
    assert canonical.semantic_packets == []


def test_registry_constructs_structure_only_adapters() -> None:
    registry = InputAdapterRegistry()

    structural, generic = registry.adapters

    assert isinstance(structural, StructuralNLAdapter)
    assert isinstance(generic, GenericNLAdapter)
    assert not hasattr(structural, "_llm_client")
    assert not hasattr(generic, "_llm_client")

def test_structural_adapter_extracts_hard_facts_and_hints(mock_client) -> None:
    """F0 Baseline: adapter populates canonical input structure correctly with compat mode."""
    canonical = StructuralNLAdapter(
        mock_client, enable_hard_facts=True,
    ).adapt(F0_STRUCTURAL_TEXT)

    input_names = {fact.name for fact in canonical.hard_facts.inputs}
    output_names = {fact.name for fact in canonical.hard_facts.outputs}

    # Inputs/outputs remain hard facts; failure handling is route-driven.
    assert {"user_request", "known_topics", "timeframe"}.issubset(input_names)
    assert {
        "draft_communication_artifact",
        "source_evidence_set",
        "short_assumptions_log",
        "completion_status",
    }.issubset(output_names)
    assert not hasattr(canonical.hard_facts, "failure_modes")
    assert canonical.hard_facts.delegation_intents == []
    assert canonical.route_priors == []


def test_structural_adapter_filters_empty_markers_from_bridge_facts() -> None:
    canonical = StructuralNLAdapter(None).adapt(
        "Failure handling:\n**Blocking Failures:** None\n\n"
        "Delegation policy:\nN/A\n"
    )

    assert not hasattr(canonical.hard_facts, "failure_modes")
    assert canonical.hard_facts.delegation_intents == []


def test_structural_adapter_strips_inline_bold_failure_items() -> None:
    canonical = StructuralNLAdapter(None).adapt(
        "Anticipated Failures: **Missing inputs**, **tone mismatch**, **unverified facts**"
    )

    assert not hasattr(canonical.hard_facts, "failure_modes")
    # Adapter produces neutral packets only; semantic mapping is LLM's job
    packet_texts = [p.text for p in canonical.semantic_packets if p.packet_type == "list_item"]
    assert len(packet_texts) == 3


def test_structural_adapter_semantic_packets_cover_neutral_types(mock_client) -> None:
    """F0 Baseline: adapter produces all 7 canonical sections and neutral semantic packet types."""
    canonical = StructuralNLAdapter(mock_client).adapt(F0_STRUCTURAL_TEXT)

    section_titles = {section.canonical_title for section in canonical.raw_sections}
    expected_sections = {
        "task family",
        "inputs for each run",
        "required outputs",
        "reusable process",
        "policies",
        "failure handling",
        "delegation policy",
    }
    assert expected_sections.issubset(section_titles), (
        f"Missing sections: {expected_sections - section_titles}"
    )

    packet_types = {packet.packet_type for packet in canonical.semantic_packets}
    assert "list_item" in packet_types
    assert "failure_mode" not in packet_types
    assert "task_family" not in packet_types

    for packet in canonical.semantic_packets:
        assert packet.source_section_id, (
            f"Packet {packet.packet_id} ({packet.packet_type}) missing source_section_id"
        )


    # Structural adapter does not perform LLM semantic mapping.
    canonical = StructuralNLAdapter(None).adapt(F0_STRUCTURAL_TEXT)

    assert len(canonical.raw_sections) >= 7
    assert len(canonical.semantic_packets) > 0
    assert len(canonical.route_priors) == 0


def test_structural_adapter_chinese_colon_and_markdown() -> None:
    """Test that Chinese colons and Markdown headings properly parse."""
    text = "# Markdown Heading\nSome text.\n\nChinese Colon Heading：\nSome list item.\n"
    canonical = StructuralNLAdapter(None).adapt(text)

    section_titles = {section.original_title for section in canonical.raw_sections}
    assert "Markdown Heading" in section_titles
    assert "Chinese Colon Heading" in section_titles


def test_shape_grammar_accepts_punctuated_headings_and_key_value_sections() -> None:
    """Shape grammar should remain morphological, not limited to word-only headings."""
    assert ShapeGrammar.COLON_HEADING.match("Input/Output Policy:")
    assert ShapeGrammar.COLON_HEADING.match("Failure-handling：")
    assert ShapeGrammar.KEY_VALUE.match("Task family: Internal newsletters.")

    profile = StructuralShapeDetector.detect("Task family: Internal newsletters.")
    assert profile.has_key_value_blocks is True
    assert profile.is_highly_structured is True


def test_structural_adapter_parses_inline_key_value_sections() -> None:
    text = (
        "Task family: Internal newsletters.\n"
        "Inputs for each run: A user request.\n"
        "Required outputs: A draft artifact.\n"
    )

    canonical = StructuralNLAdapter(None).adapt(text)

    by_title = {section.canonical_title: section for section in canonical.raw_sections}
    assert by_title["task family"].text == "Internal newsletters."
    assert by_title["inputs for each run"].text == "A user request."
    assert by_title["required outputs"].text == "A draft artifact."


def test_structural_adapter_strips_markdown_from_inline_section_titles() -> None:
    text = (
        "**Scope:** Internal communications only.\n"
        "**Examples:** Draft an announcement.\n"
        "**Non-delegable:** Final approval remains with the communications lead.\n"
    )

    canonical = StructuralNLAdapter(None).adapt(text)

    by_title = {section.canonical_title: section for section in canonical.raw_sections}
    assert by_title["scope"].section_id == "sec_scope"
    assert by_title["examples"].section_id == "sec_examples"
    assert by_title["non-delegable"].section_id == "sec_non_delegable"
    for section in canonical.raw_sections:
        assert "*" not in section.canonical_title
        assert "*" not in section.section_id


def test_structural_adapter_does_not_warn_for_empty_document_title() -> None:
    text = (
        "# Internal Communications Drafting\n\n"
        "## Task Family\n\n"
        "Internal newsletters.\n"
    )

    canonical = StructuralNLAdapter(None).adapt(text)

    empty_warnings = [
        warning for warning in canonical.warnings
        if warning.code == "EMPTY_SECTION"
    ]
    assert empty_warnings == []


def test_key_value_content_under_heading_stays_in_parent_section() -> None:
    text = (
        "Failure handling:\n"
        "Missing timeframe: ask one clarifying question.\n\n"
        "Policies:\n"
        "Do not invent facts.\n"
    )

    canonical = StructuralNLAdapter(None).adapt(text)

    by_title = {section.canonical_title: section for section in canonical.raw_sections}
    assert "missing timeframe" not in by_title
    assert by_title["failure handling"].text == (
        "Missing timeframe: ask one clarifying question."
    )


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
