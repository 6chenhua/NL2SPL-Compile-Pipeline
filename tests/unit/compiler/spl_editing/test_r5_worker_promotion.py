"""R5 Worker/Delegation Exposure Policy: post-implementation tests.

Verifies that after R5 changes:
  1. Authority updated to "selected_promoted_stage_local_irs"
  2. irs_ref.source_authority also updated
  3. WORKER_PROMOTION multi-slot grouped by candidate, primary stable
  4. Single-diagnostic promotions get primary role
  5. delegation_intent preserved as metadata, never as target
  6. Catalog lookup works via promoted diagnostic's irs_ref + kind
  7. Non-selected diagnostics not affected
  8. Empty list handling
"""

from __future__ import annotations

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder
from nl2spl.compiler.spl_editing.issues.promoter import (
    PROMOTED_AUTHORITY,
    WorkerDelegationPromoter,
    has_delegation_provenance,
    is_worker_delegation_editable,
)
from nl2spl.ir.diagnostics import (
    METADATA_KEY_AUTHORITY,
    METADATA_KEY_ISSUE_GROUP_ID,
    METADATA_KEY_PRIMARY_DIAGNOSTIC_ID,
    METADATA_KEY_ISSUE_ROLE,
    METADATA_KEY_RELATED_DIAGNOSTIC_IDS,
    METADATA_KEY_REPAIRABILITY,
    CompileDiagnostic,
    DiagnosticIRSRef,
)
from nl2spl.compiler.construct_registry import SPLConstructRegistry


# ===========================================================================
# Helpers
# ===========================================================================


def _promo_diag(
    diagnostic_id: str,
    candidate_id: str = "cand_1",
    slot_name: str = "promotion_input_contract",
    *,
    source_span_ids: list[str] | None = None,
    irs_ref_authority: str = "stage_local_irs",
    original_semantic_role: str = "delegation_intent",
) -> CompileDiagnostic:
    """Create a WORKER_PROMOTION diagnostic as produced by IRS runner.

    Mimics the shape produced by DiagnosticProjector from
    WorkerDelegationIRSChecker _check_worker_promotion.
    """
    target_ref = f"worker_promotion:{candidate_id}"
    d = CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind="type_or_contract_ambiguity",
        severity="warning",
        message=(
            f"Missing clear input contract "
            f"[construct={target_ref}, slot={slot_name}]"
        ),
        target_ref=target_ref,
        source_span_ids=list(source_span_ids or ["s1"]),
        missing_slot=MissingSlot(
            slot_name=slot_name,
            required_for="complete",
            reason=f"missing {slot_name}",
            source_span_ids=list(source_span_ids or ["s1"]),
        ),
        blocks_rendering=False,
        blocks_completion=True,
    )
    d.metadata["irs_ref"] = {
        "construct_type": "WORKER_PROMOTION",
        "construct_id": target_ref,
        "slot_name": slot_name,
        "construct_path": ["worker_plan", "promotion", candidate_id],
        "source_authority": irs_ref_authority,
    }
    d.metadata["authority"] = irs_ref_authority
    d.metadata["original_semantic_role"] = original_semantic_role
    d.metadata["promotion_candidate_id"] = candidate_id
    d.metadata["promotion_status"] = "blocked"
    d.metadata["synthetic_from_route_annotation"] = True
    return d


def _make_handoff_diag(
    diagnostic_id: str,
    slot_name: str = "target",
    handoff_id: str = "h1",
) -> CompileDiagnostic:
    """Create a WORKER_HANDOFF diagnostic with a real slot name."""
    target_ref = f"worker_handoff:{handoff_id}"
    d = CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind="type_or_contract_ambiguity",
        severity="warning",
        message=f"Missing handoff target [construct={target_ref}, slot={slot_name}]",
        target_ref=target_ref,
        source_span_ids=["s1"],
        blocks_completion=True,
    )
    d.metadata["irs_ref"] = {
        "construct_type": "WORKER_HANDOFF",
        "construct_id": target_ref,
        "slot_name": slot_name,
        "construct_path": [],
        "source_authority": "stage_local_irs",
    }
    d.metadata["authority"] = "stage_local_irs"
    d.metadata["original_semantic_role"] = "delegation_intent"
    return d


def _single_diag(
    diagnostic_id: str,
    construct_type: str,
    target_ref: str,
) -> CompileDiagnostic:
    """Create a non-promotion worker diagnostic (HANDOFF, CHILD_WORKER, etc.)."""
    d = CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind="type_or_contract_ambiguity",
        severity="warning",
        message=f"Missing slot [construct={target_ref}, slot=test]",
        target_ref=target_ref,
        source_span_ids=["s1"],
        blocks_completion=True,
    )
    d.metadata["irs_ref"] = {
        "construct_type": construct_type,
        "construct_id": target_ref,
        "slot_name": "test_slot",
        "construct_path": [],
        "source_authority": "stage_local_irs",
    }
    d.metadata["authority"] = "stage_local_irs"
    d.metadata["original_semantic_role"] = "delegation_intent"
    return d


# ===========================================================================
# R5-1: Authority update
# ===========================================================================


class TestR5AuthorityUpdate:
    """R5: Promoted diagnostics carry selected_promoted_stage_local_irs."""

    def test_authority_updated(self) -> None:
        """R5: metadata["authority"] → selected_promoted_stage_local_irs."""
        diags = [_promo_diag("diag_1")]
        WorkerDelegationPromoter().annotate(diags)
        assert diags[0].metadata["authority"] == PROMOTED_AUTHORITY

    def test_irs_ref_source_authority_updated(self) -> None:
        """R5: irs_ref.source_authority also updated."""
        diags = [_promo_diag("diag_1")]
        WorkerDelegationPromoter().annotate(diags)
        irs_ref = diags[0].metadata.get("irs_ref")
        assert isinstance(irs_ref, dict)
        assert irs_ref["source_authority"] == PROMOTED_AUTHORITY

    def test_original_authority_overwritten(self) -> None:
        """R5: The original stage_local_irs authority is replaced."""
        diags = [_promo_diag("diag_1", irs_ref_authority="stage_local_irs")]
        WorkerDelegationPromoter().annotate(diags)
        assert diags[0].metadata["authority"] == PROMOTED_AUTHORITY
        assert diags[0].metadata["authority"] != "stage_local_irs"


# ===========================================================================
# R5-2: WORKER_PROMOTION multi-slot grouping
# ===========================================================================


class TestR5PromotionGrouping:
    """R5: Multiple WORKER_PROMOTION slots for same candidate → one group."""

    def test_four_slots_grouped_together(self) -> None:
        """R5: All 4 promotion slots for cand_1 share a group."""
        diags = [
            _promo_diag("diag_ic", slot_name="promotion_input_contract"),
            _promo_diag("diag_oc", slot_name="promotion_output_contract"),
            _promo_diag("diag_ip", slot_name="promotion_invocation_point"),
            _promo_diag("diag_rh", slot_name="promotion_result_handoff"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        # All share the same group
        gids = {d.metadata[METADATA_KEY_ISSUE_GROUP_ID] for d in diags}
        assert len(gids) == 1
        gid = gids.pop()
        assert "cand_1" in gid

    def test_primary_is_promotion_input_contract(self) -> None:
        """R5: The first slot in canonical order (promotion_input_contract)
        is the primary.
        """
        diags = [
            _promo_diag("diag_rh", slot_name="promotion_result_handoff"),
            _promo_diag("diag_ic", slot_name="promotion_input_contract"),
            _promo_diag("diag_ip", slot_name="promotion_invocation_point"),
            _promo_diag("diag_oc", slot_name="promotion_output_contract"),
        ]
        # Note: scrambled input order
        WorkerDelegationPromoter().annotate(diags)

        primary = [
            d for d in diags
            if d.metadata[METADATA_KEY_ISSUE_ROLE] == "primary"
        ]
        assert len(primary) == 1
        missing = primary[0].missing_slot
        assert missing is not None
        assert missing.slot_name == "promotion_input_contract"

    def test_all_promotion_slots_are_editable(self) -> None:
        """R5: All slots in a promotion group are editable."""
        diags = [
            _promo_diag("diag_ic", slot_name="promotion_input_contract"),
            _promo_diag("diag_oc", slot_name="promotion_output_contract"),
        ]
        WorkerDelegationPromoter().annotate(diags)
        for d in diags:
            assert d.metadata[METADATA_KEY_REPAIRABILITY] == "editable"

    def test_alias_slots_have_primary_diagnostic_id_set(self) -> None:
        """R5: Alias (non-primary) slots reference the primary."""
        diags = [
            _promo_diag("diag_ic", slot_name="promotion_input_contract"),
            _promo_diag("diag_oc", slot_name="promotion_output_contract"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        alias = [
            d for d in diags
            if d.metadata[METADATA_KEY_ISSUE_ROLE] == "alias"
        ]
        assert len(alias) == 1
        assert alias[0].metadata[METADATA_KEY_PRIMARY_DIAGNOSTIC_ID] == "diag_ic"

    def test_related_ids_contains_all_four(self) -> None:
        """R5: related_diagnostic_ids lists all 4 slot diagnostics."""
        diags = [
            _promo_diag("diag_ic", slot_name="promotion_input_contract"),
            _promo_diag("diag_oc", slot_name="promotion_output_contract"),
            _promo_diag("diag_ip", slot_name="promotion_invocation_point"),
            _promo_diag("diag_rh", slot_name="promotion_result_handoff"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        for d in diags:
            related = d.metadata[METADATA_KEY_RELATED_DIAGNOSTIC_IDS]
            assert isinstance(related, list)
            assert set(related) == {"diag_ic", "diag_oc", "diag_ip", "diag_rh"}

    def test_two_candidates_produce_two_groups(self) -> None:
        """R5: cand_1 and cand_2 → two separate groups."""
        diags = [
            _promo_diag("diag_c1_ic", candidate_id="cand_1", slot_name="promotion_input_contract"),
            _promo_diag("diag_c2_ic", candidate_id="cand_2", slot_name="promotion_input_contract"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        gids = {d.metadata[METADATA_KEY_ISSUE_GROUP_ID] for d in diags}
        assert len(gids) == 2
        assert any("cand_1" in g for g in gids)
        assert any("cand_2" in g for g in gids)

    def test_both_candidates_are_primary_in_own_groups(self) -> None:
        """R5: Each candidate's promotion group has its own primary."""
        diags = [
            _promo_diag("diag_c1", candidate_id="cand_1", slot_name="promotion_input_contract"),
            _promo_diag("diag_c2", candidate_id="cand_2", slot_name="promotion_input_contract"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        for d in diags:
            assert d.metadata[METADATA_KEY_ISSUE_ROLE] == "primary"


# ===========================================================================
# R5-3: Single diagnostic promotion (non-grouped)
# ===========================================================================


class TestR5SinglePromotion:
    """R5: Single-diagnostic promotions (non-WORKER_PROMOTION)."""

    def test_worker_handoff_diag_is_primary(self) -> None:
        """R5: Single WORKER_HANDOFF diagnostic → primary, editable."""
        diags = [
            _single_diag("diag_h1", "WORKER_HANDOFF", "worker_handoff:h1"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        d = diags[0]
        assert d.metadata[METADATA_KEY_ISSUE_ROLE] == "primary"
        assert d.metadata[METADATA_KEY_REPAIRABILITY] == "editable"
        assert d.metadata[METADATA_KEY_AUTHORITY] == PROMOTED_AUTHORITY

    def test_invoke_worker_diag_is_primary(self) -> None:
        """R5: Single INVOKE_WORKER diagnostic → primary, editable."""
        diags = [
            _single_diag("diag_iw", "INVOKE_WORKER", "worker:w_main.step:st_invoke"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        d = diags[0]
        assert d.metadata[METADATA_KEY_ISSUE_ROLE] == "primary"
        assert d.metadata[METADATA_KEY_REPAIRABILITY] == "editable"

    def test_single_diag_self_references_as_primary(self) -> None:
        """R5: Single diagnostic's primary_diagnostic_id points to itself."""
        diags = [
            _single_diag("diag_x", "CHILD_WORKER", "child_worker:w_child"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        d = diags[0]
        assert d.metadata[METADATA_KEY_PRIMARY_DIAGNOSTIC_ID] == "diag_x"


# ===========================================================================
# R5-4: delegation_intent preserved, never as target
# ===========================================================================


class TestR5DelegationIntentBoundary:
    """R5: delegation_intent is metadata only — never a construct or target."""

    def test_original_semantic_role_preserved(self) -> None:
        """R5: Promoted diagnostics preserve original_semantic_role."""
        diags = [_promo_diag("diag_1")]
        WorkerDelegationPromoter().annotate(diags)
        assert diags[0].metadata["original_semantic_role"] == "delegation_intent"

    def test_no_delegation_intent_in_target_ref(self) -> None:
        """R5: Promoted diagnostic target_ref never starts with
        delegation_intent:.
        """
        diags = [
            _promo_diag("diag_1"),
            _single_diag("diag_h", "WORKER_HANDOFF", "worker_handoff:h1"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        for d in diags:
            assert not (d.target_ref or "").startswith("delegation_intent:"), (
                f"R5: target_ref must not start with delegation_intent: "
                f"got '{d.target_ref}'"
            )

    def test_no_delegation_intent_in_construct_type(self) -> None:
        """R5: irs_ref.construct_type is never DELEGATION_INTENT."""
        diags = [
            _promo_diag("diag_1"),
            _single_diag("diag_h", "WORKER_HANDOFF", "worker_handoff:h1"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        for d in diags:
            irs_ref = d.metadata.get("irs_ref")
            if isinstance(irs_ref, dict):
                assert irs_ref.get("construct_type") != "DELEGATION_INTENT", (
                    f"R5: irs_ref.construct_type must never be "
                    f"DELEGATION_INTENT, got '{irs_ref.get('construct_type')}'"
                )

    def test_has_delegation_provenance_helper(self) -> None:
        """R5: has_delegation_provenance returns True for
        delegation_intent diagnostics.
        """
        d = _promo_diag("diag_1")
        assert has_delegation_provenance(d) is True

        d2 = _single_diag("diag_no_del", "INVOKE_WORKER", "invoke_worker:x")
        # single_diag helper sets original_semantic_role = delegation_intent
        assert has_delegation_provenance(d2) is True

        # Without the metadata, it returns False
        d3 = CompileDiagnostic(
            diagnostic_id="diag_plain",
            kind="type_or_contract_ambiguity",
            severity="warning",
            message="test",
            target_ref="x",
            blocks_completion=True,
        )
        assert has_delegation_provenance(d3) is False


# ===========================================================================
# R5-5: Catalog lookup via promoted diagnostic
# ===========================================================================


class TestR5CatalogIntegration:
    """R5: Promoted diagnostic's irs_ref + kind finds catalog entries."""

    def test_promoted_promotion_diag_finds_catalog_entry(self) -> None:
        """R5: A promoted WORKER_PROMOTION diagnostic's irs_ref + kind
        finds the worker_promotion.resolve_contract affordance in the catalog.
        """
        diags = [_promo_diag("diag_1", slot_name="promotion_input_contract")]
        WorkerDelegationPromoter().annotate(diags)

        d = diags[0]
        irs_ref = d.metadata.get("irs_ref")
        assert isinstance(irs_ref, dict)

        catalog = RepairCatalogBuilder.from_construct_registry(
            SPLConstructRegistry.default()
        )

        # Look up by (construct_type, slot_name, diagnostic_kind)
        entries = catalog.find_by_construct_slot_kind(
            construct_type=irs_ref["construct_type"],
            slot_name=irs_ref["slot_name"],
            diagnostic_kind=d.kind,
        )
        assert len(entries) == 1
        assert entries[0].affordance_id == "worker_promotion.resolve_contract"

    def test_promoted_handoff_diag_finds_catalog_entry(self) -> None:
        """R5: A promoted WORKER_HANDOFF diagnostic finds its affordance
        via irs_ref dict lookup through the catalog.
        """
        diags = [
            _make_handoff_diag("diag_h", "target"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        d = diags[0]
        irs_ref_dict = d.metadata.get("irs_ref")
        assert isinstance(irs_ref_dict, dict)

        # Convert to DiagnosticIRSRef for catalog lookup
        irs_ref = DiagnosticIRSRef.from_dict(irs_ref_dict)

        catalog = RepairCatalogBuilder.from_construct_registry(
            SPLConstructRegistry.default()
        )
        entries = catalog.find_by_irs_ref(irs_ref, d.kind)
        assert len(entries) == 1
        assert entries[0].affordance_id == "worker_handoff.specify_target"


# ===========================================================================
# R5-6: is_worker_delegation_editable helper
# ===========================================================================


class TestR5IsWorkerDelegationEditable:
    """R5: is_worker_delegation_editable query helper."""

    def test_promoted_primary_returns_true(self) -> None:
        """R5: Promoted primary → True."""
        diags = [_promo_diag("diag_1", slot_name="promotion_input_contract")]
        WorkerDelegationPromoter().annotate(diags)
        assert is_worker_delegation_editable(diags[0]) is True

    def test_promoted_alias_returns_false(self) -> None:
        """R5: Promoted alias → False (only primary)."""
        diags = [
            _promo_diag("diag_ic", slot_name="promotion_input_contract"),
            _promo_diag("diag_oc", slot_name="promotion_output_contract"),
        ]
        WorkerDelegationPromoter().annotate(diags)
        alias = [d for d in diags
                 if d.metadata[METADATA_KEY_ISSUE_ROLE] == "alias"][0]
        assert is_worker_delegation_editable(alias) is False

    def test_unpromoted_returns_false(self) -> None:
        """R5: Non-promoted diagnostic → False."""
        d = CompileDiagnostic(
            diagnostic_id="diag_x",
            kind="type_or_contract_ambiguity",
            severity="warning",
            message="test",
            target_ref="x",
            blocks_completion=True,
        )
        assert is_worker_delegation_editable(d) is False


# ===========================================================================
# R5-7: Empty input handling
# ===========================================================================


class TestR5EmptyInput:
    """R5: Edge cases with empty or non-promotion input."""

    def test_empty_list_returns_empty(self) -> None:
        """R5: annotate([]) returns []."""
        result = WorkerDelegationPromoter().annotate([])
        assert result == []

    def test_non_promotion_diags_not_grouped(self) -> None:
        """R5: Non-WORKER_PROMOTION diagnostics are annotated individually,
        not grouped.
        """
        diags = [
            _single_diag("diag_h1", "WORKER_HANDOFF", "worker_handoff:h1"),
            _single_diag("diag_h2", "WORKER_HANDOFF", "worker_handoff:h2"),
        ]
        WorkerDelegationPromoter().annotate(diags)

        # Both are primary in separate groups
        gids = {d.metadata[METADATA_KEY_ISSUE_GROUP_ID] for d in diags}
        assert len(gids) == 2
        for d in diags:
            assert d.metadata[METADATA_KEY_ISSUE_ROLE] == "primary"
