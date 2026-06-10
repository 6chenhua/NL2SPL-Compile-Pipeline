"""ResourceRegistryIR - Variables, Files, APIs, Types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nl2spl.ir.worker_plan_ir import HandoffContractIR


@dataclass
class VariableSpec:
    """Variable specification.

    Attributes:
        name: Variable name (snake_case)
        data_type: Data type
        required: Whether variable is required
        description: Variable description
        source: Variable source (input/output/step/api/file)
    """

    name: str
    data_type: str
    required: bool
    description: str
    source: str


@dataclass
class FileSpec:
    """File specification.

    Attributes:
        name: File name
        path: File path
        data_type: Data type
        description: File description
    """

    name: str
    path: str
    data_type: str
    description: str


@dataclass
class APIFunction:
    """API function specification.

    Attributes:
        name: Function name
        description: Function description
        parameters: Function parameters
        return_type: Return type
    """

    name: str
    description: str
    parameters: list[dict[str, str]] = field(default_factory=list)
    return_type: str = "text"


@dataclass
class APISpec:
    """API specification.

    Attributes:
        api_name: API name
        auth: Authentication type
        description: API description
        functions: API functions
    """

    api_name: str
    auth: str
    description: str
    functions: list[APIFunction] = field(default_factory=list)


@dataclass
class TypeSpec:
    """Type specification.

    Attributes:
        type_name: Type name
        type_kind: Type kind (structured/enum)
        definition: Type definition
    """

    type_name: str
    type_kind: str
    definition: str


@dataclass
class ResourceRegistryIR:
    """Resource registry information.

    Attributes:
        variables: Variable specifications
        files: File specifications
        apis: API specifications
        types: Type specifications
    """

    variables: list[VariableSpec] = field(default_factory=list)
    files: list[FileSpec] = field(default_factory=list)
    apis: list[APISpec] = field(default_factory=list)
    types: list[TypeSpec] = field(default_factory=list)

    def get_variable_names(self) -> set[str]:
        """Get all variable names."""
        return {v.name for v in self.variables}

    def get_api_names(self) -> set[str]:
        """Get all API names."""
        return {a.api_name for a in self.apis}


@dataclass
class WorkerScopedResourceIR:
    """Worker-scoped resource extraction result.

    Stores resources grouped by worker scope:
    - global_resources: Resources shared across all workers
    - worker_resources: Resources specific to each worker
    - handoff_contracts: Contracts between workers for handoffs

    Attributes:
        global_resources: Global resource registry
        worker_resources: Resource registry per worker ID
        handoff_contracts: Handoff contract per handoff ID
    """

    global_resources: ResourceRegistryIR = field(default_factory=ResourceRegistryIR)
    worker_resources: dict[str, ResourceRegistryIR] = field(default_factory=dict)
    handoff_contracts: dict[str, "HandoffContractIR"] = field(default_factory=dict)
    resource_contract_bindings: list[Any] = field(default_factory=list)

    def get_all_variables(self) -> list[VariableSpec]:
        """Get all variables across all scopes.

        Returns:
            List of all variable specifications
        """
        result = list(self.global_resources.variables)
        for worker_resources in self.worker_resources.values():
            result.extend(worker_resources.variables)
        return result

    def get_all_apis(self) -> list[APISpec]:
        """Get all APIs across all scopes.

        Returns:
            List of all API specifications
        """
        result = list(self.global_resources.apis)
        for worker_resources in self.worker_resources.values():
            result.extend(worker_resources.apis)
        return result
