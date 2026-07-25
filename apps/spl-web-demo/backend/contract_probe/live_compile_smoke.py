"""Live compile smoke case for the SPL Web Demo contract probe."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import traceback
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[4]


class ProbeReportLike(Protocol):
    def record(self, key: str, value: Any) -> None: ...

    def pass_(self, check: str, message: str) -> None: ...

    def fail(self, check: str, message: str) -> None: ...


CompileOnce = Callable[[str, Path, int], tuple[Any, float]]
ApiFactory = Callable[[], Any]


def run_live_compile_smoke_case(
    args: Any,
    output_dir: Path,
    report: ProbeReportLike,
    *,
    repo_root: Path,
    compile_once: CompileOnce | None = None,
    api_factory: ApiFactory | None = None,
) -> str:
    """Run compile -> snapshot -> Web Demo registration without repair assumptions."""

    raw_text, input_source = _resolve_input(args, repo_root)
    attempts_requested = _positive_int(getattr(args, "compile_attempts", 1), "compile_attempts")
    sync_budget = _positive_float(
        getattr(args, "sync_budget_seconds", 120.0),
        "sync_budget_seconds",
    )
    compile_runner = compile_once or _compile_once
    resolved_api_factory = api_factory or _default_api_factory(repo_root)

    report.record("case", "live_compile_smoke")
    report.record("input_source", input_source)
    report.record("input_length", len(raw_text))
    report.record("input_sha256", hashlib.sha256(raw_text.encode("utf-8")).hexdigest())
    report.record("compile_attempts_requested", attempts_requested)
    report.record("sync_budget_seconds", sync_budget)

    attempt_summaries: list[dict[str, Any]] = []
    elapsed_values: list[float] = []
    successes = 0

    for attempt_number in range(1, attempts_requested + 1):
        attempt_dir = output_dir / f"live-compile-attempt-{attempt_number:02d}"
        attempt_dir.mkdir(parents=True, exist_ok=False)
        summary = _run_attempt(
            raw_text,
            attempt_dir,
            attempt_number,
            compile_runner,
            resolved_api_factory,
        )
        attempt_summaries.append(summary)
        elapsed = summary.get("compile_elapsed_seconds")
        if isinstance(elapsed, (int, float)):
            elapsed_values.append(float(elapsed))
        if summary.get("status") == "pass":
            successes += 1

    success_rate = successes / attempts_requested
    max_elapsed = max(elapsed_values) if elapsed_values else None
    transport_recommendation = (
        "synchronous_candidate"
        if max_elapsed is not None and max_elapsed <= sync_budget
        else "async_job_recommended"
    )
    case_summary = {
        "schema_version": "spl_web_demo.live_compile_smoke.v1",
        "status": "pass" if successes == attempts_requested else "fail",
        "input_source": input_source,
        "input_length": len(raw_text),
        "input_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "attempts_requested": attempts_requested,
        "attempts_succeeded": successes,
        "success_rate": success_rate,
        "compile_elapsed_seconds": elapsed_values,
        "max_compile_elapsed_seconds": max_elapsed,
        "sync_budget_seconds": sync_budget,
        "transport_recommendation": transport_recommendation,
        "attempts": attempt_summaries,
    }
    _write_json(output_dir / "live_compile_smoke.summary.json", case_summary)

    report.record("compile_attempts_succeeded", successes)
    report.record("compile_success_rate", success_rate)
    report.record("max_compile_elapsed_seconds", max_elapsed)
    report.record("transport_recommendation", transport_recommendation)
    if successes == attempts_requested:
        report.pass_(
            "live_compile_smoke",
            f"{successes}/{attempts_requested} compile attempts produced registrable snapshots.",
        )
        return "pass"

    report.fail(
        "live_compile_smoke",
        f"Only {successes}/{attempts_requested} compile attempts produced registrable snapshots.",
    )
    return "fail"


def _run_attempt(
    raw_text: str,
    attempt_dir: Path,
    attempt_number: int,
    compile_once: CompileOnce,
    api_factory: ApiFactory,
) -> dict[str, Any]:
    try:
        result, elapsed = compile_once(raw_text, attempt_dir, attempt_number)
        pipeline_summary = _pipeline_result_summary(result, elapsed)
        _write_json(attempt_dir / "pipeline_result.summary.json", pipeline_summary)

        snapshot_path = getattr(result, "spl_editing_snapshot_path", None)
        snapshot_status = getattr(result, "spl_editing_snapshot_status", None)
        if snapshot_status != "available" or not snapshot_path:
            return {
                "attempt": attempt_number,
                "status": "fail",
                "reason": "snapshot_unavailable",
                "compile_elapsed_seconds": elapsed,
                "pipeline_result": pipeline_summary,
            }
        snapshot_path = Path(snapshot_path)
        if not snapshot_path.exists():
            return {
                "attempt": attempt_number,
                "status": "fail",
                "reason": "snapshot_path_missing",
                "compile_elapsed_seconds": elapsed,
                "pipeline_result": pipeline_summary,
            }

        registration = _register_with_web_demo(api_factory(), snapshot_path)
        _write_json(attempt_dir / "web_demo_registration.summary.json", registration)
        passed = registration["status"] == "pass"
        return {
            "attempt": attempt_number,
            "status": "pass" if passed else "fail",
            "reason": None if passed else "web_demo_registration_failed",
            "compile_elapsed_seconds": elapsed,
            "pipeline_result": pipeline_summary,
            "web_demo_registration": registration,
        }
    except Exception as exc:  # noqa: BLE001 - probe captures contract failures.
        (attempt_dir / "exception.txt").write_text(traceback.format_exc(), encoding="utf-8")
        return {
            "attempt": attempt_number,
            "status": "fail",
            "reason": "exception",
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }


def _compile_once(raw_text: str, attempt_dir: Path, attempt_number: int) -> tuple[Any, float]:
    from nl2spl.pipeline.orchestrator import PipelineOrchestrator

    config = _build_pipeline_config(attempt_dir, attempt_number)
    started = perf_counter()
    result = PipelineOrchestrator(config).run(raw_text)
    return result, perf_counter() - started


def _build_pipeline_config(attempt_dir: Path, attempt_number: int) -> Any:
    from spl_web_demo.compiler import build_live_pipeline_config

    return build_live_pipeline_config(
        repo_root=REPO_ROOT,
        output_root=attempt_dir / "pipeline-output",
        run_name=f"live_compile_smoke_{attempt_number:02d}",
        precompute_issue_explanations=False,
    )


def _default_api_factory(repo_root: Path) -> ApiFactory:
    def factory() -> Any:
        from spl_web_demo.bootstrap import build_local_demo_api

        return build_local_demo_api(repo_root=repo_root)

    return factory


def _register_with_web_demo(api: Any, snapshot_path: Path) -> dict[str, Any]:
    create_status, create_body = api.from_snapshot({"snapshot_path": str(snapshot_path)})
    if create_status != 200:
        return {
            "status": "fail",
            "create_status": create_status,
            "create_body": create_body,
        }

    run_id = create_body.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return {
            "status": "fail",
            "create_status": create_status,
            "create_body": create_body,
            "reason": "missing_run_id",
        }

    run_status, run_body = api.get_run(run_id)
    spl_status, spl_body = api.get_spl(run_id)
    construct_status, construct_body = api.list_constructs(run_id)
    issue_status, issue_body = api.list_issues(run_id)
    issue_count = sum(
        len(section.get("items", []))
        for section in issue_body.get("sections", [])
        if isinstance(section, dict)
    )
    statuses = (run_status, spl_status, construct_status, issue_status)
    construct_count = len(construct_body.get("constructs", []))
    rendered_spl_length = len(spl_body.get("rendered_spl") or "")
    projection_available = (
        run_body.get("projection_status") == "available"
        and spl_body.get("projection_status") == "available"
        and construct_body.get("projection_status") == "available"
    )
    initial_read_model_available = (
        create_body.get("snapshot_status") == "available"
        and create_body.get("editing_available") is True
        and rendered_spl_length > 0
        and construct_count > 0
    )
    passed = (
        all(status == 200 for status in statuses)
        and projection_available
        and initial_read_model_available
    )
    return {
        "status": "pass" if passed else "fail",
        "run_id": run_id,
        "snapshot_id": create_body.get("snapshot_id"),
        "snapshot_status": create_body.get("snapshot_status"),
        "editing_available": create_body.get("editing_available"),
        "projection_status": run_body.get("projection_status"),
        "construct_count": construct_count,
        "issue_count": issue_count,
        "rendered_spl_length": rendered_spl_length,
        "http_like_statuses": {
            "create": create_status,
            "run": run_status,
            "spl": spl_status,
            "constructs": construct_status,
            "issues": issue_status,
        },
    }


def _pipeline_result_summary(result: Any, elapsed: float) -> dict[str, Any]:
    fields = _result_field_manifest(result)
    return {
        "compile_elapsed_seconds": elapsed,
        "pipeline_result_fields": fields,
        "spl_length": len(getattr(result, "spl_text", "") or ""),
        "validation_errors": len(getattr(result, "validation_errors", ()) or ()),
        "validation_warnings": len(getattr(result, "validation_warnings", ()) or ()),
        "compile_diagnostics": len(getattr(result, "compile_diagnostics", ()) or ()),
        "traces": len(getattr(result, "traces", ()) or ()),
        "adapter_warnings": len(getattr(result, "adapter_warnings", ()) or ()),
        "assumptions": len(getattr(result, "assumptions", ()) or ()),
        "completeness": getattr(result, "completeness", None),
        "final_spl_path": _path_string(getattr(result, "final_spl_path", None)),
        "final_ir_package_available": getattr(result, "final_ir_package", None) is not None,
        "rendered_artifact_count": len(getattr(result, "rendered_artifacts", ()) or ()),
        "spl_editing_snapshot_path": _path_string(
            getattr(result, "spl_editing_snapshot_path", None)
        ),
        "spl_editing_snapshot_status": getattr(
            result,
            "spl_editing_snapshot_status",
            None,
        ),
        "spl_editing_snapshot_error": getattr(result, "spl_editing_snapshot_error", None),
        "spl_editing_explanation_status": getattr(
            result,
            "spl_editing_explanation_status",
            None,
        ),
        "spl_editing_explanation_error": getattr(
            result,
            "spl_editing_explanation_error",
            None,
        ),
    }


def _result_field_manifest(result: Any) -> list[dict[str, str]]:
    if dataclasses.is_dataclass(result):
        names = [field.name for field in dataclasses.fields(result)]
    else:
        names = sorted(key for key in vars(result) if not key.startswith("_"))
    return [
        {
            "name": name,
            "runtime_type": type(getattr(result, name, None)).__name__,
        }
        for name in names
    ]


def _resolve_input(args: Any, repo_root: Path) -> tuple[str, str]:
    raw_text = getattr(args, "raw_text", None)
    input_file = getattr(args, "input_file", None)
    if raw_text:
        return raw_text, "--raw-text"
    if input_file is None:
        input_file = (
            repo_root
            / "apps"
            / "spl-web-demo"
            / "backend"
            / "contract_probe"
            / "inputs"
            / "live_compile_smoke.txt"
        )
    input_path = Path(input_file)
    if not input_path.is_absolute():
        input_path = repo_root / input_path
    raw_text = input_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise ValueError("live compile smoke input must not be empty")
    return raw_text, str(input_path)


def _positive_int(value: Any, field_name: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{field_name} must be at least 1")
    return parsed


def _positive_float(value: Any, field_name: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return parsed


def _path_string(value: Any) -> str | None:
    return str(value) if value is not None else None


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
