from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_condition_refs_do_not_enter_step_relation_or_producer_authority() -> None:
    forbidden_files = [
        ROOT / "src/nl2spl/ir/step_variable_relation_ir.py",
        ROOT / "src/nl2spl/compiler/producer_index.py",
    ]

    for path in forbidden_files:
        text = path.read_text(encoding="utf-8")
        assert "ConditionVariableReference" not in text
        assert "condition_variable_reference" not in text


def test_renderer_does_not_parse_or_rewrite_condition_refs() -> None:
    renderer_root = ROOT / "src/nl2spl/pipeline/stages/stage11_spl_renderer"

    for path in renderer_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "reference_parser" not in text
        assert "parse_description_references" not in text
        assert "ConditionVariableReference" not in text
