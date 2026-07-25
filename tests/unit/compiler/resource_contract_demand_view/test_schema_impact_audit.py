"""Phase B0 schema impact audit tests — strengthened.

These tests LOCK DOWN exact counts and locations of ``required`` field
references across the codebase.  When Phase B1 introduces tri-state
requiredness, these tests WILL FAIL — that is intentional.  Each failure
is a checklist item for the B1 migration.

Do NOT update these tests to "pass early" during B1.  Only update them
AFTER the corresponding production change is complete.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).parent.parent.parent.parent.parent / "src" / "nl2spl"


# =============================================================================
# Test 1: IR dataclasses with required: bool
# =============================================================================


_REQUIRED_BOOL_IR_FIELDS = {
    ("ir/resource_contract_ir.py", "ResourceContractDemandIR", "required"),
    ("ir/resource_contract_ir.py", "ResourceContractFieldIR", "required"),
    ("ir/worker_plan_ir.py", "ContractFieldIR", "required"),
    ("ir/worker_ir.py", "WorkerInput", "required"),
    ("ir/worker_ir.py", "WorkerOutput", "required"),
    ("ir/worker_plan_ir.py", "InputBindingIR", "required"),
    ("ir/worker_plan_ir.py", "OutputBindingIR", "required"),
    ("ir/resource_registry_ir.py", "VariableSpec", "required"),
}


def test_ir_required_fields_still_exist() -> None:
    """Verify all 8 IR types that carry required: bool are still present."""
    for rel_path, class_name, field_name in _REQUIRED_BOOL_IR_FIELDS:
        file_path = SRC_ROOT / rel_path
        assert file_path.exists(), f"IR file vanished: {rel_path}"
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        class_found = False
        field_found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                class_found = True
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and hasattr(item.target, "id"):
                        if item.target.id == field_name:  # type: ignore[union-attr]
                            field_found = True
                            break
        assert class_found, f"Class {class_name} not found in {rel_path}"
        assert field_found, f"Field {class_name}.{field_name} not found in {rel_path}"


# =============================================================================
# Test 2: Consumer files — exact list
# =============================================================================


_CONSUMER_FILES_WITH_REQUIRED_ACCESS = [
    "pipeline/stages/stage3_5_worker_boundary_planner/executor.py",
    "pipeline/stages/stage3_5_worker_boundary_planner/materializer.py",
    "pipeline/stages/stage3_5_worker_boundary_planner/prompt_builder.py",
    "pipeline/stages/stage6_resource_extractor/context_builder.py",
    "pipeline/stages/stage6_resource_extractor/worker_scoped.py",
    "pipeline/stages/stage6_resource_extractor/legacy.py",
    "pipeline/stages/stage10_worker_assembler/assembler.py",
    "pipeline/stages/stage10_worker_assembler/child_worker_builder.py",
    "pipeline/stages/stage10_worker_assembler/step_resolver.py",
    "pipeline/stages/stage9_5_normalizer/validation.py",
    "pipeline/stages/stage11_spl_renderer/renderer.py",
    "compiler/irs/checkers/post_normalize.py",
    # producer_index.py is an indirect consumer — it reads ResourceContractBindingIR
    # but does not reference .required directly
    "adapters/structural_nl.py",
    "pipeline/stages/stage2_field_router_prompt.py",
    "ir/resource_contract_ir.py",
    # ir/resource_registry_ir.py — defines required: bool field, no .required access
    # ir/worker_plan_ir.py — defines required: bool field, no .required access
    # ir/worker_ir.py — defines required: bool field, no .required access
]


def test_consumer_files_still_exist() -> None:
    """Verify all consumer files with .required access still exist."""
    # Files that use the 'required=' keyword arg pattern (not .required attr access)
    _KEYWORD_ONLY = {"pipeline/stages/stage10_worker_assembler/child_worker_builder.py"}  # noqa: N806

    for rel_path in _CONSUMER_FILES_WITH_REQUIRED_ACCESS:
        file_path = SRC_ROOT / rel_path
        assert file_path.exists(), f"Consumer file '{rel_path}' not found."
        content = file_path.read_text(encoding="utf-8")
        if rel_path in _KEYWORD_ONLY:
            assert "required" in content, (
                f"Consumer file '{rel_path}' no longer contains 'required'. "
                f"Update _CONSUMER_FILES_WITH_REQUIRED_ACCESS."
            )
        else:
            assert ".required" in content, (
                f"Consumer file '{rel_path}' no longer contains '.required'. "
                f"Update _CONSUMER_FILES_WITH_REQUIRED_ACCESS."
            )


# =============================================================================
# Test 3: Exact .required reference counts (fails when code changes)
# =============================================================================


def test_renderer_required_truthiness_count() -> None:
    """B1: Renderer now uses _required_keyword() helper, 0 truthiness branches."""
    src = (SRC_ROOT / "pipeline/stages/stage11_spl_renderer/renderer.py").read_text("utf-8")
    count = src.count('"REQUIRED" if') + src.count("'REQUIRED' if")
    assert count == 1, f"Renderer REQUIRED branches (in _required_keyword): {count} (expected 1)."


def test_validation_py_required_reference_count() -> None:
    """validation.py has exactly 11 .required references (truthiness on binding.required)."""
    src = (SRC_ROOT / "pipeline/stages/stage9_5_normalizer/validation.py").read_text("utf-8")
    count = src.count(".required")
    assert count == 11, (
        f"validation.py .required count: {count} (expected 11). "
        f"B1: if InputBindingIR/OutputBindingIR.required changes type, audit all 11."
    )


def test_context_builder_required_count() -> None:
    """B4: context_builder has 7 .required refs (added _field_requiredness_label)."""
    src = (SRC_ROOT / "pipeline/stages/stage6_resource_extractor/context_builder.py").read_text("utf-8")
    count = src.count(".required")
    assert count == 7, (
        f"context_builder .required count: {count} (expected 7)."
    )


def test_post_normalize_required_count() -> None:
    """B5r3: post_normalize.py has 3 .required refs (legacy compat + demand_attr)."""
    src = (SRC_ROOT / "compiler/irs/checkers/post_normalize.py").read_text("utf-8")
    count = src.count(".required")
    assert count == 3, (
        f"post_normalize .required count: {count} (expected 3)."
    )


def test_child_worker_builder_worker_io_count() -> None:
    """child_worker_builder.py has exactly 2 WorkerInput/WorkerOutput(required=...) calls."""
    src = (SRC_ROOT / "pipeline/stages/stage10_worker_assembler/child_worker_builder.py").read_text("utf-8")
    w_input = src.count("WorkerInput(")
    w_output = src.count("WorkerOutput(")
    assert w_input == 1, f"child_worker_builder WorkerInput: {w_input} (expected 1)"
    assert w_output == 1, f"child_worker_builder WorkerOutput: {w_output} (expected 1)"


def test_structural_nl_required_count() -> None:
    """structural_nl.py has exactly 3 .required refs (all on line 385 in merge logic)."""
    src = (SRC_ROOT / "adapters/structural_nl.py").read_text("utf-8")
    count = src.count(".required")
    assert count == 3, f"structural_nl .required count: {count} (expected 3)."


def test_stage2_prompt_required_count() -> None:
    """stage2_field_router_prompt.py has exactly 1 .required reference (payload)."""
    src = (SRC_ROOT / "pipeline/stages/stage2_field_router_prompt.py").read_text("utf-8")
    count = src.count(".required")
    assert count == 1, f"stage2_field_router_prompt .required count: {count} (expected 1)."


def test_assembler_required_count() -> None:
    """B1: assembler.py now has 6 `required=` keyword calls (all pass-through)."""
    src = (SRC_ROOT / "pipeline/stages/stage10_worker_assembler/assembler.py").read_text("utf-8")
    kw_count = src.count("required=")
    assert kw_count == 6, f"assembler required= count: {kw_count} (expected 6). B1 pass-through."


# =============================================================================
# Test 4: ResourceContractBindingIR has no required field (current state)
# =============================================================================


def test_resource_contract_binding_has_no_required_field() -> None:
    """ResourceContractBindingIR does not carry 'required'. B1 decision: should it?"""
    src = (SRC_ROOT / "ir/resource_contract_ir.py").read_text("utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ResourceContractBindingIR":
            field_names = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and hasattr(item.target, "id"):
                    field_names.append(item.target.id)  # type: ignore[union-attr]
            assert "required" not in field_names, (
                f"ResourceContractBindingIR unexpectedly has 'required' field: {field_names}."
            )
            return
    pytest.fail("ResourceContractBindingIR class not found")


# =============================================================================
# Test 5: ResourceContractDemandIR importers (locked set)
# =============================================================================


_EXPECTED_IMPORTERS = {
    "ir/__init__.py",
    "ir/resource_contract_ir.py",
    "ir/worker_plan_ir.py",
    "pipeline/stages/stage3_2_resource_contract_planner/planner.py",
    "compiler/irs/checkers/post_normalize.py",
}


def test_resource_contract_demand_ir_importers() -> None:
    """Lock the set of production files that reference ResourceContractDemandIR."""
    actual = set()
    for root, _dirs, files in os.walk(SRC_ROOT):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = Path(root) / fname
            rel = fpath.relative_to(SRC_ROOT).as_posix()
            try:
                content = fpath.read_text(encoding="utf-8")
            except Exception:
                continue
            if "ResourceContractDemandIR" in content:
                actual.add(rel)
    actual_production = {
        f for f in actual if "test" not in f and "resource_contract_demand_view" not in f
    }
    new = actual_production - _EXPECTED_IMPORTERS
    missing = _EXPECTED_IMPORTERS - actual_production
    assert not new, f"New importers: {new}. Update _EXPECTED_IMPORTERS."
    assert not missing, f"Missing importers: {missing}. Update _EXPECTED_IMPORTERS."


# =============================================================================
# Test 6: ContractFieldIR construction sites (locked set)
# =============================================================================


_CONTRACT_FIELD_IR_SITES = [
    "pipeline/stages/stage3_5_worker_boundary_planner/executor.py",
    "pipeline/stages/stage6_resource_extractor/worker_scoped.py",
]


def test_contract_field_ir_construction_sites() -> None:
    """Lock files that construct ContractFieldIR instances."""
    for rel_path in _CONTRACT_FIELD_IR_SITES:
        fpath = SRC_ROOT / rel_path
        assert fpath.exists(), f"Missing: {rel_path}"
        content = fpath.read_text(encoding="utf-8")
        assert "ContractFieldIR" in content, (
            f"{rel_path} no longer references ContractFieldIR. Update audit."
        )


# =============================================================================
# Test 7: Full .required site count (gate against silent additions)
# =============================================================================


def test_total_required_reference_count_in_consumer_files() -> None:
    """Count all .required references across known consumer files.

    This is a regression gate: if new .required usage appears in consumer
    files, this test fails and the B0 audit must be expanded.
    """
    total = 0
    for rel_path in _CONSUMER_FILES_WITH_REQUIRED_ACCESS:
        fpath = SRC_ROOT / rel_path
        content = fpath.read_text(encoding="utf-8")
        total += content.count(".required")
    # B5r3: total .required = 78 (+1 legacy compat in post_normalize).
    assert total == 78, (
        f"Total .required references across {len(_CONSUMER_FILES_WITH_REQUIRED_ACCESS)} "
        f"consumer files: {total}. If this increased, expand the audit. "
        f"If it decreased, B1 has already removed some — update this assertion."
    )
