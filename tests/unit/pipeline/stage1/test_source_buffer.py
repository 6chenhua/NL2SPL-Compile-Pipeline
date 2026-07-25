"""Unit tests for Stage 1 Source Buffer Reconstruction and Provenance Mapping."""

from __future__ import annotations

from nl2spl.canonical import CanonicalCompileInput, SemanticPacket
from nl2spl.pipeline.stages.stage1_segmentation.source_buffer import SourceSectionReconstructor


def test_source_reconstruction_normalization_and_mapping() -> None:
    # 1. Prepare semantic packets with soft line breaks and multiple spaces
    packet1 = SemanticPacket(
        packet_id="p1",
        source_section_id="sec_process",
        packet_type="process_step",
        text="If sources are needed and available,\r\nretrieve them using approved source\nrecipes.",
        modality="hard_fact",
    )
    packet2 = SemanticPacket(
        packet_id="p2",
        source_section_id="sec_process",
        packet_type="process_step",
        text="Maintain provenance  for externally sourced facts.",  # double spaces
        modality="hard_fact",
    )
    packet3 = SemanticPacket(
        packet_id="p3",
        source_section_id="sec_process",
        packet_type="process_step",
        text="When enough required information is available",
        modality="hard_fact",
    )
    # Packet in a different section
    packet4 = SemanticPacket(
        packet_id="p4",
        source_section_id="sec_policies",
        packet_type="policy",
        text="Do not invent facts.",
        modality="hard_fact",
    )

    canonical_input = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0.0",
        raw_text="dummy raw text",
        semantic_packets=[packet1, packet2, packet3, packet4],
    )

    reconstructor = SourceSectionReconstructor()
    buffers = reconstructor.reconstruct(canonical_input)

    # Assert section separation
    assert "sec_process" in buffers
    assert "sec_policies" in buffers

    process_buffer = buffers["sec_process"]
    # Check normalization policies:
    # - soft line breaks to space
    # - multiple spaces reduced to single space
    # - packets joined with single space, no auto comma insertion
    expected_text = (
        "If sources are needed and available, retrieve them using approved source recipes. "
        "Maintain provenance for externally sourced facts. "
        "When enough required information is available"
    )
    assert process_buffer.normalized_text == expected_text

    # Verify parent packet id mapping via range queries
    # Query 1: fully within packet 1
    idx1 = process_buffer.normalized_text.index("retrieve them using approved")
    parent_ids = process_buffer.get_parent_packet_ids(idx1, idx1 + 10)
    assert parent_ids == ("p1",)

    # Query 2: fully within packet 2
    idx2 = process_buffer.normalized_text.index("Maintain provenance")
    parent_ids = process_buffer.get_parent_packet_ids(idx2, idx2 + 10)
    assert parent_ids == ("p2",)

    # Query 3: spans packet 2 and packet 3 (across the space separator)
    # "facts. When enough"
    idx3 = process_buffer.normalized_text.index("facts. When enough")
    parent_ids = process_buffer.get_parent_packet_ids(idx3, idx3 + len("facts. When enough"))
    assert set(parent_ids) == {"p2", "p3"}

    # Query 4: spans packet 1 and packet 2
    idx4 = process_buffer.normalized_text.index("recipes. Maintain")
    parent_ids = process_buffer.get_parent_packet_ids(idx4, idx4 + len("recipes. Maintain"))
    assert set(parent_ids) == {"p1", "p2"}

    # Assert cross-section no merge
    policy_buffer = buffers["sec_policies"]
    assert policy_buffer.normalized_text == "Do not invent facts."
    assert len(policy_buffer.packet_ranges) == 1
    assert policy_buffer.packet_ranges[0].packet_id == "p4"
