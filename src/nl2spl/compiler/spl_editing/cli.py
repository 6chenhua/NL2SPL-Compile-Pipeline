"""SPL Editing Demo CLI — thin wrapper over SPLEditingService.

Usage:
    python -m nl2spl.compiler.spl_editing.cli demo --run <run_dir>
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

from nl2spl.compiler.artifacts.snapshot.persistence.loader import SnapshotLoader
from nl2spl.compiler.spl_editing.core.registry import SPLEditingRuntimeRegistry
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.core.service import SPLEditingService
from nl2spl.compiler.spl_editing.core.snapshot_adapter import (
    artifact_snapshot_from_document,
)
from nl2spl.compiler.spl_editing.patches.registry import PatchBundle
from nl2spl.compiler.spl_editing.verification.lanes import LaneAReplayAdapter


def build_suggestion_llm_from_env():
    """Build the live project LLM client for SPL Editing suggestions."""
    from dotenv import load_dotenv

    from nl2spl.compiler.spl_editing.core.errors import SPLEditingError
    from nl2spl.compiler.spl_editing.handlers.llm_adapter import LiveSuggestionLLM
    from nl2spl.config import LLMConfig
    from nl2spl.llm.client import LLMClient

    load_dotenv()
    config = LLMConfig()
    if not config.api_key:
        raise SPLEditingError(
            "SPL Editing suggestion generation requires a configured LLM "
            "API key. Set OPENAI_API_KEY or the project LLM config before "
            "running Fix with AI."
        )
    return LiveSuggestionLLM(LLMClient(config))


def _build_default_service(suggestion_llm=None) -> SPLEditingService:
    reg = SPLEditingRuntimeRegistry()
    if suggestion_llm is None:
        suggestion_llm = build_suggestion_llm_from_env()

    from nl2spl.compiler.spl_editing.targets.exception_flow import (
        ExceptionFlowTargetResolver,
    )
    from nl2spl.compiler.spl_editing.targets.required_output import (
        RequiredOutputTargetResolver,
    )
    from nl2spl.compiler.spl_editing.targets.worker_promotion import (
        WorkerPromotionTargetResolver,
    )

    reg.target_resolvers.register("exception_flow_target", ExceptionFlowTargetResolver())
    reg.target_resolvers.register("required_output_target", RequiredOutputTargetResolver())
    reg.target_resolvers.register("worker_promotion_target", WorkerPromotionTargetResolver())

    from nl2spl.compiler.spl_editing.context.exception_flow_context import (
        ExceptionFlowContextBuilder,
    )
    from nl2spl.compiler.spl_editing.context.required_output_context import (
        RequiredOutputContextBuilder,
    )
    from nl2spl.compiler.spl_editing.context.worker_promotion_context import (
        WorkerPromotionContextBuilder,
    )

    reg.context_builders.register("exception_flow_context", ExceptionFlowContextBuilder())
    reg.context_builders.register("required_output_context", RequiredOutputContextBuilder())
    reg.context_builders.register("worker_promotion_context", WorkerPromotionContextBuilder())

    from nl2spl.compiler.spl_editing.handlers.missing_handler.handler import (
        MissingHandlerRepairHandler,
    )
    from nl2spl.compiler.spl_editing.handlers.missing_output_producer.handler import (
        MissingOutputProducerHandler,
    )
    from nl2spl.compiler.spl_editing.handlers.type_or_contract_ambiguity.handler import (
        TypeOrContractAmbiguityHandler,
    )

    reg.handlers.register("missing_handler", MissingHandlerRepairHandler(suggestion_llm))
    reg.llm_context_builders.register(
        "missing_handler",
        _build_missing_handler_context_builder(),
    )
    reg.prompt_renderers.register(
        "missing_handler",
        _build_missing_handler_prompt_renderer(),
    )
    reg.handlers.register(
        "missing_output_producer",
        MissingOutputProducerHandler(suggestion_llm),
    )
    reg.llm_context_builders.register(
        "missing_output_producer",
        _build_generic_context_builder(),
    )
    reg.prompt_renderers.register(
        "missing_output_producer",
        _build_generic_prompt_renderer(),
    )
    reg.handlers.register(
        "type_or_contract_ambiguity",
        TypeOrContractAmbiguityHandler(suggestion_llm),
    )
    reg.llm_context_builders.register(
        "type_or_contract_ambiguity",
        _build_generic_context_builder(),
    )
    reg.prompt_renderers.register(
        "type_or_contract_ambiguity",
        _build_generic_prompt_renderer(),
    )

    from nl2spl.compiler.spl_editing.core.model import PatchTypeContract
    from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.applier import (
        AddExceptionHandlerStepApplier,
    )
    from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.preview import (
        AddExceptionHandlerStepPreviewer,
    )
    from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.validator import (
        AddExceptionHandlerStepValidator,
    )
    from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.verifier import (
        AddExceptionHandlerStepVerifier,
    )

    reg.patches.register(
        "AddExceptionHandlerStep",
        PatchBundle(
            patch_type="AddExceptionHandlerStep",
            validator=AddExceptionHandlerStepValidator(),
            applier=AddExceptionHandlerStepApplier(),
            verifier=AddExceptionHandlerStepVerifier(),
            previewer=AddExceptionHandlerStepPreviewer(),
            contract=PatchTypeContract(
                patch_type="AddExceptionHandlerStep",
                produces_step_ir=True,
                evidence_targets=("step",),
            ),
        ),
    )
    from nl2spl.compiler.spl_editing.patches.insert_producer_step.applier import (
        InsertProducerStepApplier,
    )
    from nl2spl.compiler.spl_editing.patches.insert_producer_step.preview import (
        InsertProducerStepPreviewer,
    )
    from nl2spl.compiler.spl_editing.patches.insert_producer_step.validator import (
        InsertProducerStepValidator,
    )
    from nl2spl.compiler.spl_editing.patches.insert_producer_step.verifier import (
        InsertProducerStepVerifier,
    )

    reg.patches.register(
        "InsertProducerStep",
        PatchBundle(
            patch_type="InsertProducerStep",
            validator=InsertProducerStepValidator(),
            applier=InsertProducerStepApplier(),
            verifier=InsertProducerStepVerifier(),
            previewer=InsertProducerStepPreviewer(),
            contract=PatchTypeContract(
                patch_type="InsertProducerStep",
                produces_step_ir=True,
                evidence_targets=("step",),
            ),
        ),
    )


    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_main_flow_step.applier import (
        ConvertDelegationToMainFlowStepApplier,
    )
    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_main_flow_step.validator import (
        ConvertDelegationToMainFlowStepValidator,
    )
    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_main_flow_step.verifier import (
        ConvertDelegationToMainFlowStepVerifier,
    )

    reg.patches.register(
        "ConvertDelegationIntentToMainFlowStep",
        PatchBundle(
            patch_type="ConvertDelegationIntentToMainFlowStep",
            validator=ConvertDelegationToMainFlowStepValidator(),
            applier=ConvertDelegationToMainFlowStepApplier(),
            verifier=ConvertDelegationToMainFlowStepVerifier(),
            previewer=AddExceptionHandlerStepPreviewer(),
            contract=PatchTypeContract(
                patch_type="ConvertDelegationIntentToMainFlowStep",
                produces_step_ir=True,
                evidence_targets=("step",),
            ),
        ),
    )
    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_request_input.applier import (
        ConvertDelegationToRequestInputApplier,
    )
    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_request_input.validator import (
        ConvertDelegationToRequestInputValidator,
    )
    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_request_input.verifier import (
        ConvertDelegationToRequestInputVerifier,
    )

    reg.patches.register(
        "ConvertDelegationIntentToRequestInput",
        PatchBundle(
            patch_type="ConvertDelegationIntentToRequestInput",
            validator=ConvertDelegationToRequestInputValidator(),
            applier=ConvertDelegationToRequestInputApplier(),
            verifier=ConvertDelegationToRequestInputVerifier(),
            previewer=AddExceptionHandlerStepPreviewer(),
            contract=PatchTypeContract(
                patch_type="ConvertDelegationIntentToRequestInput",
                produces_step_ir=True,
                evidence_targets=("step",),
            ),
        ),
    )

    from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.applier import (
        CreateWorkerHandoffContractApplier,
    )
    from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.validator import (
        CreateWorkerHandoffContractValidator,
    )
    from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.verifier import (
        CreateWorkerHandoffContractVerifier,
    )

    class _HandoffPreviewer:
        def preview(self, payload):
            return f"[INVOKE {payload.get('child_worker_id', '?')}]"

    reg.patches.register(
        "CreateWorkerHandoffContract",
        PatchBundle(
            patch_type="CreateWorkerHandoffContract",
            validator=CreateWorkerHandoffContractValidator(),
            applier=CreateWorkerHandoffContractApplier(),
            verifier=CreateWorkerHandoffContractVerifier(),
            previewer=_HandoffPreviewer(),
            contract=PatchTypeContract(
                patch_type="CreateWorkerHandoffContract",
                produces_step_ir=True,
                produces_handoff_ir=True,
                evidence_targets=("step", "handoff"),
            ),
        ),
    )

    return SPLEditingService(reg, lane_a=LaneAReplayAdapter())


def _build_missing_handler_context_builder():
    """Build LLMRepairContextBuilder with missing_handler provider."""
    from nl2spl.compiler.spl_editing.llm_context.builder import LLMRepairContextBuilder
    from nl2spl.compiler.spl_editing.llm_context.providers.exception_flow_handler import (
        ExceptionFlowHandlerContextProvider,
    )
    from nl2spl.compiler.spl_editing.llm_context.registry import (
        LLMRepairContextExtensionRegistry,
    )

    reg = LLMRepairContextExtensionRegistry()
    reg.register(ExceptionFlowHandlerContextProvider())
    return LLMRepairContextBuilder(provider_registry=reg)


def _build_missing_handler_prompt_renderer():
    """Build PromptRenderer with exception flow section renderer."""
    from nl2spl.compiler.spl_editing.llm_context.renderers.exception_flow_handler_section import (
        ExceptionFlowHandlerSectionRenderer,
    )
    from nl2spl.compiler.spl_editing.llm_context.rendering import PromptRenderer
    from nl2spl.compiler.spl_editing.llm_context.section_renderer import (
        SectionRendererRegistry,
    )

    sreg = SectionRendererRegistry()
    sreg.register(ExceptionFlowHandlerSectionRenderer())
    return PromptRenderer(section_renderer_registry=sreg)


def _build_generic_context_builder():
    """Build a generic LLMRepairContextBuilder with no extra providers."""
    from nl2spl.compiler.spl_editing.llm_context.builder import LLMRepairContextBuilder
    from nl2spl.compiler.spl_editing.llm_context.registry import (
        LLMRepairContextExtensionRegistry,
    )

    reg = LLMRepairContextExtensionRegistry()
    return LLMRepairContextBuilder(provider_registry=reg)


def _build_generic_prompt_renderer():
    """Build a generic PromptRenderer with no extra section renderers."""
    from nl2spl.compiler.spl_editing.llm_context.rendering import PromptRenderer

    return PromptRenderer(section_renderer_registry=None)



def _load_snapshot(run_dir: str) -> ArtifactSnapshot:
    """Load a structured ArtifactSnapshot from *run_dir*.

    Currently supported: a Python pickle file at ``{run_dir}/snapshot.pkl``.
    Raises ``FileNotFoundError`` or ``ValueError`` if structured artifacts
    are missing — never falls back to parsing text/markdown reports.
    """
    path = Path(run_dir) / "spl_editing_snapshot.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"Structured artifact snapshot not found at '{path}'. "
            f"SPL Editing requires spl_editing_snapshot.json, not a "
            f"markdown/text report or stage debug JSON."
        )

    document = SnapshotLoader().load(path)
    return artifact_snapshot_from_document(document)


def _run_demo(snapshot: ArtifactSnapshot) -> None:
    """Run the interactive demo flow."""
    svc = _build_default_service()
    run_id = svc.register_compile_result(snapshot)
    _run_demo_for_run(svc, run_id)


def _run_demo_for_run(
    svc: SPLEditingService,
    run_id: str,
    snapshot_path: Path | None = None,
) -> None:
    from nl2spl.compiler.spl_editing.presentation import (
        SPLEditingPresentationService,
    )

    presentation = SPLEditingPresentationService(svc)

    run_dir = svc._run_dirs.get(run_id)
    run_label = Path(run_dir).name if run_dir is not None else run_id
    if snapshot_path is None and run_dir is not None:
        snapshot_path = Path(run_dir) / "spl_editing_snapshot.json"

    run_view = presentation.get_run_presentation(
        run_id,
        run_label=run_label,
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
    session = svc.create_session(run_id, issue)
    generation = svc.generate_suggestions(
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

    preview = svc.preview_suggestion(
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
    updated = svc.apply_preview_result(
        session.session_id,
        applied_suggestion.suggestion_id,
        preview.preview_id,
        user_text=user_instruction,
    )
    print(f"Applied. overlay_version={updated.overlay_version}")

    print("Verifying patched snapshot...", flush=True)
    result = svc.verify_session(session.session_id)
    patched_spl = None
    if result.accepted:
        patched_spl = svc.get_patched_spl(run_id) or "(empty)"
    verification_view = presentation.present_verification(
        run_id,
        result,
        updated_spl=patched_spl,
    )
    _print_verification(verification_view, failures=result.failure_reasons)


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
        try:
            raw = input("Select issue number to inspect or fix: ").strip()
            if not raw:
                return None
            display_id = int(raw)
        except (ValueError, EOFError):
            return None
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


def _choose_fix_option(available_repairs: Iterable[object]) -> object | None:
    repairs = tuple(available_repairs)
    available = [r for r in repairs if getattr(r, "unavailable_reason", None) is None]
    if not available:
        print("\nNo available repair options for this issue.")
        return None
    while True:
        try:
            raw = input("Choose fix option number: ").strip()
            if not raw:
                return None
            idx = int(raw) - 1
        except (ValueError, EOFError):
            return None
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

def _print_suggestions(suggestions: Iterable[object]) -> None:
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
        try:
            raw = input("Apply suggestion number: ").strip()
            if not raw:
                return None
            idx = int(raw) - 1
        except (ValueError, EOFError):
            return None
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="spl-edit")
    sub = parser.add_subparsers(dest="command", required=True)

    demo_p = sub.add_parser("demo", help="Interactive SPL editing demo")
    demo_p.add_argument(
        "--run",
        required=True,
        dest="run_dir",
        help="Path to structured artifact snapshot directory",
    )

    args = parser.parse_args()

    if args.command == "demo":
        try:
            svc = _build_default_service()
            snapshot_path = Path(args.run_dir) / "spl_editing_snapshot.json"
            run_id = svc.register_snapshot_file(snapshot_path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        _run_demo_for_run(svc, run_id, snapshot_path)


if __name__ == "__main__":
    main()
