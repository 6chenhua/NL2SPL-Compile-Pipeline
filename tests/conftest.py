"""Shared pytest fixtures for NL2SPL tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from nl2spl.config import LLMConfig, PipelineConfig
from nl2spl.llm.client import LLMClient
from nl2spl.ir import (
    AmbiguityInfo,
    BlockIR,
    BlockStructureIR,
    ConstraintIR,
    DelegationCandidate,
    FieldRouteIR,
    FlowStructureIR,
    ResourceRegistryIR,
    SpanIR,
    StepIR,
    SymbolTable,
    VariableSymbol,
)


# =============================================================================
# Configuration Fixtures
# =============================================================================


@pytest.fixture
def llm_config() -> LLMConfig:
    """Create test LLM configuration."""
    return LLMConfig(
        model="gpt-4o",
        max_tokens=4096,
        temperature=0.0,
        api_key="test-api-key",
        base_url="https://api.openai.com/v1",
    )


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


# =============================================================================
# Mock LLM Client Fixtures
# =============================================================================


@pytest.fixture
def mock_client() -> MagicMock:
    """Create mock LLM client with default responses."""
    client = MagicMock(spec=LLMClient)
    client.call_json.return_value = {
        "spans": [{"span_id": "s1", "text": "test"}],
        "annotations": [],
        "split_recommendations": [],
        "diagnostics": [],
        "priors": [
            {"section_id": "sec_task_family", "suggested_field": "domain", "suggested_semantic_role": "task_family", "strength": "strong", "evidence": "mock", "source": "heuristic"},
            {"section_id": "sec_inputs_for_each_run", "suggested_field": "resources", "suggested_semantic_role": "input_contract", "strength": "strong", "evidence": "mock", "source": "heuristic"},
            {"section_id": "sec_required_outputs", "suggested_field": "resources", "suggested_semantic_role": "output_contract", "strength": "strong", "evidence": "mock", "source": "heuristic"},
            {"section_id": "sec_reusable_process", "suggested_field": "behavior", "suggested_semantic_role": "process_step", "strength": "strong", "evidence": "mock", "source": "heuristic"},
            {"section_id": "sec_policies", "suggested_field": "rules", "suggested_semantic_role": "policy", "strength": "strong", "evidence": "mock", "source": "heuristic"},
            {"section_id": "sec_failure_handling", "suggested_field": "behavior", "suggested_semantic_role": "failure_mode", "strength": "strong", "evidence": "mock", "source": "heuristic"},
            {"section_id": "sec_delegation_policy", "suggested_field": "integrations", "suggested_semantic_role": "delegation_intent", "strength": "strong", "evidence": "mock", "source": "heuristic"},
        ],
    }
    client.call_text.return_value = "test response"
    return client


@pytest.fixture
def mock_client_factory():
    """Factory for creating mock clients with specific responses."""

    def _create_client(responses: dict[str, Any]) -> MagicMock:
        client = MagicMock(spec=LLMClient)
        client.call_json.side_effect = lambda **kwargs: responses.get(
            kwargs.get("stage_name", ""), {}
        )
        return client

    return _create_client


# =============================================================================
# IR Fixtures - Spans
# =============================================================================


@pytest.fixture
def sample_span() -> SpanIR:
    """Create a single sample span."""
    return SpanIR(
        span_id="s1",
        text="First determine what kind of communication is requested.",
        ambiguity=AmbiguityInfo(),
    )


@pytest.fixture
def sample_spans() -> list[SpanIR]:
    """Create a list of sample spans."""
    return [
        SpanIR(
            span_id="s1",
            text="You are a helpful assistant for internal communications.",
            ambiguity=AmbiguityInfo(),
        ),
        SpanIR(
            span_id="s2",
            text="First determine what kind of communication is requested.",
            ambiguity=AmbiguityInfo(),
        ),
        SpanIR(
            span_id="s3",
            text="Do not invent facts or make assumptions.",
            ambiguity=AmbiguityInfo(),
        ),
        SpanIR(
            span_id="s4",
            text="Use the email API to send notifications.",
            ambiguity=AmbiguityInfo(),
        ),
        SpanIR(
            span_id="s5",
            text="Then identify missing required fields.",
            ambiguity=AmbiguityInfo(),
        ),
    ]


@pytest.fixture
def ambiguous_span() -> SpanIR:
    """Create an ambiguous span for testing."""
    return SpanIR(
        span_id="s6",
        text="You are a helpful assistant who must follow strict guidelines.",
        ambiguity=AmbiguityInfo(
            is_ambiguous=True,
            reasons=["Contains both identity and rules content"],
            needs_split=True,
        ),
    )


# =============================================================================
# IR Fixtures - Field Routes
# =============================================================================


@pytest.fixture
def sample_field_route() -> FieldRouteIR:
    """Create sample field route."""
    return FieldRouteIR(
        identity=["s1"],
        audience=[],
        rules=["s3"],
        domain=[],
        integrations=["s4"],
        behavior=["s2", "s5"],
    )


# =============================================================================
# IR Fixtures - Flow Structure
# =============================================================================


@pytest.fixture
def sample_flow_structure() -> FlowStructureIR:
    """Create sample flow structure."""
    return FlowStructureIR(
        main_flow_spans=["s1", "s2", "s5"],
        alternative_flows=[
            DelegationCandidate(
                candidate_id="dc_1",
                spans=["s4"],
                reason="API call can be delegated",
                suggested_type="api_call",
                input_variables=["notification_content"],
                output_variables=["send_result"],
            )
        ],
        exception_flows=[],
    )


# =============================================================================
# IR Fixtures - Block Structure
# =============================================================================


@pytest.fixture
def sample_block_structure() -> BlockStructureIR:
    """Create sample block structure."""
    return BlockStructureIR(
        main_flow_blocks=[
            BlockIR(
                block_id="b1",
                block_type="SEQUENTIAL",
                condition_text=None,
                spans=["s1", "s2"],
            ),
            BlockIR(
                block_id="b2",
                block_type="SEQUENTIAL",
                condition_text=None,
                spans=["s5"],
            ),
        ],
        alternative_flow_blocks={},
        exception_flow_blocks={},
    )


# =============================================================================
# IR Fixtures - Symbol Table
# =============================================================================


@pytest.fixture
def sample_symbol_table() -> SymbolTable:
    """Create sample symbol table with variables."""
    table = SymbolTable()
    table.declare(
        name="user_request",
        data_type="text",
        source="input",
        description="User's request text",
    )
    table.declare(
        name="communication_type",
        data_type="text",
        source="step",
        description="Type of communication",
    )
    table.declare(
        name="missing_fields",
        data_type="List[text]",
        source="step",
        description="List of missing required fields",
    )
    return table


# =============================================================================
# IR Fixtures - Steps
# =============================================================================


@pytest.fixture
def sample_steps() -> list[StepIR]:
    """Create sample steps."""
    return [
        StepIR(
            step_id="st1",
            text="Determine communication type",
            source_span_ids=["s2"],
            command_type="GENERAL_COMMAND",
            inputs=["user_request"],
            outputs=["communication_type"],
            integration_ref=None,
            flow_ref="main",
            block_ref="b1",
            kind="normal",
        ),
        StepIR(
            step_id="st2",
            text="Identify missing fields",
            source_span_ids=["s5"],
            command_type="GENERAL_COMMAND",
            inputs=["communication_type"],
            outputs=["missing_fields"],
            integration_ref=None,
            flow_ref="main",
            block_ref="b2",
            kind="normal",
        ),
    ]


# =============================================================================
# IR Fixtures - Constraints
# =============================================================================


@pytest.fixture
def sample_constraints() -> list[ConstraintIR]:
    """Create sample constraints."""
    return [
        ConstraintIR(
            constraint_id="c1",
            text="Do not invent facts or make assumptions.",
            kind="prohibition",
            targets=["global"],
            source_span_ids=["s3"],
        ),
    ]


# =============================================================================
# IR Fixtures - Resource Registry
# =============================================================================


@pytest.fixture
def sample_resource_registry() -> ResourceRegistryIR:
    """Create sample resource registry."""
    return ResourceRegistryIR(
        variables=[],
        files=[],
        apis=[],
        types=[],
    )


# =============================================================================
# File System Fixtures
# =============================================================================


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create temporary output directory."""
    output = tmp_path / "output"
    output.mkdir(parents=True, exist_ok=True)
    return output


@pytest.fixture
def sample_input_file(tmp_path: Path) -> Path:
    """Create a sample input file."""
    input_file = tmp_path / "input.txt"
    input_file.write_text(
        """Task family: Internal newsletters and announcements.
Inputs for each run: A user request, optional known topics.
Required outputs: A draft communication, completion status.
Reusable process: First determine communication type. Then identify missing fields.
Policies: Do not invent facts. Require evidence for claims.
Failure handling: Missing timeframe, evidence shortage.
Delegation policy: Optional source gathering if bounded.""",
        encoding="utf-8",
    )
    return input_file
