"""Unit tests for Stage 6 V2 resource context builder."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.canonical import CanonicalCompileInput, HardFacts, VariableFact
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import ContractFieldIR, WorkerSpecIR
from nl2spl.pipeline.stages.stage6_resource_extractor.context_builder import (
    build_resource_context,
)
from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor


# =============================================================================
# Context builder unit tests
# =============================================================================


class TestBuildResourceContext:
    def test_worker_scope_includes_purpose_and_contract(self) -> None:
        worker = WorkerSpecIR(
            worker_id="worker_retrieve",
            worker_name="RetrieveSources",
            kind="child",
            purpose="Retrieve source material.",
            owned_span_ids=["s2"],
            input_contract=[
                ContractFieldIR("query", "text", True, "Search query", "input"),
            ],
            output_contract=[
                ContractFieldIR("results", "List[text]", True, "Search results", "output"),
            ],
        )
        spans = [SpanIR("s2", "Retrieve sources.")]
        routes = FieldRouteIR(behavior=["s2"])

        result = build_resource_context(
            spans=spans, routes=routes,
            worker_spec=worker, scope_kind="worker", scope_id="worker_retrieve",
        )

        assert "Resource extraction scope" in result
        assert "worker_id: worker_retrieve" in result
        assert "RetrieveSources" in result
        assert "Retrieve source material" in result
        assert "Authoritative contract" in result
        assert "query: text, unspecified" in result
        assert "results: List[text], unspecified" in result

    def test_global_scope_with_canonical_hard_facts(self) -> None:
        canonical = CanonicalCompileInput(
            source_schema="structural_nl",
            schema_version="1.0",
            raw_text="",
            hard_facts=HardFacts(
                inputs=[
                    VariableFact("user_request", "A user request", "text", True,
                                 source_section_id="sec_inputs"),
                ],
                outputs=[
                    VariableFact("draft", "A draft artifact", "text", True,
                                 source_section_id="sec_outputs"),
                ],
            ),
        )
        spans = [SpanIR("s1", "Produce draft.")]
        routes = FieldRouteIR(behavior=["s1"])

        result = build_resource_context(
            spans=spans, routes=routes,
            canonical_input=canonical, scope_kind="global",
        )

        assert "Resource extraction scope" in result
        assert "global/main" in result
        assert "Authoritative contract" in result
        assert "user_request: text, required" in result
        assert "draft: text, required" in result

    def test_flow_summary_is_compact(self) -> None:
        flow = FlowStructureIR(
            main_flow_spans=["s1", "s2"],
            alternative_flows=[],
            exception_flows=[
                ExceptionFlow("exc_01", "Missing timeframe.", spans=["s_err"]),
            ],
        )
        spans = [SpanIR("s1", "A"), SpanIR("s2", "B"), SpanIR("s_err", "Err")]
        routes = FieldRouteIR(behavior=["s1", "s2"])

        result = build_resource_context(spans=spans, routes=routes, flow=flow)

        assert "Main flow spans: s1, s2" in result
        assert "Exception conditions: Missing timeframe." in result
        # Must NOT contain raw IR JSON keys
        assert '"main_flow_spans"' not in result
        assert '"exception_flows"' not in result
        assert '"flow_id"' not in result

    def test_block_summary_includes_all_flow_types(self) -> None:
        blocks = BlockStructureIR(
            main_flow_blocks=[
                BlockIR("b1", "SEQUENTIAL", spans=["s1", "s2"]),
                BlockIR("b2", "IF", condition_text="over budget", spans=["s3"]),
            ],
            alternative_flow_blocks={
                "alt_01": [
                    BlockIR("b3", "SEQUENTIAL", spans=["s_alt"]),
                ],
            },
            exception_flow_blocks={
                "exc_01": [
                    BlockIR("b4", "SEQUENTIAL", spans=["s_exc"]),
                ],
            },
        )
        spans = [SpanIR("s1", "A"), SpanIR("s2", "B"), SpanIR("s3", "C"),
                 SpanIR("s_alt", "Alt"), SpanIR("s_exc", "Exc")]
        routes = FieldRouteIR(behavior=["s1", "s2", "s3", "s_alt", "s_exc"])

        result = build_resource_context(spans=spans, routes=routes, blocks=blocks)

        assert "Main blocks:" in result
        assert "SEQUENTIAL: spans=s1, s2" in result
        assert "IF (over budget): spans=s3" in result
        assert "Alternative flow alt_01:" in result
        assert "Exception flow exc_01:" in result
        # Must NOT contain raw IR JSON keys
        assert '"block_id"' not in result
        assert '"block_type"' not in result
        assert '"main_flow_blocks"' not in result

    def test_source_data_does_not_leak_schema_keys(self) -> None:
        """V2 context data sections must NOT leak schema/internal IR keys."""
        spans = [
            SpanIR("s1", "Normalize.", source_section_id="sec_process"),
        ]
        routes = FieldRouteIR(behavior=["s1"])

        result = build_resource_context(spans=spans, routes=routes)

        # The data sections (scope, source spans, flow, block) must not
        # contain raw IR field names.  The extraction policy section
        # lists these as examples of what NOT to extract, which is fine.
        data_sections = result.split("Extraction policy")[0]
        assert "source_section_id" not in data_sections
        assert "source_packet_id" not in data_sections
        assert "source_span_ids" not in data_sections
        assert '"flow_id"' not in data_sections
        assert '"block_id"' not in data_sections

    def test_known_variables_included(self) -> None:
        sym = SymbolTable()
        sym.declare_scoped("global_var", "text", "input", "Global input",
                           scope_kind="global")
        spans = [SpanIR("s1", "Use global_var.")]
        routes = FieldRouteIR(behavior=["s1"])

        result = build_resource_context(
            spans=spans, routes=routes,
            symbol_table=sym, scope_kind="worker", scope_id="worker_main",
        )

        assert "Known variables" in result
        assert "global_var" in result

    def test_empty_known_variables_stable(self) -> None:
        sym = SymbolTable()
        spans = [SpanIR("s1", "Step.")]
        routes = FieldRouteIR(behavior=["s1"])

        result = build_resource_context(
            spans=spans, routes=routes,
            symbol_table=sym, scope_kind="worker", scope_id="no_vars",
        )

        assert "Known variables" in result
        assert "none" in result.lower()

    def test_missing_worker_and_canonical_contract_is_none(self) -> None:
        spans = [SpanIR("s1", "Step.")]
        routes = FieldRouteIR(behavior=["s1"])

        result = build_resource_context(spans=spans, routes=routes, scope_kind="global")

        assert "Authoritative contract" in result
        assert "- none" in result

    def test_extraction_policy_included(self) -> None:
        spans = [SpanIR("s1", "Step.")]
        routes = FieldRouteIR(behavior=["s1"])

        result = build_resource_context(spans=spans, routes=routes)

        assert "Extraction policy" in result
        assert "Do not redeclare authoritative contract" in result
        assert "Do not extract span_id" in result

    def test_no_flow_no_blocks_stable(self) -> None:
        spans = [SpanIR("s1", "Step.")]
        routes = FieldRouteIR(behavior=["s1"])

        result = build_resource_context(spans=spans, routes=routes)

        assert "No flow structure available" in result
        assert "No block structure available" in result


# =============================================================================
# Flag-gated integration tests
# =============================================================================


class TestStage6V2ConfigIntegration:
    """Verify execute() paths always use the scoped prompt format."""

    @pytest.fixture
    def flag_on_config(self) -> MagicMock:
        cfg = MagicMock()
        return cfg

    @pytest.fixture
    def flag_off_config(self) -> MagicMock:
        cfg = MagicMock()
        return cfg

    def _make_extractor(self, config: MagicMock) -> ResourceExtractor:
        """Create extractor with patched logger and save_checkpoint."""
        import logging
        extractor = ResourceExtractor(config, MagicMock())
        extractor.logger = logging.getLogger("test")
        extractor.save_checkpoint = MagicMock()
        return extractor

    def test_legacy_with_flag_on_uses_v2_context(
        self, flag_on_config: MagicMock,
    ) -> None:
        """Legacy path with flag on uses Resource extraction scope."""
        extractor = self._make_extractor(flag_on_config)
        extractor.client.call_json.return_value = {
            "variables": [], "files": [], "apis": [], "types": [],
        }

        spans = [SpanIR("s1", "Normalize request.")]
        routes = FieldRouteIR(behavior=["s1"])

        extractor.execute((spans, routes))

        user_prompt = extractor.client.call_json.call_args.kwargs["user_prompt"]
        assert "Resource extraction scope" in user_prompt
        assert "Authoritative contract" in user_prompt
        assert "Source spans" in user_prompt
        assert "Extraction policy" in user_prompt
        # Old format must be absent
        assert "请从以下文本中提取资源" not in user_prompt

    def test_legacy_with_config_off_still_uses_v2_context(
        self, flag_off_config: MagicMock,
    ) -> None:
        extractor = self._make_extractor(flag_off_config)
        extractor.client.call_json.return_value = {
            "variables": [], "files": [], "apis": [], "types": [],
        }

        spans = [SpanIR("s1", "Normalize request.")]
        routes = FieldRouteIR(behavior=["s1"])

        extractor.execute((spans, routes))

        user_prompt = extractor.client.call_json.call_args.kwargs["user_prompt"]
        assert "Resource extraction scope" in user_prompt
        assert "Authoritative contract" in user_prompt
        assert "Source spans" in user_prompt
        assert "Extraction policy" in user_prompt

    def test_worker_scoped_with_flag_on_uses_v2_context(
        self, flag_on_config: MagicMock,
    ) -> None:
        """Worker-scoped path with flag on includes Resource extraction scope."""
        extractor = self._make_extractor(flag_on_config)
        extractor.client.call_json.return_value = {
            "variables": [
                {"name": "query", "data_type": "text", "required": True,
                 "description": "Query", "source": "input"},
            ],
            "files": [], "apis": [], "types": [],
        }

        worker = WorkerSpecIR(
            worker_id="worker_test",
            worker_name="TestWorker",
            kind="child",
            purpose="Test extraction",
            owned_span_ids=["s1"],
            input_contract=[
                ContractFieldIR("query", "text", True, "Query", "input"),
            ],
            output_contract=[],
        )
        spans = [SpanIR("s1", "Extract resources.")]
        routes = FieldRouteIR(behavior=["s1"])

        extractor._extract_resources_for_scope(
            spans=spans, routes=routes,
            flow=FlowStructureIR(),
            blocks=BlockStructureIR(
                main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", spans=["s1"])],
            ),
            symbol_table=SymbolTable(),
            scope_kind="worker", scope_id="worker_test",
            worker_spec=worker,
        )

        user_prompt = extractor.client.call_json.call_args.kwargs["user_prompt"]
        assert "Resource extraction scope" in user_prompt
        assert "worker_id: worker_test" in user_prompt
        assert "TestWorker" in user_prompt
        assert "Authoritative contract" in user_prompt
        assert "query: text, unspecified" in user_prompt
        # Old format must be absent
        assert "worker context" not in user_prompt
        assert "请从以下文本中提取资源" not in user_prompt

    def test_worker_scoped_with_config_off_still_uses_v2_context(
        self, flag_off_config: MagicMock,
    ) -> None:
        extractor = self._make_extractor(flag_off_config)
        extractor.client.call_json.return_value = {
            "variables": [], "files": [], "apis": [], "types": [],
        }

        worker = WorkerSpecIR(
            worker_id="worker_test",
            worker_name="TestWorker",
            kind="child",
            purpose="Test extraction",
            owned_span_ids=["s1"],
            input_contract=[],
            output_contract=[],
        )
        spans = [SpanIR("s1", "Extract resources.")]
        routes = FieldRouteIR(behavior=["s1"])

        extractor._extract_resources_for_scope(
            spans=spans, routes=routes,
            flow=FlowStructureIR(),
            blocks=BlockStructureIR(
                main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", spans=["s1"])],
            ),
            symbol_table=SymbolTable(),
            scope_kind="worker", scope_id="worker_test",
            worker_spec=worker,
        )

        user_prompt = extractor.client.call_json.call_args.kwargs["user_prompt"]
        assert "Resource extraction scope" in user_prompt
        assert "worker_id: worker_test" in user_prompt
        assert "TestWorker" in user_prompt
