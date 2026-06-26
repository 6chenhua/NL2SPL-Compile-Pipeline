"""B2: EditableIssueExtractor tests."""

from __future__ import annotations

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder
from nl2spl.compiler.spl_editing.issues.extractor import EditableIssueExtractor
from nl2spl.ir.diagnostics import CompileDiagnostic

# ===========================================================================
# Helpers
# ===========================================================================


def _diag(
    diagnostic_id: str,
    kind: str = "missing_handler",
    target_ref: str = "worker:w_main.exception_flow:exc_1",
    *,
    construct_type: str = "EXCEPTION_FLOW",
    construct_id: str = "worker:w_main.exception_flow:exc_1",
    slot_name: str = "handler_action",
    authority: str = "post_normalize_irs",
    repairability: str = "editable",
    issue_role: str = "primary",
    issue_group_id: str | None = None,
    source_span_ids: list[str] | None = None,
    missing_slot_name: str | None = None,
) -> CompileDiagnostic:
    d = CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind=kind,
        severity="warning",
        message=f"Test: {kind}",
        target_ref=target_ref,
        source_span_ids=list(source_span_ids or []),
        blocks_completion=True,
        missing_slot=(
            MissingSlot(
                slot_name=missing_slot_name,
                required_for="complete",
                reason=f"missing {missing_slot_name}",
                source_span_ids=list(source_span_ids or []),
            )
            if missing_slot_name
            else None
        ),
    )
    d.metadata["irs_ref"] = {
        "construct_type": construct_type,
        "construct_id": construct_id,
        "slot_name": slot_name,
        "construct_path": [],
        "source_authority": authority,
    }
    d.metadata["authority"] = authority
    d.metadata["repairability"] = repairability
    d.metadata["issue_role"] = issue_role
    if issue_group_id:
        d.metadata["issue_group_id"] = issue_group_id
    return d


def _catalog():
    return RepairCatalogBuilder.from_construct_registry(SPLConstructRegistry.default())


# ===========================================================================
# B2-1: Extractor filters correctly
# ===========================================================================


class TestB2ExtractorFilters:
    """B2: Only eligible diagnostics become issues."""

    def test_missing_handler_becomes_issue(self) -> None:
        diags = [_diag("diag_mh")]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 1
        assert issues[0].kind == "missing_handler"

    def test_missing_output_producer_becomes_issue(self) -> None:
        diags = [
            _diag(
                "diag_mop",
                kind="missing_output_producer",
                construct_type="REQUIRED_OUTPUT",
                construct_id="worker:w_main.output:draft",
                slot_name="producer",
                target_ref="worker:w_main.output:draft",
            )
        ]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 1
        assert issues[0].kind == "missing_output_producer"

    def test_no_irs_ref_is_excluded(self) -> None:
        d = CompileDiagnostic(
            diagnostic_id="diag_no_ref",
            kind="missing_handler",
            severity="warning",
            message="test",
            target_ref="x",
            blocks_completion=True,
        )
        issues = EditableIssueExtractor(_catalog()).extract([d])
        assert len(issues) == 0

    def test_wrong_authority_is_excluded(self) -> None:
        diags = [_diag("diag_x", authority="stage_local_irs")]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 0

    def test_excluded_kind_is_excluded(self) -> None:
        diags = [_diag("diag_x", kind="route_refinement_corrected")]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 0

    def test_non_editable_repairability_is_excluded(self) -> None:
        diags = [_diag("diag_x", repairability="review_only")]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 0

    def test_no_affordance_in_catalog_is_excluded(self) -> None:
        diags = [
            _diag(
                "diag_x",
                kind="assumed_command_not_renderable",
                construct_type="GENERAL_COMMAND",
                construct_id="step:st_1",
                slot_name="source_evidence",
            )
        ]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 0


# ===========================================================================
# B2-2: Grouping — alias is not a separate issue
# ===========================================================================


class TestB2ExtractorGrouping:
    """B2: Grouped diagnostics produce one issue per primary."""

    def test_alias_is_not_separate_issue(self) -> None:
        """B2: primary + alias in same group → one issue.
        The alias diagnostic (RCD) has no affordance in the catalog,
        so it is excluded from candidates.  The primary (REQUIRED_OUTPUT)
        alone becomes the issue.
        """
        diags = [
            _diag(
                "diag_primary",
                kind="missing_output_producer",
                construct_type="REQUIRED_OUTPUT",
                construct_id="worker:w_main.output:draft",
                slot_name="producer",
                target_ref="worker:w_main.output:draft",
                issue_role="primary",
                issue_group_id="producer_group:draft",
            ),
            _diag(
                "diag_alias",
                kind="missing_output_producer",
                construct_type="RESOURCE_CONTRACT_DEMAND",
                construct_id="rcd_draft",
                slot_name="producer",
                target_ref="resource_contract_demand:rcd_draft",
                issue_role="alias",
                issue_group_id="producer_group:draft",
            ),
        ]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        # RCD alias has no affordance → filtered out → primary is the only issue
        assert len(issues) == 1
        assert issues[0].primary_diagnostic_id == "diag_primary"

    def test_alias_in_group_when_both_have_affordances(self) -> None:
        """B2: Two missing_handler diagnostics in the same group
        with the same affordance → one issue, related IDs include both.
        """
        diags = [
            _diag(
                "diag_primary",
                kind="missing_handler",
                construct_type="EXCEPTION_FLOW",
                construct_id="worker:w_main.exception_flow:exc_1",
                slot_name="handler_action",
                target_ref="worker:w_main.exception_flow:exc_1",
                issue_role="primary",
                issue_group_id="group_exc_1",
            ),
            _diag(
                "diag_second",
                kind="missing_handler",
                construct_type="EXCEPTION_FLOW",
                construct_id="worker:w_main.exception_flow:exc_1",
                slot_name="handler_action",
                target_ref="worker:w_main.exception_flow:exc_1",
                issue_role="alias",
                issue_group_id="group_exc_1",
            ),
        ]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 1
        assert issues[0].primary_diagnostic_id == "diag_primary"
        assert "diag_second" in issues[0].related_diagnostic_ids

    def test_worker_promotion_group_becomes_one_issue(self) -> None:
        """B2: 4 WORKER_PROMOTION slots grouped → one issue."""
        diags = []
        for i, slot in enumerate(
            [
                "promotion_input_contract",
                "promotion_output_contract",
                "promotion_invocation_point",
                "promotion_result_handoff",
            ]
        ):
            diags.append(
                _diag(
                    f"diag_promo_{i}",
                    kind="type_or_contract_ambiguity",
                    construct_type="WORKER_PROMOTION",
                    construct_id="worker_promotion:cand_1",
                    slot_name=slot,
                    target_ref="worker_promotion:cand_1",
                    authority="selected_promoted_stage_local_irs",
                    issue_role="primary" if i == 0 else "alias",
                    issue_group_id="worker_promotion_group:worker_promotion:cand_1",
                    missing_slot_name=slot,
                )
            )
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 1
        assert issues[0].kind == "type_or_contract_ambiguity"
        assert len(issues[0].related_diagnostic_ids) == 4

    def test_two_separate_groups_produce_two_issues(self) -> None:
        diags = [
            _diag("diag_a", issue_group_id="group_a", issue_role="primary"),
            _diag("diag_b", issue_group_id="group_b", issue_role="primary"),
        ]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 2


# ===========================================================================
# B2-3: Affordance IDs and catalog linkage
# ===========================================================================


class TestB2AffordanceLinkage:
    """B2: Issues carry correct affordance IDs from the catalog."""

    def test_missing_handler_has_correct_affordance(self) -> None:
        diags = [_diag("diag_mh")]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 1
        assert "exception_flow.add_handler_step" in issues[0].affordance_ids
        assert issues[0].default_affordance_id == "exception_flow.add_handler_step"

    def test_worker_promotion_has_correct_affordance(self) -> None:
        diags = [
            _diag(
                "diag_promo",
                kind="type_or_contract_ambiguity",
                construct_type="WORKER_PROMOTION",
                construct_id="worker_promotion:cand_1",
                slot_name="promotion_input_contract",
                target_ref="worker_promotion:cand_1",
                authority="selected_promoted_stage_local_irs",
                issue_role="primary",
                issue_group_id="g1",
                missing_slot_name="promotion_input_contract",
            )
        ]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 1
        assert "worker_promotion.resolve_contract" in issues[0].affordance_ids


# ===========================================================================
# B2-4: delegation_intent does not appear as target kind
# ===========================================================================


class TestB2DelegationIntentBoundary:
    """B2: DELEGATION_INTENT never appears as construct_type or target_ref."""

    def test_no_delegation_intent_in_issue_target_ref(self) -> None:
        diags = [
            _diag(
                "diag_promo",
                kind="type_or_contract_ambiguity",
                construct_type="WORKER_PROMOTION",
                construct_id="worker_promotion:cand_1",
                slot_name="promotion_input_contract",
                target_ref="worker_promotion:cand_1",
                authority="selected_promoted_stage_local_irs",
            )
        ]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        for issue in issues:
            assert "DELEGATION_INTENT" not in issue.target_ref
            assert issue.irs_ref.construct_type != "DELEGATION_INTENT"


# ===========================================================================
# B2-5: Empty input
# ===========================================================================


class TestB2EmptyInput:
    """B2: Edge cases."""

    def test_empty_diagnostics_produces_empty(self) -> None:
        issues = EditableIssueExtractor(_catalog()).extract([])
        assert issues == ()

    def test_no_eligible_diagnostics_produces_empty(self) -> None:
        d = CompileDiagnostic(
            diagnostic_id="d",
            kind="validation_warning",
            severity="warning",
            message="test",
            target_ref="x",
            blocks_completion=True,
        )
        issues = EditableIssueExtractor(_catalog()).extract([d])
        assert issues == ()


# ===========================================================================
# B2-6: Ungrouped missing_handler (no repairability/issue_role) still works
# ===========================================================================


class TestB2UngroupedDefaultBehavior:
    """B2: Ungrouped IRS-backed diagnostics default to editable + primary."""

    def test_missing_handler_without_explicit_repairability(self) -> None:
        """B2: A real post-normalize missing_handler has only irs_ref +
        authority, no repairability/issue_role.  It should still become
        an editable issue.
        """
        d = CompileDiagnostic(
            diagnostic_id="diag_real_mh",
            kind="missing_handler",
            severity="warning",
            message="Exception flow has condition but no handler step.",
            target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
        )
        d.metadata["irs_ref"] = {
            "construct_type": "EXCEPTION_FLOW",
            "construct_id": "worker:w_main.exception_flow:exc_1",
            "slot_name": "handler_action",
            "construct_path": [],
            "source_authority": "post_normalize_irs",
        }
        d.metadata["authority"] = "post_normalize_irs"
        # No repairability, no issue_role — bare diagnostic

        issues = EditableIssueExtractor(_catalog()).extract([d])
        assert len(issues) == 1
        assert issues[0].kind == "missing_handler"
        assert issues[0].repairability == "editable"


# ===========================================================================
# B2-7: Malformed group (no primary) is skipped
# ===========================================================================


class TestB2MalformedGroup:
    """B2: Groups without exactly one primary are skipped."""

    def test_group_with_only_alias_is_skipped(self) -> None:
        """B2: A group where every diagnostic has issue_role=alias
        produces no issue — no fallback to group[0].
        """
        diags = [
            _diag(
                "diag_a",
                kind="missing_output_producer",
                construct_type="REQUIRED_OUTPUT",
                construct_id="worker:w_main.output:draft",
                slot_name="producer",
                target_ref="worker:w_main.output:draft",
                issue_role="alias",
                issue_group_id="group_x",
            ),
            _diag(
                "diag_b",
                kind="missing_output_producer",
                construct_type="REQUIRED_OUTPUT",
                construct_id="worker:w_main.output:draft",
                slot_name="producer",
                target_ref="worker:w_main.output:draft",
                issue_role="alias",
                issue_group_id="group_x",
            ),
        ]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 0

    def test_group_with_two_primaries_is_skipped(self) -> None:
        diags = [
            _diag("diag_a", issue_role="primary", issue_group_id="group_x"),
            _diag("diag_b", issue_role="primary", issue_group_id="group_x"),
        ]
        issues = EditableIssueExtractor(_catalog()).extract(diags)
        assert len(issues) == 0
