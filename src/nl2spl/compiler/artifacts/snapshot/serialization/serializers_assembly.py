"""Serializers for WorkerIR and its nested types.

BlockIR and StepIR serializers are imported lazily from serializers_plan
to avoid circular imports at module-load time.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.artifacts.snapshot.serialization.protocol import (
    ArtifactSerializer,
)
from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    SerializerRegistry,
)
from nl2spl.ir.worker_ir import (
    AlternativeFlowRef,
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerInput,
    WorkerIR,
    WorkerOutput,
)


def _block_serializer() -> ArtifactSerializer:
    from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
        BlockIRSerializer,
    )

    return BlockIRSerializer()


def _step_serializer() -> ArtifactSerializer:
    from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
        StepIRSerializer,
    )

    return StepIRSerializer()


# ===================================================================
# Leaf types
# ===================================================================


class WorkerInputSerializer(ArtifactSerializer):
    type_id = "WorkerInput"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        i: WorkerInput = obj
        return {
            "$type": self.type_id,
            "name": i.name,
            "required": i.required,
            "requiredness": i.requiredness,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return WorkerInput(
            name=data["name"],
            required=data.get("required"),
            requiredness=data.get("requiredness", "unspecified"),
        )


class WorkerOutputSerializer(ArtifactSerializer):
    type_id = "WorkerOutput"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        o: WorkerOutput = obj
        return {
            "$type": self.type_id,
            "name": o.name,
            "required": o.required,
            "requiredness": o.requiredness,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return WorkerOutput(
            name=data["name"],
            required=data.get("required"),
            requiredness=data.get("requiredness", "unspecified"),
        )


class FlowRefSerializer(ArtifactSerializer):
    type_id = "FlowRef"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        f: FlowRef = obj
        blk_ser = _block_serializer()
        return {
            "$type": self.type_id,
            "blocks": [blk_ser.to_canonical(b) for b in f.blocks],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        blk_ser = _block_serializer()
        return FlowRef(
            blocks=[blk_ser.from_canonical(b) for b in data.get("blocks", [])],
        )


class AlternativeFlowRefSerializer(ArtifactSerializer):
    type_id = "AlternativeFlowRef"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        f: AlternativeFlowRef = obj
        blk_ser = _block_serializer()
        return {
            "$type": self.type_id,
            "flow_id": f.flow_id,
            "condition_text": f.condition_text,
            "blocks": [blk_ser.to_canonical(b) for b in f.blocks],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        blk_ser = _block_serializer()
        return AlternativeFlowRef(
            flow_id=data["flow_id"],
            condition_text=data["condition_text"],
            blocks=[blk_ser.from_canonical(b) for b in data.get("blocks", [])],
        )


class ExceptionFlowRefSerializer(ArtifactSerializer):
    type_id = "ExceptionFlowRef"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        f: ExceptionFlowRef = obj
        blk_ser = _block_serializer()
        return {
            "$type": self.type_id,
            "flow_id": f.flow_id,
            "condition_text": f.condition_text,
            "blocks": [blk_ser.to_canonical(b) for b in f.blocks],
            "spans": f.spans,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        blk_ser = _block_serializer()
        return ExceptionFlowRef(
            flow_id=data["flow_id"],
            condition_text=data["condition_text"],
            blocks=[blk_ser.from_canonical(b) for b in data.get("blocks", [])],
            spans=data.get("spans", []),
        )


# ===================================================================
# ChildWorkerIR
# ===================================================================


class ChildWorkerIRSerializer(ArtifactSerializer):
    type_id = "ChildWorkerIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        c: ChildWorkerIR = obj
        inp_ser = WorkerInputSerializer()
        out_ser = WorkerOutputSerializer()
        flow_ser = FlowRefSerializer()
        alt_ser = AlternativeFlowRefSerializer()
        exc_ser = ExceptionFlowRefSerializer()
        step_ser = _step_serializer()
        return {
            "$type": self.type_id,
            "worker_name": c.worker_name,
            "description": c.description,
            "task_text": c.task_text,
            "inputs": [inp_ser.to_canonical(i) for i in c.inputs],
            "outputs": [out_ser.to_canonical(o) for o in c.outputs],
            "main_flow": flow_ser.to_canonical(c.main_flow),
            "alternative_flows": [alt_ser.to_canonical(f) for f in c.alternative_flows],
            "exception_flows": [exc_ser.to_canonical(f) for f in c.exception_flows],
            "api_refs": c.api_refs,
            "steps": [step_ser.to_canonical(s) for s in c.steps],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        inp_ser = WorkerInputSerializer()
        out_ser = WorkerOutputSerializer()
        flow_ser = FlowRefSerializer()
        alt_ser = AlternativeFlowRefSerializer()
        exc_ser = ExceptionFlowRefSerializer()
        step_ser = _step_serializer()
        return ChildWorkerIR(
            worker_name=data["worker_name"],
            description=data["description"],
            task_text=data["task_text"],
            inputs=[inp_ser.from_canonical(i) for i in data.get("inputs", [])],
            outputs=[out_ser.from_canonical(o) for o in data.get("outputs", [])],
            main_flow=flow_ser.from_canonical(data["main_flow"]),
            alternative_flows=[
                alt_ser.from_canonical(f) for f in data.get("alternative_flows", [])
            ],
            exception_flows=[
                exc_ser.from_canonical(f) for f in data.get("exception_flows", [])
            ],
            api_refs=data.get("api_refs", []),
            steps=[step_ser.from_canonical(s) for s in data.get("steps", [])],
        )


# ===================================================================
# WorkerIR
# ===================================================================


class WorkerIRSerializer(ArtifactSerializer):
    type_id = "WorkerIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        w: WorkerIR = obj
        inp_ser = WorkerInputSerializer()
        out_ser = WorkerOutputSerializer()
        flow_ser = FlowRefSerializer()
        alt_ser = AlternativeFlowRefSerializer()
        exc_ser = ExceptionFlowRefSerializer()
        step_ser = _step_serializer()
        child_ser = ChildWorkerIRSerializer()
        return {
            "$type": self.type_id,
            "worker_name": w.worker_name,
            "description": w.description,
            "inputs": [inp_ser.to_canonical(i) for i in w.inputs],
            "outputs": [out_ser.to_canonical(o) for o in w.outputs],
            "main_flow": flow_ser.to_canonical(w.main_flow),
            "alternative_flows": [alt_ser.to_canonical(f) for f in w.alternative_flows],
            "exception_flows": [exc_ser.to_canonical(f) for f in w.exception_flows],
            "api_refs": w.api_refs,
            "steps": [step_ser.to_canonical(s) for s in w.steps],
            "scoped_steps": w.scoped_steps,
            "child_worker_refs": w.child_worker_refs,
            "child_workers": [child_ser.to_canonical(c) for c in w.child_workers],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        inp_ser = WorkerInputSerializer()
        out_ser = WorkerOutputSerializer()
        flow_ser = FlowRefSerializer()
        alt_ser = AlternativeFlowRefSerializer()
        exc_ser = ExceptionFlowRefSerializer()
        step_ser = _step_serializer()
        child_ser = ChildWorkerIRSerializer()
        return WorkerIR(
            worker_name=data["worker_name"],
            description=data["description"],
            inputs=[inp_ser.from_canonical(i) for i in data.get("inputs", [])],
            outputs=[out_ser.from_canonical(o) for o in data.get("outputs", [])],
            main_flow=flow_ser.from_canonical(data["main_flow"]),
            alternative_flows=[
                alt_ser.from_canonical(f) for f in data.get("alternative_flows", [])
            ],
            exception_flows=[
                exc_ser.from_canonical(f) for f in data.get("exception_flows", [])
            ],
            api_refs=data.get("api_refs", []),
            steps=[step_ser.from_canonical(s) for s in data.get("steps", [])],
            scoped_steps=data.get("scoped_steps", False),
            child_worker_refs=data.get("child_worker_refs", []),
            child_workers=[child_ser.from_canonical(c) for c in data.get("child_workers", [])],
        )


# ===================================================================
# Registration
# ===================================================================


def register_all(registry: SerializerRegistry) -> None:
    _reg = registry.register
    _cls = registry.register_for_class

    serializers = [
        WorkerInputSerializer(),
        WorkerOutputSerializer(),
        FlowRefSerializer(),
        AlternativeFlowRefSerializer(),
        ExceptionFlowRefSerializer(),
        ChildWorkerIRSerializer(),
        WorkerIRSerializer(),
    ]
    for s in serializers:
        _reg(s)
    _cls(WorkerInput, serializers[0])
    _cls(WorkerOutput, serializers[1])
    _cls(FlowRef, serializers[2])
    _cls(AlternativeFlowRef, serializers[3])
    _cls(ExceptionFlowRef, serializers[4])
    _cls(ChildWorkerIR, serializers[5])
    _cls(WorkerIR, serializers[6])
