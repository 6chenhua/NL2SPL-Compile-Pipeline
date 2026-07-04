from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.interaction.model import (
    RepairInputFieldView,
    RepairInputSchemaView,
    RepairInteractionView,
)


def _view(*schemas: RepairInputSchemaView) -> RepairInteractionView:
    return RepairInteractionView(
        issue_id="issue_1",
        strategy_id="worker_delegation.complete_closure.v2",
        option_id="define_child_worker",
        contract_id="worker_delegation.define_child_worker.v1",
        contract_version="1",
        revision_token="run:snapshot:0",
        interaction_kind="structured",
        availability="available",
        input_readiness="input_required",
        schemas=schemas,
    )


def test_interaction_schema_rejects_unknown_nested_reference() -> None:
    schema = RepairInputSchemaView(
        "schema.a.v1",
        "1",
        (
            RepairInputFieldView(
                "nested", "Nested", "structured_object", True, object_schema_id="missing"
            ),
        ),
    )
    with pytest.raises(ValueError, match="Unknown object schema"):
        _view(schema)


def test_interaction_schema_rejects_cycle() -> None:
    a = RepairInputSchemaView(
        "schema.a.v1",
        "1",
        (
            RepairInputFieldView(
                "to_b", "B", "structured_object", True, object_schema_id="schema.b.v1"
            ),
        ),
    )
    b = RepairInputSchemaView(
        "schema.b.v1",
        "1",
        (
            RepairInputFieldView(
                "to_a", "A", "structured_object", True, object_schema_id="schema.a.v1"
            ),
        ),
    )
    with pytest.raises(ValueError, match="Cyclic interaction schema"):
        _view(a, b)
