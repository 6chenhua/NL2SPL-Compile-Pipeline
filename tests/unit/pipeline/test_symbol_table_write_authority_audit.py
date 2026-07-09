"""S6V4.5: SymbolTable write-path authority audit tests.

Verify every ``symbol_table.declare()`` / ``declare_scoped()`` call site
is classified in the write-path inventory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nl2spl.pipeline.symbol_table_write_audit import (
    get_inventory,
    get_unclassified_paths,
    get_waivered_paths,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestS6V45WritePathInventory:
    """Verify the static inventory is complete and every entry is classified."""

    def test_all_entries_have_authority_category(self) -> None:
        unclassified = get_unclassified_paths()
        assert not unclassified, (
            f"S6V4.5: {len(unclassified)} unclassified write paths: "
            f"{[e.call_site for e in unclassified]}"
        )

    def test_all_entries_have_guard_or_waiver(self) -> None:
        for entry in get_inventory():
            has_guard = bool(entry.guard_function_or_metadata.strip())
            has_waiver = bool(entry.waiver_if_any.strip())
            assert has_guard or has_waiver, (
                f"S6V4.5: entry {entry.call_site} has no guard and no waiver."
            )

    def test_all_entries_have_tests(self) -> None:
        for entry in get_inventory():
            assert entry.tests.strip(), (
                f"S6V4.5: entry {entry.call_site} has no test references."
            )

    def test_waivered_entries_have_owner_and_reason(self) -> None:
        for entry in get_waivered_paths():
            assert "owner" in entry.waiver_if_any.lower() or "Owner" in entry.waiver_if_any, (
                f"S6V4.5: waiver for {entry.call_site} must name an owner."
            )
            assert "reason" in entry.waiver_if_any.lower() or "removal" in entry.waiver_if_any.lower(), (
                f"S6V4.5: waiver for {entry.call_site} must state reason/removal."
            )

    def test_real_static_scan_matches_inventory(self) -> None:
        """Real static scan: every declare/declare_scoped call site in
        production code MUST appear in the inventory.  And every inventory
        entry MUST correspond to a real call site.

        If this test fails because a new call site was added, BOTH the
        inventory AND this test must be updated — never remove the test.
        """
        src_dir = REPO_ROOT / "src" / "nl2spl"
        if not src_dir.exists():
            pytest.skip("Source directory not found")

        # Scan all production .py files for declare/declare_scoped calls
        scan_hits: set[str] = set()
        for py_file in src_dir.rglob("*.py"):
            # Skip tests, __pycache__, and the audit module itself
            path_str = str(py_file)
            if "tests" in path_str or "__pycache__" in path_str:
                continue
            if "symbol_table_write_audit" in path_str:
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except Exception:
                continue
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue
                if ".declare(" in stripped or ".declare_scoped(" in stripped:
                    rel = str(py_file.relative_to(REPO_ROOT)).replace("\\", "/")
                    scan_hits.add(rel)
                    break  # one hit per file is enough

        # Build inventory file set
        inventory_files: set[str] = set()
        for entry in get_inventory():
            # Extract the file path from the call_site (before " ~")
            file_part = entry.call_site.split(" ~")[0].split(":")[0]
            inventory_files.add(file_part)

        # Assert set equality
        in_scan_not_inventory = scan_hits - inventory_files
        in_inventory_not_scan = inventory_files - scan_hits

        assert not in_scan_not_inventory, (
            f"Fix4: {len(in_scan_not_inventory)} file(s) found in static scan "
            f"but NOT in inventory.  Every declare/declare_scoped call site "
            f"must be classified: {sorted(in_scan_not_inventory)}"
        )
        assert not in_inventory_not_scan, (
            f"Fix4: {len(in_inventory_not_scan)} file(s) in inventory but NOT "
            f"found in static scan.  Inventory may have stale entries: "
            f"{sorted(in_inventory_not_scan)}"
        )

    def test_all_stage6_paths_have_policy_guard(self) -> None:
        """Stage 6 write paths must reference Stage6VariableDeclarationPolicy."""
        stage6_entries = [e for e in get_inventory() if "Stage 6" in e.stage]
        for entry in stage6_entries:
            assert "policy" in entry.guard_function_or_metadata.lower(), (
                f"S6V4.5: Stage 6 entry {entry.call_site} must use "
                f"Stage6VariableDeclarationPolicy as guard."
            )
