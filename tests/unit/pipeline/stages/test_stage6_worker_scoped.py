"""Unit tests for Stage 6 worker-scoped resource extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
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
                input_contract=[
                    ContractFieldIR(
                        "query", "text", True, "User query", "input",
                        contract_demand_id="rcd_input_query",
                    )
                ],
            ),
            WorkerSpecIR(
                worker_id="worker_child",
                worker_name="ChildWorker",
                kind="child",
                purpose="Child worker",
                owned_span_ids=["s2"],
                output_contract=[
                    ContractFieldIR(
                        "result", "text", True, "Worker result", "output",
                        contract_demand_id="rcd_output_result",
                    )
                ],
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


def test_execute_worker_scoped_main_scope_excludes_child_spans(
    extractor: ResourceExtractor,
    mock_client: MagicMock,
    sample_spans: list[SpanIR],
    sample_routes: FieldRouteIR,
    sample_worker_plan: WorkerPlanIR,
    sample_flow_plan: WorkerFlowPlanIR,
    sample_block_plan: WorkerBlockPlanIR,
) -> None:
    """Main resource extraction prompt should not include child-owned spans."""
    extractor.execute_worker_scoped(
        spans=sample_spans,
        routes=sample_routes,
        worker_flow_plan=sample_flow_plan,
        worker_block_plan=sample_block_plan,
        worker_plan=sample_worker_plan,
    )

    first_prompt = mock_client.call_json.call_args_list[0].kwargs["user_prompt"]
    assert "User query" in first_prompt
    assert "Worker task" not in first_prompt


def test_execute_worker_scoped_seeds_contract_variables(
    extractor: ResourceExtractor,
    sample_spans: list[SpanIR],
    sample_routes: FieldRouteIR,
    sample_flow_plan: WorkerFlowPlanIR,
    sample_block_plan: WorkerBlockPlanIR,
) -> None:
    """WorkerSpec contracts are deterministic resources, not LLM guesses."""
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main worker",
                owned_span_ids=["s1"],
                input_contract=[
                    ContractFieldIR(
                        "main_input",
                        "text",
                        True,
                        "Main input",
                        "input",
                        contract_demand_id="rcd_main_input",
                    )
                ],
                output_contract=[
                    ContractFieldIR(
                        "main_output",
                        "text",
                        True,
                        "Main output",
                        "output",
                        contract_demand_id="rcd_main_output",
                    )
                ],
            ),
            WorkerSpecIR(
                worker_id="worker_child",
                worker_name="ChildWorker",
                kind="child",
                purpose="Child worker",
                owned_span_ids=["s2"],
                input_contract=[
                    ContractFieldIR(
                        "child_input",
                        "text",
                        True,
                        "Child input",
                        "input",
                        contract_demand_id="rcd_child_input",
                    )
                ],
                output_contract=[
                    ContractFieldIR(
                        "child_output",
                        "text",
                        True,
                        "Child output",
                        "output",
                        contract_demand_id="rcd_child_output",
                    )
                ],
            ),
        ],
    )

    result, symbol_table = extractor.execute_worker_scoped(
        spans=sample_spans,
        routes=sample_routes,
        worker_flow_plan=sample_flow_plan,
        worker_block_plan=sample_block_plan,
        worker_plan=worker_plan,
    )

    global_vars = {var.name: var for var in result.global_resources.variables}
    child_vars = {
        var.name: var for var in result.worker_resources["worker_child"].variables
    }
    assert global_vars["main_input"].source == "input"
    assert global_vars["main_output"].source == "output"
    assert child_vars["child_input"].source == "input"
    assert child_vars["child_output"].source == "output"
    assert symbol_table.get_variables_for_worker("worker_child")["child_output"].source == "output"


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


def test_build_handoff_contract_with_scoped_variables(
    extractor: ResourceExtractor,
) -> None:
    """Test _build_handoff_contract looks up worker-scoped variables."""
    from nl2spl.ir.symbol_table import SymbolTable

    symbol_table = SymbolTable()
    symbol_table.declare_scoped(
        name="query",
        data_type="text",
        source="input",
        description="Main worker query",
        scope_kind="worker",
        scope_id="worker_main",
    )
    symbol_table.declare_scoped(
        name="child_result",
        data_type="object",
        source="output",
        description="Child worker result",
        scope_kind="worker",
        scope_id="worker_child",
    )

    handoff = WorkerHandoffIR(
        handoff_id="handoff_1",
        from_worker="worker_main",
        to_worker="worker_child",
        api_ref=None,
        mode="invoke",
        condition_text=None,
        ordering="after",
        input_bindings=[
            InputBindingIR("query", "child_query", True)
        ],
        output_bindings=[
            OutputBindingIR("child_result", "result", True, "set")
        ],
    )

    contract = extractor._build_handoff_contract(handoff, symbol_table)

    assert contract.handoff_id == "handoff_1"
    assert len(contract.input_variables) == 1
    assert len(contract.output_variables) == 1
    # Should find worker-scoped variables, not fall back to "text"
    assert contract.input_variables[0].data_type == "text"
    assert contract.output_variables[0].data_type == "object"


def test_build_handoff_contract_missing_variable_fallback(
    extractor: ResourceExtractor,
) -> None:
    """Test _build_handoff_contract falls back to 'text' for missing variables."""
    from nl2spl.ir.symbol_table import SymbolTable

    symbol_table = SymbolTable()

    handoff = WorkerHandoffIR(
        handoff_id="handoff_1",
        from_worker="worker_main",
        to_worker="worker_child",
        api_ref=None,
        mode="invoke",
        condition_text=None,
        ordering="after",
        input_bindings=[
            InputBindingIR("unknown_var", "child_input", True)
        ],
        output_bindings=[
            OutputBindingIR("unknown_output", "result", True, "set")
        ],
    )

    contract = extractor._build_handoff_contract(handoff, symbol_table)

    assert contract.input_variables[0].data_type == "text"
    assert contract.output_variables[0].data_type == "text"


def test_build_handoff_contract_api_call_mode(
    extractor: ResourceExtractor,
) -> None:
    """Test _build_handoff_contract with api_call mode (to_worker=None)."""
    from nl2spl.ir.symbol_table import SymbolTable

    symbol_table = SymbolTable()
    symbol_table.declare("request", "text", "input", "Request")

    handoff = WorkerHandoffIR(
        handoff_id="handoff_api",
        from_worker="worker_main",
        to_worker=None,
        api_ref="external_api",
        mode="api_call",
        condition_text=None,
        ordering="after",
        input_bindings=[
            InputBindingIR("request", "api_request", True)
        ],
        output_bindings=[
            OutputBindingIR("api_result", "response", True, "set")
        ],
    )

    contract = extractor._build_handoff_contract(handoff, symbol_table)

    assert contract.handoff_id == "handoff_api"
    assert contract.parent_worker_id == "worker_main"
    assert contract.child_worker_id == ""


def test_build_handoff_contract_with_multiple_bindings(
    extractor: ResourceExtractor,
) -> None:
    """Test _build_handoff_contract with multiple input and output bindings."""
    from nl2spl.ir.symbol_table import SymbolTable

    symbol_table = SymbolTable()
    symbol_table.declare("query", "text", "input", "Query")
    symbol_table.declare("filters", "dict", "input", "Filters")
    symbol_table.declare("results", "list", "output", "Results")
    symbol_table.declare("metadata", "dict", "output", "Metadata")

    handoff = WorkerHandoffIR(
        handoff_id="handoff_multi",
        from_worker="worker_main",
        to_worker="worker_child",
        api_ref=None,
        mode="invoke",
        condition_text=None,
        ordering="after",
        input_bindings=[
            InputBindingIR("query", "child_query", True),
            InputBindingIR("filters", "child_filters", False),
        ],
        output_bindings=[
            OutputBindingIR("results", "parent_results", True, "merge"),
            OutputBindingIR("metadata", "parent_metadata", False, "set"),
        ],
    )

    contract = extractor._build_handoff_contract(handoff, symbol_table)

    assert len(contract.input_variables) == 2
    assert len(contract.output_variables) == 2
    assert contract.input_variables[0].name == "child_query"
    assert contract.input_variables[1].name == "child_filters"
    assert contract.input_variables[1].required is False
    assert contract.output_variables[0].name == "parent_results"
    assert contract.output_variables[1].name == "parent_metadata"
    assert contract.output_variables[1].required is False


def test_execute_worker_scoped_missing_flow_blocks_skips_worker(
    extractor: ResourceExtractor,
    sample_spans: list[SpanIR],
    sample_routes: FieldRouteIR,
) -> None:
    """Test execute_worker_scoped skips workers with missing flow/blocks."""
    from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR

    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main",
                owned_span_ids=["s1"],
                input_contract=[
                    ContractFieldIR(
                        "query", "text", True, "User query", "input",
                        contract_demand_id="rcd_input_query",
                    )
                ],
            ),
            WorkerSpecIR(
                worker_id="worker_missing",
                worker_name="MissingWorker",
                kind="child",
                purpose="Missing flow/blocks",
                owned_span_ids=["s2"],
            ),
        ],
    )
    flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(),
            # worker_missing intentionally omitted
        }
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", spans=["s1"])]
            ),
            # worker_missing intentionally omitted
        }
    )

    result, symbol_table = extractor.execute_worker_scoped(
        spans=sample_spans,
        routes=sample_routes,
        worker_flow_plan=flow_plan,
        worker_block_plan=block_plan,
        worker_plan=plan,
    )

    # Child worker with missing flow/blocks should not appear in worker_resources
    assert "worker_missing" not in result.worker_resources
    assert "worker_main" not in result.worker_resources  # main worker goes to global
    assert len(result.global_resources.variables) > 0


def test_execute_worker_scoped_multiple_child_workers(
    extractor: ResourceExtractor,
    sample_spans: list[SpanIR],
    sample_routes: FieldRouteIR,
) -> None:
    """Test execute_worker_scoped with multiple child workers."""
    plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Main",
                owned_span_ids=["s1"],
            ),
            WorkerSpecIR(
                worker_id="worker_child_a",
                worker_name="ChildA",
                kind="child",
                purpose="Child A",
                owned_span_ids=["s2"],
            ),
            WorkerSpecIR(
                worker_id="worker_child_b",
                worker_name="ChildB",
                kind="child",
                purpose="Child B",
                owned_span_ids=[],
            ),
        ],
    )
    flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(),
            "worker_child_a": FlowStructureIR(),
            "worker_child_b": FlowStructureIR(),
        }
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", spans=["s1"])]
            ),
            "worker_child_a": BlockStructureIR(
                main_flow_blocks=[BlockIR("b2", "SEQUENTIAL", spans=["s2"])]
            ),
            "worker_child_b": BlockStructureIR(
                main_flow_blocks=[BlockIR("b3", "SEQUENTIAL", spans=[])]
            ),
        }
    )

    result, symbol_table = extractor.execute_worker_scoped(
        spans=sample_spans,
        routes=sample_routes,
        worker_flow_plan=flow_plan,
        worker_block_plan=block_plan,
        worker_plan=plan,
    )

    assert "worker_child_a" in result.worker_resources
    assert "worker_child_b" in result.worker_resources
    assert len(result.worker_resources) == 2


def test_extract_resources_for_scope_includes_worker_context_in_prompt(
    extractor: ResourceExtractor,
    sample_spans: list[SpanIR],
    sample_routes: FieldRouteIR,
) -> None:
    """Test _extract_resources_for_scope includes worker context in LLM prompt."""
    from nl2spl.ir.symbol_table import SymbolTable

    worker_spec = WorkerSpecIR(
        worker_id="worker_test",
        worker_name="TestWorker",
        kind="child",
        purpose="Test resource extraction",
        owned_span_ids=["s1"],
        input_contract=[],
        output_contract=[],
    )

    extractor._extract_resources_for_scope(
        spans=sample_spans,
        routes=sample_routes,
        flow=FlowStructureIR(),
        blocks=BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", spans=["s1"])]
        ),
        symbol_table=SymbolTable(),
        scope_kind="worker",
        scope_id="worker_test",
        worker_spec=worker_spec,
    )

    # Verify the LLM was called with scoped worker metadata in the prompt
    call_args = extractor.client.call_json.call_args
    user_prompt = call_args.kwargs.get("user_prompt", "")
    assert "Resource extraction scope" in user_prompt
    assert "worker_id: worker_test" in user_prompt
    assert "TestWorker" in user_prompt
    assert "Test resource extraction" in user_prompt


def test_extract_resources_for_scope_includes_known_variables(
    extractor: ResourceExtractor,
    sample_spans: list[SpanIR],
    sample_routes: FieldRouteIR,
) -> None:
    """Test _extract_resources_for_scope includes known variables in prompt."""
    from nl2spl.ir.symbol_table import SymbolTable

    symbol_table = SymbolTable()
    symbol_table.declare_scoped(
        name="global_query",
        data_type="text",
        source="input",
        description="Global query text",
        scope_kind="global",
    )
    symbol_table.declare_scoped(
        name="local_temp",
        data_type="dict",
        source="step",
        description="Local temporary data",
        scope_kind="worker",
        scope_id="worker_test",
    )

    worker_spec = WorkerSpecIR(
        worker_id="worker_test",
        worker_name="TestWorker",
        kind="child",
        purpose="Test",
        owned_span_ids=["s1"],
        input_contract=[
            ContractFieldIR(
                name="input_data",
                data_type="text",
                required=True,
                description="Input data field",
                source="input",
            )
        ],
        output_contract=[
            ContractFieldIR(
                name="output_data",
                data_type="text",
                required=True,
                description="Output data field",
                source="output",
            )
        ],
    )

    extractor._extract_resources_for_scope(
        spans=sample_spans,
        routes=sample_routes,
        flow=FlowStructureIR(),
        blocks=BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", spans=["s1"])]
        ),
        symbol_table=symbol_table,
        scope_kind="worker",
        scope_id="worker_test",
        worker_spec=worker_spec,
    )

    call_args = extractor.client.call_json.call_args
    user_prompt = call_args.kwargs.get("user_prompt", "")

    # Verify worker scope with contracts
    assert "Resource extraction scope" in user_prompt
    assert "worker_id: worker_test" in user_prompt
    assert "TestWorker" in user_prompt
    assert "input_data" in user_prompt
    assert "output_data" in user_prompt

    # Verify known variables section
    assert "Known variables" in user_prompt
    assert "global_query" in user_prompt
    assert "local_temp" in user_prompt
