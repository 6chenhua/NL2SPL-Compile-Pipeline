"""ResourceContractDemandView data model.

Phase A temporary view model residing inside ``compiler/resource_contract_demand_view``.
It does NOT modify ``ir/resource_contract_ir.py``.

Phase B0/B1 will decide whether these fields merge back into the canon IR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ContractDirection = Literal["input", "output"]
ContractRequiredness = Literal["required", "optional", "unspecified"]
EvidenceSourceKind = Literal["stage2_annotation", "compat_section_title"]
ViewStatusKind = Literal[
    "valid",
    "invalid_direction",
    "invalid_requiredness",
    "invalid_multi_contract",
    "skipped",
]


# ── diagnostic record ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ViewDiagnostic:
    """A DemandView builder diagnostic emitted during projection.

    Attributes:
        kind: Stable diagnostic kind from ``diagnostics.py``.
        severity: ``info``, ``warning``, or ``error``.
        message: Human-readable diagnostic message.
        span_ids: Affected span IDs (tuple for immutability).
        demand_id: Affected demand ID, when applicable.
    """

    kind: str
    severity: str
    message: str
    span_ids: tuple[str, ...] = ()
    demand_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "message": self.message,
            "span_ids": sorted(self.span_ids),
            "demand_id": self.demand_id,
        }


# ── demand view item ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class DemandViewDemand:
    """A single source-demanded resource contract demand within the view.

    This is a *projection* of Stage 2 confirmed annotations — no semantic
    inference, no title/text fallback, no LLM.

    Attributes:
        demand_id: Stable identifier (``rcd_input_<span_id>`` or ``rcd_output_<span_id>``).
        direction: ``input`` or ``output``.
        requiredness: Tri-state requiredness from Stage 2 annotation contract.
        required: Compatibility boolean projection (True/False/None).
        evidence_text: Original source text.
        source_span_ids: Resolved span IDs (tuple for immutability).
        source_section_id: Adapter section provenance.
        source_packet_id: Adapter packet provenance.
        source_hint_ids: Adapter hint provenance.
        route_annotation_ids: Contributing annotation IDs.
        evidence_source: Where the evidence came from.
        view_status: Validity status for downstream consumers.
    """

    demand_id: str
    direction: ContractDirection
    requiredness: ContractRequiredness
    required: bool | None
    evidence_text: str
    source_span_ids: tuple[str, ...] = ()
    source_section_id: str | None = None
    source_packet_id: str | None = None
    source_hint_ids: tuple[str, ...] = ()
    route_annotation_ids: tuple[str, ...] = ()
    evidence_source: EvidenceSourceKind = "stage2_annotation"
    view_status: ViewStatusKind = "valid"
    resource_ref: str | None = None

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
            "source_hint_ids": sorted(self.source_hint_ids),
            "route_annotation_ids": sorted(self.route_annotation_ids),
            "evidence_source": self.evidence_source,
            "view_status": self.view_status,
            "resource_ref": self.resource_ref,
        }


# ── demand view ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResourceContractDemandView:
    """Immutable source-demanded resource contract view.

    Built by ``DemandViewBuilder`` from resolved spans and routes.
    Consumed by Stage 3.5, Stage 6, and Post-normalize IRS.

    Instances are frozen — downstream code cannot mutate demands or
    diagnostics after construction without creating a new view.
    """

    demands: tuple[DemandViewDemand, ...] = ()
    view_diagnostics: tuple[ViewDiagnostic, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        """Return deterministic JSON-serializable payload."""
        return {
            "demands": [d.to_payload() for d in self.demands],
            "view_diagnostics": [diag.to_payload() for diag in self.view_diagnostics],
            "warnings": list(self.warnings),
        }

    def input_demands(self) -> list[DemandViewDemand]:
        """Return only input-direction demands."""
        return [d for d in self.demands if d.direction == "input"]

    def output_demands(self) -> list[DemandViewDemand]:
        """Return only output-direction demands."""
        return [d for d in self.demands if d.direction == "output"]

    def valid_demands(self) -> list[DemandViewDemand]:
        """Return demands with view_status == 'valid'."""
        return [d for d in self.demands if d.view_status == "valid"]
