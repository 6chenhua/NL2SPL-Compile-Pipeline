"""Compatibility shim for construct domain types.

New code should import from ``nl2spl.compiler.constructs``.
"""

from nl2spl.compiler.constructs import (
    ActionabilityDecisionStatus,
    ConstructCompleteness,
    ConstructEdge,
    ConstructEdgeType,
    ConstructGraph,
    ConstructIRS,
    ConstructSatisfactionReport,
    CutlineReason,
    ExistencePolicy,
    FrontierStatus,
    NoDemandBehavior,
    NonEditableDisposition,
    PatchTypeMeta,
    RepairAffordanceSpec,
    SlotActionability,
    SlotActionabilityDecision,
    SlotSatisfaction,
    SlotSpec,
    SlotStatus,
    SPLConstructRegistry,
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
