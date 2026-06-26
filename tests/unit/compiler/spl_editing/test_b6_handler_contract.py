"""B6 handler contract tests: generated suggestions must pass validator."""

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder


def test_missing_output_handler_bind_is_not_user_facing_after_r11() -> None:
    """R11: default missing-output affordance no longer exposes legacy bind."""
    catalog = RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())
    entries = catalog.find_by_construct_slot_kind(
        "REQUIRED_OUTPUT", "producer", "missing_output_producer"
    )
    assert len(entries) == 1
    assert entries[0].supported_patch_types == ("InsertProducerStep",)
