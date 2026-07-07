# -*- coding: utf-8 -*-
"""
Unit tests for type_field_validator.
"""

from __future__ import annotations

from nl2spl.validator.type_field_validator import (
    DIAGNOSTIC_NOT_STRUCTURED_TYPE,
    DIAGNOSTIC_UNDECLARED_TOP_TIER_VARIABLE,
    DIAGNOSTIC_UNKNOWN_FIELD_IN_STRUCTURED_TYPE,
    extract_type_field_context,
    validate_qualified_ref_field,
)


def test_type_field_validator_named_type() -> None:
    spl_text = (
        "[DEFINE_TYPES:]\n"
        "    RunCompletionRecord = { assumptions_log: text, completion_status: text }\n"
        "[END_TYPES]\n"
        "[DEFINE_VARIABLES:]\n"
        '    "Record" run_completion_record: RunCompletionRecord\n'
        '    "Text" plain_text_var: text\n'
        "[END_VARIABLES]\n"
    )

    context = extract_type_field_context(spl_text)

    # 1. Valid qualified reference
    errors = validate_qualified_ref_field(
        top_name="run_completion_record",
        field_path=("assumptions_log",),
        context=context,
        line=10,
        column=15,
    )
    assert len(errors) == 0

    # 2. Unknown field in structured type
    errors = validate_qualified_ref_field(
        top_name="run_completion_record",
        field_path=("unknown",),
        context=context,
        line=10,
        column=15,
    )
    assert len(errors) == 1
    assert errors[0].diagnostic_code == DIAGNOSTIC_UNKNOWN_FIELD_IN_STRUCTURED_TYPE

    # 3. Undeclared top-tier variable
    errors = validate_qualified_ref_field(
        top_name="unknown_record",
        field_path=("assumptions_log",),
        context=context,
        line=10,
        column=15,
    )
    assert len(errors) == 1
    assert errors[0].diagnostic_code == DIAGNOSTIC_UNDECLARED_TOP_TIER_VARIABLE

    # 4. Not structured type
    errors = validate_qualified_ref_field(
        top_name="plain_text_var",
        field_path=("field",),
        context=context,
        line=10,
        column=15,
    )
    assert len(errors) == 1
    assert errors[0].diagnostic_code == DIAGNOSTIC_NOT_STRUCTURED_TYPE


def test_type_field_validator_inline_type() -> None:
    spl_text = (
        "[DEFINE_VARIABLES:]\n"
        '    "Record" run_record: { assumptions_log: text, completion_status: text }\n'
        "[END_VARIABLES]\n"
    )

    context = extract_type_field_context(spl_text)

    errors = validate_qualified_ref_field(
        top_name="run_record",
        field_path=("assumptions_log",),
        context=context,
        line=5,
        column=10,
    )
    assert len(errors) == 0

    errors = validate_qualified_ref_field(
        top_name="run_record",
        field_path=("unknown",),
        context=context,
        line=5,
        column=10,
    )
    assert len(errors) == 1
    assert errors[0].diagnostic_code == DIAGNOSTIC_UNKNOWN_FIELD_IN_STRUCTURED_TYPE
