"""Retired current-behavior locks for composite output lowering.

These assertions verify that the old multi-result renderer/validator behavior
is gone. They intentionally contain no xfail markers.
"""

from __future__ import annotations

import pytest

from nl2spl.pipeline.stages.stage11_spl_renderer.clause_builder import (
    ClauseBuilderMixin,
)
from nl2spl.validator.static_validator import (
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


def _wrap_in_spl(command_line: str) -> str:
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


def test_previous_multi_result_validator_behavior_is_retired() -> None:
    result = StaticValidator().validate(
        _wrap_in_spl("[COMMAND Do work RESULT a: text, b: text SET]")
    )
    assert any(error.diagnostic_code == DIAGNOSTIC_MULTI_COMMAND_RESULT for error in result.errors)


def test_previous_qualified_ref_warning_behavior_is_retired() -> None:
    result = StaticValidator().validate(
        _wrap_in_spl("[COMMAND Use aggregate based on <REF>agg.field</REF> RESULT out: text SET]")
    )
    assert not [
        error
        for error in result.errors
        if error.severity == "warning" and "Invalid variable reference" in error.message
    ]


def test_previous_renderer_comma_join_behavior_is_retired() -> None:
    builder = _ClauseBuilder()
    with pytest.raises(ValueError, match="Composite lowering must have run"):
        builder._result_clause("RESULT", ["a", "b"])
