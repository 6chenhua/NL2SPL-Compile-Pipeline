"""B2: Target resolver tests."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.model import EditableIssue
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.targets.exception_flow import (
    ExceptionFlowTargetResolver,
)
from nl2spl.compiler.spl_editing.targets.required_output import (
    RequiredOutputTargetResolver,
)
from nl2spl.compiler.spl_editing.targets.step import StepTargetResolver
from nl2spl.compiler.spl_editing.targets.worker_handoff import (
    WorkerHandoffTargetResolver,
)
from nl2spl.compiler.spl_editing.targets.worker_promotion import (
    WorkerPromotionTargetResolver,
)
from nl2spl.ir.diagnostics import DiagnosticIRSRef


def _snapshot() -> ArtifactSnapshot:
    return ArtifactSnapshot("snap_1", "run_1", 0)


def _issue(**kw: object) -> EditableIssue:
    defaults: dict[str, object] = dict(
        issue_id="i1",
        primary_diagnostic_id="d1",
        related_diagnostic_ids=("d1",),
        issue_group_id=None,
        kind="missing_handler",
        target_ref="worker:w_main.exception_flow:exc_1",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="worker:w_main.exception_flow:exc_1",
            slot_name="handler_action",
        ),
        missing_slot="handler_action",
        source_span_ids=(),
        message="test",
        affordance_ids=("exception_flow.add_handler_step",),
        default_affordance_id="exception_flow.add_handler_step",
    )
    defaults.update(kw)
    return EditableIssue(**defaults)  # type: ignore[arg-type]


# ===========================================================================
# B2-T1: ExceptionFlowTargetResolver
# ===========================================================================


class TestB2ExceptionFlowResolver:
    def test_resolver_id_matches_catalog(self) -> None:
        assert ExceptionFlowTargetResolver().resolver_id == "exception_flow_target"

    def test_extracts_worker_id(self) -> None:
        target = ExceptionFlowTargetResolver().resolve(
            _issue(target_ref="worker:w_main.exception_flow:exc_1"),
            _snapshot(),
        )
        assert target.worker_id == "w_main"
        assert target.target_kind == "EXCEPTION_FLOW"

    def test_respects_affordance_from_issue(self) -> None:
        target = ExceptionFlowTargetResolver().resolve(
            _issue(
                target_ref="worker:w_main.exception_flow:exc_1",
                default_affordance_id="exception_flow.add_handler_step",
            ),
            _snapshot(),
        )
        assert target.affordance_id == "exception_flow.add_handler_step"


# ===========================================================================
# B2-T2: RequiredOutputTargetResolver
# ===========================================================================


class TestB2RequiredOutputResolver:
    def test_extracts_worker_id(self) -> None:
        target = RequiredOutputTargetResolver().resolve(
            _issue(
                kind="missing_output_producer",
                target_ref="worker:w_main.output:draft",
                irs_ref=DiagnosticIRSRef(
                    construct_type="REQUIRED_OUTPUT",
                    construct_id="worker:w_main.output:draft",
                    slot_name="producer",
                ),
                default_affordance_id="required_output.insert_or_bind_producer",
            ),
            _snapshot(),
        )
        assert target.worker_id == "w_main"
        assert target.target_kind == "REQUIRED_OUTPUT"


# ===========================================================================
# B2-T3: WorkerPromotionTargetResolver
# ===========================================================================


class TestB2WorkerPromotionResolver:
    def test_extracts_candidate_id(self) -> None:
        target = WorkerPromotionTargetResolver().resolve(
            _issue(
                kind="type_or_contract_ambiguity",
                target_ref="worker_promotion:cand_1",
                irs_ref=DiagnosticIRSRef(
                    construct_type="WORKER_PROMOTION",
                    construct_id="worker_promotion:cand_1",
                    slot_name="promotion_input_contract",
                ),
                default_affordance_id="worker_promotion.resolve_contract",
            ),
            _snapshot(),
        )
        assert target.target_kind == "WORKER_PROMOTION"
        assert target.subtype == "delegation_intent_contract"
        assert "WorkerPlanIR" in target.editable_artifacts


# ===========================================================================
# B2-T4: WorkerHandoffTargetResolver
# ===========================================================================


class TestB2WorkerHandoffResolver:
    def test_extracts_handoff_id(self) -> None:
        target = WorkerHandoffTargetResolver().resolve(
            _issue(
                kind="type_or_contract_ambiguity",
                target_ref="worker_handoff:h1",
                irs_ref=DiagnosticIRSRef(
                    construct_type="WORKER_HANDOFF",
                    construct_id="worker_handoff:h1",
                    slot_name="target",
                ),
                default_affordance_id="worker_handoff.specify_target",
            ),
            _snapshot(),
        )
        assert target.target_kind == "WORKER_HANDOFF"


# ===========================================================================
# B2-T5: StepTargetResolver (stub)
# ===========================================================================


class TestB2StepResolver:
    def test_stub_returns_minimal_target(self) -> None:
        target = StepTargetResolver().resolve(
            _issue(
                kind="type_or_contract_ambiguity",
                irs_ref=DiagnosticIRSRef(
                    construct_type="REQUEST_INPUT",
                    construct_id="step:st_req",
                    slot_name="value_target",
                ),
            ),
            _snapshot(),
        )
        assert target.target_kind == "REQUEST_INPUT"
        assert "WorkerStepPlanIR" in target.editable_artifacts


# ===========================================================================
# B2-T6: Required resolvers raise on unrecognized target_ref
# ===========================================================================


class TestB2ResolverStrictness:
    """B2: Required resolvers raise UnsupportedIssueError on bad target_ref."""

    def test_exception_flow_resolver_rejects_non_worker_target(self) -> None:
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = ExceptionFlowTargetResolver()
        with pytest.raises(UnsupportedIssueError, match="Cannot parse"):
            resolver.resolve(
                _issue(target_ref="not_a_worker_target"),
                _snapshot(),
            )

    def test_required_output_resolver_rejects_bad_target(self) -> None:
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = RequiredOutputTargetResolver()
        with pytest.raises(UnsupportedIssueError, match="Cannot parse"):
            resolver.resolve(
                _issue(
                    kind="missing_output_producer",
                    target_ref="garbage",
                    irs_ref=DiagnosticIRSRef(
                        construct_type="REQUIRED_OUTPUT",
                        construct_id="x",
                        slot_name="producer",
                    ),
                ),
                _snapshot(),
            )

    def test_worker_promotion_resolver_rejects_bad_target(self) -> None:
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = WorkerPromotionTargetResolver()
        with pytest.raises(UnsupportedIssueError, match="Cannot parse"):
            resolver.resolve(
                _issue(
                    kind="type_or_contract_ambiguity",
                    target_ref="bad_target",
                    irs_ref=DiagnosticIRSRef(
                        construct_type="WORKER_PROMOTION",
                        construct_id="x",
                        slot_name="promotion_input_contract",
                    ),
                ),
                _snapshot(),
            )

    def test_handoff_resolver_rejects_bad_target(self) -> None:
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = WorkerHandoffTargetResolver()
        with pytest.raises(UnsupportedIssueError, match="Cannot parse"):
            resolver.resolve(
                _issue(
                    kind="type_or_contract_ambiguity",
                    target_ref="not_a_handoff_target",
                    irs_ref=DiagnosticIRSRef(
                        construct_type="WORKER_HANDOFF",
                        construct_id="x",
                        slot_name="target",
                    ),
                ),
                _snapshot(),
            )

    def test_cross_target_mismatch_rejected_exc_on_req(self) -> None:
        """B2: exception_flow resolver rejects required_output target_ref."""
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = ExceptionFlowTargetResolver()
        with pytest.raises(UnsupportedIssueError):
            resolver.resolve(
                _issue(
                    target_ref="worker:w_main.output:draft",
                    irs_ref=DiagnosticIRSRef(
                        construct_type="EXCEPTION_FLOW",
                        construct_id="x",
                        slot_name="handler_action",
                    ),
                ),
                _snapshot(),
            )

    def test_cross_target_mismatch_rejected_req_on_exc(self) -> None:
        """B2: required_output resolver rejects exception_flow target_ref."""
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = RequiredOutputTargetResolver()
        with pytest.raises(UnsupportedIssueError):
            resolver.resolve(
                _issue(
                    kind="missing_output_producer",
                    target_ref="worker:w_main.exception_flow:exc_1",
                    irs_ref=DiagnosticIRSRef(
                        construct_type="REQUIRED_OUTPUT",
                        construct_id="x",
                        slot_name="producer",
                    ),
                ),
                _snapshot(),
            )


# ===========================================================================
# B2-T7: Empty target IDs rejected
# ===========================================================================


class TestB2EmptyTargetId:
    """B2: Required resolvers reject empty target IDs."""

    def test_exception_flow_rejects_empty_flow_id(self) -> None:
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = ExceptionFlowTargetResolver()
        with pytest.raises(UnsupportedIssueError):
            resolver.resolve(
                _issue(target_ref="worker:w_main.exception_flow:"),
                _snapshot(),
            )

    def test_required_output_rejects_empty_output_name(self) -> None:
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = RequiredOutputTargetResolver()
        with pytest.raises(UnsupportedIssueError):
            resolver.resolve(
                _issue(
                    kind="missing_output_producer",
                    target_ref="worker:w_main.output:",
                    irs_ref=DiagnosticIRSRef(
                        construct_type="REQUIRED_OUTPUT",
                        construct_id="x",
                        slot_name="producer",
                    ),
                ),
                _snapshot(),
            )

    def test_worker_handoff_rejects_empty_handoff_id(self) -> None:
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = WorkerHandoffTargetResolver()
        with pytest.raises(UnsupportedIssueError):
            resolver.resolve(
                _issue(
                    kind="type_or_contract_ambiguity",
                    target_ref="worker_handoff:",
                    irs_ref=DiagnosticIRSRef(
                        construct_type="WORKER_HANDOFF",
                        construct_id="x",
                        slot_name="target",
                    ),
                ),
                _snapshot(),
            )


# ===========================================================================
# B2-T8: Construct-type guard
# ===========================================================================


class TestB2ConstructTypeGuard:
    """B2: Required resolvers reject mismatched construct_type."""

    def test_exc_resolver_rejects_req_construct(self) -> None:
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = ExceptionFlowTargetResolver()
        with pytest.raises(UnsupportedIssueError, match="construct_type"):
            resolver.resolve(
                _issue(
                    target_ref="worker:w_main.exception_flow:exc_1",
                    irs_ref=DiagnosticIRSRef(
                        construct_type="REQUIRED_OUTPUT",
                        construct_id="x",
                        slot_name="handler_action",
                    ),
                ),
                _snapshot(),
            )

    def test_req_resolver_rejects_promotion_construct(self) -> None:
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = RequiredOutputTargetResolver()
        with pytest.raises(UnsupportedIssueError, match="construct_type"):
            resolver.resolve(
                _issue(
                    kind="missing_output_producer",
                    target_ref="worker:w_main.output:draft",
                    irs_ref=DiagnosticIRSRef(
                        construct_type="WORKER_PROMOTION",
                        construct_id="x",
                        slot_name="producer",
                    ),
                ),
                _snapshot(),
            )

    def test_handoff_resolver_rejects_exc_construct(self) -> None:
        from nl2spl.compiler.spl_editing.core.errors import UnsupportedIssueError

        resolver = WorkerHandoffTargetResolver()
        with pytest.raises(UnsupportedIssueError, match="construct_type"):
            resolver.resolve(
                _issue(
                    kind="type_or_contract_ambiguity",
                    target_ref="worker_handoff:h1",
                    irs_ref=DiagnosticIRSRef(
                        construct_type="EXCEPTION_FLOW",
                        construct_id="x",
                        slot_name="target",
                    ),
                ),
                _snapshot(),
            )
