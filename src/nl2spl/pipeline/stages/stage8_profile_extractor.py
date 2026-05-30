"""Stage 8: ProfileExtractor - Extract persona, audience, concepts."""

from __future__ import annotations

import json
from dataclasses import asdict

from nl2spl.ir.agent_profile_ir import AgentProfileIR, Aspect, Concept, PersonaIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


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
            identity_role_ids = {
                a.span_id for a in routes.annotations
                if a.semantic_role == "profile_domain"
            }
            persona_role_ids = {
                a.span_id for a in routes.annotations
                if a.semantic_role in ("identity", "persona")
            }
            for sid in identity_role_ids:
                if sid in span_by_id and sid not in routes.identity:
                    identity_spans.append(span_by_id[sid])
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
        persona = PersonaIR(
            role=self._resolve_role(raw_role, identity_spans, spans),
            aspects=[Aspect(**a) for a in persona_data.get("aspects", [])],
        )

        # 5. Parse audience
        audience_data = result.get("audience", {})
        audience_aspects = [Aspect(**a) for a in audience_data.get("aspects", [])]

        # 6. Parse concepts
        concepts = [Concept(**c) for c in result.get("concepts", [])]

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
        identity_spans: list[SpanIR],
        all_spans: list[SpanIR],
    ) -> str:
        """Return a grammar-safe, non-empty persona role."""
        generic_roles = {"", "assistant", "general assistant"}
        if raw_role.lower() not in generic_roles:
            return raw_role

        if identity_spans:
            return self._role_from_text(identity_spans[0].text)

        return self._infer_role_from_spans(all_spans)

    def _infer_role_from_spans(self, spans: list[SpanIR]) -> str:
        """Infer a role from source spans when identity content is absent."""
        for span in spans:
            text = span.text.strip()
            if ":" not in text:
                continue
            label, body = text.split(":", 1)
            if label.strip().lower() in {"task family", "task", "purpose"}:
                body = self._clean_description(body)
                if body:
                    return f"Agent specializing in {self._lowercase_first(body)}"

        for span in spans:
            text = self._clean_description(span.text)
            if any(
                keyword in text.lower()
                for keyword in ("draft", "communication", "newsletter", "brief", "artifact")
            ):
                return f"Agent responsible for {self._lowercase_first(text)}"

        if spans:
            return self._role_from_text(spans[0].text)

        return "General Assistant"

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
