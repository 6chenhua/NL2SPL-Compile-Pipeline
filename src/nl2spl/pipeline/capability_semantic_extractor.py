"""Versioned Phase-B external capability semantic extractor."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

from nl2spl.compiler.capability_intent.candidate_validator import (
    SCHEMA_VERSION,
    ExternalCapabilityCandidateValidator,
)
from nl2spl.compiler.capability_intent.model import (
    EarlyCapabilityEvidenceView,
    ExternalCapabilityExtractionResult,
)
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.llm.prompts import load_prompt

STAGE_NAME = "external_capability_semantic_extractor"
PROMPT_VERSION = "external-capability-semantic-extractor.v1"


class ExternalCapabilitySemanticExtractor:
    """One LLM structured call followed by strict programmatic validation."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.validator = ExternalCapabilityCandidateValidator()

    def extract(
        self,
        spans: Iterable[SpanIR],
        routes: FieldRouteIR,
        early_evidence: EarlyCapabilityEvidenceView,
    ) -> ExternalCapabilityExtractionResult:
        resolved_spans = tuple(spans)
        system_prompt = load_prompt(STAGE_NAME)
        fingerprint = self._fingerprint(system_prompt)
        metadata = {
            "stage_name": STAGE_NAME,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "model_config_fingerprint": fingerprint,
            "resolved_span_count": len(resolved_spans),
            "coverage_policy": "all_resolved_spans",
        }
        user_prompt = self._user_prompt(resolved_spans, routes, early_evidence)
        try:
            payload = self.client.call_json(
                stage_name=STAGE_NAME,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            validated = self.validator.validate(payload, resolved_spans, early_evidence)
        except Exception as exc:
            return ExternalCapabilityExtractionResult(
                status="unavailable",
                failure_reason=f"{type(exc).__name__}: {exc}",
                metadata={**metadata, "failure_kind": type(exc).__name__},
            )
        return ExternalCapabilityExtractionResult(
            candidates=validated.candidates,
            dispositions=validated.dispositions,
            diagnostics=validated.diagnostics,
            status="available",
            metadata=metadata,
        )

    def _user_prompt(
        self,
        spans: tuple[SpanIR, ...],
        routes: FieldRouteIR,
        early_evidence: EarlyCapabilityEvidenceView,
    ) -> str:
        span_payload = [span.to_dict() for span in spans]
        context = {
            "route_annotations": [asdict(item) for item in routes.annotations],
            "early_evidence": early_evidence.to_payload(),
        }
        return (
            "Inspect every resolved span. Structured routes and early evidence "
            "are non-authoritative context only.\n\nResolved spans:\n"
            + json.dumps(span_payload, ensure_ascii=False, indent=2)
            + "\n\nNon-authoritative context:\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
            + "\n\nReturn the required JSON object."
        )

    def _fingerprint(self, system_prompt: str) -> str:
        config = getattr(self.client, "config", None)
        config_payload = {
            "model": _fingerprint_value(getattr(config, "model", None)),
            "max_tokens": _fingerprint_value(getattr(config, "max_tokens", None)),
            "temperature": _fingerprint_value(getattr(config, "temperature", None)),
            "base_url": _fingerprint_value(getattr(config, "base_url", None)),
            "prompt_sha256": hashlib.sha256(
                system_prompt.encode("utf-8")
            ).hexdigest(),
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
        }
        canonical = json.dumps(config_payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fingerprint_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return repr(value)
