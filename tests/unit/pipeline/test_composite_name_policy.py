"""
Unit tests for CompositeNamePolicy.
"""

from __future__ import annotations

from nl2spl.pipeline.stages.stage9_5_normalizer.composite_name_policy import (
    DIAGNOSTIC_COMPOSITE_NAME_POLICY_VIOLATION,
    CompositeNamePolicy,
)


def test_composite_name_policy_variable_names() -> None:
    policy = CompositeNamePolicy()

    # Accepted
    assert policy.validate_variable_name("assumptions_log_completion_status").accepted
    assert policy.validate_variable_name("run_completion_record").accepted

    # Rejected patterns
    r1 = policy.validate_variable_name("main_st_7_result_structured")
    assert not r1.accepted
    assert r1.diagnostic_code == DIAGNOSTIC_COMPOSITE_NAME_POLICY_VIOLATION

    assert not policy.validate_variable_name("result_1").accepted
    assert not policy.validate_variable_name("tmp_1").accepted
    assert not policy.validate_variable_name("var_abcd1234").accepted
    assert not policy.validate_variable_name("a_b").accepted  # Segments too short
    assert not policy.validate_variable_name("worker_main_st_7_result").accepted
    assert not policy.validate_variable_name("assumptions_log_completion_status_type").accepted


def test_composite_name_policy_type_names() -> None:
    policy = CompositeNamePolicy()

    # Accepted (CamelCase of valid variable names)
    assert policy.validate_type_name("RunCompletionRecord").accepted
    assert policy.validate_type_name("AssumptionsLogCompletionStatus").accepted

    # Rejected patterns
    assert not policy.validate_type_name("RunCompletionRecordType").accepted
    assert not policy.validate_type_name("RunCompletionRecordStructuredType").accepted
    assert not policy.validate_type_name("RunCompletionRecordStructured").accepted
    assert not policy.validate_type_name("St7Result").accepted
