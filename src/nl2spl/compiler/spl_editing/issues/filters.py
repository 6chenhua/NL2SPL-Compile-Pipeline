"""Issue filter predicates.

Each filter is a pure function: ``(CompileDiagnostic, RepairCatalog) -> bool``.
The extractor composes them to decide which diagnostics become editable issues.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalog
from nl2spl.ir.diagnostics import CompileDiagnostic

# ---------------------------------------------------------------------------
# Accepted authorities — diagnostics from these sources are eligible
# ---------------------------------------------------------------------------

_ACCEPTED_AUTHORITIES: frozenset[str] = frozenset({
    "post_normalize_irs",
    "producer_index",
    "producer_index_backed_irs",
    "selected_promoted_stage_local_irs",
})

# Diagnostic kinds that are NEVER editable (compiler health signals).
_EXCLUDED_KINDS: frozenset[str] = frozenset({
    "route_refinement_corrected",
    "missing_provenance",
    "assumed_command_not_renderable",
})


def has_irs_ref(diagnostic: CompileDiagnostic) -> bool:
    """True when the diagnostic carries ``metadata["irs_ref"]``."""
    irs_ref = diagnostic.metadata.get("irs_ref")
    return isinstance(irs_ref, dict) and bool(irs_ref.get("construct_type"))


def authority_is_accepted(diagnostic: CompileDiagnostic) -> bool:
    """True when the diagnostic's authority is in the accepted set."""
    authority = diagnostic.metadata.get("authority")
    return isinstance(authority, str) and authority in _ACCEPTED_AUTHORITIES


def kind_is_not_excluded(diagnostic: CompileDiagnostic) -> bool:
    """True when the diagnostic kind is NOT an excluded compiler signal."""
    return diagnostic.kind not in _EXCLUDED_KINDS


def has_repair_affordance(
    diagnostic: CompileDiagnostic, catalog: RepairCatalog,
) -> bool:
    """True when the catalog has at least one entry for this diagnostic."""
    irs_ref = diagnostic.metadata.get("irs_ref")
    if not isinstance(irs_ref, dict):
        return False
    ct = irs_ref.get("construct_type")
    sn = irs_ref.get("slot_name")
    if not isinstance(ct, str) or not isinstance(sn, str):
        return False
    entries = catalog.find_by_construct_slot_kind(ct, sn, diagnostic.kind)
    return len(entries) > 0


def is_editable(diagnostic: CompileDiagnostic) -> bool:
    """True when repairability is 'editable'.

    Diagnostics without an explicit ``repairability`` key that have
    a catalog entry are treated as editable (they are IRS-backed,
    user-actionable diagnostics from authorities like post_normalize).
    """
    val = diagnostic.metadata.get("repairability")
    if val is None:
        # Ungrouped IRS-backed diagnostic with catalog entry → editable
        return True
    return val == "editable"


def is_primary_issue(diagnostic: CompileDiagnostic) -> bool:
    """True when issue_role is 'primary'.

    Diagnostics without an ``issue_role`` key are treated as primary
    (ungrouped diagnostics have no alias/context peers and are the
    sole owner of their diagnostic).
    """
    val = diagnostic.metadata.get("issue_role")
    if val is None:
        return True
    return val == "primary"


# ---------------------------------------------------------------------------
# Catalog entry gating
# ---------------------------------------------------------------------------


def catalog_entry_is_user_facing(
    diagnostic: CompileDiagnostic, catalog: RepairCatalog,
) -> bool:
    """True when at least one matching catalog entry has ``user_facing=True``
    and non-None ``handler_id``, ``context_id``, ``target_resolver_id``.
    """
    irs_ref = diagnostic.metadata.get("irs_ref")
    if not isinstance(irs_ref, dict):
        return False
    ct = irs_ref.get("construct_type", "")
    sn = irs_ref.get("slot_name", "")
    entries = catalog.find_by_construct_slot_kind(ct, sn, diagnostic.kind)
    if not entries:
        return False
    return any(
        e.user_facing
        and e.handler_id is not None
        and e.context_id is not None
        and e.target_resolver_id is not None
        for e in entries
    )
