"""ResourceRegistryIR - Variables, Files, APIs, Types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from nl2spl.ir.structured_text_ir import StructuredTextIR

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
class APIParameterSpec:
    """Parameter specification for an API function."""

    name: str
    data_type: str
    required: bool
    description: str = ""


@dataclass
class APIReturnSpec:
    """Return specification for an API function."""

    data_type: str
    controlled_output: bool
    description: str = ""


@dataclass
class APIFunction:
    """API function specification.

    Attributes:
        name: Function name
        description: Function description
        parameters: Legacy function parameters
        return_type: Legacy return type
    """

    name: str
    description: str
    parameters: list[dict[str, str]] = field(default_factory=list)
    return_type: str = "text"

    function_id: str = ""
    url: str = ""
    parameter_specs: list[APIParameterSpec] = field(default_factory=list)
    controlled_input: bool = False
    return_spec: APIReturnSpec | None = None
    source_span_ids: list[str] = field(default_factory=list)


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

    api_id: str = ""
    retry_count: int | None = None
    log_exceptions: list[str] = field(default_factory=list)
    openapi_schema: StructuredTextIR = field(
        default_factory=lambda: StructuredTextIR("empty_placeholder", "{}")
    )

    source_span_ids: list[str] = field(default_factory=list)
    source_annotation_ids: list[str] = field(default_factory=list)
    declaration_demand_ids: list[str] = field(default_factory=list)
    used_by_worker_ids: list[str] = field(default_factory=list)
    origin: Literal[
        "source_backed",
        "adapter_hard_fact",
        "configured_resource",
        "user_confirmed_repair",
    ] = "source_backed"

    declaration_status: Literal[
        "grammar_minimal_partial",
        "partial_blocked",
        "complete",
    ] = "partial_blocked"
    name_status: Literal[
        "explicit_source_name",
        "normalized_explicit_name",
        "inferred_from_source",
        "user_confirmed",
    ] = "explicit_source_name"
    auth_status: Literal[
        "source_backed",
        "configured",
        "compiler_default_none",
        "unresolved",
    ] = "compiler_default_none"
    auth_evidence_authority: str | None = None
    auth_source_span_ids: list[str] = field(default_factory=list)
    schema_status: Literal[
        "known_present",
        "known_empty",
        "unknown_placeholder",
    ] = "unknown_placeholder"
    functions_status: Literal[
        "known_present",
        "known_empty",
        "unknown_placeholder",
    ] = "unknown_placeholder"
    partial_reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize default api_id if empty."""
        if not self.api_id and self.api_name:
            self.api_id = f"api:{self.api_name}"


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
    handoff_contracts: dict[str, HandoffContractIR] = field(default_factory=dict)
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
