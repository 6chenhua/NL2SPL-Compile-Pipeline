"""Worker/delegation diagnostic promotion for SPL Editing.

``WorkerDelegationPromoter.annotate()`` processes a pre-filtered list of
selected promoted worker/delegation diagnostics and annotates them with
editable-issue metadata:

- Authority updated to ``"selected_promoted_stage_local_irs"``.
- ``WORKER_PROMOTION`` multi-slot diagnostics grouped by candidate.
- ``repairability``, ``issue_group_id``, primary/alias roles set.
- ``delegation_intent`` preserved as ``original_semantic_role`` metadata
  — never as a construct target or repair target.

No patches, no LLM, no apply.
"""

from __future__ import annotations

from collections import defaultdict

from nl2spl.ir.diagnostics import (
    METADATA_KEY_AUTHORITY,
    METADATA_KEY_ISSUE_GROUP_ID,
    METADATA_KEY_ISSUE_ROLE,
    METADATA_KEY_PRIMARY_DIAGNOSTIC_ID,
    METADATA_KEY_RELATED_DIAGNOSTIC_IDS,
    METADATA_KEY_REPAIRABILITY,
    CompileDiagnostic,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROMOTED_AUTHORITY = "selected_promoted_stage_local_irs"

# WORKER_PROMOTION slots in canonical order (first = default primary).
_WORKER_PROMOTION_SLOT_ORDER: tuple[str, ...] = (
    "promotion_input_contract",
    "promotion_output_contract",
    "promotion_invocation_point",
    "promotion_result_handoff",
)

# Construct types eligible for SPL Editing exposure.
_PROMOTABLE_CONSTRUCT_TYPES: set[str] = {
    "WORKER_PROMOTION",
    "WORKER_HANDOFF",
    "CHILD_WORKER",
    "INVOKE_WORKER",
}


# ---------------------------------------------------------------------------
# Promoter
# ---------------------------------------------------------------------------


class WorkerDelegationPromoter:
    """Annotate selected promoted worker/delegation diagnostics.

    Usage::

        promoter = WorkerDelegationPromoter()
        annotated = promoter.annotate(pre_filtered_promoted_diagnostics)

    The input list must already be pre-filtered to only contain
    user-actionable, delegation-sourced diagnostics.  This promoter
    does NOT decide *which* diagnostics to promote — it annotates
    the ones that were already selected.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def annotate(
        self,
        promoted_diagnostics: list[CompileDiagnostic],
    ) -> list[CompileDiagnostic]:
        """Annotate promoted diagnostics in place and return them.

        Args:
            promoted_diagnostics: Pre-filtered list of stage-local
                diagnostics selected for promotion (e.g. by the
                orchestrator's ``_promoted_irs_diagnostics``).

        Returns:
            The same list with metadata updated in place.
        """
        if not promoted_diagnostics:
            return promoted_diagnostics

        # 1. Update authority on every promoted diagnostic
        for d in promoted_diagnostics:
            d.metadata[METADATA_KEY_AUTHORITY] = PROMOTED_AUTHORITY
            irs_ref = d.metadata.get("irs_ref")
            if isinstance(irs_ref, dict):
                irs_ref["source_authority"] = PROMOTED_AUTHORITY

        # 2. Group WORKER_PROMOTION diagnostics by candidate
        promotion_groups = self._group_promotions(promoted_diagnostics)
        grouped_ids: set[str] = set()
        for group in promotion_groups.values():
            for d in group:
                grouped_ids.add(d.diagnostic_id)

        # 3. Annotate WORKER_PROMOTION groups
        for candidate_key, group in promotion_groups.items():
            self._annotate_promotion_group(candidate_key, group)

        # 4. Annotate non-promotion diagnostics individually
        for d in promoted_diagnostics:
            if d.diagnostic_id in grouped_ids:
                continue
            self._annotate_single(d)

        return promoted_diagnostics

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------

    @staticmethod
    def _group_promotions(
        diagnostics: list[CompileDiagnostic],
    ) -> dict[str, list[CompileDiagnostic]]:
        """Group WORKER_PROMOTION diagnostics by candidate.

        The candidate key is the ``target_ref`` prefix up to the
        last colon (the candidate_id).  For example::

            worker_promotion:cand_1 → key="worker_promotion:cand_1"
            worker_promotion:del_s1  → key="worker_promotion:del_s1"
        """
        groups: dict[str, list[CompileDiagnostic]] = defaultdict(list)

        for d in diagnostics:
            if not WorkerDelegationPromoter._is_promotion_diag(d):
                continue
            key = WorkerDelegationPromoter._promotion_candidate_key(d)
            groups[key].append(d)

        return dict(groups)

    @staticmethod
    def _is_promotion_diag(d: CompileDiagnostic) -> bool:
        """True when the diagnostic comes from a WORKER_PROMOTION construct."""
        irs_ref = d.metadata.get("irs_ref")
        if isinstance(irs_ref, dict):
            return irs_ref.get("construct_type") == "WORKER_PROMOTION"
        # Fallback: check target_ref prefix
        return d.target_ref is not None and d.target_ref.startswith("worker_promotion:")

    @staticmethod
    def _promotion_candidate_key(d: CompileDiagnostic) -> str:
        """Extract the candidate key from a promotion diagnostic.

        The target_ref format is ``worker_promotion:{candidate_id}``.
        Everything up to the trailing slot suffix is the candidate key.
        """
        target = d.target_ref or ""
        # target_ref is just "worker_promotion:{candidate_id}"
        # No slot suffix in current target_ref format, so use as-is
        return target

    # ------------------------------------------------------------------
    # Annotation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _annotate_promotion_group(
        candidate_key: str,
        group: list[CompileDiagnostic],
    ) -> None:
        """Annotate a group of WORKER_PROMOTION diagnostics for one candidate.

        The group is sorted by canonical slot order.  The first slot
        in that order is the primary; the rest are aliases.  All are
        ``editable``.
        """

        # Sort by canonical slot order
        def _slot_order(d: CompileDiagnostic) -> int:
            slot_name = ""
            missing_slot = d.missing_slot
            if missing_slot is not None:
                slot_name = missing_slot.slot_name
            return (
                _WORKER_PROMOTION_SLOT_ORDER.index(slot_name)
                if slot_name in _WORKER_PROMOTION_SLOT_ORDER
                else 99
            )

        sorted_group = sorted(group, key=_slot_order)
        primary = sorted_group[0]

        group_id = f"worker_promotion_group:{candidate_key}"
        all_ids = sorted([d.diagnostic_id for d in sorted_group])

        for d in sorted_group:
            d.metadata[METADATA_KEY_ISSUE_GROUP_ID] = group_id
            d.metadata[METADATA_KEY_PRIMARY_DIAGNOSTIC_ID] = primary.diagnostic_id
            d.metadata[METADATA_KEY_RELATED_DIAGNOSTIC_IDS] = list(all_ids)
            d.metadata[METADATA_KEY_REPAIRABILITY] = "editable"
            d.metadata[METADATA_KEY_ISSUE_ROLE] = (
                "primary" if d.diagnostic_id == primary.diagnostic_id else "alias"
            )

    @staticmethod
    def _annotate_single(d: CompileDiagnostic) -> None:
        """Annotate a single non-promotion diagnostic as an editable issue."""
        d.metadata[METADATA_KEY_REPAIRABILITY] = "editable"
        d.metadata[METADATA_KEY_ISSUE_ROLE] = "primary"
        d.metadata[METADATA_KEY_PRIMARY_DIAGNOSTIC_ID] = d.diagnostic_id
        d.metadata[METADATA_KEY_RELATED_DIAGNOSTIC_IDS] = [d.diagnostic_id]

        # Individual issue group based on target_ref
        target = d.target_ref or d.diagnostic_id
        d.metadata[METADATA_KEY_ISSUE_GROUP_ID] = f"worker_delegation_group:{target}"


# ---------------------------------------------------------------------------
# Convenience query helpers
# ---------------------------------------------------------------------------


def is_worker_delegation_editable(diagnostic: CompileDiagnostic) -> bool:
    """Return True when the diagnostic is a primary editable
    worker/delegation issue.
    """
    return (
        diagnostic.metadata.get(METADATA_KEY_AUTHORITY) == PROMOTED_AUTHORITY
        and diagnostic.metadata.get(METADATA_KEY_ISSUE_ROLE) == "primary"
        and diagnostic.metadata.get(METADATA_KEY_REPAIRABILITY) == "editable"
    )


def has_delegation_provenance(diagnostic: CompileDiagnostic) -> bool:
    """Return True when the diagnostic carries delegation_intent provenance."""
    return diagnostic.metadata.get("original_semantic_role") == "delegation_intent"
