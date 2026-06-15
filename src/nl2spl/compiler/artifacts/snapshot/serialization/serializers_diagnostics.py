"""Serializers for diagnostics artifacts.

Critical constraint: ``CompileDiagnostic.metadata["irs_ref"]`` MUST
round-trip through ``DiagnosticIRSRef.to_dict()`` / ``from_dict()``.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.artifacts.snapshot.serialization.protocol import (
    ArtifactSerializer,
)
from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    SerializerRegistry,
)
from nl2spl.ir.diagnostics import (
    CompileDiagnostic,
    DiagnosticIRSRef,
    TraceRecord,
)

# Sentinel for distinguishing "no key" from "key with None value"
_IRS_REF_KEY = "irs_ref"


class DiagnosticIRSRefSerializer(ArtifactSerializer):
    type_id = "DiagnosticIRSRef"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        ref: DiagnosticIRSRef = obj
        result = ref.to_dict()
        result["$type"] = self.type_id
        return result

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return DiagnosticIRSRef.from_dict(data)


class CompileDiagnosticSerializer(ArtifactSerializer):
    type_id = "CompileDiagnostic"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        d: CompileDiagnostic = obj
        # Canonicalise metadata: DiagnosticIRSRef -> dict via to_dict()
        meta = dict(d.metadata) if d.metadata else {}
        if _IRS_REF_KEY in meta:
            irs_ref = meta[_IRS_REF_KEY]
            if isinstance(irs_ref, DiagnosticIRSRef):
                meta[_IRS_REF_KEY] = irs_ref.to_dict()

        result: dict[str, Any] = {
            "$type": self.type_id,
            "diagnostic_id": d.diagnostic_id,
            "kind": d.kind,
            "severity": d.severity,
            "message": d.message,
            "target_ref": d.target_ref,
            "source_span_ids": d.source_span_ids,
            "source_section_id": d.source_section_id,
            "source_packet_id": d.source_packet_id,
            "suggested_resolution": d.suggested_resolution,
            "metadata": meta,
            "blocks_rendering": d.blocks_rendering,
            "blocks_completion": d.blocks_completion,
        }

        # missing_slot — optional nested type
        if d.missing_slot is not None:
            result["missing_slot"] = {
                "slot_name": d.missing_slot.slot_name,
                "required_for": d.missing_slot.required_for,
                "reason": d.missing_slot.reason,
                "source_span_ids": d.missing_slot.source_span_ids,
                "suggested_question": d.missing_slot.suggested_question,
            }
        else:
            result["missing_slot"] = None

        return result

    def from_canonical(self, data: dict[str, Any]) -> Any:
        # Restore metadata: irs_ref dict -> DiagnosticIRSRef
        meta = dict(data.get("metadata", {}))
        if _IRS_REF_KEY in meta and isinstance(meta[_IRS_REF_KEY], dict):
            meta[_IRS_REF_KEY] = DiagnosticIRSRef.from_dict(meta[_IRS_REF_KEY])

        # Restore missing_slot if present
        missing_slot = None
        ms_data = data.get("missing_slot")
        if ms_data is not None and isinstance(ms_data, dict):
            from nl2spl.compiler.compile_result import MissingSlot

            missing_slot = MissingSlot(
                slot_name=ms_data["slot_name"],
                required_for=ms_data["required_for"],
                reason=ms_data["reason"],
                source_span_ids=ms_data.get("source_span_ids", []),
                suggested_question=ms_data.get("suggested_question"),
            )

        return CompileDiagnostic(
            diagnostic_id=data["diagnostic_id"],
            kind=data["kind"],
            severity=data["severity"],
            message=data["message"],
            target_ref=data.get("target_ref"),
            source_span_ids=data.get("source_span_ids", []),
            source_section_id=data.get("source_section_id"),
            source_packet_id=data.get("source_packet_id"),
            suggested_resolution=data.get("suggested_resolution"),
            missing_slot=missing_slot,
            metadata=meta,
            blocks_rendering=data.get("blocks_rendering", False),
            blocks_completion=data.get("blocks_completion", True),
        )


class TraceRecordSerializer(ArtifactSerializer):
    type_id = "TraceRecord"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        t: TraceRecord = obj
        result: dict[str, Any] = {
            "$type": self.type_id,
            "target_ref": t.target_ref,
            "source_span_ids": t.source_span_ids,
            "source_section_id": t.source_section_id,
            "source_packet_id": t.source_packet_id,
            "relation": t.relation,
            "explanation": t.explanation,
            "needs_confirmation": t.needs_confirmation,
        }
        if t.metadata:
            result["metadata"] = t.metadata
        return result

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return TraceRecord(
            target_ref=data["target_ref"],
            source_span_ids=data.get("source_span_ids", []),
            source_section_id=data.get("source_section_id"),
            source_packet_id=data.get("source_packet_id"),
            relation=data.get("relation", "direct"),
            explanation=data.get("explanation", ""),
            needs_confirmation=data.get("needs_confirmation", False),
            metadata=data.get("metadata", {}),
        )


def register_all(registry: SerializerRegistry) -> None:
    s1 = DiagnosticIRSRefSerializer()
    s2 = CompileDiagnosticSerializer()
    s3 = TraceRecordSerializer()
    registry.register(s1)
    registry.register(s2)
    registry.register(s3)
    registry.register_for_class(DiagnosticIRSRef, s1)
    registry.register_for_class(CompileDiagnostic, s2)
    registry.register_for_class(TraceRecord, s3)
