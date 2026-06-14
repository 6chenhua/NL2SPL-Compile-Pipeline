"""Serializers for source-layer artifacts: SpanIR, FieldRouteIR, CanonicalCompileInput."""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.artifacts.snapshot.serialization.protocol import (
    ArtifactSerializer,
)
from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    SerializerRegistry,
)
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation, StructuralPrior
from nl2spl.ir.span_ir import AmbiguityInfo, SpanIR

# ===================================================================
# SpanIR
# ===================================================================


class AmbiguityInfoSerializer(ArtifactSerializer):
    type_id = "AmbiguityInfo"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        a: AmbiguityInfo = obj
        return {
            "$type": self.type_id,
            "is_ambiguous": a.is_ambiguous,
            "reasons": a.reasons,
            "needs_split": a.needs_split,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return AmbiguityInfo(
            is_ambiguous=data.get("is_ambiguous", False),
            reasons=data.get("reasons", []),
            needs_split=data.get("needs_split", False),
        )


class SpanIRSerializer(ArtifactSerializer):
    type_id = "SpanIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        s: SpanIR = obj
        amb_ser = AmbiguityInfoSerializer()
        return {
            "$type": self.type_id,
            "span_id": s.span_id,
            "text": s.text,
            "ambiguity": amb_ser.to_canonical(s.ambiguity),
            "source_section_id": s.source_section_id,
            "source_packet_id": s.source_packet_id,
            "section_context": s.section_context,
            "is_placeholder": s.is_placeholder,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        amb_ser = AmbiguityInfoSerializer()
        return SpanIR(
            span_id=data["span_id"],
            text=data["text"],
            ambiguity=amb_ser.from_canonical(data.get("ambiguity", {})),
            source_section_id=data.get("source_section_id"),
            source_packet_id=data.get("source_packet_id"),
            section_context=data.get("section_context"),
            is_placeholder=data.get("is_placeholder", False),
        )


# ===================================================================
# FieldRouteIR
# ===================================================================


class RouteAnnotationSerializer(ArtifactSerializer):
    type_id = "RouteAnnotation"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        a: RouteAnnotation = obj
        return {
            "$type": self.type_id,
            "span_id": a.span_id,
            "field": a.field,
            "semantic_role": a.semantic_role,
            "route_family": a.route_family,
            "source_section_id": a.source_section_id,
            "source_packet_id": a.source_packet_id,
            "source_hint_ids": a.source_hint_ids,
            "construct_target": a.construct_target,
            "slot_target": a.slot_target,
            "executable": a.executable,
            "primary": a.primary,
            "diagnostics": a.diagnostics,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return RouteAnnotation(
            span_id=data["span_id"],
            field=data.get("field", ""),
            semantic_role=data.get("semantic_role", ""),
            route_family=data.get("route_family", "flow_relevant"),
            source_section_id=data.get("source_section_id"),
            source_packet_id=data.get("source_packet_id"),
            source_hint_ids=data.get("source_hint_ids", []),
            construct_target=data.get("construct_target"),
            slot_target=data.get("slot_target"),
            executable=data.get("executable", False),
            primary=data.get("primary", False),
            diagnostics=data.get("diagnostics", []),
        )


class StructuralPriorSerializer(ArtifactSerializer):
    type_id = "StructuralPrior"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        s: StructuralPrior = obj
        return {
            "$type": self.type_id,
            "span_id": s.span_id,
            "suggested_field": s.suggested_field,
            "source_section_id": s.source_section_id,
            "source_packet_id": s.source_packet_id,
            "source_hint_ids": s.source_hint_ids,
            "prior_kind": s.prior_kind,
            "confidence": s.confidence,
            "reason": s.reason,
            "packet_type": s.packet_type,
            "section_title": s.section_title,
            "structural_tags": s.structural_tags,
            "metadata": s.metadata,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return StructuralPrior(
            span_id=data["span_id"],
            suggested_field=data.get("suggested_field"),
            source_section_id=data.get("source_section_id"),
            source_packet_id=data.get("source_packet_id"),
            source_hint_ids=data.get("source_hint_ids", []),
            prior_kind=data.get("prior_kind", "neutral_context"),
            confidence=data.get("confidence", "context"),
            reason=data.get("reason"),
            packet_type=data.get("packet_type"),
            section_title=data.get("section_title"),
            structural_tags=data.get("structural_tags", []),
            metadata=data.get("metadata", {}),
        )


class FieldRouteIRSerializer(ArtifactSerializer):
    type_id = "FieldRouteIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        r: FieldRouteIR = obj
        ann_ser = RouteAnnotationSerializer()
        sp_ser = StructuralPriorSerializer()
        return {
            "$type": self.type_id,
            "identity": r.identity,
            "audience": r.audience,
            "rules": r.rules,
            "domain": r.domain,
            "integrations": r.integrations,
            "behavior": r.behavior,
            "annotations": [ann_ser.to_canonical(a) for a in r.annotations],
            "structural_priors": [sp_ser.to_canonical(s) for s in r.structural_priors],
            "route_diagnostics": r.route_diagnostics,
            "structured_route_diagnostics": r.structured_route_diagnostics,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        ann_ser = RouteAnnotationSerializer()
        sp_ser = StructuralPriorSerializer()
        return FieldRouteIR(
            identity=data.get("identity", []),
            audience=data.get("audience", []),
            rules=data.get("rules", []),
            domain=data.get("domain", []),
            integrations=data.get("integrations", []),
            behavior=data.get("behavior", []),
            annotations=[ann_ser.from_canonical(a) for a in data.get("annotations", [])],
            structural_priors=[
                sp_ser.from_canonical(s) for s in data.get("structural_priors", [])
            ],
            route_diagnostics=data.get("route_diagnostics", []),
            structured_route_diagnostics=data.get("structured_route_diagnostics", []),
        )


# ===================================================================
# CanonicalCompileInput
# ===================================================================


class CanonicalCompileInputSerializer(ArtifactSerializer):
    type_id = "CanonicalCompileInput"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        from nl2spl.canonical.compile_input import CanonicalCompileInput

        c: CanonicalCompileInput = obj
        return {
            "$type": self.type_id,
            "source_schema": c.source_schema,
            "schema_version": c.schema_version,
            "raw_text": c.raw_text,
            "raw_sections": [_raw_section_to_canonical(sec) for sec in c.raw_sections],
            "semantic_packets": [
                _semantic_packet_to_canonical(packet)
                for packet in c.semantic_packets
            ],
            "hard_facts": _hard_facts_to_canonical(c.hard_facts),
            "compile_hints": _compile_hints_to_canonical(c.compile_hints),
            "warnings": [_adapter_warning_to_canonical(w) for w in c.warnings],
            "detection": (
                _detection_to_canonical(c.detection)
                if c.detection is not None
                else None
            ),
            "route_priors": [_json_safe_route_prior(p) for p in c.route_priors],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        from nl2spl.canonical.compile_input import (
            AdapterDetectionResult,
            AdapterWarning,
            CanonicalCompileInput,
            CompileHint,
            CompileHints,
            DelegationIntentFact,
            EvidenceRef,
            HardFacts,
            RawSection,
            SemanticPacket,
            VariableFact,
        )

        return CanonicalCompileInput(
            source_schema=data.get("source_schema", "generic_nl"),
            schema_version=data.get("schema_version", "1.0"),
            raw_text=data["raw_text"],
            raw_sections=[
                RawSection(
                    section_id=sec["section_id"],
                    canonical_title=sec.get("canonical_title", ""),
                    original_title=sec.get("original_title", ""),
                    text=sec.get("text", ""),
                    order=sec.get("order", 0),
                    start_offset=sec.get("start_offset"),
                    end_offset=sec.get("end_offset"),
                    structure_type=sec.get("structure_type", "paragraph"),
                    list_items=sec.get("list_items"),
                )
                for sec in data.get("raw_sections", [])
            ],
            semantic_packets=[
                SemanticPacket(
                    packet_id=p["packet_id"],
                    source_section_id=p.get("source_section_id", ""),
                    packet_type=p.get("packet_type", "info"),
                    text=p.get("text", ""),
                    modality=p.get("modality", "hint"),
                    compile_targets=p.get("compile_targets", []),
                    suggested_name=p.get("suggested_name"),
                    required=p.get("required"),
                    metadata=p.get("metadata", {}),
                )
                for p in data.get("semantic_packets", [])
            ],
            hard_facts=_hard_facts_from_canonical(
                data.get("hard_facts") or {},
                HardFacts,
                VariableFact,
                DelegationIntentFact,
                EvidenceRef,
            ),
            compile_hints=_compile_hints_from_canonical(
                data.get("compile_hints") or {},
                CompileHints,
                CompileHint,
                EvidenceRef,
            ),
            warnings=[
                AdapterWarning(**w)
                for w in data.get("warnings", [])
            ],
            detection=(
                AdapterDetectionResult(**data["detection"])
                if data.get("detection") is not None
                else None
            ),
            route_priors=data.get("route_priors", []),
        )


def _raw_section_to_canonical(sec: Any) -> dict[str, Any]:
    return {
        "section_id": sec.section_id,
        "canonical_title": sec.canonical_title,
        "original_title": sec.original_title,
        "text": sec.text,
        "order": sec.order,
        "start_offset": sec.start_offset,
        "end_offset": sec.end_offset,
        "structure_type": sec.structure_type,
        "list_items": sec.list_items,
    }


def _semantic_packet_to_canonical(packet: Any) -> dict[str, Any]:
    return {
        "packet_id": packet.packet_id,
        "source_section_id": packet.source_section_id,
        "packet_type": packet.packet_type,
        "text": packet.text,
        "modality": packet.modality,
        "compile_targets": packet.compile_targets,
        "suggested_name": packet.suggested_name,
        "required": packet.required,
        "metadata": packet.metadata,
    }


def _evidence_to_canonical(evidence: Any) -> dict[str, Any]:
    return {
        "source_section_id": evidence.source_section_id,
        "source_packet_id": evidence.source_packet_id,
        "source_span_ids": evidence.source_span_ids,
        "quoted_text": evidence.quoted_text,
    }


def _evidence_from_canonical(data: dict[str, Any], evidence_cls: type) -> Any:
    return evidence_cls(
        source_section_id=data.get("source_section_id", ""),
        source_packet_id=data.get("source_packet_id"),
        source_span_ids=data.get("source_span_ids", []),
        quoted_text=data.get("quoted_text"),
    )


def _variable_fact_to_canonical(fact: Any) -> dict[str, Any]:
    return {
        "name": fact.name,
        "description": fact.description,
        "data_type": fact.data_type,
        "required": fact.required,
        "source_section_id": fact.source_section_id,
        "evidence": [_evidence_to_canonical(e) for e in fact.evidence],
    }


def _delegation_intent_to_canonical(fact: Any) -> dict[str, Any]:
    return {
        "name": fact.name,
        "text": fact.text,
        "suggested_worker_name": fact.suggested_worker_name,
        "input_names": fact.input_names,
        "output_names": fact.output_names,
        "evidence": [_evidence_to_canonical(e) for e in fact.evidence],
    }


def _hard_facts_to_canonical(hard_facts: Any) -> dict[str, Any]:
    return {
        "inputs": [_variable_fact_to_canonical(f) for f in hard_facts.inputs],
        "outputs": [_variable_fact_to_canonical(f) for f in hard_facts.outputs],
        "delegation_intents": [
            _delegation_intent_to_canonical(f)
            for f in hard_facts.delegation_intents
        ],
    }


def _hard_facts_from_canonical(
    data: dict[str, Any],
    hard_facts_cls: type,
    variable_cls: type,
    delegation_cls: type,
    evidence_cls: type,
) -> Any:
    return hard_facts_cls(
        inputs=[
            variable_cls(
                name=f.get("name", ""),
                description=f.get("description", ""),
                data_type=f.get("data_type", ""),
                required=f.get("required", False),
                source_section_id=f.get("source_section_id", ""),
                evidence=[
                    _evidence_from_canonical(e, evidence_cls)
                    for e in f.get("evidence", [])
                ],
            )
            for f in data.get("inputs", [])
        ],
        outputs=[
            variable_cls(
                name=f.get("name", ""),
                description=f.get("description", ""),
                data_type=f.get("data_type", ""),
                required=f.get("required", False),
                source_section_id=f.get("source_section_id", ""),
                evidence=[
                    _evidence_from_canonical(e, evidence_cls)
                    for e in f.get("evidence", [])
                ],
            )
            for f in data.get("outputs", [])
        ],
        delegation_intents=[
            delegation_cls(
                name=f.get("name", ""),
                text=f.get("text", ""),
                suggested_worker_name=f.get("suggested_worker_name"),
                input_names=f.get("input_names", []),
                output_names=f.get("output_names", []),
                evidence=[
                    _evidence_from_canonical(e, evidence_cls)
                    for e in f.get("evidence", [])
                ],
            )
            for f in data.get("delegation_intents", [])
        ],
    )


_COMPILE_HINT_FIELDS: tuple[str, ...] = (
    "profile_hints",
    "process_hints",
    "constraint_hints",
    "flow_hints",
    "resource_hints",
    "delegation_hints",
)


def _compile_hint_to_canonical(hint: Any) -> dict[str, Any]:
    return {
        "source_section_id": hint.source_section_id,
        "text": hint.text,
        "target": hint.target,
        "suggested_kind": hint.suggested_kind,
        "suggested_flow": hint.suggested_flow,
        "suggested_block_type": hint.suggested_block_type,
        "suggested_step_type": hint.suggested_step_type,
        "suggested_condition": hint.suggested_condition,
        "suggested_type": hint.suggested_type,
        "suggested_worker_name": hint.suggested_worker_name,
        "evidence": [_evidence_to_canonical(e) for e in hint.evidence],
        "metadata": hint.metadata,
    }


def _compile_hints_to_canonical(hints: Any) -> dict[str, Any]:
    return {
        field_name: [
            _compile_hint_to_canonical(h)
            for h in getattr(hints, field_name)
        ]
        for field_name in _COMPILE_HINT_FIELDS
    }


def _compile_hints_from_canonical(
    data: dict[str, Any],
    hints_cls: type,
    hint_cls: type,
    evidence_cls: type,
) -> Any:
    kwargs = {}
    for field_name in _COMPILE_HINT_FIELDS:
        kwargs[field_name] = [
            hint_cls(
                source_section_id=h.get("source_section_id", ""),
                text=h.get("text", ""),
                target=h.get("target"),
                suggested_kind=h.get("suggested_kind"),
                suggested_flow=h.get("suggested_flow"),
                suggested_block_type=h.get("suggested_block_type"),
                suggested_step_type=h.get("suggested_step_type"),
                suggested_condition=h.get("suggested_condition"),
                suggested_type=h.get("suggested_type"),
                suggested_worker_name=h.get("suggested_worker_name"),
                evidence=[
                    _evidence_from_canonical(e, evidence_cls)
                    for e in h.get("evidence", [])
                ],
                metadata=h.get("metadata", {}),
            )
            for h in data.get(field_name, [])
        ]
    return hints_cls(**kwargs)


def _adapter_warning_to_canonical(warning: Any) -> dict[str, Any]:
    return {
        "code": warning.code,
        "message": warning.message,
        "source_section_id": warning.source_section_id,
        "severity": warning.severity,
    }


def _detection_to_canonical(detection: Any) -> dict[str, Any]:
    return {
        "matched": detection.matched,
        "schema_name": detection.schema_name,
        "schema_version": detection.schema_version,
        "matched_sections": detection.matched_sections,
        "missing_sections": detection.missing_sections,
        "unexpected_sections": detection.unexpected_sections,
        "duplicate_sections": detection.duplicate_sections,
        "empty_sections": detection.empty_sections,
        "parse_errors": detection.parse_errors,
    }


def _json_safe_route_prior(prior: Any) -> Any:
    if isinstance(prior, (str, int, float, bool)) or prior is None:
        return prior
    if isinstance(prior, list):
        return [_json_safe_route_prior(item) for item in prior]
    if isinstance(prior, tuple):
        return [_json_safe_route_prior(item) for item in prior]
    if isinstance(prior, dict):
        return {str(k): _json_safe_route_prior(v) for k, v in prior.items()}
    to_payload = getattr(prior, "to_payload", None)
    if callable(to_payload):
        return _json_safe_route_prior(to_payload())
    raise TypeError(f"Unsupported route prior for canonical JSON: {type(prior)!r}")


# ===================================================================
# Registration
# ===================================================================


def register_all(registry: SerializerRegistry) -> None:
    _reg = registry.register
    _cls = registry.register_for_class

    amb = AmbiguityInfoSerializer()
    span = SpanIRSerializer()
    ann = RouteAnnotationSerializer()
    sp = StructuralPriorSerializer()
    route = FieldRouteIRSerializer()
    cci = CanonicalCompileInputSerializer()

    for s in (amb, span, ann, sp, route, cci):
        _reg(s)

    _cls(AmbiguityInfo, amb)
    _cls(SpanIR, span)
    _cls(RouteAnnotation, ann)
    _cls(StructuralPrior, sp)
    _cls(FieldRouteIR, route)

    # CanonicalCompileInput may not be importable at registration time
    # (lazy import); register the class when first used.
    from nl2spl.canonical.compile_input import (  # noqa: N817
        CanonicalCompileInput,
    )

    _cls(CanonicalCompileInput, cci)
