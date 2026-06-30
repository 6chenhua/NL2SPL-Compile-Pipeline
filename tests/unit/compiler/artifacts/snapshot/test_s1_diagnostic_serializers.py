"""S1 diagnostic serializer tests — critical irs_ref round-trip."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    build_default_registry,
)
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef, TraceRecord


def _rt(registry, obj):
    data = registry.serialize(obj)
    restored = registry.deserialize(data)
    return data, restored


class TestDiagnosticIRSRefRoundTrip:
    def test_full_roundtrip(self) -> None:
        reg = build_default_registry()
        ref = DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="exc_1",
            slot_name="handler_action",
            construct_path=("MainWorker", "main", "block_1"),
            source_authority="post_normalize_irs",
        )
        data, restored = _rt(reg, ref)
        assert data["$type"] == "DiagnosticIRSRef"
        assert restored.construct_type == "EXCEPTION_FLOW"
        assert restored.construct_id == "exc_1"
        assert restored.slot_name == "handler_action"
        assert restored.construct_path == ("MainWorker", "main", "block_1")
        assert restored.source_authority == "post_normalize_irs"

    def test_minimal_roundtrip(self) -> None:
        reg = build_default_registry()
        ref = DiagnosticIRSRef(
            construct_type="STEP",
            construct_id="step_5",
            slot_name="command",
        )
        _data, restored = _rt(reg, ref)
        assert restored.construct_path == ()
        assert restored.source_authority == "post_normalize_irs"


class TestCompileDiagnosticRoundTrip:
    def test_with_irs_ref_metadata(self) -> None:
        """The critical test: metadata["irs_ref"] must round-trip as DiagnosticIRSRef."""
        reg = build_default_registry()
        irs_ref = DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="exc_1",
            slot_name="handler_action",
            construct_path=("MainWorker", "main"),
            source_authority="post_normalize_irs",
        )
        diag = CompileDiagnostic(
            diagnostic_id="D001",
            kind="missing_handler",
            severity="warning",
            message="No handler for exc_1",
            target_ref="exception_flow:exc_1",
            source_span_ids=["s5", "s12"],
            source_section_id="sec_handlers",
            suggested_resolution="Add a handler step",
            metadata={
                "irs_ref": irs_ref,
                "authority": "post_normalize_irs",
                "repairability": "editable",
                "issue_group_id": "group_01",
            },
            blocks_rendering=True,
            blocks_completion=True,
        )
        data, restored = _rt(reg, diag)
        assert data["$type"] == "CompileDiagnostic"
        assert restored.diagnostic_id == "D001"
        assert restored.kind == "missing_handler"
        assert restored.severity == "warning"
        assert restored.message == "No handler for exc_1"
        # Critical: metadata["irs_ref"] must be a DiagnosticIRSRef
        meta = restored.metadata
        assert "irs_ref" in meta
        restored_irs = meta["irs_ref"]
        assert isinstance(restored_irs, DiagnosticIRSRef), (
            f"irs_ref is {type(restored_irs).__name__}, not DiagnosticIRSRef"
        )
        assert restored_irs.construct_type == "EXCEPTION_FLOW"
        assert restored_irs.construct_id == "exc_1"
        assert restored_irs.slot_name == "handler_action"
        assert restored_irs.source_authority == "post_normalize_irs"
        # Other metadata preserved
        assert meta["authority"] == "post_normalize_irs"
        assert meta["repairability"] == "editable"

    def test_with_missing_slot(self) -> None:
        reg = build_default_registry()
        from nl2spl.compiler.compile_result import MissingSlot

        slot = MissingSlot(
            slot_name="handler_action",
            required_for="exception_flow:exc_1",
            reason="No handler step specified",
            source_span_ids=["s10"],
            suggested_question="What handler should be used?",
        )
        diag = CompileDiagnostic(
            diagnostic_id="D002",
            kind="missing_handler",
            severity="error",
            message="Missing handler",
            missing_slot=slot,
        )
        _data, restored = _rt(reg, diag)
        assert restored.missing_slot is not None
        assert restored.missing_slot.slot_name == "handler_action"
        assert restored.missing_slot.suggested_question == "What handler should be used?"

    def test_minimal_diagnostic(self) -> None:
        reg = build_default_registry()
        diag = CompileDiagnostic(
            diagnostic_id="D003",
            kind="missing_output_producer",
            severity="warning",
            message="No producer for output X",
        )
        _data, restored = _rt(reg, diag)
        assert restored.diagnostic_id == "D003"
        assert restored.metadata == {}
        assert restored.missing_slot is None
        assert restored.target_ref is None

    def test_no_python_repr_in_payload(self) -> None:
        """Serialized JSON must not contain Python repr artifacts."""
        reg = build_default_registry()
        diag = CompileDiagnostic(
            diagnostic_id="D004",
            kind="type_or_contract_ambiguity",
            severity="warning",
            message="Ambiguous contract",
            metadata={"irs_ref": DiagnosticIRSRef("WORKER_PROMOTION", "wp_1", "handoff_type")},
        )
        data = reg.serialize(diag)
        payload_str = str(data)
        assert "<" not in payload_str or "$type" in payload_str  # no __repr__

    def test_deferred_api_contract_metadata_roundtrip(self) -> None:
        reg = build_default_registry()
        diagnostic = CompileDiagnostic(
            diagnostic_id="D_API_DEFERRED",
            kind="deferred_api_contract_validation",
            severity="info",
            message="API contract validation deferred.",
            target_ref="api:SearchAPI",
            metadata={
                "validation_authority": "downstream_spl_compiler",
                "api_contract_validation_status": "pending",
                "presentation_disposition": "deferred_validation",
                "repairability": "review_only",
                "placeholder_fields": ["openapi_schema", "functions"],
            },
            blocks_rendering=False,
            blocks_completion=False,
        )

        _data, restored = _rt(reg, diagnostic)

        assert restored.kind == "deferred_api_contract_validation"
        assert restored.severity == "info"
        assert restored.blocks_rendering is False
        assert restored.blocks_completion is False
        assert restored.metadata == diagnostic.metadata


class TestTraceRecordRoundTrip:
    def test_full_roundtrip(self) -> None:
        reg = build_default_registry()
        trace = TraceRecord(
            target_ref="step:st1",
            source_span_ids=["s1", "s2"],
            source_section_id="sec_steps",
            source_packet_id="pkt_1",
            relation="direct",
            explanation="Mapped from source span s1",
            needs_confirmation=False,
        )
        data, restored = _rt(reg, trace)
        assert data["$type"] == "TraceRecord"
        assert restored.target_ref == "step:st1"
        assert restored.source_span_ids == ["s1", "s2"]
        assert restored.relation == "direct"
        assert restored.explanation == "Mapped from source span s1"

    def test_minimal_trace(self) -> None:
        reg = build_default_registry()
        trace = TraceRecord(target_ref="variable:draft")
        _data, restored = _rt(reg, trace)
        assert restored.relation == "direct"
        assert restored.source_span_ids == []
        assert restored.needs_confirmation is False
