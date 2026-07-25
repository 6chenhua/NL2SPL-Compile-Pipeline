"""Construct domain package."""

from nl2spl.compiler.constructs.graph import (
    ConstructEdge,
    ConstructEdgeType,
    ConstructGraph,
)
from nl2spl.compiler.constructs.registry import SPLConstructRegistry
from nl2spl.compiler.constructs.satisfaction import (
    ConstructCompleteness,
    ConstructSatisfactionReport,
    CutlineReason,
    FrontierStatus,
    SlotSatisfaction,
    SlotStatus,
)
from nl2spl.compiler.constructs.spec import (
    ConstructIRS,
    ExistencePolicy,
    NoDemandBehavior,
    SlotSpec,
)
from nl2spl.compiler.repair_contracts import (
    ActionabilityDecisionStatus,
    NonEditableDisposition,
    PatchTypeMeta,
    RepairAffordanceSpec,
    SlotActionability,
    SlotActionabilityDecision,
)

__all__ = [
    "ActionabilityDecisionStatus",
    "ConstructCompleteness",
    "ConstructEdge",
    "ConstructEdgeType",
    "ConstructGraph",
    "ConstructIRS",
    "ConstructSatisfactionReport",
    "CutlineReason",
    "ExistencePolicy",
    "FrontierStatus",
    "NoDemandBehavior",
    "NonEditableDisposition",
    "PatchTypeMeta",
    "RepairAffordanceSpec",
    "SPLConstructRegistry",
    "SlotActionability",
    "SlotActionabilityDecision",
    "SlotSatisfaction",
    "SlotSpec",
    "SlotStatus",
]
