"""Advanced developer-only presentation details."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IssueAdvancedDetails:
    primary_diagnostic_id: str
    related_diagnostic_ids: tuple[str, ...] = ()
    diagnostic_kind: str = ""
    target_ref: str = ""
    irs_construct_type: str = ""
    irs_construct_id: str = ""
    irs_slot_name: str = ""
    authority: str = ""
    repairability_metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RunAdvancedDetails:
    snapshot_path: str = ""
    base_snapshot_id: str = ""
    parent_snapshot_id: str | None = None
    compile_run_id: str = ""


__all__ = ["IssueAdvancedDetails", "RunAdvancedDetails"]
