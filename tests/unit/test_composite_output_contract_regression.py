"""
Phase 0 future contract regression tests.
These tests describe the expected contract behavior and must pass now.
"""

from __future__ import annotations

import pytest

from nl2spl.pipeline.stages.stage11_spl_renderer.clause_builder import (
    ClauseBuilderMixin,
)
from nl2spl.validator.static_validator import (
    DIAGNOSTIC_INVALID_FIELD_ASSIGNMENT_TARGET,
    DIAGNOSTIC_MULTI_COMMAND_RESULT,
    StaticValidator,
)


class _ClauseBuilder(ClauseBuilderMixin):
    def __init__(self) -> None:
        self._produced_variables: set[str] = set()
        self._result_data_types: dict[str, str] = {}

    def _format_data_type(self, data_type: str) -> str:
        return data_type

    def _result_item(self, variable_name: str) -> str:
        return f"{variable_name}: text"


def wrap_in_spl(command_line: str) -> str:
    return (
        '[DEFINE_AGENT: Agent "Test"]\n'
        "[DEFINE_PERSONA:]\n"
        "ROLE: Tester\n"
        "[END_PERSONA]\n"
        "[DEFINE_VARIABLES:]\n"
        "[END_VARIABLES]\n"
        '[DEFINE_WORKER: "Test" MainWorker]\n'
        "    [INPUTS]\n"
        "    [END_INPUTS]\n"
        "    [OUTPUTS]\n"
        "    [END_OUTPUTS]\n"
        "    [MAIN_FLOW]\n"
        "        [SEQUENTIAL_BLOCK]\n"
        f"            COMMAND-1 {command_line}\n"
        "        [END_SEQUENTIAL_BLOCK]\n"
        "    [END_MAIN_FLOW]\n"
        "[END_WORKER]\n"
        "[END_AGENT]"
    )


def test_static_validator_rejects_multi_result_command() -> None:
    validator = StaticValidator()
    spl = wrap_in_spl("[COMMAND Do work RESULT a: text, b: text SET]")
    result = validator.validate(spl)
    errors = [e for e in result.errors if e.diagnostic_code == DIAGNOSTIC_MULTI_COMMAND_RESULT]
    assert len(errors) == 1


def test_static_validator_rejects_multi_result_response() -> None:
    validator = StaticValidator()
    spl = wrap_in_spl("[CALL SearchAPI RESPONSE a: text, b: text SET]")
    result = validator.validate(spl)
    errors = [e for e in result.errors if e.diagnostic_code == DIAGNOSTIC_MULTI_COMMAND_RESULT]
    assert len(errors) == 1


def test_static_validator_rejects_multi_result_value() -> None:
    validator = StaticValidator()
    spl = wrap_in_spl("[INPUT Ask VALUE a: text, b: text SET]")
    result = validator.validate(spl)
    errors = [e for e in result.errors if e.diagnostic_code == DIAGNOSTIC_MULTI_COMMAND_RESULT]
    assert len(errors) == 1


def test_static_validator_allows_qualified_read_ref() -> None:
    validator = StaticValidator()
    spl = wrap_in_spl("[COMMAND Do work VALUE <REF>agg.field</REF> SET]")
    result = validator.validate(spl)
    warnings = [e for e in result.errors if e.severity == "warning"]
    # There should be no warnings about invalid identifier for qualified reference
    assert len(warnings) == 0


def test_static_validator_rejects_qualified_write_target() -> None:
    validator = StaticValidator()
    spl = wrap_in_spl("[COMMAND Do work RESULT <REF>agg.field</REF> SET]")
    result = validator.validate(spl)
    errors = [
        e for e in result.errors if e.diagnostic_code == DIAGNOSTIC_INVALID_FIELD_ASSIGNMENT_TARGET
    ]
    assert len(errors) == 1


def test_renderer_result_clause_fails_closed_for_multiple_outputs() -> None:
    builder = _ClauseBuilder()
    with pytest.raises(ValueError, match="Composite lowering must have run"):
        builder._result_clause("RESULT", ["a", "b"])
