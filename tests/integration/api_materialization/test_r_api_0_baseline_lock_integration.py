"""R-API-0 Baseline Lock Integration Tests.

This module locks current E2E baseline behavior and gaps for API materialization prior to
subsequent R-API phases (R-API-1 through R-API-6).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.pipeline.orchestrator import PipelineOrchestrator, PipelineResult


class TestRAPIBaselineLockIntegration:
    """Baseline lock tests for integration / E2E components."""

    def test_explicit_fixture_e2e_baseline(self, tmp_path: Path) -> None:
        """Lock current behavior: Explicit SearchAPI text currently does NOT generate direct CALL_API or APISpec.

        Input: "Retrieve approved sources using SearchAPI."
        Current Gap: The current pipeline does not perform API materialization, so SearchAPI is not declared in
        ResourceRegistryIR.apis and [CALL SearchAPI] is not emitted.
        Future Behavior (R-API-6): SearchAPI vertical slice will produce declared APISpec and [CALL SearchAPI].
        """
        config = PipelineConfig(
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

        orchestrator = PipelineOrchestrator(config)

        # Mock LLM responses to simulate explicit SearchAPI extraction without API materialization
        mock_llm_responses = {
            "stage1_span_slicer": {
                "spans": [
                    {"span_id": "s1", "text": "Retrieve approved sources using SearchAPI."}
                ]
            },
            "stage2_field_router": {
                "routes": {
                    "identity": [],
                    "audience": [],
                    "rules": [],
                    "domain": [],
                    "integrations": ["s1"],
                    "behavior": ["s1"],
                },
                "ambiguity_updates": [],
            },
            "stage3_ambiguity_resolver": {
                "resolved_spans": [],
                "resolved_routes": {
                    "identity": [],
                    "audience": [],
                    "rules": [],
                    "domain": [],
                    "integrations": ["s1"],
                    "behavior": ["s1"],
                },
            },
            "stage4_flow_assembler": {
                "main_flow_spans": ["s1"],
                "alternative_flows": [],
                "exception_flows": [],
                "delegation_candidates": [],
            },
            "stage5_block_assembler": {
                "main_flow_blocks": [
                    {"block_id": "b1", "block_type": "SEQUENTIAL", "spans": ["s1"]}
                ]
            },
            "stage6_resource_extractor": {
                "variables": [],
                "files": [],
                "apis": [],
                "types": [],
            },
            "stage7_step_extractor": {
                "steps": [
                    {
                        "step_id": "st1",
                        "text": "Retrieve approved sources using SearchAPI",
                        "source_span_ids": ["s1"],
                        "command_type": "GENERAL_COMMAND",
                    }
                ],
                "new_variables": [],
            },
            "stage8_profile_extractor": {
                "persona": {"role": "Data Retriever"},
                "audience_aspects": [],
                "concepts": [],
            },
            "stage9_constraint_extractor": {
                "constraints": []
            },
        }

        with patch.object(orchestrator.client, "call_json") as mock_call:
            mock_call.side_effect = lambda stage_name, **kwargs: mock_llm_responses.get(
                stage_name, {}
            )

            result = orchestrator.run("Retrieve approved sources using SearchAPI.")

            # Assert baseline gap:
            # 1. No [CALL SearchAPI] in rendered SPL
            assert "[CALL SearchAPI" not in result.spl_text
            # 2. No SearchAPI in stage6_resources.apis
            stage6_resources = result.intermediate_results.get("stage6_resources")
            assert stage6_resources is not None
            assert not any(api.api_name == "SearchAPI" for api in stage6_resources.apis)
