"""Phase 4 tests for ResourceResolver.

Covers:
1. Resolve variable resource
2. Resolve file resource
3. Attach binding when available
4. Return None for unknown resource
"""

from __future__ import annotations

from nl2spl.ir.resource_contract_ir import ResourceContractBindingIR
from nl2spl.ir.resource_registry_ir import FileSpec, ResourceRegistryIR, VariableSpec
from nl2spl.pipeline.resource_resolver import resolve_resource_ref


def _make_registry() -> ResourceRegistryIR:
    return ResourceRegistryIR(
        variables=[
            VariableSpec(
                name="topic_summary",
                data_type="text",
                required=True,
                description="Topic summary",
                source="input",
            ),
        ],
        files=[
            FileSpec(
                name="finished_draft",
                path="< >",
                data_type="text",
                description="Finished draft",
            ),
        ],
    )


def test_resolve_variable() -> None:
    """Variable in the registry is found."""
    registry = _make_registry()
    result = resolve_resource_ref("topic_summary", registry)
    assert result is not None
    assert result.name == "topic_summary"
    assert result.resource_kind == "variable"
    assert result.data_type == "text"


def test_resolve_file() -> None:
    """File in the registry is found."""
    registry = _make_registry()
    result = resolve_resource_ref("finished_draft", registry)
    assert result is not None
    assert result.name == "finished_draft"
    assert result.resource_kind == "file"
    assert result.data_type == "text"


def test_resolve_unknown_returns_none() -> None:
    """Unknown name returns None."""
    registry = _make_registry()
    result = resolve_resource_ref("nonexistent", registry)
    assert result is None


def test_resolve_with_binding() -> None:
    """When a binding matches, it is attached to the result."""
    registry = _make_registry()
    bindings = [
        ResourceContractBindingIR(
            contract_demand_id="rcd_output_s11",
            resource_name="finished_draft",
            resource_kind="file",
            direction="output",
            scope_kind="global",
            scope_id=None,
        ),
    ]
    result = resolve_resource_ref("finished_draft", registry, bindings)
    assert result is not None
    assert result.binding is not None
    assert result.binding.contract_demand_id == "rcd_output_s11"


def test_resolve_file_without_binding() -> None:
    """File without a binding still resolves."""
    registry = _make_registry()
    result = resolve_resource_ref("finished_draft", registry, bindings=[])
    assert result is not None
    assert result.resource_kind == "file"
    assert result.binding is None


def test_resolve_prefers_binding_in_requested_scope() -> None:
    """Same resource name in multiple scopes resolves to the requested scope."""
    registry = _make_registry()
    bindings = [
        ResourceContractBindingIR(
            contract_demand_id="rcd_output_global",
            resource_name="finished_draft",
            resource_kind="file",
            direction="output",
            scope_kind="global",
            scope_id=None,
        ),
        ResourceContractBindingIR(
            contract_demand_id="rcd_output_worker_child",
            resource_name="finished_draft",
            resource_kind="file",
            direction="output",
            scope_kind="worker",
            scope_id="worker_child",
        ),
    ]

    result = resolve_resource_ref(
        "finished_draft",
        registry,
        bindings,
        scope_kind="worker",
        scope_id="worker_child",
    )

    assert result is not None
    assert result.binding is not None
    assert result.binding.contract_demand_id == "rcd_output_worker_child"
