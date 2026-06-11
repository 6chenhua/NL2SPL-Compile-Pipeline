"""DemandViewBuilder — pure projection from resolved annotations.

Reads confirmed ``RouteAnnotation`` fields only.  Does not accept
``CanonicalCompileInput``, does not inspect section titles, does not
parse evidence text, does not call an LLM.
"""

from __future__ import annotations

from nl2spl.compiler.resource_contract_demand_view.diagnostics import (
    RESOURCE_CONTRACT_AMBIGUOUS_MULTI_DIRECTION_SPAN,
    RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_DIRECTION,
    RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_REQUIREDNESS,
    RESOURCE_CONTRACT_ANNOTATION_MISSING_DIRECTION,
    RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS,
    RESOURCE_CONTRACT_DUPLICATE_DEMAND_ID,
    RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT,
    RESOURCE_CONTRACT_MULTI_ANNOTATION_REQUIRES_SPLIT,
    severity_for_kind,
)
from nl2spl.compiler.resource_contract_demand_view.model import (
    ContractDirection,
    ContractRequiredness,
    DemandViewDemand,
    ResourceContractDemandView,
    ViewDiagnostic,
)
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR

# ── constants ───────────────────────────────────────────────────────────────

_CONTRACT_ROLES = frozenset({"input_contract", "output_contract"})


# ── helpers ─────────────────────────────────────────────────────────────────


def _direction_candidates(ann: RouteAnnotation) -> tuple[ContractDirection, ...]:
    """Return all direction signals from a single ``RouteAnnotation``.

    Collects candidates from semantic_role, slot_target, and metadata,
    then returns the deduplicated ordered tuple.  Returns empty tuple
    when no direction signal exists.
    """
    candidates: list[ContractDirection] = []

    if ann.semantic_role == "input_contract":
        candidates.append("input")
    elif ann.semantic_role == "output_contract":
        candidates.append("output")

    if ann.slot_target == "input":
        candidates.append("input")
    elif ann.slot_target == "output":
        candidates.append("output")

    meta_dir = ann.metadata.get("direction")
    if meta_dir == "input":
        candidates.append("input")
    elif meta_dir == "output":
        candidates.append("output")

    # dedup preserving order
    seen: set[ContractDirection] = set()
    result: list[ContractDirection] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return tuple(result)


def _requiredness_info(
    anns: list[RouteAnnotation],
) -> tuple[ContractRequiredness, bool]:
    """Resolve requiredness across *anns*.

    Returns ``(requiredness, is_conflict)``:

    * No annotation carries requiredness → ``("unspecified", False)``
      (missing, not conflicting).
    * All annotations that do carry requiredness agree → the agreed value
      with ``is_conflict=False``.
    * Annotations disagree → ``("unspecified", True)`` (conflict).
    """
    values: set[ContractRequiredness] = set()
    for ann in anns:
        rval = ann.metadata.get("requiredness")
        if rval in ("required", "optional", "unspecified"):
            values.add(rval)  # type: ignore[arg-type]

    if len(values) == 0:
        return ("unspecified", False)  # genuinely missing
    if len(values) == 1:
        return (next(iter(values)), False)  # agreed
    return ("unspecified", True)  # conflicting


def _required_bool(requiredness: ContractRequiredness) -> bool | None:
    """Compatibility projection from tri-state to bool | None.

    * required → True
    * optional → False
    * unspecified → None (must never be silently treated as True)
    """
    if requiredness == "required":
        return True
    if requiredness == "optional":
        return False
    return None


def _make_demand_id(direction: ContractDirection, span_id: str) -> str:
    """Build a stable demand id: ``rcd_{direction}_{span_id}``."""
    return f"rcd_{direction}_{span_id}"


# ── public API ──────────────────────────────────────────────────────────────


class DemandViewBuilder:
    """Build a ``ResourceContractDemandView`` from resolved routes.

    The builder performs a *pure projection*: it reads structured
    annotation fields and emits demands.  It makes zero semantic
    guesses.

    Input contract:
      - ``resolved_spans`` — list of resolved ``SpanIR`` objects.
      - ``resolved_routes`` — ``FieldRouteIR`` with finalized annotations.

    The builder does NOT accept ``CanonicalCompileInput``, raw text, or
    an LLM client.
    """

    def build(
        self,
        resolved_spans: list[SpanIR],
        resolved_routes: FieldRouteIR,
    ) -> ResourceContractDemandView:
        """Project resource contract annotations into a DemandView.

        Args:
            resolved_spans: Resolved spans (for evidence text lookup).
            resolved_routes: Resolved field routes with annotations.

        Returns:
            ``ResourceContractDemandView`` with demands and diagnostics.
        """
        span_by_id = {s.span_id: s for s in resolved_spans}

        # Stage 1 — collect contract annotations
        contract_anns = self._select_contract_annotations(resolved_routes)

        # Stage 1b — validate contract annotation invariants.
        # A resource contract annotation MUST have executable=False.
        # Violations produce invalid_annotation_contract diagnostics and
        # the annotation is excluded from demand projection.
        diagnostics: list[ViewDiagnostic] = []
        valid_anns: list[RouteAnnotation] = []
        for ann in contract_anns:
            if ann.executable is not False:
                kind = RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT
                diagnostics.append(ViewDiagnostic(
                    kind=kind,
                    severity=severity_for_kind(kind),
                    message=(
                        f"Resource contract annotation for span {ann.span_id} "
                        f"has executable={ann.executable}; expected executable=False. "
                        f"semantic_role={ann.semantic_role}."
                    ),
                    span_ids=(ann.span_id,),
                ))
            else:
                valid_anns.append(ann)
        contract_anns = valid_anns

        # ── Stage 1c — suspicious non-contract annotations ─────────────
        # Annotations with construct_target=RESOURCE_CONTRACT or
        # route_family=resource_contract but whose semantic_role is NOT
        # input_contract/output_contract are suspicious.  They do NOT
        # generate demand but MUST produce a visible diagnostic.
        for ann in resolved_routes.annotations:
            if ann.semantic_role in _CONTRACT_ROLES:
                continue  # already handled as contract annotation
            suspicious = (
                ann.construct_target == "RESOURCE_CONTRACT"
                or ann.route_family == "resource_contract"
            )
            if suspicious:
                kind = RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT
                diagnostics.append(ViewDiagnostic(
                    kind=kind,
                    severity=severity_for_kind(kind),
                    message=(
                        f"Annotation for span {ann.span_id} has "
                        f"construct_target={ann.construct_target!r}, "
                        f"route_family={ann.route_family!r} but "
                        f"semantic_role={ann.semantic_role!r}; "
                        f"not a resource contract role; no demand generated."
                    ),
                    span_ids=(ann.span_id,),
                ))

        # ── Stage 2 — per-annotation direction consistency check ───────
        # A single annotation with conflicting direction signals
        # (e.g. semantic_role=input + slot_target=output) is rejected.
        annotations_with_direction: list[tuple[RouteAnnotation, ContractDirection]] = []
        spans_with_intra_ann_direction_conflict: set[str] = set()

        for ann in contract_anns:
            candidates = _direction_candidates(ann)
            if len(candidates) == 0:
                continue  # no direction — handled by no-direction diagnostics
            if len(candidates) > 1:
                # Intra-annotation direction conflict
                kind = RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_DIRECTION
                diagnostics.append(ViewDiagnostic(
                    kind=kind,
                    severity=severity_for_kind(kind),
                    message=(
                        f"Direction conflict within annotation for span "
                        f"{ann.span_id}: semantic_role={ann.semantic_role}, "
                        f"slot_target={ann.slot_target}, "
                        f"metadata.direction={ann.metadata.get('direction')} "
                        f"— candidates={list(candidates)}."
                    ),
                    span_ids=(ann.span_id,),
                ))
                spans_with_intra_ann_direction_conflict.add(ann.span_id)
            else:
                annotations_with_direction.append((ann, candidates[0]))

        # Stage 3 — group per (span_id, direction, source_packet_id)
        grouped: dict[tuple[str, ContractDirection, str | None],
                      list[RouteAnnotation]] = {}
        for ann, direction in annotations_with_direction:
            if ann.span_id in spans_with_intra_ann_direction_conflict:
                continue
            key = (ann.span_id, direction, ann.source_packet_id)
            grouped.setdefault(key, []).append(ann)

        # Identify spans with contract annotations but zero resolvable direction
        spans_with_contract_anns: set[str] = {a.span_id for a in contract_anns}
        spans_with_direction: set[str] = {key[0] for key in grouped}
        spans_without_direction = (
            spans_with_contract_anns
            - spans_with_direction
            - spans_with_intra_ann_direction_conflict
        )

        # ── Stage 4 — multi-direction conflict detection ───────────────
        span_dirs: dict[str, set[ContractDirection]] = {}
        for span_id, direction, _pkt in grouped:
            span_dirs.setdefault(span_id, set()).add(direction)

        suppressed_span_ids: set[str] = set()
        for span_id, dirs in sorted(span_dirs.items()):
            if len(dirs) <= 1:
                continue
            involved = [k for k in grouped if k[0] == span_id]
            packets_per_dir: dict[ContractDirection, set[str | None]] = {}
            for (_, d, pkt) in involved:
                packets_per_dir.setdefault(d, set()).add(pkt)
            input_pkts = packets_per_dir.get("input", set())
            output_pkts = packets_per_dir.get("output", set())
            none_involved = (
                None in (input_pkts | output_pkts)
                if (input_pkts or output_pkts)
                else False
            )
            disjoint = bool(
                input_pkts
                and output_pkts
                and not none_involved
                and input_pkts.isdisjoint(output_pkts)
            )
            if disjoint:
                kind = RESOURCE_CONTRACT_MULTI_ANNOTATION_REQUIRES_SPLIT
                diagnostics.append(ViewDiagnostic(
                    kind=kind,
                    severity=severity_for_kind(kind),
                    message=(
                        f"Span {span_id} has both input and output "
                        f"resource contract annotations with different "
                        f"packet IDs; span may need splitting."
                    ),
                    span_ids=(span_id,),
                ))
            else:
                kind = RESOURCE_CONTRACT_AMBIGUOUS_MULTI_DIRECTION_SPAN
                diagnostics.append(ViewDiagnostic(
                    kind=kind,
                    severity=severity_for_kind(kind),
                    message=(
                        f"Span {span_id} has both input_contract and "
                        f"output_contract annotations — direction "
                        f"conflict."
                    ),
                    span_ids=(span_id,),
                ))
                suppressed_span_ids.add(span_id)

        # ── Stage 5 — produce demands ──────────────────────────────────
        demands: dict[str, DemandViewDemand] = {}
        demands_per_key: dict[tuple[str, ContractDirection, str | None], str] = {}

        for (span_id, direction, packet_id), anns in sorted(grouped.items()):
            if span_id in suppressed_span_ids:
                continue

            demand_id = _make_demand_id(direction, span_id)

            # Check for duplicate demand_id (same span+direction, different packets)
            dedup_key = (span_id, direction, packet_id)
            if demand_id in demands:
                # Same demand_id from a different key — emit duplicate diagnostic
                existing_key_pkt = None
                for (s2, d2, p2), did in demands_per_key.items():
                    if did == demand_id and (s2, d2, p2) != dedup_key:
                        existing_key_pkt = p2
                        break
                kind = RESOURCE_CONTRACT_DUPLICATE_DEMAND_ID
                diagnostics.append(ViewDiagnostic(
                    kind=kind,
                    severity=severity_for_kind(kind),
                    message=(
                        f"Duplicate demand_id {demand_id}: "
                        f"span={span_id}, direction={direction}, "
                        f"packets={packet_id} vs {existing_key_pkt}."
                    ),
                    span_ids=(span_id,),
                    demand_id=demand_id,
                ))
                continue

            # Resolve requiredness
            requiredness, req_conflict = _requiredness_info(anns)

            # Build provenance
            span = span_by_id.get(span_id)
            evidence_text = span.text if span else ""

            source_section_id: str | None = None
            source_packet_id: str | None = None
            source_hint_ids: list[str] = []
            for a in anns:
                if a.source_section_id and not source_section_id:
                    source_section_id = a.source_section_id
                if a.source_packet_id and not source_packet_id:
                    source_packet_id = a.source_packet_id
                for hid in a.source_hint_ids:
                    if hid not in source_hint_ids:
                        source_hint_ids.append(hid)

            route_ann_ids = [a.span_id for a in anns]
            view_status: str = "valid"

            # Emit requiredness diagnostics
            if req_conflict:
                view_status = "invalid_requiredness"
                kind = RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_REQUIREDNESS
                diagnostics.append(ViewDiagnostic(
                    kind=kind,
                    severity=severity_for_kind(kind),
                    message=(
                        f"Conflicting requiredness across annotations for "
                        f"span {span_id} (demand {demand_id})."
                    ),
                    span_ids=(span_id,),
                    demand_id=demand_id,
                ))
            elif requiredness == "unspecified":
                # Genuinely missing — demand kept, diagnostic emitted
                kind = RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS
                diagnostics.append(ViewDiagnostic(
                    kind=kind,
                    severity=severity_for_kind(kind),
                    message=(
                        f"Requiredness is unspecified for demand "
                        f"{demand_id} (span {span_id})."
                    ),
                    span_ids=(span_id,),
                    demand_id=demand_id,
                ))

            demand = DemandViewDemand(
                demand_id=demand_id,
                direction=direction,
                requiredness=requiredness,
                required=_required_bool(requiredness),
                evidence_text=evidence_text,
                source_span_ids=(span_id,),
                source_section_id=source_section_id,
                source_packet_id=source_packet_id,
                source_hint_ids=tuple(source_hint_ids),
                route_annotation_ids=tuple(route_ann_ids),
                evidence_source="stage2_annotation",
                view_status=view_status,  # type: ignore[arg-type]
            )
            demands[demand_id] = demand
            demands_per_key[dedup_key] = demand_id

        # ── No-direction diagnostics ───────────────────────────────────
        for span_id in sorted(spans_without_direction):
            anns_for_span = [a for a in contract_anns if a.span_id == span_id]
            kind = RESOURCE_CONTRACT_ANNOTATION_MISSING_DIRECTION
            diagnostics.append(ViewDiagnostic(
                kind=kind,
                severity=severity_for_kind(kind),
                message=(
                    f"No direction could be resolved from resource contract "
                    f"annotations for span {span_id}. "
                    f"semantic_role must be input_contract or output_contract."
                ),
                span_ids=(span_id,),
            ))
            # Also check requiredness gap (only genuinely missing, not conflict)
            rq, rq_conflict = _requiredness_info(anns_for_span)
            if rq_conflict:
                kind2 = RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_REQUIREDNESS
                diagnostics.append(ViewDiagnostic(
                    kind=kind2,
                    severity=severity_for_kind(kind2),
                    message=(
                        f"Conflicting requiredness on annotations for "
                        f"span {span_id} (direction also missing)."
                    ),
                    span_ids=(span_id,),
                ))
            elif rq == "unspecified":
                kind2 = RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS
                diagnostics.append(ViewDiagnostic(
                    kind=kind2,
                    severity=severity_for_kind(kind2),
                    message=(
                        f"Requiredness is unspecified for resource contract "
                        f"annotations on span {span_id}."
                    ),
                    span_ids=(span_id,),
                ))

        # Sort by demand_id for determinism
        sorted_demands = sorted(demands.values(), key=lambda d: d.demand_id)

        return ResourceContractDemandView(
            demands=tuple(sorted_demands),
            view_diagnostics=tuple(
                sorted(diagnostics, key=lambda d: (d.kind, d.demand_id or ""))
            ),
        )

    # ── annotation selection ──────────────────────────────────────────────

    @staticmethod
    def _select_contract_annotations(
        routes: FieldRouteIR,
    ) -> list[RouteAnnotation]:
        """Return explicit resource contract annotations.

        DemandView existence is authorized only by Stage 2's explicit
        ``input_contract`` / ``output_contract`` semantic roles.  Other
        fields such as ``route_family``, ``construct_target``, and
        ``slot_target`` are consistency signals once an annotation is selected;
        they must not independently create a resource contract demand.
        """
        return [
            ann for ann in routes.annotations
            if ann.semantic_role in _CONTRACT_ROLES
        ]
