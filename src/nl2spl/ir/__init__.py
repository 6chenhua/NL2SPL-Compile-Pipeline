"""IR data models for NL2SPL pipeline."""

from nl2spl.ir.action_placement_ir import (
    ExecutableActionCandidate,
    ExecutableActionPlacement,
    ExecutableActionPlacementPlan,
)
from nl2spl.ir.agent_profile_ir import AgentProfileIR, Aspect, Concept, PersonaIR
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.composite_output_plan_ir import (
    CompositeFieldMapping,
    CompositeOutputPlan,
    DeclarationRewrite,
    FieldProjectionRelation,
    OutputIntent,
    ReferenceRewrite,
    WorkerOutputRewrite,
)
from nl2spl.ir.condition_variable_reference_ir import (
    ConditionTextRewrite,
    ConditionVariableReferenceIR,
    ConditionVariableReferencePlan,
)
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.control_region_ir import ControlRegion, ControlRegionPlan
from nl2spl.ir.diagnostics import CompileDiagnostic, StepRenderInfo, TraceRecord
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation, StructuralPrior
from nl2spl.ir.flow_structure_ir import DelegationCandidate, FlowStructureIR
from nl2spl.ir.resource_contract_ir import (
    ContractDirection,
    ContractRequiredness,
    ResourceContractBindingIR,
    ResourceContractDemandIR,
    ResourceContractFieldIR,
    ResourceContractPlanIR,
    ResourceKind,
    ResourceScopeKind,
)
from nl2spl.ir.resource_registry_ir import (
    APIFunction,
    APIParameterSpec,
    APIReturnSpec,
    APISpec,
    FileSpec,
    ResourceRegistryIR,
    TypeSpec,
    VariableSpec,
    WorkerScopedResourceIR,
)
from nl2spl.ir.span_ir import AmbiguityInfo, SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.step_variable_relation_ir import (
    RequiredOutputFulfillmentState,
    StepVariableRelation,
    StepVariableRelationPlan,
)
from nl2spl.ir.structured_text_ir import StructuredTextFormat, StructuredTextIR
from nl2spl.ir.symbol_table import SymbolTable, VariableSymbol
from nl2spl.ir.worker_ir import FlowRef, WorkerIR
from nl2spl.ir.worker_plan_ir import (
    BoundaryKind,
    CandidateTaskUnitIR,
    ContractFieldIR,
    ControlComplexityRegionIR,
    HandoffContractIR,
    HandoffFailurePolicyIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    Risk,
    Signal,
    WorkerBlockPlanIR,
    WorkerBoundaryDecisionIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerScopedFlowIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)

CompositeOutputFieldMapping = CompositeFieldMapping

__all__ = [
    "SpanIR",
    "AmbiguityInfo",
    "ExecutableActionCandidate",
    "ExecutableActionPlacement",
    "ExecutableActionPlacementPlan",
    "FieldRouteIR",
    "RouteAnnotation",
    "StructuralPrior",
    "FlowStructureIR",
    "DelegationCandidate",
    "BlockStructureIR",
    "BlockIR",
    "ConditionTextRewrite",
    "ConditionVariableReferenceIR",
    "ConditionVariableReferencePlan",
    "AgentProfileIR",
    "PersonaIR",
    "Aspect",
    "Concept",
    "CompileDiagnostic",
    "ControlRegion",
    "ControlRegionPlan",
    "CompositeOutputFieldMapping",
    "CompositeFieldMapping",
    "CompositeOutputPlan",
    "FieldProjectionRelation",
    "OutputIntent",
    "DeclarationRewrite",
    "ReferenceRewrite",
    "WorkerOutputRewrite",
    "StepRenderInfo",
    "TraceRecord",
    "ConstraintIR",
    "ResourceContractDemandIR",
    "ResourceContractPlanIR",
    "ResourceContractFieldIR",
    "ResourceContractBindingIR",
    "ResourceKind",
    "ResourceScopeKind",
    "ContractDirection",
    "ContractRequiredness",
    "RequiredOutputFulfillmentState",
    "ResourceRegistryIR",
    "VariableSpec",
    "FileSpec",
    "APISpec",
    "APIFunction",
    "APIParameterSpec",
    "APIReturnSpec",
    "TypeSpec",
    "WorkerScopedResourceIR",
    "SymbolTable",
    "VariableSymbol",
    "StepVariableRelation",
    "StepVariableRelationPlan",
    "StepIR",
    "WorkerIR",
    "FlowRef",
    "BoundaryKind",
    "Signal",
    "Risk",
    "ContractFieldIR",
    "CandidateTaskUnitIR",
    "ControlComplexityRegionIR",
    "HandoffContractIR",
    "WorkerBoundaryDecisionIR",
    "WorkerSpecIR",
    "InputBindingIR",
    "OutputBindingIR",
    "InvokeLocationHintIR",
    "HandoffFailurePolicyIR",
    "WorkerHandoffIR",
    "WorkerPlanIR",
    "WorkerScopedFlowIR",
    "WorkerFlowPlanIR",
    "WorkerBlockPlanIR",
    "WorkerStepPlanIR",
    "StructuredTextIR",
    "StructuredTextFormat",
]
