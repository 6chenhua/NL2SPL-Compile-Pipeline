"""Direct-run SPL Editing demo from a persisted snapshot JSON.

Run this file directly.  It does not require command-line arguments.

Snapshot lookup:
  examples/output/<run_name>/spl_editing_snapshot.json

This directory is only the runnable demo entry point.  It is not a
compile run directory and is never used as the snapshot source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SRC_ROOT = REPO_ROOT / "src"
RUNS_ROOT = REPO_ROOT / "examples" / "output"


def _reexec_with_project_venv() -> None:
    if os.environ.get("SPL_EDITING_DEMO_BOOTSTRAPPED") == "1":
        return
    venv_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_python.is_file():
        return
    if Path(sys.executable).resolve() == venv_python.resolve():
        return
    env = os.environ.copy()
    env["SPL_EDITING_DEMO_BOOTSTRAPPED"] = "1"
    completed = subprocess.run(
        [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]],
        env=env,
        check=False,
    )
    raise SystemExit(completed.returncode)


_reexec_with_project_venv()

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


SNAPSHOT_FILENAME = "spl_editing_snapshot.json"


class _ListOnlySuggestionLLM:
    """Placeholder suggestion backend for non-interactive issue-list rendering."""

    def generate(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("Suggestion generation is unavailable in --list-only mode.")


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    from nl2spl.compiler.spl_editing.cli import (
        _build_default_service,
        build_suggestion_llm_from_env,
    )
    from nl2spl.compiler.spl_editing.presentation import (
        SPLEditingPresentationService,
    )

    snapshot_path = _choose_snapshot_path(run_name=args.run)
    if snapshot_path is None:
        print("No spl_editing_snapshot.json found.")
        print("Run examples/usage.py first, or copy a snapshot JSON here.")
        return

    if args.e2e_worker_delegation:
        _run_worker_delegation_e2e(snapshot_path)
        return

    llm = _ListOnlySuggestionLLM() if args.list_only else build_suggestion_llm_from_env()
    service = _build_default_service(suggestion_llm=llm)
    run_id = service.register_snapshot_file(snapshot_path)
    presentation = SPLEditingPresentationService(service)

    run_view = presentation.get_run_presentation(
        run_id,
        run_label=snapshot_path.parent.name,
        snapshot_path=snapshot_path,
    )
    issue_list = presentation.list_issue_presentations(run_id)

    _print_run_summary(run_view)
    selectable = _print_issue_list(issue_list)
    if args.list_only:
        return
    if not selectable:
        print("No editable issues found in this snapshot.")
        return

    from nl2spl.compiler.spl_editing.presentation.explanation_cache import (
        read_cached_issue_explanation,
        schedule_issue_explanations,
    )

    explanation_future = schedule_issue_explanations(
        snapshot_path,
        llm,
        language=os.getenv("SPL_EDITING_EXPLANATION_LANGUAGE", "zh-CN"),
    )

    card = _choose_issue(selectable)
    if card is None:
        return

    detail = presentation.get_issue_detail_presentation(run_id, card.issue_id)
    explanation = read_cached_issue_explanation(snapshot_path, card.issue_id)
    if explanation is None:
        try:
            explanation_future.result()
        except Exception as exc:
            print(f"\nAI explanation precompute failed: {exc}")
        explanation = read_cached_issue_explanation(snapshot_path, card.issue_id)
    _print_issue_explanation(explanation, detail)
    if not card.can_fix:
        print("\nThis issue is not fixable in the current snapshot.")
        return

    option = _choose_fix_option(detail.available_repairs)
    if option is None:
        return

    if getattr(option, "option_id", None):
        _run_typed_interaction_repair(
            service=service,
            presentation=presentation,
            run_id=run_id,
            issue_id=card.issue_id,
            option=option,
        )
        return

    user_instruction = _collect_user_repair_instruction()

    issue = presentation.issue_by_id(run_id, card.issue_id)
    session = service.create_session(run_id, issue)
    generation = service.generate_suggestions(
        session.session_id,
        user_instruction=user_instruction,
        selected_patch_types=option.patch_types,
    )
    if generation.status in ("generation_blocked", "repair_unavailable"):
        print(f"\nSuggestion generation unavailable: {generation.status}")
        if generation.reasons:
            print(f"  reasons: {'; '.join(generation.reasons)}")
        return
    suggestions = generation.suggestions
    if not suggestions:
        print("\nNo repair suggestions generated for this issue.")
        return

    suggestion_views = presentation.present_suggestions(suggestions)
    _print_suggestions(suggestion_views)

    applied_suggestion = _choose_suggestion(suggestions)
    if applied_suggestion is None:
        return

    preview = service.preview_suggestion(
        session.session_id,
        applied_suggestion.suggestion_id,
        user_text=user_instruction,
    )
    confirmation = presentation.present_apply_confirmation(applied_suggestion)
    _print_confirmation(confirmation)
    print("\nPreview:")
    for line in preview.rendered_preview.splitlines():
        print(f"  {line}")
    confirm = input("Confirm apply? [y/N] ").strip().lower()
    if confirm != "y":
        print("Cancelled. Snapshot was not changed.")
        return

    print("Applying suggestion...", flush=True)
    updated = service.apply_preview_result(
        session.session_id,
        applied_suggestion.suggestion_id,
        preview.preview_id,
        user_text=user_instruction,
    )
    print(f"Applied. overlay_version={updated.overlay_version}")

    print("Verifying patched snapshot...", flush=True)
    result = service.verify_session(session.session_id)
    patched_spl = None
    if result.accepted:
        patched_spl = service.get_patched_spl(run_id) or "(empty)"
    verification_view = presentation.present_verification(
        run_id,
        result,
        updated_spl=patched_spl,
    )
    _print_verification(verification_view, failures=result.failure_reasons)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render the SPL Editing demo from a persisted snapshot JSON."
    )
    parser.add_argument(
        "--run",
        default=os.getenv("SPL_EDITING_DEMO_RUN"),
        help="Compile run directory under examples/output to load, e.g. 'demo'.",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        default=os.getenv("SPL_EDITING_DEMO_LIST_ONLY") == "1",
        help="Print run and issue presentation without entering Fix-with-AI flow.",
    )
    parser.add_argument(
        "--e2e-worker-delegation",
        action="store_true",
        help=(
            "Run deterministic Define-child, Keep-main, and negative Worker "
            "Delegation scenarios and write acceptance bundles."
        ),
    )
    return parser.parse_args(argv)


def _choose_snapshot_path(run_name: str | None = None) -> Path | None:
    if run_name:
        path = RUNS_ROOT / run_name / SNAPSHOT_FILENAME
        return path if path.is_file() else None

    candidates = _snapshot_candidates()
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    print("Available compile runs")
    for index, path in enumerate(candidates, 1):
        print(f"  [{index}] {path.parent.name}")
        print("       Snapshot: available")
    while True:
        raw = input("Select run number: ").strip()
        try:
            idx = int(raw) - 1
        except ValueError:
            print(f"Invalid choice: {raw}")
            continue
        if 0 <= idx < len(candidates):
            return candidates[idx]
        print(f"Invalid choice: {raw}")


def _snapshot_candidates() -> list[Path]:
    candidates: list[Path] = []
    for run_dir in sorted(RUNS_ROOT.iterdir()):
        if not run_dir.is_dir():
            continue
        if run_dir.resolve() == HERE.resolve():
            continue
        path = run_dir / SNAPSHOT_FILENAME
        if path.is_file():
            candidates.append(path)
    return candidates


def _print_run_summary(view) -> None:
    print("\nSPL Editing snapshot")
    print(f"  Run: {view.run_label}")
    print(f"  Snapshot: {view.snapshot_id}")
    print(f"  Version: overlay {view.overlay_version}")
    print(f"  Editable issues: {view.editable_issue_count}")
    print(f"  Review needed: {view.review_issue_count}")
    print(f"  Deferred validation: {view.deferred_validation_count}")
    if view.issue_summary:
        print("\nIssue summary")
        for item in view.issue_summary:
            print(f"  {item.label}: {item.count}")


def _print_issue_list(view) -> list[object]:
    selectable: list[object] = []
    print("\nIssues")
    for section in view.sections:
        if not section.visible_by_default or not section.items:
            continue
        print(f"\n{section.label}")
        for card in section.items:
            print(f"  [{card.display_id}] {card.title}")
            print(f"       {card.impact}")
            if card.can_fix:
                print(f"       Fix with AI: {card.fix_label}")
            else:
                print(f"       Status: {card.fix_label}")
            if card.missing_items:
                print(f"       Missing: {', '.join(card.missing_items)}")
            if card.suggested_resolution:
                print(f"       Suggested resolution: {card.suggested_resolution}")
            if card.can_fix:
                selectable.append(card)
    return selectable


def _choose_issue(selectable: list[object]) -> object | None:
    while True:
        raw = input("Select issue number to inspect or fix: ").strip()
        try:
            display_id = int(raw)
        except ValueError:
            print(f"Invalid choice: {raw}")
            continue
        for card in selectable:
            if card.display_id == display_id:
                return card
        print(f"Invalid choice: {raw}")


def _print_issue_detail(detail) -> None:
    print(f"\nIssue: {detail.title}")
    print("\nWhat was detected:")
    print(f"  {detail.what_was_detected}")
    if detail.missing_items:
        print("\nMissing information:")
        for item in detail.missing_items:
            print(f"  - {item}")
    print("\nWhy this matters:")
    print(f"  {detail.why_it_matters}")
    if detail.source_context:
        print("\nSource context:")
        print(f"  {detail.source_context}")
    if detail.suggested_resolution:
        print("\nSuggested resolution:")
        print(f"  {detail.suggested_resolution}")
    print("\nAvailable fixes:")
    for index, option in enumerate(detail.available_repairs, 1):
        print(f"  [{index}] {option.label}")
        print(f"      {option.description}")
        if option.unavailable_reason:
            print(f"      Unavailable: {option.unavailable_reason}")


def _print_issue_explanation(explanation, detail) -> None:
    if explanation is None:
        _print_issue_detail(detail)
        return
    print("\nAI issue explanation (cached in snapshot)")
    print(json.dumps(explanation, ensure_ascii=False, indent=2))


def _choose_fix_option(
    available_repairs: tuple[object, ...],
) -> object | None:
    """Let the user pick one repair option (patch type group).

    Uses the same 1-based numbering shown by ``_print_issue_detail``
    so the displayed index matches the user's input.  Unavailable
    options are rejected with their reason shown.
    """
    repairs = tuple(available_repairs)
    available = [r for r in repairs if getattr(r, "unavailable_reason", None) is None]
    if not available:
        print("\nNo available repair options for this issue.")
        return None
    while True:
        raw = input("Choose fix option number: ").strip()
        try:
            idx = int(raw) - 1
        except ValueError:
            print(f"Invalid choice: {raw}")
            continue
        if 0 <= idx < len(repairs):
            choice = repairs[idx]
            reason = getattr(choice, "unavailable_reason", None)
            if reason is not None:
                print(f"Option [{idx + 1}] is not available: {reason}")
                continue
            return choice
        print(f"Invalid choice: {raw}")


def _collect_user_repair_instruction() -> str | None:
    print("\nOptional repair instruction")
    print("  Press Enter to let SPL Editing choose the simplest valid repair.")
    try:
        raw = input("Describe your preferred repair, or press Enter: ").strip()
    except EOFError:
        return None
    return raw or None


def _run_typed_interaction_repair(*, service, presentation, run_id, issue_id, option) -> None:
    """Render and submit a backend-owned interaction without issue-specific UI logic."""
    from nl2spl.compiler.spl_editing.interaction.model import (
        SubmitRepairDirectiveDraftRequest,
    )

    snapshot = service._get_snapshot(run_id)
    revision = f"{snapshot.compile_run_id}:{snapshot.snapshot_id}:{snapshot.overlay_version}"
    interaction = presentation.get_repair_interaction(run_id, issue_id, option.option_id, revision)
    field_values, selected_ref_ids, new_facts, additional_instruction = _collect_interaction_values(
        interaction
    )
    request = SubmitRepairDirectiveDraftRequest(
        run_id=run_id,
        issue_id=issue_id,
        strategy_id=interaction.strategy_id,
        option_id=interaction.option_id,
        contract_id=interaction.contract_id,
        contract_version=interaction.contract_version,
        revision_token=interaction.revision_token,
        field_values=field_values,
        selected_ref_ids=selected_ref_ids,
        new_fact_declarations=new_facts,
        additional_instruction=additional_instruction,
    )
    result = presentation.submit_repair_directive_draft(request)
    if result.input_readiness != "input_complete":
        print(f"\nInput status: {result.input_readiness}")
        for error in result.errors:
            print(f"  - {error.field_id or 'request'}: {error.message} ({error.code})")
        return
    handle = presentation.preview_repair_directive(result.normalized_directive_id)
    print("\nPreview:")
    for line in handle.preview.rendered_preview.splitlines():
        print(f"  {line}")
    if input("Confirm apply? [y/N] ").strip().lower() != "y":
        print("Cancelled. Snapshot was not changed.")
        return
    updated, verification = presentation.apply_repair_preview(
        result.normalized_directive_id, handle.preview.preview_id
    )
    print(f"Applied. overlay_version={updated.overlay_version}")
    patched_spl = service.get_patched_spl(run_id) if verification.accepted else None
    view = presentation.present_verification(run_id, verification, updated_spl=patched_spl)
    _print_verification(view, failures=verification.failure_reasons)


def _collect_interaction_values(interaction):
    schemas = {schema.schema_id: schema for schema in interaction.schemas}
    values: dict[str, object] = {}
    refs: dict[str, tuple[str, ...]] = {}
    facts: list[dict[str, object]] = []
    additional_instruction = None
    print("\nRequired information")
    for field in interaction.fields:
        value = _collect_field_value(field, schemas)
        if field.field_id == "additional_instruction":
            additional_instruction = value or None
        elif field.input_type == "reference_select":
            refs[field.field_id] = tuple(value or ())
        elif field.input_type == "new_fact_list":
            facts.extend(value or ())
        elif value is not None:
            values[field.field_id] = value
    return values, refs, tuple(facts), additional_instruction


def _collect_field_value(field, schemas):
    label = field.label + (" *" if field.required else "")
    if field.input_type in {"short_text", "long_text"}:
        default = str(field.value) if field.value is not None else ""
        prompt = f"{label}" + (f" [{default}]" if default else "") + ": "
        raw = input(prompt).strip()
        return raw or default or None
    if field.input_type in {"single_choice", "multi_choice", "reference_select"}:
        if not field.options:
            return () if field.input_type != "single_choice" else None
        print(f"{label}:")
        for index, choice in enumerate(field.options, 1):
            print(f"  [{index}] {choice.label}")
        raw = input("Select number(s), comma-separated: ").strip()
        if not raw:
            return () if field.input_type != "single_choice" else None
        selected = tuple(field.options[int(item.strip()) - 1].value for item in raw.split(","))
        return selected[0] if field.input_type == "single_choice" else selected
    if field.input_type in {"structured_object", "new_fact_list"}:
        schema_id = field.object_schema_id or field.fact_schema_id
        schema = schemas[schema_id]
        raw_count = input(f"{label} - number of entries: ").strip()
        count = int(raw_count or ("1" if field.required else "0"))
        return tuple(_collect_schema_object(schema, schemas) for _ in range(count))
    raise ValueError(f"Unsupported interaction input type: {field.input_type}")


def _collect_schema_object(schema, schemas) -> dict[str, object]:
    result: dict[str, object] = {}
    print(f"  {schema.schema_id}")
    for field in schema.fields:
        value = _collect_field_value(field, schemas)
        if field.input_type == "reference_select":
            values = tuple(value or ())
            value = values[0] if values else None
        if value is not None:
            result[field.field_id] = value
    return result


def _run_worker_delegation_e2e(snapshot_path: Path) -> None:
    """Execute deterministic real-snapshot E2E scenarios and emit audit bundles."""
    root = REPO_ROOT / ".test-artifacts" / "spl_editing" / "worker_delegation_v2"
    root.mkdir(parents=True, exist_ok=True)
    define = _execute_worker_scenario(snapshot_path, "define_child_worker")
    keep = _execute_worker_scenario(snapshot_path, "keep_in_main_flow")
    negative = _execute_negative_worker_scenario(snapshot_path)
    if not define["accepted"] or not keep["accepted"] or negative["accepted"]:
        raise RuntimeError("Worker Delegation E2E acceptance criteria failed")
    print("Worker Delegation v2 E2E: PASS")
    print(f"  Define child worker: Lane {define['lane']} accepted")
    print(f"  Keep in main flow: Lane {keep['lane']} accepted")
    print("  Negative validation: rejected without overlay")
    print(f"  Acceptance bundles: {root}")


def _worker_runtime(snapshot_path: Path):
    from nl2spl.compiler.spl_editing.cli import _build_default_service
    from nl2spl.compiler.spl_editing.presentation import SPLEditingPresentationService

    service = _build_default_service(suggestion_llm=_ListOnlySuggestionLLM())
    run_id = service.register_snapshot_file(snapshot_path)
    # E2E acceptance output belongs under .test-artifacts.  Keep the loaded
    # canonical fixture read-only and disable overlay persistence for this run.
    service._snapshot_repository = None
    presentation = SPLEditingPresentationService(service)
    issue = next(
        item
        for item in service.list_editable_issues(run_id)
        if item.irs_ref.construct_type == "WORKER_PROMOTION"
    )
    snapshot = service._get_snapshot(run_id)
    revision = f"{snapshot.compile_run_id}:{snapshot.snapshot_id}:{snapshot.overlay_version}"
    return service, presentation, run_id, issue, snapshot, revision


def _execute_worker_scenario(snapshot_path: Path, option_id: str) -> dict[str, object]:
    from nl2spl.compiler.spl_editing.interaction.model import (
        SubmitRepairDirectiveDraftRequest,
    )

    service, presentation, run_id, issue, before, revision = _worker_runtime(snapshot_path)
    interaction = presentation.get_repair_interaction(run_id, issue.issue_id, option_id, revision)
    if option_id == "define_child_worker":
        input_ref = next(
            choice.value
            for field in interaction.fields
            if field.field_id == "input_refs"
            for choice in field.options
            if choice.label == "user_request"
        )
        field_values = {
            "delegated_responsibility": "Gather approved source evidence",
            "invocation_timing": "append",
            "result_usage": (
                {
                    "output_local_id": "evidence",
                    "create_parent_local_temporary": "yes",
                },
            ),
        }
        selected = {"input_refs": (input_ref,)}
        facts = (
            {
                "local_id": "evidence",
                "display_name": "delegated evidence",
                "semantic_description": "Approved evidence returned by the child worker",
                "data_type_hint": "text",
            },
        )
        contract_id = "worker_delegation.define_child_worker.v1"
    else:
        field_values = {"task_selection": "source gathering and template matching"}
        selected = {}
        facts = ()
        contract_id = "worker_delegation.keep_in_main_flow.v1"
    request = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        option_id,
        contract_id,
        "1",
        revision,
        field_values,
        selected,
        facts,
    )
    submitted = presentation.submit_repair_directive_draft(request)
    if submitted.input_readiness != "input_complete":
        raise RuntimeError(f"{option_id} draft rejected: {submitted.errors}")
    handle = presentation.preview_repair_directive(submitted.normalized_directive_id)
    updated, verification = presentation.apply_repair_preview(
        submitted.normalized_directive_id, handle.preview.preview_id
    )
    after = service._get_snapshot(run_id)
    after_spl = service.get_patched_spl(run_id)
    if verification.lane != "B" or not verification.accepted:
        raise RuntimeError(f"{option_id} verification failed: {verification.failure_reasons}")
    if option_id == "define_child_worker":
        if "ChildWorker_" not in after_spl or "[INVOKE ChildWorker_" not in after_spl:
            child_visible = "ChildWorker_" in after_spl
            invoke_visible = "[INVOKE ChildWorker_" in after_spl
            raise RuntimeError(
                "Define-child result is not visible in rendered SPL "
                f"(child={child_visible}, invoke={invoke_visible}): " + after_spl[-2000:]
            )
    elif "source gathering and template matching" not in after_spl.casefold():
        raise RuntimeError("Keep-main command is not visible in rendered SPL: " + after_spl[-1800:])
    summary = {
        "scenario_id": option_id,
        "accepted": verification.accepted,
        "lane": verification.lane,
        "directive_id": submitted.normalized_directive_id,
        "preview_id": handle.preview.preview_id,
        "patch_id": verification.patch_id,
        "overlay_version": updated.overlay_version,
    }
    _write_acceptance_bundle(
        scenario_id=option_id,
        before=before,
        after=after,
        before_spl=before.final_spl or "",
        after_spl=after_spl,
        preview=handle.preview,
        verification=verification,
        service=service,
        directive_id=submitted.normalized_directive_id,
    )
    return summary


def _execute_negative_worker_scenario(snapshot_path: Path) -> dict[str, object]:
    from nl2spl.compiler.spl_editing.interaction.model import (
        SubmitRepairDirectiveDraftRequest,
    )

    service, presentation, run_id, issue, before, revision = _worker_runtime(snapshot_path)
    request = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        "define_child_worker",
        "worker_delegation.define_child_worker.v1",
        "1",
        revision,
        {"invocation_timing": "after", "placement_ref": "unknown-ref"},
        {"input_refs": ("unknown-ref",)},
        (),
    )
    result = presentation.submit_repair_directive_draft(request)
    after = service._get_snapshot(run_id)
    accepted = (
        result.input_readiness == "input_complete"
        or after.overlay_version != before.overlay_version
    )
    _write_acceptance_bundle(
        scenario_id="negative",
        before=before,
        after=after,
        before_spl=before.final_spl or "",
        after_spl=after.final_spl or "",
        preview={
            "input_readiness": result.input_readiness,
            "errors": [_jsonable(item) for item in result.errors],
        },
        verification={
            "accepted": False,
            "lane": None,
            "failure_reasons": [item.code for item in result.errors],
        },
        service=service,
        directive_id=None,
    )
    return {"scenario_id": "negative", "accepted": accepted, "lane": None}


def _write_acceptance_bundle(
    *,
    scenario_id,
    before,
    after,
    before_spl,
    after_spl,
    preview,
    verification,
    service,
    directive_id,
) -> None:
    bundle_dir = (
        REPO_ROOT / ".test-artifacts" / "spl_editing" / "worker_delegation_v2" / scenario_id
    )
    bundle_dir.mkdir(parents=True, exist_ok=True)
    before_inventory = _typed_artifact_inventory(before)
    after_inventory = _typed_artifact_inventory(after)
    if after.overlay_version > before.overlay_version:
        from nl2spl.compiler.spl_editing.verification.lanes import LaneBReplayAdapter

        replay = LaneBReplayAdapter().replay(after)
        after_diagnostics = replay.post_normalize_diagnostics
    else:
        after_diagnostics = after.compile_diagnostics
    payloads = {
        "before_final.spl": before_spl,
        "after_final.spl": after_spl,
        "before_diagnostics.json": _json_text(before.compile_diagnostics),
        "after_diagnostics.json": _json_text(after_diagnostics),
        "preview_summary.json": _json_text(preview),
        "verification_result.json": _json_text(verification),
        "evidence_provenance_summary.json": _json_text(
            _evidence_summary(after, service, directive_id)
        ),
        "artifact_diff.json": _json_text(
            {
                "changed_categories": [
                    name
                    for name in before_inventory
                    if before_inventory[name] != after_inventory[name]
                ],
                "before": before_inventory,
                "after": after_inventory,
            }
        ),
    }
    hashes: dict[str, str] = {}
    for name, content in payloads.items():
        path = bundle_dir / name
        path.write_text(content, encoding="utf-8", newline="")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    verification_data = _jsonable(verification)
    preview_data = _jsonable(preview)
    evidence = _evidence_summary(after, service, directive_id)
    manifest = {
        "scenario_id": scenario_id,
        "base_snapshot_id": before.snapshot_id,
        "base_overlay_version": before.overlay_version,
        "result_overlay_version": after.overlay_version,
        "strategy_id": "worker_delegation.complete_closure.v2",
        "option_id": scenario_id if scenario_id != "negative" else "define_child_worker",
        "normalized_directive_id": directive_id,
        "preview_id": preview_data.get("preview_id"),
        "patch_id": verification_data.get("patch_id"),
        "evidence_ids": evidence.get("evidence_packet_ids", []),
        "verification_lane": verification_data.get("lane"),
        "verification_status": "accepted" if verification_data.get("accepted") else "rejected",
        "file_hashes": hashes,
    }
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _typed_artifact_inventory(snapshot) -> dict[str, object]:
    workers = snapshot.worker_plan.workers if snapshot.worker_plan is not None else ()
    handoffs = snapshot.worker_plan.handoffs if snapshot.worker_plan is not None else ()
    steps = snapshot.worker_step_plan.worker_steps if snapshot.worker_step_plan is not None else {}
    blocks = (
        snapshot.worker_block_plan.worker_blocks if snapshot.worker_block_plan is not None else {}
    )
    flows = snapshot.worker_flow_plan.worker_flows if snapshot.worker_flow_plan is not None else {}
    symbols = getattr(snapshot.symbol_table, "_variables", {}) if snapshot.symbol_table else {}
    return {
        "WorkerPlanIR": {
            "workers": [_jsonable(item) for item in workers],
            "handoffs": [_jsonable(item) for item in handoffs],
        },
        "WorkerFlowPlanIR": sorted(flows),
        "WorkerBlockPlanIR": {
            worker_id: [_jsonable(item) for item in structure.main_flow_blocks]
            for worker_id, structure in sorted(blocks.items())
        },
        "WorkerStepPlanIR": {
            worker_id: [_jsonable(item) for item in values]
            for worker_id, values in sorted(steps.items())
        },
        "handoff_invoke_bindings": [
            {
                "handoff_id": item.handoff_id,
                "input_bindings": _jsonable(item.input_bindings),
                "output_bindings": _jsonable(item.output_bindings),
                "invoke_step_ids": [
                    step.step_id
                    for values in steps.values()
                    for step in values
                    if step.handoff_id == item.handoff_id
                ],
            }
            for item in handoffs
        ],
        "PromotionResolutionMarker": _jsonable(snapshot.promotion_resolution_markers),
        "SymbolTable_local_temporary_results": [
            _jsonable(value)
            for (_scope_kind, _scope_id, name), value in sorted(symbols.items())
            if name.startswith("tmp_")
        ],
    }


def _evidence_summary(snapshot, service, directive_id) -> dict[str, object]:
    steps = (
        snapshot.worker_step_plan.get_all_steps() if snapshot.worker_step_plan is not None else []
    )
    matching = [
        step
        for step in steps
        if directive_id and step.metadata.get("normalized_directive_id") == directive_id
    ]
    apply_results = tuple(getattr(service, "_apply_results", {}).values())
    evidence_packet_ids = sorted(
        {
            step.metadata.get("evidence_packet_id")
            for step in matching
            if step.metadata.get("evidence_packet_id")
        }
    )
    return {
        "evidence_packet_ids": evidence_packet_ids,
        "changed_artifact_evidence": [
            _jsonable(item) for result in apply_results for item in result.evidence_refs
        ],
        "step_provenance": [
            {"step_id": step.step_id, "metadata": _jsonable(step.metadata)} for step in matching
        ],
        "resolution_markers": [
            _jsonable(marker)
            for marker in snapshot.promotion_resolution_markers
            if directive_id and marker.normalized_directive_id == directive_id
        ],
    }


def _jsonable(value):
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _json_text(value) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _print_suggestions(suggestions: tuple[object, ...]) -> None:
    print("\nRepair suggestion" if len(suggestions) == 1 else "\nRepair suggestions")
    for index, suggestion in enumerate(suggestions, 1):
        print(f"  [{index}] {suggestion.title}")
        if suggestion.explanation:
            print(f"       {suggestion.explanation}")
        if suggestion.expected_effect:
            print("       Expected effect:")
            for item in suggestion.expected_effect:
                print(f"         - {item}")
        if suggestion.risks:
            print("       Risks:")
            for item in suggestion.risks:
                print(f"         - {item}")
        if suggestion.preview:
            print("       Preview:")
            for line in suggestion.preview.splitlines():
                print(f"         {line}")
        print()


def _choose_suggestion(suggestions: Iterable[object]):
    values = tuple(suggestions)
    if len(values) == 1:
        return values[0]
    while True:
        raw = input("Apply suggestion number: ").strip()
        try:
            idx = int(raw) - 1
        except ValueError:
            print(f"Invalid choice: {raw}")
            continue
        if 0 <= idx < len(values):
            return values[idx]
        print(f"Invalid choice: {raw}")


def _print_confirmation(view) -> None:
    print(f"\nApply suggestion: {view.title}")
    print("\nThis will:")
    for item in view.will_do:
        print(f"  - {item}")
    print("\nThis will not:")
    for item in view.will_not_do:
        print(f"  - {item}")
    print(f"\nVerification lane: {view.verification_lane}")


def _print_verification(view, *, failures: tuple[str, ...]) -> None:
    print("\nVerification result")
    print(f"  status: {view.status}")
    if view.resolved:
        print(f"  resolved: {', '.join(view.resolved)}")
    if view.new_blocking_diagnostics:
        print(f"  new blocking: {', '.join(view.new_blocking_diagnostics)}")
    if failures:
        print(f"  failures: {'; '.join(failures)}")
    if view.authority_summary:
        print("\nCompiler authorities:")
        for item in view.authority_summary:
            print(f"  - {item}")
    if view.new_snapshot_id is not None:
        print("\nNew snapshot:")
        print(f"  snapshot_id: {view.new_snapshot_id}")
        print(f"  overlay_version: {view.overlay_version}")
    if view.updated_spl:
        print("\nUpdated SPL")
        print(view.updated_spl)


if __name__ == "__main__":
    main()
