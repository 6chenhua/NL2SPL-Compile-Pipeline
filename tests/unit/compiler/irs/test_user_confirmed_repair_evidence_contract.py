"""Phase U1: User-Confirmed Repair Evidence Contract Tests.

Post-U1 verification that ``user_confirmed_repair`` evidence flows through
all post-normalize step command checkers with proper evidence/structure separation.

Design rule: tests assert on slot-level facts (status, diagnostic_kind,
slot_name, renderable) — never on full diagnostic message strings.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.post_normalize import PostNormalizeIRSCheckerV6
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.instance import ConstructInstance
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR


# =============================================================================
# Helpers
# =============================================================================


def _step(
    *,
    step_id: str = "st_1",
    command_type: str = "GENERAL_COMMAND",
    text: str = "Do something.",
    outputs: tuple[str, ...] = (),
    source_span_ids: tuple[str, ...] = (),
    origin: str | None = None,
    integration_ref: str | None = None,
    handoff_id: str | None = None,
    repair_patch_id: str | None = None,
    related_diagnostic_id: str | None = None,
    user_text: str | None = None,
) -> StepIR:
    """Build a minimal StepIR, optionally with user_confirmed_repair metadata."""
    metadata: dict[str, str] = {}
    if origin is not None:
        metadata["origin"] = origin
    if repair_patch_id is not None:
        metadata["repair_patch_id"] = repair_patch_id
    if related_diagnostic_id is not None:
        metadata["related_diagnostic_id"] = related_diagnostic_id
    if user_text is not None:
        metadata["user_text"] = user_text

    return StepIR(
        step_id=step_id,
        text=text,
        source_span_ids=list(source_span_ids),
        command_type=command_type,
        outputs=list(outputs),
        integration_ref=integration_ref,
        handoff_id=handoff_id,
        metadata=metadata,
    )


def _worker(steps: list[StepIR]) -> WorkerIR:
    """Build a minimal WorkerIR carrying the given steps."""
    return WorkerIR(
        worker_name="MainWorker",
        description="Test worker",
        steps=steps,
    )


def _worker_plan() -> WorkerPlanIR:
    """Build a minimal WorkerPlanIR with a main worker spec and no handoffs."""
    spec = WorkerSpecIR(
        worker_id="worker_main",
        worker_name="MainWorker",
        kind="main",
        purpose="test",
        boundary_kind="main_worker",
        output_contract=[],
    )
    return WorkerPlanIR(main_worker_id="worker_main", workers=[spec])


def _build_instance(step: StepIR, worker_id: str = "worker_main") -> ConstructInstance:
    """Build a ConstructInstance matching what ``_append_step_instance`` creates."""
    return ConstructInstance(
        construct_id=f"worker:{worker_id}.step:{step.step_id}",
        construct_type=step.command_type,
        ir_ref=step,
        materialized=True,
        source_demanded=bool(step.source_span_ids),
        primary_parent_id=f"worker:{worker_id}",
        construct_path=("worker", worker_id, "steps", step.step_id),
        source_span_ids=list(step.source_span_ids),
        metadata={"kind": "step", "step": step, "worker_id": worker_id},
    )


def _context(
    *,
    worker: WorkerIR | None = None,
    worker_plan: WorkerPlanIR | None = None,
) -> IRSCheckContext:
    """Build a minimal IRSCheckContext for the post-normalize checker."""
    return IRSCheckContext(
        stage_name="post_normalize",
        resources=ResourceRegistryIR(),
        normalized_ir=worker,
        worker_plan=worker_plan,
    )


@pytest.fixture
def checker() -> PostNormalizeIRSCheckerV6:
    return PostNormalizeIRSCheckerV6()


@pytest.fixture
def registry() -> SPLConstructRegistry:
    return SPLConstructRegistry.default()


# =============================================================================
# source_evidence_slot — CORRECT BASELINE
# =============================================================================


class TestSourceEvidenceSlot:
    """``_source_evidence_slot()`` correctly handles all evidence kinds."""

    def test_ucr_returns_satisfied(self, checker: PostNormalizeIRSCheckerV6) -> None:
        step = _step(command_type="GENERAL_COMMAND", origin="user_confirmed_repair")
        slot = PostNormalizeIRSCheckerV6._source_evidence_slot(step, None, set())
        assert slot.status == "satisfied"
        assert slot.relation == "inferred"

    def test_ucr_with_outputs_satisfied(self, checker: PostNormalizeIRSCheckerV6) -> None:
        step = _step(
            command_type="REQUEST_INPUT",
            outputs=("user_answer",),
            origin="user_confirmed_repair",
        )
        slot = PostNormalizeIRSCheckerV6._source_evidence_slot(step, None, set())
        assert slot.status == "satisfied"

    def test_source_span_still_priority(self, checker: PostNormalizeIRSCheckerV6) -> None:
        step = _step(
            command_type="GENERAL_COMMAND",
            source_span_ids=("s1",),
            origin="user_confirmed_repair",
        )
        slot = PostNormalizeIRSCheckerV6._source_evidence_slot(step, None, set())
        assert slot.status == "satisfied"
        assert slot.relation == "direct"

    def test_unconfirmed_no_source_still_missing(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        step = _step(command_type="GENERAL_COMMAND")
        irs = registry.get("GENERAL_COMMAND")
        assert irs is not None
        slot = PostNormalizeIRSCheckerV6._source_evidence_slot(step, irs, set())
        assert slot.status == "missing"
        assert slot.diagnostic_kind is not None


# =============================================================================
# GENERAL_COMMAND — CORRECT BASELINE
# =============================================================================


class TestGeneralCommandUCR:
    """GENERAL_COMMAND with UCR is fully renderable (correct baseline, preserved)."""

    def test_ucr_renderable(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        step = _step(
            command_type="GENERAL_COMMAND",
            text="Update the database.",
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("GENERAL_COMMAND")
        assert irs is not None

        report = checker._check_general_command(
            _build_instance(step), step, irs, set(),
        )
        assert report.renderable is True
        assert report.completeness == "complete"

        action = _find_slot(report, "action_text")
        assert action is not None
        assert action.status == "satisfied"

        evidence = _find_slot(report, "source_evidence")
        assert evidence is not None
        assert evidence.status == "satisfied"


# =============================================================================
# REQUEST_INPUT — FIXED
# =============================================================================


class TestRequestInputUCR:
    """REQUEST_INPUT with UCR: evidence satisfies source_evidence slot,
    but structure slots (prompt_text, value_target) are independently checked."""

    def test_with_text_and_outputs_is_complete(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        """UCR + text + outputs → complete and renderable."""
        step = _step(
            command_type="REQUEST_INPUT",
            text="Please provide your name.",
            outputs=("user_name",),
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("REQUEST_INPUT")
        assert irs is not None

        report = checker._check_request_input(
            _build_instance(step), step, irs, set(),
        )

        prompt = _find_slot(report, "prompt_text")
        assert prompt is not None
        assert prompt.status == "satisfied"

        value_target = _find_slot(report, "value_target")
        assert value_target is not None
        assert value_target.status == "satisfied"

        evidence = _find_slot(report, "source_evidence")
        assert evidence is not None
        assert evidence.status == "satisfied"

        assert report.renderable is True
        assert report.completeness == "complete"

    def test_no_outputs_value_target_missing_not_renderable(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        """UCR cannot compensate for missing outputs → value_target missing, not renderable."""
        step = _step(
            command_type="REQUEST_INPUT",
            text="Ask user something.",
            outputs=(),
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("REQUEST_INPUT")
        assert irs is not None

        report = checker._check_request_input(
            _build_instance(step), step, irs, set(),
        )

        evidence = _find_slot(report, "source_evidence")
        assert evidence is not None
        assert evidence.status == "satisfied"

        value_target = _find_slot(report, "value_target")
        assert value_target is not None
        assert value_target.status == "missing"

        assert report.renderable is False

    def test_no_text_prompt_missing(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        """Empty step.text → prompt_text missing regardless of UCR."""
        step = _step(
            command_type="REQUEST_INPUT",
            text="",
            outputs=("answer",),
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("REQUEST_INPUT")
        assert irs is not None

        report = checker._check_request_input(
            _build_instance(step), step, irs, set(),
        )

        prompt = _find_slot(report, "prompt_text")
        assert prompt is not None
        assert prompt.status == "missing"
        assert report.renderable is False

    def test_no_outputs_value_target_remains_missing(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        """Even with UCR and text, missing outputs still means missing value_target."""
        step = _step(
            command_type="REQUEST_INPUT",
            text="Enter something.",
            outputs=(),
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("REQUEST_INPUT")
        assert irs is not None

        report = checker._check_request_input(
            _build_instance(step), step, irs, set(),
        )

        value_target = _find_slot(report, "value_target")
        assert value_target is not None
        assert value_target.status == "missing"


# =============================================================================
# CALL_API — FIXED
# =============================================================================


class TestCallAPIUCR:
    """CALL_API with UCR: evidence satisfies call_action, but api_name still
    requires integration_ref to be declared."""

    def test_with_valid_declared_api_is_complete(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        """UCR + text + declared API → complete and renderable."""
        step = _step(
            command_type="CALL_API",
            text="Fetch weather data.",
            integration_ref="WeatherAPI",
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("CALL_API")
        assert irs is not None

        report = checker._check_call_api(
            _build_instance(step), step, irs, {"WeatherAPI"}, set(), {},
        )

        api_name = _find_slot(report, "api_name")
        assert api_name is not None
        assert api_name.status == "satisfied"

        call_action = _find_slot(report, "call_action")
        assert call_action is not None
        assert call_action.status == "satisfied"

        assert report.renderable is True

    def test_with_declared_api_and_text_is_satisfied(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        """call_action slot is satisfied for UCR step with text and declared API."""
        step = _step(
            command_type="CALL_API",
            text="Call the SendEmail API.",
            integration_ref="SendEmail",
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("CALL_API")
        assert irs is not None

        report = checker._check_call_api(
            _build_instance(step), step, irs, {"SendEmail"}, set(), {},
        )
        call_action = _find_slot(report, "call_action")
        assert call_action is not None
        assert call_action.status == "satisfied"

    def test_missing_integration_ref_still_missing(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        """UCR does not compensate for missing integration_ref."""
        step = _step(
            command_type="CALL_API",
            text="Call something.",
            integration_ref=None,
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("CALL_API")
        assert irs is not None

        report = checker._check_call_api(
            _build_instance(step), step, irs, set(), set(), {},
        )
        api_name = _find_slot(report, "api_name")
        assert api_name is not None
        assert api_name.status == "missing"
        assert report.renderable is False

    def test_missing_integration_ref_not_renderable(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        """UCR CALL_API without integration_ref is not renderable."""
        step = _step(
            command_type="CALL_API",
            text="Do something.",
            integration_ref=None,
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("CALL_API")
        assert irs is not None

        report = checker._check_call_api(
            _build_instance(step), step, irs, set(), set(), {},
        )
        assert report.renderable is False


# =============================================================================
# INVOKE_WORKER
# =============================================================================


class TestInvokeWorkerUCR:
    """INVOKE_WORKER with UCR: handoff contract validation is the authority."""

    def test_with_refs_is_renderable(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        """INVOKE_WORKER UCR with integration_ref + handoff_id is renderable
        when handoff index is not provided (compat mode)."""
        step = _step(
            command_type="INVOKE_WORKER",
            text="Invoke child worker.",
            integration_ref="ChildWorker",
            handoff_id="h1",
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("INVOKE_WORKER")
        assert irs is not None

        report = checker._check_invoke_worker(
            _build_instance(step), step, irs,
        )
        # In compat mode (no handoff_index), handoff present and target present → renderable
        assert report.renderable is True

    def test_no_handoff_id_not_renderable(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        """UCR cannot compensate for missing handoff_id."""
        step = _step(
            command_type="INVOKE_WORKER",
            text="Invoke worker.",
            integration_ref="ChildWorker",
            handoff_id=None,
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("INVOKE_WORKER")
        assert irs is not None

        report = checker._check_invoke_worker(
            _build_instance(step), step, irs,
        )

        handoff_slot = _find_slot(report, "handoff_id")
        assert handoff_slot is not None
        assert handoff_slot.status == "missing"
        assert report.renderable is False

    def test_no_integration_ref_not_renderable(
        self, checker: PostNormalizeIRSCheckerV6, registry: SPLConstructRegistry
    ) -> None:
        """UCR cannot compensate for missing integration_ref."""
        step = _step(
            command_type="INVOKE_WORKER",
            text="Invoke something.",
            integration_ref=None,
            handoff_id="h1",
            origin="user_confirmed_repair",
        )
        worker = _worker([step])
        ctx = _context(worker=worker, worker_plan=_worker_plan())
        irs = registry.get("INVOKE_WORKER")
        assert irs is not None

        report = checker._check_invoke_worker(
            _build_instance(step), step, irs,
        )

        target_slot = _find_slot(report, "target_worker")
        assert target_slot is not None
        assert target_slot.status == "missing"
        assert report.renderable is False


# =============================================================================
# append_step_instance — FIXED
# =============================================================================


class TestAppendStepInstanceSourceDemanded:
    """source_demanded now accounts for all evidence sources, not just source spans."""

    def test_ucr_step_source_demanded_is_true(self) -> None:
        """U1 FIX: source_demanded is True for UCR step."""
        step = _step(
            command_type="GENERAL_COMMAND",
            origin="user_confirmed_repair",
        )
        instances: list = []
        PostNormalizeIRSCheckerV6._append_step_instance(instances, step, "worker_main")
        assert len(instances) == 1
        assert instances[0].source_demanded is True

    def test_source_backed_step_source_demanded_is_true(self) -> None:
        """Source-backed step still has source_demanded=True."""
        step = _step(
            command_type="GENERAL_COMMAND",
            source_span_ids=("s1",),
        )
        instances: list = []
        PostNormalizeIRSCheckerV6._append_step_instance(instances, step, "worker_main")
        assert len(instances) == 1
        assert instances[0].source_demanded is True


# =============================================================================
# Slot helpers
# =============================================================================


def _find_slot(report, slot_name: str):
    """Find a slot by name in a ConstructSatisfactionReport."""
    for slot in report.slots:
        if slot.slot_name == slot_name:
            return slot
    return None
