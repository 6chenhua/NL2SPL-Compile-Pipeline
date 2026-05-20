"""Verify Stage 4 executor injects IRS checklist when flag is on."""

from unittest.mock import MagicMock

from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler


class TestStage4PromptInjection:
    def _make_stage(self, flag_enabled: bool) -> FlowAssembler:
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            enable_irs_prompt_builder=flag_enabled,
        )
        return FlowAssembler(config, MagicMock())

    def test_flag_off_no_irs_in_prompt(self):
        stage = self._make_stage(flag_enabled=False)
        captured: list[str] = []

        def fake_call_json(*, stage_name, system_prompt, user_prompt):
            captured.append(system_prompt)
            return {"main_flow_spans": [], "alternative_flows": [], "exception_flows": []}

        stage.client.call_json = fake_call_json
        spans = [SpanIR("s1", "Do work.")]
        routes = FieldRouteIR(behavior=["s1"])
        stage.execute((spans, routes))

        assert len(captured) == 1
        assert "CONSTRUCT:" not in captured[0]

    def test_flag_on_injects_exception_flow_irs(self):
        stage = self._make_stage(flag_enabled=True)
        captured: list[str] = []

        def fake_call_json(*, stage_name, system_prompt, user_prompt):
            captured.append(system_prompt)
            return {"main_flow_spans": [], "alternative_flows": [], "exception_flows": []}

        stage.client.call_json = fake_call_json
        spans = [SpanIR("s1", "Do work.")]
        routes = FieldRouteIR(behavior=["s1"])
        stage.execute((spans, routes))

        assert len(captured) == 1
        assert "CONSTRUCT: EXCEPTION_FLOW" in captured[0]
        assert "handler_action" in captured[0]
        assert "missing_handler" in captured[0]
