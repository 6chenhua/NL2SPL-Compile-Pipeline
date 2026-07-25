"""R16 static audits for R12+ strategy/stage-slice architecture."""

from __future__ import annotations

import pathlib


def _read_tree(*roots: str):
    for root in roots:
        base = pathlib.Path(root)
        if base.exists():
            for py_file in base.glob("**/*.py"):
                yield py_file, py_file.read_text(encoding="utf-8")


def test_no_direct_ir_construction_in_patches_or_materialization() -> None:
    forbidden = ("StepIR(", "BlockIR(", "WorkerHandoffIR(")
    offenders = []
    for path, source in _read_tree(
        "src/nl2spl/compiler/spl_editing/patches",
        "src/nl2spl/compiler/spl_editing/materialization",
    ):
        for token in forbidden:
            if token in source:
                offenders.append(f"{path}:{token}")
    assert offenders == []


def test_no_diagnostic_message_parsing_in_materialization_or_stage_slices() -> None:
    offenders = [
        str(path)
        for path, source in _read_tree(
            "src/nl2spl/compiler/spl_editing/materialization",
            "src/nl2spl/compiler/spl_editing/stage_slices",
        )
        if "diagnostic.message" in source
    ]
    assert offenders == []


def test_old_exception_handler_materializer_name_removed_from_production_code() -> None:
    offenders = [
        str(path)
        for path, source in _read_tree("src/nl2spl/compiler/spl_editing")
        if "Stage7ExceptionHandlerStepMaterializer" in source
    ]
    assert offenders == []


def test_cli_default_flow_requires_preview_apply() -> None:
    source = pathlib.Path("src/nl2spl/compiler/spl_editing/cli.py").read_text(encoding="utf-8")
    assert ".preview_suggestion(" in source
    assert ".apply_preview_result(" in source
    assert ".apply_suggestion(" not in source
