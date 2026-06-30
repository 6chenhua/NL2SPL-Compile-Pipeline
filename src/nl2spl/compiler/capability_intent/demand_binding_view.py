"""Read-only DemandView projection consumed by the capability resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nl2spl.compiler.resource_contract_demand_view.model import (
    ResourceContractDemandView,
)


@dataclass(frozen=True)
class CapabilityDemandBindingViewIR:
    demand_id: str
    direction: Literal["input", "output"]
    requiredness: Literal["required", "optional", "unspecified"]
    evidence_text: str
    source_span_ids: tuple[str, ...]
    source_section_id: str | None
    source_packet_id: str | None
    source_hint_ids: tuple[str, ...]
    view_status: str
    resource_ref: str | None


def project_capability_binding_view(
    demand_view: ResourceContractDemandView | None,
) -> tuple[CapabilityDemandBindingViewIR, ...]:
    if demand_view is None:
        return ()
    return tuple(
        CapabilityDemandBindingViewIR(
            demand_id=item.demand_id,
            direction=item.direction,
            requiredness=item.requiredness,
            evidence_text=item.evidence_text,
            source_span_ids=tuple(item.source_span_ids),
            source_section_id=item.source_section_id,
            source_packet_id=item.source_packet_id,
            source_hint_ids=tuple(item.source_hint_ids),
            view_status=item.view_status,
            resource_ref=item.resource_ref,
        )
        for item in sorted(demand_view.demands, key=lambda demand: demand.demand_id)
    )
