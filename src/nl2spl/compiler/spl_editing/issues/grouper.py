"""Producer issue grouping — policy and annotation.

``ProducerIssueGrouper.annotate()`` processes a list of
``CompileDiagnostic`` and annotates producer-adjacent diagnostics with
grouping metadata (``issue_group_id``, repairability, primary/alias role).

No patches, no LLM, no editable-issue extraction — pure grouping policy.
"""

from __future__ import annotations

import re
from collections import defaultdict

from nl2spl.ir.diagnostics import (
    METADATA_KEY_ISSUE_GROUP_ID,
    METADATA_KEY_ISSUE_ROLE,
    METADATA_KEY_PRIMARY_DIAGNOSTIC_ID,
    METADATA_KEY_RELATED_DIAGNOSTIC_IDS,
    METADATA_KEY_REPAIRABILITY,
    CompileDiagnostic,
    IssueRole,
    Repairability,
)

# ---------------------------------------------------------------------------
# Repairability matrix
# ---------------------------------------------------------------------------

# Diagnostic kinds that are producer-adjacent and participate in grouping.
_PRODUCER_DIAGNOSTIC_KINDS: set[str] = {
    "missing_output_producer",
    "unspecified_output_missing_producer",
    "resource_kind_mismatch",
    "missing_resource_contract",
}

# Repairability defaults by diagnostic kind.
_REPAIRABILITY_BY_KIND: dict[str, Repairability] = {
    "missing_output_producer": "editable",
    "unspecified_output_missing_producer": "review_only",
    "resource_kind_mismatch": "non_repairable",
    "missing_resource_contract": "non_repairable",
}

# Producer diagnostic kinds that can serve as the primary editable issue.
_EDITABLE_PRODUCER_KINDS: set[str] = {"missing_output_producer"}


# ---------------------------------------------------------------------------
# Grouper
# ---------------------------------------------------------------------------


class ProducerIssueGrouper:
    """Group producer-adjacent diagnostics by resource name and annotate them.

    Usage::

        grouper = ProducerIssueGrouper()
        grouper.annotate(consolidated_diagnostics)

    After annotation, each producer-adjacent diagnostic's ``metadata``
    dict will contain:

    - ``issue_group_id`` — shared across diagnostics for the same resource
    - ``primary_diagnostic_id`` — the diagnostic_id of the primary issue
    - ``related_diagnostic_ids`` — all diagnostic_ids in this group
    - ``repairability`` — ``"editable"``, ``"review_only"``, or ``"non_repairable"``
    - ``issue_role`` — ``"primary"``, ``"alias"``, or ``"context"``
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def annotate(self, diagnostics: list[CompileDiagnostic]) -> None:
        """Annotate producer-adjacent diagnostics in place.

        Non-producer diagnostics are left untouched.
        """
        producer_diags = [
            d for d in diagnostics if d.kind in _PRODUCER_DIAGNOSTIC_KINDS
        ]
        if not producer_diags:
            return

        # 1. Assign default repairability from the matrix
        for d in producer_diags:
            d.metadata[METADATA_KEY_REPAIRABILITY] = _REPAIRABILITY_BY_KIND.get(
                d.kind, "non_repairable"
            )

        # 2. Group by resource name
        groups = self._group_by_resource(producer_diags)

        # 3. Annotate each group
        group_index = 0
        for resource_name, group_diags in sorted(groups.items()):
            group_id = f"producer_group:{resource_name}"
            group_index += 1

            # Sort for deterministic primary selection:
            #  1. Editable kinds first
            #  2. REQUIRED_OUTPUT preferred over RESOURCE_CONTRACT_DEMAND
            #  3. diagnostic_id for tie-breaking
            def _sort_key(d: CompileDiagnostic) -> tuple[int, int, str]:
                editable_rank = 0 if d.kind in _EDITABLE_PRODUCER_KINDS else 1
                # Prefer REQUIRED_OUTPUT constructs as primary
                irs_ref = d.metadata.get("irs_ref", {})
                ct = irs_ref.get("construct_type", "") if isinstance(irs_ref, dict) else ""
                ct_rank = 0 if ct == "REQUIRED_OUTPUT" else 1
                return (editable_rank, ct_rank, d.diagnostic_id)

            sorted_group = sorted(group_diags, key=_sort_key)

            # Primary is the first item after sorting
            primary = sorted_group[0]

            # Annotate each diagnostic in the group
            for d in sorted_group:
                d.metadata[METADATA_KEY_ISSUE_GROUP_ID] = group_id
                d.metadata[METADATA_KEY_PRIMARY_DIAGNOSTIC_ID] = primary.diagnostic_id
                d.metadata[METADATA_KEY_RELATED_DIAGNOSTIC_IDS] = sorted(
                    [x.diagnostic_id for x in sorted_group]
                )

                # Role assignment
                if d.diagnostic_id == primary.diagnostic_id:
                    d.metadata[METADATA_KEY_ISSUE_ROLE] = "primary"
                elif d.metadata.get(METADATA_KEY_REPAIRABILITY) == "editable":
                    # Another editable diagnostic for the same resource → alias
                    d.metadata[METADATA_KEY_ISSUE_ROLE] = "alias"
                else:
                    # Non-editable → context
                    d.metadata[METADATA_KEY_ISSUE_ROLE] = "context"

    # ------------------------------------------------------------------
    # Resource name extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _group_by_resource(
        diagnostics: list[CompileDiagnostic],
    ) -> dict[str, list[CompileDiagnostic]]:
        """Group diagnostics by the resource/output name they refer to."""
        groups: dict[str, list[CompileDiagnostic]] = defaultdict(list)

        for d in diagnostics:
            resource_name = ProducerIssueGrouper._extract_resource_name(d)
            groups[resource_name].append(d)

        return dict(groups)

    @staticmethod
    def _extract_resource_name(diagnostic: CompileDiagnostic) -> str:
        """Extract the resource/output name from a producer diagnostic.

        Tries multiple strategies in order:
        1. Parse ``target_ref`` for ``output:`` or ``variable:`` suffix.
        2. Parse ``irs_ref.construct_id`` for output suffix.
        3. Extract quoted name from the message text.
        4. Fall back to diagnostic_id (guarantees a unique group per diagnostic).
        """
        # Strategy 1: target_ref parsing
        if diagnostic.target_ref:
            name = ProducerIssueGrouper._name_from_target_ref(
                diagnostic.target_ref
            )
            if name:
                return name

        # Strategy 2: irs_ref.construct_id
        irs_ref = diagnostic.metadata.get("irs_ref")
        if isinstance(irs_ref, dict):
            cid = irs_ref.get("construct_id", "")
            if isinstance(cid, str) and cid:
                name = ProducerIssueGrouper._name_from_construct_id(cid)
                if name:
                    return name

        # Strategy 3: quoted name in message
        msg = diagnostic.message
        if msg:
            name = ProducerIssueGrouper._name_from_message(msg)
            if name:
                return name

        # Strategy 4: fallback — use diagnostic_id to ensure unique group
        return f"unknown:{diagnostic.diagnostic_id}"

    @staticmethod
    def _name_from_target_ref(target_ref: str) -> str | None:
        """Extract resource name from a target_ref like
        ``worker:w_main.output:draft`` or ``variable:draft``.
        """
        # Pattern: worker:{id}.output:{name}
        m = re.search(r"\.output:([^.\s]+)$", target_ref)
        if m:
            return m.group(1)
        # Pattern: variable:{name}
        m = re.search(r"^variable:([^.\s]+)$", target_ref)
        if m:
            return m.group(1)
        # Pattern: resource_contract_demand:{demand_id}
        # For this, we try the message instead.
        return None

    @staticmethod
    def _name_from_construct_id(construct_id: str) -> str | None:
        """Extract resource name from an irs_ref construct_id."""
        # worker:{id}.output:{name}
        m = re.search(r"\.output:([^.\s]+)$", construct_id)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def _name_from_message(message: str) -> str | None:
        """Extract a resource name from a diagnostic message.

        Tries the most specific patterns first:

        1. ``materialized resource(s) name1, name2 but...``
           (the actual resource name from RCD messages).
        2. Quoted name: ``'name'`` or ``"name"``
           (the output name from REQUIRED_OUTPUT messages).
        """
        # Pattern 1: materialized resource name (RCD producer messages)
        m = re.search(
            r"materialized resource\(s\)\s+([\w_]+(?:\s*,\s*[\w_]+)*)\s+but",
            message,
        )
        if m:
            names = [n.strip() for n in m.group(1).split(",")]
            if names:
                return names[0]

        # Pattern 2: quoted name (REQUIRED_OUTPUT, generic)
        m = re.search(r"Required output '([^']+)'", message)
        if m:
            return m.group(1)

        # Pattern 3: any quoted name (fallback)
        m = re.search(r"['\"]([^'\"]+)['\"]", message)
        if m:
            return m.group(1)

        return None


# ---------------------------------------------------------------------------
# Convenience query helpers
# ---------------------------------------------------------------------------


def is_producer_editable(diagnostic: CompileDiagnostic) -> bool:
    """Return True when the diagnostic is a primary editable producer issue."""
    return (
        diagnostic.metadata.get(METADATA_KEY_ISSUE_ROLE) == "primary"
        and diagnostic.metadata.get(METADATA_KEY_REPAIRABILITY) == "editable"
    )


def get_producer_group_id(diagnostic: CompileDiagnostic) -> str | None:
    """Return the issue_group_id for a producer diagnostic, or None."""
    gid = diagnostic.metadata.get(METADATA_KEY_ISSUE_GROUP_ID)
    return gid if isinstance(gid, str) else None
