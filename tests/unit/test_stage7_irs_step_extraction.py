"""Unit tests for Stage 7 IRS step-level checker."""

from unittest.mock import MagicMock, patch

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.stages.stage7_step_extractor.extractor import StepExtractor
from nl2spl.pipeline.stages.stage7_step_extractor.irs_checker import (
    check_steps_irs,
    check_worker_step_plan_irs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _step(
    step_id: str = "st_1",
    command_type: str = "GENERAL_COMMAND",
    text: str = "Process data",
    source_span_ids: list[str] | None = None,
    integration_ref: str | None = None,
    handoff_id: str | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
) -> StepIR:
    return StepIR(
        step_id=step_id,
        text=text,
        source_span_ids=source_span_ids or [],
        command_type=command_type,
        inputs=inputs or [],
        outputs=outputs or [],
        integration_ref=integration_ref,
        flow_ref="main",
        block_ref="b_1",
        handoff_id=handoff_id,
    )


def _find_slot(report, slot_name: str):
    for s in report.slots:
        if s.slot_name == slot_name:
            return s
    raise KeyError(slot_name)


# ---------------------------------------------------------------------------
# GENERAL_COMMAND
# ---------------------------------------------------------------------------

class TestGeneralCommand:
    def test_source_backed_is_complete_and_renderable(self):
        step = _step("st_1", source_span_ids=["s1"])
        reports, diags = check_steps_irs([step])
        assert len(reports) == 1
        assert reports[0].completeness == "complete"
        assert reports[0].renderable is True
        assert len(diags) == 0

    def test_no_source_span_is_assumed_command(self):
        step = _step("st_1", source_span_ids=[])
        reports, diags = check_steps_irs([step])
        assert len(diags) == 1
        assert diags[0].kind == "assumed_command_not_renderable"
        assert reports[0].renderable is False
        assert reports[0].completeness == "partial"

    def test_source_evidence_slot_satisfied(self):
        step = _step("st_1", source_span_ids=["s1", "s2"])
        reports, _ = check_steps_irs([step])
        slot = _find_slot(reports[0], "source_evidence")
        assert slot.status == "satisfied"
        assert slot.relation == "direct"

    def test_source_evidence_slot_missing(self):
        step = _step("st_1", source_span_ids=[])
        reports, _ = check_steps_irs([step])
        slot = _find_slot(reports[0], "source_evidence")
        assert slot.status == "missing"
        assert slot.diagnostic_kind == "assumed_command_not_renderable"

    def test_action_text_always_satisfied(self):
        step = _step("st_1", text="Compute the result")
        reports, _ = check_steps_irs([step])
        slot = _find_slot(reports[0], "action_text")
        assert slot.status == "satisfied"

    def test_result_variable_satisfied_when_outputs_present(self):
        step = _step("st_1", source_span_ids=["s1"], outputs=["result"])
        reports, _ = check_steps_irs([step])
        slot = _find_slot(reports[0], "result_variable")
        assert slot.status == "satisfied"


# ---------------------------------------------------------------------------
# REQUEST_INPUT
# ---------------------------------------------------------------------------

class TestRequestInput:
    def test_source_backed_is_complete(self):
        step = _step("st_1", command_type="REQUEST_INPUT", text="Ask user for preference", source_span_ids=["s1"])
        reports, diags = check_steps_irs([step])
        assert len(reports) == 1
        assert reports[0].completeness == "complete"
        assert reports[0].renderable is True
        assert len(diags) == 0

    def test_no_source_span_is_type_or_contract_ambiguity(self):
        step = _step("st_1", command_type="REQUEST_INPUT", text="Ask user", source_span_ids=[])
        reports, diags = check_steps_irs([step])
        assert len(diags) == 1
        assert diags[0].kind == "type_or_contract_ambiguity"
        assert "ask/request/prompt" in diags[0].message.lower()

    def test_prompt_text_always_satisfied(self):
        step = _step("st_1", command_type="REQUEST_INPUT", text="Please enter your name")
        reports, _ = check_steps_irs([step])
        slot = _find_slot(reports[0], "prompt_text")
        assert slot.status == "satisfied"


# ---------------------------------------------------------------------------
# CALL_API
# ---------------------------------------------------------------------------

class TestCallAPI:
    def test_full_source_backed_is_complete(self):
        step = _step("st_1", command_type="CALL_API", text="Call SendGrid",
                     source_span_ids=["s1"], integration_ref="SendGrid")
        reports, diags = check_steps_irs([step])
        assert reports[0].completeness == "complete"
        assert reports[0].renderable is True
        assert len(diags) == 0

    def test_missing_integration_ref_is_ambiguous(self):
        step = _step("st_1", command_type="CALL_API", text="Call API",
                     source_span_ids=["s1"], integration_ref=None)
        reports, diags = check_steps_irs([step])
        assert any(d.kind == "type_or_contract_ambiguity" for d in diags)
        assert "integration_ref" in " ".join(d.message for d in diags).lower()

    def test_missing_source_spans_is_ambiguous(self):
        step = _step("st_1", command_type="CALL_API", text="Call SendGrid",
                     source_span_ids=[], integration_ref="SendGrid")
        reports, diags = check_steps_irs([step])
        assert any(d.kind == "type_or_contract_ambiguity" for d in diags)
        assert "source-span" in " ".join(d.message for d in diags)

    def test_both_missing_produces_two_diagnostics(self):
        step = _step("st_1", command_type="CALL_API", text="Call API",
                     source_span_ids=[], integration_ref=None)
        _, diags = check_steps_irs([step])
        assert len(diags) == 2
        kinds = {d.kind for d in diags}
        assert kinds == {"type_or_contract_ambiguity"}

    def test_api_name_slot_satisfied(self):
        step = _step("st_1", command_type="CALL_API", source_span_ids=["s1"], integration_ref="Stripe")
        reports, _ = check_steps_irs([step])
        slot = _find_slot(reports[0], "api_name")
        assert slot.status == "satisfied"


# ---------------------------------------------------------------------------
# INVOKE_WORKER
# ---------------------------------------------------------------------------

class TestInvokeWorker:
    def test_handoff_id_and_target_present_is_complete(self):
        step = _step("st_1", command_type="INVOKE_WORKER", text="Invoke source worker",
                     handoff_id="handoff_1", integration_ref="WorkerSource")
        reports, diags = check_steps_irs([step])
        assert reports[0].completeness == "complete"
        assert reports[0].renderable is True
        assert len(diags) == 0

    def test_missing_handoff_id_is_ambiguous(self):
        step = _step("st_1", command_type="INVOKE_WORKER", text="Invoke worker",
                     handoff_id=None, integration_ref="WorkerX")
        reports, diags = check_steps_irs([step])
        assert any(d.kind == "type_or_contract_ambiguity" for d in diags)
        assert any("handoff_id" in d.message for d in diags)

    def test_missing_target_worker_is_ambiguous(self):
        step = _step("st_1", command_type="INVOKE_WORKER", text="Invoke worker",
                     handoff_id="handoff_1", integration_ref=None)
        reports, diags = check_steps_irs([step])
        assert any(d.kind == "type_or_contract_ambiguity" for d in diags)
        assert any("integration_ref" in d.message for d in diags)


# ---------------------------------------------------------------------------
# DISPLAY_MESSAGE (skipped)
# ---------------------------------------------------------------------------

class TestSkippedTypes:
    def test_display_message_is_skipped(self):
        step = _step("st_1", command_type="DISPLAY_MESSAGE", text="Show result")
        reports, diags = check_steps_irs([step])
        assert reports == []
        assert diags == []

    def test_unknown_type_is_skipped(self):
        step = _step("st_1", command_type="UNKNOWN_TYPE", text="???")
        reports, diags = check_steps_irs([step])
        assert reports == []
        assert diags == []


# ---------------------------------------------------------------------------
# Mixed steps
# ---------------------------------------------------------------------------

class TestMixedSteps:
    def test_mixed_valid_and_invalid_steps(self):
        steps = [
            _step("st_1", command_type="GENERAL_COMMAND", source_span_ids=["s1"]),
            _step("st_2", command_type="REQUEST_INPUT", source_span_ids=[]),
            _step("st_3", command_type="CALL_API", integration_ref=None, source_span_ids=["s3"]),
            _step("st_4", command_type="INVOKE_WORKER", handoff_id="h1", integration_ref="W"),
            _step("st_5", command_type="DISPLAY_MESSAGE"),
        ]
        reports, diags = check_steps_irs(steps)
        # st_5 is skipped; st_2, st_3 have issues
        assert len(reports) == 4
        # st_2: 1 diag, st_3: 1 diag (missing integration_ref)
        assert len(diags) == 2

    def test_empty_steps_produces_nothing(self):
        reports, diags = check_steps_irs([])
        assert reports == []
        assert diags == []


# ---------------------------------------------------------------------------
# Diagnostic ID uniqueness
# ---------------------------------------------------------------------------

class TestDiagnosticIDUniqueness:
    def test_unique_diagnostic_ids_legacy(self):
        steps = [
            _step("st_1", command_type="GENERAL_COMMAND", source_span_ids=[]),
            _step("st_2", command_type="REQUEST_INPUT", source_span_ids=[]),
        ]
        _, diags = check_steps_irs(steps)
        ids = {d.diagnostic_id for d in diags}
        assert len(ids) == 2
        # R6.4: diagnostic_id format changed to irs_{hash}
        assert all(did.startswith("irs_") for did in ids)

    def test_unique_ids_per_slot_same_step_call_api(self):
        step = _step("st_1", command_type="CALL_API", integration_ref=None, source_span_ids=[])
        _, diags = check_steps_irs([step])
        assert len(diags) == 2
        ids = {d.diagnostic_id for d in diags}
        assert len(ids) == 2, f"duplicate IDs: {ids}"
        # R6.4: different slots produce different irs_{hash} IDs
        assert all(did.startswith("irs_") for did in ids)

    def test_unique_ids_per_slot_same_step_invoke_worker(self):
        step = _step("st_1", command_type="INVOKE_WORKER", integration_ref=None, handoff_id=None)
        _, diags = check_steps_irs([step])
        assert len(diags) == 2
        ids = {d.diagnostic_id for d in diags}
        assert len(ids) == 2, f"duplicate IDs: {ids}"
        # R6.4: different slots produce different irs_{hash} IDs
        assert all(did.startswith("irs_") for did in ids)


# ---------------------------------------------------------------------------
# Worker-aware path
# ---------------------------------------------------------------------------

class TestWorkerAwarePath:
    def test_worker_scoped_construct_ids(self):
        plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    _step("st_1", command_type="GENERAL_COMMAND", source_span_ids=["s1"]),
                ],
            },
        )
        reports, _ = check_worker_step_plan_irs(plan)
        assert len(reports) == 1
        assert reports[0].construct_id == "worker:worker_main.step:st_1"

    def test_multiple_workers(self):
        plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    _step("st_1", command_type="GENERAL_COMMAND", source_span_ids=["s1"]),
                ],
                "child_worker": [
                    _step("st_2", command_type="CALL_API", integration_ref=None, source_span_ids=[]),
                ],
            },
        )
        reports, diags = check_worker_step_plan_irs(plan)
        assert len(reports) == 2
        assert len(diags) >= 1  # CALL_API has 2 issues

    def test_unique_diagnostic_ids_across_workers(self):
        plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    _step("st_1", command_type="GENERAL_COMMAND", source_span_ids=[]),
                ],
                "child_review": [
                    _step("st_1", command_type="REQUEST_INPUT", source_span_ids=[]),
                ],
            },
        )
        _, diags = check_worker_step_plan_irs(plan)
        ids = {d.diagnostic_id for d in diags}
        assert len(ids) == 2
        # R6.4: diagnostic_id format changed to irs_{hash}
        assert all(did.startswith("irs_") for did in ids)

    def test_target_ref_includes_worker(self):
        plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    _step("st_1", command_type="GENERAL_COMMAND", source_span_ids=[]),
                ],
            },
        )
        _, diags = check_worker_step_plan_irs(plan)
        assert diags[0].target_ref == "worker:worker_main.step:st_1"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self):
        steps = [_step("st_1", command_type="GENERAL_COMMAND", source_span_ids=[])]
        a_r, a_d = check_steps_irs(steps)
        b_r, b_d = check_steps_irs(steps)
        assert len(a_r) == len(b_r)
        assert len(a_d) == len(b_d)
        assert a_d[0].diagnostic_id == b_d[0].diagnostic_id


# ---------------------------------------------------------------------------
# Custom registry
# ---------------------------------------------------------------------------

class TestCustomRegistry:
    def test_accepts_custom_registry(self):
        registry = SPLConstructRegistry.default()
        steps = [_step("st_1", source_span_ids=["s1"])]
        reports, _ = check_steps_irs(steps, registry=registry)
        assert len(reports) == 1


# ---------------------------------------------------------------------------
# Construct type mapping
# ---------------------------------------------------------------------------

class TestConstructMapping:
    @pytest.mark.parametrize("cmd_type, expected", [
        ("GENERAL_COMMAND", "GENERAL_COMMAND"),
        ("REQUEST_INPUT", "REQUEST_INPUT"),
        ("CALL_API", "CALL_API"),
        ("INVOKE_WORKER", "INVOKE_WORKER"),
    ])
    def test_command_type_maps_to_construct(self, cmd_type, expected):
        step = _step("st_1", command_type=cmd_type, source_span_ids=["s1"],
                     integration_ref="X", handoff_id="h1")
        reports, _ = check_steps_irs([step])
        assert reports[0].construct_type == expected


# ---------------------------------------------------------------------------
# Prompt injection tests
# ---------------------------------------------------------------------------

class TestPromptInjection:
    def _make_stage(self, flag_enabled: bool) -> StepExtractor:
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
        )
        return StepExtractor(config, MagicMock())

    def _spans(self) -> list[SpanIR]:
        return [SpanIR("s1", "Process the request.")]

    def _routes(self) -> FieldRouteIR:
        return FieldRouteIR(behavior=["s1"])

    def _flow(self) -> FlowStructureIR:
        return FlowStructureIR(main_flow_spans=["s1"])

    def _blocks(self) -> BlockStructureIR:
        return BlockStructureIR(main_flow_blocks=[])

    def _symbols(self) -> SymbolTable:
        return SymbolTable()

    def test_flag_off_no_irs_checklist_in_prompt(self):
        """When flag is False, system prompt must NOT contain IRS checklist."""
        stage = self._make_stage(flag_enabled=False)
        captured_prompt: list[str] = []

        def fake_call_json(*, stage_name, system_prompt, user_prompt):
            captured_prompt.append(system_prompt)
            return {"steps": [], "new_variables": []}

        stage.client.call_json = fake_call_json
        stage.execute((self._spans(), self._routes(), self._flow(), self._blocks(), self._symbols()))

        assert len(captured_prompt) == 1
        assert "CONSTRUCT:" not in captured_prompt[0]
        assert "IRS-Driven Construct Checklist" not in captured_prompt[0]

    def test_config_does_not_inject_irs_checklist(self):
        """Stage-local IRS checklist injection is removed."""
        stage = self._make_stage(flag_enabled=True)
        captured_prompt: list[str] = []

        def fake_call_json(*, stage_name, system_prompt, user_prompt):
            captured_prompt.append(system_prompt)
            return {"steps": [], "new_variables": []}

        stage.client.call_json = fake_call_json
        stage.execute((self._spans(), self._routes(), self._flow(), self._blocks(), self._symbols()))

        assert len(captured_prompt) == 1
        assert "CONSTRUCT:" not in captured_prompt[0]
        assert "IRS-Driven Construct Checklist" not in captured_prompt[0]


# ---------------------------------------------------------------------------
# Worker-scoped prompt injection tests
# ---------------------------------------------------------------------------

class TestWorkerScopedPromptInjection:
    def _make_stage(self, flag_enabled: bool) -> StepExtractor:
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
        )
        return StepExtractor(config, MagicMock())

    def _spans(self) -> list[SpanIR]:
        return [SpanIR("s1", "Process the request.")]

    def _routes(self) -> FieldRouteIR:
        return FieldRouteIR(behavior=["s1"])

    def _symbols(self) -> SymbolTable:
        return SymbolTable()

    def _worker_plan(self) -> WorkerPlanIR:
        main = WorkerSpecIR(
            worker_id="worker_main", worker_name="Main", kind="main",
            purpose="Main worker", owned_span_ids=["s1"],
            input_contract=[], output_contract=[], depends_on=[],
            constraints=[], boundary_kind="main_worker",
            decision_evidence=[], reason="",
        )
        return WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[main],
            candidates=[],
            decisions=[],
            handoffs=[],
        )

    def _worker_flow_plan(self) -> WorkerFlowPlanIR:
        return WorkerFlowPlanIR(
            worker_flows={
                "worker_main": FlowStructureIR(main_flow_spans=["s1"]),
            }
        )

    def _worker_block_plan(self) -> WorkerBlockPlanIR:
        return WorkerBlockPlanIR(
            worker_blocks={
                "worker_main": BlockStructureIR(main_flow_blocks=[]),
            }
        )

    def test_flag_off_no_irs_checklist_in_worker_scoped_prompt(self):
        stage = self._make_stage(flag_enabled=False)
        captured_prompt: list[str] = []

        def fake_call_json(*, stage_name, system_prompt, user_prompt):
            captured_prompt.append(system_prompt)
            return {"steps": [], "new_variables": []}

        stage.client.call_json = fake_call_json
        stage.execute_worker_scoped(
            self._spans(), self._routes(),
            self._worker_flow_plan(), self._worker_block_plan(),
            self._symbols(), self._worker_plan(),
        )

        assert len(captured_prompt) >= 1
        assert "CONSTRUCT:" not in captured_prompt[0]

    def test_config_does_not_inject_irs_checklist_in_worker_scoped_prompt(self):
        stage = self._make_stage(flag_enabled=True)
        captured_prompt: list[str] = []

        def fake_call_json(*, stage_name, system_prompt, user_prompt):
            captured_prompt.append(system_prompt)
            return {"steps": [], "new_variables": []}

        stage.client.call_json = fake_call_json
        stage.execute_worker_scoped(
            self._spans(), self._routes(),
            self._worker_flow_plan(), self._worker_block_plan(),
            self._symbols(), self._worker_plan(),
        )

        assert len(captured_prompt) >= 1
        assert "CONSTRUCT:" not in captured_prompt[0]
        assert "IRS-Driven Construct Checklist" not in captured_prompt[0]
