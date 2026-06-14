"""Serializers for ResourceRegistryIR and WorkerScopedResourceIR."""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.artifacts.snapshot.serialization.protocol import (
    ArtifactSerializer,
)
from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    SerializerRegistry,
)
from nl2spl.ir.resource_contract_ir import ResourceContractBindingIR
from nl2spl.ir.resource_registry_ir import (
    APIFunction,
    APISpec,
    FileSpec,
    ResourceRegistryIR,
    TypeSpec,
    VariableSpec,
    WorkerScopedResourceIR,
)


class VariableSpecSerializer(ArtifactSerializer):
    type_id = "VariableSpec"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        v: VariableSpec = obj
        return {
            "$type": self.type_id,
            "name": v.name,
            "data_type": v.data_type,
            "required": v.required,
            "description": v.description,
            "source": v.source,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return VariableSpec(
            name=data["name"],
            data_type=data["data_type"],
            required=data["required"],
            description=data["description"],
            source=data["source"],
        )


class FileSpecSerializer(ArtifactSerializer):
    type_id = "FileSpec"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        f: FileSpec = obj
        return {
            "$type": self.type_id,
            "name": f.name,
            "path": f.path,
            "data_type": f.data_type,
            "description": f.description,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return FileSpec(
            name=data["name"],
            path=data["path"],
            data_type=data["data_type"],
            description=data["description"],
        )


class APIFunctionSerializer(ArtifactSerializer):
    type_id = "APIFunction"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        f: APIFunction = obj
        return {
            "$type": self.type_id,
            "name": f.name,
            "description": f.description,
            "parameters": f.parameters,
            "return_type": f.return_type,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return APIFunction(
            name=data["name"],
            description=data["description"],
            parameters=data.get("parameters", []),
            return_type=data.get("return_type", "text"),
        )


class APISpecSerializer(ArtifactSerializer):
    type_id = "APISpec"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        a: APISpec = obj
        fn_ser = APIFunctionSerializer()
        return {
            "$type": self.type_id,
            "api_name": a.api_name,
            "auth": a.auth,
            "description": a.description,
            "functions": [fn_ser.to_canonical(f) for f in a.functions],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        fn_ser = APIFunctionSerializer()
        return APISpec(
            api_name=data["api_name"],
            auth=data["auth"],
            description=data["description"],
            functions=[fn_ser.from_canonical(f) for f in data.get("functions", [])],
        )


class TypeSpecSerializer(ArtifactSerializer):
    type_id = "TypeSpec"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        t: TypeSpec = obj
        return {
            "$type": self.type_id,
            "type_name": t.type_name,
            "type_kind": t.type_kind,
            "definition": t.definition,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return TypeSpec(
            type_name=data["type_name"],
            type_kind=data["type_kind"],
            definition=data["definition"],
        )


class ResourceContractBindingIRSerializer(ArtifactSerializer):
    type_id = "ResourceContractBindingIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        b: ResourceContractBindingIR = obj
        return {
            "$type": self.type_id,
            "contract_demand_id": b.contract_demand_id,
            "resource_name": b.resource_name,
            "resource_kind": b.resource_kind,
            "direction": b.direction,
            "scope_kind": b.scope_kind,
            "scope_id": b.scope_id,
            "source_span_ids": list(b.source_span_ids),
            "source_section_id": b.source_section_id,
            "source_packet_id": b.source_packet_id,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return ResourceContractBindingIR(
            contract_demand_id=data["contract_demand_id"],
            resource_name=data["resource_name"],
            resource_kind=data["resource_kind"],
            direction=data["direction"],
            scope_kind=data["scope_kind"],
            scope_id=data.get("scope_id"),
            source_span_ids=list(data.get("source_span_ids", [])),
            source_section_id=data.get("source_section_id"),
            source_packet_id=data.get("source_packet_id"),
        )


class ResourceRegistryIRSerializer(ArtifactSerializer):
    type_id = "ResourceRegistryIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        r: ResourceRegistryIR = obj
        v_ser = VariableSpecSerializer()
        f_ser = FileSpecSerializer()
        a_ser = APISpecSerializer()
        t_ser = TypeSpecSerializer()
        return {
            "$type": self.type_id,
            "variables": [v_ser.to_canonical(v) for v in r.variables],
            "files": [f_ser.to_canonical(f) for f in r.files],
            "apis": [a_ser.to_canonical(a) for a in r.apis],
            "types": [t_ser.to_canonical(t) for t in r.types],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        v_ser = VariableSpecSerializer()
        f_ser = FileSpecSerializer()
        a_ser = APISpecSerializer()
        t_ser = TypeSpecSerializer()
        return ResourceRegistryIR(
            variables=[v_ser.from_canonical(v) for v in data.get("variables", [])],
            files=[f_ser.from_canonical(f) for f in data.get("files", [])],
            apis=[a_ser.from_canonical(a) for a in data.get("apis", [])],
            types=[t_ser.from_canonical(t) for t in data.get("types", [])],
        )


class WorkerScopedResourceIRSerializer(ArtifactSerializer):
    type_id = "WorkerScopedResourceIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        w: WorkerScopedResourceIR = obj
        reg_ser = ResourceRegistryIRSerializer()
        result: dict[str, Any] = {
            "$type": self.type_id,
            "global_resources": reg_ser.to_canonical(w.global_resources),
            "worker_resources": {
                wid: reg_ser.to_canonical(r)
                for wid, r in w.worker_resources.items()
            },
        }
        # Serialize handoff_contracts using ContractFieldIRSerializer (lazy import)
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
            ContractFieldIRSerializer,
        )

        cf_ser = ContractFieldIRSerializer()
        hc: dict[str, dict[str, Any]] = {}
        for hid, contract in w.handoff_contracts.items():
            hc[hid] = {
                "$type": "HandoffContractIR",
                "handoff_id": contract.handoff_id,
                "parent_worker_id": contract.parent_worker_id,
                "child_worker_id": contract.child_worker_id,
                "input_variables": [
                    cf_ser.to_canonical(v) for v in contract.input_variables
                ],
                "output_variables": [
                    cf_ser.to_canonical(v) for v in contract.output_variables
                ],
            }
        result["handoff_contracts"] = hc
        binding_ser = ResourceContractBindingIRSerializer()
        result["resource_contract_bindings"] = [
            (
                binding_ser.to_canonical(binding)
                if isinstance(binding, ResourceContractBindingIR)
                else binding
            )
            for binding in w.resource_contract_bindings
        ]
        return result

    def from_canonical(self, data: dict[str, Any]) -> Any:
        reg_ser = ResourceRegistryIRSerializer()
        binding_ser = ResourceContractBindingIRSerializer()
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
            ContractFieldIRSerializer,
        )

        cf_ser = ContractFieldIRSerializer()
        raw_hc = data.get("handoff_contracts", {})
        # Reconstruct HandoffContractIR objects
        from nl2spl.ir.worker_plan_ir import HandoffContractIR

        handoff_contracts: dict[str, HandoffContractIR] = {}
        for hid, hc_data in raw_hc.items():
            input_vars = [
                cf_ser.from_canonical(v) for v in hc_data.get("input_variables", [])
            ]
            output_vars = [
                cf_ser.from_canonical(v) for v in hc_data.get("output_variables", [])
            ]
            handoff_contracts[hid] = HandoffContractIR(
                handoff_id=hc_data["handoff_id"],
                parent_worker_id=hc_data["parent_worker_id"],
                child_worker_id=hc_data["child_worker_id"],
                input_variables=input_vars,
                output_variables=output_vars,
            )
        return WorkerScopedResourceIR(
            global_resources=reg_ser.from_canonical(data["global_resources"]),
            worker_resources={
                wid: reg_ser.from_canonical(r)
                for wid, r in data.get("worker_resources", {}).items()
            },
            handoff_contracts=handoff_contracts,
            resource_contract_bindings=[
                (
                    binding_ser.from_canonical(binding)
                    if (
                        isinstance(binding, dict)
                        and binding.get("$type") == binding_ser.type_id
                    )
                    else binding
                )
                for binding in data.get("resource_contract_bindings", [])
            ],
        )


def register_all(registry: SerializerRegistry) -> None:
    serializers = [
        VariableSpecSerializer(),
        FileSpecSerializer(),
        APIFunctionSerializer(),
        APISpecSerializer(),
        TypeSpecSerializer(),
        ResourceContractBindingIRSerializer(),
        ResourceRegistryIRSerializer(),
        WorkerScopedResourceIRSerializer(),
    ]
    for s in serializers:
        registry.register(s)
    registry.register_for_class(VariableSpec, serializers[0])
    registry.register_for_class(FileSpec, serializers[1])
    registry.register_for_class(APIFunction, serializers[2])
    registry.register_for_class(APISpec, serializers[3])
    registry.register_for_class(TypeSpec, serializers[4])
    registry.register_for_class(ResourceContractBindingIR, serializers[5])
    registry.register_for_class(ResourceRegistryIR, serializers[6])
    registry.register_for_class(WorkerScopedResourceIR, serializers[7])
