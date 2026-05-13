"""Unit tests for Stage 6 worker-scoped resource extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import (
    HandoffContractIR,
    InputBindingIR,
    OutputBindingIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor


@pytest.fixture
def mock_client() -> MagicMock:
    """Mock LLM client."""
    client = MagicMock()
    client.call_json.return_value = {
        "variables": [
            {
                "name": "query",
                "data_type": "text",
                "required": True,
                "description": "User query",
                "source": "input",
            }
        ],
        "files": [],
        "apis": [],
        "types": [],
    }
    return client


@pytest.fixture
def extractor(pipeline_config: MagicMock, mock_client: MagicMock) -> ResourceExtractor:
    """Create ResourceExtractor instance."""
    return ResourceExtractor(pipeline_config, mock_client)


@pytest.fixture
def sample_spans() -> list[SpanIR]:
    """Sample spans."""
    return [
        SpanIR(span_id="s1", text="User query"),
        SpanIR(span_id="s2", text="Worker task"),
    ]


@pytest.fixture
def sample_routes() -> FieldRouteIR:
    """Sample field routes."""
    return FieldRouteIR(behavior=["s1", "s2"], integrations=[])


@pytest.fixture
def sample_worker_plan() -> WorkerPlanIR:
    """Sample worker plan."""
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker",
                owned_span_ids=["s1"],
            ),
            WorkerSpecIR(
                worker_id="worker_child",
                worker_name="ChildWorker",
                kind="child",
                purpose="Child worker",
                owned_span_ids=["s2"],
            ),
        ],
        handoffs=[
            WorkerHandoffIR(
                handoff_id="handoff_1",
                from_worker="worker_main",
                to_worker="worker_child",
                api_ref=None,
                mode="invoke",
                condition_text=None,
                ordering="after",
                input_bindings=[
                    InputBindingIR(
                        parent_variable="query",
                        child_input="child_query",
                        required=True,
                    )
                ],
                output_bindings=[
                    OutputBindingIR(
                        child_output="child_result",
                        parent_variable="result",
                        required=True,
                        merge_strategy="set",
                    )
                ],
            )
        ],
    )


@pytest.fixture
def sample_flow_plan() -> WorkerFlowPlanIR:
    """Sample flow plan."""
    return WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(),
            "worker_child": FlowStructureIR(),
        }
    )


@pytest.fixture
def sample_block_plan() -> WorkerBlockPlanIR:
    """Sample block plan."""
    return WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])]
            ),
            "worker_child": BlockStructureIR(
                main_flow_blocks=[BlockIR(block_id="b2", block_type="SEQUENTIAL", spans=["s2"])]
            ),
        }
    )


def test_execute_worker_scoped_returns_correct_types(
    extractor: ResourceExtractor,
    sample_spans: list[SpanIR],
    sample_routes: FieldRouteIR,
    sample_worker_plan: WorkerPlanIR,
    sample_flow_plan: WorkerFlowPlanIR,
    sample_block_plan: WorkerBlockPlanIR,
) -> None:
    """Test execute_worker_scoped returns correct types."""
    result, symbol_table = extractor.execute_worker_scoped(
        spans=sample_spans,
        routes=sample_routes,
        worker_flow_plan=sample_flow_plan,
        worker_block_plan=sample_block_plan,
        worker_plan=sample_worker_plan,
    )

    # Check return types
    assert hasattr(result, "global_resources")
    assert hasattr(result, "worker_resources")
    assert hasattr(result, "handoff_contracts")
    assert hasattr(symbol_table, "_variables")


def test_execute_worker_scoped_extracts_global_resources(
    extractor: ResourceExtractor,
    sample_spans: list[SpanIR],
    sample_routes: FieldRouteIR,
    sample_worker_plan: WorkerPlanIR,
    sample_flow_plan: WorkerFlowPlanIR,
    sample_block_plan: WorkerBlockPlanIR,
) -> None:
    """Test execute_worker_scoped extracts global resources."""
    result, symbol_table = extractor.execute_worker_scoped(
        spans=sample_spans,
        routes=sample_routes,
        worker_flow_plan=sample_flow_plan,
        worker_block_plan=sample_block_plan,
        worker_plan=sample_worker_plan,
    )

    # Should have global resources
    assert len(result.global_resources.variables) > 0


def test_execute_worker_scoped_extracts_worker_resources(
    extractor: ResourceExtractor,
    sample_spans: list[SpanIR],
    sample_routes: FieldRouteIR,
    sample_worker_plan: WorkerPlanIR,
    sample_flow_plan: WorkerFlowPlanIR,
    sample_block_plan: WorkerBlockPlanIR,
) -> None:
    """Test execute_worker_scoped extracts worker resources."""
    result, symbol_table = extractor.execute_worker_scoped(
        spans=sample_spans,
        routes=sample_routes,
        worker_flow_plan=sample_flow_plan,
        worker_block_plan=sample_block_plan,
        worker_plan=sample_worker_plan,
    )

    # Should have worker resources for child worker
    assert "worker_child" in result.worker_resources


def test_execute_worker_scoped_extracts_handoff_contracts(
    extractor: ResourceExtractor,
    sample_spans: list[SpanIR],
    sample_routes: FieldRouteIR,
    sample_worker_plan: WorkerPlanIR,
    sample_flow_plan: WorkerFlowPlanIR,
    sample_block_plan: WorkerBlockPlanIR,
) -> None:
    """Test execute_worker_scoped extracts handoff contracts."""
    # Add variables to symbol table for handoff contract building
    extractor.client.call_json.return_value = {
        "variables": [
            {
                "name": "query",
                "data_type": "text",
                "required": True,
                "description": "User query",
                "source": "input",
            },
            {
                "name": "result",
                "data_type": "text",
                "required": True,
                "description": "Result",
                "source": "output",
            },
        ],
        "files": [],
        "apis": [],
        "types": [],
    }

    result, symbol_table = extractor.execute_worker_scoped(
        spans=sample_spans,
        routes=sample_routes,
        worker_flow_plan=sample_flow_plan,
        worker_block_plan=sample_block_plan,
        worker_plan=sample_worker_plan,
    )

    # Should have handoff contracts
    assert "handoff_1" in result.handoff_contracts
    contract = result.handoff_contracts["handoff_1"]
    assert contract.handoff_id == "handoff_1"
    assert contract.parent_worker_id == "worker_main"
    assert contract.child_worker_id == "worker_child"


def test_execute_worker_scoped_symbol_table_has_scoped_variables(
    extractor: ResourceExtractor,
    sample_spans: list[SpanIR],
    sample_routes: FieldRouteIR,
    sample_worker_plan: WorkerPlanIR,
    sample_flow_plan: WorkerFlowPlanIR,
    sample_block_plan: WorkerBlockPlanIR,
) -> None:
    """Test symbol table has scoped variables after execution."""
    result, symbol_table = extractor.execute_worker_scoped(
        spans=sample_spans,
        routes=sample_routes,
        worker_flow_plan=sample_flow_plan,
        worker_block_plan=sample_block_plan,
        worker_plan=sample_worker_plan,
    )

    # Should have variables in _variables with scope
    assert len(symbol_table._variables) > 0

    # Check that global variables exist
    global_vars = [
        var for key, var in symbol_table._variables.items() if key[0] == "global"
    ]
    assert len(global_vars) > 0


def test_build_handoff_contract(
    extractor: ResourceExtractor,
) -> None:
    """Test _build_handoff_contract method."""
    from nl2spl.ir.symbol_table import SymbolTable

    # Create a symbol table with variables
    symbol_table = SymbolTable()
    symbol_table.declare(
        name="query",
        data_type="text",
        source="input",
        description="User query",
    )
    symbol_table.declare(
        name="result",
        data_type="text",
        source="output",
        description="Result",
    )

    # Create a handoff
    handoff = WorkerHandoffIR(
        handoff_id="handoff_1",
        from_worker="worker_main",
        to_worker="worker_child",
        api_ref=None,
        mode="invoke",
        condition_text=None,
        ordering="after",
        input_bindings=[
            InputBindingIR(
                parent_variable="query",
                child_input="child_query",
                required=True,
            )
        ],
        output_bindings=[
            OutputBindingIR(
                child_output="child_result",
                parent_variable="result",
                required=True,
                merge_strategy="set",
            )
        ],
    )

    # Build contract
    contract = extractor._build_handoff_contract(handoff, symbol_table)

    # Verify contract
    assert contract.handoff_id == "handoff_1"
    assert contract.parent_worker_id == "worker_main"
    assert contract.child_worker_id == "worker_child"
    assert len(contract.input_variables) == 1
    assert len(contract.output_variables) == 1
    assert contract.input_variables[0].name == "child_query"
    assert contract.output_variables[0].name == "result"
