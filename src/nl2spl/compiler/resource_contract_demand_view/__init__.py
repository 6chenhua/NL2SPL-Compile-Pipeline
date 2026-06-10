"""ResourceContractDemandView — compiler projection utility.

Provides a pure projection from resolved Stage 2 RouteAnnotations into
source-demanded resource contract demands.  Not a pipeline stage.
"""

from __future__ import annotations

from nl2spl.compiler.resource_contract_demand_view.builder import DemandViewBuilder
from nl2spl.compiler.resource_contract_demand_view.diagnostics import (
    RESOURCE_CONTRACT_AMBIGUOUS_MULTI_DIRECTION_SPAN,
    RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_DIRECTION,
    RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_REQUIREDNESS,
    RESOURCE_CONTRACT_ANNOTATION_COVERAGE_GAP,
    RESOURCE_CONTRACT_ANNOTATION_MISSING,
    RESOURCE_CONTRACT_ANNOTATION_MISSING_DIRECTION,
    RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS,
    RESOURCE_CONTRACT_ANNOTATION_UNMATCHED_STRUCTURAL_FACT,
    RESOURCE_CONTRACT_DUPLICATE_DEMAND_ID,
    RESOURCE_CONTRACT_HEADER_FALLBACK_USED,
    RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT,
    RESOURCE_CONTRACT_MULTI_ANNOTATION_REQUIRES_SPLIT,
    severity_for_kind,
)
from nl2spl.compiler.resource_contract_demand_view.model import (
    DemandViewDemand,
    ResourceContractDemandView,
    ViewDiagnostic,
)
from nl2spl.compiler.resource_contract_demand_view.projector import (
    ViewDiagnosticProjector,
)

__all__ = [
    # builder
    "DemandViewBuilder",
    # model
    "DemandViewDemand",
    "ResourceContractDemandView",
    "ViewDiagnostic",
    # diagnostics
    "RESOURCE_CONTRACT_AMBIGUOUS_MULTI_DIRECTION_SPAN",
    "RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_DIRECTION",
    "RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_REQUIREDNESS",
    "RESOURCE_CONTRACT_ANNOTATION_COVERAGE_GAP",
    "RESOURCE_CONTRACT_ANNOTATION_MISSING",
    "RESOURCE_CONTRACT_ANNOTATION_MISSING_DIRECTION",
    "RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS",
    "RESOURCE_CONTRACT_ANNOTATION_UNMATCHED_STRUCTURAL_FACT",
    "RESOURCE_CONTRACT_DUPLICATE_DEMAND_ID",
    "RESOURCE_CONTRACT_HEADER_FALLBACK_USED",
    "RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT",
    "RESOURCE_CONTRACT_MULTI_ANNOTATION_REQUIRES_SPLIT",
    "severity_for_kind",
    # projector
    "ViewDiagnosticProjector",
]
