"""R4 RepairMaterializationService and Registry unit tests."""

from __future__ import annotations

import json

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.spl_editing.context.required_output_context import RequiredOutputContextBuilder
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent, RepairEvidencePacket
from nl2spl.compiler.spl_editing.materialization import (
    IdAllocator,
    MaterializationDependencyClosure,
    MaterializationInput,
    MaterializationPlan,
    MaterializationPlanRegistry,
    MaterializationRequest,
    MaterializationResult,
    RefRoleConstraint,
    RepairMaterializationService,
    RequiredArtifactField,
    build_default_materialization_registry,
    validate_dependency_closure,
)
from nl2spl.compiler.spl_editing.materialization.errors import (
    DependencyClosureValidationError,
    DuplicateMaterializationPlanError,
    MaterializationConsistencyError,
    MaterializationPlanNotFoundError,
)
from nl2spl.compiler.spl_editing.selectable_refs import SelectableRefSetBuilder
from nl2spl.compiler.spl_editing.selectable_refs.model import (
    ResolvedSelectableRef,
    SelectableRef,
    SelectableRefSet,
)
from nl2spl.compiler.spl_editing.targets.required_output import RequiredOutputTargetResolver
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)

# ===========================================================================
# Dummies & Fixtures
# ===========================================================================


class DummyMaterializer:
    """Mock materializer implementing Materializer Protocol."""

    def __init__(
        self,
        materializer_id: str = "dummy_materializer",
        stage_authority: str = "stage7.worker_step_plan",
    ) -> None:
        self._materializer_id = materializer_id
        self._stage_authority = stage_authority
        self.called = False
        self.should_fail_with_consistency = False
        self.custom_result: MaterializationResult | None = None

    @property
    def materializer_id(self) -> str:
        return self._materializer_id

    @property
    def stage_authority(self) -> str:
        return self._stage_authority

    def materialize(self, input_data: MaterializationInput) -> MaterializationResult:
        self.called = True
        if self.should_fail_with_consistency:
            # return invalid IDs to trigger consistency exception in Service
            return MaterializationResult(
                patched_snapshot=input_data.snapshot,
                overlay_event=None,
                changed_refs=(),
                changed_step_ids=(),
                changed_handoff_ids=(),
                evidence_refs=(),
                materialization_plan_id="tampered_plan",
                materializer_id="tampered_materializer",
                materialization_authority="tampered_authority",
                consumed_selected_ref_ids=(),
                evidence_packet_id="tampered_packet",
                dependency_validation_metadata={},
            )
        if self.custom_result:
            return self.custom_result
        return MaterializationResult(
            patched_snapshot=input_data.snapshot,
            overlay_event=None,
            changed_refs=("step:w_main:st2",),
            changed_step_ids=("st2",),
            changed_handoff_ids=(),
            evidence_refs=(),
            materialization_plan_id=input_data.plan.materialization_plan_id,
            materializer_id=self.materializer_id,
            materialization_authority=self.stage_authority,
            consumed_selected_ref_ids=(),
            evidence_packet_id=input_data.evidence_packet.evidence_packet_id,
            dependency_validation_metadata={"validated": True},
        )


def _make_dummy_snapshot() -> ArtifactSnapshot:
    step_plan = WorkerStepPlanIR(
        main_worker_id="w_main",
        worker_steps={
            "w_main": [
                StepIR(
                    step_id="st1", text="Step 1", source_span_ids=[], command_type="GENERAL_COMMAND"
                )
            ]
        },
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "w_main": BlockStructureIR(main_flow_blocks=[BlockIR(block_id="b1", block_type="main")])
        }
    )
    worker_plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[
            WorkerSpecIR(
                worker_id="w_main", worker_name="Main Worker", kind="main", purpose="Testing"
            )
        ],
        handoffs=[
            WorkerHandoffIR(
                handoff_id="h1",
                from_worker="w_main",
                to_worker=None,
                api_ref=None,
                mode="invoke",
                condition_text=None,
                ordering="before",
            )
        ],
    )
    return ArtifactSnapshot(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=1,
        worker_step_plan=step_plan,
        worker_block_plan=block_plan,
        worker_plan=worker_plan,
    )


def _make_dummy_catalog_entry() -> RepairCatalogEntry:
    return RepairCatalogEntry(
        entry_id="REQUIRED_OUTPUT.producer.missing_output_producer.required_output.insert_or_bind_producer",
        affordance_id="required_output.insert_or_bind_producer",
        construct_type="REQUIRED_OUTPUT",
        slot_name="producer",
        diagnostic_kind="missing_output_producer",
        supported_patch_types=("InsertProducerStep",),
        default_verification_lane="B",
        materialization_plan_id="stage7.step_producer_repair.v1",
        selectable_ref_policy_id="required_output.producer.selectable_refs.v1",
        intent_schema_id="intent.insert_producer_step.v1",
        required_context_facts=("target_output_name",),
        stage_authority="stage7.worker_step_plan",
        editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        user_facing=True,
    )


def _make_dummy_intent() -> ConstructRepairIntent:
    return ConstructRepairIntent(
        intent_id="intent_1",
        issue_id="issue_1",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="required_output:w_main:required_output_context::draft",
        target_slot_name="producer",
        target_ref_id="required_output:w_main:required_output_context::draft",
        selected_ref_ids=(),
        materialization_plan_id="stage7.step_producer_repair.v1",
    )


def _make_dummy_refset() -> SelectableRefSet:
    return SelectableRefSet(
        set_id="set_1",
        issue_id="issue_1",
        snapshot_id="snap_1",
        worker_scope="w_main",
        refs=(
            SelectableRef(
                ref_id="required_output:w_main:required_output_context::draft",
                ref_kind="required_output",
                ref_role="target_output",
                canonical_name="draft",
                display_label="draft",
                worker_id="w_main",
            ),
        ),
        policy_id="required_output.producer.selectable_refs.v1",
        is_available=True,
    )


def _make_dummy_plan() -> MaterializationPlan:
    return MaterializationPlan(
        materialization_plan_id="stage7.step_producer_repair.v1",
        patch_type="InsertProducerStep",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        stage_authority="stage7.worker_step_plan",
        dependency_closure=MaterializationDependencyClosure(
            required_artifacts=("worker_step_plan", "worker_block_plan"),
            required_artifact_fields=(
                RequiredArtifactField(
                    artifact_name="worker_step_plan", field_path=("worker_steps",)
                ),
            ),
            required_ref_role_constraints=(
                RefRoleConstraint(role="target_output", min_count=1, max_count=1),
            ),
            worker_scope_requirement="main",
            required_id_allocator_namespaces=("step", "block"),
        ),
        editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        output_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        writes_to=("worker_step_plan_pre_normalize",),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id="dummy_materializer",
    )


# ===========================================================================
# Test Cases
# ===========================================================================


def test_registry_rejects_duplicate_plan_id() -> None:
    """Verify that registering a plan with a duplicate plan_id raises DuplicateMaterializationPlanError."""  # noqa: E501
    registry = MaterializationPlanRegistry()
    plan = _make_dummy_plan()
    m1 = DummyMaterializer()
    registry.register(plan, m1)

    m2 = DummyMaterializer()
    with pytest.raises(DuplicateMaterializationPlanError):
        registry.register(plan, m2)


def test_unknown_plan_id_fails() -> None:
    """Verify that looking up or getting materializer for an unregistered plan ID raises MaterializationPlanNotFoundError."""  # noqa: E501
    registry = MaterializationPlanRegistry()
    with pytest.raises(MaterializationPlanNotFoundError):
        registry.get("unknown_plan_id")
    with pytest.raises(MaterializationPlanNotFoundError):
        registry.get_materializer("unknown_plan_id")


def test_dependency_closure_rejects_missing_artifact() -> None:
    """Verify validate_dependency_closure rejects snapshot missing required artifacts."""
    plan = _make_dummy_plan()
    snapshot = ArtifactSnapshot(
        snapshot_id="snap_empty", compile_run_id="run_empty", overlay_version=1
    )
    refset = _make_dummy_refset()
    target = RepairTarget(
        target_ref="test",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=None,
        affordance_id="aff_1",
        construct_path=(),
        worker_id="w_main",
        canonical_name="draft",
    )
    allocator = IdAllocator.from_snapshot(
        snapshot, plan.dependency_closure.required_id_allocator_namespaces
    )

    res = validate_dependency_closure(plan, snapshot, refset, target, allocator)
    assert not res.is_valid
    assert any("worker_step_plan" in err for err in res.errors)
    assert any("worker_block_plan" in err for err in res.errors)


def test_dependency_closure_rejects_missing_ref_role() -> None:
    """Verify validate_dependency_closure rejects refsets lacking required ref roles."""
    plan = _make_dummy_plan()
    snapshot = _make_dummy_snapshot()
    # Empty refset
    refset = SelectableRefSet(
        set_id="set_1",
        issue_id="i1",
        snapshot_id="snap_1",
        worker_scope="w_main",
        refs=(),
        policy_id="required_output.producer.selectable_refs.v1",
        is_available=True,
    )
    target = RepairTarget(
        target_ref="test",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=None,
        affordance_id="aff_1",
        construct_path=(),
        worker_id="w_main",
        canonical_name="draft",
    )
    allocator = IdAllocator.from_snapshot(
        snapshot, plan.dependency_closure.required_id_allocator_namespaces
    )

    res = validate_dependency_closure(plan, snapshot, refset, target, allocator)
    assert not res.is_valid
    assert any("target_output" in err for err in res.errors)


def test_write_layer_lane_mismatch_rejected() -> None:
    """Verify validate_dependency_closure rejects pre-normalize writes targeting lane A."""
    # plan specifies pre-normalize write, normalizer=True, but lane is A
    plan = MaterializationPlan(
        materialization_plan_id="plan_mismatch",
        patch_type="InsertProducerStep",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        stage_authority="stage7.worker_step_plan",
        dependency_closure=MaterializationDependencyClosure(),
        editable_artifacts=("worker_step_plan",),
        output_artifacts=("worker_step_plan",),
        writes_to=("worker_step_plan_pre_normalize",),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="A",  # Invalid for pre-normalize write
        materializer_id="dummy_materializer",
    )
    snapshot = _make_dummy_snapshot()
    refset = _make_dummy_refset()
    target = RepairTarget(
        target_ref="test",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=None,
        affordance_id="aff_1",
        construct_path=(),
        worker_id="w_main",
        canonical_name="draft",
    )
    allocator = IdAllocator.from_snapshot(
        snapshot, plan.dependency_closure.required_id_allocator_namespaces
    )

    res = validate_dependency_closure(plan, snapshot, refset, target, allocator)
    assert not res.is_valid
    assert any("expected 'B'" in err or "verification_lane is 'A'" in err for err in res.errors)


def test_materialization_service_invokes_registered_materializer() -> None:
    """Verify that RepairMaterializationService correctly executes the registered materializer."""
    registry = MaterializationPlanRegistry()
    plan = _make_dummy_plan()
    m = DummyMaterializer()
    registry.register(plan, m)

    service = RepairMaterializationService(registry)
    target_ref_id = "required_output:w_main:required_output_context::draft"
    req = MaterializationRequest(
        snapshot=_make_dummy_snapshot(),
        issue=EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=(),
            issue_group_id=None,
            kind="missing_output_producer",
            target_ref=target_ref_id,
            irs_ref=None,
            missing_slot="producer",
            source_span_ids=(),
            message="msg",
        ),
        target=RepairTarget(
            target_ref=target_ref_id,
            target_kind="REQUIRED_OUTPUT",
            irs_ref=None,
            affordance_id="required_output.insert_or_bind_producer",
            construct_path=(),
            worker_id="w_main",
            canonical_name="draft",
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        ),
        catalog_entry=_make_dummy_catalog_entry(),
        intent=_make_dummy_intent(),
        refset=_make_dummy_refset(),
        resolved_refs=(),
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="packet_1",
            confirmed_intent_id="intent_1",
            repair_patch_id="patch_1",
            related_diagnostic_id="d1",
            user_text="fix",
        ),
    )

    res = service.materialize(req)
    assert m.called
    assert res.patched_snapshot is not None
    assert res.materialization_plan_id == "stage7.step_producer_repair.v1"


def test_materialization_plan_serializes_to_audit_metadata() -> None:
    """Verify that MaterializationPlan metadata can be serialized to a dictionary."""
    plan = _make_dummy_plan()
    meta = plan.to_audit_metadata()
    assert meta["materialization_plan_id"] == "stage7.step_producer_repair.v1"
    assert meta["patch_type"] == "InsertProducerStep"
    assert meta["verification_lane"] == "B"
    assert meta["normalizer_required"] is True


def test_catalog_intent_plan_id_mismatch() -> None:
    """Verify that RepairMaterializationService rejects mismatched plan IDs (tri-party check)."""
    registry = MaterializationPlanRegistry()
    plan = _make_dummy_plan()
    m = DummyMaterializer()
    registry.register(plan, m)
    service = RepairMaterializationService(registry)

    # Intent plan ID differs from registry plan
    target_ref_id = "required_output:w_main:required_output_context::draft"
    intent = ConstructRepairIntent(
        intent_id="intent_1",
        issue_id="issue_1",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="required_output:w_main:required_output_context::draft",
        target_slot_name="producer",
        target_ref_id=target_ref_id,
        selected_ref_ids=(),
        materialization_plan_id="mismatch_plan_id",
    )

    req = MaterializationRequest(
        snapshot=_make_dummy_snapshot(),
        issue=EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=(),
            issue_group_id=None,
            kind="missing_output_producer",
            target_ref=target_ref_id,
            irs_ref=None,
            missing_slot="producer",
            source_span_ids=(),
            message="msg",
        ),
        target=RepairTarget(
            target_ref=target_ref_id,
            target_kind="REQUIRED_OUTPUT",
            irs_ref=None,
            affordance_id="required_output.insert_or_bind_producer",
            construct_path=(),
            worker_id="w_main",
            canonical_name="draft",
        ),
        catalog_entry=_make_dummy_catalog_entry(),
        intent=intent,
        refset=_make_dummy_refset(),
        resolved_refs=(),
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="packet_1",
            confirmed_intent_id="intent_1",
            repair_patch_id="patch_1",
            related_diagnostic_id="d1",
            user_text="fix",
        ),
    )

    with pytest.raises(MaterializationPlanNotFoundError):
        service.materialize(req)


def test_dependency_failure_prevents_materializer_call() -> None:
    """Verify that the materializer is not invoked if dependency validation fails."""
    registry = MaterializationPlanRegistry()
    plan = _make_dummy_plan()
    m = DummyMaterializer()
    registry.register(plan, m)
    service = RepairMaterializationService(registry)

    # Snapshot lacks required artifacts but has matching snapshot_id
    snapshot = ArtifactSnapshot(snapshot_id="snap_1", compile_run_id="run_empty", overlay_version=1)
    target_ref_id = "required_output:w_main:required_output_context::draft"

    req = MaterializationRequest(
        snapshot=snapshot,
        issue=EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=(),
            issue_group_id=None,
            kind="missing_output_producer",
            target_ref=target_ref_id,
            irs_ref=None,
            missing_slot="producer",
            source_span_ids=(),
            message="msg",
        ),
        target=RepairTarget(
            target_ref=target_ref_id,
            target_kind="REQUIRED_OUTPUT",
            irs_ref=None,
            affordance_id="required_output.insert_or_bind_producer",
            construct_path=(),
            worker_id="w_main",
            canonical_name="draft",
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        ),
        catalog_entry=_make_dummy_catalog_entry(),
        intent=_make_dummy_intent(),
        refset=_make_dummy_refset(),
        resolved_refs=(),
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="packet_1",
            confirmed_intent_id="intent_1",
            repair_patch_id="patch_1",
            related_diagnostic_id="d1",
            user_text="fix",
        ),
    )

    with pytest.raises(DependencyClosureValidationError):
        service.materialize(req)

    assert not m.called


def test_materializer_typed_error_propagation() -> None:
    """Verify that any MaterializationError raised inside the materializer propagates upward."""

    class ErrorMaterializer:
        materializer_id = "dummy_materializer"
        stage_authority = "stage7.worker_step_plan"

        def materialize(self, input_data: MaterializationInput) -> MaterializationResult:
            raise DependencyClosureValidationError("Mock validation error inside materializer")

    registry = MaterializationPlanRegistry()
    plan = _make_dummy_plan()
    registry.register(plan, ErrorMaterializer())
    service = RepairMaterializationService(registry)

    target_ref_id = "required_output:w_main:required_output_context::draft"
    req = MaterializationRequest(
        snapshot=_make_dummy_snapshot(),
        issue=EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=(),
            issue_group_id=None,
            kind="missing_output_producer",
            target_ref=target_ref_id,
            irs_ref=None,
            missing_slot="producer",
            source_span_ids=(),
            message="msg",
        ),
        target=RepairTarget(
            target_ref=target_ref_id,
            target_kind="REQUIRED_OUTPUT",
            irs_ref=None,
            affordance_id="required_output.insert_or_bind_producer",
            construct_path=(),
            worker_id="w_main",
            canonical_name="draft",
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        ),
        catalog_entry=_make_dummy_catalog_entry(),
        intent=_make_dummy_intent(),
        refset=_make_dummy_refset(),
        resolved_refs=(),
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="packet_1",
            confirmed_intent_id="intent_1",
            repair_patch_id="patch_1",
            related_diagnostic_id="d1",
            user_text="fix",
        ),
    )

    with pytest.raises(DependencyClosureValidationError):
        service.materialize(req)


def test_default_registry_contains_registered_stage7_plans() -> None:
    """R9: default registry contains the materialized Stage7 MVP plans."""
    registry = build_default_materialization_registry()
    assert set(registry._plans) == {
        "stage7.step_producer_repair.v1",
        "stage7.exception_handler_step_repair.v1",
        "worker_handoff.contract_repair.v1",
        "worker_delegation.complete_closure.v2",
    }


def test_allocator_independent_of_overlay_version() -> None:
    """Verify IdAllocator allocation is independent of overlay_version or intent texts."""
    snapshot = _make_dummy_snapshot()
    allocator = IdAllocator.from_snapshot(snapshot, ("step", "block", "handoff"))

    # Allocations are sequential and stateful
    id1 = allocator.allocate_step_id()
    id2 = allocator.allocate_step_id()
    assert id1 != id2
    assert id1.startswith("st")
    assert id2.startswith("st")


def test_id_namespace_isolation_and_existing_id_collision() -> None:
    """Verify IdAllocator prevents collisions with existing snapshot IDs and maintains namespace isolation."""  # noqa: E501
    snapshot = _make_dummy_snapshot()  # Contains step_id='st1', block_id='b1', handoff_id='h1'
    allocator = IdAllocator.from_snapshot(snapshot, ("step", "block", "handoff"))

    allocated_step = allocator.allocate_step_id()
    assert allocated_step != "st1"  # Collision prevented

    allocated_block = allocator.allocate_block_id("w_main")
    assert allocated_block != "b1"  # Collision prevented

    allocated_handoff = allocator.allocate_handoff_id()
    assert allocated_handoff != "h1"  # Collision prevented


def test_frozen_dtos_immutability() -> None:
    """Verify that MaterializationPlan and dependency closure DTOs are frozen and immutable."""
    plan = _make_dummy_plan()
    with pytest.raises(AttributeError):
        plan.materialization_plan_id = "new_id"  # type: ignore[misc]

    with pytest.raises(AttributeError):
        plan.dependency_closure.required_artifacts = ()  # type: ignore[misc]


def test_json_serialization_of_audit_metadata() -> None:
    """Verify plan.to_audit_metadata() yields JSON-serializable keys and values."""
    plan = _make_dummy_plan()
    meta = plan.to_audit_metadata()
    serialized = json.dumps(meta)
    deserialized = json.loads(serialized)
    assert deserialized["materialization_plan_id"] == "stage7.step_producer_repair.v1"


def test_result_carries_audit_metadata_and_lineage() -> None:
    """Verify MaterializationResult properly carries required audit, plan, and evidence parameters."""  # noqa: E501
    res = MaterializationResult(
        patched_snapshot=_make_dummy_snapshot(),
        overlay_event=None,
        changed_refs=("step:w_main:st1",),
        changed_step_ids=("st1",),
        changed_handoff_ids=(),
        evidence_refs=(),
        materialization_plan_id="plan_1",
        materializer_id="mat_1",
        materialization_authority="authority_1",
        consumed_selected_ref_ids=("ref_1",),
        evidence_packet_id="packet_1",
        dependency_validation_metadata={"success": True},
    )
    assert res.materialization_plan_id == "plan_1"
    assert res.materializer_id == "mat_1"
    assert res.materialization_authority == "authority_1"
    assert res.consumed_selected_ref_ids == ("ref_1",)
    assert res.evidence_packet_id == "packet_1"


def test_dependency_closure_rejects_missing_field() -> None:
    """Verify validate_dependency_closure rejects snapshot missing required fields inside artifacts."""  # noqa: E501
    plan = MaterializationPlan(
        materialization_plan_id="plan_field_check",
        patch_type="InsertProducerStep",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        stage_authority="stage7.worker_step_plan",
        dependency_closure=MaterializationDependencyClosure(
            required_artifacts=("worker_step_plan",),
            required_artifact_fields=(
                RequiredArtifactField(
                    artifact_name="worker_step_plan", field_path=("non_existent_field",)
                ),
            ),
        ),
        editable_artifacts=("worker_step_plan",),
        output_artifacts=("worker_step_plan",),
        writes_to=("worker_step_plan_pre_normalize",),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id="dummy_materializer",
    )
    snapshot = _make_dummy_snapshot()
    refset = _make_dummy_refset()
    target = RepairTarget(
        target_ref="test",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=None,
        affordance_id="aff_1",
        construct_path=(),
        worker_id="w_main",
        canonical_name="draft",
    )
    allocator = IdAllocator.from_snapshot(
        snapshot, plan.dependency_closure.required_id_allocator_namespaces
    )

    res = validate_dependency_closure(plan, snapshot, refset, target, allocator)
    assert not res.is_valid
    assert any("non_existent_field" in err for err in res.errors)


def test_ref_role_min_max_bounds() -> None:
    """Verify role bounds apply to confirmed resolved refs, not all candidates."""
    plan = MaterializationPlan(
        materialization_plan_id="plan_role_bounds",
        patch_type="InsertProducerStep",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        stage_authority="stage7.worker_step_plan",
        dependency_closure=MaterializationDependencyClosure(
            required_ref_role_constraints=(
                RefRoleConstraint(role="selectable_input", min_count=1, max_count=1),
            ),
        ),
        editable_artifacts=("worker_step_plan",),
        output_artifacts=("worker_step_plan",),
        writes_to=("worker_step_plan_pre_normalize",),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id="dummy_materializer",
    )
    snapshot = _make_dummy_snapshot()
    refs = (
        SelectableRef(
            ref_id="ref_1",
            ref_kind="worker_input",
            ref_role="selectable_input",
            canonical_name="name1",
            display_label="l1",
            worker_id="w_main",
        ),
        SelectableRef(
            ref_id="ref_2",
            ref_kind="worker_input",
            ref_role="selectable_input",
            canonical_name="name2",
            display_label="l2",
            worker_id="w_main",
        ),
    )
    refset = SelectableRefSet(
        set_id="set_1",
        issue_id="i1",
        snapshot_id="snap_1",
        worker_scope="w_main",
        refs=refs,
        policy_id="required_output.producer.selectable_refs.v1",
        is_available=True,
    )
    target = RepairTarget(
        target_ref="test",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=None,
        affordance_id="aff_1",
        construct_path=(),
        worker_id="w_main",
        canonical_name="draft",
    )
    allocator = IdAllocator.from_snapshot(
        snapshot, plan.dependency_closure.required_id_allocator_namespaces
    )
    resolved_refs = tuple(
        ResolvedSelectableRef(ref=ref, resolved_role="selectable_input", scope_matched=True)
        for ref in refs
    )

    res = validate_dependency_closure(
        plan, snapshot, refset, target, allocator, resolved_refs=resolved_refs
    )
    assert not res.is_valid
    assert any("greater than max_count 1" in err for err in res.errors)


def test_worker_scope_mismatch() -> None:
    """Verify validate_dependency_closure rejects targets mismatching required worker scope (e.g. main vs child)."""  # noqa: E501
    plan = MaterializationPlan(
        materialization_plan_id="plan_worker_scope",
        patch_type="InsertProducerStep",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        stage_authority="stage7.worker_step_plan",
        dependency_closure=MaterializationDependencyClosure(
            worker_scope_requirement="child",  # Requires child scope
        ),
        editable_artifacts=("worker_step_plan",),
        output_artifacts=("worker_step_plan",),
        writes_to=("worker_step_plan_pre_normalize",),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id="dummy_materializer",
    )
    snapshot = _make_dummy_snapshot()
    refset = _make_dummy_refset()

    # Target points to main worker ID instead of child worker
    target = RepairTarget(
        target_ref="test",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=None,
        affordance_id="aff_1",
        construct_path=(),
        worker_id="w_main",
        canonical_name="draft",
    )
    allocator = IdAllocator.from_snapshot(
        snapshot, plan.dependency_closure.required_id_allocator_namespaces
    )

    res = validate_dependency_closure(plan, snapshot, refset, target, allocator)
    assert not res.is_valid
    assert any("requires a child worker scope" in err for err in res.errors)


def test_allocator_unavailable_namespace() -> None:
    """Verify validate_dependency_closure rejects allocations requiring namespaces unsupported by allocator."""  # noqa: E501
    plan = MaterializationPlan(
        materialization_plan_id="plan_alloc_ns",
        patch_type="InsertProducerStep",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        stage_authority="stage7.worker_step_plan",
        dependency_closure=MaterializationDependencyClosure(
            required_id_allocator_namespaces=("unknown_ns",),
        ),
        editable_artifacts=("worker_step_plan",),
        output_artifacts=("worker_step_plan",),
        writes_to=("worker_step_plan_pre_normalize",),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id="dummy_materializer",
    )
    snapshot = _make_dummy_snapshot()
    refset = _make_dummy_refset()
    target = RepairTarget(
        target_ref="test",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=None,
        affordance_id="aff_1",
        construct_path=(),
        worker_id="w_main",
        canonical_name="draft",
    )
    allocator = IdAllocator.from_snapshot(
        snapshot, ("step", "block", "handoff")
    )  # Namespace 'unknown_ns' is not supported

    res = validate_dependency_closure(plan, snapshot, refset, target, allocator)
    assert not res.is_valid
    assert any("namespace 'unknown_ns' is not available" in err for err in res.errors)


def test_materializer_id_mismatch_during_registration() -> None:
    """Verify that registering a materializer with mismatched materializer_id raises MaterializationConsistencyError."""  # noqa: E501
    registry = MaterializationPlanRegistry()
    plan = _make_dummy_plan()
    # Materializer ID does not match plan.materializer_id
    m = DummyMaterializer(materializer_id="mismatched_id")
    with pytest.raises(MaterializationConsistencyError):
        registry.register(plan, m)


def test_write_layer_verification_lane_compatibility_matrix() -> None:
    """Verify writes_to matrix constraints enforce normalizer requirements and lanes."""
    # Plan specifies pre-normalize writes, but normalizer_required is False
    plan = MaterializationPlan(
        materialization_plan_id="plan_layer_mismatch",
        patch_type="InsertProducerStep",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        stage_authority="stage7.worker_step_plan",
        dependency_closure=MaterializationDependencyClosure(),
        editable_artifacts=("worker_step_plan",),
        output_artifacts=("worker_step_plan",),
        writes_to=("worker_step_plan_pre_normalize",),
        normalizer_required=False,  # Mismatch: pre-normalize requires normalizer
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id="dummy_materializer",
    )
    snapshot = _make_dummy_snapshot()
    refset = _make_dummy_refset()
    target = RepairTarget(
        target_ref="test",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=None,
        affordance_id="aff_1",
        construct_path=(),
        worker_id="w_main",
        canonical_name="draft",
    )
    allocator = IdAllocator.from_snapshot(
        snapshot, plan.dependency_closure.required_id_allocator_namespaces
    )

    res = validate_dependency_closure(plan, snapshot, refset, target, allocator)
    assert not res.is_valid
    assert any("normalizer_required is False" in err for err in res.errors)


def test_materializer_tampered_metadata_rejected_by_service() -> None:
    """Verify Service rejects MaterializationResult if returned plan ID or materializer ID has been tampered with."""  # noqa: E501
    registry = MaterializationPlanRegistry()
    plan = _make_dummy_plan()
    m = DummyMaterializer()
    m.should_fail_with_consistency = True  # Materializer will return invalid metadata in result
    registry.register(plan, m)

    service = RepairMaterializationService(registry)
    target_ref_id = "required_output:w_main:required_output_context::draft"
    req = MaterializationRequest(
        snapshot=_make_dummy_snapshot(),
        issue=EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=(),
            issue_group_id=None,
            kind="missing_output_producer",
            target_ref=target_ref_id,
            irs_ref=None,
            missing_slot="producer",
            source_span_ids=(),
            message="msg",
        ),
        target=RepairTarget(
            target_ref=target_ref_id,
            target_kind="REQUIRED_OUTPUT",
            irs_ref=None,
            affordance_id="required_output.insert_or_bind_producer",
            construct_path=(),
            worker_id="w_main",
            canonical_name="draft",
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        ),
        catalog_entry=_make_dummy_catalog_entry(),
        intent=_make_dummy_intent(),
        refset=_make_dummy_refset(),
        resolved_refs=(),
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="packet_1",
            confirmed_intent_id="intent_1",
            repair_patch_id="patch_1",
            related_diagnostic_id="d1",
            user_text="fix",
        ),
    )

    # Since all input checks pass, it will execute DummyMaterializer.materialize()
    # and fail on the returned tampered metadata (which triggers MaterializationConsistencyError)
    with pytest.raises(MaterializationConsistencyError) as excinfo:
        service.materialize(req)
    assert "Materializer returned invalid plan ID" in str(excinfo.value)


def test_regression_required_output_catalog_entry_lane_is_b() -> None:
    """Regression test: verify required-output and exception-flow catalog entries default to lane B."""  # noqa: E501
    registry = SPLConstructRegistry.default()
    # 1. check required_output
    ro_irs = registry.get("REQUIRED_OUTPUT")
    ro_slot = ro_irs.get_slot("producer")
    assert ro_slot is not None
    ro_aff = next(
        a
        for a in ro_slot.repair_affordances
        if a.affordance_id == "required_output.insert_or_bind_producer"
    )
    assert ro_aff.default_verification_lane == "B"

    # 2. check exception_flow
    ef_irs = registry.get("EXCEPTION_FLOW")
    ef_slot = ef_irs.get_slot("handler_action")
    assert ef_slot is not None
    ef_aff = next(
        a
        for a in ef_slot.repair_affordances
        if a.affordance_id == "exception_flow.add_handler_step"
    )
    assert ef_aff.default_verification_lane == "B"


def test_id_allocator_unknown_namespace_rejected() -> None:
    """Verify that constructing or scanning with unknown namespaces raises ValueError."""
    # 1. Constructor rejection
    with pytest.raises(ValueError):
        IdAllocator(set(), set(), set(), ("unknown_ns",))

    # 2. from_snapshot rejection
    snapshot = _make_dummy_snapshot()
    with pytest.raises(ValueError):
        IdAllocator.from_snapshot(snapshot, ("step", "unknown_ns"))


def test_id_allocator_namespace_availability_depends_on_artifact() -> None:
    """Verify namespace availability is active only if the source artifact exists and is scanned successfully."""  # noqa: E501
    # 1. If artifact is missing in snapshot, the namespace is not available
    snapshot_missing = ArtifactSnapshot(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=1,
        worker_step_plan=None,  # missing step plan
        worker_block_plan=None,  # missing block plan
        worker_plan=None,  # missing worker plan
    )
    allocator = IdAllocator.from_snapshot(snapshot_missing, ("step", "block", "handoff"))
    assert not allocator.is_namespace_available("step")
    assert not allocator.is_namespace_available("block")
    assert not allocator.is_namespace_available("handoff")

    # 2. If artifact is present in snapshot, it is available
    snapshot_ok = _make_dummy_snapshot()
    allocator_ok = IdAllocator.from_snapshot(snapshot_ok, ("step", "block", "handoff"))
    assert allocator_ok.is_namespace_available("step")
    assert allocator_ok.is_namespace_available("block")
    assert allocator_ok.is_namespace_available("handoff")


def test_service_ref_lineage_reconciliation_fails() -> None:
    """Verify strict check of selected vs confirmed vs resolved refs, and consumed refs bounds check."""  # noqa: E501
    registry = MaterializationPlanRegistry()
    plan = _make_dummy_plan()
    m = DummyMaterializer()
    registry.register(plan, m)
    service = RepairMaterializationService(registry)
    target_ref_id = "required_output:w_main:required_output_context::draft"

    # Mismatch 1: intent has selected refs but evidence packet confirms none
    req_mismatch_evidence = MaterializationRequest(
        snapshot=_make_dummy_snapshot(),
        issue=EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=(),
            issue_group_id=None,
            kind="missing_output_producer",
            target_ref=target_ref_id,
            irs_ref=None,
            missing_slot="producer",
            source_span_ids=(),
            message="msg",
        ),
        target=RepairTarget(
            target_ref=target_ref_id,
            target_kind="REQUIRED_OUTPUT",
            irs_ref=None,
            affordance_id="required_output.insert_or_bind_producer",
            construct_path=(),
            worker_id="w_main",
            canonical_name="draft",
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        ),
        catalog_entry=_make_dummy_catalog_entry(),
        intent=ConstructRepairIntent(
            intent_id="intent_1",
            issue_id="issue_1",
            patch_type="InsertProducerStep",
            affordance_id="required_output.insert_or_bind_producer",
            target_construct_type="REQUIRED_OUTPUT",
            target_construct_id=target_ref_id,
            target_slot_name="producer",
            target_ref_id=target_ref_id,
            selected_ref_ids=("ref_a",),  # selected ref_a
            materialization_plan_id="stage7.step_producer_repair.v1",
        ),
        refset=_make_dummy_refset(),
        resolved_refs=(),
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="packet_1",
            confirmed_intent_id="intent_1",
            repair_patch_id="patch_1",
            related_diagnostic_id="d1",
            user_text="fix",
            confirmed_selected_ref_ids=(),  # mismatch: empty
        ),
    )
    with pytest.raises(MaterializationConsistencyError) as excinfo:
        service.materialize(req_mismatch_evidence)
    assert "Ref lineage mismatch" in str(excinfo.value)

    # Mismatch 2: materializer returns consumed refs that were not resolved (hallucinated consumed ref)  # noqa: E501
    # Correct input refs alignment:
    ref_a_obj = SelectableRef(
        ref_id="ref_a",
        ref_kind="step",
        ref_role="selectable_input",
        canonical_name="a",
        display_label="a",
        worker_id="w_main",
    )
    dummy_refset = SelectableRefSet(
        set_id="set_1",
        issue_id="issue_1",
        snapshot_id="snap_1",
        worker_scope="w_main",
        refs=(
            SelectableRef(
                ref_id="required_output:w_main:required_output_context::draft",
                ref_kind="required_output",
                ref_role="target_output",
                canonical_name="draft",
                display_label="draft",
                worker_id="w_main",
            ),
            ref_a_obj,
        ),
        policy_id="required_output.producer.selectable_refs.v1",
        is_available=True,
    )
    resolved_ref_a = ResolvedSelectableRef(
        ref=ref_a_obj, resolved_role="selectable_input", scope_matched=True
    )

    # Materializer returns hallucinated consumed ref_b
    m.custom_result = MaterializationResult(
        patched_snapshot=_make_dummy_snapshot(),
        overlay_event=None,
        changed_refs=(),
        changed_step_ids=(),
        changed_handoff_ids=(),
        evidence_refs=(),
        materialization_plan_id=plan.materialization_plan_id,
        materializer_id=plan.materializer_id,
        materialization_authority=plan.stage_authority,
        consumed_selected_ref_ids=("ref_b",),  # hallucinated!
        evidence_packet_id="packet_1",
        dependency_validation_metadata={},
    )

    req_consumed_mismatch = MaterializationRequest(
        snapshot=_make_dummy_snapshot(),
        issue=EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=(),
            issue_group_id=None,
            kind="missing_output_producer",
            target_ref=target_ref_id,
            irs_ref=None,
            missing_slot="producer",
            source_span_ids=(),
            message="msg",
        ),
        target=RepairTarget(
            target_ref=target_ref_id,
            target_kind="REQUIRED_OUTPUT",
            irs_ref=None,
            affordance_id="required_output.insert_or_bind_producer",
            construct_path=(),
            worker_id="w_main",
            canonical_name="draft",
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        ),
        catalog_entry=_make_dummy_catalog_entry(),
        intent=ConstructRepairIntent(
            intent_id="intent_1",
            issue_id="issue_1",
            patch_type="InsertProducerStep",
            affordance_id="required_output.insert_or_bind_producer",
            target_construct_type="REQUIRED_OUTPUT",
            target_construct_id=target_ref_id,
            target_slot_name="producer",
            target_ref_id=target_ref_id,
            selected_ref_ids=("ref_a",),
            materialization_plan_id="stage7.step_producer_repair.v1",
        ),
        refset=dummy_refset,
        resolved_refs=(resolved_ref_a,),
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="packet_1",
            confirmed_intent_id="intent_1",
            repair_patch_id="patch_1",
            related_diagnostic_id="d1",
            user_text="fix",
            confirmed_selected_ref_ids=("ref_a",),
        ),
    )
    with pytest.raises(MaterializationConsistencyError) as excinfo:
        service.materialize(req_consumed_mismatch)
    assert "Consumed selected ref IDs" in str(excinfo.value)
    m.custom_result = None  # reset


def test_service_id_associations_validation_fails() -> None:
    """Verify that mismatching issue ID or intent ID raises MaterializationConsistencyError."""
    registry = MaterializationPlanRegistry()
    plan = _make_dummy_plan()
    m = DummyMaterializer()
    registry.register(plan, m)
    service = RepairMaterializationService(registry)
    target_ref_id = "required_output:w_main:required_output_context::draft"

    # Mismatch: intent has issue_id="issue_2" but issue has "issue_1"
    req_mismatch_issue = MaterializationRequest(
        snapshot=_make_dummy_snapshot(),
        issue=EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=(),
            issue_group_id=None,
            kind="missing_output_producer",
            target_ref=target_ref_id,
            irs_ref=None,
            missing_slot="producer",
            source_span_ids=(),
            message="msg",
        ),
        target=RepairTarget(
            target_ref=target_ref_id,
            target_kind="REQUIRED_OUTPUT",
            irs_ref=None,
            affordance_id="required_output.insert_or_bind_producer",
            construct_path=(),
            worker_id="w_main",
            canonical_name="draft",
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        ),
        catalog_entry=_make_dummy_catalog_entry(),
        intent=ConstructRepairIntent(
            intent_id="intent_1",
            issue_id="issue_2",  # Mismatch
            patch_type="InsertProducerStep",
            affordance_id="required_output.insert_or_bind_producer",
            target_construct_type="REQUIRED_OUTPUT",
            target_construct_id=target_ref_id,
            target_slot_name="producer",
            target_ref_id=target_ref_id,
            selected_ref_ids=(),
            materialization_plan_id="stage7.step_producer_repair.v1",
        ),
        refset=_make_dummy_refset(),
        resolved_refs=(),
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="packet_1",
            confirmed_intent_id="intent_1",
            repair_patch_id="patch_1",
            related_diagnostic_id="d1",
            user_text="fix",
        ),
    )
    with pytest.raises(MaterializationConsistencyError) as excinfo:
        service.materialize(req_mismatch_issue)
    assert "Issue ID mismatch: intent has" in str(excinfo.value)


def test_worker_scope_requirement_cannot_be_bypassed_by_empty_worker() -> None:
    """Verify that worker scope requirement checks are not bypassed by a missing or None worker_id."""  # noqa: E501
    plan = _make_dummy_plan()  # requires main worker scope
    snapshot = _make_dummy_snapshot()
    refset = _make_dummy_refset()
    allocator = IdAllocator.from_snapshot(
        snapshot, plan.dependency_closure.required_id_allocator_namespaces
    )

    # 1. target.worker_id is None
    target_no_worker = RepairTarget(
        target_ref="test",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=None,
        affordance_id="aff_1",
        construct_path=(),
        worker_id=None,  # Mismatch: None worker ID
    )
    res1 = validate_dependency_closure(plan, snapshot, refset, target_no_worker, allocator)
    assert not res1.is_valid
    assert any("Target worker_id is missing, but plan requires" in err for err in res1.errors)

    # 2. target.worker_id is empty string
    target_empty_worker = RepairTarget(
        target_ref="test",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=None,
        affordance_id="aff_1",
        construct_path=(),
        worker_id="",  # Mismatch: empty worker ID
    )
    res2 = validate_dependency_closure(plan, snapshot, refset, target_empty_worker, allocator)
    assert not res2.is_valid
    assert any("Target worker_id is missing, but plan requires" in err for err in res2.errors)


def test_registry_prevents_duplicate_materializer_different_authority() -> None:
    """Verify registry raises MaterializationConsistencyError if same materializer_id binds to multiple authorities."""  # noqa: E501
    registry = MaterializationPlanRegistry()
    plan1 = _make_dummy_plan()
    m1 = DummyMaterializer(
        materializer_id="dummy_materializer", stage_authority="stage7.worker_step_plan"
    )
    registry.register(plan1, m1)

    plan2 = MaterializationPlan(
        materialization_plan_id="another_plan_id",
        patch_type="InsertProducerStep",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        stage_authority="stage9.worker_handoff",  # Different authority!
        dependency_closure=MaterializationDependencyClosure(),
        editable_artifacts=("WorkerStepPlanIR",),
        output_artifacts=("WorkerStepPlanIR",),
        writes_to=("worker_step_plan_pre_normalize",),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id="dummy_materializer",  # Mismatched authority registration
    )
    m2 = DummyMaterializer(
        materializer_id="dummy_materializer", stage_authority="stage9.worker_handoff"
    )
    with pytest.raises(MaterializationConsistencyError) as excinfo:
        registry.register(plan2, m2)
    assert "already registered under stage authority" in str(excinfo.value)


def test_plan_to_audit_metadata_roundtrip_serialization() -> None:
    """Verify complete recursive serialization/deserialization of dependency closure and plan fields."""  # noqa: E501
    plan = _make_dummy_plan()
    meta = plan.to_audit_metadata()

    # Reconstruct plan from serialized metadata dict
    reconstructed = MaterializationPlan.from_audit_metadata(meta)
    assert reconstructed == plan
    assert (
        reconstructed.dependency_closure.required_artifacts
        == plan.dependency_closure.required_artifacts
    )
    assert (
        reconstructed.dependency_closure.required_artifact_fields
        == plan.dependency_closure.required_artifact_fields
    )
    assert (
        reconstructed.dependency_closure.required_ref_role_constraints
        == plan.dependency_closure.required_ref_role_constraints
    )
    assert (
        reconstructed.dependency_closure.worker_scope_requirement
        == plan.dependency_closure.worker_scope_requirement
    )
    assert (
        reconstructed.dependency_closure.required_id_allocator_namespaces
        == plan.dependency_closure.required_id_allocator_namespaces
    )


def test_real_required_output_target_binds_to_selectable_target_ref() -> None:
    """Production issue-target and selectable-ref namespaces bind structurally."""
    snapshot = _make_dummy_snapshot()
    snapshot = ArtifactSnapshot(
        snapshot_id=snapshot.snapshot_id,
        compile_run_id=snapshot.compile_run_id,
        overlay_version=snapshot.overlay_version,
        worker_plan=snapshot.worker_plan,
        worker_block_plan=snapshot.worker_block_plan,
        worker_step_plan=snapshot.worker_step_plan,
        resources=ResourceRegistryIR(),
        symbol_table=SymbolTable(),
    )
    issue = EditableIssue(
        issue_id="issue_1",
        primary_diagnostic_id="d1",
        related_diagnostic_ids=("d1",),
        issue_group_id=None,
        kind="missing_output_producer",
        target_ref="worker:w_main.output:draft",
        irs_ref=DiagnosticIRSRef(
            construct_type="REQUIRED_OUTPUT",
            construct_id="worker:w_main.output:draft",
            slot_name="producer",
        ),
        missing_slot="producer",
        source_span_ids=(),
        message="Missing producer",
        default_affordance_id="required_output.insert_or_bind_producer",
    )
    target = RequiredOutputTargetResolver().resolve(issue, snapshot)
    context = RequiredOutputContextBuilder().build(issue, target, snapshot)
    refset = SelectableRefSetBuilder.build(snapshot, context)
    target_ref = next(ref for ref in refset.refs if ref.ref_role == "target_output")

    catalog_entry = _make_dummy_catalog_entry()
    plan = _make_dummy_plan()
    registry = MaterializationPlanRegistry()
    materializer = DummyMaterializer()
    registry.register(plan, materializer)
    intent = ConstructRepairIntent(
        intent_id="intent_1",
        issue_id=issue.issue_id,
        patch_type="InsertProducerStep",
        affordance_id=catalog_entry.affordance_id,
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id=issue.irs_ref.construct_id,
        target_slot_name="producer",
        target_ref_id=target_ref.ref_id,
        selected_ref_ids=(),
        materialization_plan_id=plan.materialization_plan_id,
    )
    request = MaterializationRequest(
        snapshot=snapshot,
        issue=issue,
        target=target,
        catalog_entry=catalog_entry,
        intent=intent,
        refset=refset,
        resolved_refs=(),
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="packet_1",
            confirmed_intent_id=intent.intent_id,
            repair_patch_id="patch_1",
            related_diagnostic_id=issue.primary_diagnostic_id,
            user_text="fix",
        ),
    )

    result = RepairMaterializationService(registry).materialize(request)
    assert materializer.called
    assert result.materialization_plan_id == plan.materialization_plan_id
    assert target.target_ref == "worker:w_main.output:draft"
    assert target_ref.ref_id.startswith("required_output:w_main:")


def test_dependency_role_minimum_ignores_unselected_candidates() -> None:
    """Available candidates cannot satisfy a required confirmed-input role."""
    input_ref = SelectableRef(
        ref_id="input:w_main:field",
        ref_kind="worker_input",
        ref_role="selectable_input",
        canonical_name="field",
        display_label="field",
        worker_id="w_main",
    )
    target_ref = _make_dummy_refset().refs[0]
    refset = SelectableRefSet(
        set_id="set_1",
        issue_id="issue_1",
        snapshot_id="snap_1",
        worker_scope="w_main",
        refs=(target_ref, input_ref),
        policy_id="required_output.producer.selectable_refs.v1",
    )
    plan = MaterializationPlan(
        materialization_plan_id="selected_inputs_required",
        patch_type="InsertProducerStep",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        stage_authority="stage7.worker_step_plan",
        dependency_closure=MaterializationDependencyClosure(
            required_ref_role_constraints=(
                RefRoleConstraint(role="selectable_input", min_count=1, max_count=None),
            ),
        ),
        editable_artifacts=("WorkerStepPlanIR",),
        output_artifacts=("WorkerStepPlanIR",),
        writes_to=("worker_step_plan_pre_normalize",),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id="dummy_materializer",
    )
    snapshot = _make_dummy_snapshot()
    result = validate_dependency_closure(
        plan,
        snapshot,
        refset,
        RepairTarget(
            target_ref="worker:w_main.output:draft",
            target_kind="REQUIRED_OUTPUT",
            irs_ref=None,
            affordance_id="required_output.insert_or_bind_producer",
            construct_path=(),
            worker_id="w_main",
            canonical_name="draft",
        ),
        IdAllocator.from_snapshot(snapshot, ()),
        resolved_refs=(),
        target_ref=target_ref,
    )
    assert not result.is_valid
    assert any("less than min_count 1" in error for error in result.errors)


@pytest.mark.parametrize("forgery", ["canonical", "role", "scope"])
def test_service_rejects_forged_resolved_ref_metadata(forgery: str) -> None:
    """Resolved wrappers must preserve canonical ref, role, and scope evidence."""
    target_ref = _make_dummy_refset().refs[0]
    input_ref = SelectableRef(
        ref_id="input:w_main:field",
        ref_kind="worker_input",
        ref_role="selectable_input",
        canonical_name="field",
        display_label="field",
        worker_id="w_main",
    )
    refset = SelectableRefSet(
        set_id="set_1",
        issue_id="issue_1",
        snapshot_id="snap_1",
        worker_scope="w_main",
        refs=(target_ref, input_ref),
        policy_id="required_output.producer.selectable_refs.v1",
    )
    resolved_ref = input_ref
    resolved_role = "selectable_input"
    scope_matched = True
    if forgery == "canonical":
        resolved_ref = SelectableRef(
            ref_id=input_ref.ref_id,
            ref_kind="required_output",
            ref_role="target_output",
            canonical_name="forged",
            display_label="forged",
            worker_id="w_main",
        )
    elif forgery == "role":
        resolved_role = "target_output"
    else:
        scope_matched = False

    plan = _make_dummy_plan()
    registry = MaterializationPlanRegistry()
    registry.register(plan, DummyMaterializer())
    intent = ConstructRepairIntent(
        intent_id="intent_1",
        issue_id="issue_1",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="worker:w_main.output:draft",
        target_slot_name="producer",
        target_ref_id=target_ref.ref_id,
        selected_ref_ids=(input_ref.ref_id,),
        materialization_plan_id=plan.materialization_plan_id,
    )
    request = MaterializationRequest(
        snapshot=_make_dummy_snapshot(),
        issue=EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=("d1",),
            issue_group_id=None,
            kind="missing_output_producer",
            target_ref="worker:w_main.output:draft",
            irs_ref=None,
            missing_slot="producer",
            source_span_ids=(),
            message="Missing producer",
        ),
        target=RepairTarget(
            target_ref="worker:w_main.output:draft",
            target_kind="REQUIRED_OUTPUT",
            irs_ref=None,
            affordance_id="required_output.insert_or_bind_producer",
            construct_path=(),
            worker_id="w_main",
            canonical_name="draft",
            editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        ),
        catalog_entry=_make_dummy_catalog_entry(),
        intent=intent,
        refset=refset,
        resolved_refs=(
            ResolvedSelectableRef(
                ref=resolved_ref,
                resolved_role=resolved_role,
                scope_matched=scope_matched,
            ),
        ),
        evidence_packet=RepairEvidencePacket(
            evidence_packet_id="packet_1",
            confirmed_intent_id="intent_1",
            repair_patch_id="patch_1",
            related_diagnostic_id="d1",
            user_text="fix",
            confirmed_selected_ref_ids=(input_ref.ref_id,),
        ),
    )

    with pytest.raises(MaterializationConsistencyError):
        RepairMaterializationService(registry).materialize(request)
