"""Unit tests for SymbolTable scope support (D4 decision)."""

from __future__ import annotations

from nl2spl.ir.symbol_table import SymbolTable, VariableSymbol


def test_variable_symbol_default_scope() -> None:
    """Test VariableSymbol has correct default scope."""
    var = VariableSymbol(
        name="query",
        data_type="text",
        source="input",
        description="User query",
    )

    assert var.scope_kind == "global"
    assert var.scope_id is None


def test_variable_symbol_worker_scope() -> None:
    """Test VariableSymbol with worker scope."""
    var = VariableSymbol(
        name="result",
        data_type="text",
        source="step",
        description="Worker result",
        scope_kind="worker",
        scope_id="worker_1",
    )

    assert var.scope_kind == "worker"
    assert var.scope_id == "worker_1"


def test_variable_symbol_handoff_scope() -> None:
    """Test VariableSymbol with handoff scope."""
    var = VariableSymbol(
        name="input",
        data_type="text",
        source="input",
        description="Handoff input",
        scope_kind="handoff",
        scope_id="handoff_1",
    )

    assert var.scope_kind == "handoff"
    assert var.scope_id == "handoff_1"


def test_symbol_table_declare_global() -> None:
    """Test declaring a global variable."""
    table = SymbolTable()
    table.declare(
        name="query",
        data_type="text",
        source="input",
        description="User query",
    )

    # Should be in both interfaces
    assert "query" in table.variables
    assert ("global", None, "query") in table._variables

    # Verify scope fields
    var = table.variables["query"]
    assert var.scope_kind == "global"
    assert var.scope_id is None


def test_symbol_table_declare_scoped_worker() -> None:
    """Test declaring a worker-scoped variable."""
    table = SymbolTable()
    table.declare_scoped(
        name="result",
        data_type="text",
        source="step",
        description="Worker result",
        scope_kind="worker",
        scope_id="worker_1",
    )

    # Should NOT be in legacy interface (only global goes there)
    assert "result" not in table.variables

    # Should be in new interface
    assert ("worker", "worker_1", "result") in table._variables

    # Verify scope fields
    var = table._variables[("worker", "worker_1", "result")]
    assert var.scope_kind == "worker"
    assert var.scope_id == "worker_1"


def test_symbol_table_declare_scoped_global() -> None:
    """Test declaring a global variable via declare_scoped."""
    table = SymbolTable()
    table.declare_scoped(
        name="query",
        data_type="text",
        source="input",
        description="User query",
        scope_kind="global",
        scope_id=None,
    )

    # Should be in both interfaces
    assert "query" in table.variables
    assert ("global", None, "query") in table._variables


def test_symbol_table_same_name_different_scope() -> None:
    """Test same variable name in different scopes."""
    table = SymbolTable()

    # Global variable
    table.declare_scoped(
        name="result",
        data_type="text",
        source="input",
        description="Global result",
        scope_kind="global",
    )

    # Worker variable with same name
    table.declare_scoped(
        name="result",
        data_type="text",
        source="step",
        description="Worker result",
        scope_kind="worker",
        scope_id="worker_1",
    )

    # Both should exist
    assert ("global", None, "result") in table._variables
    assert ("worker", "worker_1", "result") in table._variables

    # They should be different
    global_var = table._variables[("global", None, "result")]
    worker_var = table._variables[("worker", "worker_1", "result")]
    assert global_var.description == "Global result"
    assert worker_var.description == "Worker result"


def test_symbol_table_get_variables_for_worker() -> None:
    """Test getting variables visible to a worker."""
    table = SymbolTable()

    # Global variable
    table.declare_scoped(
        name="global_var",
        data_type="text",
        source="input",
        description="Global variable",
        scope_kind="global",
    )

    # Worker 1 variable
    table.declare_scoped(
        name="worker1_var",
        data_type="text",
        source="step",
        description="Worker 1 variable",
        scope_kind="worker",
        scope_id="worker_1",
    )

    # Worker 2 variable
    table.declare_scoped(
        name="worker2_var",
        data_type="text",
        source="step",
        description="Worker 2 variable",
        scope_kind="worker",
        scope_id="worker_2",
    )

    # Worker 1 should see global + worker1
    worker1_vars = table.get_variables_for_worker("worker_1")
    assert "global_var" in worker1_vars
    assert "worker1_var" in worker1_vars
    assert "worker2_var" not in worker1_vars

    # Worker 2 should see global + worker2
    worker2_vars = table.get_variables_for_worker("worker_2")
    assert "global_var" in worker2_vars
    assert "worker2_var" in worker2_vars
    assert "worker1_var" not in worker2_vars


def test_symbol_table_get_variables_for_handoff() -> None:
    """Test getting variables visible to a handoff."""
    table = SymbolTable()

    # Global variable
    table.declare_scoped(
        name="global_var",
        data_type="text",
        source="input",
        description="Global variable",
        scope_kind="global",
    )

    # Handoff 1 variable
    table.declare_scoped(
        name="handoff1_var",
        data_type="text",
        source="input",
        description="Handoff 1 variable",
        scope_kind="handoff",
        scope_id="handoff_1",
    )

    # Handoff 2 variable
    table.declare_scoped(
        name="handoff2_var",
        data_type="text",
        source="input",
        description="Handoff 2 variable",
        scope_kind="handoff",
        scope_id="handoff_2",
    )

    # Handoff 1 should see global + handoff1
    handoff1_vars = table.get_variables_for_handoff("handoff_1")
    assert "global_var" in handoff1_vars
    assert "handoff1_var" in handoff1_vars
    assert "handoff2_var" not in handoff1_vars

    # Handoff 2 should see global + handoff2
    handoff2_vars = table.get_variables_for_handoff("handoff_2")
    assert "global_var" in handoff2_vars
    assert "handoff2_var" in handoff2_vars
    assert "handoff1_var" not in handoff2_vars


def test_symbol_table_get_variable_list_for_worker_prompt() -> None:
    """Test generating variable list for worker prompt."""
    table = SymbolTable()

    # Global variable
    table.declare_scoped(
        name="global_var",
        data_type="text",
        source="input",
        description="Global variable",
        scope_kind="global",
    )

    # Worker variable
    table.declare_scoped(
        name="worker_var",
        data_type="text",
        source="step",
        description="Worker variable",
        scope_kind="worker",
        scope_id="worker_1",
    )

    # Get prompt for worker 1
    prompt = table.get_variable_list_for_worker_prompt("worker_1")

    # Should contain both variables
    assert "global_var" in prompt
    assert "worker_var" in prompt
    assert "[worker: worker_1]" in prompt


def test_symbol_table_get_all_declared_variables() -> None:
    """Test getting all declared variables."""
    table = SymbolTable()

    # Global variable
    table.declare_scoped(
        name="global_var",
        data_type="text",
        source="input",
        description="Global variable",
        scope_kind="global",
    )

    # Worker contract variable (input/output)
    table.declare_scoped(
        name="contract_var",
        data_type="text",
        source="input",
        description="Contract variable",
        scope_kind="worker",
        scope_id="worker_1",
    )

    # Worker internal variable (step, not declared)
    table.declare_scoped(
        name="internal_var",
        data_type="text",
        source="step",
        description="Internal variable",
        scope_kind="worker",
        scope_id="worker_1",
    )
    # Set declared=False for internal variable
    table._variables[("worker", "worker_1", "internal_var")].declared = False

    # Get all declared
    all_vars = table.get_all_declared_variables()

    # Global should be included
    assert "global_var" in all_vars

    # Contract should be included
    assert "contract_var" in all_vars

    # Internal should NOT be included (declared=False)
    assert "internal_var" not in all_vars


def test_symbol_table_backward_compatibility() -> None:
    """Test backward compatibility with existing code."""
    table = SymbolTable()

    # Use old declare method
    table.declare(
        name="query",
        data_type="text",
        source="input",
        description="User query",
    )

    # Should work with old interface
    assert "query" in table.variables
    var = table.variables["query"]
    assert var.name == "query"
    assert var.data_type == "text"

    # Should also work with new interface
    assert ("global", None, "query") in table._variables

    # Reference methods should still work
    assert table.reference("query") == "<REF>query</REF>"
    assert table.value_reference("query") == "<REF>*query</REF>"


def test_symbol_table_empty_worker_prompt() -> None:
    """Test generating prompt when no variables visible."""
    table = SymbolTable()

    # Get prompt for non-existent worker
    prompt = table.get_variable_list_for_worker_prompt("non_existent")

    assert prompt == "No variables available."
