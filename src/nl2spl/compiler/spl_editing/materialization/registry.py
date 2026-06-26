"""Materialization plan registry."""

from __future__ import annotations

from typing import Protocol

from nl2spl.compiler.spl_editing.materialization.errors import (
    DuplicateMaterializationPlanError,
    MaterializationConsistencyError,
    MaterializationPlanNotFoundError,
)
from nl2spl.compiler.spl_editing.materialization.model import (
    MaterializationInput,
    MaterializationPlan,
    MaterializationResult,
)


class Materializer(Protocol):
    """Protocol defining target materializers for specific plans."""

    @property
    def materializer_id(self) -> str:
        """Globally unique identifier for the materializer."""
        ...

    @property
    def stage_authority(self) -> str:
        """Compiler stage authority represented by this materializer."""
        ...

    def materialize(self, input_data: MaterializationInput) -> MaterializationResult:
        """Execute the materialization logic on the given input."""
        ...


class MaterializationPlanRegistry:
    """Registry holding materialization plans and registered materializers."""

    def __init__(self) -> None:
        self._plans: dict[str, MaterializationPlan] = {}
        self._materializers: dict[str, Materializer] = {}
        self._materializer_authorities: dict[str, str] = {}

    def register(self, plan: MaterializationPlan, materializer: Materializer) -> None:
        """Register a materialization plan and its matching materializer."""
        if plan.materialization_plan_id in self._plans:
            raise DuplicateMaterializationPlanError(
                f"Plan ID '{plan.materialization_plan_id}' is already registered."
            )

        if materializer.materializer_id != plan.materializer_id:
            raise MaterializationConsistencyError(
                f"Materializer ID mismatch: expected '{plan.materializer_id}', got '{materializer.materializer_id}'."  # noqa: E501
            )

        if materializer.stage_authority != plan.stage_authority:
            raise MaterializationConsistencyError(
                f"Materializer stage authority mismatch: expected '{plan.stage_authority}', got '{materializer.stage_authority}'."  # noqa: E501
            )

        # Enforce unique 1:1 mapping between materializer_id and stage_authority
        if materializer.materializer_id in self._materializer_authorities:
            existing_auth = self._materializer_authorities[materializer.materializer_id]
            if existing_auth != plan.stage_authority:
                raise MaterializationConsistencyError(
                    f"Materializer '{materializer.materializer_id}' is already registered under stage authority "  # noqa: E501
                    f"'{existing_auth}', cannot register under different authority '{plan.stage_authority}'."  # noqa: E501
                )
        else:
            self._materializer_authorities[materializer.materializer_id] = plan.stage_authority

        self._plans[plan.materialization_plan_id] = plan
        self._materializers[plan.materialization_plan_id] = materializer

    def get(self, plan_id: str) -> MaterializationPlan:
        """Get the registered materialization plan by ID."""
        if plan_id not in self._plans:
            raise MaterializationPlanNotFoundError(f"Plan ID '{plan_id}' is not registered.")
        return self._plans[plan_id]

    def get_materializer(self, plan_id: str) -> Materializer:
        """Get the registered materializer for the given plan ID."""
        if plan_id not in self._materializers:
            raise MaterializationPlanNotFoundError(
                f"No materializer registered for plan ID '{plan_id}'."
            )
        return self._materializers[plan_id]


def build_default_materialization_registry() -> MaterializationPlanRegistry:
    """Return the default registry containing all registered materialization plans."""
    from nl2spl.compiler.spl_editing.materialization.model import (
        MaterializationDependencyClosure,
        RefRoleConstraint,
        RequiredArtifactField,
    )
    from nl2spl.compiler.spl_editing.materialization.stage7 import (
        Stage7ExceptionHandlerStepMaterializer,
        Stage7ProducerRepairMaterializer,
    )
    from nl2spl.compiler.spl_editing.materialization.worker_handoff import (
        WorkerHandoffContractMaterializer,
    )

    registry = MaterializationPlanRegistry()

    # ------------------------------------------------------------------
    # stage7.step_producer_repair.v1
    # Required-output missing-producer insertion via Stage 7 authority.
    # ------------------------------------------------------------------
    plan = MaterializationPlan(
        materialization_plan_id="stage7.step_producer_repair.v1",
        patch_type="InsertProducerStep",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        stage_authority="stage7.worker_step_plan",
        dependency_closure=MaterializationDependencyClosure(
            required_artifacts=("worker_plan", "worker_block_plan", "worker_step_plan"),
            required_artifact_fields=(
                RequiredArtifactField("worker_plan", ("main_worker_id",)),
                RequiredArtifactField("worker_step_plan", ("worker_steps",)),
                RequiredArtifactField("worker_block_plan", ("worker_blocks",)),
            ),
            required_ref_role_constraints=(
                # Exactly one target_output ref scoped to target worker
                RefRoleConstraint("target_output", 1, 1, "target"),
                # Zero or more selectable_input refs scoped to target worker
                RefRoleConstraint("selectable_input", 0, None, "target"),
            ),
            worker_scope_requirement="main",
            required_id_allocator_namespaces=("step",),
        ),
        editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        output_artifacts=("WorkerStepPlanIR",),
        writes_to=("worker_step_plan_pre_normalize",),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id="stage7.step_producer_repair.v1",
    )
    registry.register(plan, Stage7ProducerRepairMaterializer())

    # ------------------------------------------------------------------
    # stage7.exception_handler_step_repair.v1
    # Exception-flow missing-handler insertion via Stage 7 authority.
    # ------------------------------------------------------------------
    plan = MaterializationPlan(
        materialization_plan_id="stage7.exception_handler_step_repair.v1",
        patch_type="AddExceptionHandlerStep",
        target_construct_type="EXCEPTION_FLOW",
        target_slot_name="handler_action",
        stage_authority="stage7.worker_step_plan",
        dependency_closure=MaterializationDependencyClosure(
            required_artifacts=(
                "worker_plan",
                "worker_flow_plan",
                "worker_block_plan",
                "worker_step_plan",
            ),
            required_artifact_fields=(
                RequiredArtifactField("worker_plan", ("main_worker_id",)),
                RequiredArtifactField("worker_flow_plan", ("worker_flows",)),
                RequiredArtifactField("worker_step_plan", ("worker_steps",)),
                RequiredArtifactField("worker_block_plan", ("worker_blocks",)),
            ),
            required_ref_role_constraints=(
                RefRoleConstraint("target_exception_flow", 1, 1, "target"),
                RefRoleConstraint("selectable_input", 0, None, "target"),
            ),
            worker_scope_requirement="main",
            required_id_allocator_namespaces=("step", "block"),
        ),
        editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        output_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        writes_to=("worker_step_plan_pre_normalize", "worker_block_plan_pre_normalize"),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id="stage7.exception_handler_step_repair.v1",
    )
    registry.register(plan, Stage7ExceptionHandlerStepMaterializer())

    # ------------------------------------------------------------------
    # worker_handoff.contract_repair.v1
    # Worker promotion contract materialization across worker plan + invoke step.
    # ------------------------------------------------------------------
    plan = MaterializationPlan(
        materialization_plan_id="worker_handoff.contract_repair.v1",
        patch_type="CreateWorkerHandoffContract",
        target_construct_type="WORKER_PROMOTION",
        target_slot_name="promotion_input_contract",
        stage_authority="stage3_5.worker_boundary + stage7.worker_step_plan",
        dependency_closure=MaterializationDependencyClosure(
            required_artifacts=("worker_plan", "worker_step_plan"),
            required_artifact_fields=(
                RequiredArtifactField("worker_plan", ("main_worker_id",)),
                RequiredArtifactField("worker_plan", ("workers",)),
                RequiredArtifactField("worker_step_plan", ("worker_steps",)),
            ),
            required_ref_role_constraints=(
                RefRoleConstraint("target_worker", 1, 1, "target"),
                RefRoleConstraint("selectable_input", 0, None, "target"),
            ),
            worker_scope_requirement="main",
            required_id_allocator_namespaces=("step", "handoff"),
        ),
        editable_artifacts=("WorkerPlanIR", "WorkerHandoffIR", "WorkerStepPlanIR"),
        output_artifacts=("WorkerPlanIR", "WorkerStepPlanIR"),
        writes_to=("worker_plan_pre_normalize", "worker_step_plan_pre_normalize"),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id="worker_handoff.contract_repair.v1",
    )
    registry.register(plan, WorkerHandoffContractMaterializer())

    return registry
