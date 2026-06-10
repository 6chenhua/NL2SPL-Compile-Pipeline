"""Phase 4 tests for Stage 6 resource_contracts materialization.

Covers:
1. ResourceContractFieldIR(resource_kind=file) -> FileSpec
2. scope-aware binding
3. binding contains demand_id + direction + scope
"""

from __future__ import annotations

from nl2spl.ir.resource_contract_ir import (
    ResourceContractBindingIR,
    ResourceContractFieldIR,
)
from nl2spl.ir.worker_plan_ir import ContractFieldIR, WorkerSpecIR
from nl2spl.pipeline.stages.stage6_resource_extractor.worker_scoped import (
    WorkerScopedMixin,
)


def test_resource_contract_field_file_kind_has_path() -> None:
    """File contract field carries path='< >' for runtime resolution."""
    field = ResourceContractFieldIR(
        demand_id="rcd_output_s11",
        name="finished_draft",
        resource_kind="file",
        direction="output",
        data_type="text",
        required=True,
        description="Finished draft in Word or Google Doc format",
        path="< >",
        source_span_ids=["s11"],
        evidence_text="Finished draft (Word or Google Doc, 200-500 words)",
    )
    assert field.resource_kind == "file"
    assert field.path == "< >"
    assert field.demand_id == "rcd_output_s11"


def test_resource_contract_field_variable_kind() -> None:
    """Variable contract field does NOT have a path."""
    field = ResourceContractFieldIR(
        demand_id="rcd_input_s8",
        name="topic_summary",
        resource_kind="variable",
        direction="input",
        data_type="text",
        required=True,
        description="Topic summary text",
        source_span_ids=["s8"],
    )
    assert field.resource_kind == "variable"
    assert field.path is None


def test_scope_aware_binding_contains_scope() -> None:
    """Binding must carry scope_kind and scope_id for multi-worker disambiguation."""
    binding = ResourceContractBindingIR(
        contract_demand_id="rcd_output_s11",
        resource_name="finished_draft",
        resource_kind="file",
        direction="output",
        scope_kind="global",
        scope_id=None,
        source_span_ids=["s11"],
        source_section_id="sec_required_outputs",
        source_packet_id="p_list_item_finished_draft",
    )
    assert binding.scope_kind == "global"
    assert binding.scope_id is None
    assert binding.contract_demand_id == "rcd_output_s11"


def test_worker_scope_binding_distinguishes_workers() -> None:
    """Two bindings for the same resource name in different workers are distinct."""
    b1 = ResourceContractBindingIR(
        contract_demand_id="rcd_output_s11",
        resource_name="finished_draft",
        resource_kind="file",
        direction="output",
        scope_kind="worker",
        scope_id="worker_main",
    )
    b2 = ResourceContractBindingIR(
        contract_demand_id="rcd_output_s11",
        resource_name="finished_draft",
        resource_kind="file",
        direction="output",
        scope_kind="worker",
        scope_id="worker_child_1",
    )
    assert b1.scope_id != b2.scope_id
    assert b1.resource_name == b2.resource_name


def test_stage6_syncs_file_contract_to_worker_output_without_variable_merge() -> None:
    """Stage 6 must backfill worker output contract from materialized fields."""
    worker = WorkerSpecIR(
        worker_id="worker_main",
        worker_name="MainWorker",
        kind="main",
        purpose="test",
        boundary_kind="main_worker",
        output_contract=[
            ContractFieldIR(
                name="",
                data_type="",
                required=True,
                description="Finished draft",
                source="output",
                contract_demand_id="rcd_output_s11",
            ),
        ],
    )
    field = ResourceContractFieldIR(
        demand_id="rcd_output_s11",
        name="finished_draft",
        resource_kind="file",
        direction="output",
        data_type="text",
        required=True,
        description="Finished draft document",
        path="< >",
    )

    WorkerScopedMixin._sync_resource_contract_fields_to_worker(worker, [field])
    output = worker.output_contract[0]

    assert output.name == "finished_draft"
    assert output.data_type == "text"
    assert output.resource_kind == "file"
    assert output.contract_demand_id == "rcd_output_s11"

    variables, warnings = WorkerScopedMixin()._merge_contract_variables([], worker)
    assert variables == []
    assert warnings == []
