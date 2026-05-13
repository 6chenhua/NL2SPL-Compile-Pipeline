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


def test_get_all_declared_variables_includes_handoff_contracts() -> None:
    """Test get_all_declared_variables includes handoff input/output variables."""
    table = SymbolTable()

    # Global variable
    table.declare_scoped(
        name="query",
        data_type="text",
        source="input",
        description="Global query",
        scope_kind="global",
    )

    # Handoff input variable
    table.declare_scoped(
        name="handoff_input",
        data_type="text",
        source="input",
        description="Handoff input",
        scope_kind="handoff",
        scope_id="handoff_1",
    )

    # Handoff output variable
    table.declare_scoped(
        name="handoff_output",
        data_type="text",
        source="output",
        description="Handoff output",
        scope_kind="handoff",
        scope_id="handoff_1",
    )

    all_vars = table.get_all_declared_variables()

    assert "query" in all_vars
    assert "handoff_input" in all_vars  # input source => always included
    assert "handoff_output" in all_vars  # output source => always included


def test_get_all_declared_variables_excludes_unddeclared_internal() -> None:
    """Test get_all_declared_variables excludes internal step vars with declared=False."""
    table = SymbolTable()

    table.declare_scoped(
        name="internal_step_var",
        data_type="text",
        source="step",
        description="Internal step variable",
        scope_kind="worker",
        scope_id="worker_1",
    )
    table._variables[("worker", "worker_1", "internal_step_var")].declared = False

    all_vars = table.get_all_declared_variables()
    assert "internal_step_var" not in all_vars

    # Once declared is set back to True, it should appear
    table._variables[("worker", "worker_1", "internal_step_var")].declared = True
    all_vars = table.get_all_declared_variables()
    assert "internal_step_var" in all_vars


def test_get_variable_list_for_worker_prompt_includes_handoff_variables() -> None:
    """Test prompt generation when handoff-scoped variables exist."""
    table = SymbolTable()

    table.declare_scoped(
        name="global_var",
        data_type="text",
        source="input",
        description="Global variable",
        scope_kind="global",
    )

    table.declare_scoped(
        name="handoff_var",
        data_type="text",
        source="input",
        description="Handoff variable",
        scope_kind="handoff",
        scope_id="handoff_1",
    )

    # Worker prompt should include global vars but not handoff-scoped vars
    prompt = table.get_variable_list_for_worker_prompt("worker_1")
    assert "global_var" in prompt
    assert "handoff_var" not in prompt


def test_declare_scoped_preserves_flow_and_block_ref() -> None:
    """Test declare_scoped preserves flow_ref and block_ref."""
    table = SymbolTable()
    table.declare_scoped(
        name="var1",
        data_type="text",
        source="step",
        description="Variable with flow/block",
        scope_kind="worker",
        scope_id="worker_1",
        flow_ref="alternative",
        block_ref="b2",
    )

    key = ("worker", "worker_1", "var1")
    var = table._variables[key]
    assert var.flow_ref == "alternative"
    assert var.block_ref == "b2"


def test_declare_legacy_sets_correct_defaults() -> None:
    """Test declare() sets scope_kind='global' and scope_id=None."""
    table = SymbolTable()
    table.declare(
        name="query",
        data_type="text",
        source="input",
        description="User query",
        flow_ref="main",
        block_ref="b1",
    )

    var = table.variables["query"]
    assert var.scope_kind == "global"
    assert var.scope_id is None
    assert var.flow_ref == "main"
    assert var.block_ref == "b1"


def test_get_variables_for_worker_handoff_not_visible() -> None:
    """Test handoff-scoped variables are NOT visible to workers."""
    table = SymbolTable()

    table.declare_scoped(
        name="global_var",
        data_type="text",
        source="input",
        description="Global",
        scope_kind="global",
    )
    table.declare_scoped(
        name="handoff_var",
        data_type="text",
        source="input",
        description="Handoff",
        scope_kind="handoff",
        scope_id="handoff_1",
    )

    worker_vars = table.get_variables_for_worker("worker_1")
    assert "global_var" in worker_vars
    assert "handoff_var" not in worker_vars


def test_get_variables_for_handoff_worker_not_visible() -> None:
    """Test worker-scoped variables are NOT visible to handoffs."""
    table = SymbolTable()

    table.declare_scoped(
        name="global_var",
        data_type="text",
        source="input",
        description="Global",
        scope_kind="global",
    )
    table.declare_scoped(
        name="worker_var",
        data_type="text",
        source="step",
        description="Worker",
        scope_kind="worker",
        scope_id="worker_1",
    )

    handoff_vars = table.get_variables_for_handoff("handoff_1")
    assert "global_var" in handoff_vars
    assert "worker_var" not in handoff_vars


def test_global_variable_visible_to_both_worker_and_handoff() -> None:
    """Test global variables are visible to both worker and handoff queries."""
    table = SymbolTable()

    table.declare_scoped(
        name="shared_query",
        data_type="text",
        source="input",
        description="Shared query",
        scope_kind="global",
    )

    worker_vars = table.get_variables_for_worker("worker_1")
    handoff_vars = table.get_variables_for_handoff("handoff_1")

    assert "shared_query" in worker_vars
    assert "shared_query" in handoff_vars
