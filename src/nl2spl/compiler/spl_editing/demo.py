"""Demo CLI for SPL Editing — thin wrapper over SPLEditingService.

Usage:
    spl-edit issues --run <run_id>
    spl-edit suggest --run <run_id> --diagnostic <diag_id> [--instruction "..."]
    spl-edit apply --session <session_id> --suggestion <sug_id>
    spl-edit verify --session <session_id>
    spl-edit demo --run <run_id>
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.registry import SPLEditingRuntimeRegistry
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.core.service import SPLEditingService
from nl2spl.compiler.spl_editing.patches.registry import PatchBundle


def _build_default_service(suggestion_llm=None) -> SPLEditingService:
    """Build a service with MVP registrations wired."""
    reg = SPLEditingRuntimeRegistry()
    if suggestion_llm is None:
        from nl2spl.compiler.spl_editing.cli import build_suggestion_llm_from_env

        suggestion_llm = build_suggestion_llm_from_env()

    # Target resolvers
    from nl2spl.compiler.spl_editing.targets.exception_flow import (
        ExceptionFlowTargetResolver,
    )
    from nl2spl.compiler.spl_editing.targets.required_output import (
        RequiredOutputTargetResolver,
    )
    from nl2spl.compiler.spl_editing.targets.worker_handoff import (
        WorkerHandoffTargetResolver,
    )
    from nl2spl.compiler.spl_editing.targets.worker_promotion import (
        WorkerPromotionTargetResolver,
    )

    reg.target_resolvers.register("exception_flow_target", ExceptionFlowTargetResolver())
    reg.target_resolvers.register("required_output_target", RequiredOutputTargetResolver())
    reg.target_resolvers.register("worker_promotion_target", WorkerPromotionTargetResolver())
    reg.target_resolvers.register("handoff_target", WorkerHandoffTargetResolver())

    # Context builders
    from nl2spl.compiler.spl_editing.context.exception_flow_context import (
        ExceptionFlowContextBuilder,
    )
    from nl2spl.compiler.spl_editing.context.required_output_context import (
        RequiredOutputContextBuilder,
    )
    from nl2spl.compiler.spl_editing.context.worker_handoff_context import (
        WorkerHandoffContextBuilder,
    )
    from nl2spl.compiler.spl_editing.context.worker_promotion_context import (
        WorkerPromotionContextBuilder,
    )

    reg.context_builders.register("exception_flow_context", ExceptionFlowContextBuilder())
    reg.context_builders.register("required_output_context", RequiredOutputContextBuilder())
    reg.context_builders.register("worker_promotion_context", WorkerPromotionContextBuilder())
    reg.context_builders.register("handoff_context", WorkerHandoffContextBuilder())

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

    # Patches (validators + appliers + verifiers)
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


    from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.preview import (
        AddExceptionHandlerStepPreviewer,
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

    from nl2spl.compiler.spl_editing.patches.define_child_worker_closure import (
        register_define_child_worker_closure_patch,
    )

    register_define_child_worker_closure_patch(reg)

    return SPLEditingService(reg)


def _build_missing_handler_context_builder():
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



def demo_flow(snapshot: ArtifactSnapshot, instruction: str | None = None) -> None:
    """Run an interactive demo flow over a snapshot."""
    svc = _build_default_service()
    run_id = svc.register_compile_result(snapshot)

    issues = svc.list_editable_issues(run_id)
    if not issues:
        print("No editable issues found.")
        return

    print("Editable issues:")
    for idx, issue in enumerate(issues, 1):
        print(f"  [{idx}] {issue.kind} — {issue.message[:80]}")
    print()

    # Select first issue for demo
    issue = issues[0]
    print(f"Selecting issue: {issue.kind} ({issue.issue_id})")

    session = svc.create_session(run_id, issue)
    print(f"Session created: {session.session_id}")

    generation = svc.generate_suggestions(session.session_id, instruction)
    suggestions = generation.suggestions
    label = "suggestion" if len(suggestions) == 1 else "suggestions"
    print(f"\nAI repair {label} ({len(suggestions)}):")
    for idx, s in enumerate(suggestions, 1):
        print(f"  [{idx}] {s.title}")
        if s.spl_preview:
            print(f"       Preview: {s.spl_preview}")
    print()

    if suggestions:
        sug = suggestions[0]
        print(f"Applying suggestion: {sug.title}")
        updated = svc.apply_suggestion(session.session_id, sug.suggestion_id)
        print(f"Applied — overlay version {updated.overlay_version}")

        result = svc.verify_session(session.session_id)
        print(f"\nVerification: {'accepted' if result.accepted else 'rejected'}")
        if result.resolved_diagnostic_ids:
            print(f"  Resolved: {', '.join(result.resolved_diagnostic_ids)}")
        if result.failure_reasons:
            print(f"  Failures: {', '.join(result.failure_reasons)}")
