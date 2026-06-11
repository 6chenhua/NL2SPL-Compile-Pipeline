"""ResourceContractPlanner — deterministic demand aggregation from span/route
evidence.

Design gate 1: the planner MUST consume deterministic section/list-item
evidence in addition to ``RouteAnnotation``.  When an ``Inputs for each run``
or ``Required Outputs`` section contains list items, those items produce
demands even if no final contract annotation exists.
"""

from __future__ import annotations

from collections import defaultdict

from nl2spl.canonical.compile_input import CanonicalCompileInput, RawSection, SemanticPacket
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.resource_contract_ir import (
    ContractDirection,
    ResourceContractDemandIR,
    ResourceContractPlanIR,
)
from nl2spl.ir.span_ir import SpanIR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INPUT_SECTION_TITLES = frozenset({"inputs for each run", "inputs_for_each_run"})
_OUTPUT_SECTION_TITLES = frozenset({"required outputs", "required_outputs"})

_CONTRACT_ROLES = frozenset({"input_contract", "output_contract"})


def _is_empty_marker(text: str) -> bool:
    """Return True if *text* is a recognized empty-value marker."""
    stripped = text.strip().rstrip(".").lower()
    return stripped in {"none", "n/a", "na", "nil", "null", "—", "-"}


def _direction_for_role(role: str) -> ContractDirection:
    """Map semantic_role to direction."""
    return "input" if "input" in role else "output"


def _direction_for_section_title(title: str) -> ContractDirection | None:
    """Return direction for a known section title, or None."""
    if title in _INPUT_SECTION_TITLES:
        return "input"
    if title in _OUTPUT_SECTION_TITLES:
        return "output"
    return None


def _compute_required(direction: ContractDirection, evidence_text: str) -> bool:
    """Determine whether a demand is required from its source.

    Outputs are always required.  Inputs are required unless the source
    text explicitly marks them as optional.
    """
    if direction == "output":
        return True
    return not evidence_text.lower().startswith("optional ")


class ResourceContractPlanner:
    """Build source-demanded resource contract plan from structured evidence.

    The planner is pure deterministic code — no LLM, no raw-NL heuristics.
    """

    # -- public API ----------------------------------------------------------

    def plan(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None = None,
    ) -> ResourceContractPlanIR:
        """Aggregate resource contract demands from all evidence sources.

        Args:
            spans: Resolved spans with provenance.
            routes: Resolved field routes with annotations and structural priors.
            canonical_input: Canonical adapter output (sections, packets).

        Returns:
            ``ResourceContractPlanIR`` with demands and warnings.
        """
        span_by_id = {s.span_id: s for s in spans}

        # Build lookup tables from canonical_input
        section_by_id: dict[str, RawSection] = {}
        packet_by_id: dict[str, SemanticPacket] = {}
        list_item_packets_by_section: dict[str, list[SemanticPacket]] = defaultdict(list)
        if canonical_input is not None:
            section_by_id = {s.section_id: s for s in canonical_input.raw_sections}
            packet_by_id = {p.packet_id: p for p in canonical_input.semantic_packets}
            for packet in canonical_input.semantic_packets:
                if packet.packet_type in ("list_item", "sentence"):
                    list_item_packets_by_section[packet.source_section_id].append(packet)

        # ── Rule 1: annotation evidence ────────────────────────────────
        demands_by_key: dict[tuple[str, str], ResourceContractDemandIR] = {}
        for ann in self._contract_annotations(routes):
            direction = _direction_for_role(ann.semantic_role or "")
            span = span_by_id.get(ann.span_id)
            evidence_text = span.text if span else ""
            key = (ann.span_id, direction)
            if key in demands_by_key:
                self._merge_annotation_evidence(demands_by_key[key], ann)
                continue
            req = _compute_required(direction, evidence_text)
            demand = ResourceContractDemandIR(
                demand_id=self._demand_id(direction, ann.span_id),
                direction=direction,
                requiredness="required" if req else "optional",
                required=req,
                evidence_text=evidence_text,
                source_span_ids=[ann.span_id],
                source_section_id=ann.source_section_id,
                source_packet_id=ann.source_packet_id,
                route_annotation_ids=[ann.span_id],
                evidence_sources=["route_annotation"],
            )
            demands_by_key[key] = demand

        # ── Rule 2: deterministic section/list-item evidence ───────────
        for span in spans:
            if _is_empty_marker(span.text):
                continue
            section_id = span.source_section_id
            if not section_id:
                continue
            section = section_by_id.get(section_id)
            if section is None:
                continue
            direction = _direction_for_section_title(section.canonical_title)
            if direction is None:
                continue

            packet = packet_by_id.get(span.source_packet_id or "")
            if packet is not None and packet.packet_type not in ("list_item", "sentence"):
                continue

            key = (span.span_id, direction)
            if key in demands_by_key:
                # Evidence already captured via annotation; add deterministic source tags.
                existing = demands_by_key[key]
                for tag in ("section_title", "list_item_packet"):
                    if tag not in existing.evidence_sources:
                        existing.evidence_sources.append(tag)
                continue

            req = _compute_required(direction, span.text)
            demand = ResourceContractDemandIR(
                demand_id=self._demand_id(direction, span.span_id),
                direction=direction,
                requiredness="required" if req else "optional",
                required=req,
                evidence_text=span.text,
                source_span_ids=[span.span_id],
                source_section_id=section_id,
                source_packet_id=span.source_packet_id,
                evidence_sources=["section_title"],
            )
            if packet is not None:
                demand.evidence_sources.append("list_item_packet")
            demands_by_key[key] = demand

        demands = sorted(demands_by_key.values(), key=lambda d: d.demand_id)

        # ── Rule 3: warnings for unmapped list items ───────────────────
        warnings: list[str] = []
        matched_packet_ids: set[str] = set()
        for demand in demands:
            if demand.source_packet_id:
                matched_packet_ids.add(demand.source_packet_id)

        for section_id, packets in list_item_packets_by_section.items():
            section = section_by_id.get(section_id)
            if section is None:
                continue
            direction = _direction_for_section_title(section.canonical_title)
            if direction is None:
                continue
            for packet in packets:
                if _is_empty_marker(packet.text):
                    continue
                if packet.packet_id not in matched_packet_ids:
                    warnings.append(
                        f"ResourceContractPlan: list item in section "
                        f"'{section.canonical_title}' (packet_id={packet.packet_id}) "
                        f"has no resolved span; demand not generated. "
                        f"text='{packet.text[:120]}'"
                    )

        return ResourceContractPlanIR(demands=demands, warnings=warnings)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _contract_annotations(routes: FieldRouteIR) -> list[RouteAnnotation]:
        """Return annotations that carry resource contract semantics.

        ARC5: demand existence is authorized ONLY by semantic_role in
        {input_contract, output_contract}.  route_family and construct_target
        are consistency evidence only and must not independently create demand.
        """
        return [
            ann for ann in routes.annotations
            if ann.semantic_role in _CONTRACT_ROLES
        ]

    @staticmethod
    def _merge_annotation_evidence(
        demand: ResourceContractDemandIR, ann: RouteAnnotation
    ) -> None:
        """Merge an additional annotation into an existing demand."""
        if ann.span_id not in demand.route_annotation_ids:
            demand.route_annotation_ids.append(ann.span_id)
        if ann.span_id not in demand.source_span_ids:
            demand.source_span_ids.append(ann.span_id)
        demand.evidence_sources.append("route_annotation")

    @staticmethod
    def _demand_id(direction: ContractDirection, span_id: str) -> str:
        """Build a stable demand id."""
        return f"rcd_{direction}_{span_id}"
