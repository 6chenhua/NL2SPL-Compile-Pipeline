"""Handler LLM failure contract tests.

Repair handlers must surface malformed LLM output instead of hiding
the error behind local suggestions.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairTarget,
)
from nl2spl.compiler.spl_editing.handlers.missing_handler.handler import (
    MissingHandlerRepairHandler,
)
from nl2spl.compiler.spl_editing.handlers.missing_output_producer.handler import (
    MissingOutputProducerHandler,
)
from nl2spl.compiler.spl_editing.handlers.type_or_contract_ambiguity.handler import (
    TypeOrContractAmbiguityHandler,
)
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from tests.spl_editing_stub_llm import StubSuggestionLLM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exception_issue(**overrides: object) -> EditableIssue:
    d: dict[str, object] = dict(
        issue_id="i1",
        primary_diagnostic_id="d1",
        related_diagnostic_ids=("d1",),
        issue_group_id=None,
        kind="missing_handler",
        target_ref="worker:w_main.exception_flow:exc_1",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="x",
            slot_name="handler_action",
        ),
        missing_slot="handler_action",
        source_span_ids=(),
        message="Template unavailable.",
    )
    d.update(overrides)
    return EditableIssue(**d)  # type: ignore[arg-type]


def _exception_target() -> RepairTarget:
    return RepairTarget(
        target_ref="worker:w_main.exception_flow:exc_1",
        target_kind="EXCEPTION_FLOW",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="x",
            slot_name="handler_action",
        ),
        affordance_id="exception_flow.add_handler_step",
        construct_path=(),
        worker_id="w_main",
    )


def _exception_context() -> RepairContext:
    return RepairContext(issue=_exception_issue(), target=_exception_target())


def _exception_entry() -> RepairCatalogEntry:
    return RepairCatalogEntry(
        entry_id="EXCEPTION_FLOW.handler_action.missing_handler."
        "exception_flow.add_handler_step",
        affordance_id="exception_flow.add_handler_step",
        construct_type="EXCEPTION_FLOW",
        slot_name="handler_action",
        diagnostic_kind="missing_handler",
        handler_id="missing_handler",
        context_id="exception_flow_context",
        target_resolver_id="exception_flow_target",
        supported_patch_types=("AddExceptionHandlerStep",),
        default_patch_type="AddExceptionHandlerStep",
        default_verification_lane="A",
    )


def _output_issue() -> EditableIssue:
    return EditableIssue(
        issue_id="i1",
        primary_diagnostic_id="d1",
        related_diagnostic_ids=("d1",),
        issue_group_id=None,
        kind="missing_output_producer",
        target_ref="worker:w_main.output:draft",
        irs_ref=DiagnosticIRSRef(
            construct_type="REQUIRED_OUTPUT",
            construct_id="x",
            slot_name="producer",
        ),
        missing_slot="producer",
        source_span_ids=(),
        message="No producer for draft.",
    )


def _output_target() -> RepairTarget:
    return RepairTarget(
        target_ref="worker:w_main.output:draft",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=DiagnosticIRSRef(
            construct_type="REQUIRED_OUTPUT",
            construct_id="x",
            slot_name="producer",
        ),
        affordance_id="required_output.insert_or_bind_producer",
        construct_path=(),
        worker_id="w_main",
    )


def _output_context() -> RepairContext:
    return RepairContext(issue=_output_issue(), target=_output_target())


def _output_entry() -> RepairCatalogEntry:
    return RepairCatalogEntry(
        entry_id="REQUIRED_OUTPUT.producer.missing_output_producer."
        "required_output.insert_or_bind_producer",
        affordance_id="required_output.insert_or_bind_producer",
        construct_type="REQUIRED_OUTPUT",
        slot_name="producer",
        diagnostic_kind="missing_output_producer",
        handler_id="missing_output_producer",
        context_id="required_output_context",
        target_resolver_id="required_output_target",
        supported_patch_types=("InsertProducerStep", "BindExistingProducerStep"),
        default_patch_type="InsertProducerStep",
        default_verification_lane="A",
    )


def _promotion_issue() -> EditableIssue:
    return EditableIssue(
        issue_id="i1",
        primary_diagnostic_id="d1",
        related_diagnostic_ids=("d1",),
        issue_group_id=None,
        kind="type_or_contract_ambiguity",
        target_ref="worker_promotion:cand_1",
        irs_ref=DiagnosticIRSRef(
            construct_type="WORKER_PROMOTION",
            construct_id="x",
            slot_name="promotion_input_contract",
        ),
        missing_slot="promotion_input_contract",
        source_span_ids=(),
        message="Unclear contract.",
    )


def _promotion_target() -> RepairTarget:
    return RepairTarget(
        target_ref="worker_promotion:cand_1",
        target_kind="WORKER_PROMOTION",
        irs_ref=DiagnosticIRSRef(
            construct_type="WORKER_PROMOTION",
            construct_id="x",
            slot_name="promotion_input_contract",
        ),
        affordance_id="worker_promotion.resolve_contract",
        construct_path=(),
        worker_id="w_main",
    )


def _promotion_context() -> RepairContext:
    return RepairContext(
        issue=_promotion_issue(),
        target=_promotion_target(),
        metadata={},
    )


def _promotion_entry() -> RepairCatalogEntry:
    return RepairCatalogEntry(
        entry_id="WORKER_PROMOTION.promotion_input_contract."
        "type_or_contract_ambiguity.worker_promotion.resolve_contract",
        affordance_id="worker_promotion.resolve_contract",
        construct_type="WORKER_PROMOTION",
        slot_name="promotion_input_contract",
        diagnostic_kind="type_or_contract_ambiguity",
        supported_patch_types=(
            "ConvertDelegationIntentToMainFlowStep",
            "ConvertDelegationIntentToRequestInput",
        ),
    )


# ---------------------------------------------------------------------------
# Tests: MissingHandler LLM failure
# ---------------------------------------------------------------------------


class TestMissingHandlerLLMFailure:
    def test_malformed_llm_raises(self) -> None:
        """Missing handler: malformed LLM output is not hidden."""
        llm = StubSuggestionLLM(fixed_response={
            "patch_type": "AddExceptionHandlerStep",
            "title": "T",
            # missing payload -> parse failure
        })
        handler = MissingHandlerRepairHandler(llm)
        with pytest.raises(PatchValidationError, match="LLM did not produce"):
            handler.generate_suggestions(
                _exception_issue(), _exception_target(),
                _exception_context(), (_exception_entry(),),
            )


# ---------------------------------------------------------------------------
# Tests: MissingOutputProducer LLM failure
# ---------------------------------------------------------------------------


class TestMissingOutputProducerLLMFailure:
    def test_malformed_llm_raises(self) -> None:
        """Output producer: malformed LLM output is not hidden."""
        llm = StubSuggestionLLM(fixed_response={"not": "valid"})
        handler = MissingOutputProducerHandler(llm)
        with pytest.raises(PatchValidationError, match="LLM did not produce"):
            handler.generate_suggestions(
                _output_issue(), _output_target(),
                _output_context(), (_output_entry(),),
            )


# ---------------------------------------------------------------------------
# Tests: TypeOrContractAmbiguity LLM failure
# ---------------------------------------------------------------------------


class TestAmbiguityHandlerLLMFailure:
    def test_malformed_llm_raises(self) -> None:
        """Ambiguity handler: malformed LLM output is not hidden."""
        llm = StubSuggestionLLM(fixed_response={"not": "valid"})
        handler = TypeOrContractAmbiguityHandler(llm)
        with pytest.raises(PatchValidationError, match="LLM did not produce"):
            handler.generate_suggestions(
                _promotion_issue(), _promotion_target(),
                _promotion_context(), (_promotion_entry(),),
            )
