"""R5 Runner Factory tests.

Tests for IRS v6 runner factory functions that build runners
with appropriate checker registrations based on feature flags.
"""

from __future__ import annotations

from nl2spl.compiler.irs import (
    IRSCheckContext,
    IRSCheckerRegistry,
    IRSRunner,
    build_irs_checker_registry,
    build_irs_runner,
)
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import AmbiguityInfo, SpanIR
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    WorkerPlanIR,
    WorkerSpecIR,
)


def _make_minimal_worker_spec(worker_id: str = "main") -> WorkerSpecIR:
    """Helper to create minimal WorkerSpecIR."""
    return WorkerSpecIR(
        worker_id=worker_id,
        worker_name=worker_id,
        kind="main" if worker_id == "main" else "child",
        purpose="Main workflow" if worker_id == "main" else "Child worker",
        owned_span_ids=["s1"],
        input_contract=[],
        output_contract=[],
        depends_on=[],
        constraints=[],
        boundary_kind="main_worker" if worker_id == "main" else "explicit_delegation",
        decision_evidence=[],
        reason="",
    )


def _make_minimal_candidate(candidate_id: str = "cand_1") -> CandidateTaskUnitIR:
    """Helper to create minimal CandidateTaskUnitIR."""
    return CandidateTaskUnitIR(
        candidate_id=candidate_id,
        candidate_kind="explicit_delegation",
        source_span_ids=["s1"],
        task_text="Process payment",
        purpose="Payment processing",
        possible_inputs=[],
        possible_outputs=[],
        signals=["delegation"],
        risks=["no_clear_input_contract"],
    )


def _make_minimal_worker_plan() -> WorkerPlanIR:
    """Helper to create minimal WorkerPlanIR."""
    return WorkerPlanIR(
        main_worker_id="main",
        workers=[_make_minimal_worker_spec()],
        candidates=[_make_minimal_candidate()],
        handoffs=[],
        decisions=[],
    )


class TestBuildIRSCheckerRegistry:
    """Tests for build_irs_checker_registry factory."""

    def test_default_registry_empty(self) -> None:
        """Default registry has no checkers registered."""
        registry = build_irs_checker_registry()
        assert isinstance(registry, IRSCheckerRegistry)
        # Registry should be empty by default
        assert registry.get_for_stage("stage3_5") == []

    def test_enable_worker_delegation_registers_checker(self) -> None:
        """enable_worker_delegation=True registers WorkerDelegationIRSChecker."""
        registry = build_irs_checker_registry(enable_worker_delegation=True)
        checkers = registry.get_for_stage("stage3_5")
        assert len(checkers) == 1
        checker = checkers[0]
        assert checker.checker_id == "worker_delegation"
        # Verify it's the correct checker type by checking it has the expected methods
        assert hasattr(checker, "extract_instances")
        assert hasattr(checker, "check_instance")

    def test_disable_worker_delegation_no_checker(self) -> None:
        """enable_worker_delegation=False does not register checker."""
        registry = build_irs_checker_registry(enable_worker_delegation=False)
        assert registry.get_for_stage("stage3_5") == []


class TestBuildIRSRunner:
    """Tests for build_irs_runner factory."""

    def test_default_runner_no_checkers(self) -> None:
        """Default runner has no checkers registered."""
        runner = build_irs_runner()
        assert isinstance(runner, IRSRunner)
        # Runner should have empty checker registry by default
        assert runner._registry.get_for_stage("stage3_5") == []

    def test_enable_worker_delegation_runner(self) -> None:
        """enable_worker_delegation=True creates runner with checker."""
        runner = build_irs_runner(enable_worker_delegation=True)
        checkers = runner._registry.get_for_stage("stage3_5")
        assert len(checkers) == 1
        assert checkers[0].checker_id == "worker_delegation"

    def test_runner_can_run_stage3_5_context(self) -> None:
        """Runner with worker_delegation can run stage3_5 context."""
        runner = build_irs_runner(enable_worker_delegation=True)

        # Create minimal stage3_5 context
        span = SpanIR(
            span_id="s1",
            text="Process payment for order",
            ambiguity=AmbiguityInfo(),
        )
        routes = FieldRouteIR(behavior=["s1"])
        worker_plan = _make_minimal_worker_plan()

        context = IRSCheckContext(
            stage_name="stage3_5",
            spans=(span,),
            routes=routes,
            worker_plan=worker_plan,
            metadata={"planner_enabled": True},
        )

        result = runner.run_stage("stage3_5", context)
        assert result.reports  # Should have reports
        assert result.diagnostics  # Should have diagnostics

    def test_factory_does_not_require_llm_client(self) -> None:
        """Factory functions do not require LLM client."""
        # Should not raise any errors about missing LLM client
        registry = build_irs_checker_registry(enable_worker_delegation=True)
        assert registry is not None

        runner = build_irs_runner(enable_worker_delegation=True)
        assert runner is not None

    def test_factory_does_not_modify_worker_plan(self) -> None:
        """Factory-built runner does not modify WorkerPlanIR."""
        runner = build_irs_runner(enable_worker_delegation=True)

        span = SpanIR(
            span_id="s1",
            text="Process payment",
            ambiguity=AmbiguityInfo(),
        )
        routes = FieldRouteIR(behavior=["s1"])
        worker_plan = _make_minimal_worker_plan()

        # Capture original state
        original_workers_count = len(worker_plan.workers)
        original_candidates_count = len(worker_plan.candidates)
        original_handoffs_count = len(worker_plan.handoffs)
        original_decisions_count = len(worker_plan.decisions)

        context = IRSCheckContext(
            stage_name="stage3_5",
            spans=(span,),
            routes=routes,
            worker_plan=worker_plan,
            metadata={},
        )

        runner.run_stage("stage3_5", context)

        # Verify WorkerPlanIR unchanged
        assert len(worker_plan.workers) == original_workers_count
        assert len(worker_plan.candidates) == original_candidates_count
        assert len(worker_plan.handoffs) == original_handoffs_count
        assert len(worker_plan.decisions) == original_decisions_count
