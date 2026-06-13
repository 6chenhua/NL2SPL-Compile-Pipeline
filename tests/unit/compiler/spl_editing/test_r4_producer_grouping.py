"""R4 Producer Issue Grouping: post-implementation tests.

Verifies that after R4 changes:
  1. missing_output_producer from REQUIRED_OUTPUT → primary, editable
  2. missing_output_producer from RESOURCE_CONTRACT_DEMAND → alias, editable
  3. unspecified_output_missing_producer → review_only
  4. resource_kind_mismatch / missing_resource_contract → non_repairable, context
  5. Grouping: same output name → shared issue_group_id
  6. Grouping: different outputs → separate groups
  7. Non-producer diagnostics are untouched
  8. is_producer_editable helper works correctly
"""

from __future__ import annotations

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.compiler.spl_editing.issues.grouper import (
    ProducerIssueGrouper,
    is_producer_editable,
)
from nl2spl.ir.diagnostics import (
    METADATA_KEY_ISSUE_GROUP_ID,
    METADATA_KEY_PRIMARY_DIAGNOSTIC_ID,
    METADATA_KEY_ISSUE_ROLE,
    METADATA_KEY_RELATED_DIAGNOSTIC_IDS,
    METADATA_KEY_REPAIRABILITY,
    CompileDiagnostic,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_diag(
    diagnostic_id: str,
    kind: str,
    target_ref: str,
    message: str = "",
    *,
    irs_ref: dict | None = None,
) -> CompileDiagnostic:
    """Build a minimal diagnostic with optional irs_ref metadata."""
    d = CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind=kind,
        severity="warning",
        message=message,
        target_ref=target_ref,
        blocks_completion=(kind != "unspecified_output_missing_producer"),
    )
    if irs_ref is not None:
        d.metadata["irs_ref"] = irs_ref
    return d


def _req_output_diag(
    diagnostic_id: str,
    worker_id: str = "w_main",
    output_name: str = "draft",
) -> CompileDiagnostic:
    """Create a REQUIRED_OUTPUT.producer missing_output_producer diagnostic."""
    return _make_diag(
        diagnostic_id=diagnostic_id,
        kind="missing_output_producer",
        target_ref=f"worker:{worker_id}.output:{output_name}",
        message=(
            f"Required output '{output_name}' (draft document) has "
            "no source-backed producer step. "
            "[construct=worker:w_main.output:draft, slot=producer]"
        ),
        irs_ref={
            "construct_type": "REQUIRED_OUTPUT",
            "construct_id": f"worker:{worker_id}.output:{output_name}",
            "slot_name": "producer",
            "construct_path": ["worker_plan", worker_id, "output_contract", output_name],
            "source_authority": "post_normalize_irs",
        },
    )


def _rcd_producer_diag(
    diagnostic_id: str,
    demand_id: str = "rcd_output_draft",
    resource_names: str = "draft",
) -> CompileDiagnostic:
    """Create a RESOURCE_CONTRACT_DEMAND.producer missing_output_producer diagnostic."""
    return _make_diag(
        diagnostic_id=diagnostic_id,
        kind="missing_output_producer",
        target_ref=f"resource_contract_demand:{demand_id}",
        message=(
            f"Resource contract output '{demand_id}' (requiredness=required) "
            f"has materialized resource(s) {resource_names} "
            "but no renderable producer. "
            f"[construct=resource_contract_demand:{demand_id}, slot=producer]"
        ),
        irs_ref={
            "construct_type": "RESOURCE_CONTRACT_DEMAND",
            "construct_id": f"resource_contract_demand:{demand_id}",
            "slot_name": "producer",
            "construct_path": ["resource_contract", demand_id],
            "source_authority": "post_normalize_irs",
        },
    )


def _unspecified_diag(
    diagnostic_id: str,
    demand_id: str = "rcd_unspec_x",
    resource_name: str = "optional_output",
) -> CompileDiagnostic:
    """Create an unspecified_output_missing_producer diagnostic."""
    return _make_diag(
        diagnostic_id=diagnostic_id,
        kind="unspecified_output_missing_producer",
        target_ref=f"resource_contract_demand:{demand_id}",
        message=(
            f"Resource contract output '{demand_id}' "
            f"has requiredness=unspecified and no renderable producer. "
            f"Review whether this output should be declared optional "
            f"or a producer step should be added."
        ),
        irs_ref={
            "construct_type": "RESOURCE_CONTRACT_DEMAND",
            "construct_id": f"resource_contract_demand:{demand_id}",
            "slot_name": "producer",
            "source_authority": "post_normalize_irs",
        },
    )


def _resource_kind_mismatch_diag(
    diagnostic_id: str,
    demand_id: str = "rcd_mismatch",
) -> CompileDiagnostic:
    """Create a resource_kind_mismatch diagnostic."""
    return _make_diag(
        diagnostic_id=diagnostic_id,
        kind="resource_kind_mismatch",
        target_ref=f"resource_contract_demand:{demand_id}",
        message=(
            f"Resource contract demand '{demand_id}' has "
            "binding(s) whose resource_kind/name do not match..."
        ),
    )


def _missing_resource_contract_diag(
    diagnostic_id: str,
    demand_id: str = "rcd_nomat",
) -> CompileDiagnostic:
    """Create a missing_resource_contract diagnostic."""
    return _make_diag(
        diagnostic_id=diagnostic_id,
        kind="missing_resource_contract",
        target_ref=f"resource_contract_demand:{demand_id}",
        message=(
            f"Resource contract demand '{demand_id}' (output, "
            f"requiredness=required) has no materialized resource."
        ),
    )


# ===========================================================================
# R4-1: Primary / alias grouping
# ===========================================================================


class TestR4PrimaryAliasGrouping:
    """R4: REQUIRED_OUTPUT.producer = primary,
    RESOURCE_CONTRACT_DEMAND.producer = alias.
    """

    def test_same_output_produces_single_group(self) -> None:
        """R4: Two missing_output_producer diagnostics for the same output
        'draft' → one group, shared issue_group_id.
        """
        diags = [
            _req_output_diag("diag_req", output_name="draft"),
            _rcd_producer_diag("diag_rcd", resource_names="draft"),
        ]
        ProducerIssueGrouper().annotate(diags)

        # Both share the same group
        gid0 = diags[0].metadata.get(METADATA_KEY_ISSUE_GROUP_ID)
        gid1 = diags[1].metadata.get(METADATA_KEY_ISSUE_GROUP_ID)
        assert gid0 is not None
        assert gid0 == gid1
        assert gid0 == "producer_group:draft"

    def test_required_output_is_primary(self) -> None:
        """R4: REQUIRED_OUTPUT.producer → role=primary, editable."""
        diags = [
            _req_output_diag("diag_req", output_name="draft"),
            _rcd_producer_diag("diag_rcd", resource_names="draft"),
        ]
        ProducerIssueGrouper().annotate(diags)

        req = diags[0]
        assert req.metadata[METADATA_KEY_ISSUE_ROLE] == "primary"
        assert req.metadata[METADATA_KEY_REPAIRABILITY] == "editable"
        assert req.metadata[METADATA_KEY_PRIMARY_DIAGNOSTIC_ID] == "diag_req"

    def test_rcd_producer_is_alias(self) -> None:
        """R4: RESOURCE_CONTRACT_DEMAND.producer → role=alias, editable."""
        diags = [
            _req_output_diag("diag_req", output_name="draft"),
            _rcd_producer_diag("diag_rcd", resource_names="draft"),
        ]
        ProducerIssueGrouper().annotate(diags)

        rcd = diags[1]
        assert rcd.metadata[METADATA_KEY_ISSUE_ROLE] == "alias"
        assert rcd.metadata[METADATA_KEY_REPAIRABILITY] == "editable"
        assert rcd.metadata[METADATA_KEY_PRIMARY_DIAGNOSTIC_ID] == "diag_req"

    def test_related_diagnostic_ids_contains_both(self) -> None:
        """R4: related_diagnostic_ids lists all diagnostics in the group."""
        diags = [
            _req_output_diag("diag_req", output_name="draft"),
            _rcd_producer_diag("diag_rcd", resource_names="draft"),
        ]
        ProducerIssueGrouper().annotate(diags)

        for d in diags:
            related = d.metadata.get(METADATA_KEY_RELATED_DIAGNOSTIC_IDS)
            assert isinstance(related, list)
            assert set(related) == {"diag_req", "diag_rcd"}


# ===========================================================================
# R4-2: Different outputs → separate groups
# ===========================================================================


class TestR4SeparateGroups:
    """R4: Different missing outputs produce separate groups."""

    def test_two_outputs_produce_two_groups(self) -> None:
        """R4: draft and final_report → two distinct groups."""
        diags = [
            _req_output_diag("diag_draft", output_name="draft"),
            _req_output_diag("diag_report", output_name="final_report"),
        ]
        ProducerIssueGrouper().annotate(diags)

        g0 = diags[0].metadata[METADATA_KEY_ISSUE_GROUP_ID]
        g1 = diags[1].metadata[METADATA_KEY_ISSUE_GROUP_ID]
        assert g0 != g1
        assert "draft" in g0
        assert "final_report" in g1

    def test_both_are_primary_in_their_own_groups(self) -> None:
        """R4: Each REQUIRED_OUTPUT is primary in its own group."""
        diags = [
            _req_output_diag("diag_draft", output_name="draft"),
            _req_output_diag("diag_report", output_name="final_report"),
        ]
        ProducerIssueGrouper().annotate(diags)

        for d in diags:
            assert d.metadata[METADATA_KEY_ISSUE_ROLE] == "primary"
            assert d.metadata[METADATA_KEY_PRIMARY_DIAGNOSTIC_ID] == d.diagnostic_id


# ===========================================================================
# R4-3: Review-only: unspecified_output_missing_producer
# ===========================================================================


class TestR4UnspecifiedOutput:
    """R4: unspecified_output_missing_producer → review_only."""

    def test_unspecified_is_review_only(self) -> None:
        """R4: unspecified_output_missing_producer is review_only."""
        diags = [_unspecified_diag("diag_unspec")]
        ProducerIssueGrouper().annotate(diags)

        assert diags[0].metadata[METADATA_KEY_REPAIRABILITY] == "review_only"

    def test_unspecified_in_same_group_as_missing_producer(self) -> None:
        """R4: When unspecified and missing_producer refer to the same
        resource, they may group together. The unspecified one gets
        role=context (non-editable).
        """
        diags = [
            _req_output_diag("diag_req", output_name="optional_output"),
            # This unspecified diag's message mentions 'optional_output'
            # as a materialized resource → same group
            _make_diag(
                diagnostic_id="diag_unspec",
                kind="unspecified_output_missing_producer",
                target_ref="resource_contract_demand:rcd_unspec",
                message=(
                    "Resource contract output 'rcd_unspec' "
                    "has requiredness=unspecified and no renderable producer. "
                    "Review whether this output should be declared optional "
                    "or a producer step should be added. "
                    "has materialized resource(s) optional_output but "
                    "is not required."
                ),
                irs_ref={
                    "construct_type": "RESOURCE_CONTRACT_DEMAND",
                    "construct_id": "resource_contract_demand:rcd_unspec",
                    "slot_name": "producer",
                    "source_authority": "post_normalize_irs",
                },
            ),
        ]
        ProducerIssueGrouper().annotate(diags)

        # Both in the same group (same resource name extracted from message)
        # The unspecified one is non-editable → context role
        unspec = [d for d in diags if d.kind == "unspecified_output_missing_producer"][0]
        assert unspec.metadata[METADATA_KEY_REPAIRABILITY] == "review_only"
        # If grouped together, the role is 'context' (not primary/alias for editable)
        role = unspec.metadata.get(METADATA_KEY_ISSUE_ROLE)
        assert role in ("context", "alias"), (
            f"Unspecified output in a group should be context or alias, got {role}"
        )


# ===========================================================================
# R4-4: Non-repairable: resource_kind_mismatch / missing_resource_contract
# ===========================================================================


class TestR4NonRepairable:
    """R4: resource_kind_mismatch and missing_resource_contract
    are non_repairable for producer patches.
    """

    def test_resource_kind_mismatch_is_non_repairable(self) -> None:
        """R4: resource_kind_mismatch → non_repairable."""
        diags = [_resource_kind_mismatch_diag("diag_mismatch")]
        ProducerIssueGrouper().annotate(diags)

        assert diags[0].metadata[METADATA_KEY_REPAIRABILITY] == "non_repairable"

    def test_missing_resource_contract_is_non_repairable(self) -> None:
        """R4: missing_resource_contract → non_repairable."""
        diags = [_missing_resource_contract_diag("diag_nomat")]
        ProducerIssueGrouper().annotate(diags)

        assert diags[0].metadata[METADATA_KEY_REPAIRABILITY] == "non_repairable"


# ===========================================================================
# R4-5: Non-producer diagnostics are untouched
# ===========================================================================


class TestR4NonProducerUntouched:
    """R4: Diagnostics that aren't producer-adjacent are left alone."""

    def test_missing_handler_untouched(self) -> None:
        """R4: missing_handler diagnostic gets no grouping metadata."""
        diag = CompileDiagnostic(
            diagnostic_id="diag_mh",
            kind="missing_handler",
            severity="warning",
            message="No handler",
            target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
            metadata={
                "irs_ref": {
                    "construct_type": "EXCEPTION_FLOW",
                    "construct_id": "worker:w_main.exception_flow:exc_1",
                    "slot_name": "handler_action",
                    "source_authority": "post_normalize_irs",
                },
            },
        )
        diags = [diag]
        ProducerIssueGrouper().annotate(diags)

        assert METADATA_KEY_ISSUE_GROUP_ID not in diag.metadata
        assert METADATA_KEY_ISSUE_ROLE not in diag.metadata

    def test_type_or_contract_ambiguity_untouched(self) -> None:
        """R4: type_or_contract_ambiguity diagnostic gets no grouping metadata."""
        diag = CompileDiagnostic(
            diagnostic_id="diag_amb",
            kind="type_or_contract_ambiguity",
            severity="warning",
            message="Ambiguous",
            target_ref="worker_promotion:del_s1",
            blocks_completion=True,
        )
        diags = [diag]
        ProducerIssueGrouper().annotate(diags)

        assert METADATA_KEY_ISSUE_GROUP_ID not in diag.metadata

    def test_mixed_producer_and_non_producer(self) -> None:
        """R4: In a mixed list, only producer diagnostics are annotated."""
        diags = [
            _req_output_diag("diag_prod", output_name="draft"),
            CompileDiagnostic(
                diagnostic_id="diag_mh",
                kind="missing_handler",
                severity="warning",
                message="No handler",
                target_ref="worker:w_main.exception_flow:exc_1",
                blocks_completion=True,
            ),
        ]
        ProducerIssueGrouper().annotate(diags)

        # Producer diagnostic is annotated
        assert METADATA_KEY_ISSUE_GROUP_ID in diags[0].metadata
        # Non-producer is untouched
        assert METADATA_KEY_ISSUE_GROUP_ID not in diags[1].metadata


# ===========================================================================
# R4-6: is_producer_editable helper
# ===========================================================================


class TestR4IsProducerEditable:
    """R4: is_producer_editable query helper."""

    def test_primary_editable_returns_true(self) -> None:
        """R4: primary + editable → True."""
        diags = [_req_output_diag("diag_req", output_name="draft")]
        ProducerIssueGrouper().annotate(diags)
        assert is_producer_editable(diags[0]) is True

    def test_alias_editable_returns_false(self) -> None:
        """R4: alias + editable → False (only primary is 'the' editable issue)."""
        diags = [
            _req_output_diag("diag_req", output_name="draft"),
            _rcd_producer_diag("diag_rcd", resource_names="draft"),
        ]
        ProducerIssueGrouper().annotate(diags)
        rcd = [d for d in diags if d.kind == "missing_output_producer"
               and d.metadata.get(METADATA_KEY_ISSUE_ROLE) == "alias"][0]
        assert is_producer_editable(rcd) is False

    def test_review_only_returns_false(self) -> None:
        """R4: review_only → False."""
        diags = [_unspecified_diag("diag_unspec")]
        ProducerIssueGrouper().annotate(diags)
        assert is_producer_editable(diags[0]) is False

    def test_unannotated_returns_false(self) -> None:
        """R4: Diagnostic without grouping metadata → False."""
        diag = CompileDiagnostic(
            diagnostic_id="diag_x",
            kind="missing_output_producer",
            severity="warning",
            message="Test",
            target_ref="x",
            blocks_completion=True,
        )
        assert is_producer_editable(diag) is False


# ===========================================================================
# R4-7: Deterministic grouping
# ===========================================================================


class TestR4Deterministic:
    """R4: Grouping is deterministic."""

    def test_repeated_annotation_is_idempotent(self) -> None:
        """R4: Annotating the same diagnostics twice produces the same result."""
        diags_a = [
            _req_output_diag("diag_req", output_name="draft"),
            _rcd_producer_diag("diag_rcd", resource_names="draft"),
        ]
        diags_b = [
            _req_output_diag("diag_req", output_name="draft"),
            _rcd_producer_diag("diag_rcd", resource_names="draft"),
        ]

        ProducerIssueGrouper().annotate(diags_a)
        ProducerIssueGrouper().annotate(diags_b)

        for da, db in zip(diags_a, diags_b):
            assert da.metadata[METADATA_KEY_ISSUE_GROUP_ID] == db.metadata[METADATA_KEY_ISSUE_GROUP_ID]
            assert da.metadata[METADATA_KEY_ISSUE_ROLE] == db.metadata[METADATA_KEY_ISSUE_ROLE]

    def test_primary_is_first_editable_by_diagnostic_id(self) -> None:
        """R4: When multiple editable diagnostics exist, the primary is
        the one with the lexicographically smallest diagnostic_id.
        """
        # Create two REQUIRED_OUTPUT diagnostics for the same output
        # (simulating a rare double-emission scenario).
        diags = [
            _make_diag(
                diagnostic_id="diag_aaa",
                kind="missing_output_producer",
                target_ref="worker:w_main.output:draft",
                message="Required output 'draft' has no producer.",
                irs_ref={
                    "construct_type": "REQUIRED_OUTPUT",
                    "construct_id": "worker:w_main.output:draft",
                    "slot_name": "producer",
                    "source_authority": "post_normalize_irs",
                },
            ),
            _make_diag(
                diagnostic_id="diag_bbb",
                kind="missing_output_producer",
                target_ref="worker:w_main.output:draft",
                message="Required output 'draft' has no producer.",
                irs_ref={
                    "construct_type": "REQUIRED_OUTPUT",
                    "construct_id": "worker:w_main.output:draft",
                    "slot_name": "producer",
                    "source_authority": "post_normalize_irs",
                },
            ),
        ]
        ProducerIssueGrouper().annotate(diags)

        # diag_aaa is lexicographically smaller → primary
        primary = [d for d in diags
                   if d.metadata.get(METADATA_KEY_ISSUE_ROLE) == "primary"]
        assert len(primary) == 1
        assert primary[0].diagnostic_id == "diag_aaa"

        alias = [d for d in diags
                 if d.metadata.get(METADATA_KEY_ISSUE_ROLE) == "alias"]
        assert len(alias) == 1
        assert alias[0].diagnostic_id == "diag_bbb"
