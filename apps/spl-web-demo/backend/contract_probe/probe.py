"""Contract probe for the SPL Web Demo service boundary.

The probe intentionally calls existing service/presentation APIs directly,
without HTTP.  By default it uses the checked-in demo snapshot so the SPL
Editing contract can be verified without requiring a live LLM-backed compile.
Pass --raw-text or --input-file to also exercise PipelineOrchestrator first.
"""

from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_SNAPSHOT = REPO_ROOT / "examples" / "output" / "demo" / "spl_editing_snapshot.json"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "apps" / "spl-web-demo" / ".probe-output"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = _make_output_dir(args.output_root)
    report = ProbeReport(output_dir)
    report.record("output_dir", str(output_dir))

    try:
        snapshot_path = _resolve_snapshot_path(args, output_dir, report)
        if snapshot_path is None:
            report.fail("pipeline", "No snapshot path was produced or provided.")
            return report.finish()
        report.record("snapshot_path", str(snapshot_path))

        editing_result = _probe_spl_editing(snapshot_path, output_dir, report, args)
        report.record("editing_probe_status", editing_result)
        return report.finish()
    except Exception as exc:  # noqa: BLE001 - probe should capture contract failures.
        report.fail("probe", f"{type(exc).__name__}: {exc}")
        (output_dir / "exception.txt").write_text(traceback.format_exc(), encoding="utf-8")
        return report.finish()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SPL Web Demo contract probe.")
    parser.add_argument(
        "--snapshot-path",
        type=Path,
        default=DEFAULT_SNAPSHOT,
        help="Existing spl_editing_snapshot.json to probe. Defaults to examples/output/demo.",
    )
    parser.add_argument(
        "--raw-text",
        help="Natural-language input. If set, the probe runs PipelineOrchestrator first.",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        help="File containing natural-language input for PipelineOrchestrator.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root directory for timestamped probe output.",
    )
    parser.add_argument(
        "--option-id",
        default="keep_in_main_flow",
        help="Repair option to probe for worker delegation.",
    )
    parser.add_argument(
        "--task-selection",
        default="source gathering",
        help="Value for the keep_in_main_flow task_selection field.",
    )
    parser.add_argument(
        "--skip-apply",
        action="store_true",
        help="Stop after preview generation.",
    )
    return parser.parse_args(argv)


def _make_output_dir(output_root: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = Path(output_root) / stamp
    out.mkdir(parents=True, exist_ok=False)
    return out


def _resolve_snapshot_path(
    args: argparse.Namespace,
    output_dir: Path,
    report: ProbeReport,
) -> Path | None:
    raw_text = args.raw_text
    if args.input_file is not None:
        raw_text = args.input_file.read_text(encoding="utf-8")
    if raw_text:
        return _run_pipeline(raw_text, output_dir, report)

    snapshot_path = Path(args.snapshot_path)
    if not snapshot_path.is_absolute():
        snapshot_path = REPO_ROOT / snapshot_path
    if not snapshot_path.exists():
        report.fail("snapshot", f"Snapshot path does not exist: {snapshot_path}")
        return None
    report.pass_("snapshot", "Using existing snapshot file.")
    return snapshot_path


def _run_pipeline(raw_text: str, output_dir: Path, report: ProbeReport) -> Path | None:
    from dotenv import load_dotenv

    from nl2spl.compiler.artifacts.snapshot.config import SnapshotPersistenceConfig
    from nl2spl.config import LLMConfig, Stage1SegmentationConfig, load_config
    from nl2spl.pipeline.orchestrator import PipelineOrchestrator

    load_dotenv()
    config = load_config(
        llm=LLMConfig(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "16000")),
        ),
        log_level="INFO",
        save_intermediate=True,
        output_dir=output_dir / "pipeline-output",
        run_name="contract_probe",
        snapshot=SnapshotPersistenceConfig(),
        stage1=Stage1SegmentationConfig(
            mode=os.getenv("NL2SPL_STAGE1_SEGMENTATION_MODE", "llm_source_constrained")
        ),
    )
    result = PipelineOrchestrator(config).run(raw_text)
    summary = {
        "spl_length": len(result.spl_text or ""),
        "validation_errors": len(result.validation_errors),
        "validation_warnings": len(result.validation_warnings),
        "compile_diagnostics": len(result.compile_diagnostics),
        "traces": len(result.traces),
        "completeness": result.completeness,
        "spl_editing_snapshot_path": str(result.spl_editing_snapshot_path)
        if result.spl_editing_snapshot_path
        else None,
        "spl_editing_snapshot_status": result.spl_editing_snapshot_status,
        "spl_editing_snapshot_error": result.spl_editing_snapshot_error,
    }
    _write_json(output_dir / "pipeline_result.summary.json", summary)
    if result.spl_editing_snapshot_status == "available" and result.spl_editing_snapshot_path:
        report.pass_("pipeline", "Pipeline produced an available SPL Editing snapshot.")
        return Path(result.spl_editing_snapshot_path)
    report.fail(
        "pipeline",
        f"Pipeline snapshot unavailable: {result.spl_editing_snapshot_status}",
    )
    return Path(result.spl_editing_snapshot_path) if result.spl_editing_snapshot_path else None


def _probe_spl_editing(
    snapshot_path: Path,
    output_dir: Path,
    report: ProbeReport,
    args: argparse.Namespace,
) -> str:
    from nl2spl.compiler.spl_editing.demo import _build_default_service
    from nl2spl.compiler.spl_editing.interaction.model import (
        SubmitRepairDirectiveDraftRequest,
        revision_token_string,
    )
    from nl2spl.compiler.spl_editing.presentation.explanation_cache import (
        read_cached_issue_explanation,
        read_explanation_cache,
    )
    from nl2spl.compiler.spl_editing.presentation.service import (
        SPLEditingPresentationService,
    )

    service = _build_default_service(suggestion_llm=object())
    editing_run_id = service.register_snapshot_file(snapshot_path)
    presentation = SPLEditingPresentationService(service)
    snapshot = service._get_snapshot(editing_run_id)
    revision_token = revision_token_string(snapshot.revision_token)

    _write_json(
        output_dir / "snapshot_registration.summary.json",
        {
            "editing_run_id": editing_run_id,
            "snapshot_id": snapshot.snapshot_id,
            "overlay_version": snapshot.overlay_version,
            "revision_token": revision_token,
            "diagnostic_count": len(snapshot.compile_diagnostics),
            "trace_count": len(snapshot.traces),
            "span_count": len(snapshot.spans),
        },
    )
    report.record("editing_run_id", editing_run_id)
    report.record("snapshot_id", snapshot.snapshot_id)
    report.record("revision_token", revision_token)
    report.record("diagnostic_count", len(snapshot.compile_diagnostics))
    report.record("trace_count", len(snapshot.traces))
    report.record("span_count", len(snapshot.spans))
    report.pass_("snapshot_registration", f"Registered snapshot as {editing_run_id}.")

    run_view = presentation.get_run_presentation(
        editing_run_id,
        snapshot_path=snapshot_path,
    )
    _write_json(output_dir / "run_presentation.dump.json", _safe(run_view))

    issue_list = presentation.list_issue_presentations(editing_run_id)
    _write_json(output_dir / "issue_list.dump.json", _safe(issue_list))
    report.pass_("issue_list", "Issue list presentation serialized.")

    issue = _select_worker_promotion_issue(service, editing_run_id)
    if issue is None:
        report.fail("worker_issue", "No editable WORKER_PROMOTION issue found.")
        return "display_only"
    report.record("selected_issue_id", issue.issue_id)
    report.pass_("worker_issue", f"Selected issue {issue.issue_id}.")

    issue_detail = presentation.get_issue_detail_presentation(editing_run_id, issue.issue_id)
    _write_json(output_dir / "issue_detail.dump.json", _safe(issue_detail))

    cache = read_explanation_cache(snapshot_path)
    cached_explanation = read_cached_issue_explanation(snapshot_path, issue.issue_id)
    _write_json(
        output_dir / "explanation_cache.dump.json",
        {
            "cache_status": cache.get("status") if isinstance(cache, dict) else None,
            "cache_language": cache.get("language") if isinstance(cache, dict) else None,
            "selected_issue_status": _issue_explanation_status(cache, issue.issue_id),
            "selected_issue_explanation": cached_explanation,
        },
    )

    option_id = args.option_id
    interaction = presentation.get_repair_interaction(
        editing_run_id,
        issue.issue_id,
        option_id,
        revision_token,
    )
    _write_json(output_dir / "repair_interaction.dump.json", _safe(interaction))
    unsupported = _unsupported_field_types(interaction)
    if unsupported:
        report.fail("interaction", f"Unsupported MVP field types: {', '.join(unsupported)}")
        return "unsupported_interaction"
    report.record("option_id", option_id)
    report.record("contract_id", interaction.contract_id)
    report.record(
        "interaction_fields",
        ", ".join(
            f"{field.field_id}:{field.input_type}:{'required' if field.required else 'optional'}"
            for field in getattr(interaction, "fields", ()) or ()
        ),
    )
    report.pass_("interaction", f"Interaction serialized for option {option_id}.")

    request = SubmitRepairDirectiveDraftRequest(
        run_id=editing_run_id,
        issue_id=issue.issue_id,
        strategy_id=interaction.strategy_id,
        option_id=interaction.option_id,
        contract_id=interaction.contract_id,
        contract_version=interaction.contract_version,
        revision_token=interaction.revision_token,
        field_values=_field_values_for_interaction(interaction, args.task_selection),
        selected_ref_ids={},
        new_fact_declarations=(),
        additional_instruction=None,
    )
    submitted = presentation.submit_repair_directive_draft(request)
    _write_json(output_dir / "directive_validation.dump.json", _safe(submitted))
    if submitted.input_readiness != "input_complete" or not submitted.normalized_directive_id:
        report.fail("directive", f"Directive readiness: {submitted.input_readiness}")
        return "directive_not_complete"
    report.record("directive_id", submitted.normalized_directive_id)
    report.pass_("directive", f"Directive {submitted.normalized_directive_id} accepted.")

    handle = presentation.preview_repair_directive(submitted.normalized_directive_id)
    _write_json(output_dir / "preview_handle.dump.json", _preview_summary(handle))
    preview_id = handle.preview.preview_id
    report.record("preview_id", preview_id)
    report.record("rendered_preview", getattr(handle.preview, "rendered_preview", None))
    report.pass_("preview", f"Preview {preview_id} materialized.")

    if args.skip_apply:
        return "preview_only"

    session, verification = presentation.apply_repair_preview(
        submitted.normalized_directive_id,
        preview_id,
    )
    patched = service._snapshots.get(
        editing_run_id,
        snapshot.snapshot_id,
        overlay_version=session.overlay_version,
    )
    final_spl_available = bool(getattr(patched, "final_spl", None))
    marker_count = len(getattr(patched, "promotion_resolution_markers", ()) or ())
    refreshed_issues = presentation.list_issue_presentations(editing_run_id)
    _write_json(
        output_dir / "apply_verification.dump.json",
        {
            "session": _safe(session),
            "verification": _safe(verification),
            "patched_snapshot": {
                "snapshot_id": getattr(patched, "snapshot_id", None),
                "overlay_version": getattr(patched, "overlay_version", None),
                "final_spl_available": final_spl_available,
                "promotion_resolution_marker_count": marker_count,
            },
            "refreshed_issue_summary": _safe(refreshed_issues.summary),
        },
    )
    report.record("overlay_version_after_apply", session.overlay_version)
    report.record("verification_accepted", getattr(verification, "accepted", None))
    report.record("verification_lane", getattr(verification, "lane", None))
    report.record(
        "diagnostic_diff_summary",
        getattr(verification, "diagnostic_diff_summary", None),
    )
    report.record("patched_final_spl_available", final_spl_available)
    report.record("promotion_resolution_marker_count", marker_count)
    if getattr(verification, "accepted", False):
        report.pass_("apply", "Apply completed and verification accepted.")
        return "applied"
    report.fail("apply", "Apply completed but verification was not accepted.")
    return "verification_failed"


def _select_worker_promotion_issue(service: Any, editing_run_id: str) -> Any | None:
    inventory = service.list_issue_inventory(editing_run_id)
    for issue in inventory.editable:
        irs_ref = getattr(issue, "irs_ref", None)
        if getattr(irs_ref, "construct_type", None) == "WORKER_PROMOTION":
            return issue
    return inventory.editable[0] if inventory.editable else None


def _field_values_for_interaction(interaction: Any, task_selection: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in getattr(interaction, "fields", ()) or ():
        if getattr(field, "field_id", "") == "task_selection":
            values[field.field_id] = task_selection
        elif getattr(field, "required", False) and getattr(field, "options", ()):
            values[field.field_id] = field.options[0].value
        elif getattr(field, "required", False) and getattr(field, "input_type", "") in {
            "short_text",
            "long_text",
        }:
            values[field.field_id] = f"probe value for {field.field_id}"
    return values


def _unsupported_field_types(interaction: Any) -> tuple[str, ...]:
    supported = {"short_text", "long_text", "single_choice", "multi_choice"}
    values: list[str] = []
    for field in getattr(interaction, "fields", ()) or ():
        input_type = getattr(field, "input_type", "")
        if input_type and input_type not in supported:
            values.append(input_type)
    return tuple(sorted(set(values)))


def _issue_explanation_status(cache: Any, issue_id: str) -> str:
    if not isinstance(cache, dict):
        return "missing"
    items = cache.get("items")
    item = items.get(issue_id) if isinstance(items, dict) else None
    if not isinstance(item, dict):
        return "missing"
    status = item.get("status")
    return status if status in {"ready", "pending", "error"} else "missing"


def _preview_summary(handle: Any) -> dict[str, Any]:
    preview = handle.preview
    typed = getattr(preview, "typed_artifact", None)
    construct_nodes = getattr(typed, "construct_nodes", ()) if typed is not None else ()
    return {
        "directive_id": handle.directive_id,
        "session_id": handle.session_id,
        "suggestion_id": handle.suggestion_id,
        "evidence_user_text_length": len(handle.evidence_user_text or ""),
        "preview": {
            "preview_id": getattr(preview, "preview_id", None),
            "base_snapshot_id": getattr(preview, "base_snapshot_id", None),
            "rendered_preview": getattr(preview, "rendered_preview", None),
            "typed_artifact_type": type(typed).__name__ if typed is not None else None,
            "typed_construct_node_count": len(construct_nodes or ()),
            "typed_construct_roles": sorted(
                {getattr(node, "role", "") for node in construct_nodes or ()}
            ),
        },
    }


def _safe(value: Any, *, _seen: set[int] | None = None, _depth: int = 0) -> Any:
    if _seen is None:
        _seen = set()
    if _depth > 8:
        return repr(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    ident = id(value)
    if ident in _seen:
        return "<cycle>"
    if dataclasses.is_dataclass(value):
        _seen.add(ident)
        result = {
            field.name: _safe(getattr(value, field.name), _seen=_seen, _depth=_depth + 1)
            for field in dataclasses.fields(value)
        }
        _seen.remove(ident)
        return result
    if isinstance(value, dict):
        _seen.add(ident)
        result = {
            str(_safe(k, _seen=_seen, _depth=_depth + 1)): _safe(v, _seen=_seen, _depth=_depth + 1)
            for k, v in value.items()
        }
        _seen.remove(ident)
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        _seen.add(ident)
        result = [_safe(item, _seen=_seen, _depth=_depth + 1) for item in value]
        _seen.remove(ident)
        return result
    if hasattr(value, "__dict__"):
        _seen.add(ident)
        result = {}
        for key, item in vars(value).items():
            if key.startswith("_"):
                continue
            result[key] = _safe(item, _seen=_seen, _depth=_depth + 1)
        _seen.remove(ident)
        return result or repr(value)
    return repr(value)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_safe(value), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


class ProbeReport:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.records: dict[str, Any] = {}
        self.passes: list[dict[str, str]] = []
        self.failures: list[dict[str, str]] = []

    def record(self, key: str, value: Any) -> None:
        self.records[key] = value

    def pass_(self, check: str, message: str) -> None:
        self.passes.append({"check": check, "message": message})

    def fail(self, check: str, message: str) -> None:
        self.failures.append({"check": check, "message": message})

    def finish(self) -> int:
        status = "pass" if not self.failures else "fail"
        summary = {
            "status": status,
            "records": self.records,
            "passes": self.passes,
            "failures": self.failures,
        }
        _write_json(self.output_dir / "probe_summary.json", summary)
        self._write_markdown(status)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if status == "pass" else 1

    def _write_markdown(self, status: str) -> None:
        lines = [
            "# SPL Web Demo Contract Probe Report",
            "",
            f"- Status: `{status}`",
            f"- Output dir: `{self.output_dir}`",
            "",
            "## Key Facts",
            "",
            "| Field | Value |",
            "|---|---|",
        ]
        key_order = (
            "editing_run_id",
            "snapshot_id",
            "revision_token",
            "selected_issue_id",
            "option_id",
            "contract_id",
            "interaction_fields",
            "directive_id",
            "preview_id",
            "overlay_version_after_apply",
            "verification_accepted",
            "verification_lane",
            "diagnostic_diff_summary",
            "patched_final_spl_available",
            "promotion_resolution_marker_count",
        )
        for key in key_order:
            if key in self.records:
                lines.append(f"| `{key}` | `{self.records[key]}` |")
        lines.extend(
            [
                "",
                "## Records",
                "",
            ]
        )
        for key, value in self.records.items():
            lines.append(f"- `{key}`: `{value}`")
        lines.extend(["", "## Passes", ""])
        for item in self.passes:
            lines.append(f"- `{item['check']}`: {item['message']}")
        lines.extend(["", "## Failures", ""])
        if not self.failures:
            lines.append("- None")
        else:
            for item in self.failures:
                lines.append(f"- `{item['check']}`: {item['message']}")
        lines.append("")
        (self.output_dir / "probe_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
