"""Stage 8: ProfileExtractor - Extract persona, audience, concepts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from nl2spl.ir.agent_profile_ir import AgentProfileIR, Aspect, Concept, PersonaIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


@dataclass(frozen=True)
class _ProfileEvidence:
    source_span_ids: list[str]
    source_section_id: str | None
    source_packet_id: str | None
    relation: str


@dataclass(frozen=True)
class _ProfileValue:
    text: str
    evidence: _ProfileEvidence


class ProfileExtractor(PipelineStage[
    tuple[list[SpanIR], FieldRouteIR, SymbolTable],
    AgentProfileIR
]):
    """Extract persona, audience, and concepts from spans.

    This stage extracts agent profile information from identity,
    audience, and domain spans.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage8_profile_extractor"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR, SymbolTable]
    ) -> AgentProfileIR:
        """Execute profile extraction.

        Args:
            input_data: Tuple of (spans, routes, symbol_table)

        Returns:
            AgentProfileIR object

        Raises:
            StageError: If extraction fails
        """
        spans, routes, symbol_table = input_data
        self.logger.info("Starting profile extraction with %d spans", len(spans))

        # 1. Filter identity/audience/domain spans + annotation-driven profile
        identity_spans = [s for s in spans if s.span_id in routes.identity]
        audience_spans = [s for s in spans if s.span_id in routes.audience]
        domain_spans = [s for s in spans if s.span_id in routes.domain]

        # D5: enrich with profile annotations, routing by semantic_role
        if routes.annotations:
            span_by_id = {s.span_id: s for s in spans}
            persona_role_ids = {
                a.span_id for a in routes.annotations
                if a.semantic_role in ("identity", "persona")
            }
            for sid in persona_role_ids:
                if sid in span_by_id and sid not in routes.identity:
                    identity_spans.append(span_by_id[sid])
            domain_role_ids = {
                a.span_id for a in routes.annotations
                if a.semantic_role == "profile_domain"
            }
            for sid in domain_role_ids:
                if sid in span_by_id and sid not in routes.domain:
                    domain_spans.append(span_by_id[sid])

        self.logger.info(
            "Found %d identity, %d audience, %d domain spans",
            len(identity_spans),
            len(audience_spans),
            len(domain_spans),
        )

        # 2. Build prompt
        all_spans_json = json.dumps([s.to_dict() for s in spans], ensure_ascii=False)
        identity_json = json.dumps([s.to_dict() for s in identity_spans], ensure_ascii=False)
        audience_json = json.dumps([s.to_dict() for s in audience_spans], ensure_ascii=False)
        domain_json = json.dumps([s.to_dict() for s in domain_spans], ensure_ascii=False)
        variable_list = symbol_table.get_variable_list_for_prompt()

        system_prompt = load_prompt("stage8")

        user_prompt = f"""请从以下文本中提取 persona、audience、concepts：

all source spans：
---
{all_spans_json}
---

identity spans：
---
{identity_json}
---

audience spans：
---
{audience_json}
---

domain spans：
---
{domain_json}
---

已知变量：
---
{variable_list}
---

输出 JSON："""

        # 3. Call LLM
        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed: %s", e)
            raise

        # 4. Parse persona
        persona_data = result.get("persona", {})
        raw_role = str(persona_data.get("role") or "").strip()
        role_value = self._resolve_role(raw_role, persona_data, identity_spans, spans)
        persona = PersonaIR(
            role=role_value.text,
            aspects=[
                self._aspect_from_payload(a, identity_spans, spans, "direct")
                for a in persona_data.get("aspects", [])
                if isinstance(a, dict)
            ],
            source_span_ids=role_value.evidence.source_span_ids,
            source_section_id=role_value.evidence.source_section_id,
            source_packet_id=role_value.evidence.source_packet_id,
            provenance_relation=role_value.evidence.relation,
        )

        # 5. Parse audience
        audience_data = result.get("audience", {})
        audience_aspects = [
            self._aspect_from_payload(a, audience_spans, spans, "direct")
            for a in audience_data.get("aspects", [])
            if isinstance(a, dict)
        ]

        # 6. Parse concepts
        concepts = [
            self._concept_from_payload(c, domain_spans, spans)
            for c in result.get("concepts", [])
            if isinstance(c, dict)
        ]

        self.logger.info(
            "Extracted persona with %d aspects, %d audience aspects, %d concepts",
            len(persona.aspects),
            len(audience_aspects),
            len(concepts),
        )

        # 7. Build AgentProfileIR
        profile = AgentProfileIR(
            persona=persona,
            audience_aspects=audience_aspects,
            concepts=concepts,
        )

        # 8. Save checkpoint
        self.save_checkpoint(asdict(profile))

        return profile

    def _resolve_role(
        self,
        raw_role: str,
        persona_data: dict[str, Any],
        identity_spans: list[SpanIR],
        all_spans: list[SpanIR],
    ) -> _ProfileValue:
        """Return a grammar-safe, non-empty persona role with provenance."""
        generic_roles = {"", "assistant", "general assistant"}
        if raw_role.lower() not in generic_roles:
            evidence = self._resolve_profile_evidence(
                payload=persona_data,
                candidate_spans=identity_spans,
                all_spans=all_spans,
                value_parts=[raw_role],
                relation_with_valid_ids="direct",
            )
            return _ProfileValue(raw_role, evidence)

        if identity_spans:
            role = self._role_from_text(identity_spans[0].text)
            return _ProfileValue(
                role,
                self._evidence_from_spans([identity_spans[0]], "inferred"),
            )

        return self._infer_role_from_spans(all_spans)

    def _infer_role_from_spans(self, spans: list[SpanIR]) -> _ProfileValue:
        """Infer a role from source spans when identity content is absent."""
        for span in spans:
            text = span.text.strip()
            if ":" not in text:
                continue
            label, body = text.split(":", 1)
            if label.strip().lower() in {"task family", "task", "purpose"}:
                body = self._clean_description(body)
                if body:
                    return _ProfileValue(
                        f"Agent specializing in {self._lowercase_first(body)}",
                        self._evidence_from_spans([span], "inferred"),
                    )

        for span in spans:
            text = self._clean_description(span.text)
            if any(
                keyword in text.lower()
                for keyword in ("draft", "communication", "newsletter", "brief", "artifact")
            ):
                return _ProfileValue(
                    f"Agent responsible for {self._lowercase_first(text)}",
                    self._evidence_from_spans([span], "inferred"),
                )

        if spans:
            return _ProfileValue(
                self._role_from_text(spans[0].text),
                self._evidence_from_spans([spans[0]], "inferred"),
            )

        return _ProfileValue(
            "General Assistant",
            _ProfileEvidence([], None, None, "assumed"),
        )

    def _aspect_from_payload(
        self,
        payload: dict[str, Any],
        candidate_spans: list[SpanIR],
        all_spans: list[SpanIR],
        relation_with_valid_ids: str,
    ) -> Aspect:
        """Build an Aspect using only validated or exact-recovered evidence."""
        name = str(payload.get("name") or "").strip()
        text = str(payload.get("text") or "").strip()
        evidence = self._resolve_profile_evidence(
            payload=payload,
            candidate_spans=candidate_spans,
            all_spans=all_spans,
            value_parts=[name, text],
            relation_with_valid_ids=relation_with_valid_ids,
        )
        return Aspect(
            name=name,
            text=text,
            source_span_ids=evidence.source_span_ids,
            source_section_id=evidence.source_section_id,
            source_packet_id=evidence.source_packet_id,
            provenance_relation=evidence.relation,
        )

    def _concept_from_payload(
        self,
        payload: dict[str, Any],
        candidate_spans: list[SpanIR],
        all_spans: list[SpanIR],
    ) -> Concept:
        """Build a Concept using only validated or exact-recovered evidence."""
        term = str(payload.get("term") or "").strip()
        definition = str(payload.get("definition") or "").strip()
        evidence = self._resolve_profile_evidence(
            payload=payload,
            candidate_spans=candidate_spans,
            all_spans=all_spans,
            value_parts=[term, definition],
            relation_with_valid_ids="normalized",
        )
        return Concept(
            term=term,
            definition=definition,
            source_span_ids=evidence.source_span_ids,
            source_section_id=evidence.source_section_id,
            source_packet_id=evidence.source_packet_id,
            provenance_relation=evidence.relation,
        )

    def _resolve_profile_evidence(
        self,
        payload: dict[str, Any],
        candidate_spans: list[SpanIR],
        all_spans: list[SpanIR],
        value_parts: list[str],
        relation_with_valid_ids: str,
    ) -> _ProfileEvidence:
        """Validate LLM-provided source ids, then fall back to exact recovery.

        When route-specific candidates are absent, all-spans fallback is only
        exact/substring recovery.  It does not trust arbitrary LLM ids and it
        never upgrades unrelated source text to a direct profile relation.
        """
        raw_ids = self._payload_source_span_ids(payload)
        matched_spans = self._valid_payload_spans(
            raw_ids, candidate_spans, all_spans, value_parts
        )
        if matched_spans:
            relation = relation_with_valid_ids if candidate_spans else "normalized"
            if len(matched_spans) > 1 and relation == "normalized":
                relation = "derived"
            return self._evidence_from_spans(matched_spans, relation)

        recovery_candidates = candidate_spans if candidate_spans else all_spans
        recovered = self._recover_exact_spans(value_parts, recovery_candidates)
        if recovered:
            relation = "normalized" if len(recovered) == 1 else "derived"
            return self._evidence_from_spans(recovered, relation)

        return _ProfileEvidence([], None, None, "assumed")

    def _valid_payload_spans(
        self,
        raw_ids: list[str],
        candidate_spans: list[SpanIR],
        all_spans: list[SpanIR],
        value_parts: list[str],
    ) -> list[SpanIR]:
        if not raw_ids:
            return []
        raw_id_set = set(raw_ids)
        if candidate_spans:
            candidate_ids = {span.span_id for span in candidate_spans}
            return [
                span for span in all_spans
                if span.span_id in raw_id_set and span.span_id in candidate_ids
            ]
        return [
            span for span in all_spans
            if span.span_id in raw_id_set and self._span_matches_values(span, value_parts)
        ]

    def _payload_source_span_ids(self, payload: dict[str, Any]) -> list[str]:
        raw = payload.get("source_span_ids")
        if not isinstance(raw, list):
            return []
        seen: set[str] = set()
        span_ids: list[str] = []
        for item in raw:
            if not isinstance(item, str) or not item or item in seen:
                continue
            seen.add(item)
            span_ids.append(item)
        return span_ids

    def _recover_exact_spans(
        self,
        value_parts: list[str],
        candidate_spans: list[SpanIR],
    ) -> list[SpanIR]:
        return [
            span for span in candidate_spans
            if self._span_matches_values(span, value_parts)
        ]

    def _span_matches_values(self, span: SpanIR, value_parts: list[str]) -> bool:
        span_text = self._normalize_for_match(span.text)
        if not span_text:
            return False
        for value in value_parts:
            normalized = self._normalize_for_match(value)
            if len(normalized) < 3:
                continue
            if normalized in span_text or span_text in normalized:
                return True
        return False

    def _evidence_from_spans(
        self,
        spans: list[SpanIR],
        relation: str,
    ) -> _ProfileEvidence:
        return _ProfileEvidence(
            source_span_ids=[span.span_id for span in spans],
            source_section_id=self._shared_origin(spans, "source_section_id"),
            source_packet_id=self._shared_origin(spans, "source_packet_id"),
            relation=relation if spans else "assumed",
        )

    def _shared_origin(self, spans: list[SpanIR], attr: str) -> str | None:
        if not spans:
            return None
        values = [getattr(span, attr) for span in spans]
        first = values[0]
        if first is None:
            return None
        if all(value == first for value in values):
            return first
        return None

    def _normalize_for_match(self, text: str) -> str:
        return " ".join(str(text).lower().strip().split())

    def _role_from_text(self, text: str) -> str:
        """Create a concise role description from a source text fragment."""
        role = self._clean_description(text)
        return role or "General Assistant"

    def _clean_description(self, text: str, max_length: int = 180) -> str:
        """Normalize a source fragment for use as ROLE text."""
        cleaned = " ".join(text.strip().split()).strip(" .")
        if not cleaned:
            return ""
        if len(cleaned) > max_length:
            cleaned = cleaned[: max_length - 3].rstrip(" ,;:") + "..."
        return cleaned + "."

    def _lowercase_first(self, text: str) -> str:
        """Lowercase the first character without disturbing the rest."""
        if not text:
            return text
        return text[0].lower() + text[1:]
