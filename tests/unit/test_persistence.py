"""Unit tests for persistence helpers."""

from __future__ import annotations

from pathlib import Path

from nl2spl.utils.persistence import save_final_spl, save_intermediate_result


def test_save_intermediate_result_uses_stable_filename(tmp_path: Path) -> None:
    """Intermediate results use the stage name without a filename timestamp."""
    filepath = save_intermediate_result("stage1_span_slicer", {"spans": []}, tmp_path)

    assert filepath == tmp_path / "stage1_span_slicer.json"
    assert filepath.exists()


def test_save_final_spl_writes_utf8_text(tmp_path: Path) -> None:
    """Final SPL is saved as a UTF-8 text file."""
    spl_text = "[DEFINE_AGENT: Test \"测试\"]\n[END_AGENT]"

    filepath = save_final_spl(spl_text, tmp_path)

    assert filepath == tmp_path / "final_spl.txt"
    assert filepath.read_text(encoding="utf-8") == spl_text


def test_save_final_spl_overwrites_existing_file(tmp_path: Path) -> None:
    """Saving final SPL twice overwrites the previous content."""
    filepath = save_final_spl("old", tmp_path)

    second_path = save_final_spl("new", tmp_path)

    assert second_path == filepath
    assert filepath.read_text(encoding="utf-8") == "new"
