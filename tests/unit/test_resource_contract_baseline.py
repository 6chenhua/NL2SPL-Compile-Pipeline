"""Phase 0 baseline tests for resource contract refactor.

These tests capture the CURRENT behavior of the pipeline with respect to
resource contract handling.  They document the failure chain where
``Finished draft (Word or Google Doc...)`` is materialized as a text variable
instead of a file resource.

These tests should PASS against the current codebase.  After Phase 1-6
implementation, they will be updated to reflect the new expected behavior.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nl2spl.adapters.structural_nl import StructuralNLAdapter

# =============================================================================
# Fixture helpers
# =============================================================================

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "resource_contract"


def _load_fixture(name: str) -> str:
    """Load a resource-contract fixture by filename."""
    path = FIXTURE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    return path.read_text(encoding="utf-8")


INTERNAL_COMMS_MD = _load_fixture("internal_comms_required_outputs.md")


# =============================================================================
# Baseline 1: Adapter still writes to hard_facts.outputs
# =============================================================================


def test_adapter_no_longer_writes_hard_facts_by_default() -> None:
    """Phase 6: Adapter no longer writes hard_facts.inputs/outputs by default.

    Resource contract demands now flow through ResourceContractPlan instead.
    """
    canonical = StructuralNLAdapter(None).adapt(INTERNAL_COMMS_MD)

    assert not canonical.hard_facts.outputs, (
        "hard_facts.outputs should be empty by default after Phase 6"
    )
    assert not canonical.hard_facts.inputs, (
        "hard_facts.inputs should be empty by default after Phase 6"
    )


def test_adapter_hard_facts_legacy_path_still_works_when_enabled() -> None:
    """Phase 6: Legacy hard_facts path still works with enable_hard_facts=True."""
    canonical = StructuralNLAdapter(
        None, enable_hard_facts=True,
    ).adapt(INTERNAL_COMMS_MD)

    assert canonical.hard_facts.outputs, (
        "hard_facts.outputs should be populated when legacy path is enabled"
    )
    output_names = {f.name for f in canonical.hard_facts.outputs}
    assert "finished_draft_word_or_google_doc_200_500_words_no_approval_marks" in output_names

    assert canonical.hard_facts.inputs
    input_names = {f.name for f in canonical.hard_facts.inputs}
    assert "topic_summary" in input_names


def test_adapter_semantic_packets_still_produced() -> None:
    """Phase 6: Semantic packets are still produced regardless of hard_facts flag."""
    canonical = StructuralNLAdapter(None).adapt(INTERNAL_COMMS_MD)
    # Semantic packets (list items, sentences) are adapter's core output
    assert canonical.semantic_packets, "semantic_packets must always be produced"
    packet_types = {p.packet_type for p in canonical.semantic_packets}
    assert "list_item" in packet_types


# =============================================================================
# Baseline 3: Current demo SPL has finished_draft in [DEFINE_VARIABLES:] only
# =============================================================================


def _load_demo_file(filename: str) -> str:
    """Load a file from the demo output directory."""
    demo_dir = Path(__file__).parent.parent.parent / "examples" / "output" / "demo"
    path = demo_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"Demo file not found: {path}")
    return path.read_text(encoding="utf-8")


def test_final_spl_has_finished_draft_in_files_not_variables() -> None:
    """Phase 7: finished_draft now appears in [DEFINE_FILES:] as a file resource.

    This is the target behavior — ``Finished draft (Word or Google Doc...)``
    is materialized as a file output with ``< >`` runtime path.
    """
    spl = _load_demo_file("final_spl.txt")

    assert "[DEFINE_FILES:]" in spl, "Expected [DEFINE_FILES:] section"
    files_section = spl.split("[DEFINE_FILES:]")[1].split("[END_FILES]")[0]

    # finished_draft MUST appear in files section
    assert "finished_draft" in files_section, (
        "Target: finished_draft must appear in [DEFINE_FILES:]"
    )

    # Verify the file declaration format: name < >: type
    finished_draft_line = next(
        line for line in files_section.splitlines()
        if "finished_draft" in line
    )
    assert "< >" in finished_draft_line, (
        f"Expected '< >' runtime path marker, got: {finished_draft_line!r}"
    )
    assert ": text" in finished_draft_line, (
        f"Expected ': text' type, got: {finished_draft_line!r}"
    )


def test_demo_files_section_contains_finished_draft() -> None:
    """Phase 7: [DEFINE_FILES:] now contains the finished draft file resource."""
    spl = _load_demo_file("final_spl.txt")
    files_section = spl.split("[DEFINE_FILES:]")[1].split("[END_FILES]")[0]

    # finished_draft must be present as a file resource
    assert "finished_draft" in files_section, (
        "Target: finished_draft output must appear in [DEFINE_FILES:]"
    )


# =============================================================================
# Baseline 4: Feedback report provenance — updated for Phase 7
# =============================================================================


def test_feedback_report_mentions_finished_draft() -> None:
    """Phase 7: The feedback report still mentions finished_draft."""
    report = _load_demo_file("feedback_report.md")
    assert "finished_draft" in report, (
        "Expected finished_draft to be mentioned in feedback report"
    )
    # Verify it appears as a file declaration in the SPL draft section
    assert "finished_draft < >: text" in report, (
        "Expected finished_draft file declaration in SPL draft section"
    )


def test_feedback_report_spl_draft_has_define_files() -> None:
    """Phase 7: The SPL draft in feedback report has [DEFINE_FILES:] section."""
    report = _load_demo_file("feedback_report.md")
    assert "[DEFINE_FILES:]" in report
    assert "[END_FILES]" in report
