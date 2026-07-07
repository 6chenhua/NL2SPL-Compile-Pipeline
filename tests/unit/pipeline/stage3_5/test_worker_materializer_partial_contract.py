"""Phase 0 baseline: Materializer must preserve child worker with missing contract.

These tests currently FAIL on main — the materializer rejects candidates
with no_clear_input_contract / no_clear_output_contract instead of creating
partial WorkerSpecIR skeletons.
"""

from __future__ import annotations

from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    WorkerBoundaryDecisionIR,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
    WorkerPlanMaterializer,
)
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.planner import (
    WorkerBoundaryPlanner,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candidate(
    candidate_id: str = "candidate_1",
    *,
    inputs: list[ContractFieldIR] | None = None,
    outputs: list[ContractFieldIR] | None = None,
    candidate_kind: str = "bounded_subtask",
    task_text: str = "Gather required sources.",
    purpose: str = "Retrieve sources for evidence",
    span_ids: list[str] | None = None,
) -> CandidateTaskUnitIR:
    return CandidateTaskUnitIR(
        candidate_id=candidate_id,
        candidate_kind=candidate_kind,
        task_text=task_text,
        purpose=purpose,
        possible_inputs=inputs or [],
        possible_outputs=outputs or [],
        source_span_ids=span_ids or ["s10", "s11"],
    )


def _decision(
    candidate_id: str = "candidate_1",
    *,
    decision: str = "extract_child_worker",
    boundary_kind: str = "bounded_subtask",
    reason: str = "Detected subtask boundary",
) -> WorkerBoundaryDecisionIR:
    return WorkerBoundaryDecisionIR(
        candidate_id=candidate_id,
        decision=decision,
        boundary_strength="moderate",
        boundary_kind=boundary_kind,
        reason=reason,
        rejection_reason=None,
        evidence=[],
    )


def _field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(name, "text", True, f"{name} field", source)


def _materializer() -> WorkerPlanMaterializer:
    return WorkerPlanMaterializer()


# ---------------------------------------------------------------------------
# Materializer: contract absence -> partial worker, NOT reject
# ---------------------------------------------------------------------------


class TestMaterializerPreservesPartialWorker:
    """Materializer must create child WorkerSpecIR even when contract is missing."""

    def test_preserves_child_worker_with_empty_inputs(self) -> None:
        """Candidate with empty possible_inputs should still produce a WorkerSpecIR."""
        m = _materializer()
        candidate = _candidate(
            inputs=[],
            outputs=[_field("result", "output")],
        )
        decision = _decision()

        worker_plan, warnings = m.materialize(
            candidates=[candidate],
            decisions=[decision],
            hard_fact_inputs=[_field("request")],
            hard_fact_outputs=[_field("result", "output")],
            behavior_span_ids={"s10", "s11"},
        )

        # The worker should EXIST in the plan
        child_workers = [w for w in worker_plan.workers if w.kind == "child"]
        assert len(child_workers) >= 1, (
            f"Expected at least 1 child worker, got {len(child_workers)}. "
            f"Warnings: {warnings}"
        )
        child = child_workers[0]
        # _worker_id_from_candidate strips "candidate_" prefix → "1"
        assert child.worker_id == "1"
        assert child.kind == "child"
        assert child.purpose == "Retrieve sources for evidence"
        assert child.owned_span_ids == ["s10", "s11"]

    def test_preserves_child_worker_with_empty_outputs(self) -> None:
        """Candidate with empty possible_outputs should still produce a WorkerSpecIR."""
        m = _materializer()
        candidate = _candidate(
            inputs=[_field("request")],
            outputs=[],
        )
        decision = _decision()

        worker_plan, warnings = m.materialize(
            candidates=[candidate],
            decisions=[decision],
            hard_fact_inputs=[_field("request")],
            hard_fact_outputs=[_field("result", "output")],
            behavior_span_ids={"s10", "s11"},
        )

        child_workers = [w for w in worker_plan.workers if w.kind == "child"]
        assert len(child_workers) >= 1, (
            f"Expected at least 1 child worker, got {len(child_workers)}. "
            f"Warnings: {warnings}"
        )

    def test_does_not_reject_for_missing_contract_only(self) -> None:
        """Decision must not be rewritten to keep_in_main_worker when only contract
        is missing."""
        m = _materializer()
        candidate = _candidate(inputs=[], outputs=[])
        decision = _decision()

        worker_plan, _warnings = m.materialize(
            candidates=[candidate],
            decisions=[decision],
            hard_fact_inputs=[_field("request")],
            hard_fact_outputs=[_field("result", "output")],
            behavior_span_ids={"s10", "s11"},
        )

        # The decision in the plan should NOT be keep_in_main_worker
        rejected = [
            d for d in worker_plan.rejected_candidates
            if d.candidate_id == "candidate_1"
        ]
        assert len(rejected) == 0, (
            f"Candidate should not be in rejected_candidates just for "
            f"missing contract. Rejected: {rejected}"
        )


# ---------------------------------------------------------------------------
# Risk filter: contract-missing NOT a candidate-blocking risk
# ---------------------------------------------------------------------------


class TestRiskFilterDoesNotAutoRejectContractMissing:
    """Stage 3.5 risk filter must NOT treat contract gaps as candidate-blocking."""

    def test_no_clear_input_contract_is_not_in_candidate_blocking(self) -> None:
        """no_clear_input_contract must be a promotion-incompleteness risk,
        not a candidate-blocking risk."""
        blocking = WorkerBoundaryPlanner._BLOCKING_RISKS
        assert "no_clear_input_contract" not in blocking, (
            f"no_clear_input_contract should be a PROMOTION-incompleteness risk, "
            f"not a candidate-BLOCKING risk. Currently in: {blocking}"
        )

    def test_no_clear_output_contract_is_not_in_candidate_blocking(self) -> None:
        """no_clear_output_contract must be a promotion-incompleteness risk."""
        blocking = WorkerBoundaryPlanner._BLOCKING_RISKS
        assert "no_clear_output_contract" not in blocking, (
            f"no_clear_output_contract should be a PROMOTION-incompleteness risk, "
            f"not a candidate-BLOCKING risk. Currently in: {blocking}"
        )

    def test_insufficient_semantic_boundary_still_blocking(self) -> None:
        """insufficient_semantic_boundary should remain a candidate-blocking risk."""
        blocking = WorkerBoundaryPlanner._BLOCKING_RISKS
        assert "insufficient_semantic_boundary" in blocking, (
            "insufficient_semantic_boundary MUST remain a candidate-BLOCKING risk."
        )


# ---------------------------------------------------------------------------
# Security: invented contract fields still rejected
# ---------------------------------------------------------------------------


class TestInventedContractFieldsStillRejected:
    """LLM-invented contract fields must still be rejected, even with partial contract."""

    def test_invented_input_not_in_hard_facts_still_rejected(self) -> None:
        """A candidate whose contract fields don't match hard facts must be rejected."""
        m = _materializer()
        # Candidate claims an input the LLM invented (not from hard facts)
        invented_input = _field("invented_input")
        candidate = _candidate(
            inputs=[invented_input],
            outputs=[_field("result", "output")],
        )
        decision = _decision()

        worker_plan, _warnings = m.materialize(
            candidates=[candidate],
            decisions=[decision],
            hard_fact_inputs=[_field("real_input")],   # invented_input NOT here
            hard_fact_outputs=[],                       # empty hard outs — triggers check
        )

        # Should NOT have a child worker with the invented field
        child_workers = [w for w in worker_plan.workers if w.kind == "child"]
        if child_workers:
            # If a worker exists, its input contract should NOT contain invented_input
            assert not any(
                f.name == "invented_input" for w in child_workers
                for f in w.input_contract
            ), "Invented contract field must not survive into WorkerSpecIR"
