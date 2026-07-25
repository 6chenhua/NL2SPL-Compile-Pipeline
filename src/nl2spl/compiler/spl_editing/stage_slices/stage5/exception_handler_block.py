"""Stage 5 repair slice for exception handler block ensure/materialization."""

from __future__ import annotations

from dataclasses import replace

from nl2spl.compiler.spl_editing.stage_slices.errors import (
    StageAuthorityMismatchError,
    StageSliceValidationError,
)
from nl2spl.compiler.spl_editing.stage_slices.model import StageSliceInput
from nl2spl.compiler.spl_editing.stage_slices.result import StageSliceResult
from nl2spl.compiler.spl_editing.stage_slices.typed_plan import BlockShapePlan
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR

_SLICE_ID = "stage5.exception_handler_block_repair.v1"
_STAGE_AUTHORITY = "stage5.worker_block_plan"
_POLICY_ID = "exception_handler.minimal_block.v1"
_ALLOWED_BLOCK_TYPES = {"SEQUENTIAL", "IF", "FOR", "WHILE"}
_FORBIDDEN_FACT_SOURCE = ("diagnostic", "message")


class Stage5ExceptionHandlerBlockRepairSlice:
    """Ensure or materialize the handler block for an exception flow."""

    @property
    def slice_id(self) -> str:
        return _SLICE_ID

    @property
    def stage_authority(self) -> str:
        return _STAGE_AUTHORITY

    @property
    def policy_id(self) -> str:
        return _POLICY_ID

    @property
    def output_artifacts(self) -> tuple[str, ...]:
        return ("WorkerBlockPlanIR",)

    @property
    def write_layers(self) -> tuple[str, ...]:
        return ("worker_block_plan_pre_normalize",)

    def execute(self, input_data: StageSliceInput) -> StageSliceResult:
        """Ensure a handler block exists without generating any command step."""
        if input_data.stage_authority != self.stage_authority:
            raise StageAuthorityMismatchError(
                f"Stage5 handler block slice requires authority '{self.stage_authority}'."
            )
        if input_data.slice_id != self.slice_id:
            raise StageSliceValidationError(
                f"StageSliceInput slice_id '{input_data.slice_id}' does not match '{self.slice_id}'."
            )
        self._reject_forbidden_fact_sources(input_data)

        target = input_data.target
        if target.irs_ref.construct_type != "EXCEPTION_FLOW":
            raise StageSliceValidationError("Stage5 handler block target must be EXCEPTION_FLOW.")
        if target.irs_ref.slot_name != "handler_action":
            raise StageSliceValidationError("Stage5 handler block target slot must be handler_action.")
        worker_id = target.worker_id or ""
        flow_id = target.canonical_name or ""
        if not worker_id:
            raise StageSliceValidationError("RepairTarget.worker_id is required.")
        if not flow_id:
            raise StageSliceValidationError("RepairTarget.canonical_name is required.")

        snapshot = input_data.snapshot
        block_plan = snapshot.worker_block_plan
        flow_plan = snapshot.worker_flow_plan
        if block_plan is None:
            raise StageSliceValidationError("worker_block_plan is required.")
        if flow_plan is None:
            raise StageSliceValidationError("worker_flow_plan is required.")
        worker_flow = flow_plan.worker_flows.get(worker_id)
        if worker_flow is None or not any(
            getattr(exc, "flow_id", None) == flow_id
            for exc in getattr(worker_flow, "exception_flows", [])
        ):
            raise StageSliceValidationError(
                f"Exception flow '{flow_id}' not found in worker '{worker_id}'."
            )

        block_structure = block_plan.worker_blocks.get(worker_id)
        current_blocks = ()
        if block_structure is not None:
            current_blocks = tuple(block_structure.exception_flow_blocks.get(flow_id, ()))
        if current_blocks:
            existing = current_blocks[0]
            return StageSliceResult(
                slice_id=self.slice_id,
                stage_authority=self.stage_authority,
                policy_id=input_data.stage_policy.policy_id,
                changed_artifact_refs=(),
                generated_construct_refs=(f"block:{worker_id}:{existing.block_id}",),
                consumed_selected_ref_ids=(),
                consumed_directive_id=input_data.directive.directive_id,
                allocated_ids=(),
                trace={
                    "action": "bind_existing",
                    "worker_id": worker_id,
                    "flow_id": flow_id,
                    "block_id": existing.block_id,
                    "block_type": existing.block_type,
                },
            )

        if input_data.id_allocator is None:
            raise StageSliceValidationError("Stage5 handler block slice requires id_allocator.")
        block_shape = self._resolve_block_shape(input_data.typed_plan)
        block_id = input_data.id_allocator.allocate_block_id(worker_id)
        new_block = BlockIR(block_id=block_id, block_type=block_shape.block_type, spans=[])

        worker_blocks: dict[str, BlockStructureIR] = {}
        for wid, structure in block_plan.worker_blocks.items():
            exception_blocks = {
                fid: list(blocks)
                for fid, blocks in structure.exception_flow_blocks.items()
            }
            worker_blocks[wid] = replace(structure, exception_flow_blocks=exception_blocks)
        if worker_id not in worker_blocks:
            worker_blocks[worker_id] = BlockStructureIR()
        current_structure = worker_blocks[worker_id]
        exception_blocks = {
            fid: list(blocks)
            for fid, blocks in current_structure.exception_flow_blocks.items()
        }
        exception_blocks[flow_id] = [new_block]
        new_structure = replace(current_structure, exception_flow_blocks=exception_blocks)
        worker_blocks[worker_id] = new_structure
        updated_block_plan = replace(block_plan, worker_blocks=worker_blocks)

        return StageSliceResult(
            slice_id=self.slice_id,
            stage_authority=self.stage_authority,
            policy_id=input_data.stage_policy.policy_id,
            changed_artifact_refs=("worker_block_plan",),
            generated_construct_refs=(f"block:{worker_id}:{block_id}",),
            consumed_selected_ref_ids=(),
            consumed_directive_id=input_data.directive.directive_id,
            allocated_ids=(block_id,),
            trace={
                "action": "materialize",
                "worker_id": worker_id,
                "flow_id": flow_id,
                "block_id": block_id,
                "block_type": new_block.block_type,
            },
            artifact_updates={"worker_block_plan": updated_block_plan},
        )

    def _resolve_block_shape(self, typed_plan) -> BlockShapePlan:
        if typed_plan is None:
            return BlockShapePlan(block_type="SEQUENTIAL", child_action_slots=("handler_action",))
        if not isinstance(typed_plan, BlockShapePlan):
            raise StageSliceValidationError("Stage5 handler block typed_plan must be BlockShapePlan.")
        if typed_plan.block_type not in _ALLOWED_BLOCK_TYPES:
            raise StageSliceValidationError(
                f"Unsupported handler block_type '{typed_plan.block_type}'."
            )
        return typed_plan

    def _reject_forbidden_fact_sources(self, input_data: StageSliceInput) -> None:
        needle = ".".join(_FORBIDDEN_FACT_SOURCE)
        values = [
            input_data.directive.requested_behavior or "",
            *input_data.directive.constraints,
        ]
        if any(needle in value.casefold() for value in values):
            raise StageSliceValidationError(
                "Stage5 handler block facts must come from structured target facts, not diagnostic metadata."
            )
