"""S6V3: Stage6VariableDeclarationPolicy tests.

Verify the deterministic admission gate:
- Input contract candidates → accepted
- Required deliverable candidates → accepted
- Explicit action output intent candidates → accepted
- Guard/control context only candidates → rejected
- Display/profile/rule text only candidates → rejected
- llm_candidate_io without evidence → rejected
- Same-name variable with explicit authority → accepted (not a blacklist)
"""

from __future__ import annotations

import inspect

from nl2spl.ir.resource_registry_ir import VariableSpec
from nl2spl.ir.variable_declaration_authority_ir import (
    DeclarationAuthorityRegistry,
    sidecar_from_adapter_fact,
    sidecar_from_candidate_io,
    sidecar_from_resource_contract_demand,
)
from nl2spl.pipeline.stages.stage6_resource_extractor.variable_declaration_policy import (
    DeclarationEvidenceView,
    PolicyResult,
    Stage6VariableDeclarationPolicy,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input_candidate(name: str = "user_request") -> VariableSpec:
    return VariableSpec(name, "text", True, "The user request.", "input")


def _make_output_candidate(name: str = "draft") -> VariableSpec:
    return VariableSpec(name, "text", True, "Draft artifact.", "output")


def _make_step_candidate(
    name: str = "identified_topics",
    data_type: str = "List[text]",
    description: str = "Identified topics.",
) -> VariableSpec:
    return VariableSpec(name, data_type, False, description, "step")


def _make_boolean_step_candidate(name: str = "sources_needed") -> VariableSpec:
    return VariableSpec(name, "boolean", False, "Whether sources are needed.", "step")


# ---------------------------------------------------------------------------
# Accepted paths
# ---------------------------------------------------------------------------


class TestS6V3AcceptedPaths:
    """Candidates with proper evidence must be accepted."""

    def test_input_from_declared_evidence_accepted(self) -> None:
        evidence = DeclarationEvidenceView(
            declared_input_names={"user_request"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        result = policy.evaluate([_make_input_candidate("user_request")])
        assert result.accepted_names == {"user_request"}
        assert len(result.rejected) == 0

    def test_output_from_declared_evidence_accepted(self) -> None:
        evidence = DeclarationEvidenceView(
            declared_output_names={"draft"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        result = policy.evaluate([_make_output_candidate("draft")])
        assert result.accepted_names == {"draft"}
        assert len(result.rejected) == 0

    def test_action_output_intent_accepted(self) -> None:
        evidence = DeclarationEvidenceView(
            action_output_names={"identified_topics"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        result = policy.evaluate(
            [_make_step_candidate("identified_topics", "List[text]")]
        )
        assert result.accepted_names == {"identified_topics"}
        assert len(result.rejected) == 0

    def test_response_target_accepted(self) -> None:
        evidence = DeclarationEvidenceView(
            response_target_names={"api_result"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        result = policy.evaluate(
            [VariableSpec("api_result", "text", False, "API result.", "api")]
        )
        assert result.accepted_names == {"api_result"}
        assert len(result.rejected) == 0

    def test_registry_admissible_accepted(self) -> None:
        reg = DeclarationAuthorityRegistry()
        reg.register(sidecar_from_adapter_fact("user_request", "text"))
        evidence = DeclarationEvidenceView()
        policy = Stage6VariableDeclarationPolicy(evidence, reg)
        result = policy.evaluate([_make_input_candidate("user_request")])
        assert result.accepted_names == {"user_request"}

    def test_resource_contract_demand_accepted(self) -> None:
        reg = DeclarationAuthorityRegistry()
        reg.register(
            sidecar_from_resource_contract_demand("draft", "text", "rcd_001")
        )
        evidence = DeclarationEvidenceView()
        policy = Stage6VariableDeclarationPolicy(evidence, reg)
        result = policy.evaluate([_make_output_candidate("draft")])
        assert result.accepted_names == {"draft"}


# ---------------------------------------------------------------------------
# Rejected paths
# ---------------------------------------------------------------------------


class TestS6V3RejectedPaths:
    """Candidates without proper evidence must be rejected."""

    def test_step_variable_without_output_authority_rejected(self) -> None:
        """Raw source='step' from LLM is not declaration authority."""
        evidence = DeclarationEvidenceView(
            declared_input_names={"known_input"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        result = policy.evaluate(
            [_make_step_candidate("communication_type", "text",
                                  "Type of communication determined.")]
        )
        assert result.accepted_names == set()
        assert result.rejected_names == {"communication_type"}
        assert result.rejected[0].rejection_reason == "unbacked_step_variable"

    def test_boolean_predicate_from_control_context_rejected(self) -> None:
        evidence = DeclarationEvidenceView(
            read_only_context_terms={"sources", "needed", "available",
                                     "whether", "enough", "information",
                                     "revision"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        result = policy.evaluate([_make_boolean_step_candidate("sources_needed")])
        assert result.accepted_names == set()
        assert result.rejected_names == {"sources_needed"}
        audit = result.rejected[0]
        assert audit.rejection_reason == (
            "predicate_as_variable_without_declaration_authority"
        )

    def test_candidate_io_in_registry_rejected(self) -> None:
        reg = DeclarationAuthorityRegistry()
        reg.register(sidecar_from_candidate_io("sources_needed", "boolean"))
        evidence = DeclarationEvidenceView()
        policy = Stage6VariableDeclarationPolicy(evidence, reg)
        result = policy.evaluate([_make_boolean_step_candidate("sources_needed")])
        assert result.accepted_names == set()
        assert result.rejected_names == {"sources_needed"}
        audit = result.rejected[0]
        assert audit.rejection_reason == "inadmissible_candidate_io"

    def test_control_clause_only_rejected(self) -> None:
        """Non-boolean variable from control context still rejected."""
        evidence = DeclarationEvidenceView(
            read_only_context_terms={"threshold", "exceeded", "check"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        result = policy.evaluate(
            [VariableSpec("threshold_exceeded", "text", False,
                          "Whether threshold exceeded.", "step")]
        )
        assert result.accepted_names == set()
        audit = result.rejected[0]
        assert audit.rejection_reason == "control_clause_only"

    def test_no_evidence_at_all_rejected(self) -> None:
        # Provide at least one evidence field to trigger strict mode
        evidence = DeclarationEvidenceView(
            declared_input_names={"known_input"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        result = policy.evaluate(
            [VariableSpec("mystery_var", "text", False, "???", "api")]
        )
        assert result.accepted_names == set()
        audit = result.rejected[0]
        # source="api" bypasses the "unbacked_step_variable" check
        assert audit.rejection_reason == "missing_declaration_authority"


# ---------------------------------------------------------------------------
# Mixed batch
# ---------------------------------------------------------------------------


class TestS6V3MixedBatch:
    """A mixed batch should correctly split accepted/rejected."""

    def test_mixed_candidates(self) -> None:
        evidence = DeclarationEvidenceView(
            declared_input_names={"user_request"},
            declared_output_names={"draft"},
            read_only_context_terms={"sources", "needed"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        candidates = [
            _make_input_candidate("user_request"),           # → accepted (declared input)
            _make_output_candidate("draft"),                 # → accepted (declared output)
            _make_boolean_step_candidate("sources_needed"),  # → rejected (read-only contamination + boolean)
            _make_step_candidate("random_step"),             # → accepted (step, no contamination)
        ]
        result = policy.evaluate(candidates)
        assert result.accepted_names == {"user_request", "draft"}
        assert result.rejected_names == {"sources_needed", "random_step"}
        assert len(result.accepted) == 2
        assert len(result.rejected) == 2

    def test_empty_candidates(self) -> None:
        evidence = DeclarationEvidenceView()
        policy = Stage6VariableDeclarationPolicy(evidence)
        result = policy.evaluate([])
        assert result.accepted == []
        assert result.rejected == []

    def test_all_accepted(self) -> None:
        evidence = DeclarationEvidenceView(
            declared_input_names={"a", "b", "c"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        candidates = [
            VariableSpec("a", "text", True, "", "input"),
            VariableSpec("b", "text", True, "", "input"),
            VariableSpec("c", "text", True, "", "input"),
        ]
        result = policy.evaluate(candidates)
        assert len(result.accepted) == 3
        assert len(result.rejected) == 0


# ---------------------------------------------------------------------------
# Not a blacklist — same name, different authority
# ---------------------------------------------------------------------------


class TestS6V3NotABlacklist:
    """Prove the policy does not use variable-name blacklists."""

    def test_same_name_accepted_with_authority(self) -> None:
        """sources_needed is NOT blacklisted — it's accepted if it has
        declaration authority."""
        evidence = DeclarationEvidenceView(
            declared_input_names={"sources_needed"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        result = policy.evaluate([_make_boolean_step_candidate("sources_needed")])
        assert result.accepted_names == {"sources_needed"}, (
            "S6V3: sources_needed WITH declaration authority MUST be "
            "accepted. This proves we are not blacklisting by name."
        )

    def test_no_variable_name_blacklist_in_code(self) -> None:
        """Static check: the policy source does not contain demo variable
        names as hardcoded blacklist entries."""
        from nl2spl.pipeline.stages.stage6_resource_extractor import (
            variable_declaration_policy,
        )

        src = inspect.getsource(variable_declaration_policy)
        demo_names = [
            "enough_required_information",
            "user_asks_for_revision",
            "sources_needed",
            "sources_available",
        ]
        for name in demo_names:
            assert name not in src, (
                f"S6V3: policy source must not contain '{name}' as a "
                f"hardcoded blacklist entry."
            )


# ---------------------------------------------------------------------------
# Audit record quality
# ---------------------------------------------------------------------------


class TestS6V3AuditRecords:
    """Every rejected candidate must have a structured rejection reason."""

    def test_every_rejection_has_reason(self) -> None:
        # Provide evidence + read-only context to trigger strict mode
        evidence = DeclarationEvidenceView(
            declared_input_names={"known_input"},
            read_only_context_terms={"threshold", "exceeded", "check"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        candidates = [
            # Step variable with read-only contamination → rejected
            VariableSpec("threshold_exceeded", "boolean", False,
                         "Whether threshold exceeded.", "step"),
            # Non-step variable without evidence → rejected
            VariableSpec("mystery_var", "text", False, "???", "api"),
        ]
        result = policy.evaluate(candidates)
        assert len(result.rejected) == 2
        for audit in result.rejected:
            assert audit.rejection_reason is not None, (
                f"Rejected variable {audit.variable_name} must have "
                f"a rejection_reason."
            )
            assert audit.reason != "", (
                f"Rejected variable {audit.variable_name} must have "
                f"a human-readable reason."
            )

    def test_rejection_reason_is_valid_enum(self) -> None:
        from nl2spl.pipeline.stages.stage6_resource_extractor.variable_declaration_policy import (
            REJECTION_DESCRIPTIONS,
        )
        valid_reasons = set(REJECTION_DESCRIPTIONS.keys())
        # Use read-only context + boolean step → should be rejected
        evidence = DeclarationEvidenceView(
            declared_input_names={"known_input"},
            read_only_context_terms={"something", "flag"},
        )
        policy = Stage6VariableDeclarationPolicy(evidence)
        result = policy.evaluate([
            VariableSpec("some_flag", "boolean", False,
                         "Whether something flag is set.", "step"),
            VariableSpec("unknown_api", "text", False, "???", "api"),
        ])
        for audit in result.rejected:
            assert audit.rejection_reason in valid_reasons, (
                f"Rejection reason {audit.rejection_reason!r} is not a "
                f"known RejectionReason."
            )


# ---------------------------------------------------------------------------
# PolicyResult properties
# ---------------------------------------------------------------------------


class TestS6V3PolicyResult:
    """PolicyResult convenience properties."""

    def test_accepted_names(self) -> None:
        result = PolicyResult(
            accepted=[
                VariableSpec("a", "text", True, "", "input"),
                VariableSpec("b", "text", True, "", "output"),
            ],
            rejected=[],
        )
        assert result.accepted_names == {"a", "b"}

    def test_rejected_names(self) -> None:
        from nl2spl.pipeline.stages.stage6_resource_extractor.variable_declaration_policy import (
            VariableCandidateAudit,
        )
        result = PolicyResult(
            accepted=[],
            rejected=[
                VariableCandidateAudit(
                    variable_name="x", accepted=False,
                    reason="test", rejection_reason="unbacked_step_variable",
                ),
            ],
        )
        assert result.rejected_names == {"x"}
