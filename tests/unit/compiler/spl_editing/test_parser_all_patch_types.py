"""Parser validation coverage for all 6 registered patch types."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.errors import (
    PatchValidationError,
    UnsupportedPatchTypeError,
)
from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _parse(raw: str, *allowed: str) -> dict:
    return parse_suggestion_payload(raw, allowed)


# ---------------------------------------------------------------------------
# Common rejections (patch-type agnostic)
# ---------------------------------------------------------------------------


class TestCommonRejections:
    def test_rejects_malformed_json(self) -> None:
        with pytest.raises(PatchValidationError, match="JSON"):
            _parse("not json", "AddExceptionHandlerStep")

    def test_rejects_non_dict(self) -> None:
        with pytest.raises(PatchValidationError, match="object"):
            _parse("[]", "AddExceptionHandlerStep")

    def test_rejects_missing_patch_type(self) -> None:
        raw = '{"title":"T","explanation":"E","payload":{}}'
        with pytest.raises(PatchValidationError, match="patch_type"):
            _parse(raw, "AddExceptionHandlerStep")

    def test_rejects_unsupported_patch_type(self) -> None:
        raw = '{"patch_type":"WrongType","title":"T","explanation":"E","payload":{}}'
        with pytest.raises(UnsupportedPatchTypeError, match="WrongType"):
            _parse(raw, "AddExceptionHandlerStep")

    def test_rejects_missing_title(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","explanation":"E",'
            '"payload":{"handler_text":"H","command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(PatchValidationError, match="title"):
            _parse(raw, "AddExceptionHandlerStep")

    def test_rejects_empty_title(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"","explanation":"E",'
            '"payload":{"handler_text":"H","command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(PatchValidationError, match="title"):
            _parse(raw, "AddExceptionHandlerStep")

    def test_rejects_missing_explanation(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T",'
            '"payload":{"handler_text":"H","command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(PatchValidationError, match="explanation"):
            _parse(raw, "AddExceptionHandlerStep")

    def test_rejects_non_string_explanation(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":123,'
            '"payload":{"handler_text":"H","command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(PatchValidationError, match="explanation"):
            _parse(raw, "AddExceptionHandlerStep")


# ---------------------------------------------------------------------------
# AddExceptionHandlerStep (existing — confirm still works)
# ---------------------------------------------------------------------------


class TestAddExceptionHandlerPayload:
    PATCH = "AddExceptionHandlerStep"

    def test_valid_payload(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E",'
            '"payload":{"handler_text":"Do work","command_type":"GENERAL_COMMAND"}}'
        )
        data = _parse(raw, self.PATCH)
        assert data["patch_type"] == self.PATCH
        assert data["payload"]["handler_text"] == "Do work"

    def test_missing_handler_text(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E",'
            '"payload":{"command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(PatchValidationError, match="handler_text"):
            _parse(raw, self.PATCH)

    def test_invalid_command_type(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E",'
            '"payload":{"handler_text":"H","command_type":"INVALID"}}'
        )
        with pytest.raises(PatchValidationError, match="command_type"):
            _parse(raw, self.PATCH)

    def test_rejects_non_list_inputs(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E",'
            '"payload":{"handler_text":"H","command_type":"GENERAL_COMMAND","inputs":"x"}}'
        )
        with pytest.raises(PatchValidationError, match="inputs"):
            _parse(raw, self.PATCH)

    def test_rejects_non_string_input_item(self) -> None:
        raw = (
            '{"patch_type":"AddExceptionHandlerStep","title":"T","explanation":"E",'
            '"payload":{"handler_text":"H","command_type":"GENERAL_COMMAND","inputs":[123]}}'
        )
        with pytest.raises(PatchValidationError, match=r"inputs\[0\]"):
            _parse(raw, self.PATCH)


# ---------------------------------------------------------------------------
# InsertProducerStep
# ---------------------------------------------------------------------------


class TestInsertProducerPayload:
    PATCH = "InsertProducerStep"

    def test_valid_payload(self) -> None:
        raw = (
            '{"patch_type":"InsertProducerStep","title":"T","explanation":"E",'
            '"payload":{"producer_text":"Produce output.","command_type":"GENERAL_COMMAND"}}'
        )
        data = _parse(raw, self.PATCH)
        assert data["patch_type"] == self.PATCH
        assert data["payload"]["producer_text"] == "Produce output."

    def test_missing_producer_text(self) -> None:
        raw = (
            '{"patch_type":"InsertProducerStep","title":"T","explanation":"E",'
            '"payload":{"command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(PatchValidationError, match="producer_text"):
            _parse(raw, self.PATCH)

    def test_empty_producer_text(self) -> None:
        raw = (
            '{"patch_type":"InsertProducerStep","title":"T","explanation":"E",'
            '"payload":{"producer_text":"","command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(PatchValidationError, match="producer_text"):
            _parse(raw, self.PATCH)

    def test_non_string_producer_text(self) -> None:
        raw = (
            '{"patch_type":"InsertProducerStep","title":"T","explanation":"E",'
            '"payload":{"producer_text":123,"command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(PatchValidationError, match="producer_text"):
            _parse(raw, self.PATCH)

    def test_invalid_command_type(self) -> None:
        raw = (
            '{"patch_type":"InsertProducerStep","title":"T","explanation":"E",'
            '"payload":{"producer_text":"P","command_type":"INVALID"}}'
        )
        with pytest.raises(PatchValidationError, match="command_type"):
            _parse(raw, self.PATCH)

    def test_accepts_request_input_command_type(self) -> None:
        raw = (
            '{"patch_type":"InsertProducerStep","title":"T","explanation":"E",'
            '"payload":{"producer_text":"Ask user.","command_type":"REQUEST_INPUT"}}'
        )
        data = _parse(raw, self.PATCH)
        assert data["payload"]["command_type"] == "REQUEST_INPUT"



# ---------------------------------------------------------------------------
# ConvertDelegationIntentToMainFlowStep
# ---------------------------------------------------------------------------


class TestConvertToMainFlowPayload:
    PATCH = "ConvertDelegationIntentToMainFlowStep"

    def test_valid_payload(self) -> None:
        raw = (
            '{"patch_type":"ConvertDelegationIntentToMainFlowStep","title":"T",'
            '"explanation":"E","payload":{"action_text":"Do the task."}}'
        )
        data = _parse(raw, self.PATCH)
        assert data["payload"]["action_text"] == "Do the task."

    def test_missing_action_text(self) -> None:
        raw = (
            '{"patch_type":"ConvertDelegationIntentToMainFlowStep","title":"T",'
            '"explanation":"E","payload":{}}'
        )
        with pytest.raises(PatchValidationError, match="action_text"):
            _parse(raw, self.PATCH)

    def test_empty_action_text(self) -> None:
        raw = (
            '{"patch_type":"ConvertDelegationIntentToMainFlowStep","title":"T",'
            '"explanation":"E","payload":{"action_text":""}}'
        )
        with pytest.raises(PatchValidationError, match="action_text"):
            _parse(raw, self.PATCH)


# ---------------------------------------------------------------------------
# ConvertDelegationIntentToRequestInput
# ---------------------------------------------------------------------------


class TestConvertToRequestInputPayload:
    PATCH = "ConvertDelegationIntentToRequestInput"

    def test_valid_payload(self) -> None:
        raw = (
            '{"patch_type":"ConvertDelegationIntentToRequestInput","title":"T",'
            '"explanation":"E","payload":{"prompt_text":"Provide details.",'
            '"value_target":"details"}}'
        )
        data = _parse(raw, self.PATCH)
        assert data["payload"]["prompt_text"] == "Provide details."
        assert data["payload"]["value_target"] == "details"

    def test_missing_prompt_text(self) -> None:
        raw = (
            '{"patch_type":"ConvertDelegationIntentToRequestInput","title":"T",'
            '"explanation":"E","payload":{"value_target":"v"}}'
        )
        with pytest.raises(PatchValidationError, match="prompt_text"):
            _parse(raw, self.PATCH)

    def test_missing_value_target(self) -> None:
        raw = (
            '{"patch_type":"ConvertDelegationIntentToRequestInput","title":"T",'
            '"explanation":"E","payload":{"prompt_text":"P"}}'
        )
        with pytest.raises(PatchValidationError, match="value_target"):
            _parse(raw, self.PATCH)

    def test_empty_value_target(self) -> None:
        raw = (
            '{"patch_type":"ConvertDelegationIntentToRequestInput","title":"T",'
            '"explanation":"E","payload":{"prompt_text":"P","value_target":""}}'
        )
        with pytest.raises(PatchValidationError, match="value_target"):
            _parse(raw, self.PATCH)


# ---------------------------------------------------------------------------
# CreateWorkerHandoffContract
# ---------------------------------------------------------------------------


class TestCreateHandoffPayload:
    PATCH = "CreateWorkerHandoffContract"

    def test_valid_payload(self) -> None:
        raw = (
            '{"patch_type":"CreateWorkerHandoffContract","title":"T",'
            '"explanation":"E","payload":{"input_bindings":{"req":"req"},'
            '"output_bindings":{"res":"res"},"invocation_point":"main"}}'
        )
        data = _parse(raw, self.PATCH)
        assert data["payload"]["input_bindings"] == {"req": "req"}
        assert data["payload"]["output_bindings"] == {"res": "res"}
        assert data["payload"]["invocation_point"] == "main"

    def test_missing_input_bindings(self) -> None:
        raw = (
            '{"patch_type":"CreateWorkerHandoffContract","title":"T",'
            '"explanation":"E","payload":{"output_bindings":{"a":"b"},'
            '"invocation_point":"main"}}'
        )
        with pytest.raises(PatchValidationError, match="input_bindings"):
            _parse(raw, self.PATCH)

    def test_empty_input_bindings(self) -> None:
        raw = (
            '{"patch_type":"CreateWorkerHandoffContract","title":"T",'
            '"explanation":"E","payload":{"input_bindings":{},'
            '"output_bindings":{"a":"b"},"invocation_point":"main"}}'
        )
        with pytest.raises(PatchValidationError, match="input_bindings"):
            _parse(raw, self.PATCH)

    def test_input_bindings_not_a_dict(self) -> None:
        raw = (
            '{"patch_type":"CreateWorkerHandoffContract","title":"T",'
            '"explanation":"E","payload":{"input_bindings":"not_a_dict",'
            '"output_bindings":{"a":"b"},"invocation_point":"main"}}'
        )
        with pytest.raises(PatchValidationError, match="input_bindings"):
            _parse(raw, self.PATCH)

    def test_missing_invocation_point(self) -> None:
        raw = (
            '{"patch_type":"CreateWorkerHandoffContract","title":"T",'
            '"explanation":"E","payload":{"input_bindings":{"a":"b"},'
            '"output_bindings":{"c":"d"}}}'
        )
        with pytest.raises(PatchValidationError, match="invocation_point"):
            _parse(raw, self.PATCH)


# ---------------------------------------------------------------------------
# Boundary: UnsupportedPatchTypeError always propagates
# ---------------------------------------------------------------------------


class TestUnsupportedPatchTypePropagation:
    """Unsupported patch type must raise, never be swallowed by any validator."""

    def test_unsupported_propagates_for_insert_producer(self) -> None:
        raw = (
            '{"patch_type":"WrongType","title":"T","explanation":"E",'
            '"payload":{"producer_text":"P","command_type":"GENERAL_COMMAND"}}'
        )
        with pytest.raises(UnsupportedPatchTypeError):
            _parse(raw, "InsertProducerStep")

    def test_unsupported_propagates_for_handoff(self) -> None:
        raw = (
            '{"patch_type":"WrongType","title":"T","explanation":"E",'
            '"payload":{"input_bindings":{"a":"b"},"output_bindings":{"c":"d"},'
            '"invocation_point":"main"}}'
        )
        with pytest.raises(UnsupportedPatchTypeError):
            _parse(raw, "CreateWorkerHandoffContract")
