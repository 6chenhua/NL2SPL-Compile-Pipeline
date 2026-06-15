"""SPL Editing Demo CLI — thin wrapper over SPLEditingService.

Usage:
    python -m nl2spl.compiler.spl_editing.cli demo --run <run_dir>
"""

from __future__ import annotations

import argparse
import sys
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
    reg.handlers.register(
        "missing_output_producer",
        MissingOutputProducerHandler(suggestion_llm),
    )
    reg.handlers.register(
        "type_or_contract_ambiguity",
        TypeOrContractAmbiguityHandler(suggestion_llm),
    )

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
    from nl2spl.compiler.spl_editing.core.model import PatchTypeContract as _PTC
    reg.patches.register("AddExceptionHandlerStep", PatchBundle(
        patch_type="AddExceptionHandlerStep",
        validator=AddExceptionHandlerStepValidator(),
        applier=AddExceptionHandlerStepApplier(),
        verifier=AddExceptionHandlerStepVerifier(),
        previewer=AddExceptionHandlerStepPreviewer(),
        contract=_PTC(patch_type="AddExceptionHandlerStep",
                       produces_step_ir=True, evidence_targets=("step",)),
    ))
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
    reg.patches.register("InsertProducerStep", PatchBundle(
        patch_type="InsertProducerStep",
        validator=InsertProducerStepValidator(),
        applier=InsertProducerStepApplier(),
        verifier=InsertProducerStepVerifier(),
        previewer=InsertProducerStepPreviewer(),
        contract=_PTC(patch_type="InsertProducerStep",
                       produces_step_ir=True, evidence_targets=("step",)),
    ))
    from nl2spl.compiler.spl_editing.patches.bind_existing_producer_step.applier import (
        BindExistingProducerStepApplier,
    )
    from nl2spl.compiler.spl_editing.patches.bind_existing_producer_step.preview import (
        BindExistingProducerStepPreviewer,
    )
    from nl2spl.compiler.spl_editing.patches.bind_existing_producer_step.validator import (
        BindExistingProducerStepValidator,
    )
    from nl2spl.compiler.spl_editing.patches.bind_existing_producer_step.verifier import (
        BindExistingProducerStepVerifier,
    )
    reg.patches.register("BindExistingProducerStep", PatchBundle(
        patch_type="BindExistingProducerStep",
        validator=BindExistingProducerStepValidator(),
        applier=BindExistingProducerStepApplier(),
        verifier=BindExistingProducerStepVerifier(),
        previewer=BindExistingProducerStepPreviewer(),
        contract=_PTC(patch_type="BindExistingProducerStep",
                       evidence_targets=("step",)),
    ))

    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_main_flow_step.applier import (
        ConvertDelegationToMainFlowStepApplier,
    )
    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_main_flow_step.validator import (
        ConvertDelegationToMainFlowStepValidator,
    )
    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_main_flow_step.verifier import (
        ConvertDelegationToMainFlowStepVerifier,
    )
    reg.patches.register("ConvertDelegationIntentToMainFlowStep", PatchBundle(
        patch_type="ConvertDelegationIntentToMainFlowStep",
        validator=ConvertDelegationToMainFlowStepValidator(),
        applier=ConvertDelegationToMainFlowStepApplier(),
        verifier=ConvertDelegationToMainFlowStepVerifier(),
        previewer=AddExceptionHandlerStepPreviewer(),
        contract=_PTC(patch_type="ConvertDelegationIntentToMainFlowStep",
                       produces_step_ir=True, evidence_targets=("step",)),
    ))
    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_request_input.applier import (
        ConvertDelegationToRequestInputApplier,
    )
    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_request_input.validator import (
        ConvertDelegationToRequestInputValidator,
    )
    from nl2spl.compiler.spl_editing.patches.convert_delegation_to_request_input.verifier import (
        ConvertDelegationToRequestInputVerifier,
    )
    reg.patches.register("ConvertDelegationIntentToRequestInput", PatchBundle(
        patch_type="ConvertDelegationIntentToRequestInput",
        validator=ConvertDelegationToRequestInputValidator(),
        applier=ConvertDelegationToRequestInputApplier(),
        verifier=ConvertDelegationToRequestInputVerifier(),
        previewer=AddExceptionHandlerStepPreviewer(),
        contract=_PTC(patch_type="ConvertDelegationIntentToRequestInput",
                       produces_step_ir=True, evidence_targets=("step",)),
    ))

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
    reg.patches.register("CreateWorkerHandoffContract", PatchBundle(
        patch_type="CreateWorkerHandoffContract",
        validator=CreateWorkerHandoffContractValidator(),
        applier=CreateWorkerHandoffContractApplier(),
        verifier=CreateWorkerHandoffContractVerifier(),
        previewer=_HandoffPreviewer(),
        contract=_PTC(patch_type="CreateWorkerHandoffContract",
                       produces_step_ir=True, produces_handoff_ir=True,
                       evidence_targets=("step", "handoff")),
    ))

    return SPLEditingService(reg, lane_a=LaneAReplayAdapter())


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


def _run_demo_for_run(svc: SPLEditingService, run_id: str) -> None:
    """Run the interactive demo flow for a registered compile run."""
    issues = svc.list_editable_issues(run_id)

    if not issues:
        print("No user-facing editable issues found.")
        return

    print("Editable issues:")
    for idx, issue in enumerate(issues, 1):
        print(f"  [{idx}] {issue.kind}")
        print(f"       target: {issue.target_ref}")
        print(f"       summary: {issue.message[:100]}")
        print(f"       repairability: {issue.repairability}")
        print()

    issue = _choose_issue(issues)
    if issue is None:
        return

    session = svc.create_session(run_id, issue)
    suggestions = svc.generate_suggestions(session.session_id)
    if not suggestions:
        print("No suggestions generated.")
        return

    print("AI repair suggestions:")
    for idx, s in enumerate(suggestions, 1):
        print(f"  [{idx}] {s.title}")
        if s.spl_preview:
            print("       Preview:")
            for line in s.spl_preview.split("\n"):
                print(f"         {line}")
        print()

    sug = _choose_suggestion(suggestions)
    if sug is None:
        return

    print(f"\nApply suggestion: {sug.title}")
    confirm = input("Confirm apply? [y/N] ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    updated = svc.apply_suggestion(session.session_id, sug.suggestion_id)
    print(f"Applied — overlay version {updated.overlay_version}")

    result = svc.verify_session(session.session_id)
    print(f"\nVerification: {'accepted' if result.accepted else 'rejected'}")
    print(f"  lane: {result.lane}")
    if result.resolved_diagnostic_ids:
        print(f"  resolved diagnostics: {', '.join(result.resolved_diagnostic_ids)}")
    if result.new_blocking_diagnostic_ids:
        print(f"  new blocking diagnostics: {', '.join(result.new_blocking_diagnostic_ids)}")
    if result.failure_reasons:
        print(f"  failures: {'; '.join(result.failure_reasons)}")

    # Print patched SPL via service (real Lane A replay)
    if result.accepted:
        spl = svc.get_patched_spl(run_id)
        print("\n--- Patched SPL ---")
        print(spl or "(no SPL produced)")
    print()


def _choose_issue(issues):
    try:
        choice = input("Select issue number: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(issues):
            return issues[idx]
        print(f"Invalid choice: {choice}")
    except (ValueError, EOFError):
        pass
    return None


def _choose_suggestion(suggestions):
    try:
        choice = input("Apply suggestion number: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(suggestions):
            return suggestions[idx]
        print(f"Invalid choice: {choice}")
    except (ValueError, EOFError):
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser(prog="spl-edit")
    sub = parser.add_subparsers(dest="command", required=True)

    demo_p = sub.add_parser("demo", help="Interactive SPL editing demo")
    demo_p.add_argument("--run", required=True, dest="run_dir",
                        help="Path to structured artifact snapshot directory")

    args = parser.parse_args()

    if args.command == "demo":
        try:
            svc = _build_default_service()
            snapshot_path = Path(args.run_dir) / "spl_editing_snapshot.json"
            run_id = svc.register_snapshot_file(snapshot_path)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        _run_demo_for_run(svc, run_id)


if __name__ == "__main__":
    main()
