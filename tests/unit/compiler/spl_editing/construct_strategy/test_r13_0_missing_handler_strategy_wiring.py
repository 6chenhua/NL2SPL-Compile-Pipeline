"""Unit tests for Phase R13.0 missing_handler strategy shadow wiring."""

from __future__ import annotations

import inspect

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder
from nl2spl.compiler.spl_editing.core.service import SPLEditingService
from nl2spl.compiler.spl_editing.handlers.missing_handler.prompt import (
    MISSING_HANDLER_SYSTEM_PROMPT,
)
from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload
from nl2spl.compiler.spl_editing.presentation.templates.repair_option_copy import (
    option_label_for_entry,
)
from nl2spl.compiler.spl_editing.strategy.defaults import build_default_strategy_registry


def _missing_handler_entry(*, strategy_enabled: bool):
    registry = SPLConstructRegistry.default()
    strategy_registry = build_default_strategy_registry() if strategy_enabled else None
    catalog = RepairCatalogBuilder.from_construct_registry(
        registry,
        strategy_registry=strategy_registry,
    )
    return catalog.find_by_construct_slot_kind(
        "EXCEPTION_FLOW",
        "handler_action",
        "missing_handler",
    )[0]


def test_missing_handler_catalog_entry_has_shadow_strategy_metadata() -> None:
    entry = _missing_handler_entry(strategy_enabled=True)

    assert entry.repair_strategy_id == "exception_flow.complete_handler_action.v1"
    assert entry.preview_required is True
    assert entry.strategy_display_label == "Complete Exception Handler Action"
    assert entry.default_verification_lane == "B"
    assert entry.default_patch_type == "AddExceptionHandlerStep"


def test_missing_handler_presentation_uses_strategy_label_not_patch_type() -> None:
    entry = _missing_handler_entry(strategy_enabled=True)

    label = option_label_for_entry(entry)

    assert label == "Complete Exception Handler Action"
    assert "AddExceptionHandlerStep" not in label


def test_missing_handler_catalog_without_strategy_registry_stays_legacy() -> None:
    entry = _missing_handler_entry(strategy_enabled=False)

    assert entry.repair_strategy_id is None
    assert entry.preview_required is False
    assert not hasattr(SPLEditingService, "preview_repair")
    assert hasattr(SPLEditingService, "apply_preview_result")


def test_missing_handler_prompt_does_not_ask_for_concrete_command_family() -> None:
    forbidden = ("GENERAL_COMMAND", "REQUEST_INPUT", "DISPLAY_MESSAGE")

    for token in forbidden:
        assert token not in MISSING_HANDLER_SYSTEM_PROMPT
    assert "StepIR" not in MISSING_HANDLER_SYSTEM_PROMPT
    assert "BlockIR" not in MISSING_HANDLER_SYSTEM_PROMPT
    assert "handler_goal" in MISSING_HANDLER_SYSTEM_PROMPT


def test_missing_handler_parser_accepts_strategy_level_handler_goal() -> None:
    data = parse_suggestion_payload(
        '{"patch_type":"AddExceptionHandlerStep","title":"Complete handler",'
        '"explanation":"Adds handler intent.",'
        '"payload":{"handler_goal":"Ask the user for source access."}}',
        ("AddExceptionHandlerStep",),
    )

    assert data["payload"]["handler_goal"] == "Ask the user for source access."
    assert "command_type" not in data["payload"]


def test_missing_handler_prompt_module_does_not_import_stage_slices() -> None:
    import nl2spl.compiler.spl_editing.handlers.missing_handler.prompt as prompt_module

    source = inspect.getsource(prompt_module)

    assert "Stage5ExceptionHandlerBlockRepairSlice" not in source
    assert "Stage7ExceptionHandlerCommandRepairSlice" not in source
    assert "stage_slices" not in source
