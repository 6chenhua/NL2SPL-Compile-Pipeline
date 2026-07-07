"""ResourceContractPlan IR — source-demanded resource contract evidence.

``ResourceContractPlanIR`` aggregates span-level route evidence and
deterministic structural evidence into stable, checkpointable
construct-level demand instances.  It does NOT decide ``resource_kind``,
name, or data_type — those decisions belong to Stage 6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ContractDirection = Literal["input", "output"]
ContractRequiredness = Literal["required", "optional", "unspecified"]


@dataclass
class ResourceContractDemandIR:
    """A single source-demanded resource contract instance.

    Attributes:
        demand_id: Stable identifier (``rcd_input_<span_id>`` or
            ``rcd_output_<span_id>``).
        direction: ``input`` or ``output``.
        required: Whether the source marks this as required
            (B1: ``bool | None`` — compat projection).
        evidence_text: Original source text backing this demand.
        requiredness: Tri-state (B1: canonical semantics).
        source_span_ids: Resolved span IDs that carry this evidence.
        source_section_id: Adapter section provenance.
        source_packet_id: Adapter packet provenance.
        route_annotation_ids: IDs of contributing ``RouteAnnotation``
            spans (empty when demand is purely deterministic).
        evidence_sources: Tags describing where the evidence came from
            (``section_title``, ``list_item_packet``,
            ``route_annotation``, ``structural_prior``).
        metadata: Extension map for downstream consumers.
    """

    demand_id: str
    direction: ContractDirection
    required: bool | None  # B1: type widened; NO default for positional compat
    evidence_text: str
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    route_annotation_ids: list[str] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    requiredness: ContractRequiredness = "unspecified"

    def __post_init__(self) -> None:
        """Hydrate requiredness from legacy bool required when not explicitly set.

        B1 compat: when old code constructs ``ResourceContractDemandIR(..., required=True)``
        without passing ``requiredness``, auto-set ``requiredness`` to match.
        When ``requiredness`` is explicitly passed it takes priority.
        """
        if self.requiredness == "unspecified" and self.required is not None:
            object.__setattr__(
                self,
                "requiredness",
                "required" if self.required else "optional",
            )

    def to_payload(self) -> dict[str, Any]:
        """Return deterministic JSON-serializable payload."""
        return {
            "demand_id": self.demand_id,
            "direction": self.direction,
            "requiredness": self.requiredness,
            "required": self.required,
            "evidence_text": self.evidence_text,
            "source_span_ids": sorted(self.source_span_ids),
            "source_section_id": self.source_section_id,
            "source_packet_id": self.source_packet_id,
            "route_annotation_ids": sorted(self.route_annotation_ids),
            "evidence_sources": sorted(self.evidence_sources),
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass
class ResourceContractPlanIR:
    """Source-demanded resource contract plan.

    Consumed by Stage 3.5, Stage 6, and IRS.  Does NOT contain
    ``resource_kind``, variable names, or data types.
    """

    demands: list[ResourceContractDemandIR] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        """Return deterministic JSON-serializable payload."""
        return {
            "demands": [d.to_payload() for d in self.demands],
            "warnings": list(self.warnings),
        }

    def input_demands(self) -> list[ResourceContractDemandIR]:
        """Return only input-direction demands."""
        return [d for d in self.demands if d.direction == "input"]

    def output_demands(self) -> list[ResourceContractDemandIR]:
        """Return only output-direction demands."""
        return [d for d in self.demands if d.direction == "output"]


# =============================================================================
# Stage 6 materialization types
# =============================================================================

ResourceKind = Literal["variable", "file", "api", "type"]
ResourceScopeKind = Literal["global", "worker", "handoff"]


@dataclass
class ResourceContractFieldIR:
    """Stage 6 LLM output: a materialized resource contract field.

    Attributes:
        demand_id: Back-reference to ``ResourceContractDemandIR``.
        name: Resource name (snake_case).
        resource_kind: ``variable``, ``file``, ``api``, or ``type``.
        direction: ``input`` or ``output``.
        data_type: Data type.
        required: Whether the resource is required.
        description: Human-readable description.
        path: File path (``< >`` for runtime) when resource_kind is ``file``.
        source_span_ids: Resolved span IDs for provenance.
        source_section_id: Adapter section provenance.
        source_packet_id: Adapter packet provenance.
        evidence_text: Original evidence text backing this field.
        justification: LLM justification for resource_kind selection.
    """

    demand_id: str
    name: str
    resource_kind: ResourceKind
    direction: ContractDirection
    data_type: str
    required: bool | None  # B1: type widened; NO default for positional compat
    description: str
    requiredness: ContractRequiredness = "unspecified"
    path: str | None = None
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    evidence_text: str | None = None
    justification: str | None = None

    def __post_init__(self) -> None:
        """Hydrate requiredness from legacy bool required when not explicitly set."""
        if self.requiredness == "unspecified" and self.required is not None:
            object.__setattr__(
                self,
                "requiredness",
                "required" if self.required else "optional",
            )


@dataclass
class ResourceContractBindingIR:
    """Scope-aware binding between a resource and its source demand.

    Records which materialized resource (variable, file, etc.) satisfies
    which contract demand, in which scope.  Used by ProducerIndex,
    resource resolver, and IRS for demand-satisfaction checks.
    """

    contract_demand_id: str
    resource_name: str
    resource_kind: ResourceKind
    direction: ContractDirection
    scope_kind: ResourceScopeKind
    scope_id: str | None
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
