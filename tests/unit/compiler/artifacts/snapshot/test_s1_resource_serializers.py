"""S1 resource serializer round-trip tests."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    build_default_registry,
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
from nl2spl.ir.worker_plan_ir import ContractFieldIR, HandoffContractIR


def _rt(registry, obj):
    data = registry.serialize(obj)
    restored = registry.deserialize(data)
    return data, restored


class TestVariableSpecRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        v = VariableSpec(name="draft", data_type="text", required=True,
                         description="Draft content", source="input")
        data, restored = _rt(reg, v)
        assert data["$type"] == "VariableSpec"
        assert restored.name == "draft"
        assert restored.data_type == "text"
        assert restored.required is True


class TestFileSpecRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        f = FileSpec(name="template", path="/templates/email.txt",
                     data_type="text", description="Email template")
        data, restored = _rt(reg, f)
        assert data["$type"] == "FileSpec"
        assert restored.path == "/templates/email.txt"


class TestAPIFunctionRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        f = APIFunction(
            name="send_email",
            description="Send an email",
            parameters=[{"name": "to", "type": "string"}],
            return_type="json",
        )
        data, restored = _rt(reg, f)
        assert data["$type"] == "APIFunction"
        assert len(restored.parameters) == 1
        assert restored.parameters[0]["name"] == "to"


class TestAPISpecRoundTrip:
    def test_with_functions(self) -> None:
        reg = build_default_registry()
        api = APISpec(
            api_name="EmailAPI",
            auth="api_key",
            description="Email sending API",
            functions=[APIFunction(name="send", description="Send", return_type="text")],
        )
        data, restored = _rt(reg, api)
        assert data["$type"] == "APISpec"
        assert len(restored.functions) == 1
        assert isinstance(restored.functions[0], APIFunction)


class TestTypeSpecRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        t = TypeSpec(type_name="Status", type_kind="enum", definition="DRAFT | SENT | ARCHIVED")
        data, restored = _rt(reg, t)
        assert data["$type"] == "TypeSpec"
        assert restored.type_kind == "enum"


class TestResourceRegistryIRRoundTrip:
    def test_full_roundtrip(self) -> None:
        reg = build_default_registry()
        r = ResourceRegistryIR(
            variables=[VariableSpec(name="draft", data_type="text", required=True,
                                    description="Draft", source="input")],
            files=[FileSpec(name="tmpl", path="/t.txt", data_type="text", description="T")],
            apis=[],
            types=[TypeSpec(type_name="Color", type_kind="enum", definition="RED | GREEN")],
        )
        data, restored = _rt(reg, r)
        assert data["$type"] == "ResourceRegistryIR"
        assert len(restored.variables) == 1
        assert len(restored.types) == 1

    def test_empty_registry(self) -> None:
        reg = build_default_registry()
        r = ResourceRegistryIR()
        _data, restored = _rt(reg, r)
        assert restored.variables == []


class TestWorkerScopedResourceIRRoundTrip:
    def test_with_worker_resources(self) -> None:
        reg = build_default_registry()
        global_res = ResourceRegistryIR(
            variables=[VariableSpec(name="shared", data_type="text", required=False,
                                    description="Shared", source="input")],
        )
        worker_res = ResourceRegistryIR(
            variables=[VariableSpec(name="local", data_type="int", required=True,
                                    description="Local", source="step")],
        )
        w = WorkerScopedResourceIR(
            global_resources=global_res,
            worker_resources={"MainWorker": worker_res},
        )
        data, restored = _rt(reg, w)
        assert data["$type"] == "WorkerScopedResourceIR"
        assert isinstance(restored.global_resources, ResourceRegistryIR)
        assert "MainWorker" in restored.worker_resources
        assert isinstance(restored.worker_resources["MainWorker"], ResourceRegistryIR)
        assert len(restored.global_resources.variables) == 1
        assert restored.global_resources.variables[0].name == "shared"

    def test_with_handoff_contracts(self) -> None:
        """Non-empty handoff_contracts must round-trip without AttributeError."""
        reg = build_default_registry()
        contract = HandoffContractIR(
            handoff_id="h_001",
            parent_worker_id="MainWorker",
            child_worker_id="SubWorker",
            input_variables=[
                ContractFieldIR(name="payload", data_type="json", required=True,
                                description="Payload", source="input"),
            ],
            output_variables=[
                ContractFieldIR(name="result", data_type="json", required=True,
                                description="Result", source="output"),
            ],
        )
        w = WorkerScopedResourceIR(
            global_resources=ResourceRegistryIR(),
            handoff_contracts={"h_001": contract},
            resource_contract_bindings=["binding_1", "binding_2"],
        )
        data, restored = _rt(reg, w)
        assert data["$type"] == "WorkerScopedResourceIR"
        assert "h_001" in restored.handoff_contracts
        restored_hc = restored.handoff_contracts["h_001"]
        assert isinstance(restored_hc, HandoffContractIR)
        assert len(restored_hc.input_variables) == 1
        assert restored_hc.input_variables[0].name == "payload"
        assert len(restored_hc.output_variables) == 1
        assert restored_hc.output_variables[0].name == "result"
        # resource_contract_bindings preserved
        assert restored.resource_contract_bindings == ["binding_1", "binding_2"]

    def test_with_resource_contract_binding_ir(self) -> None:
        reg = build_default_registry()
        binding = ResourceContractBindingIR(
            contract_demand_id="rcd_output_s1",
            resource_name="draft",
            resource_kind="variable",
            direction="output",
            scope_kind="worker",
            scope_id="worker_main",
            source_span_ids=["s1"],
            source_section_id="sec_1",
            source_packet_id="pkt_1",
        )
        w = WorkerScopedResourceIR(
            global_resources=ResourceRegistryIR(),
            resource_contract_bindings=[binding],
        )

        data, restored = _rt(reg, w)

        assert data["resource_contract_bindings"][0]["$type"] == (
            "ResourceContractBindingIR"
        )
        restored_binding = restored.resource_contract_bindings[0]
        assert isinstance(restored_binding, ResourceContractBindingIR)
        assert restored_binding.contract_demand_id == "rcd_output_s1"
        assert restored_binding.resource_name == "draft"
        assert restored_binding.scope_id == "worker_main"
