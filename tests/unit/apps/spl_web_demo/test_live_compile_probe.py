from __future__ import annotations

import json
import sys
from argparse import Namespace
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "apps" / "spl-web-demo" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from contract_probe.live_compile_probe import _parse_args  # noqa: E402
from contract_probe.live_compile_smoke import (  # noqa: E402
    _build_pipeline_config,
    run_live_compile_smoke_case,
)


@dataclass
class FakePipelineResult:
    spl_text: str = "[DEFINE_AGENT: Demo]"
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    compile_diagnostics: list[Any] = field(default_factory=list)
    traces: list[Any] = field(default_factory=list)
    adapter_warnings: list[str] = field(default_factory=list)
    assumptions: list[Any] = field(default_factory=list)
    completeness: str = "partial"
    final_spl_path: Path | None = None
    final_ir_package: object | None = object()
    rendered_artifacts: tuple[Any, ...] = ()
    spl_editing_snapshot_path: Path | None = None
    spl_editing_snapshot_status: str = "available"
    spl_editing_snapshot_error: str | None = None
    spl_editing_explanation_status: str = "not_requested"
    spl_editing_explanation_error: str | None = None


class FakeReport:
    def __init__(self) -> None:
        self.records: dict[str, Any] = {}
        self.passes: list[tuple[str, str]] = []
        self.failures: list[tuple[str, str]] = []

    def record(self, key: str, value: Any) -> None:
        self.records[key] = value

    def pass_(self, check: str, message: str) -> None:
        self.passes.append((check, message))

    def fail(self, check: str, message: str) -> None:
        self.failures.append((check, message))


class FakeApi:
    def from_snapshot(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        assert Path(payload["snapshot_path"]).exists()
        return 200, {
            "run_id": "demo",
            "snapshot_id": "snap-demo",
            "snapshot_status": "available",
            "editing_available": True,
        }

    def get_run(self, run_id: str) -> tuple[int, dict[str, Any]]:
        assert run_id == "demo"
        return 200, {"projection_status": "available"}

    def get_spl(self, run_id: str) -> tuple[int, dict[str, Any]]:
        assert run_id == "demo"
        return 200, {
            "projection_status": "available",
            "rendered_spl": "[DEFINE_AGENT: Demo]",
        }

    def list_constructs(self, run_id: str) -> tuple[int, dict[str, Any]]:
        assert run_id == "demo"
        return 200, {
            "projection_status": "available",
            "constructs": [{"construct_ref": "worker-demo"}],
        }

    def list_issues(self, run_id: str) -> tuple[int, dict[str, Any]]:
        assert run_id == "demo"
        return 200, {
            "sections": [
                {
                    "section_id": "editable",
                    "items": [{"issue_id": "issue-1"}],
                }
            ]
        }


def _args(*, attempts: int = 1, budget: float = 120.0) -> Namespace:
    return Namespace(
        raw_text="Create a source-backed internal newsletter workflow.",
        input_file=None,
        compile_attempts=attempts,
        sync_budget_seconds=budget,
    )


def test_live_compile_smoke_records_success_rate_and_registration(tmp_path: Path) -> None:
    report = FakeReport()

    def compile_once(raw_text: str, attempt_dir: Path, attempt_number: int):
        assert raw_text.startswith("Create a source-backed")
        snapshot_path = attempt_dir / "spl_editing_snapshot.json"
        snapshot_path.write_text("{}", encoding="utf-8")
        return (
            FakePipelineResult(
                final_spl_path=attempt_dir / "final_spl.txt",
                spl_editing_snapshot_path=snapshot_path,
            ),
            float(attempt_number * 10),
        )

    status = run_live_compile_smoke_case(
        _args(attempts=2, budget=25.0),
        tmp_path,
        report,
        repo_root=REPO_ROOT,
        compile_once=compile_once,
        api_factory=FakeApi,
    )

    assert status == "pass"
    assert report.records["compile_attempts_succeeded"] == 2
    assert report.records["compile_success_rate"] == 1.0
    assert report.records["transport_recommendation"] == "synchronous_candidate"
    summary = json.loads((tmp_path / "live_compile_smoke.summary.json").read_text())
    assert summary["attempts_succeeded"] == 2
    assert summary["attempts"][0]["web_demo_registration"]["construct_count"] == 1
    assert summary["attempts"][0]["web_demo_registration"]["issue_count"] == 1
    field_names = {
        item["name"] for item in summary["attempts"][0]["pipeline_result"]["pipeline_result_fields"]
    }
    assert "spl_editing_snapshot_status" in field_names
    assert "final_ir_package" in field_names


def test_live_compile_smoke_rejects_empty_initial_construct_projection(tmp_path: Path) -> None:
    report = FakeReport()

    class EmptyConstructApi(FakeApi):
        def list_constructs(self, run_id: str) -> tuple[int, dict[str, Any]]:
            assert run_id == "demo"
            return 200, {"projection_status": "available", "constructs": []}

    def compile_once(_raw_text: str, attempt_dir: Path, _attempt_number: int):
        snapshot_path = attempt_dir / "spl_editing_snapshot.json"
        snapshot_path.write_text("{}", encoding="utf-8")
        return FakePipelineResult(spl_editing_snapshot_path=snapshot_path), 10.0

    status = run_live_compile_smoke_case(
        _args(),
        tmp_path,
        report,
        repo_root=REPO_ROOT,
        compile_once=compile_once,
        api_factory=EmptyConstructApi,
    )

    assert status == "fail"
    summary = json.loads((tmp_path / "live_compile_smoke.summary.json").read_text())
    registration = summary["attempts"][0]["web_demo_registration"]
    assert registration["status"] == "fail"
    assert registration["construct_count"] == 0


def test_live_compile_smoke_fails_closed_when_snapshot_is_unavailable(tmp_path: Path) -> None:
    report = FakeReport()
    api_factory_calls = 0

    def compile_once(_raw_text: str, _attempt_dir: Path, _attempt_number: int):
        return (
            FakePipelineResult(
                spl_editing_snapshot_path=None,
                spl_editing_snapshot_status="unavailable",
                spl_editing_snapshot_error="projection failed",
            ),
            130.0,
        )

    def api_factory() -> FakeApi:
        nonlocal api_factory_calls
        api_factory_calls += 1
        return FakeApi()

    status = run_live_compile_smoke_case(
        _args(budget=120.0),
        tmp_path,
        report,
        repo_root=REPO_ROOT,
        compile_once=compile_once,
        api_factory=api_factory,
    )

    assert status == "fail"
    assert api_factory_calls == 0
    assert report.records["compile_success_rate"] == 0.0
    assert report.records["transport_recommendation"] == "async_job_recommended"
    summary = json.loads((tmp_path / "live_compile_smoke.summary.json").read_text())
    assert summary["attempts"][0]["reason"] == "snapshot_unavailable"


def test_live_compile_config_disables_explanation_precompute(tmp_path: Path) -> None:
    config = _build_pipeline_config(tmp_path, 1)

    assert config.snapshot.enabled is True
    assert config.snapshot.precompute_issue_explanations is False
    assert config.run_name == "live_compile_smoke_01"
    assert config.stage1.mode in {
        "legacy_packet_passthrough",
        "llm_source_constrained_shadow",
        "llm_source_constrained",
        "deterministic_fallback_only",
    }


def test_live_compile_probe_cli_exposes_attempts_and_sync_budget() -> None:
    args = _parse_args(
        [
            "--raw-text",
            "Create a demo workflow.",
            "--compile-attempts",
            "3",
            "--sync-budget-seconds",
            "90",
        ]
    )

    assert args.raw_text == "Create a demo workflow."
    assert args.compile_attempts == 3
    assert args.sync_budget_seconds == 90.0
