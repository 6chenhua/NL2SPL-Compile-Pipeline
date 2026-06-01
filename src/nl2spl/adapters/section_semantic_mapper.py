from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from nl2spl.canonical import AdapterWarning, RawSection, SemanticPacket
from nl2spl.llm.prompts import load_prompt


@dataclass
class RoutePrior:
    """Weak semantic prior produced from structural evidence.

    RoutePrior is not an authoritative route. Stage 2 validates and converts
    accepted priors into RouteAnnotation objects.
    """

    section_id: str
    suggested_field: str
    suggested_semantic_role: str
    strength: Literal["weak", "medium", "strong"]
    evidence: str
    source: Literal["llm", "heuristic"] = "llm"
    packet_id: str | None = None
    span_hint_id: str | None = None


class SectionSemanticMapper:
    """Produce evidence-bound route priors via LLM.

    With no LLM client, exact canonical section titles produce weak
    compatibility priors. The structural adapter still preserves all shape
    evidence as neutral packets.
    """

    ALLOWED_FIELDS = {"behavior", "rules", "domain", "resources", "integrations"}
    ALLOWED_ROLES = {
        "process_step",
        "failure_mode",
        "delegation_intent",
        "input_contract",
        "output_contract",
        "policy",
        "task_family",
        "exception_handler_action",
    }
    ALLOWED_STRENGTHS = {"weak", "medium", "strong"}
    EXACT_TITLE_PRIORS: dict[str, tuple[str, str]] = {
        "task family": ("domain", "task_family"),
        "inputs for each run": ("resources", "input_contract"),
        "required outputs": ("resources", "output_contract"),
        "reusable process": ("behavior", "process_step"),
        "policies": ("rules", "policy"),
        "failure handling": ("behavior", "failure_mode"),
        "delegation policy": ("behavior", "delegation_intent"),
    }

    def __init__(self, llm_client: Any | None = None) -> None:
        self.client = llm_client

    def map_sections(
        self,
        sections: list[RawSection],
        packets: list[SemanticPacket] | None = None,
    ) -> tuple[list[RoutePrior], list[AdapterWarning]]:
        """Map sections/packets to weak semantic priors."""
        if not self.client:
            return self._exact_title_priors(sections), []

        packets = packets or []
        valid_section_ids = {s.section_id for s in sections}
        valid_packet_ids = {p.packet_id for p in packets}
        packets_by_section: dict[str, list[dict[str, str]]] = {}
        for packet in packets:
            packets_by_section.setdefault(packet.source_section_id, []).append({
                "packet_id": packet.packet_id,
                "packet_type": packet.packet_type,
                "text": packet.text,
            })

        sections_data = [
            {
                "section_id": section.section_id,
                "title": section.original_title,
                "text_preview": section.text[:200],
                "packets": packets_by_section.get(section.section_id, []),
            }
            for section in sections
        ]

        warnings: list[AdapterWarning] = []
        try:
            result = self.client.call_json(
                stage_name="section_semantic_mapper",
                system_prompt=load_prompt("stage0_section_mapper"),
                user_prompt=json.dumps({"sections": sections_data}, ensure_ascii=False),
            )
        except Exception as exc:
            warnings.append(
                AdapterWarning(
                    code="llm_semantic_mapping_failed",
                    message=(
                        f"SectionSemanticMapper LLM call failed: {exc}; "
                        "no route priors produced."
                    ),
                    severity="warning",
                )
            )
            return [], warnings

        priors: list[RoutePrior] = []
        for raw in result.get("priors", []) or []:
            section_id = raw.get("section_id")
            field = raw.get("suggested_field")
            role = raw.get("suggested_semantic_role")
            strength = raw.get("strength", "weak")
            evidence = raw.get("evidence")
            packet_id = raw.get("packet_id")

            if section_id not in valid_section_ids:
                warnings.append(AdapterWarning("invalid_prior_section", f"Invalid section_id: {section_id}"))
                continue
            if packet_id and packet_id not in valid_packet_ids:
                warnings.append(AdapterWarning("invalid_prior_packet", f"Invalid packet_id: {packet_id}"))
                continue
            if field not in self.ALLOWED_FIELDS:
                warnings.append(AdapterWarning("invalid_prior_field", f"Invalid field: {field}"))
                continue
            if role not in self.ALLOWED_ROLES:
                warnings.append(AdapterWarning("invalid_prior_role", f"Invalid role: {role}"))
                continue
            if strength not in self.ALLOWED_STRENGTHS:
                warnings.append(AdapterWarning("invalid_prior_strength", f"Invalid strength: {strength}"))
                continue
            if not isinstance(evidence, str) or not evidence.strip():
                warnings.append(AdapterWarning("invalid_prior_evidence", "Missing or empty evidence"))
                continue

            priors.append(
                RoutePrior(
                    section_id=section_id,
                    suggested_field=field,
                    suggested_semantic_role=role,
                    strength=strength,
                    evidence=evidence,
                    source="llm",
                    packet_id=packet_id,
                    span_hint_id=raw.get("span_hint_id"),
                )
            )

        return priors, warnings

    @classmethod
    def _exact_title_priors(cls, sections: list[RawSection]) -> list[RoutePrior]:
        """Compatibility priors for exact canonical structural titles only."""
        priors: list[RoutePrior] = []
        for section in sections:
            key = section.canonical_title.replace("_", " ").strip().lower()
            mapping = cls.EXACT_TITLE_PRIORS.get(key)
            if mapping is None:
                continue
            field, role = mapping
            priors.append(
                RoutePrior(
                    section_id=section.section_id,
                    suggested_field=field,
                    suggested_semantic_role=role,
                    strength="weak",
                    evidence=f"exact_title:{section.original_title}",
                    source="heuristic",
                )
            )
        return priors
