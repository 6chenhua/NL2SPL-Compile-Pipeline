"""Direct-run SPL Editing demo from a persisted snapshot JSON.

Run this file directly.  It does not require command-line arguments.

Snapshot lookup:
  examples/output/<run_name>/spl_editing_snapshot.json

This directory is only the runnable demo entry point.  It is not a
compile run directory and is never used as the snapshot source.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterable
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


def main() -> None:
    from nl2spl.compiler.spl_editing.cli import (
        _build_default_service,
        build_suggestion_llm_from_env,
    )
    from nl2spl.compiler.spl_editing.presentation import (
        SPLEditingPresentationService,
    )

    snapshot_path = _choose_snapshot_path()
    if snapshot_path is None:
        print("No spl_editing_snapshot.json found.")
        print("Run examples/usage.py first, or copy a snapshot JSON here.")
        return

    service = _build_default_service(
        suggestion_llm=build_suggestion_llm_from_env(),
    )
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
    if not selectable:
        print("No editable issues found in this snapshot.")
        return

    card = _choose_issue(selectable)
    if card is None:
        return

    detail = presentation.get_issue_detail_presentation(run_id, card.issue_id)
    _print_issue_detail(detail)
    if not card.can_fix:
        print("\nThis issue is not fixable in the current snapshot.")
        return

    option = _choose_fix_option(detail.available_repairs)
    if option is None:
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


def _choose_snapshot_path() -> Path | None:
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
    print(f"  Editable issues: {view.issue_count}")
    if view.issue_summary:
        print("\nIssue summary")
        for item in view.issue_summary:
            print(f"  {item.label}: {item.count}")


def _print_issue_list(view) -> list[object]:
    selectable: list[object] = []
    print("\nEditable issues")
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
