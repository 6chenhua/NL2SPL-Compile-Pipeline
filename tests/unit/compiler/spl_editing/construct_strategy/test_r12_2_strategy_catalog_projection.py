"""Unit tests for Phase R12.2 RepairStrategy Registry and Catalog Integration."""

from __future__ import annotations

import ast
import pathlib
import sys
import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry, RepairAffordanceSpec
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder, RepairCatalogEntry
from nl2spl.compiler.spl_editing.presentation.templates.repair_option_copy import option_label_for_entry
from nl2spl.compiler.spl_editing.strategy import RepairStrategySpec, RepairStrategyRegistry
from nl2spl.compiler.spl_editing.strategy.defaults import (
    build_default_strategy_registry,
    iter_default_strategy_specs,
)
from nl2spl.compiler.spl_editing.strategy.errors import DuplicateStrategyError


def test_defaults_registry_populates_three_strategies() -> None:
    """Verify defaults.py builds the registry with exactly the three expected MVP strategies."""
    specs = list(iter_default_strategy_specs())
    assert len(specs) == 3

    strategy_ids = {spec.strategy_id for spec in specs}
    expected_ids = {
        "exception_flow.complete_handler_action.v1",
        "required_output.materialize_producer.v1",
        "worker_delegation.complete_closure.v1",
    }
    assert strategy_ids == expected_ids

    registry = build_default_strategy_registry()
    for sid in expected_ids:
        assert registry.get(sid) is not None


def test_duplicate_strategy_registration_raises() -> None:
    """Verify duplicate strategy registration raises DuplicateStrategyError."""
    registry = build_default_strategy_registry()
    specs = list(iter_default_strategy_specs())
    with pytest.raises(DuplicateStrategyError):
        registry.register(specs[0])


def test_catalog_entry_without_strategy_is_legacy() -> None:
    """Verify catalog entries default correctly when no strategy registry is passed."""
    registry = SPLConstructRegistry.default()
    catalog = RepairCatalogBuilder.from_construct_registry(registry)

    entries = catalog.find_by_construct_slot_kind(
        "EXCEPTION_FLOW",
        "handler_action",
        "missing_handler",
    )
    assert len(entries) == 1
    entry = entries[0]
    # Under legacy mode, strategy display metadata is None/False
    assert entry.repair_strategy_id is None
    assert entry.strategy_display_label is None
    assert entry.closure_summary is None
    assert entry.preview_required is False


def test_catalog_builder_with_empty_strategy_registry_safe_miss() -> None:
    """Verify that passing an empty strategy registry to the catalog builder succeeds and all strategy metadata defaults to None/False."""
    registry = SPLConstructRegistry.default()
    empty_strategy_reg = RepairStrategyRegistry()
    catalog = RepairCatalogBuilder.from_construct_registry(registry, strategy_registry=empty_strategy_reg)

    entries = catalog.find_by_construct_slot_kind(
        "EXCEPTION_FLOW",
        "handler_action",
        "missing_handler",
    )
    assert len(entries) == 1
    entry = entries[0]
    assert entry.repair_strategy_id is None
    assert entry.strategy_display_label is None
    assert entry.closure_summary is None
    assert entry.preview_required is False


def test_catalog_projection_helper_safe_miss() -> None:
    """Verify that catalog_projection.project_strategy_metadata behaves correctly on mismatch and None inputs."""
    from nl2spl.compiler.spl_editing.strategy.catalog_projection import project_strategy_metadata
    empty_strategy_reg = RepairStrategyRegistry()
    
    # 1. Non-existent strategy
    proj = project_strategy_metadata("non_existent_strategy_id", empty_strategy_reg)
    assert proj["repair_strategy_id"] is None
    assert proj["strategy_display_label"] is None
    assert proj["closure_summary"] is None
    assert proj["preview_required"] is False

    # 2. None strategy_id
    proj2 = project_strategy_metadata(None, empty_strategy_reg)
    assert proj2["repair_strategy_id"] is None
    assert proj2["strategy_display_label"] is None
    assert proj2["closure_summary"] is None
    assert proj2["preview_required"] is False


def test_catalog_entry_with_strategy_enriches_metadata() -> None:
    """Verify catalog builder enriches entries when strategy registry is provided."""
    registry = SPLConstructRegistry.default()
    strategy_reg = build_default_strategy_registry()
    catalog = RepairCatalogBuilder.from_construct_registry(registry, strategy_registry=strategy_reg)

    entries = catalog.find_by_construct_slot_kind(
        "EXCEPTION_FLOW",
        "handler_action",
        "missing_handler",
    )
    assert len(entries) == 1
    entry = entries[0]
    assert entry.repair_strategy_id == "exception_flow.complete_handler_action.v1"
    assert entry.strategy_display_label == "Complete Exception Handler Action"
    assert entry.closure_summary == "Ensure handler block and materialize handler command"
    assert entry.preview_required is True


def test_presentation_uses_strategy_label_not_patch_type() -> None:
    """Verify option_label_for_entry uses strategy label rather than leaking patch type names when strategy id exists."""
    entry = RepairCatalogEntry(
        entry_id="e1",
        affordance_id="exception_flow.add_handler_step",
        construct_type="EXCEPTION_FLOW",
        slot_name="handler_action",
        diagnostic_kind="missing_handler",
        repair_strategy_id="exception_flow.complete_handler_action.v1",
        strategy_display_label="Complete Exception Handler Action",
        supported_patch_types=("AddExceptionHandlerStep",),
    )
    label = option_label_for_entry(entry)
    assert label == "Complete Exception Handler Action"
    assert "AddExceptionHandlerStep" not in label


def test_presentation_falls_back_to_patch_label_for_legacy() -> None:
    """Verify option_label_for_entry falls back to patch-type label for legacy entry (no repair_strategy_id)."""
    entry = RepairCatalogEntry(
        entry_id="e1",
        affordance_id="exception_flow.add_handler_step",
        construct_type="EXCEPTION_FLOW",
        slot_name="handler_action",
        diagnostic_kind="missing_handler",
        repair_strategy_id=None,
        supported_patch_types=("AddExceptionHandlerStep",),
    )
    label = option_label_for_entry(entry)
    assert label == "Add handler step"


def test_worker_promotion_slots_preserve_own_names_under_shared_strategy() -> None:
    """Verify catalog entries preserve their own slot_name while sharing the same strategy id.

    The strategy spec target slot is 'promotion_input_contract', but other slots like
    'promotion_output_contract' sharing 'worker_delegation.complete_closure.v1' must
    preserve their individual slot names in the derived catalog.
    """
    registry = SPLConstructRegistry.default()
    strategy_reg = build_default_strategy_registry()
    catalog = RepairCatalogBuilder.from_construct_registry(registry, strategy_registry=strategy_reg)

    # WORKER_PROMOTION slots should each produce an entry
    slots = [
        "promotion_input_contract",
        "promotion_output_contract",
        "promotion_invocation_point",
        "promotion_result_handoff",
    ]
    for slot_name in slots:
        entries = catalog.find_by_construct_slot_kind(
            "WORKER_PROMOTION",
            slot_name,
            "type_or_contract_ambiguity",
        )
        assert len(entries) == 1
        entry = entries[0]
        assert entry.repair_strategy_id == "worker_delegation.complete_closure.v1"
        assert entry.slot_name == slot_name  # Preserved!
        assert entry.strategy_display_label == "Complete Worker Delegation Handoff Contract"


def test_catalog_does_not_import_stage_slices_handlers_or_llm() -> None:
    """Enforce import isolation: verify strategy/defaults and catalog do not import runtime modules."""
    forbidden_modules = {
        "nl2spl.compiler.spl_editing.patches",
        "nl2spl.compiler.spl_editing.handlers",
        "nl2spl.compiler.spl_editing.cli",
        "nl2spl.compiler.spl_editing.core.service",
    }
    for mod in list(sys.modules.keys()):
        if mod.startswith("nl2spl.compiler.spl_editing.strategy") or \
           mod.startswith("nl2spl.compiler.spl_editing.core.catalog"):
            module_obj = sys.modules[mod]
            module_vars = vars(module_obj)
            for var_name, var_val in module_vars.items():
                if hasattr(var_val, "__name__"):
                    mod_name = var_val.__name__
                    assert not any(mod_name.startswith(f) for f in forbidden_modules), (
                        f"Module '{mod}' imports forbidden runtime entity '{mod_name}'"
                    )
