"""EditableIssueExtractor — compile diagnostics → editable issues.

Filters ``CompileDiagnostic`` through authority, irs_ref, and
``RepairCatalog`` checks, applies R4/R5 grouping metadata, and emits
one ``EditableIssue`` per primary diagnostic.
"""

from __future__ import annotations

from collections import defaultdict

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalog
from nl2spl.compiler.spl_editing.core.model import EditableIssue
from nl2spl.compiler.spl_editing.issues import filters as _f
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef


class EditableIssueExtractor:
    """Extract user-actionable editable issues from compile diagnostics.

    Usage::

        catalog = RepairCatalogBuilder.from_construct_registry(registry)
        extractor = EditableIssueExtractor(catalog)
        issues = extractor.extract(compile_diagnostics)
    """

    def __init__(self, catalog: RepairCatalog) -> None:
        self._catalog = catalog

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        diagnostics: list[CompileDiagnostic],
    ) -> tuple[EditableIssue, ...]:
        """Return editable issues for user-facing display.

        Only diagnostics that pass all filters and are the primary in
        their issue group become ``EditableIssue`` entries.  Alias /
        context diagnostics are not emitted as separate issues.
        """
        # 1. Filter to candidate diagnostics
        candidates = [
            d for d in diagnostics
            if _f.has_irs_ref(d)
            and _f.authority_is_accepted(d)
            and _f.kind_is_not_excluded(d)
            and _f.has_repair_affordance(d, self._catalog)
            and _f.catalog_entry_is_user_facing(d, self._catalog)
            and _f.is_editable(d)
        ]

        if not candidates:
            return ()

        # 2. Group by issue_group_id; ungrouped diagnostics each get
        #    their own single-item group
        groups: dict[str, list[CompileDiagnostic]] = defaultdict(list)
        ungrouped: list[CompileDiagnostic] = []
        for d in candidates:
            gid = d.metadata.get("issue_group_id")
            if isinstance(gid, str) and gid:
                groups[gid].append(d)
            else:
                ungrouped.append(d)

        issues: list[EditableIssue] = []

        # 3. Emit one issue per primary in each group
        for group in groups.values():
            issue = self._build_issue(group)
            if issue is not None:
                issues.append(issue)

        # 4. Ungrouped diagnostics — each is its own primary
        for d in ungrouped:
            if _f.is_primary_issue(d):
                issue = self._build_issue([d])
                if issue is not None:
                    issues.append(issue)

        return tuple(sorted(issues, key=lambda i: i.issue_id))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_issue(
        self,
        group: list[CompileDiagnostic],
    ) -> EditableIssue | None:
        """Build an EditableIssue from a group of diagnostics.

        The primary diagnostic is the one with ``issue_role == "primary"``.
        Groups without exactly one primary are skipped — no fallback.
        """
        # Find primary — must be exactly one; skip malformed groups
        primaries = [d for d in group if _f.is_primary_issue(d)]
        if len(primaries) != 1:
            return None
        primary = primaries[0]

        # Collect affordance IDs from all group members
        affordance_ids: list[str] = []
        for d in group:
            entries = self._lookup_entries(d)
            for e in entries:
                if e.affordance_id not in affordance_ids:
                    affordance_ids.append(e.affordance_id)

        irs_ref_dict = primary.metadata.get("irs_ref", {})
        irs_ref = DiagnosticIRSRef.from_dict(irs_ref_dict) if irs_ref_dict else None
        if irs_ref is None:
            return None

        missing_slot_name = None
        ms = primary.missing_slot
        if ms is not None:
            missing_slot_name = ms.slot_name

        return EditableIssue(
            issue_id=primary.diagnostic_id,
            primary_diagnostic_id=primary.diagnostic_id,
            related_diagnostic_ids=tuple(
                sorted({d.diagnostic_id for d in group})
            ),
            issue_group_id=primary.metadata.get("issue_group_id"),
            kind=primary.kind,
            target_ref=primary.target_ref or primary.diagnostic_id,
            irs_ref=irs_ref,
            missing_slot=missing_slot_name,
            source_span_ids=tuple(sorted(primary.source_span_ids)),
            message=primary.message,
            suggested_resolution=primary.suggested_resolution,
            blocks_rendering=primary.blocks_rendering,
            blocks_completion=primary.blocks_completion,
            authority=primary.metadata.get("authority", "post_normalize_irs"),
            affordance_ids=tuple(affordance_ids),
            default_affordance_id=affordance_ids[0] if affordance_ids else None,
            repairable=True,
            repairability="editable",
        )

    def _lookup_entries(self, diagnostic: CompileDiagnostic):
        irs_ref = diagnostic.metadata.get("irs_ref")
        if not isinstance(irs_ref, dict):
            return ()
        ct = irs_ref.get("construct_type", "")
        sn = irs_ref.get("slot_name", "")
        return self._catalog.find_by_construct_slot_kind(ct, sn, diagnostic.kind)
