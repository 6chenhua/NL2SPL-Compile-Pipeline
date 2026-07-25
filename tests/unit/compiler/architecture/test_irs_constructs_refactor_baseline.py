from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
SNAPSHOT_SCRIPT = ROOT / "scripts" / "dev" / "snapshot_irs_constructs_refactor.py"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "irs_constructs_refactor"


def _load_snapshot_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "snapshot_irs_constructs_refactor",
        SNAPSHOT_SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_fixture(filename: str) -> Any:
    path = FIXTURE_DIR / filename
    if filename.endswith(".json"):
        return json.loads(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


def test_phase0_snapshots_match_current_behavior() -> None:
    snapshots = _load_snapshot_module().build_all_snapshots()
    for filename, current in snapshots.items():
        if filename == "import_boundary_baseline.json":
            continue
        assert current == _read_fixture(filename), filename


def test_phase0_baseline_records_required_artifacts() -> None:
    registry_shape = _read_fixture("construct_registry_shape.json")
    construct_types = {entry["construct_type"] for entry in registry_shape}
    assert "EXCEPTION_FLOW" in construct_types
    assert "RESOURCE_CONTRACT_DEMAND" in construct_types

    catalog_entries = _read_fixture("repair_catalog_entries.json")
    entry_ids = {entry["entry_id"] for entry in catalog_entries}
    assert (
        "EXCEPTION_FLOW.handler_action.missing_handler."
        "exception_flow.add_handler_step"
    ) in entry_ids

    diagnostic_registry = _read_fixture("diagnostic_registry_kinds.json")
    assert "missing_handler" in diagnostic_registry["enabled"]

    prompts = _read_fixture("stage_prompt_snapshots.json")
    assert "EXCEPTION_FLOW" in prompts["stage4"]
    assert "GENERAL_COMMAND" in prompts["stage7"]

    report = _read_fixture("report_renderer_snapshot.txt")
    assert "NL2SPL Compile Report" in report
    assert "missing_handler" in report
