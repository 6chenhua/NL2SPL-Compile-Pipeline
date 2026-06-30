"""Current resource-contract baseline tests.

These tests intentionally describe the checked-in demo artifacts as they exist
today.  File-resource materialization for ``finished_draft`` is outside the API
materialization review scope and should be covered by its own resource-contract
phase when that artifact is regenerated.
"""

from __future__ import annotations

from pathlib import Path

from nl2spl.adapters.structural_nl import StructuralNLAdapter


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "resource_contract"


def _load_fixture(name: str) -> str:
    path = FIXTURE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    return path.read_text(encoding="utf-8")


INTERNAL_COMMS_MD = _load_fixture("internal_comms_required_outputs.md")


def test_adapter_no_longer_writes_hard_facts_by_default() -> None:
    """Resource contract demands flow through ResourceContractPlan by default."""
    canonical = StructuralNLAdapter(None).adapt(INTERNAL_COMMS_MD)

    assert not canonical.hard_facts.outputs
    assert not canonical.hard_facts.inputs


def test_adapter_hard_facts_legacy_path_still_works_when_enabled() -> None:
    """Legacy hard_facts path still works when explicitly enabled."""
    canonical = StructuralNLAdapter(
        None,
        enable_hard_facts=True,
    ).adapt(INTERNAL_COMMS_MD)

    output_names = {f.name for f in canonical.hard_facts.outputs}
    assert (
        "finished_draft_word_or_google_doc_200_500_words_no_approval_marks"
        in output_names
    )

    input_names = {f.name for f in canonical.hard_facts.inputs}
    assert "topic_summary" in input_names


def test_adapter_semantic_packets_still_produced() -> None:
    """Semantic packets are produced regardless of hard_facts mode."""
    canonical = StructuralNLAdapter(None).adapt(INTERNAL_COMMS_MD)

    assert canonical.semantic_packets
    packet_types = {p.packet_type for p in canonical.semantic_packets}
    assert "list_item" in packet_types


def _load_demo_file(filename: str) -> str:
    demo_dir = Path(__file__).parent.parent.parent / "examples" / "output" / "demo"
    path = demo_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"Demo file not found: {path}")
    return path.read_text(encoding="utf-8")


def test_final_spl_current_demo_has_no_file_resource_section() -> None:
    """Current checked-in demo output has no [DEFINE_FILES:] section."""
    spl = _load_demo_file("final_spl.txt")

    assert "[DEFINE_FILES:]" not in spl
    assert "[END_FILES]" not in spl


def test_current_demo_does_not_claim_finished_draft_file_resource() -> None:
    """Current checked-in demo does not contain the future finished_draft file."""
    spl = _load_demo_file("final_spl.txt")

    assert "finished_draft < >: text" not in spl
    assert "finished_draft_word_or_google_doc_200_500_words_no_approval_marks" not in spl


def test_feedback_report_matches_current_demo_without_finished_draft() -> None:
    """Current checked-in feedback report mirrors the demo SPL draft."""
    report = _load_demo_file("feedback_report.md")

    assert "finished_draft < >: text" not in report
    assert "finished_draft_word_or_google_doc_200_500_words_no_approval_marks" not in report


def test_feedback_report_spl_draft_has_no_define_files_section() -> None:
    """Current checked-in feedback report has no [DEFINE_FILES:] section."""
    report = _load_demo_file("feedback_report.md")

    assert "[DEFINE_FILES:]" not in report
    assert "[END_FILES]" not in report
