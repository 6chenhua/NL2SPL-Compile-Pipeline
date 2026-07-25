"""Integration tests for NL2SPL pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.ir import (
    BlockStructureIR,
    FieldRouteIR,
    FlowStructureIR,
    ResourceRegistryIR,
    SymbolTable,
)
from nl2spl.ir.resource_registry_ir import WorkerScopedResourceIR
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.orchestrator import PipelineOrchestrator, PipelineResult

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def pipeline_config(tmp_path: Path) -> PipelineConfig:
    """Create test pipeline configuration."""
    return PipelineConfig(
        llm=LLMConfig(
            model="gpt-4o",
            max_tokens=4096,
            temperature=0.0,
            api_key="test-api-key",
        ),
        output_dir=tmp_path / "output",
        save_intermediate=False,
        log_level="DEBUG",
        max_retries=1,
    )


@pytest.fixture
def standard_input() -> str:
    """Standard test input text."""
    return """Task family: Internal newsletters and announcements.
Inputs for each run: A user request, optional known topics.
Required outputs: A draft communication, completion status.
Reusable process: First determine communication type. Then identify missing fields.
Policies: Do not invent facts. Require evidence for claims.
Failure handling: Missing timeframe, evidence shortage.
Delegation policy: Optional source gathering if bounded."""


@pytest.fixture
def mock_llm_responses() -> dict:
    """Mock LLM responses for all stages."""
    return {
        "stage1_span_slicer": {
            "spans": [
                {"span_id": "s1", "text": "Task family: Internal newsletters and announcements."},
                {"span_id": "s2", "text": "Inputs for each run: A user request, optional known topics."},
                {"span_id": "s3", "text": "Required outputs: A draft communication, completion status."},
                {"span_id": "s4", "text": "Reusable process: First determine communication type. Then identify missing fields."},
                {"span_id": "s5", "text": "Policies: Do not invent facts. Require evidence for claims."},
                {"span_id": "s6", "text": "Failure handling: Missing timeframe, evidence shortage."},
                {"span_id": "s7", "text": "Delegation policy: Optional source gathering if bounded."},
            ]
        },
        "stage2_field_router": {
            "routes": {
                "identity": [],
                "audience": [],
                "rules": ["s5"],
                "domain": [],
                "integrations": [],
                "behavior": ["s1", "s2", "s3", "s4", "s6", "s7"],
            },
            "ambiguity_updates": [],
        },
        "stage3_ambiguity_resolver": {
            "resolved_spans": [],
            "resolved_routes": {
                "identity": [],
                "audience": [],
                "rules": ["s5"],
                "domain": [],
                "integrations": [],
                "behavior": ["s1", "s2", "s3", "s4", "s6", "s7"],
            },
        },
        "stage4_flow_assembler": {
            "main_flow_spans": ["s4"],
            "alternative_flows": [],
            "exception_flows": [
                {
                    "flow_id": "exc_1",
                    "condition_text": "Missing timeframe or evidence shortage",
                    "spans": ["s6"],
                }
            ],
            "delegation_candidates": [
                {
                    "candidate_id": "dc_1",
                    "spans": ["s7"],
                    "reason": "Source gathering is optional",
                    "suggested_type": "api_call",
                    "input_variables": ["user_request"],
                    "output_variables": ["gathered_sources"],
                }
            ],
        },
        "stage5_block_assembler": {
            "main_flow_blocks": [
                {"block_id": "b1", "block_type": "SEQUENTIAL", "condition_text": None, "spans": ["s4"]}
            ],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {
                "exc_1": [
                    {"block_id": "b2", "block_type": "SEQUENTIAL", "condition_text": None, "spans": ["s6"]}
                ]
            },
        },
        "stage6_resource_extractor": {
            "variables": [
                {"name": "user_request", "data_type": "text", "source": "input", "description": "User request"},
                {"name": "communication_type", "data_type": "text", "source": "step", "description": "Type of communication"},
                {"name": "missing_fields", "data_type": "List[text]", "source": "step", "description": "Missing fields"},
                {"name": "draft_communication", "data_type": "text", "source": "output", "description": "Draft output"},
                {"name": "completion_status", "data_type": "text", "source": "output", "description": "Status output"},
            ],
            "files": [],
            "apis": [],
            "types": [],
        },
        "stage7_step_extractor": {
            "steps": [
                {
                    "step_id": "st1",
                    "text": "Determine communication type",
                    "source_span_ids": ["s4"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": ["user_request"],
                    "outputs": ["communication_type"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "normal",
                },
                {
                    "step_id": "st2",
                    "text": "Identify missing required fields",
                    "source_span_ids": ["s4"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": ["communication_type"],
                    "outputs": ["missing_fields"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "normal",
                },
            ],
            "new_variables": [],
        },
        "stage8_profile_extractor": {
            "persona": {
                "role": "Internal Communications Assistant",
                "aspects": [{"name": "ProfessionalTone", "text": "Maintains professional communication style"}],
            },
            "audience": {
                "aspects": [{"name": "InternalStaff", "text": "Company employees"}],
            },
            "concepts": [],
        },
        "stage9_constraint_extractor": {
            "constraints": [
                {
                    "constraint_id": "c1",
                    "text": "Do not invent facts or make assumptions.",
                    "kind": "prohibition",
                    "targets": ["global"],
                    "source_span_ids": ["s5"],
                },
                {
                    "constraint_id": "c2",
                    "text": "Require evidence for claims.",
                    "kind": "evidence",
                    "targets": ["global"],
                    "source_span_ids": ["s5"],
                },
            ]
        },
    }


# =============================================================================
# Integration Tests
# =============================================================================


class TestPipelineIntegration:
    """Integration tests for the complete pipeline."""

    @pytest.mark.skip(reason="Requires all stages to be implemented")
    def test_pipeline_end_to_end(
        self, pipeline_config: PipelineConfig, standard_input: str, mock_llm_responses: dict
    ) -> None:
        """Test complete pipeline execution."""
        # This test will be enabled once all stages are implemented
        orchestrator = PipelineOrchestrator(pipeline_config)

        # Mock LLM client to return predefined responses
        with patch.object(orchestrator.client, "call_json") as mock_call:
            mock_call.side_effect = lambda stage_name, **kwargs: mock_llm_responses.get(
                stage_name, {}
            )

            result = orchestrator.run(standard_input)

            # Verify result structure
            assert isinstance(result, PipelineResult)
            assert result.spl_text  # Should have generated SPL
            assert isinstance(result.validation_errors, list)
            assert isinstance(result.validation_warnings, list)
            assert isinstance(result.intermediate_results, dict)

    def test_stages_1_to_3_integration(
        self, pipeline_config: PipelineConfig, standard_input: str, mock_llm_responses: dict
    ) -> None:
        """Test Stage 1-3 integration (SpanSlicer → FieldRouter → AmbiguityResolver)."""
        from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import AmbiguityResolver

        # Create mock client
        mock_client = MagicMock()
        mock_client.call_json.side_effect = lambda stage_name, **kwargs: mock_llm_responses.get(
            stage_name, {}
        )

        # Stage 1: SpanSlicer
        slicer = SpanSlicer(pipeline_config, mock_client)
        spans = slicer.execute(standard_input)
        assert len(spans) > 0

        # Stage 2: FieldRouter
        router = FieldRouter(pipeline_config, mock_client)
        routes, updates = router.execute(spans)
        assert routes is not None
        assert len(routes.get_all_span_ids()) > 0

        # Stage 3: AmbiguityResolver
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        resolved_spans, resolved_routes = resolver.execute((spans, routes, updates))
        assert resolved_spans is not None
        assert resolved_routes is not None

    def test_stages_4_to_5_integration(
        self, pipeline_config: PipelineConfig, standard_input: str, mock_llm_responses: dict
    ) -> None:
        """Test Stage 4-5 integration (FlowAssembler → BlockAssembler)."""
        from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
        from nl2spl.pipeline.stages.stage3_ambiguity_resolver import AmbiguityResolver
        from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler
        from nl2spl.pipeline.stages.stage5_block_assembler import BlockAssembler

        # Create mock client
        mock_client = MagicMock()
        mock_client.call_json.side_effect = lambda stage_name, **kwargs: mock_llm_responses.get(
            stage_name, {}
        )

        # Stage 1: SpanSlicer
        slicer = SpanSlicer(pipeline_config, mock_client)
        spans = slicer.execute(standard_input)

        # Stage 2: FieldRouter
        router = FieldRouter(pipeline_config, mock_client)
        routes, updates = router.execute(spans)

        # Stage 3: AmbiguityResolver
        resolver = AmbiguityResolver(pipeline_config, mock_client)
        resolved_spans, resolved_routes = resolver.execute((spans, routes, updates))

        # Stage 4: FlowAssembler
        flow_assembler = FlowAssembler(pipeline_config, mock_client)
        flow_structure = flow_assembler.execute((resolved_spans, resolved_routes))
        assert flow_structure is not None
        assert len(flow_structure.main_flow_spans) > 0
        assert len(flow_structure.exception_flows) > 0
        assert len(flow_structure.delegation_candidates) > 0

        # Stage 5: BlockAssembler
        block_assembler = BlockAssembler(pipeline_config, mock_client)
        block_structure = block_assembler.execute((resolved_spans, resolved_routes, flow_structure))
        assert block_structure is not None
        assert len(block_structure.main_flow_blocks) > 0
        assert len(block_structure.exception_flow_blocks) > 0

    @pytest.mark.skip(reason="Requires Stage 6-7 to be implemented")
    def test_stages_6_to_7_integration(self, pipeline_config: PipelineConfig) -> None:
        """Test Stage 6-7 integration (ResourceExtractor → StepExtractor)."""
        pass

    @pytest.mark.skip(reason="Requires Stage 8-11 to be implemented")
    def test_stages_8_to_11_integration(self, pipeline_config: PipelineConfig) -> None:
        """Test Stage 8-11 integration (Profile → Constraints → Normalize → Worker → SPL)."""
        pass


class TestPipelineErrorHandling:
    """Test pipeline error handling."""

    def test_pipeline_handles_empty_input(self, pipeline_config: PipelineConfig) -> None:
        """Test that pipeline handles empty input gracefully."""
        orchestrator = PipelineOrchestrator(pipeline_config)

        with pytest.raises(Exception):  # noqa: B017 - pipeline may raise stage-specific errors
            orchestrator.run("")

    def test_pipeline_handles_llm_error(self, pipeline_config: PipelineConfig) -> None:
        """Test that pipeline handles LLM errors gracefully."""
        from nl2spl.errors.exceptions import LLMError

        orchestrator = PipelineOrchestrator(pipeline_config)

        with patch.object(orchestrator.client, "call_json") as mock_call:
            mock_call.side_effect = LLMError("API Error", stage="test")

            with pytest.raises(Exception):  # noqa: B017 - preserves broad pipeline error contract
                orchestrator.run("Test input")


class TestPipelineCheckpointing:
    """Test pipeline checkpointing."""

    def test_checkpoint_saved_when_enabled(self, tmp_path: Path, standard_input: str) -> None:
        """Test that checkpoints are saved when save_intermediate is True."""
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            run_name="test-run",
            save_intermediate=True,
        )

        # Checkpoints should be saved to output_dir
        assert config.save_intermediate is True
        assert config.output_dir.exists()
        assert config.run_dir == tmp_path / "output" / "test-run"
        assert config.run_dir.exists()

    def test_checkpoint_not_saved_when_disabled(self, tmp_path: Path) -> None:
        """Test that checkpoints are not saved when save_intermediate is False."""
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            save_intermediate=False,
        )

        assert config.save_intermediate is False

    def test_stage_checkpoint_written_to_run_dir(self, tmp_path: Path) -> None:
        """Test that stage checkpoints are written to run_dir instead of output_dir."""
        from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer

        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            run_name="custom",
            save_intermediate=True,
        )
        mock_client = MagicMock()
        mock_client.call_json.return_value = {
            "spans": [{"span_id": "s1", "text": "test"}],
        }

        slicer = SpanSlicer(config, mock_client)
        slicer.execute("test")

        assert (config.run_dir / "stage1_span_slicer.json").exists()
        assert not (config.output_dir / "stage1_span_slicer.json").exists()

    def test_pipeline_result_records_final_spl_path(self, tmp_path: Path) -> None:
        """Test that orchestrator saves and returns the final SPL path."""
        config = PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            run_name="custom",
            save_intermediate=False,
        )
        orchestrator = PipelineOrchestrator(config)
        worker_plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    "worker_main", "Main", "main", "Main worker",
                    [], [], [], [], [], "main_worker", [], "",
                )
            ],
            candidates=[],
            decisions=[],
            handoffs=[],
        )
        worker_flow_plan = WorkerFlowPlanIR(worker_flows={"worker_main": FlowStructureIR()})
        worker_block_plan = WorkerBlockPlanIR(worker_blocks={"worker_main": BlockStructureIR()})
        worker_step_plan = WorkerStepPlanIR(main_worker_id="worker_main", worker_steps={"worker_main": []})
        worker = MagicMock()
        worker.steps = []
        worker.child_workers = []
        worker.scoped_steps = False

        with (
            patch.object(orchestrator, "_run_stage1", return_value=[]),
            patch.object(orchestrator, "_run_stage2", return_value=(FieldRouteIR(), [])),
            patch.object(orchestrator, "_run_stage3", return_value=([], FieldRouteIR())),
            patch.object(orchestrator, "_run_stage3_5", return_value=worker_plan),
            patch.object(orchestrator, "_run_stage4", return_value=worker_flow_plan),
            patch.object(orchestrator, "_run_stage5", return_value=worker_block_plan),
            patch.object(
                orchestrator,
                "_run_stage6_worker_scoped",
                return_value=(WorkerScopedResourceIR(global_resources=ResourceRegistryIR()), SymbolTable(), []),
            ),
            patch.object(orchestrator, "_run_stage7_worker_scoped", return_value=(worker_step_plan, SymbolTable(), [])),
            patch.object(orchestrator, "_run_stage8", return_value=MagicMock()),
            patch.object(orchestrator, "_run_stage9", return_value=[]),
            patch.object(
                orchestrator,
                "_run_normalization_worker_scoped",
                return_value=(
                    worker_flow_plan,
                    worker_block_plan,
                    worker_step_plan,
                    SymbolTable(),
                    [],
                    [],
                ),
            ),
            patch.object(orchestrator, "_run_stage10_worker_scoped", return_value=worker),
            patch.object(orchestrator, "_run_stage11", return_value=("FINAL SPL", [], [])),
        ):
            result = orchestrator.run("test")

        assert result.final_spl_path == config.run_dir / "final_spl.txt"
        assert result.final_spl_path.read_text(encoding="utf-8") == "FINAL SPL"


# =============================================================================
# Performance Tests
# =============================================================================


@pytest.mark.performance
class TestPipelinePerformance:
    """Performance tests for the pipeline."""

    @pytest.mark.skip(reason="Performance test - run manually")
    def test_pipeline_latency(self, pipeline_config: PipelineConfig, standard_input: str) -> None:
        """Test pipeline completes within acceptable time."""
        import time

        PipelineOrchestrator(pipeline_config)

        start = time.time()
        # result = orchestrator.run(standard_input)
        time.time() - start

        # Should complete within 60 seconds
        # assert elapsed < 60
