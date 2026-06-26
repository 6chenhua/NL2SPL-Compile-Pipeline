"""B3: Repair handler and parser tests."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.errors import (
    PatchValidationError,
    UnsupportedIssueError,
    UnsupportedPatchTypeError,
)
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairSuggestion,
    RepairTarget,
)
from nl2spl.compiler.spl_editing.handlers.base import SuggestionPolicy
from nl2spl.compiler.spl_editing.handlers.missing_handler.handler import (
    MissingHandlerRepairHandler,
)
from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload
from nl2spl.compiler.spl_editing.handlers.type_or_contract_ambiguity.handler import (
    TypeOrContractAmbiguityHandler,
)
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from tests.spl_editing_stub_llm import StubSuggestionLLM

_RENDERED_MISSING_HANDLER_PROMPT = (
    "Allowed patch types: AddExceptionHandlerStep\nReturn JSON for AddExceptionHandlerStep."
)


def _issue(**kw: object) -> EditableIssue:
    d: dict[str, object] = dict(
        issue_id="i1",
        primary_diagnostic_id="d1",
        related_diagnostic_ids=("d1",),
        issue_group_id=None,
        kind="missing_handler",
        target_ref="worker:w_main.exception_flow:exc_1",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW", construct_id="x", slot_name="handler_action"
        ),
        missing_slot="handler_action",
        source_span_ids=(),
        message="Template unavailable.",
    )
    d.update(kw)
    return EditableIssue(**d)  # type: ignore[arg-type]


def _target() -> RepairTarget:
    return RepairTarget(
        target_ref="worker:w_main.exception_flow:exc_1",
        target_kind="EXCEPTION_FLOW",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW", construct_id="x", slot_name="handler_action"
        ),
        affordance_id="exception_flow.add_handler_step",
        construct_path=(),
        worker_id="w_main",
    )


def _context() -> RepairContext:
    return RepairContext(issue=_issue(), target=_target())


def _entry() -> RepairCatalogEntry:
    return RepairCatalogEntry(
        entry_id="EXCEPTION_FLOW.handler_action.missing_handler.exception_flow.add_handler_step",
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


# ===========================================================================
# B3-1: Parser rejects unsupported patch types
# ===========================================================================


class TestB3Parser:
    """B3: parse_suggestion_payload rejects unsupported patch types."""

    def test_accepts_allowed_patch_type(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E",'
            '"payload":{"handler_text":"Do work","command_type":"GENERAL_COMMAND"}}'
        )
        data = parse_suggestion_payload(raw, ("AddExceptionHandlerStep",))
        assert data["patch_type"] == "AddExceptionHandlerStep"

    def test_rejects_unsupported_patch_type(self) -> None:
        raw = '{"patch_type":"SomeUnknownPatch","title":"T","explanation":"E","payload":{}}'
        with pytest.raises(UnsupportedPatchTypeError, match="SomeUnknownPatch"):
            parse_suggestion_payload(raw, ("AddExceptionHandlerStep",))

    def test_rejects_malformed_json(self) -> None:
        with pytest.raises(PatchValidationError, match="JSON"):
            parse_suggestion_payload("not json", ("AddExceptionHandlerStep",))

    def test_rejects_missing_keys(self) -> None:
        raw = '{"patch_type":"AddExceptionHandlerStep"}'
        with pytest.raises(PatchValidationError, match="title"):
            parse_suggestion_payload(raw, ("AddExceptionHandlerStep",))

    def test_rejects_empty_payload(self) -> None:
        raw = '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E","payload":{}}'
        with pytest.raises(PatchValidationError, match="handler_text"):
            parse_suggestion_payload(raw, ("AddExceptionHandlerStep",))

    def test_rejects_invalid_command_type(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E",'
            '"payload":{"handler_text":"Do something","command_type":"INVALID"}}'
        )
        with pytest.raises(PatchValidationError, match="command_type"):
            parse_suggestion_payload(raw, ("AddExceptionHandlerStep",))

    def test_rejects_non_string_handler_text(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E",'
            '"payload":{"handler_text":123,"command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(PatchValidationError, match="handler_text"):
            parse_suggestion_payload(raw, ("AddExceptionHandlerStep",))

    def test_accepts_valid_payload(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E",'
            '"payload":{"handler_text":"Do work","command_type":"GENERAL_COMMAND"}}'
        )
        data = parse_suggestion_payload(raw, ("AddExceptionHandlerStep",))
        assert data["payload"]["handler_text"] == "Do work"

    def test_rejects_non_string_input_item(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E",'
            '"payload":{"handler_text":"H","command_type":"GENERAL_COMMAND",'
            '"inputs":[123]}}'
        )
        with pytest.raises(PatchValidationError, match=r"inputs\[0\]"):
            parse_suggestion_payload(raw, ("AddExceptionHandlerStep",))

    def test_rejects_empty_string_output_item(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E",'
            '"payload":{"handler_text":"H","command_type":"GENERAL_COMMAND",'
            '"outputs":[""]}}'
        )
        with pytest.raises(PatchValidationError, match=r"outputs\[0\]"):
            parse_suggestion_payload(raw, ("AddExceptionHandlerStep",))

    def test_rejects_empty_title(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"","explanation":"E",'
            '"payload":{"handler_text":"H","command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(PatchValidationError, match="title"):
            parse_suggestion_payload(raw, ("AddExceptionHandlerStep",))

    def test_rejects_numeric_explanation(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":123,'
            '"payload":{"handler_text":"H","command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(PatchValidationError, match="explanation"):
            parse_suggestion_payload(raw, ("AddExceptionHandlerStep",))


# ===========================================================================
# B3-2: MissingHandlerRepairHandler with stub LLM
# ===========================================================================


class TestB3MissingHandlerHandler:
    """B3: Missing handler generates suggestions via stub LLM."""

    def test_generates_suggestion_with_stub(self) -> None:
        llm = StubSuggestionLLM()
        handler = MissingHandlerRepairHandler(llm)
        suggestions = handler.generate_suggestions(
            _issue(),
            _target(),
            _context(),
            (_entry(),),
            rendered_user_prompt=_RENDERED_MISSING_HANDLER_PROMPT,
        )
        assert len(suggestions) == handler.policy.max_suggestions
        s = suggestions[0]
        assert s.title == "Stub suggestion 1"
        assert s.patch.patch_type == "AddExceptionHandlerStep"
        assert s.patch.payload["command_type"] == "GENERAL_COMMAND"
        assert s.spl_preview is not None
        assert "GENERAL_COMMAND" in s.spl_preview

    def test_malformed_llm_output_raises(self) -> None:
        """B3: malformed LLM output is surfaced."""
        llm = StubSuggestionLLM(
            fixed_response={
                "patch_type": "AddExceptionHandlerStep",
                "title": "T",
                # missing "explanation" key -> parse failure
            }
        )
        handler = MissingHandlerRepairHandler(llm)
        with pytest.raises(PatchValidationError, match="LLM did not produce"):
            handler.generate_suggestions(
                _issue(),
                _target(),
                _context(),
                (_entry(),),
                rendered_user_prompt=_RENDERED_MISSING_HANDLER_PROMPT,
            )

    def test_handler_does_not_write_ir(self) -> None:
        """B3: Handler generates suggestions without importing patch applier."""
        handler = MissingHandlerRepairHandler(StubSuggestionLLM())
        suggestions = handler.generate_suggestions(
            _issue(),
            _target(),
            _context(),
            (_entry(),),
            rendered_user_prompt=_RENDERED_MISSING_HANDLER_PROMPT,
        )
        for s in suggestions:
            assert isinstance(s, RepairSuggestion)
            # No IR mutation --suggestions are pure data

    def test_llm_output_truncated_to_max_suggestions(self) -> None:
        llm = StubSuggestionLLM()
        handler = MissingHandlerRepairHandler(
            llm,
            policy=SuggestionPolicy(max_suggestions=2),
        )
        suggestions = handler.generate_suggestions(
            _issue(),
            _target(),
            _context(),
            (_entry(),),
            rendered_user_prompt=_RENDERED_MISSING_HANDLER_PROMPT,
        )
        assert len(suggestions) == 2

    def test_selected_patch_types_filters_correctly(self) -> None:
        """B3: Missing handler with selected_patch_types still generates suggestions."""
        llm = StubSuggestionLLM()
        handler = MissingHandlerRepairHandler(
            llm,
            policy=SuggestionPolicy(max_suggestions=2),
        )
        suggestions = handler.generate_suggestions(
            _issue(),
            _target(),
            _context(),
            (_entry(),),
            selected_patch_types=("AddExceptionHandlerStep",),
            rendered_user_prompt=_RENDERED_MISSING_HANDLER_PROMPT,
        )
        assert len(suggestions) == 2
        assert all(s.patch.patch_type == "AddExceptionHandlerStep" for s in suggestions)


# ===========================================================================
# B3-3: Error propagation --unsupported patch type is NOT swallowed
# ===========================================================================


class TestB3ErrorPropagation:
    """B3: UnsupportedPatchTypeError propagates, not hidden by fallback."""

    def test_unsupported_patch_type_propagates(self) -> None:
        """B3: Stub returning unsupported patch_type 鈫?UnsupportedPatchTypeError
        propagates to caller, not replaced by fallback.
        """
        llm = StubSuggestionLLM(
            fixed_response={
                "patch_type": "WrongType",
                "title": "Bad",
                "explanation": "Bad",
                "payload": {"handler_text": "X", "command_type": "GENERAL_COMMAND"},
            }
        )
        handler = MissingHandlerRepairHandler(llm)
        with pytest.raises(UnsupportedPatchTypeError):
            handler.generate_suggestions(
                _issue(),
                _target(),
                _context(),
                (_entry(),),
                rendered_user_prompt=_RENDERED_MISSING_HANDLER_PROMPT,
            )


# ===========================================================================
# B3-4: TypeOrContractAmbiguityHandler stub
# ===========================================================================


class TestB3AmbiguityHandler:
    """B3: TypeOrContractAmbiguityHandler uses LLM-backed suggestions."""

    def test_rejects_non_mvp_construct_type(self) -> None:
        handler = TypeOrContractAmbiguityHandler(StubSuggestionLLM())
        issue = EditableIssue(
            issue_id="i1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=("d1",),
            issue_group_id=None,
            kind="type_or_contract_ambiguity",
            target_ref="worker:w_main.step:st1",
            irs_ref=DiagnosticIRSRef(
                construct_type="CALL_API",
                construct_id="x",
                slot_name="api_name",
            ),
            missing_slot="api_name",
            source_span_ids=(),
            message="test",
        )
        with pytest.raises(UnsupportedIssueError, match="CALL_API"):
            handler.generate_suggestions(
                issue,
                _target(),
                _context(),
                (_entry(),),
            )

    def test_mvp_construct_returns_llm_suggestion(self) -> None:
        """B3: WORKER_PROMOTION with correct affordance returns LLM suggestion."""
        handler = TypeOrContractAmbiguityHandler(StubSuggestionLLM())
        issue = EditableIssue(
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
            message="test",
        )
        entry = RepairCatalogEntry(
            entry_id="WORKER_PROMOTION.promotion_input_contract.type_or_contract_ambiguity.worker_promotion.resolve_contract",
            affordance_id="worker_promotion.resolve_contract",
            construct_type="WORKER_PROMOTION",
            slot_name="promotion_input_contract",
            diagnostic_kind="type_or_contract_ambiguity",
            supported_patch_types=(
                "ConvertDelegationIntentToMainFlowStep",
                "ConvertDelegationIntentToRequestInput",
            ),
        )
        result = handler.generate_suggestions(
            issue,
            _target(),
            _context(),
            (entry,),
        )
        assert len(result) >= 1
        types = {r.patch.patch_type for r in result}
        assert "ConvertDelegationIntentToMainFlowStep" in types

    def test_rejects_unrecognized_affordance_subtype(self) -> None:
        """B3: WORKER_PROMOTION with wrong affordance_id 鈫?UnsupportedIssueError."""
        handler = TypeOrContractAmbiguityHandler(StubSuggestionLLM())
        issue = EditableIssue(
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
            message="test",
        )
        entry = RepairCatalogEntry(
            entry_id="x",
            affordance_id="wrong_affordance_id",
            construct_type="WORKER_PROMOTION",
            slot_name="promotion_input_contract",
            diagnostic_kind="type_or_contract_ambiguity",
        )
        with pytest.raises(UnsupportedIssueError, match="not supported"):
            handler.generate_suggestions(
                issue,
                _target(),
                _context(),
                (entry,),
            )

    # ===========================================================================
    # B3-5: Prompt contract includes allowed patch types
    # ===========================================================================

    def test_worker_handoff_subtype_rejected(self) -> None:
        """B3: WORKER_HANDOFF subtype raises UnsupportedIssueError."""
        handler = TypeOrContractAmbiguityHandler(StubSuggestionLLM())
        issue = EditableIssue(
            issue_id="i1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=("d1",),
            issue_group_id=None,
            kind="type_or_contract_ambiguity",
            target_ref="worker_handoff:h1",
            irs_ref=DiagnosticIRSRef(
                construct_type="WORKER_HANDOFF",
                construct_id="x",
                slot_name="target",
            ),
            missing_slot="target",
            source_span_ids=(),
            message="test",
        )
        entry = RepairCatalogEntry(
            entry_id="WORKER_HANDOFF.target.type_or_contract_ambiguity.worker_handoff.specify_target",
            affordance_id="worker_handoff.specify_target",
            construct_type="WORKER_HANDOFF",
            slot_name="target",
            diagnostic_kind="type_or_contract_ambiguity",
        )
        with pytest.raises(UnsupportedIssueError, match="WORKER_HANDOFF"):
            handler.generate_suggestions(
                issue,
                _target(),
                _context(),
                (entry,),
            )

    def test_selected_patch_types_filters_to_single_type(self) -> None:
        """B3: selected_patch_types restricts output to one patch type."""
        llm = StubSuggestionLLM()
        handler = TypeOrContractAmbiguityHandler(
            llm,
            policy=SuggestionPolicy(max_suggestions=3),
        )
        issue = EditableIssue(
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
            message="test",
        )
        entry = RepairCatalogEntry(
            entry_id="WORKER_PROMOTION.promotion_input_contract.type_or_contract_ambiguity.worker_promotion.resolve_contract",
            affordance_id="worker_promotion.resolve_contract",
            construct_type="WORKER_PROMOTION",
            slot_name="promotion_input_contract",
            diagnostic_kind="type_or_contract_ambiguity",
            supported_patch_types=(
                "ConvertDelegationIntentToMainFlowStep",
                "ConvertDelegationIntentToRequestInput",
            ),
        )
        result = handler.generate_suggestions(
            issue,
            _target(),
            _context(),
            (entry,),
            selected_patch_types=("ConvertDelegationIntentToMainFlowStep",),
        )
        assert len(result) == 3
        # All suggestions must be the selected type
        types = {r.patch.patch_type for r in result}
        assert types == {"ConvertDelegationIntentToMainFlowStep"}

    def test_selected_patch_type_returns_multiple_suggestions(self) -> None:
        """B3: Single selected patch type returns multiple unique suggestions."""
        llm = StubSuggestionLLM()
        handler = TypeOrContractAmbiguityHandler(
            llm,
            policy=SuggestionPolicy(max_suggestions=3),
        )
        issue = EditableIssue(
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
            message="test",
        )
        entry = RepairCatalogEntry(
            entry_id="WORKER_PROMOTION.promotion_input_contract.type_or_contract_ambiguity.worker_promotion.resolve_contract",
            affordance_id="worker_promotion.resolve_contract",
            construct_type="WORKER_PROMOTION",
            slot_name="promotion_input_contract",
            diagnostic_kind="type_or_contract_ambiguity",
            supported_patch_types=(
                "ConvertDelegationIntentToMainFlowStep",
                "ConvertDelegationIntentToRequestInput",
            ),
        )
        result = handler.generate_suggestions(
            issue,
            _target(),
            _context(),
            (entry,),
            selected_patch_types=("ConvertDelegationIntentToMainFlowStep",),
        )
        assert len(result) == 3
        assert len({r.patch.payload["action_text"] for r in result}) == 3
        assert all(r.patch.patch_type == "ConvertDelegationIntentToMainFlowStep" for r in result)


class TestB3PromptContract:
    """B3: Prompts include catalog-derived allowed patch types."""

    def test_missing_handler_prompt_includes_allowed_types(self) -> None:
        from nl2spl.compiler.spl_editing.handlers.missing_handler.prompt import (
            build_missing_handler_user_prompt,
        )

        prompt = build_missing_handler_user_prompt(
            condition_text="Template unavailable.",
            target_ref="worker:w_main.exception_flow:exc_1",
            allowed_patch_types=("AddExceptionHandlerStep",),
        )
        assert "AddExceptionHandlerStep" in prompt
        assert "Allowed patch types" in prompt

    def test_missing_handler_system_prompt_has_no_demo_answers(self) -> None:
        from nl2spl.compiler.spl_editing.handlers.missing_handler.prompt import (
            MISSING_HANDLER_SYSTEM_PROMPT,
        )

        forbidden = (
            "Missing timeframe",
            "default timeframe",
            "insufficient source access",
            "alternative_sources",
        )
        for text in forbidden:
            assert text not in MISSING_HANDLER_SYSTEM_PROMPT

    def test_previous_suggestions_are_not_copied_into_handler_prompts(self) -> None:
        from nl2spl.compiler.spl_editing.handlers.missing_handler.prompt import (
            build_missing_handler_user_prompt,
        )
        from nl2spl.compiler.spl_editing.handlers.missing_output_producer.prompt import (
            build_missing_output_user_prompt,
        )
        from nl2spl.compiler.spl_editing.handlers.type_or_contract_ambiguity.prompt import (
            build_type_or_contract_user_prompt,
        )

        previous = ("Ask the user to provide the missing timeframe",)
        prompts = (
            build_missing_handler_user_prompt(
                condition_text="Condition text",
                target_ref="target",
                allowed_patch_types=("AddExceptionHandlerStep",),
                previous_suggestions=previous,
            ),
            build_missing_output_user_prompt(
                output_name="result",
                target_ref="target",
                allowed_patch_types=("InsertProducerStep",),
                previous_suggestions=previous,
            ),
            build_type_or_contract_user_prompt(
                issue_message="Issue text",
                target_ref="target",
                construct_type="WORKER_PROMOTION",
                slot_name="promotion_input_contract",
                allowed_patch_types=("ConvertDelegationIntentToMainFlowStep",),
                parent_worker_id="parent",
                child_worker_id="child",
                child_input_fields=(),
                child_output_fields=(),
                previous_suggestions=previous,
            ),
        )
        for prompt in prompts:
            assert "Previous candidate count: 1" in prompt
            assert previous[0] not in prompt
            assert "generate something DIFFERENT" not in prompt

    def test_append_previous_suggestions_does_not_copy_answers(self) -> None:
        from nl2spl.compiler.spl_editing.llm_context.rendering import (
            append_previous_suggestions,
        )

        previous = ("Ask the user to provide the missing timeframe",)
        prompt = append_previous_suggestions("base prompt", previous)
        assert "Previous candidate count: 1" in prompt
        assert previous[0] not in prompt
        assert "generate something DIFFERENT" not in prompt


# ===========================================================================
# B3-6: Stub LLM adapter contract
# ===========================================================================


class TestB3StubAdapterContract:
    """B3: StubSuggestionLLM records calls including prompts."""

    def test_stub_records_prompt_calls(self) -> None:
        llm = StubSuggestionLLM(
            fixed_response={
                "patch_type": "AddExceptionHandlerStep",
                "title": "T",
                "explanation": "E",
                "payload": {"handler_text": "H", "command_type": "GENERAL_COMMAND"},
            }
        )
        llm.generate_json("system", "user")
        assert len(llm.calls) == 1
        assert llm.calls[0]["system_prompt"] == "system"
        assert llm.calls[0]["user_prompt"] == "user"

    def test_handler_provides_prompt_with_allowed_types(self) -> None:
        """B3: Handler passes allowed patch types via prompt builder."""
        llm = StubSuggestionLLM(
            fixed_response={
                "patch_type": "AddExceptionHandlerStep",
                "title": "T",
                "explanation": "E",
                "payload": {"handler_text": "H", "command_type": "GENERAL_COMMAND"},
            }
        )
        handler = MissingHandlerRepairHandler(llm, policy=SuggestionPolicy(max_suggestions=1))
        handler.generate_suggestions(
            _issue(),
            _target(),
            _context(),
            (_entry(),),
            rendered_user_prompt=_RENDERED_MISSING_HANDLER_PROMPT,
        )
        user_prompt = llm.calls[0]["user_prompt"]
        assert "Allowed patch types" in user_prompt
        assert "AddExceptionHandlerStep" in user_prompt
