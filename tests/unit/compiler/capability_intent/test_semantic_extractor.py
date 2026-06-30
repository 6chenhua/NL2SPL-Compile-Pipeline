from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from nl2spl.compiler.capability_intent.model import EarlyCapabilityEvidenceView
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.capability_semantic_extractor import (
    ExternalCapabilitySemanticExtractor,
)


@dataclass
class FakeClient:
    payload: dict

    def __post_init__(self) -> None:
        self.calls: list[dict] = []
        self.config = SimpleNamespace(
            model="test-model",
            max_tokens=4096,
            temperature=0.0,
            base_url="https://example.invalid",
        )

    def call_json(self, **kwargs: object) -> dict:
        self.calls.append(kwargs)
        return self.payload


def _named_payload() -> dict:
    return {
        "candidates": [
            {
                "source_span_ids": ["s2"],
                "operation_surface": "retrieve the record",
                "capability_surface": "RecordsAPI",
                "capability_ref_candidate": "RecordsAPI",
                "boundary_claim": "external",
                "identity_claim": "explicit_name",
                "invocation_claim": "executable",
                "evidence": [
                    {
                        "source_span_id": "s2",
                        "claim": "operation",
                        "surface_text": "retrieve the record",
                        "relation": "direct",
                    },
                    {
                        "source_span_id": "s2",
                        "claim": "boundary",
                        "surface_text": "RecordsAPI",
                        "relation": "direct",
                    },
                    {
                        "source_span_id": "s2",
                        "claim": "identity",
                        "surface_text": "RecordsAPI",
                        "relation": "direct",
                    },
                    {
                        "source_span_id": "s2",
                        "claim": "invocation",
                        "surface_text": "retrieve the record",
                        "relation": "direct",
                    },
                ],
            }
        ],
        "dispositions": [
            {
                "source_span_id": "s1",
                "status": "no_external_boundary",
                "reason_code": "internal_validation",
            }
        ],
    }


def test_extractor_scans_all_spans_and_emits_validated_candidate() -> None:
    client = FakeClient(_named_payload())
    extractor = ExternalCapabilitySemanticExtractor(client)
    spans = [
        SpanIR(span_id="s1", text="Validate the request internally."),
        SpanIR(span_id="s2", text="Use RecordsAPI to retrieve the record."),
    ]

    result = extractor.extract(
        spans,
        FieldRouteIR(behavior=["s1", "s2"], integrations=[]),
        EarlyCapabilityEvidenceView(),
    )

    assert result.status == "available"
    assert len(client.calls) == 1
    assert len(result.candidates) == 1
    assert result.candidates[0].operation_text == "retrieve the record"
    assert {item.source_span_id for item in result.dispositions} == {"s1", "s2"}
    assert result.metadata["coverage_policy"] == "all_resolved_spans"
    assert len(result.metadata["model_config_fingerprint"]) == 64


def test_hallucinated_surface_is_rejected_not_repaired() -> None:
    payload = _named_payload()
    payload["candidates"][0]["capability_surface"] = "InventedAPI"
    client = FakeClient(payload)

    result = ExternalCapabilitySemanticExtractor(client).extract(
        [SpanIR(span_id="s2", text="Use RecordsAPI to retrieve the record.")],
        FieldRouteIR(),
        EarlyCapabilityEvidenceView(),
    )

    assert result.status == "available"
    assert result.candidates == ()
    assert result.diagnostics[0].kind == "capability_intent_candidate_invalid"
    assert result.dispositions[0].status == "insufficient_evidence"


def test_schema_failure_is_explicitly_unavailable() -> None:
    client = FakeClient({"candidates": [], "dispositions": [], "extra": True})

    result = ExternalCapabilitySemanticExtractor(client).extract(
        [SpanIR(span_id="s1", text="Validate internally.")],
        FieldRouteIR(),
        EarlyCapabilityEvidenceView(),
    )

    assert result.status == "unavailable"
    assert result.failure_reason is not None
    assert result.candidates == ()
    assert "unknown capability payload fields" in result.failure_reason


def test_llm_failure_is_not_misreported_as_no_intent() -> None:
    class FailingClient(FakeClient):
        def call_json(self, **kwargs: object) -> dict:
            raise RuntimeError("service unavailable")

    result = ExternalCapabilitySemanticExtractor(FailingClient({})).extract(
        [SpanIR(span_id="s1", text="Use RecordsAPI.")],
        FieldRouteIR(),
        EarlyCapabilityEvidenceView(),
    )

    assert result.status == "unavailable"
    assert result.failure_reason == "RuntimeError: service unavailable"
