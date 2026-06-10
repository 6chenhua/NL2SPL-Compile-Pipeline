"""ResourceContractAnnotationCoverageValidator — purely diagnostic.

Checks whether structural hard facts have corresponding confirmed
resource contract annotations/demands in the DemandView.  Produces
``ViewDiagnostic`` records only; never generates demands, never
modifies routes or the DemandView.
"""

from __future__ import annotations

from nl2spl.canonical.compile_input import CanonicalCompileInput, VariableFact
from nl2spl.compiler.resource_contract_demand_view.diagnostics import (
    RESOURCE_CONTRACT_ANNOTATION_COVERAGE_GAP,
    RESOURCE_CONTRACT_ANNOTATION_MISSING,
    severity_for_kind,
)
from nl2spl.compiler.resource_contract_demand_view.model import (
    DemandViewDemand,
    ResourceContractDemandView,
    ViewDiagnostic,
)
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR


class ResourceContractAnnotationCoverageValidator:
    """Check structural hard facts against confirmed DemandView demands.

    Independent, read-only component.  Does NOT generate demands, modify
    routes, or touch the DemandView.
    """

    def validate(
        self,
        canonical_input: CanonicalCompileInput,
        resolved_spans: list[SpanIR],  # noqa: ARG002 — reserved for future use
        resolved_routes: FieldRouteIR,  # noqa: ARG002 — reserved for future use
        demand_view: ResourceContractDemandView,
    ) -> list[ViewDiagnostic]:
        """Produce coverage diagnostics for unmatched structural hard facts.

        Args:
            canonical_input: Adapter output with hard facts.
            resolved_spans: Resolved spans (reserved).
            resolved_routes: Resolved routes (reserved).
            demand_view: Confirmed resource contract demands.

        Returns:
            List of ``ViewDiagnostic``.  Empty when all structural facts
            are covered.
        """
        diagnostics: list[ViewDiagnostic] = []

        # Build lookup: direction → set of demand identifiers
        # (packet_id, span_id, section_id) for matching.
        valid_demands = list(demand_view.valid_demands()) if demand_view.demands else []
        demand_lookup = _build_demand_lookup(valid_demands)

        for direction, facts in (
            ("input", canonical_input.hard_facts.inputs),
            ("output", canonical_input.hard_facts.outputs),
        ):
            for fact in facts:
                if self._fact_is_covered(fact, direction, demand_lookup):
                    continue
                # Collect evidence span_ids for stable diagnostic identity
                ev_span_ids: list[str] = []
                for ev in fact.evidence:
                    for sid in (getattr(ev, "source_span_ids", []) or []):
                        if sid not in ev_span_ids:
                            ev_span_ids.append(sid)
                # Include packet ID in the diagnostic demand_id for
                # disambiguation when no span IDs exist.
                pkt_ref = ""
                for ev in fact.evidence:
                    pid = getattr(ev, "source_packet_id", None)
                    if pid:
                        pkt_ref = f" (packet={pid})"
                        break
                diagnostics.append(ViewDiagnostic(
                    kind=RESOURCE_CONTRACT_ANNOTATION_MISSING,
                    severity=severity_for_kind(RESOURCE_CONTRACT_ANNOTATION_MISSING),
                    message=(
                        f"Structural hard fact '{fact.name}' "
                        f"(direction={direction}, "
                        f"required={fact.required}){pkt_ref} has no matching "
                        f"confirmed resource contract annotation in DemandView."
                    ),
                    span_ids=tuple(ev_span_ids),
                    demand_id=f"missing:{direction}:{fact.name}" if not ev_span_ids else None,
                ))

        # Coverage gap: any structural fact without a matching demand
        # qualifies as a gap.
        if diagnostics:
            # Flag the first occurrence as a coverage gap summary
            unmatched_dirs = sorted(set(
                "input" for _ in canonical_input.hard_facts.inputs
                if not self._fact_is_covered(_, "input", demand_lookup)
            ) | set(
                "output" for _ in canonical_input.hard_facts.outputs
                if not self._fact_is_covered(_, "output", demand_lookup)
            ))
            if unmatched_dirs:
                diagnostics.insert(0, ViewDiagnostic(
                    kind=RESOURCE_CONTRACT_ANNOTATION_COVERAGE_GAP,
                    severity=severity_for_kind(
                        RESOURCE_CONTRACT_ANNOTATION_COVERAGE_GAP
                    ),
                    message=(
                        f"Resource contract annotation coverage gap detected: "
                        f"{len(diagnostics)} unmatched structural facts "
                        f"(directions: {', '.join(unmatched_dirs)}). "
                        f"Stage 2 may not have produced confirmed resource "
                        f"contract annotations for all adapter hard facts."
                    ),
                    span_ids=(),
                    demand_id=None,
                ))

        return diagnostics

    @staticmethod
    def _fact_is_covered(
        fact: VariableFact,
        direction: str,
        demand_lookup: dict[str, set[str]],
    ) -> bool:
        """Check whether *fact* has at least one matching demand.

        A match occurs when ANY evidence key (packet_id or span_id) from
        the fact appears in the demand lookup for the same direction.
        """
        return bool(demand_lookup.get(direction, set()) & _fact_match_keys(fact))


def _fact_match_keys(fact: VariableFact) -> set[str]:
    """Extract individual match keys from a VariableFact's evidence.

    Returns a set of packet_id and span_id strings.  A match on ANY
    key is sufficient.
    """
    keys: set[str] = set()
    for ev in fact.evidence:
        pid = getattr(ev, "source_packet_id", None)
        if pid:
            keys.add(f"pkt:{pid}")
        for sid in (getattr(ev, "source_span_ids", []) or []):
            keys.add(f"span:{sid}")
    return keys


def _build_demand_lookup(
    demands: list[DemandViewDemand],
) -> dict[str, set[str]]:
    """Build direction → {match_key} for coverage matching."""
    lookup: dict[str, set[str]] = {"input": set(), "output": set()}
    for d in demands:
        pkt = d.source_packet_id
        if pkt:
            lookup[d.direction].add(f"pkt:{pkt}")
        for sid in d.source_span_ids:
            lookup[d.direction].add(f"span:{sid}")
    return lookup
