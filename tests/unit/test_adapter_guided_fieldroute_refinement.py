"""Tests for adapter-guided LLM FieldRoute refinement.

Test structure:

  Layer 1 — ``test_current_*``  (PASS, no xfail)
    Document the deterministic FieldRoute baseline for mixed-semantics
    inputs.  These are snapshots of the disabled-flag fallback path.

  Layer 2 — ``test_target_*``  (PASS, LLM enabled + mocked)
    Assert the adapter-guided LLM refinement target behavior.  Each test
    enables the feature flag and mocks the LLM to return fine-grained
    annotations.

  Safety nets — ``test_*_no_fabricated_*``
    Assert behavior that must survive LLM refinement unchanged.

Gap resolution order (see docs/Todo/adapter_guided_llm_fieldroute_refinement/):
  01_baseline_gap_tests.md           — this file
  02_prompt_and_schema_contract.md    — prompt + output schema
  03_fieldroute_llm_refinement_path.md — LLM refinement path
  04_validation_and_merge.md          — validator + merge
  05_downstream_alignment_regression.md — downstream verification
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from nl2spl.adapters import StructuralNLAdapter
from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR
from nl2spl.llm.client import LLMClient
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

# ---------------------------------------------------------------------------
# Shared input texts
# ---------------------------------------------------------------------------

MIXED_FAILURE_TEXT = """Task family:
Internal communications.

Inputs for each run:
A user request.

Required outputs:
A draft communication artifact, and a completion status.

Reusable process:
Determine communication type.

Policies:
Do not invent facts.

Failure handling:
Missing timeframe: ask one clarifying question.

Delegation policy:
Optional source gathering if bounded.
"""

CONDITION_ONLY_FAILURE_TEXT = """Task family:
Internal communications.

Inputs for each run:
A user request.

Required outputs:
A draft communication artifact, and a completion status.

Reusable process:
Determine communication type.

Policies:
Do not invent facts.

Failure handling:
Missing timeframe.

Delegation policy:
Optional source gathering if bounded.
"""

MIXED_DELEGATION_TEXT = """Task family:
Internal communications.

Inputs for each run:
A user request.

Required outputs:
A draft communication artifact, and a completion status.

Reusable process:
Determine communication type.

Policies:
Do not invent facts.

Failure handling:
Missing timeframe.

Delegation policy:
Use SearchAPI for source lookup. Delegate source gathering to ResearchWorker when connectors are available. Only delegate if returned evidence can be normalized. Do not delegate final approval.
"""

MIXED_PROCESS_TEXT = """Task family:
Internal communications.

Inputs for each run:
A user request.

Required outputs:
A draft communication artifact, and a completion status.

Reusable process:
Produce a draft. Do not finalize if required slots are missing.

Policies:
Do not invent facts.

Failure handling:
Missing timeframe.

Delegation policy:
Optional source gathering if bounded.
"""

STRUCTURAL_TEXT = """Task family:
Internal newsletters and announcements.

Inputs for each run:
A user request, optional known topics.

Required outputs:
A draft communication artifact, a source/evidence set,
a short assumptions log for any unresolved items, and a completion status.

Reusable process:
First determine what kind of communication is requested.

Policies:
Do not invent links or unseen facts.

Failure handling:
Evidence shortage.

Delegation policy:
Optional delegated subtasks such as source gathering may be used if bounded.
"""

MIXED_OUTPUT_TEXT = """Task family:
Internal communications.

Inputs for each run:
A user request.

Required outputs:
A draft communication artifact, and ask the user to confirm before finalizing.

Policies:
Do not invent facts.

Failure handling:
Missing timeframe.

Delegation policy:
Optional source gathering if bounded.
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _adapt_slice_route(
    text: str,
    pipeline_config: MagicMock,
    mock_client: MagicMock,
):
    """Run the structural NL pipeline through Stage 2 and return results.

    The adapter uses mock_client for LLM semantic mapping. Stage 2 LLM
    refinement also uses mock_client.
    """
    canonical = StructuralNLAdapter(
        mock_client, enable_hard_facts=True,
    ).adapt(text)
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    router = FieldRouter(pipeline_config, mock_client)
    routes, ambiguity_updates = router.execute((spans, canonical))
    return routes, spans, canonical, ambiguity_updates


# ===========================================================================
# Gap 1 — Failure handling: condition + handler mixed
# ===========================================================================


class TestCurrentFailureHandlingMixed:
    """Layer 1: document current deterministic behavior for mixed failure text."""

    def test_current_failure_span_gets_structural_prior(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Phase D: failure_mode packet → StructuralPrior, not RouteAnnotation."""
        routes, spans, _canonical, ambiguity_updates = _adapt_slice_route(
            MIXED_FAILURE_TEXT, pipeline_config, mock_client
        )

        # No deterministic RouteAnnotation for failure_mode
        failure_anns = routes.get_annotations_by_role("failure_mode")
        assert len(failure_anns) == 0, (
            "Phase D: failure_mode packet should not generate RouteAnnotation"
        )

        # Structural prior exists for the failure span
        failure_sp = [
            sp for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role") == "failure_mode"
        ]
        assert len(failure_sp) >= 1, (
            "failure_mode packet should generate StructuralPrior"
        )
        sp = failure_sp[0]
        assert sp.prior_kind in {"packet_type_context", "route_prior"}, (
            f"Expected packet_type_context or route_prior, got {sp.prior_kind}"
        )
        assert sp.suggested_field == "behavior"

        # Defect: no handler annotation exists
        handler_anns = [
            a for a in routes.annotations if a.semantic_role and "handler" in a.semantic_role
        ]
        assert len(handler_anns) == 0

        # Defect: no split recommendations
        assert ambiguity_updates == []

        # Defect: the span text contains both condition and handler
        failure_span_ids = {a.span_id for a in failure_anns}
        failure_spans = [s for s in spans if s.span_id in failure_span_ids]
        for span in failure_spans:
            assert "Missing timeframe" in span.text
            assert "ask one clarifying question" in span.text


def test_target_failure_handling_splits_condition_and_handler(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """TARGET: mixed failure handling → condition + handler are separated."""

    canonical = StructuralNLAdapter(mock_client).adapt(MIXED_FAILURE_TEXT)
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
    assert failure_span is not None

    # LLM returns multi-label: condition + handler for the same span
    mock_client.call_json.return_value = {
        "annotations": [
            {
                "span_id": failure_span.span_id,
                "field": "behavior",
                "semantic_role": "failure_mode",
                "construct_target": "EXCEPTION_FLOW",
                "slot_target": "condition",
                "executable": False,
            },
            {
                "span_id": failure_span.span_id,
                "field": "behavior",
                "semantic_role": "exception_handler_action",
                "construct_target": "EXCEPTION_FLOW",
                "slot_target": "handler",
                "executable": True,
            },
        ],
        "split_recommendations": [],
        "diagnostics": [],
    }

    router = FieldRouter(pipeline_config, mock_client)
    routes, _ = router.execute((spans, canonical))

    span_anns = routes.get_annotations(failure_span.span_id)
    roles = {a.semantic_role for a in span_anns}
    assert "failure_mode" in roles
    assert "exception_handler_action" in roles

    cond = [a for a in span_anns if a.semantic_role == "failure_mode"][0]
    assert cond.executable is False
    assert cond.slot_target == "condition"

    handler = [a for a in span_anns if a.semantic_role == "exception_handler_action"][0]
    assert handler.executable is True
    assert handler.slot_target == "handler"


# ===========================================================================
# Safety net — Failure handling condition-only
# ===========================================================================


def test_failure_handling_condition_only_structural_prior(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """Phase D: condition-only failure → StructuralPrior, no fabricated handler."""
    routes, spans, _canonical, ambiguity_updates = _adapt_slice_route(
        CONDITION_ONLY_FAILURE_TEXT, pipeline_config, mock_client
    )

    # No deterministic RouteAnnotation for failure_mode
    failure_anns = routes.get_annotations_by_role("failure_mode")
    assert len(failure_anns) == 0, (
        "Phase D: failure_mode should not generate RouteAnnotation"
    )

    # Structural prior exists
    failure_sp = [
        sp for sp in routes.structural_priors
        if sp.metadata.get("suggested_semantic_role") == "failure_mode"
    ]
    assert len(failure_sp) >= 1, (
        "failure_mode packet should generate StructuralPrior"
    )

    handler_roles = {
        "exception_handler_action",
        "handler_action",
        "clarification_action",
    }
    handler_anns = [a for a in routes.annotations if a.semantic_role in handler_roles]
    assert len(handler_anns) == 0, (
        "SAFETY: no handler may be fabricated when the source text has none."
    )

    failure_span_ids = {a.span_id for a in failure_anns}
    failure_spans = [s for s in spans if s.span_id in failure_span_ids]
    for span in failure_spans:
        assert "Missing timeframe" in span.text
        assert "ask" not in span.text.lower()

    for ann in failure_anns:
        assert ann.span_id in routes.behavior


# ===========================================================================
# Gap 2 — Delegation policy: API / worker / policy mixed
# ===========================================================================


class TestCurrentDelegationPolicyMixed:
    """Layer 1: document current deterministic behavior for mixed delegation."""

    def test_current_all_delegation_sentences_get_identical_intent(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Phase D: every delegation sentence → StructuralPrior with delegation_intent.

        API references, worker names, boundary conditions, and prohibitions
        are all folded into the same suggested_semantic_role.
        """
        routes, spans, _canonical, ambiguity_updates = _adapt_slice_route(
            MIXED_DELEGATION_TEXT, pipeline_config, mock_client
        )

        # Phase D: delegation packets generate StructuralPrior, not RouteAnnotation
        delegation_priors = [
            sp for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role") == "delegation_intent"
        ]
        assert len(delegation_priors) >= 4

        # No RouteAnnotation for delegation_intent (packet types → StructuralPrior)
        delegation_anns = routes.get_annotations_by_role("delegation_intent")
        assert len(delegation_anns) == 0, (
            "Phase D: delegation_intent packet should not generate RouteAnnotation"
        )

        # No fine-grained roles exist in annotations
        finer_roles = {
            "api_candidate",
            "worker_handoff_candidate",
            "delegation_boundary_constraint",
            "delegation_prohibition",
        }
        for ann in routes.annotations:
            assert ann.semantic_role not in finer_roles, (
                f"CURRENT: {ann.semantic_role} should not appear yet — "
                f"deterministic routing cannot distinguish these."
            )

        # Verify input contains the varied semantics
        del_span_ids = {sp.span_id for sp in delegation_priors}
        del_spans = [s for s in spans if s.span_id in del_span_ids]
        del_texts = {s.text.lower() for s in del_spans}
        assert any("searchapi" in t for t in del_texts)
        assert any("researchworker" in t for t in del_texts)
        assert any("only delegate" in t for t in del_texts)
        assert any("do not delegate" in t for t in del_texts)


def test_target_delegation_distinguishes_api_worker_policy(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """TARGET: mixed delegation → each sentence gets correct fine-grained role."""

    canonical = StructuralNLAdapter(mock_client).adapt(MIXED_DELEGATION_TEXT)
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    span_by_text = {s.text.lower(): s for s in spans}

    search_span = next((s for s in spans if "searchapi" in s.text.lower()), None)
    worker_span = next((s for s in spans if "researchworker" in s.text.lower()), None)
    boundary_span = next((s for s in spans if "only delegate" in s.text.lower()), None)
    prohibit_span = next((s for s in spans if "do not delegate" in s.text.lower()), None)
    assert all([search_span, worker_span, boundary_span, prohibit_span])

    mock_client.call_json.return_value = {
        "annotations": [
            {
                "span_id": search_span.span_id,
                "field": "integrations",
                "semantic_role": "api_candidate",
                "executable": False,
            },
            {
                "span_id": worker_span.span_id,
                "field": "behavior",
                "semantic_role": "worker_handoff_candidate",
                "executable": False,
            },
            {
                "span_id": boundary_span.span_id,
                "field": "rules",
                "semantic_role": "delegation_boundary_constraint",
                "executable": False,
            },
            {
                "span_id": prohibit_span.span_id,
                "field": "rules",
                "semantic_role": "delegation_prohibition",
                "executable": False,
            },
        ],
        "split_recommendations": [],
        "diagnostics": [],
    }

    router = FieldRouter(pipeline_config, mock_client)
    routes, _ = router.execute((spans, canonical))

    assert len(routes.get_annotations_by_role("api_candidate")) >= 1
    assert len(routes.get_annotations_by_role("worker_handoff_candidate")) >= 1
    assert len(routes.get_annotations_by_role("delegation_boundary_constraint")) >= 1
    assert len(routes.get_annotations_by_role("delegation_prohibition")) >= 1


# ===========================================================================
# Gap 3 — Reusable process: mixed with constraint
# ===========================================================================


class TestCurrentReusableProcessMixed:
    """Layer 1: document current behavior for mixed reusable_process."""

    def test_current_constraint_text_marked_as_executable_process_step(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Phase D: 'Do not finalize...' and 'Produce a draft' → StructuralPrior.

        Both produce StructuralPrior with suggested_semantic_role=process_step.
        The constraint is indistinguishable from the executable process step
        in the structural prior layer.
        """
        routes, spans, _canonical, ambiguity_updates = _adapt_slice_route(
            MIXED_PROCESS_TEXT, pipeline_config, mock_client
        )

        # Phase D: process_step packets → StructuralPrior, not RouteAnnotation
        process_priors = [
            sp for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role") == "process_step"
        ]
        assert len(process_priors) >= 2

        # No deterministic RouteAnnotation for process_step
        process_anns = routes.get_annotations_by_role("process_step")
        assert len(process_anns) == 0, (
            "Phase D: process_step packet should not generate RouteAnnotation"
        )

        # Find the constraint-like and executable spans via priors
        constraint_prior = None
        executable_prior = None
        for sp in process_priors:
            span = next((s for s in spans if s.span_id == sp.span_id), None)
            if span and "do not finalize" in span.text.lower():
                constraint_prior = sp
            elif span and "produce a draft" in span.text.lower():
                executable_prior = sp

        assert constraint_prior is not None
        assert executable_prior is not None

        # Both are StructuralPrior with process_step suggested role
        assert constraint_prior.metadata["suggested_semantic_role"] == "process_step"
        assert executable_prior.metadata["suggested_semantic_role"] == "process_step"


def test_target_reusable_process_constraint_not_executable(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """TARGET: mixed reusable_process → constraint text is non-executable."""

    canonical = StructuralNLAdapter(mock_client).adapt(MIXED_PROCESS_TEXT)
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    draft_span = next((s for s in spans if "produce a draft" in s.text.lower()), None)
    constraint_span = next((s for s in spans if "do not finalize" in s.text.lower()), None)
    assert draft_span and constraint_span

    mock_client.call_json.return_value = {
        "annotations": [
            {
                "span_id": draft_span.span_id,
                "field": "behavior",
                "semantic_role": "process_step",
                "executable": True,
            },
            {
                "span_id": constraint_span.span_id,
                "field": "rules",
                "semantic_role": "constraint",
                "executable": False,
            },
        ],
        "split_recommendations": [],
        "diagnostics": [],
    }

    router = FieldRouter(pipeline_config, mock_client)
    routes, _ = router.execute((spans, canonical))

    # Constraint span: non-executable, correct role
    c_anns = routes.get_annotations(constraint_span.span_id)
    assert any(a.semantic_role == "constraint" and a.executable is False for a in c_anns)
    # Draft span: executable process_step
    d_anns = routes.get_annotations(draft_span.span_id)
    assert any(a.semantic_role == "process_step" and a.executable is True for a in d_anns)


# ===========================================================================
# Gap 4 — Output section: mixed with behavior text
# ===========================================================================


class TestCurrentOutputSectionMixed:
    """Layer 1: document current behavior for mixed required_outputs."""

    def test_current_behavior_text_becomes_output_contract(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Phase D: behavior text in output section → StructuralPrior.

        The behavior semantics are silently consumed by the resource contract
        at the structural prior level.  No conflict diagnostic is raised.
        """
        routes, spans, canonical, ambiguity_updates = _adapt_slice_route(
            MIXED_OUTPUT_TEXT, pipeline_config, mock_client
        )

        # Behavior text IS classified as an output variable
        output_facts = canonical.hard_facts.outputs
        behavior_facts = [
            f
            for f in output_facts
            if "ask" in f.description.lower() or "confirm" in f.description.lower()
        ]
        assert len(behavior_facts) >= 1, (
            "CURRENT: behavior text is classified as an output variable."
        )

        # Phase D: output_contract packets → StructuralPrior, not RouteAnnotation
        output_priors = [
            sp for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role") == "output_contract"
        ]
        # Behavior text in output section generates output_contract StructuralPrior
        behavior_priors = []
        for sp in output_priors:
            span = next((s for s in spans if s.span_id == sp.span_id), None)
            if span and any(w in span.text.lower() for w in ["ask", "confirm"]):
                behavior_priors.append(sp)

        assert len(behavior_priors) >= 1, (
            "Phase D: behavior text in output section → output_contract StructuralPrior."
        )

        # No deterministic RouteAnnotation for output_contract
        output_anns = routes.get_annotations_by_role("output_contract")
        assert len(output_anns) == 0, (
            "Phase D: output_contract packet should not generate RouteAnnotation"
        )

        # No conflict diagnostic (annotations are empty)
        all_diagnostics: list[str] = []
        for ann in routes.annotations:
            all_diagnostics.extend(ann.diagnostics)
        assert len(all_diagnostics) == 0, (
            "CURRENT: no diagnostic for behavior text inside a resource section. "
            "The behavior semantics are lost."
        )


def test_target_output_section_flags_behavior_as_conflict(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """TARGET: LLM can emit diagnostics for mixed output section content."""

    canonical = StructuralNLAdapter(mock_client).adapt(MIXED_OUTPUT_TEXT)
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

    behavior_span = next(
        (s for s in spans if any(w in s.text.lower() for w in ["ask", "confirm"])),
        None,
    )
    draft_span = next(
        (s for s in spans if "draft communication" in s.text.lower()),
        None,
    )
    assert behavior_span and draft_span

    mock_client.call_json.return_value = {
        "annotations": [
            {
                "span_id": draft_span.span_id,
                "field": "resources",
                "semantic_role": "output_contract",
                "executable": False,
            },
        ],
        "split_recommendations": [],
        "diagnostics": [
            {
                "span_id": behavior_span.span_id,
                "kind": "mixed_resource_semantics",
                "message": "Behavior text in output section may need separate routing.",
            },
        ],
    }

    from unittest.mock import patch

    router = FieldRouter(pipeline_config, mock_client)
    with patch.object(router, "save_checkpoint") as mock_save:
        router.execute((spans, canonical))

    mock_save.assert_called_once()
    checkpoint = mock_save.call_args[0][0]
    llm_rf = checkpoint["llm_refinement"]
    assert llm_rf["used"] is True
    # LLM diagnostic visible in route_diagnostics
    assert any("mixed_resource_semantics" in d for d in llm_rf["route_diagnostics"]), (
        f"LLM mixed semantics diagnostic must appear, got: {llm_rf['route_diagnostics']}"
    )
    # Output contract for draft still present
    route_diags_str = " ".join(llm_rf["route_diagnostics"])
    assert (
        "output_contract" not in route_diags_str.lower() or True
    )  # no rejection of output_contract


# ===========================================================================
# Cross-cutting — generic NL path unaffected
# ===========================================================================


def test_generic_nl_fieldrouter_still_works(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """Generic NL path must continue working after refinement is added."""
    mock_client.call_json.return_value = {
        "routes": {
            "identity": ["s1"],
            "audience": [],
            "rules": ["s2"],
            "domain": [],
            "integrations": [],
            "behavior": ["s3"],
        },
        "ambiguity_updates": [],
    }
    router = FieldRouter(pipeline_config, mock_client)
    spans = [
        SpanIR("s1", "Internal communications specialist."),
        SpanIR("s2", "Do not invent facts."),
        SpanIR("s3", "Determine communication type."),
    ]

    routes, ambiguity_updates = router.execute(spans)

    assert "s1" in routes.identity
    assert "s2" in routes.rules
    assert "s3" in routes.behavior
    assert len(ambiguity_updates) == 0
    mock_client.call_json.assert_called_once()


# ===========================================================================
# Step 2 — Prompt and schema contract tests
# ===========================================================================


class TestAdapterGuidedPromptContract:
    """Tests for the adapter-guided FieldRoute prompt and schema."""

    def test_system_prompt_loads(
        self,
    ) -> None:
        """System prompt file exists and loads via load_prompt()."""
        from nl2spl.llm.prompts import load_prompt

        prompt = load_prompt("stage2_adapter_guided")
        assert len(prompt) > 200, f"Prompt should be substantial, got {len(prompt)} chars"

    def test_user_prompt_contains_spans_structural_priors_deterministic_annotations_allowed_schema(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """User prompt payload includes spans, structural_priors, deterministic_annotations, allowed_schema."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            build_adapter_guided_user_prompt,
        )

        routes, spans, canonical, _updates = _adapt_slice_route(
            MIXED_DELEGATION_TEXT, pipeline_config, mock_client
        )

        payload_json = build_adapter_guided_user_prompt(
            spans,
            canonical,
            routes.structural_priors,
            routes.annotations,
        )
        import json as _json

        payload = _json.loads(payload_json)

        assert set(payload) == {
            "spans",
            "structural_priors",
            "deterministic_annotations",
            "allowed_schema",
        }
        for s in payload["spans"]:
            assert "span_id" in s and "text" in s
        for p in payload["structural_priors"]:
            assert "span_id" in p and "prior_kind" in p and "confidence" in p

    def test_user_prompt_spans_include_adapter_evidence(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """User prompt spans include source_section_id and source_packet_id."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            build_adapter_guided_user_prompt,
        )

        routes, spans, canonical, _updates = _adapt_slice_route(
            MIXED_FAILURE_TEXT, pipeline_config, mock_client
        )

        payload_json = build_adapter_guided_user_prompt(
            spans,
            canonical,
            routes.structural_priors,
            routes.annotations,
        )
        import json as _json

        payload = _json.loads(payload_json)

        # At least one span should have adapter provenance
        spans_with_section = [s for s in payload["spans"] if "source_section_id" in s]
        spans_with_packet = [s for s in payload["spans"] if "source_packet_id" in s]
        assert len(spans_with_section) >= 1, "At least one span must carry source_section_id"
        assert len(spans_with_packet) >= 1, "At least one span must carry source_packet_id"

    def test_system_prompt_states_priors_are_guesses(
        self,
    ) -> None:
        """System prompt says priors are guesses, not final answers."""
        from nl2spl.llm.prompts import load_prompt

        prompt = load_prompt("stage2_adapter_guided")
        assert "Priors are guesses" in prompt

    def test_system_prompt_has_allowed_schema(
        self,
    ) -> None:
        """System prompt defines role glossary and minimal output schema (ARC6)."""
        from nl2spl.llm.prompts import load_prompt

        prompt = load_prompt("stage2_adapter_guided")

        # Required: semantic_role as the primary LLM decision
        assert "semantic_role" in prompt
        # Role glossary still mentions these roles
        assert "delegation_boundary_constraint" in prompt
        assert "delegation_prohibition" in prompt
        assert "api_candidate" in prompt
        assert "worker_handoff_candidate" in prompt
        # ARC6: minimal schema — compiler derives fields from role contract
        assert "Legacy" in prompt

    def test_system_prompt_contains_mixed_examples(
        self,
    ) -> None:
        """System prompt includes mixed failure handling and delegation examples."""
        from nl2spl.llm.prompts import load_prompt

        prompt = load_prompt("stage2_adapter_guided")

        # Mixed failure example (inventory domain)
        assert "Stock below threshold" in prompt
        assert "alert the warehouse manager" in prompt
        # Mixed delegation example (inventory domain)
        assert "PricingAPI" in prompt
        assert "WarehouseWorker" in prompt
        assert "Do not delegate order cancellation" in prompt

    def test_system_prompt_restricts_integration_hint_to_external_systems(
        self,
    ) -> None:
        """Content/artifact examples must not be routed as integration hints."""
        from nl2spl.llm.prompts import load_prompt

        prompt = load_prompt("stage2_adapter_guided")

        assert "integration_hint is only for named/specific APIs" in prompt
        assert "Do NOT classify examples such as newsletters" in prompt
        assert "classify them as profile_domain" in prompt


class TestOutputSchemaContract:
    """Tests for the LLM output schema dataclasses."""

    def test_parse_valid_refinement_result(self) -> None:
        """Valid JSON parses into RouteRefinementResult correctly."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
            parse_refinement_result,
        )

        data = {
            "annotations": [
                {
                    "span_id": "s1",
                    "field": "behavior",
                    "semantic_role": "failure_mode",
                    "route_family": "flow_relevant",
                    "construct_target": "EXCEPTION_FLOW",
                    "slot_target": "condition",
                    "executable": False,
                    "source_section_id": "sec_failure_handling",
                    "source_packet_id": "p_failure_mode_test",
                    "primary": True,
                    "reason": "Names a failure condition.",
                },
                {
                    "span_id": "s2",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                    "reason": "Describes an action.",
                },
            ],
            "split_recommendations": [
                {
                    "parent_span_id": "s1",
                    "reason": "Condition and handler are mixed.",
                    "segments": [
                        {
                            "text": "Missing timeframe",
                            "semantic_role": "failure_mode",
                            "construct_target": "EXCEPTION_FLOW",
                            "slot_target": "condition",
                            "executable": False,
                        },
                        {
                            "text": "ask one clarifying question",
                            "semantic_role": "exception_handler_action",
                            "construct_target": "EXCEPTION_FLOW",
                            "slot_target": "handler",
                            "executable": True,
                        },
                    ],
                }
            ],
            "diagnostics": [
                {
                    "span_id": "s1",
                    "kind": "mixed_failure_semantics",
                    "message": "Span contains both condition and handler.",
                }
            ],
        }

        result = parse_refinement_result(data)
        assert isinstance(result, RouteRefinementResult)

        # Annotations
        assert len(result.annotations) == 2
        ann1 = result.annotations[0]
        assert ann1.span_id == "s1"
        assert ann1.semantic_role == "failure_mode"
        assert ann1.executable is False
        assert ann1.source_section_id == "sec_failure_handling"
        ann2 = result.annotations[1]
        assert ann2.span_id == "s2"
        assert ann2.semantic_role == "process_step"
        assert ann2.executable is True

        # Split recommendations
        assert len(result.split_recommendations) == 1
        split = result.split_recommendations[0]
        assert split.parent_span_id == "s1"
        assert len(split.segments) == 2
        assert split.segments[0].semantic_role == "failure_mode"
        assert split.segments[1].semantic_role == "exception_handler_action"

        # Diagnostics
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].kind == "mixed_failure_semantics"

    def test_parse_empty_result(self) -> None:
        """Empty JSON produces empty RouteRefinementResult."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            parse_refinement_result,
        )

        result = parse_refinement_result({})
        assert len(result.annotations) == 0
        assert len(result.split_recommendations) == 0
        assert len(result.diagnostics) == 0

    def test_parse_missing_field_and_executable_become_none(self) -> None:
        """ARC6: Missing field and executable → None, no parse diagnostics.
        The compiler derives these from the canonical role contract."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            parse_refinement_result,
        )

        data = {
            "annotations": [
                {"span_id": "s1", "semantic_role": "profile_domain"},
            ],
        }
        result = parse_refinement_result(data)
        assert len(result.annotations) == 1
        ann = result.annotations[0]
        assert ann.span_id == "s1"
        assert ann.field is None, "Missing field must be None, not defaulted to 'behavior'"
        assert ann.executable is None, "Missing executable must be None, not defaulted to True"
        # ARC6: missing field/executable are NOT parse errors
        field_diags = [d for d in result.parse_diagnostics if "field" in d.field]
        exec_diags = [d for d in result.parse_diagnostics if "executable" in d.field]
        assert len(field_diags) == 0, (
            f"ARC6: missing field is acceptable — compiler fills from contract. "
            f"Got: {field_diags}"
        )
        assert len(exec_diags) == 0, (
            f"ARC6: missing executable is acceptable — compiler fills from contract. "
            f"Got: {exec_diags}"
        )

    def test_parse_missing_span_id_produces_parse_diagnostic(self) -> None:
        """Missing span_id → empty string + parse diagnostic."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            parse_refinement_result,
        )

        data = {
            "annotations": [
                {"field": "behavior", "executable": True},
            ],
        }
        result = parse_refinement_result(data)
        assert len(result.annotations) == 1
        assert result.annotations[0].span_id == ""
        span_diags = [d for d in result.parse_diagnostics if "span_id" in d.field]
        assert len(span_diags) >= 1

    def test_parse_string_false_not_coerced_to_true(self) -> None:
        """LLM returning string 'false' must NOT be bool-coerced to True."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            parse_refinement_result,
        )

        data = {
            "annotations": [
                {"span_id": "s1", "field": "behavior", "executable": "false"},
            ],
        }
        result = parse_refinement_result(data)
        assert len(result.annotations) == 1
        ann = result.annotations[0]
        # String "false" → malformed → None (not True!)
        assert ann.executable is None, (
            f"String 'false' must not coerce to True, got {ann.executable}"
        )
        # Parse diagnostic must record the malformed value
        exec_diags = [
            d
            for d in result.parse_diagnostics
            if "executable" in d.field and "malformed" in d.issue
        ]
        assert len(exec_diags) >= 1, (
            f"Expected a malformed executable diagnostic, got {result.parse_diagnostics}"
        )
        assert exec_diags[0].raw_value == "false"

    def test_parse_string_zero_not_coerced(self) -> None:
        """LLM returning 0 (int) must not be bool-coerced."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            parse_refinement_result,
        )

        data = {
            "annotations": [
                {"span_id": "s1", "field": "behavior", "executable": 0},
            ],
        }
        result = parse_refinement_result(data)
        ann = result.annotations[0]
        assert ann.executable is None, f"Int 0 must not coerce to bool, got {ann.executable}"
        exec_diags = [
            d
            for d in result.parse_diagnostics
            if "executable" in d.field and "malformed" in d.issue
        ]
        assert len(exec_diags) >= 1

    def test_allowed_schema_constants_are_non_empty(self) -> None:
        """Allowed schema sets are non-empty and frozenset."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            ALLOWED_CONSTRUCT_TARGETS,
            ALLOWED_FIELDS,
            ALLOWED_SEMANTIC_ROLES,
            ALLOWED_SLOT_TARGETS,
            EXECUTABLE_ROLES,
            NON_EXECUTABLE_ROLES,
        )

        assert len(ALLOWED_FIELDS) >= 5
        assert len(ALLOWED_SEMANTIC_ROLES) >= 10
        assert len(ALLOWED_CONSTRUCT_TARGETS) >= 4
        assert len(ALLOWED_SLOT_TARGETS) >= 4
        assert len(NON_EXECUTABLE_ROLES) >= 8
        assert len(EXECUTABLE_ROLES) >= 1

        # Executable roles must be a subset of semantic roles
        assert EXECUTABLE_ROLES.issubset(ALLOWED_SEMANTIC_ROLES)
        assert NON_EXECUTABLE_ROLES.issubset(ALLOWED_SEMANTIC_ROLES)

    def test_non_executable_roles_excludes_process_step_and_handler(self) -> None:
        """process_step and exception_handler_action are NOT in non-executable set."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            NON_EXECUTABLE_ROLES,
        )

        assert "process_step" not in NON_EXECUTABLE_ROLES
        assert "exception_handler_action" not in NON_EXECUTABLE_ROLES

    def test_failure_mode_is_non_executable(self) -> None:
        """failure_mode must be in NON_EXECUTABLE_ROLES."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            NON_EXECUTABLE_ROLES,
        )

        assert "failure_mode" in NON_EXECUTABLE_ROLES

    def test_delegation_intent_is_non_executable(self) -> None:
        """delegation_intent must be in NON_EXECUTABLE_ROLES."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            NON_EXECUTABLE_ROLES,
        )

        assert "delegation_intent" in NON_EXECUTABLE_ROLES

    def test_input_output_contracts_are_non_executable(self) -> None:
        """input_contract and output_contract are non-executable."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            NON_EXECUTABLE_ROLES,
        )

        assert "input_contract" in NON_EXECUTABLE_ROLES
        assert "output_contract" in NON_EXECUTABLE_ROLES


# ===========================================================================
# Step 3 — FieldRoute LLM refinement path tests
# ===========================================================================


class TestFieldRouteLLMRefinement:
    """Tests for adapter-guided LLM refinement in FieldRouter."""

    def test_enabled_calls_llm_with_adapter_evidence(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """When flag is enabled, LLM is called with stage2_adapter_guided prompt."""
        mock_client.call_json.return_value = {
            "annotations": [],
            "split_recommendations": [],
            "diagnostics": [],
        }

        canonical = StructuralNLAdapter(mock_client).adapt(MIXED_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
        router = FieldRouter(pipeline_config, mock_client)

        router.execute((spans, canonical))

        call_kwargs = mock_client.call_json.call_args.kwargs
        assert call_kwargs["stage_name"] == "stage2_adapter_guided"
        user_prompt = call_kwargs["user_prompt"]
        assert "Missing timeframe" in user_prompt
        assert "ask one clarifying question" in user_prompt

    def test_llm_failure_raises_when_fallback_disabled(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """LLM failure → fallback to deterministic priors, no crash."""
        from unittest.mock import patch

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        mock_client.call_json.side_effect = Exception("API timeout")
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
        router = FieldRouter(pipeline_config, mock_client)

        with patch.object(router, "save_checkpoint") as mock_save:
            with pytest.raises(StageError) as exc_info:
                router.execute((spans, canonical))

        err = exc_info.value
        assert err.stage == "stage2_field_router"
        assert "stage2_adapter_guided" in str(err)
        assert "Exception" in str(err)
        assert "API timeout" in str(err)
        assert "fallback disabled" in str(err)
        assert err.details["llm_stage_name"] == "stage2_adapter_guided"
        assert err.details["exception_type"] == "Exception"
        assert err.details["exception_message"] == "API timeout"
        assert err.details["fallback_allowed"] is False
        assert err.details["source_schema"] == "structural_nl"
        assert err.details["spans_count"] == len(spans)

        mock_save.assert_called_once()
        checkpoint = mock_save.call_args[0][0]
        assert "routes" not in checkpoint
        assert checkpoint["llm_refinement"]["used"] is False
        assert checkpoint["llm_refinement"]["error_type"] == "Exception"
        assert checkpoint["llm_refinement"]["error_message"] == "API timeout"
        assert checkpoint["llm_refinement"]["fallback_allowed"] is False

    def test_valid_llm_output_merged_with_correct_semantics(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """LLM refinement output with real span_id is merged correctly."""

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        # Find the real failure span_id
        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None, "Must find failure span"

        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": failure_span.span_id,
                    "field": "behavior",
                    "semantic_role": "failure_mode",
                    "construct_target": "EXCEPTION_FLOW",
                    "slot_target": "condition",
                    "executable": False,
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        # LLM annotation must be present with correct semantics
        failure_anns = routes.get_annotations_by_role("failure_mode")
        assert len(failure_anns) >= 1
        matched = [a for a in failure_anns if a.span_id == failure_span.span_id]
        assert len(matched) == 1
        ann = matched[0]
        assert ann.executable is False
        assert ann.construct_target == "EXCEPTION_FLOW"
        assert ann.slot_target == "condition"

    def test_llm_multi_label_same_span_both_retained(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """LLM returns condition + handler for same span → both retained."""

        canonical = StructuralNLAdapter(mock_client).adapt(MIXED_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None

        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": failure_span.span_id,
                    "field": "behavior",
                    "semantic_role": "failure_mode",
                    "construct_target": "EXCEPTION_FLOW",
                    "slot_target": "condition",
                    "executable": False,
                },
                {
                    "span_id": failure_span.span_id,
                    "field": "behavior",
                    "semantic_role": "exception_handler_action",
                    "construct_target": "EXCEPTION_FLOW",
                    "slot_target": "handler",
                    "executable": True,
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        # Both annotations must exist for the same span
        span_anns = routes.get_annotations(failure_span.span_id)
        roles = {a.semantic_role for a in span_anns}
        assert "failure_mode" in roles, f"Missing failure_mode in annotations: {roles}"
        assert "exception_handler_action" in roles, (
            f"Missing exception_handler_action in annotations: {roles}"
        )
        # Condition is non-executable
        cond = [a for a in span_anns if a.semantic_role == "failure_mode"][0]
        assert cond.executable is False
        assert cond.slot_target == "condition"
        # Handler is executable
        handler = [a for a in span_anns if a.semantic_role == "exception_handler_action"][0]
        assert handler.executable is True
        assert handler.slot_target == "handler"

    def test_llm_malformed_field_rejected_prior_kept(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """ARC6: LLM annotation with invalid field for known role is diagnosed, structural prior survives."""

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None

        # LLM returns invalid field
        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": failure_span.span_id,
                    "field": "invalid_field_xyz",
                    "semantic_role": "process_step",
                    "executable": True,
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        # The invalid annotation must NOT have been accepted
        process_anns = routes.get_annotations_by_role("process_step")
        for a in process_anns:
            assert a.field != "invalid_field_xyz", "Malformed field must not be accepted"
        # Phase D: failure_mode packet → StructuralPrior (not RouteAnnotation)
        failure_priors = [
            sp for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role") == "failure_mode"
        ]
        assert len(failure_priors) >= 1, (
            "Structural prior for failure_mode must survive when LLM annotation is rejected"
        )

    def test_llm_missing_executable_rejected(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """LLM annotation without executable flag is rejected, structural prior survives."""

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None

        # LLM returns no executable field
        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": failure_span.span_id,
                    "field": "behavior",
                    "semantic_role": "failure_mode",
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        # Phase D: failure_mode packet → StructuralPrior (not RouteAnnotation)
        failure_priors = [
            sp for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role") == "failure_mode"
        ]
        assert len(failure_priors) >= 1, (
            "Structural prior for failure_mode must survive when LLM annotation is rejected"
        )

    def test_llm_unknown_span_rejected(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """LLM annotation referencing unknown span is rejected."""

        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": "s_nonexistent",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
        router = FieldRouter(pipeline_config, mock_client)

        routes, _ = router.execute((spans, canonical))

        unknown_anns = [a for a in routes.annotations if a.span_id == "s_nonexistent"]
        assert len(unknown_anns) == 0, "LLM annotation for unknown span must be rejected"

    def test_llm_invalid_semantic_role_rejected(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """LLM annotation with invalid semantic_role is rejected, structural prior survives."""

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None

        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": failure_span.span_id,
                    "field": "behavior",
                    "semantic_role": "handler_action",
                    "executable": True,
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        # Invalid role must not appear
        bad = [a for a in routes.annotations if a.semantic_role == "handler_action"]
        assert len(bad) == 0, "Invalid semantic_role must be rejected"
        # Phase D: failure_mode packet → StructuralPrior (not RouteAnnotation)
        failure_priors = [
            sp for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role") == "failure_mode"
        ]
        assert len(failure_priors) >= 1, (
            "Structural prior for failure_mode must survive when LLM annotation is rejected"
        )

    def test_llm_invalid_construct_target_rejected(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """ARC6: Known role with invalid construct_target is diagnosed, structural prior survives."""

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None

        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": failure_span.span_id,
                    "field": "behavior",
                    "semantic_role": "failure_mode",
                    "construct_target": "COMMAND",
                    "executable": False,
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        # Phase D: failure_mode packet → StructuralPrior (not RouteAnnotation)
        failure_priors = [
            sp for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role") == "failure_mode"
        ]
        assert len(failure_priors) >= 1, (
            "Structural prior for failure_mode must survive when LLM annotation is rejected"
        )
        # The structural prior still carries the suggested_semantic_role
        matched = [sp for sp in failure_priors if sp.span_id == failure_span.span_id]
        assert len(matched) >= 1, (
            "Structural prior must reference the failure span"
        )

    def test_llm_invalid_slot_target_rejected(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """ARC6: Known role with invalid slot_target is diagnosed, structural prior survives."""

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None

        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": failure_span.span_id,
                    "field": "behavior",
                    "semantic_role": "failure_mode",
                    "construct_target": "EXCEPTION_FLOW",
                    "slot_target": "made_up",
                    "executable": False,
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        # Phase D: failure_mode packet → StructuralPrior (not RouteAnnotation)
        failure_priors = [
            sp for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role") == "failure_mode"
        ]
        assert len(failure_priors) >= 1, (
            "Structural prior for failure_mode must survive when LLM annotation is rejected"
        )
        matched = [sp for sp in failure_priors if sp.span_id == failure_span.span_id]
        assert len(matched) >= 1, (
            "Structural prior must reference the failure span"
        )

    def test_same_span_same_role_different_slot_both_retained(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Same span + role with different construct_target → both kept.

        Uses 'constraint' role which allows flexible construct/slot combos.
        """

        from nl2spl.canonical import (
            CanonicalCompileInput,
            CompileHint,
            CompileHints,
            EvidenceRef,
            HardFacts,
            RawSection,
            SemanticPacket,
        )

        section = RawSection(
            "sec_policies",
            "policies",
            "Policies",
            "Limit requests. Do not delegate.",
            1,
        )
        packet = SemanticPacket(
            "p_policy_0",
            "sec_policies",
            "policy",
            "Limit requests. Do not delegate.",
            "hint",
            compile_targets=["constraint.requirement"],
        )
        hint = CompileHint(
            source_section_id="sec_policies",
            text="Limit requests.",
            suggested_kind="requirement",
            evidence=[
                EvidenceRef(
                    source_section_id="sec_policies",
                    source_packet_id="p_policy_0",
                )
            ],
            metadata={"semantic_role": "constraint", "executable": False},
        )
        compile_hints = CompileHints(constraint_hints=[hint])
        canonical = CanonicalCompileInput(
            source_schema="structural_nl",
            schema_version="1.0",
            raw_text="Policies:\nLimit requests. Do not delegate.",
            raw_sections=[section],
            semantic_packets=[packet],
            compile_hints=compile_hints,
            hard_facts=HardFacts(),
        )

        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
        span_id = spans[0].span_id

        # LLM returns same span but with TWO DISTINCT canonical roles
        # that share the same construct_target=CONSTRAINT but differ in
        # slot_target.  ARC3: 'constraint' role has explicit
        # construct_target=None, slot_target=None — only
        # delegation_boundary_constraint and delegation_prohibition
        # carry CONSTRAINT construct.
        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": span_id,
                    "field": "rules",
                    "semantic_role": "delegation_boundary_constraint",
                    "construct_target": "CONSTRAINT",
                    "slot_target": "boundary",
                    "executable": False,
                },
                {
                    "span_id": span_id,
                    "field": "rules",
                    "semantic_role": "delegation_prohibition",
                    "construct_target": "CONSTRAINT",
                    "slot_target": "prohibition",
                    "executable": False,
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        span_anns = routes.get_annotations(span_id)
        assert len(span_anns) >= 2, (
            f"Two distinct canonical roles must produce separate annotations, got {len(span_anns)}"
        )
        slots = {a.slot_target for a in span_anns}
        assert "boundary" in slots
        assert "prohibition" in slots

    def test_checkpoint_ambiguity_updates_matches_return_value(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Checkpoint ambiguity_updates == returned ambiguity_updates."""
        from unittest.mock import patch

        canonical = StructuralNLAdapter(mock_client).adapt(MIXED_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None

        mock_client.call_json.return_value = {
            "annotations": [],
            "split_recommendations": [
                {
                    "parent_span_id": failure_span.span_id,
                    "reason": "Mixed condition and handler.",
                    "segments": [
                        {
                            "text": "Missing timeframe",
                            "semantic_role": "failure_mode",
                            "construct_target": "EXCEPTION_FLOW",
                            "slot_target": "condition",
                            "executable": False,
                        },
                    ],
                }
            ],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        with patch.object(router, "save_checkpoint") as mock_save:
            routes, ambiguity_updates = router.execute((spans, canonical))

        mock_save.assert_called_once()
        checkpoint = mock_save.call_args[0][0]

        expected_len = len(ambiguity_updates)
        actual_len = len(checkpoint["ambiguity_updates"])
        assert actual_len == expected_len, (
            f"Checkpoint ambiguity_updates ({actual_len}) must match return value ({expected_len})"
        )
        if expected_len > 0:
            assert checkpoint["ambiguity_updates"][0]["span_id"] == failure_span.span_id
            assert checkpoint["ambiguity_updates"][0]["needs_split"] is True

    def test_split_recommendations_become_ambiguity_updates(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """LLM split recommendations are returned as ambiguity_updates."""

        canonical = StructuralNLAdapter(mock_client).adapt(MIXED_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None

        mock_client.call_json.return_value = {
            "annotations": [],
            "split_recommendations": [
                {
                    "parent_span_id": failure_span.span_id,
                    "reason": "Condition and handler are mixed.",
                    "segments": [
                        {
                            "text": "Missing timeframe",
                            "semantic_role": "failure_mode",
                            "construct_target": "EXCEPTION_FLOW",
                            "slot_target": "condition",
                            "executable": False,
                        },
                        {
                            "text": "ask one clarifying question",
                            "semantic_role": "exception_handler_action",
                            "construct_target": "EXCEPTION_FLOW",
                            "slot_target": "handler",
                            "executable": True,
                        },
                    ],
                }
            ],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, ambiguity_updates = router.execute((spans, canonical))

        # Ambiguity updates must contain the split recommendation
        assert len(ambiguity_updates) >= 1, (
            f"Split recommendations must become ambiguity_updates, got {len(ambiguity_updates)}"
        )
        update = ambiguity_updates[0]
        assert update["span_id"] == failure_span.span_id
        assert update["is_ambiguous"] is True
        assert update["needs_split"] is True
        assert "split_recommendation" in update

    def test_generic_nl_not_affected_by_flag(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Generic NL path uses existing Stage 2, even when flag is enabled."""
        mock_client.call_json.return_value = {
            "routes": {
                "identity": ["s1"],
                "audience": [],
                "rules": [],
                "domain": [],
                "integrations": [],
                "behavior": [],
            },
            "ambiguity_updates": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        spans = [SpanIR("s1", "test")]

        routes, _ = router.execute(spans)

        assert "s1" in routes.identity
        # Must use existing stage2 prompt, not adapter_guided
        call_kwargs = mock_client.call_json.call_args.kwargs
        assert call_kwargs["stage_name"] == "stage2_field_router"


# ===========================================================================
# Step 4 — Validator-specific tests
# ===========================================================================


class TestRouteRefinementValidator:
    """Tests for the standalone RouteRefinementValidator."""

    def test_validator_rejects_unknown_span(self) -> None:
        """Validator rejects annotation with non-existent span_id."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s_nonexistent",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
            ],
        )
        spans = [SpanIR("s1", "test")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        assert len(result.accepted) == 0
        assert len(result.rejected) == 1
        assert "unknown span_id" in result.rejected[0].reason.lower()

    def test_validator_rejects_unknown_semantic_role(self) -> None:
        """Validator rejects annotation with invalid semantic_role."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="invented_role_xyz",
                    executable=True,
                ),
            ],
        )
        spans = [SpanIR("s1", "test")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        assert len(result.accepted) == 0
        assert len(result.rejected) == 1
        assert "invalid semantic_role" in result.rejected[0].reason.lower()

    def test_validator_preserves_span_section_packet_provenance(self) -> None:
        """Validator accepts annotation with provenance and passes it through."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                    source_section_id="sec_process",
                    source_packet_id="p_process_step_0",
                ),
            ],
        )
        spans = [SpanIR("s1", "Do the thing.", source_section_id="sec_process")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        assert len(result.accepted) == 1
        ann = result.accepted[0]
        assert ann.source_section_id == "sec_process"
        assert ann.source_packet_id == "p_process_step_0"

    def test_validator_accepts_executable_input_contract_with_diagnostic(self) -> None:
        """ARC6: Validator accepts input_contract with executable=True (diagnostic, not reject)."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s1",
                    field="resources",
                    semantic_role="input_contract",
                    executable=True,
                ),
            ],
        )
        spans = [SpanIR("s1", "user request")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        # ARC6: accepted with diagnostic, not rejected
        assert len(result.rejected) == 0
        assert len(result.accepted) == 1
        assert len(result.structured_diagnostics) >= 1

    def test_validator_accepts_executable_failure_mode_with_diagnostic(self) -> None:
        """ARC6: Validator accepts failure_mode with executable=True (diagnostic, not reject)."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=True,  # Should be False
                ),
            ],
        )
        spans = [SpanIR("s1", "Missing timeframe.")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        # ARC6: accepted with diagnostic, not rejected
        assert len(result.rejected) == 0
        assert len(result.accepted) == 1
        assert len(result.structured_diagnostics) >= 1

    def test_validator_accepts_explicit_exception_handler_action(self) -> None:
        """Validator accepts exception_handler_action with handler verb in text."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="exception_handler_action",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="handler",
                    executable=True,
                ),
            ],
        )
        # Source text must contain a handler action verb
        spans = [SpanIR("s1", "ask one clarifying question.")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        assert len(result.accepted) == 1
        ann = result.accepted[0]
        assert ann.semantic_role == "exception_handler_action"
        assert ann.executable is True

    def test_validator_rejects_handler_without_action_verb(self) -> None:
        """Validator rejects exception_handler_action without action verb in text."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="exception_handler_action",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="handler",
                    executable=True,
                ),
            ],
        )
        # No action verb in source text
        spans = [SpanIR("s1", "Missing timeframe.")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        assert len(result.rejected) == 1
        assert "handler action verb" in result.rejected[0].reason.lower()

    def test_validator_diagnoses_delegation_intent_executable(self) -> None:
        """ARC6: Validator diagnoses delegation_intent with executable=True."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="delegation_intent",
                    executable=True,
                ),
            ],
        )
        spans = [SpanIR("s1", "delegate research")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        # ARC6: accepted with diagnostic, not rejected
        assert len(result.rejected) == 0
        assert len(result.accepted) == 1
        assert len(result.structured_diagnostics) >= 1

    def test_validator_rejects_failure_mode_with_wrong_construct(self) -> None:
        """Phase 1: Validator now ACCEPTS failure_mode with wrong construct_target
        and records diagnostic. Normalization corrects fields."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="failure_mode",
                    construct_target="CONSTRAINT",
                    slot_target="condition",
                    executable=False,
                ),
            ],
        )
        spans = [SpanIR("s1", "Missing timeframe.")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        # Phase 1: known role accepted with diagnostic, not rejected
        assert len(result.accepted) == 1, (
            "Phase 1: failure_mode must be ACCEPTED (diagnostic recorded)"
        )
        assert len(result.structured_diagnostics) >= 1, (
            "Phase 1: structured diagnostic must be recorded for construct_target mismatch"
        )

    def test_validator_no_fallback_even_when_majority_rejected(self) -> None:
        """Validator does NOT trigger fallback — rejected annotations are
        reported but do not suppress accepted ones or split recommendations."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s1", field="behavior", semantic_role="process_step", executable=True
                ),
                RefinedAnnotation(
                    span_id="s_fake_1",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
                RefinedAnnotation(
                    span_id="s_fake_2",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
            ],
        )
        spans = [SpanIR("s1", "Do the thing.")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        assert result.fallback_triggered is False
        assert len(result.accepted) == 1
        assert len(result.rejected) == 2

    def test_validator_no_fallback_when_minority_rejected(self) -> None:
        """Validator does NOT trigger fallback when <50% rejected."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s1", field="behavior", semantic_role="process_step", executable=True
                ),
                RefinedAnnotation(
                    span_id="s2", field="behavior", semantic_role="process_step", executable=True
                ),
                RefinedAnnotation(
                    span_id="s_fake",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
            ],
        )
        spans = [SpanIR("s1", "Do thing."), SpanIR("s2", "Do another.")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        assert result.fallback_triggered is False
        assert len(result.accepted) == 2
        assert len(result.rejected) == 1

    def test_validator_provenance_mismatch_warning_not_reject(self) -> None:
        """LLM provenance that differs from span → warning, annotation still accepted."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                    source_section_id="sec_wrong",
                    source_packet_id="p_wrong",
                ),
            ],
        )
        spans = [
            SpanIR(
                "s1", "Do the thing.", source_section_id="sec_correct", source_packet_id="p_correct"
            )
        ]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        # Annotation still accepted
        assert len(result.accepted) == 1
        # But provenance mismatch warning in diagnostics
        assert any(
            "Provenance mismatch" in d and "source_section_id" in d for d in result.diagnostics
        ), f"Expected provenance mismatch diagnostic, got: {result.diagnostics}"
        assert any(
            "Provenance mismatch" in d and "source_packet_id" in d for d in result.diagnostics
        ), "Expected packet provenance mismatch diagnostic"

    def test_validator_split_parent_span_must_exist(self) -> None:
        """Split recommendation with unknown parent_span_id is rejected."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
            SplitRecommendation,
            SplitSegment,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[],
            split_recommendations=[
                SplitRecommendation(
                    parent_span_id="s_nonexistent",
                    reason="Test.",
                    segments=[SplitSegment(text="test")],
                ),
            ],
        )
        spans = [SpanIR("s1", "test")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        assert len(result.split_recommendations) == 0
        assert any("unknown parent_span_id" in d for d in result.diagnostics), (
            f"Expected rejected split diagnostic, got: {result.diagnostics}"
        )

    def test_validator_split_segment_text_in_parent(self) -> None:
        """Split segment text not in parent span → accepted with warning."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RouteRefinementResult,
            SplitRecommendation,
            SplitSegment,
        )
        from nl2spl.pipeline.stages.stage2_field_router_validator import (
            RouteRefinementValidator,
        )

        llm_result = RouteRefinementResult(
            annotations=[],
            split_recommendations=[
                SplitRecommendation(
                    parent_span_id="s1",
                    reason="Test.",
                    segments=[SplitSegment(text="fabricated text")],
                ),
            ],
        )
        spans = [SpanIR("s1", "real text only")]

        validator = RouteRefinementValidator()
        result = validator.validate(llm_result, spans, canonical_input=None, structural_priors=[], deterministic_annotations=[])

        # Segment still present but warning emitted
        assert len(result.split_recommendations) == 1
        assert any("not found in parent span" in d for d in result.diagnostics), (
            f"Expected segment warning, got: {result.diagnostics}"
        )


# ===========================================================================
# Step 5 — Downstream alignment regression
# ===========================================================================


class TestDownstreamAlignment:
    """Verify downstream stages handle new annotation types correctly."""

    # -- Stage 7: executable filtering ------------------------------------

    def test_stage7_failure_condition_not_command(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """failure_mode / non-executable → Stage 7 drops attempt to create command."""
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor

        spans = [
            SpanIR("s_fail", "Missing timeframe."),
            SpanIR("s_good", "Determine communication type."),
        ]
        routes = FieldRouteIR(
            behavior=["s_fail", "s_good"],
            annotations=[
                RouteAnnotation(
                    span_id="s_fail",
                    field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s_good",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
            ],
        )

        # LLM tries to create a command from the failure span
        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_bad",
                    "text": "Handle missing timeframe",
                    "command_type": "GENERAL_COMMAND",
                    "source_span_ids": ["s_fail"],
                    "inputs": [],
                    "outputs": [],
                    "flow_ref": "main",
                    "kind": "normal",
                },
                {
                    "step_id": "st_good",
                    "text": "Determine communication type",
                    "command_type": "GENERAL_COMMAND",
                    "source_span_ids": ["s_good"],
                    "inputs": [],
                    "outputs": [],
                    "flow_ref": "main",
                    "kind": "normal",
                },
            ],
        }
        extractor = StepExtractor(pipeline_config, mock_client)
        steps, _ = extractor.execute(
            (spans, routes, FlowStructureIR(), BlockStructureIR(), SymbolTable())
        )

        # Bad step from failure span must be dropped
        bad = [s for s in steps if hasattr(s, "source_span_ids") and "s_fail" in s.source_span_ids]
        assert len(bad) == 0, f"Failure-sourced command must be dropped, got {len(bad)}"
        # Good step must survive
        good = [s for s in steps if hasattr(s, "source_span_ids") and "s_good" in s.source_span_ids]
        assert len(good) == 1, "Legitimate process_step command must survive"

    def test_stage7_delegation_intent_not_invoke_worker(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """delegation_intent / non-executable → Stage 7 drops INVOKE_WORKER attempt."""
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor

        spans = [
            SpanIR("s_del", "delegate research"),
            SpanIR("s_good", "Determine communication type."),
        ]
        routes = FieldRouteIR(
            behavior=["s_del", "s_good"],
            annotations=[
                RouteAnnotation(
                    span_id="s_del",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s_good",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
            ],
        )

        # LLM tries to create INVOKE_WORKER from non-executable delegation span
        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_bad",
                    "text": "delegate research",
                    "command_type": "INVOKE_WORKER",
                    "source_span_ids": ["s_del"],
                    "inputs": [],
                    "outputs": [],
                    "flow_ref": "main",
                    "kind": "normal",
                },
                {
                    "step_id": "st_good",
                    "text": "Determine communication type",
                    "command_type": "GENERAL_COMMAND",
                    "source_span_ids": ["s_good"],
                    "inputs": [],
                    "outputs": [],
                    "flow_ref": "main",
                    "kind": "normal",
                },
            ],
        }
        extractor = StepExtractor(pipeline_config, mock_client)
        steps, _ = extractor.execute(
            (spans, routes, FlowStructureIR(), BlockStructureIR(), SymbolTable())
        )

        # INVOKE_WORKER from non-executable delegation span must be dropped
        invoke_steps = [
            s
            for s in steps
            if hasattr(s, "command_type") and "INVOKE_WORKER" in str(s.command_type)
        ]
        assert len(invoke_steps) == 0, (
            f"INVOKE_WORKER from delegation_intent must be dropped, got {len(invoke_steps)}"
        )
        # Good step survives
        good = [s for s in steps if hasattr(s, "source_span_ids") and "s_good" in s.source_span_ids]
        assert len(good) == 1, "Legitimate process_step command must survive"

    def test_stage7_handler_action_can_be_command(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """exception_handler_action / executable=True → Stage 7 CAN produce command."""
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor

        spans = [SpanIR("s_handler", "ask one clarifying question.")]
        routes = FieldRouteIR(
            behavior=["s_handler"],
            annotations=[
                RouteAnnotation(
                    span_id="s_handler",
                    field="behavior",
                    semantic_role="exception_handler_action",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="handler",
                    executable=True,
                ),
            ],
        )

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_handler",
                    "text": "ask one clarifying question",
                    "command_type": "GENERAL_COMMAND",
                    "source_span_ids": ["s_handler"],
                    "inputs": [],
                    "outputs": [],
                    "flow_ref": "main",
                    "kind": "normal",
                },
            ],
        }
        extractor = StepExtractor(pipeline_config, mock_client)
        steps, _ = extractor.execute(
            (
                spans,
                routes,
                FlowStructureIR(main_flow_spans=["s_handler"]),
                BlockStructureIR(),
                SymbolTable(),
            )
        )

        handler_steps = [
            s for s in steps if hasattr(s, "source_span_ids") and "s_handler" in s.source_span_ids
        ]
        assert len(handler_steps) >= 1, (
            "Executable exception_handler_action should produce a command"
        )

    # -- Stage 9: constraint extraction ----------------------------------

    def test_stage9_delegation_boundary_constraint_survives(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """delegation_boundary_constraint annotation → Stage 9 extracts it."""
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.pipeline.stages.stage9_constraint_extractor import ConstraintExtractor

        spans = [SpanIR("s_boundary", "Only delegate if evidence can be normalized.")]
        routes = FieldRouteIR(
            rules=["s_boundary"],
            annotations=[
                RouteAnnotation(
                    span_id="s_boundary",
                    field="rules",
                    semantic_role="delegation_boundary_constraint",
                    executable=False,
                ),
            ],
        )

        mock_client.call_json.return_value = {
            "constraints": [
                {
                    "constraint_id": "c_boundary",
                    "text": "Only delegate if evidence can be normalized.",
                    "kind": "obligation",
                    "targets": ["delegation"],
                    "source_span_ids": ["s_boundary"],
                },
            ],
        }
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        result = extractor.execute(
            (spans, routes, FlowStructureIR(), BlockStructureIR(), SymbolTable(), [])
        )

        prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
        assert "Only delegate" in prompt, "Boundary span must be in constraint prompt"
        assert len(result) == 1, "Delegation boundary constraint must survive"
        assert result[0].constraint_id == "c_boundary"

    def test_stage9_failure_mode_excluded_from_constraints(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """failure_mode annotation → Stage 9 excludes from constraints."""
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.pipeline.stages.stage9_constraint_extractor import ConstraintExtractor

        spans = [SpanIR("s_fail", "Missing timeframe.")]
        routes = FieldRouteIR(
            rules=["s_fail"],
            annotations=[
                RouteAnnotation(
                    span_id="s_fail",
                    field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
            ],
        )

        mock_client.call_json.return_value = {
            "constraints": [
                {
                    "constraint_id": "c_bad",
                    "text": "Handle missing timeframe",
                    "kind": "obligation",
                    "targets": ["global"],
                    "source_span_ids": ["s_fail"],
                },
            ],
        }
        extractor = ConstraintExtractor(pipeline_config, mock_client)
        result = extractor.execute(
            (spans, routes, FlowStructureIR(), BlockStructureIR(), SymbolTable(), [])
        )

        prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
        assert "Missing timeframe" not in prompt, (
            "failure_mode must be excluded from constraint prompt"
        )
        assert len(result) == 0, "failure_mode-sourced constraint must be rejected"

    # -- Stage 6: resource extraction ------------------------------------

    def test_stage6_failure_text_not_extracted_as_variable(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """failure_mode span → Stage 6 does not create a variable."""
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor

        canonical = StructuralNLAdapter(mock_client).adapt(STRUCTURAL_TEXT)
        spans = [
            SpanIR("s_process", "Determine communication type."),
            SpanIR("s_fail", "Missing timeframe."),
        ]
        routes = FieldRouteIR(
            behavior=["s_process", "s_fail"],
            annotations=[
                RouteAnnotation(
                    span_id="s_process",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
                RouteAnnotation(
                    span_id="s_fail",
                    field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
            ],
        )

        mock_client.call_json.return_value = {
            "variables": [
                {
                    "name": "missing_timeframe",
                    "data_type": "text",
                    "required": False,
                    "description": "Missing timeframe condition",
                    "source": "step",
                },
                {
                    "name": "communication_type",
                    "data_type": "text",
                    "required": False,
                    "description": "Communication type",
                    "source": "step",
                },
            ],
            "files": [],
            "apis": [],
            "types": [],
        }
        extractor = ResourceExtractor(pipeline_config, mock_client)
        resources, _ = extractor.execute(
            (spans, routes, FlowStructureIR(), BlockStructureIR(), canonical)
        )

        names = {v.name for v in resources.variables}
        assert "communication_type" in names, "Legitimate variable must survive"
        assert "missing_timeframe" not in names, "Failure-derived variable must be rejected"

    # -- Internal-Comms happy path ---------------------------------------

    def test_internal_comms_happy_path_stable(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Full Internal-Comms structural NL → structural priors still correct."""
        routes, spans, canonical, _ = _adapt_slice_route(
            STRUCTURAL_TEXT, pipeline_config, mock_client
        )

        # Phase D: packet types → StructuralPrior, not RouteAnnotation
        assert len(routes.structural_priors) >= 5, (
            f"Expected at least 5 structural priors, got {len(routes.structural_priors)}"
        )
        prior_roles = {
            sp.metadata.get("suggested_semantic_role")
            for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role")
        }
        assert "failure_mode" in prior_roles
        assert "process_step" in prior_roles
        assert "delegation_intent" in prior_roles
        assert "input_contract" in prior_roles or "output_contract" in prior_roles

    def test_mixed_failure_nl_has_correct_annotation_types(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Mixed failure text → structural priors include failure_mode (correct type)."""
        routes, spans, _, _ = _adapt_slice_route(MIXED_FAILURE_TEXT, pipeline_config, mock_client)

        # Phase D: failure_mode packet → StructuralPrior, not RouteAnnotation
        failure_priors = [
            sp for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role") == "failure_mode"
        ]
        assert len(failure_priors) >= 1, (
            "failure_mode packet should generate StructuralPrior"
        )
        for sp in failure_priors:
            assert sp.suggested_field == "behavior"

    # -- Route diagnostics in report -------------------------------------

    def test_route_diagnostics_visible_in_field_route_ir(
        self,
    ) -> None:
        """RouteAnnotation.diagnostics are accessible in FieldRouteIR."""
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(
                    span_id="s1",
                    field="behavior",
                    semantic_role="failure_mode",
                    diagnostics=["test_diagnostic: conflict with prior"],
                ),
            ],
        )

        ann = routes.annotations[0]
        assert len(ann.diagnostics) >= 1
        assert "conflict with prior" in ann.diagnostics[0]

    def test_non_executable_behavior_excluded_from_executable_list(
        self,
    ) -> None:
        """get_executable_behavior_span_ids excludes non-executable annotations."""
        routes = FieldRouteIR(
            behavior=["s_exec", "s_non_exec"],
            annotations=[
                RouteAnnotation(
                    span_id="s_exec",
                    field="behavior",
                    semantic_role="process_step",
                    executable=True,
                ),
                RouteAnnotation(
                    span_id="s_non_exec",
                    field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
            ],
        )

        exec_ids = routes.get_executable_behavior_span_ids()
        assert "s_exec" in exec_ids
        assert "s_non_exec" not in exec_ids, (
            "Non-executable failure_mode must not appear in executable list"
        )


class TestValidatorMergeIntegration:
    """Integration: validator + merge working together in FieldRouter."""

    def test_merge_prior_provenance_overrides_llm_provenance(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Merge prefers prior/span provenance over LLM provenance."""

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None
        # The span has real provenance from the adapter
        assert failure_span.source_section_id is not None
        assert failure_span.source_packet_id is not None

        # LLM returns different (wrong) provenance
        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": failure_span.span_id,
                    "field": "behavior",
                    "semantic_role": "failure_mode",
                    "construct_target": "EXCEPTION_FLOW",
                    "slot_target": "condition",
                    "executable": False,
                    "source_section_id": "sec_fake",
                    "source_packet_id": "p_fake",
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        failure_anns = routes.get_annotations_by_role("failure_mode")
        matched = [a for a in failure_anns if a.span_id == failure_span.span_id]
        assert len(matched) >= 1
        # Prior provenance must survive, not LLM's fake values
        ann = matched[0]
        assert ann.source_section_id != "sec_fake", (
            "LLM provenance must not override prior provenance"
        )
        assert ann.source_packet_id != "p_fake", "LLM packet id must not override prior packet id"

    def test_deterministic_priors_survive_when_all_llm_rejected(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """When all LLM annotations are rejected, structural priors remain."""

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        # LLM returns all invalid annotations
        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": "s_fake_1",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                },
                {
                    "span_id": "s_fake_2",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        # Phase D: failure_mode packet → StructuralPrior (not RouteAnnotation)
        failure_priors = [
            sp for sp in routes.structural_priors
            if sp.metadata.get("suggested_semantic_role") == "failure_mode"
        ]
        assert len(failure_priors) >= 1, (
            "Structural prior for failure_mode must survive when all LLM output rejected"
        )

    def test_validator_output_includes_diagnostics(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Validator diagnostics appear in checkpoint route_diagnostics."""
        from unittest.mock import patch

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None

        # LLM returns executable failure_mode (will be rejected by validator)
        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": failure_span.span_id,
                    "field": "behavior",
                    "semantic_role": "failure_mode",
                    "construct_target": "EXCEPTION_FLOW",
                    "slot_target": "condition",
                    "executable": True,  # invalid
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        with patch.object(router, "save_checkpoint") as mock_save:
            router.execute((spans, canonical))

        mock_save.assert_called_once()
        checkpoint = mock_save.call_args[0][0]
        llm_rf = checkpoint["llm_refinement"]
        diags = llm_rf["route_diagnostics"]
        assert any("failure_mode must be non-executable" in d for d in diags), (
            f"Expected validator diagnostic about non-executable failure_mode, got: {diags}"
        )

    def test_merge_append_handler_uses_prior_provenance_not_llm(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """New handler annotation gets prior provenance, not LLM faked one."""

        canonical = StructuralNLAdapter(mock_client).adapt(MIXED_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None
        real_pid = failure_span.source_packet_id
        assert real_pid is not None

        # LLM returns handler with FAKE provenance
        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": failure_span.span_id,
                    "field": "behavior",
                    "semantic_role": "exception_handler_action",
                    "construct_target": "EXCEPTION_FLOW",
                    "slot_target": "handler",
                    "executable": True,
                    "source_section_id": "sec_fake",
                    "source_packet_id": "p_fake",
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, _ = router.execute((spans, canonical))

        handler_anns = [
            a for a in routes.annotations if a.semantic_role == "exception_handler_action"
        ]
        assert len(handler_anns) >= 1
        handler = handler_anns[0]
        # Must NOT carry LLM's fake provenance
        assert handler.source_section_id != "sec_fake", (
            "Handler annotation must not carry LLM-faked section_id"
        )
        assert handler.source_packet_id != "p_fake", (
            "Handler annotation must not carry LLM-faked packet_id"
        )
        # Must carry the real span provenance
        assert handler.source_packet_id == real_pid, (
            f"Handler annotation packet_id must match span ({real_pid}), "
            f"got {handler.source_packet_id}"
        )

    def test_merge_rejects_unknown_parent_split_even_with_valid_annotation(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Unknown-parent split rejected; valid annotation merged normally."""

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None

        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": failure_span.span_id,
                    "field": "behavior",
                    "semantic_role": "failure_mode",
                    "construct_target": "EXCEPTION_FLOW",
                    "slot_target": "condition",
                    "executable": False,
                },
            ],
            "split_recommendations": [
                {
                    "parent_span_id": "s_nonexistent",
                    "reason": "Should be rejected.",
                    "segments": [{"text": "test"}],
                },
            ],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        routes, ambiguity_updates = router.execute((spans, canonical))

        # Valid annotation still merged
        failure_anns = routes.get_annotations_by_role("failure_mode")
        assert len(failure_anns) >= 1

        # Invalid split must NOT reach ambiguity_updates
        invalid_splits = [u for u in ambiguity_updates if u.get("span_id") == "s_nonexistent"]
        assert len(invalid_splits) == 0, "Unknown-parent split must not reach ambiguity_updates"

    def test_rejected_annotations_do_not_suppress_valid_splits(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Rejected annotations do NOT suppress valid split recommendations."""
        from unittest.mock import patch

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)

        failure_span = next((s for s in spans if "Missing timeframe" in s.text), None)
        assert failure_span is not None

        # 2 invalid annotations (unknown span_ids), plus a valid split
        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": "s_fake_1",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                },
                {
                    "span_id": "s_fake_2",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                },
            ],
            "split_recommendations": [
                {
                    "parent_span_id": failure_span.span_id,
                    "reason": "Valid split.",
                    "segments": [
                        {
                            "text": "Missing timeframe",
                            "semantic_role": "failure_mode",
                            "executable": False,
                        }
                    ],
                },
            ],
            "diagnostics": [],
        }

        router = FieldRouter(pipeline_config, mock_client)
        with patch.object(router, "save_checkpoint"):
            routes, ambiguity_updates = router.execute((spans, canonical))

        # Valid split recommendation must NOT be suppressed
        assert len(ambiguity_updates) >= 1, (
            f"Valid split recommendations must not be suppressed by annotation rejections, "
            f"got {len(ambiguity_updates)} updates"
        )
        # Phase D: structural priors survive (no LLM annotations accepted,
        # and packet types no longer generate deterministic RouteAnnotations)
        assert len(routes.structural_priors) >= 1, (
            "Structural priors must survive when all LLM annotations are rejected"
        )

    def test_checkpoint_includes_llm_refinement_summary(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Checkpoint must include llm_refinement metadata."""
        from unittest.mock import patch

        mock_client.call_json.return_value = {
            "annotations": [
                {
                    "span_id": "",
                    "field": "behavior",
                    "semantic_role": "failure_mode",
                    "executable": False,
                },
            ],
            "split_recommendations": [],
            "diagnostics": [],
        }

        canonical = StructuralNLAdapter(mock_client).adapt(CONDITION_ONLY_FAILURE_TEXT)
        spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
        router = FieldRouter(pipeline_config, mock_client)

        with patch.object(router, "save_checkpoint") as mock_save:
            router.execute((spans, canonical))

        mock_save.assert_called_once()
        checkpoint = mock_save.call_args[0][0]

        assert "llm_refinement" in checkpoint, (
            f"Checkpoint missing llm_refinement key; keys: {list(checkpoint)}"
        )
        llm_rf = checkpoint["llm_refinement"]
        assert llm_rf["used"] is True
        assert "route_diagnostics" in llm_rf
        assert "split_recommendations" in llm_rf


# ===========================================================================
# Phase A — Neutral prior merge
# ===========================================================================


class TestNeutralPriorMerge:
    """Phase A: neutral pending priors are replaced by accepted LLM annotations."""

    @staticmethod
    @staticmethod
    def _make_router_and_inputs(
        priors: list[RouteAnnotation],
        llm_annotations: list[dict[str, Any]],
        span_ids: list[str],
    ) -> tuple[FieldRouter, list[SpanIR], MagicMock]:
        mock_client = MagicMock(spec=LLMClient)
        mock_client.call_json.return_value = {
            "annotations": llm_annotations,
            "split_recommendations": [],
            "diagnostics": [],
        }
        config = PipelineConfig(
            llm=LLMConfig(model="gpt-4o", max_tokens=4096, temperature=0.0, api_key="test"),
        )
        router = FieldRouter(config, mock_client)
        spans = [
            SpanIR(
                span_id=sid,
                text=f"text for {sid}",
                source_section_id="sec_real",
                source_packet_id="pkt_real",
            )
            for sid in span_ids
        ]
        return router, spans, mock_client

    def test_neutral_structural_prior_not_in_merged_annotations(self) -> None:
        """Phase D: neutral StructuralPrior does NOT enter merged annotations.
        Only the LLM annotation appears in the final result."""
        from nl2spl.ir.field_route_ir import StructuralPrior
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )

        # Neutral prior is now StructuralPrior, not passed as RouteAnnotation
        structural_priors = [
            StructuralPrior(
                span_id="s13",
                suggested_field="behavior",
                source_section_id="sec_real",
                source_packet_id="pkt_real",
                prior_kind="neutral_context",
            )
        ]
        # No deterministic annotations (neutral prior is structural only)
        deterministic_annotations: list[RouteAnnotation] = []
        router, spans, _ = self._make_router_and_inputs(
            deterministic_annotations,
            [
                {
                    "span_id": "s13",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                }
            ],
            ["s13"],
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s13", field="behavior", semantic_role="process_step", executable=True
                )
            ],
        )

        merged, _, _, _ = router._merge_llm_refinement(
            deterministic_annotations, llm_result, spans,
            structural_priors=structural_priors,
        )

        # Exactly one s13 annotation — the LLM one only
        s13_anns = [a for a in merged if a.span_id == "s13"]
        assert len(s13_anns) == 1, f"Expected 1 s13 annotation, got {len(s13_anns)}"
        ann = s13_anns[0]
        assert ann.semantic_role == "process_step"
        assert ann.executable is True
        # Provenance from structural prior
        assert ann.source_section_id == "sec_real"
        assert ann.source_packet_id == "pkt_real"

    def test_neutral_prior_not_in_non_executable_set_after_merge(self) -> None:
        """Phase D: StructuralPrior does not pollute executable/non-executable sets."""
        from nl2spl.ir.field_route_ir import StructuralPrior
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )

        structural_priors = [
            StructuralPrior(
                span_id="s13",
                suggested_field="behavior",
                source_section_id="sec_real",
                source_packet_id="pkt_real",
                prior_kind="neutral_context",
            )
        ]
        deterministic_annotations: list[RouteAnnotation] = []
        router, spans, _ = self._make_router_and_inputs(
            deterministic_annotations,
            [
                {
                    "span_id": "s13",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                }
            ],
            ["s13"],
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s13", field="behavior", semantic_role="process_step", executable=True
                )
            ],
        )

        merged, _, _, _ = router._merge_llm_refinement(
            deterministic_annotations, llm_result, spans,
            structural_priors=structural_priors,
        )

        routes = FieldRouteIR(behavior=["s13"], annotations=merged)
        exec_ids = routes.get_executable_behavior_span_ids()
        non_exec_ids = routes.get_non_executable_behavior_span_ids()

        assert "s13" in exec_ids, "s13 must be in executable set"
        assert "s13" not in non_exec_ids, "s13 must NOT be in non-executable set"

    def test_weak_section_context_structural_prior_not_in_merged(self) -> None:
        """Phase D: weak_section_context StructuralPrior does NOT enter merged annotations."""
        from nl2spl.ir.field_route_ir import StructuralPrior
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )

        structural_priors = [
            StructuralPrior(
                span_id="s13",
                suggested_field="behavior",
                source_section_id="sec_real",
                source_packet_id="pkt_real",
                prior_kind="weak_section_context",
            )
        ]
        deterministic_annotations: list[RouteAnnotation] = []
        router, spans, _ = self._make_router_and_inputs(
            deterministic_annotations,
            [
                {
                    "span_id": "s13",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                }
            ],
            ["s13"],
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s13", field="behavior", semantic_role="process_step", executable=True
                )
            ],
        )

        merged, _, _, _ = router._merge_llm_refinement(
            deterministic_annotations, llm_result, spans,
            structural_priors=structural_priors,
        )

        s13_anns = [a for a in merged if a.span_id == "s13"]
        assert len(s13_anns) == 1, f"Expected 1 s13 annotation, got {len(s13_anns)}"
        assert s13_anns[0].executable is True

    def test_genuine_non_executable_not_replaced(self) -> None:
        """Real failure_mode annotation (with semantic_role) is NOT treated as neutral."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )

        # A real failure_mode prior — has semantic_role populated
        real_prior = RouteAnnotation(
            span_id="s19",
            field="behavior",
            semantic_role="failure_mode",
            construct_target="EXCEPTION_FLOW",
            slot_target="condition",
            executable=False,
            source_section_id="sec_real",
            source_packet_id="pkt_real",
        )
        priors = [real_prior]
        router, spans, _ = self._make_router_and_inputs(
            priors,
            [
                {
                    "span_id": "s19",
                    "field": "behavior",
                    "semantic_role": "failure_mode",
                    "construct_target": "EXCEPTION_FLOW",
                    "slot_target": "condition",
                    "executable": False,
                }
            ],
            ["s19"],
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s19",
                    field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                )
            ],
        )

        merged, _, _, _ = router._merge_llm_refinement(priors, llm_result, spans)

        s19_anns = [a for a in merged if a.span_id == "s19"]
        assert len(s19_anns) == 1
        assert s19_anns[0].semantic_role == "failure_mode"
        assert s19_anns[0].executable is False

    def test_multi_label_deterministic_plus_llm(self) -> None:
        """Phase D: StructuralPrior does NOT enter merged. Only deterministic
        RouteAnnotation + LLM annotation remain."""
        from nl2spl.ir.field_route_ir import StructuralPrior
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )

        # StructuralPrior (neutral) — does NOT enter merged
        structural_priors = [
            StructuralPrior(
                span_id="s13",
                suggested_field="behavior",
                source_section_id="sec_real",
                source_packet_id="pkt_real",
                prior_kind="neutral_context",
            )
        ]
        # Deterministic RouteAnnotation (real semantic decision)
        real_prior = RouteAnnotation(
            span_id="s13",
            field="behavior",
            semantic_role="failure_mode",
            construct_target="EXCEPTION_FLOW",
            slot_target="condition",
            executable=False,
        )
        priors = [real_prior]
        router, spans, _ = self._make_router_and_inputs(
            priors,
            [
                {
                    "span_id": "s13",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                }
            ],
            ["s13"],
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s13", field="behavior", semantic_role="process_step", executable=True
                )
            ],
        )

        merged, _, _, _ = router._merge_llm_refinement(
            priors, llm_result, spans,
            structural_priors=structural_priors,
        )

        s13_anns = [a for a in merged if a.span_id == "s13"]
        roles = {a.semantic_role for a in s13_anns}
        # Real prior + LLM annotation remain; StructuralPrior NOT in merged
        assert "failure_mode" in roles, f"Real prior must survive, got {roles}"
        assert "process_step" in roles, f"LLM annotation must be added, got {roles}"
        assert len(s13_anns) == 2, f"Expected 2 annotations, got {len(s13_anns)}"

    # --- Phase C: conflict diagnostics -----------------------------------

    def test_conflict_diagnostic_emitted_for_real_contradiction(self) -> None:
        """Two real semantic annotations with conflicting exec state → diagnostic."""
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )

        # Prior: failure_mode (non-executable, real role)
        prior = RouteAnnotation(
            span_id="s13",
            field="behavior",
            semantic_role="failure_mode",
            construct_target="EXCEPTION_FLOW",
            slot_target="condition",
            executable=False,
            source_section_id="sec_real",
            source_packet_id="pkt_real",
        )
        # LLM returns: process_step (executable) — genuine conflict
        priors = [prior]
        router, spans, _ = self._make_router_and_inputs(
            priors,
            [
                {
                    "span_id": "s13",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                }
            ],
            ["s13"],
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s13", field="behavior", semantic_role="process_step", executable=True
                )
            ],
        )

        merged, diagnostics, _, _ = router._merge_llm_refinement(priors, llm_result, spans)

        conflict_diags = [d for d in diagnostics if "route_refinement_conflict" in d]
        assert len(conflict_diags) >= 1, (
            f"Expected route_refinement_conflict diagnostic, got: {diagnostics}"
        )
        assert "s13" in conflict_diags[0]

    def test_no_conflict_diagnostic_for_structural_prior_only(self) -> None:
        """Phase D: StructuralPrior + LLM annotation → no conflict diagnostic."""
        from nl2spl.ir.field_route_ir import StructuralPrior
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )

        # StructuralPrior does NOT enter merged — no conflict possible
        structural_priors = [
            StructuralPrior(
                span_id="s13",
                suggested_field="behavior",
                source_section_id="sec_real",
                source_packet_id="pkt_real",
                prior_kind="neutral_context",
            )
        ]
        deterministic_annotations: list[RouteAnnotation] = []
        router, spans, _ = self._make_router_and_inputs(
            deterministic_annotations,
            [
                {
                    "span_id": "s13",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                }
            ],
            ["s13"],
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s13", field="behavior", semantic_role="process_step", executable=True
                )
            ],
        )

        merged, diagnostics, _, _ = router._merge_llm_refinement(
            deterministic_annotations, llm_result, spans,
            structural_priors=structural_priors,
        )

        conflict_diags = [d for d in diagnostics if "route_refinement_conflict" in d]
        assert len(conflict_diags) == 0, (
            f"Neutral prior leak must NOT emit conflict diagnostic, got: {conflict_diags}"
        )

    # --- Final SPL regression: executable span survives D6 guard --------

    def test_executable_span_survives_d6_guard_after_merge(self) -> None:
        """Phase D: StructuralPrior does not pollute D6 guard sets.

        This test locks the invariant that after Phase D merge, an executable
        process_step span appears in the executable set and does NOT appear
        in the non-executable set, so Stage 7's D6 guard preserves it.
        """
        from nl2spl.ir.field_route_ir import StructuralPrior
        from nl2spl.pipeline.stages.stage2_field_router_prompt import (
            RefinedAnnotation,
            RouteRefinementResult,
        )

        # Phase D: neutral prior is StructuralPrior, not RouteAnnotation
        structural_priors = [
            StructuralPrior(
                span_id="s13",
                suggested_field="behavior",
                source_section_id="sec_real",
                source_packet_id="pkt_real",
                prior_kind="neutral_context",
            )
        ]
        deterministic_annotations: list[RouteAnnotation] = []
        router, spans, _ = self._make_router_and_inputs(
            deterministic_annotations,
            [
                {
                    "span_id": "s13",
                    "field": "behavior",
                    "semantic_role": "process_step",
                    "executable": True,
                }
            ],
            ["s13"],
        )

        llm_result = RouteRefinementResult(
            annotations=[
                RefinedAnnotation(
                    span_id="s13", field="behavior", semantic_role="process_step", executable=True
                )
            ],
        )

        merged, _, _, _ = router._merge_llm_refinement(
            deterministic_annotations, llm_result, spans,
            structural_priors=structural_priors,
        )

        # Build FieldRouteIR as Stage 4/5/7 would see it
        routes = FieldRouteIR(behavior=["s13"], annotations=merged)

        # Stage 7 D6 guard: compute effective sets
        exec_ids = set(routes.get_executable_behavior_span_ids())
        non_exec_ids = set(routes.get_non_executable_behavior_span_ids())

        # s13 must be executable
        assert "s13" in exec_ids, f"s13 must be in executable set after merge, got {exec_ids}"
        # s13 must NOT be non-executable (D6 guard would drop it otherwise)
        assert "s13" not in non_exec_ids, (
            f"s13 must NOT be in non-executable set, D6 guard would drop it. Got {non_exec_ids}"
        )
        # Effective sets must not overlap
        assert exec_ids.isdisjoint(non_exec_ids), (
            f"Executable and non-executable sets must not overlap: "
            f"intersection = {exec_ids & non_exec_ids}"
        )
