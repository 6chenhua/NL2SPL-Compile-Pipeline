"""End-to-End Acceptance: User-Confirmed REQUEST_INPUT Must Render.

This test proves the original bug is fixed:
    "用户明明已经确认REQUEST_INPUT，但是却被'拦住'，没有渲染出来"

Scenario:
    1. User confirms an AddExceptionHandlerStep repair that creates a
       REQUEST_INPUT step with prompt text + output variable
    2. The step has metadata.origin="user_confirmed_repair" and NO source spans
    3. post-normalize IRS must NOT emit false prompt/value diagnostics
    4. post-normalize IRS must report renderable=True, complete=True
    5. Gate must keep the step
    6. ProducerIndex must recognize it as a renderable producer
    7. The step carries full repair provenance (repair_patch_id,
       related_diagnostic_id, user_text)

This is the canonical acceptance test per §16.1 of the implementation plan.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.post_normalize import PostNormalizeIRSCheckerV6
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.instance import ConstructInstance
from nl2spl.compiler.producer_index import ProducerIndex, _step_is_renderable
from nl2spl.compiler.evidence import classify_step_evidence, StepEvidenceKind
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR


# =============================================================================
# The canonical UCR REQUEST_INPUT step (as produced by AddExceptionHandlerStep)
# =============================================================================


def _ucr_request_input_step() -> StepIR:
    """Build the exact StepIR that AddExceptionHandlerStep would produce."""
    return StepIR(
        step_id="st_repair_1_worker_main",
        text="Please provide your name.",
        source_span_ids=[],  # <-- THE KEY: no source spans
        command_type="REQUEST_INPUT",
        outputs=["user_name"],
        metadata={
            "origin": "user_confirmed_repair",
            "repair_patch_id": "patch_001",
            "related_diagnostic_id": "diag_missing_handler_abc",
            "user_text": "The user confirmed: add an INPUT step to collect name.",
        },
    )


# =============================================================================
# Helpers
# =============================================================================


def _build_instance(step: StepIR) -> ConstructInstance:
    return ConstructInstance(
        construct_id=f"worker:worker_main.step:{step.step_id}",
        construct_type=step.command_type,
        ir_ref=step,
        materialized=True,
        source_demanded=True,  # U1 fix: UCR makes it demanded
        primary_parent_id="worker:worker_main",
        construct_path=("worker", "worker_main", "steps", step.step_id),
        source_span_ids=[],
        metadata={"kind": "step", "step": step, "worker_id": "worker_main"},
    )


def _context() -> IRSCheckContext:
    return IRSCheckContext(
        stage_name="post_normalize",
        resources=ResourceRegistryIR(),
        normalized_ir=WorkerIR(
            worker_name="MainWorker",
            description="Test",
            steps=[_ucr_request_input_step()],
        ),
        worker_plan=WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="test",
                boundary_kind="main_worker",
                output_contract=[],
            )],
        ),
    )


# =============================================================================
# E2E tests
# =============================================================================


class TestE2EUserConfirmedRequestInput:
    """The definitive end-to-end test suite proving the bug is fixed.

    If any test here fails, the user's REQUEST_INPUT is still being blocked.
    """

    # -- Test 1: evidence classification --------------------------------

    def test_ucr_evidence_classification(self) -> None:
        """Classify: UCR step is classified as USER_CONFIRMED_REPAIR."""
        step = _ucr_request_input_step()
        evidence = classify_step_evidence(step)
        assert evidence.primary_kind == StepEvidenceKind.USER_CONFIRMED_REPAIR
        assert evidence.satisfied is True
        assert evidence.is_user_confirmed() is True
        assert evidence.repair_metadata_complete() is True
        assert evidence.repair_patch_id == "patch_001"
        assert evidence.related_diagnostic_id == "diag_missing_handler_abc"
        assert evidence.user_text == "The user confirmed: add an INPUT step to collect name."

    # -- Test 2: post-normalize IRS — the original bug -------------------

    def test_post_normalize_irs_accepts_ucr_request_input(self) -> None:
        """THE CORE FIX: post-normalize IRS must not block UCR REQUEST_INPUT."""
        checker = PostNormalizeIRSCheckerV6()
        step = _ucr_request_input_step()
        ctx = _context()
        registry = SPLConstructRegistry.default()
        irs = registry.get("REQUEST_INPUT")
        assert irs is not None

        report = checker._check_request_input(
            _build_instance(step), step, irs, set(),
        )

        # 1. prompt_text must be SATISFIED (was "missing" before U1 fix)
        prompt = _find_slot(report, "prompt_text")
        assert prompt is not None
        assert prompt.status == "satisfied", (
            f"ORIGINAL BUG: prompt_text is '{prompt.status}' — "
            f"user-confirmed REQUEST_INPUT was blocked because the checker "
            f"required source_span_ids for prompt_text."
        )
        assert prompt.diagnostic_kind is None

        # 2. value_target must be SATISFIED (was "missing" before U1 fix)
        value_target = _find_slot(report, "value_target")
        assert value_target is not None
        assert value_target.status == "satisfied", (
            f"ORIGINAL BUG: value_target is '{value_target.status}' — "
            f"user-confirmed REQUEST_INPUT was blocked because the checker "
            f"required source_span_ids for value_target."
        )

        # 3. source_evidence must be SATISFIED (this one always worked)
        evidence = _find_slot(report, "source_evidence")
        assert evidence is not None
        assert evidence.status == "satisfied"

        # 4. The step MUST be renderable
        assert report.renderable is True, (
            f"ORIGINAL BUG: REQUEST_INPUT is NOT renderable — "
            f"the user confirmed a repair, but the IRS blocked rendering "
            f"because source_backed was False."
        )

        # 5. Completeness must be "complete"
        assert report.completeness == "complete"

    def test_post_normalize_irs_no_false_diagnostics(self) -> None:
        """No false 'assumed_command_not_renderable' for UCR REQUEST_INPUT."""
        checker = PostNormalizeIRSCheckerV6()
        step = _ucr_request_input_step()
        ctx = _context()
        registry = SPLConstructRegistry.default()
        irs = registry.get("REQUEST_INPUT")
        assert irs is not None

        report = checker._check_request_input(
            _build_instance(step), step, irs, set(),
        )

        for slot in report.slots:
            assert slot.diagnostic_kind != "assumed_command_not_renderable", (
                f"ORIGINAL BUG: slot '{slot.slot_name}' has diagnostic "
                f"'assumed_command_not_renderable' — this was the false "
                f"diagnostic that blocked UCR REQUEST_INPUT from rendering."
            )

    # -- Test 3: structural constraint — UCR does NOT bypass structure -----

    def test_ucr_no_outputs_still_blocked(self) -> None:
        """UCR evidence does NOT compensate for missing outputs."""
        checker = PostNormalizeIRSCheckerV6()
        step = StepIR(
            step_id="st_bad",
            text="Ask something.",
            source_span_ids=[],
            command_type="REQUEST_INPUT",
            outputs=[],  # <-- missing outputs
            metadata={"origin": "user_confirmed_repair"},
        )
        ctx = _context()
        registry = SPLConstructRegistry.default()
        irs = registry.get("REQUEST_INPUT")
        assert irs is not None

        report = checker._check_request_input(
            _build_instance(step), step, irs, set(),
        )

        # Evidence is satisfied
        evidence = _find_slot(report, "source_evidence")
        assert evidence is not None
        assert evidence.status == "satisfied"

        # Value_target still missing — structure NOT bypassed
        value_target = _find_slot(report, "value_target")
        assert value_target is not None
        assert value_target.status == "missing"

        # Not renderable — correct
        assert report.renderable is False

    # -- Test 4: Gate acceptance -----------------------------------------

    def test_gate_accepts_ucr_request_input(self) -> None:
        """Gate must NOT filter out UCR REQUEST_INPUT."""
        from nl2spl.pipeline.executable_gate import ExecutableElementGate
        step = _ucr_request_input_step()
        gate = ExecutableElementGate()
        origin = gate.classify_origin(step)
        assert origin == "user_confirmed_repair"
        ok, reason = gate.is_renderable(step, origin, {}, set(), {})
        assert ok is True, f"ORIGINAL BUG: Gate blocked UCR REQUEST_INPUT: {reason}"

    # -- Test 5: ProducerIndex recognition -------------------------------

    def test_producer_index_recognizes_ucr_producer(self) -> None:
        """ProducerIndex must recognize UCR step as renderable producer."""
        step = _ucr_request_input_step()
        assert _step_is_renderable(step) is True, (
            "ORIGINAL BUG: ProducerIndex did not recognize UCR step as renderable"
        )
        index = ProducerIndex(steps=[step])
        assert index.is_produced("user_name"), (
            "ORIGINAL BUG: UCR step output not recognized as produced"
        )

    # -- Test 6: Full provenance trace -----------------------------------

    def test_ucr_step_trace_is_not_assumed(self) -> None:
        """Provenance trace must NOT mark UCR step as 'assumed'."""
        from nl2spl.pipeline.provenance import ProvenanceAggregator

        step = _ucr_request_input_step()
        aggregator = ProvenanceAggregator()
        spans: dict = {}
        traces: list = []
        diags: list = []
        aggregator._trace_steps([step], spans, traces, diags)

        trace = traces[0]
        assert trace.relation == "user_confirmed_repair", (
            f"ORIGINAL BUG: provenance relation is '{trace.relation}' — "
            f"UCR step was treated as inferred/assumed instead of "
            f"user_confirmed_repair."
        )
        assert trace.needs_confirmation is False, (
            "ORIGINAL BUG: provenance says needs_confirmation=True for "
            "user-confirmed repair step."
        )
        assert trace.metadata.get("repair_patch_id") == "patch_001"
        assert trace.metadata.get("related_diagnostic_id") == "diag_missing_handler_abc"
        assert trace.metadata.get("user_text") == (
            "The user confirmed: add an INPUT step to collect name."
        )

    # -- Test 7: Cross-layer consistency ---------------------------------

    def test_all_authorities_agree(self) -> None:
        """UCR REQUEST_INPUT is accepted by IRS, Gate, ProducerIndex, and Evidence."""
        step = _ucr_request_input_step()

        # Evidence
        evidence = classify_step_evidence(step)
        assert evidence.satisfied is True

        # IRS (post-normalize)
        checker = PostNormalizeIRSCheckerV6()
        registry = SPLConstructRegistry.default()
        irs = registry.get("REQUEST_INPUT")
        assert irs is not None
        report = checker._check_request_input(
            _build_instance(step), step, irs, set(),
        )
        assert report.renderable is True

        # Gate
        from nl2spl.pipeline.executable_gate import ExecutableElementGate
        gate = ExecutableElementGate()
        origin = gate.classify_origin(step)
        ok, _ = gate.is_renderable(step, origin, {}, set(), {})
        assert ok is True

        # ProducerIndex
        assert _step_is_renderable(step) is True

        # All authorities agree: the step IS renderable


# =============================================================================
# Slot helpers
# =============================================================================


def _find_slot(report, slot_name: str):
    for slot in report.slots:
        if slot.slot_name == slot_name:
            return slot
    return None
