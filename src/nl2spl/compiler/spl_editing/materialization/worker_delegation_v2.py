"""Compatibility facade for the stage-owned Worker Delegation v2 closure."""

from __future__ import annotations

from importlib import import_module

_PLAN_ID = "worker_delegation.complete_closure.v2"
_AUTHORITY = (
    "stage3_5.worker_boundary + stage4.worker_flow_plan + "
    "stage5.worker_block_plan + stage7.worker_step_plan"
)


class DefineChildWorkerClosureMaterializer:
    def __init__(self) -> None:
        module = import_module("nl2spl.compiler.spl_editing.stage_slices.worker_delegation_v2")
        self._delegate = module.DefineChildWorkerClosureMaterializer()
        self.stage_slice_registry = self._delegate.stage_slice_registry
        self.required_stage_slice_ids = self._delegate.required_stage_slice_ids

    @property
    def materializer_id(self) -> str:
        return _PLAN_ID

    @property
    def stage_authority(self) -> str:
        return _AUTHORITY

    def materialize(self, input_data):
        return self._delegate.materialize(input_data)


__all__ = ["DefineChildWorkerClosureMaterializer"]
