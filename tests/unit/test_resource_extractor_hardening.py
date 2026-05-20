"""Unit tests for Phase 7 resource name filter."""

import pytest

from nl2spl.pipeline.stages.stage6_resource_extractor.resource_name_filter import (
    RESERVED_RESOURCE_NAMES,
    is_allowed_resource_variable,
    looks_like_ir_field,
)


# ---------------------------------------------------------------------------
# looks_like_ir_field
# ---------------------------------------------------------------------------

class TestLooksLikeIRField:
    @pytest.mark.parametrize("name", [
        "span_id", "source_span_id", "source_span_ids",
        "source_section_id", "source_packet_id",
        "block_id", "flow_id", "step_id", "worker_id",
        "target_ref", "diagnostic_id",
    ])
    def test_reserved_names_match_heuristic(self, name):
        assert looks_like_ir_field(name), f"{name} should look like IR field"

    @pytest.mark.parametrize("name", [
        "main_flow_spans", "exception_flows",
    ])
    def test_compound_reserved_names_blocked_anyway(self, name):
        """Compound names caught by direct reserved check even if heuristic misses."""
        allowed, _ = is_allowed_resource_variable(name)
        assert not allowed, f"{name} should be blocked"

    @pytest.mark.parametrize("name", [
        "SourceSpanId", "source-span-id", "SOURCE_SPAN_ID",
        "StepID", "step-id", "BlockId", "block_id",
        "FlowID", "flow-id", "WorkerId",
    ])
    def test_case_and_separator_variants_match(self, name):
        assert looks_like_ir_field(name), f"{name} should look like IR field"

    @pytest.mark.parametrize("name", [
        "purchase_request", "draft_artifact", "user_name",
        "communication_type", "normalized_request",
        "approval_record", "eligible_vendor_pool",
        "budget_owner", "cost_center", "urgency",
    ])
    def test_legitimate_variables_dont_match(self, name):
        assert not looks_like_ir_field(name), f"{name} should NOT look like IR field"


# ---------------------------------------------------------------------------
# is_allowed_resource_variable
# ---------------------------------------------------------------------------

class TestIsAllowedResourceVariable:
    def test_reserved_name_blocked(self):
        allowed, reason = is_allowed_resource_variable("span_id")
        assert not allowed
        assert "reserved" in reason

    def test_ir_field_pattern_blocked(self):
        allowed, reason = is_allowed_resource_variable("SourceSpanId")
        assert not allowed
        # Direct reserved-match takes priority over heuristic; either word is fine.
        assert "reserved" in reason or "resembles" in reason

    def test_legitimate_variable_allowed(self):
        allowed, reason = is_allowed_resource_variable("purchase_request")
        assert allowed
        assert reason is None

    @pytest.mark.parametrize("name", [
        "purchase_request", "draft_artifact", "user_name",
        "normalized_request", "approval_record",
        "eligible_vendor_pool", "budget_owner", "cost_center", "urgency",
        "communication_type", "compliance_artifacts", "user_request",
    ])
    def test_internal_comms_inputs_preserved(self, name):
        allowed, _ = is_allowed_resource_variable(name)
        assert allowed, f"{name} should be allowed"


# ---------------------------------------------------------------------------
# Reserved names set
# ---------------------------------------------------------------------------

class TestReservedNames:
    def test_contains_all_required_names(self):
        required = {
            "span_id", "source_span_id", "source_span_ids",
            "source_section_id", "source_packet_id",
            "main_flow_spans", "exception_flows",
            "block_id", "flow_id", "step_id", "worker_id",
            "target_ref", "diagnostic_id",
        }
        assert RESERVED_RESOURCE_NAMES == required

    def test_deterministic(self):
        a = sorted(RESERVED_RESOURCE_NAMES)
        b = sorted(RESERVED_RESOURCE_NAMES)
        assert a == b


# ---------------------------------------------------------------------------
# Case-insensitive matching
# ---------------------------------------------------------------------------

class TestCaseInsensitive:
    @pytest.mark.parametrize("name", [
        "SourceSectionId", "SOURCE_SECTION_ID",
        "sourceSectionId", "source_section_id",
    ])
    def test_all_variants_of_source_section_id_blocked(self, name):
        allowed, _ = is_allowed_resource_variable(name)
        assert not allowed

    @pytest.mark.parametrize("name", [
        "SpanId", "SPAN_ID", "span-id", "SpanID",
    ])
    def test_all_variants_of_span_id_blocked(self, name):
        allowed, _ = is_allowed_resource_variable(name)
        assert not allowed

    def test_underscore_vs_hyphen_variants_equivalent(self):
        """source-section-id and source_section_id must match the same way."""
        a, _ = is_allowed_resource_variable("source-section-id")
        b, _ = is_allowed_resource_variable("source_section_id")
        assert a == b  # both blocked
        assert a is False


# ---------------------------------------------------------------------------
# No false positives on required outputs
# ---------------------------------------------------------------------------

class TestRequiredOutputsPreserved:
    @pytest.mark.parametrize("name", [
        "sourcing_evaluation_record",
        "selected_vendor_decision_or_rejection_outcome",
        "approval_record",
        "po_or_equivalent_issuance_artifact",
        "audit_evidence_bundle",
    ])
    def test_enterprise_procedure_outputs_preserved(self, name):
        allowed, _ = is_allowed_resource_variable(name)
        assert allowed, f"required output '{name}' must be preserved"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self):
        for name in ["span_id", "purchase_request", "SourceSpanId", "draft_artifact"]:
            a_allowed, a_reason = is_allowed_resource_variable(name)
            b_allowed, b_reason = is_allowed_resource_variable(name)
            assert a_allowed == b_allowed
            assert a_reason == b_reason


# ---------------------------------------------------------------------------
# Stage 6 parse boundary: filter applied during variable extraction
# ---------------------------------------------------------------------------

class TestStage6ParseBoundary:
    def _make_stage(self, flag_enabled: bool):
        from unittest.mock import MagicMock
        from nl2spl.config import LLMConfig, PipelineConfig
        from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            enable_resource_name_filter=flag_enabled,
        )
        return ResourceExtractor(config, MagicMock())

    def test_flag_off_span_id_allowed(self):
        """Flag off: reserved name passes through (backward compatible)."""
        from nl2spl.ir.field_route_ir import FieldRouteIR
        from nl2spl.ir.span_ir import SpanIR
        stage = self._make_stage(flag_enabled=False)
        stage.client.call_json = lambda **kw: {
            "variables": [{"name": "span_id", "data_type": "text", "source": "step"}],
            "files": [], "apis": [], "types": [],
        }
        resources, symbols = stage.execute((
            [SpanIR("s1", "text")], FieldRouteIR(behavior=["s1"]),
        ))
        assert any(v.name == "span_id" for v in resources.variables)
        assert "span_id" in symbols.variables
        assert not getattr(stage, "resource_filter_warnings", [])

    def test_flag_on_span_id_rejected(self):
        """Flag on: reserved name rejected from resources and symbols."""
        from nl2spl.ir.field_route_ir import FieldRouteIR
        from nl2spl.ir.span_ir import SpanIR
        stage = self._make_stage(flag_enabled=True)
        stage.client.call_json = lambda **kw: {
            "variables": [
                {"name": "span_id", "data_type": "text", "source": "step"},
                {"name": "purchase_request", "data_type": "text", "source": "input"},
            ],
            "files": [], "apis": [], "types": [],
        }
        resources, symbols = stage.execute((
            [SpanIR("s1", "text")], FieldRouteIR(behavior=["s1"]),
        ))
        # reserved name rejected
        assert not any(v.name == "span_id" for v in resources.variables)
        assert "span_id" not in symbols.variables
        # legitimate variable preserved
        assert any(v.name == "purchase_request" for v in resources.variables)
        assert "purchase_request" in symbols.variables
        # warning recorded
        warnings = getattr(stage, "resource_filter_warnings", [])
        assert any("span_id" in w for w in warnings)
        assert any("Rejected" in w for w in warnings)

    def test_flag_on_source_section_id_rejected(self):
        """Case-insensitive: SourceSectionId is caught."""
        from nl2spl.ir.field_route_ir import FieldRouteIR
        from nl2spl.ir.span_ir import SpanIR
        stage = self._make_stage(flag_enabled=True)
        stage.client.call_json = lambda **kw: {
            "variables": [{"name": "SourceSectionId", "data_type": "text", "source": "step"}],
            "files": [], "apis": [], "types": [],
        }
        resources, _ = stage.execute((
            [SpanIR("s1", "text")], FieldRouteIR(behavior=["s1"]),
        ))
        assert not any(v.name == "SourceSectionId" for v in resources.variables)


# ---------------------------------------------------------------------------
# Worker-scoped parse boundary
# ---------------------------------------------------------------------------

class TestWorkerScopedParseBoundary:
    def _make_stage(self, flag_enabled: bool):
        from unittest.mock import MagicMock
        from nl2spl.config import LLMConfig, PipelineConfig
        from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            enable_resource_name_filter=flag_enabled,
        )
        return ResourceExtractor(config, MagicMock())

    def test_filter_on_worker_scoped_rejects_span_id(self):
        from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
        from nl2spl.ir.field_route_ir import FieldRouteIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.span_ir import SpanIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.ir.worker_plan_ir import (
            WorkerBlockPlanIR, WorkerFlowPlanIR, WorkerPlanIR,
            WorkerSpecIR,
        )

        stage = self._make_stage(flag_enabled=True)
        stage.client.call_json = lambda **kw: {
            "variables": [
                {"name": "span_id", "data_type": "text", "source": "step"},
                {"name": "purchase_request", "data_type": "text", "source": "input"},
            ],
            "files": [], "apis": [], "types": [],
        }

        spans = [SpanIR("s1", "text")]
        routes = FieldRouteIR(behavior=["s1"])
        worker_plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR("worker_main", "Main", "main", "Main worker",
                             ["s1"], [], [], [], [], "main_worker", [], ""),
            ],
            candidates=[], decisions=[], handoffs=[],
        )
        flow_plan = WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])}
        )
        block_plan = WorkerBlockPlanIR(
            worker_blocks={"worker_main": BlockStructureIR(
                main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
            )}
        )

        ws_resources, symbols = stage.execute_worker_scoped(
            spans, routes, flow_plan, block_plan, worker_plan,
        )

        # reserved name rejected from global and scoped resources
        all_vars = ws_resources.get_all_variables()
        assert not any(v.name == "span_id" for v in all_vars)
        assert "span_id" not in symbols.variables
        # legitimate variable preserved
        assert any(v.name == "purchase_request" for v in all_vars)
        assert "purchase_request" in symbols.variables
        # warning recorded on stage
        warnings = getattr(stage, "resource_filter_warnings", [])
        assert any("span_id" in w for w in warnings)
        assert any("Rejected" in w for w in warnings)

    def test_flag_off_worker_scoped_span_id_allowed(self):
        from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
        from nl2spl.ir.field_route_ir import FieldRouteIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.span_ir import SpanIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.ir.worker_plan_ir import (
            WorkerBlockPlanIR, WorkerFlowPlanIR, WorkerPlanIR,
            WorkerSpecIR,
        )

        stage = self._make_stage(flag_enabled=False)
        stage.client.call_json = lambda **kw: {
            "variables": [{"name": "span_id", "data_type": "text", "source": "step"}],
            "files": [], "apis": [], "types": [],
        }

        spans = [SpanIR("s1", "text")]
        routes = FieldRouteIR(behavior=["s1"])
        worker_plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR("worker_main", "Main", "main", "Main worker",
                             ["s1"], [], [], [], [], "main_worker", [], ""),
            ],
            candidates=[], decisions=[], handoffs=[],
        )
        flow_plan = WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])}
        )
        block_plan = WorkerBlockPlanIR(
            worker_blocks={"worker_main": BlockStructureIR(
                main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
            )}
        )

        ws_resources, symbols = stage.execute_worker_scoped(
            spans, routes, flow_plan, block_plan, worker_plan,
        )

        # flag off: reserved name passes through
        all_vars = ws_resources.get_all_variables()
        assert any(v.name == "span_id" for v in all_vars)
        assert "span_id" in symbols.variables
        assert not getattr(stage, "resource_filter_warnings", [])


# ---------------------------------------------------------------------------
# Orchestrator e2e: filter warnings reach adapter_warnings
# ---------------------------------------------------------------------------

class TestOrchestratorFilterWarnings:
    def test_filter_warning_in_adapter_warnings(self, tmp_path):
        from pathlib import Path
        from unittest.mock import MagicMock, patch
        from nl2spl.config import LLMConfig, PipelineConfig
        from nl2spl.ir.field_route_ir import FieldRouteIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
        from nl2spl.ir.span_ir import SpanIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.pipeline.orchestrator import PipelineOrchestrator

        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
            enable_worker_boundary_planner=False,
            enable_resource_name_filter=True,
        )
        orch = PipelineOrchestrator(config)

        fake_resources = ResourceRegistryIR(
            variables=[VariableSpec("purchase_request", "text", True, "Purchase request", "input")],
        )
        fake_warnings = ["Rejected schema-looking variable 'span_id': reserved IR/schema name: span_id"]

        with (
            patch.object(orch, "_run_stage1", return_value=[SpanIR("s1", "text")]),
            patch.object(orch, "_run_stage2", return_value=(FieldRouteIR(behavior=["s1"]), [])),
            patch.object(orch, "_run_stage3", return_value=([SpanIR("s1", "text")], FieldRouteIR(behavior=["s1"]))),
            patch.object(orch, "_run_stage4", return_value=FlowStructureIR()),
            patch.object(orch, "_run_stage5", return_value=BlockStructureIR()),
            patch.object(orch, "_run_stage6", return_value=(fake_resources, SymbolTable(), fake_warnings)),
            patch.object(orch, "_run_stage7", return_value=([], MagicMock(), [])),
            patch.object(orch, "_run_stage8", return_value=MagicMock()),
            patch.object(orch, "_run_stage9", return_value=[]),
            patch.object(orch, "_run_normalization", return_value=(FlowStructureIR(), BlockStructureIR(), [], [], MagicMock(), [], [])),
            patch.object(orch, "_run_stage10", return_value=MagicMock()),
            patch.object(orch, "_run_stage11", return_value=("SPL", [], [])),
        ):
            result = orch.run("test")

        found = any("Rejected schema-looking variable" in w for w in result.adapter_warnings)
        assert found, f"Expected filter warning in adapter_warnings, got: {result.adapter_warnings}"
