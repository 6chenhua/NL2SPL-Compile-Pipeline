"""DecisionValidatorMixin for Stage 3.5 WorkerBoundaryPlanner."""

from __future__ import annotations

from nl2spl.ir.worker_plan_ir import WorkerPlanIR


class DecisionValidatorMixin:
    """Mixin providing LLM decision validation (Layer-1)."""

    def _validate_planner_decisions(self, plan: WorkerPlanIR) -> None:
        """Validate LLM decisions against core semantic invariants.

        Acts as the first line of defense (Layer-1 validation) against
        self-contradictory or semantically-invalid LLM outputs. It checks
        that accepted and rejected candidates are logically consistent
        before the more expensive structural validation (Layer-2) runs.

        Validation rules:
        1. **Consistency check**: An accepted candidate (extract_child_worker)
           must NOT have a rejection_reason.
        2. **Evidence check**: An accepted candidate MUST have at least one
           positive signal in ``evidence``.
        3. **Risk check**: An accepted candidate must NOT carry any
           ``_BLOCKING_RISKS`` (e.g., insufficient_semantic_boundary).
        4. **Completeness check**: A rejected candidate MUST provide a
           ``rejection_reason``.
        5. **Legitimacy check**: The ``rejection_reason`` must be one of the
           pre-defined reasons in ``_REJECTION_REASONS``.

        Raises:
            ValueError: If any invariant is violated.
        """
        candidates_by_id = {
            candidate.candidate_id: candidate for candidate in plan.candidates
        }
        for decision in plan.decisions:
            if decision.decision == "extract_child_worker":
                # Rule 1: accepted candidate must not have a rejection_reason
                if decision.rejection_reason is not None:
                    raise ValueError(
                        f"Accepted candidate has rejection_reason: {decision.candidate_id}"
                    )
                # Rule 2: accepted candidate must have positive evidence
                if not decision.evidence:
                    raise ValueError(
                        f"Accepted candidate has no positive signal evidence: "
                        f"{decision.candidate_id}"
                    )
                # Rule 3: accepted candidate must not carry blocking risks
                candidate = candidates_by_id.get(decision.candidate_id)
                if candidate and set(candidate.risks) & self._BLOCKING_RISKS:
                    raise ValueError(
                        f"Accepted candidate has blocking risks: {decision.candidate_id}"
                    )
                continue

            # Rule 4: rejected candidate must state why it was rejected
            if decision.rejection_reason is None:
                raise ValueError(
                    f"Rejected candidate is missing rejection_reason: {decision.candidate_id}"
                )
            # Rule 5: rejection_reason must be a known, pre-defined reason
            if decision.rejection_reason not in self._REJECTION_REASONS:
                raise ValueError(
                    f"Unsupported rejection_reason for {decision.candidate_id}: "
                    f"{decision.rejection_reason}"
                )
