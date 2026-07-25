from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from nl2spl.config import PipelineConfig

REPO_ROOT = Path(__file__).resolve().parents[4]


def _read_repo_file(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_orchestrator_uses_subsystem_not_concrete_checkers() -> None:
    source = _read_repo_file("src/nl2spl/pipeline/orchestrator.py")

    assert "build_irs_subsystem" in source
    assert "IRSSubsystem" in source
    assert "WorkerDelegationIRSChecker" not in source
    assert "Stage4ExceptionFlowIRSChecker" not in source
    assert "Stage7StepIRSChecker" not in source


@pytest.mark.parametrize(
    "relative_path",
    [
        "src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py",
        "src/nl2spl/pipeline/executable_gate.py",
        "src/nl2spl/compiler/producer_index.py",
    ],
)
def test_renderer_gate_and_producer_index_do_not_import_irs_runtime(
    relative_path: str,
) -> None:
    source = _read_repo_file(relative_path)

    forbidden = [
        "IRSRunner",
        "IRSChecker",
        "DiagnosticProjector",
        "build_irs_subsystem",
        "WorkerDelegationIRSChecker",
        "Stage4ExceptionFlowIRSChecker",
        "Stage7StepIRSChecker",
    ]
    for token in forbidden:
        assert token not in source


def test_pipeline_config_uses_single_irs_runtime_config() -> None:
    fields = {field.name for field in dataclasses.fields(PipelineConfig)}

    assert "irs" in fields
    assert "enable_irs_v6_runner" not in fields
    assert "enable_irs_worker_delegation_check" not in fields
    assert "enable_irs_stage4_exception_flow_check" not in fields
    assert "enable_irs_stage7_step_check" not in fields
    assert "enable_irs_diagnostic_consolidation" not in fields


def test_skill_docs_reference_productized_irs_runtime() -> None:
    skill_paths = [
        ".codex/skills/irs-knowledge/SKILL.md",
        ".agents/skills/irs-knowledge/SKILL.md",
        ".codex/skills/irs-knowledge/reference/module-structure.md",
        ".agents/skills/irs-knowledge/reference/module-structure.md",
        ".codex/skills/irs-knowledge/reference/authority-boundary.md",
        ".agents/skills/irs-knowledge/reference/authority-boundary.md",
        ".codex/skills/irs-knowledge/examples/add-checker.md",
        ".agents/skills/irs-knowledge/examples/add-checker.md",
        ".codex/skills/irs-knowledge/examples/anti-patterns.md",
        ".agents/skills/irs-knowledge/examples/anti-patterns.md",
    ]

    combined = "\n".join(_read_repo_file(path) for path in skill_paths)

    assert "IRSRuntimeConfig" in combined
    assert "IRSSubsystem" in combined
    assert "DiagnosticConsolidator" in combined
    assert "ConstructSatisfactionFeedbackProjector" in combined
    assert "Information Requirements Satisfaction" not in combined
    assert "enable_irs_v6_runner" not in combined
    assert "enable_irs_worker_delegation_check" not in combined
    assert "enable_irs_stage4_exception_flow_check" not in combined
    assert "enable_irs_stage7_step_check" not in combined
    assert "enable_irs_diagnostic_consolidation" not in combined


def test_r10_to_r13_productization_tests_exist() -> None:
    expected = [
        "tests/unit/compiler/irs/test_r10_irs_subsystem_foundation.py",
        "tests/unit/compiler/irs/test_r11_stage_local_runtime_integration.py",
        "tests/unit/test_diagnostic_consolidator.py",
        "tests/unit/compiler/irs/test_r13_construct_satisfaction_feedback.py",
    ]

    for relative_path in expected:
        assert (REPO_ROOT / relative_path).is_file(), relative_path


def test_productization_tests_do_not_use_disabled_markers() -> None:
    test_paths = [
        "tests/unit/compiler/irs/test_r10_irs_subsystem_foundation.py",
        "tests/unit/compiler/irs/test_r11_stage_local_runtime_integration.py",
        "tests/unit/test_diagnostic_consolidator.py",
        "tests/unit/compiler/irs/test_r13_construct_satisfaction_feedback.py",
        "tests/unit/compiler/irs/test_r14_productization_final_audit.py",
    ]

    for relative_path in test_paths:
        source = _read_repo_file(relative_path)
        skip_token = "pytest.mark." + "skip"
        expected_failure_token = "pytest.mark." + "x" + "fail"
        assert skip_token not in source
        assert expected_failure_token not in source
        assert ("@" + skip_token) not in source
        assert ("@" + expected_failure_token) not in source


@pytest.mark.parametrize(
    "relative_path",
    [
        "src/nl2spl/compiler/irs/feedback_projector.py",
        "src/nl2spl/compiler/diagnostic_consolidator.py",
    ],
)
def test_report_and_diagnostic_product_modules_do_not_import_pipeline_or_llm(
    relative_path: str,
) -> None:
    source = _read_repo_file(relative_path)

    assert "nl2spl.pipeline" not in source
    assert "nl2spl.llm" not in source
