"""Compat shim for legacy code that constructs ResourceContract*IR with bool required.

B1 introduced ``requiredness: ContractRequiredness`` and ``required: bool | None``.
Old code that only sets ``required=True/False`` needs this shim to bridge the gap.

Once all production consumers use ``requiredness`` directly, this file should be
removed (Phase E).  Marked as ``MIGRATION SHIM``.
"""

from __future__ import annotations

from nl2spl.ir.resource_contract_ir import (
    ContractRequiredness,
    ResourceContractDemandIR,
    ResourceContractFieldIR,
    ResourceContractPlanIR,
)


def demand_with_required(
    required: bool,
    **kwargs: object,
) -> ResourceContractDemandIR:
    """Build a ``ResourceContractDemandIR`` from legacy bool required.

    MIGRATION SHIM — remove after all production callers use requiredness.
    """
    requiredness: ContractRequiredness = "required" if required else "optional"
    return ResourceContractDemandIR(
        requiredness=requiredness,
        required=required,
        **kwargs,  # type: ignore[arg-type]
    )


def field_with_required(
    required: bool,
    **kwargs: object,
) -> ResourceContractFieldIR:
    """Build a ``ResourceContractFieldIR`` from legacy bool required.

    MIGRATION SHIM — remove after all production callers use requiredness.
    """
    requiredness: ContractRequiredness = "required" if required else "optional"
    return ResourceContractFieldIR(
        requiredness=requiredness,
        required=required,
        **kwargs,  # type: ignore[arg-type]
    )


def plan_with_required(
    demands: list[ResourceContractDemandIR],
    warnings: list[str] | None = None,
) -> ResourceContractPlanIR:
    """Build a ``ResourceContractPlanIR`` ensuring all demands have requiredness set.

    MIGRATION SHIM — remove after Phase D removes ResourceContractPlanner.
    """
    hydrated: list[ResourceContractDemandIR] = []
    for d in demands:
        if d.requiredness == "unspecified" and d.required is not None:
            hydrated.append(demand_with_required(
                required=d.required,
                demand_id=d.demand_id,
                direction=d.direction,
                evidence_text=d.evidence_text,
                source_span_ids=list(d.source_span_ids),
                source_section_id=d.source_section_id,
                source_packet_id=d.source_packet_id,
                route_annotation_ids=list(d.route_annotation_ids),
                evidence_sources=list(d.evidence_sources),
            ))
        else:
            hydrated.append(d)
    return ResourceContractPlanIR(demands=hydrated, warnings=warnings or [])
