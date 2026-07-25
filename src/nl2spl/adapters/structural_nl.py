"""Adapter for stable section-based natural language specifications."""

from __future__ import annotations

import re
from collections import Counter
from typing import Literal

from nl2spl.adapters.base import InputAdapter
from nl2spl.adapters.morphology import ShapeGrammar
from nl2spl.canonical.compile_input import (
    AdapterDetectionResult,
    AdapterWarning,
    CanonicalCompileInput,
    CompileHints,
    EvidenceRef,
    HardFacts,
    RawSection,
    SemanticPacket,
    VariableFact,
)

VARIABLE_NAME_ALIASES = {
    "a user request": "user_request",
    "user request": "user_request",
    "optional known topics": "known_topics",
    "known topics": "known_topics",
    "optional timeframe": "timeframe",
    "timeframe": "timeframe",
    "available connectors or source repositories": "connectors_or_source_repositories",
    "available connectors": "available_connectors",
    "source repositories": "source_repositories",
    "optional format preferences": "format_preferences",
    "format preferences": "format_preferences",
    "a draft communication artifact": "draft_communication_artifact",
    "draft communication artifact": "draft_communication_artifact",
    "a source/evidence set": "source_evidence_set",
    "source/evidence set": "source_evidence_set",
    "a source evidence set": "source_evidence_set",
    "source evidence set": "source_evidence_set",
    "a short assumptions log for any unresolved items": "assumptions_log",
    "short assumptions log for any unresolved items": "assumptions_log",
    "assumptions log": "assumptions_log",
    "a completion status": "completion_status",
    "completion status": "completion_status",
}


def _is_empty_marker(text: str) -> bool:
    """Return True when text is an explicit empty marker."""
    candidate = text.strip()
    candidate = re.sub(r"^\s*[-*+]\s+", "", candidate)
    candidate = re.sub(r"^\s*\d+\.\s+", "", candidate)
    if ":" in candidate or "\uff1a" in candidate:
        _label, candidate = re.split(r"[:\uff1a]", candidate, maxsplit=1)
    candidate = candidate.replace("**", "").replace("__", "")
    normalized = re.sub(r"[^\w\s]", "", candidate.lower()).strip()

    empty_markers = {
        "none",
        "na",
        "n a",
        "not applicable",
        "nil",
        "empty",
    }
    return normalized in empty_markers


_INPUT_TITLES = frozenset({"inputs for each run", "inputs_for_each_run"})
_OUTPUT_TITLES = frozenset({"required outputs", "required_outputs"})


def _compute_packet_required(section: RawSection, clean_text: str) -> bool | None:
    """Compute the requiredness bool for a list-item packet from structural
    section evidence.

    This is the adapter's own deterministic logic — NOT a downstream
    fallback on section titles or evidence text.  It uses the adapter's
    known section canonical_title to decide direction, then applies the
    same logic the adapter uses for hard_facts extraction.

    * Required Outputs → always ``True``
    * Inputs for each run → ``True`` unless the item text starts with
      "optional " (case-insensitive)
    * Unknown sections → ``None``
    """
    title = section.canonical_title
    if title in _OUTPUT_TITLES:
        return True
    if title in _INPUT_TITLES:
        return not clean_text.lower().startswith("optional ")
    return None


class StructuralNLAdapter(InputAdapter):
    """Parse known structural NL section headings into canonical input.

    The adapter reads structure and provenance only.  It does not call an LLM
    and does not decide open semantic roles such as process, failure, handler,
    or delegation.  The optional ``llm_client`` parameter is accepted for
    compatibility with older callers but is intentionally ignored.
    """

    name = "structural_nl"
    schema_version = "1.0"

    def __init__(
        self,
        llm_client: object | None = None,
        *,
        enable_hard_facts: bool = False,
    ) -> None:
        _ = llm_client
        self._hard_facts_enabled = enable_hard_facts

    def detect(self, raw_text: str) -> AdapterDetectionResult:
        """Detect structural_nl by section evidence."""
        sections, unexpected = self._parse_sections(raw_text)
        matched_titles = [section.original_title for section in sections]
        counts = Counter(matched_titles)
        matched_unique = list(dict.fromkeys(matched_titles))
        duplicate_sections = sorted(title for title, count in counts.items() if count > 1)
        empty_sections = [
            section.original_title
            for section in sections
            if not section.text.strip()
            and not self._is_document_title_section(section, sections, raw_text)
        ]
        missing_sections = []

        from nl2spl.adapters.morphology import StructuralShapeDetector
        profile = StructuralShapeDetector.detect(raw_text)
        matched = profile.is_highly_structured

        return AdapterDetectionResult(
            matched=matched,
            schema_name=self.name,
            schema_version=self.schema_version,
            matched_sections=matched_unique,
            missing_sections=missing_sections,
            unexpected_sections=unexpected,
            duplicate_sections=duplicate_sections,
            empty_sections=empty_sections,
            parse_errors=[],
        )

    def adapt(self, raw_text: str) -> CanonicalCompileInput:
        """Adapt structural NL into canonical compile input."""
        sections, _unexpected = self._parse_sections(raw_text)
        detection = self.detect(raw_text)
        semantic_packets: list[SemanticPacket] = []
        hard_facts = HardFacts()
        compile_hints = CompileHints()
        warnings = self._warnings_from_detection(detection)
        for section in sections:
            # Output neutral structural packets with no semantic decisions.
            if section.structure_type == "list" and section.list_items:
                for item_idx, item in enumerate(section.list_items):
                    clean = self._clean_item(item)
                    if not clean or _is_empty_marker(clean):
                        continue
                    required = _compute_packet_required(section, clean)
                    packet = self._packet(
                        "list_item", section, clean, "hint", [],
                        required=required,
                    )
                    packet.metadata.setdefault("executable", False)
                    packet.metadata["failure_item_index"] = item_idx
                    semantic_packets.append(packet)
            else:
                for text in self._split_sentences(section.text):
                    if text.strip():
                        if _is_empty_marker(text.strip()):
                            continue
                        packet = self._packet("sentence", section, text, "hint", [])
                        packet.metadata.setdefault("executable", False)
                        semantic_packets.append(packet)

            # Legacy compatibility path for exact-schema inputs and outputs.
            # Disabled by default since ResourceContractPlan took over.
            # Re-enable via PipelineConfig.enable_adapter_hard_facts = True.
            title = section.canonical_title
            if self._hard_facts_enabled:
                if title in ("inputs for each run", "inputs_for_each_run"):
                    inputs = self._extract_variables(section, source="input")
                    for fact in inputs:
                        fact.source_packet_id = f"adapter_compat_exact_schema_{fact.name}"
                    hard_facts.inputs.extend(self._merge_variable_facts(inputs, warnings))
                elif title in ("required outputs", "required_outputs"):
                    outputs = self._extract_variables(section, source="output")
                    for fact in outputs:
                        fact.source_packet_id = f"adapter_compat_exact_schema_{fact.name}"
                    hard_facts.outputs.extend(self._merge_variable_facts(outputs, warnings))

        return CanonicalCompileInput(
            source_schema=self.name,
            schema_version=self.schema_version,
            raw_text=raw_text,
            raw_sections=sections,
            semantic_packets=self._dedupe_packet_ids(semantic_packets),
            hard_facts=hard_facts,
            compile_hints=compile_hints,
            warnings=warnings,
            detection=detection,
            route_priors=[],
        )

    def _parse_sections(self, raw_text: str) -> tuple[list[RawSection], list[str]]:
        lines = raw_text.splitlines(keepends=True)
        headings: list[tuple[int, int, int, str, str, str]] = []
        unexpected: list[str] = []
        offset = 0

        for index, line in enumerate(lines):
            stripped = line.strip()
            line_start = offset
            line_end = offset + len(line)
            inline_text = ""
            previous_nonempty = next(
                (candidate.strip() for candidate in reversed(lines[:index]) if candidate.strip()),
                "",
            )
            if self._looks_like_heading(stripped):
                original_title = self._clean_heading_title(stripped)
                canonical_title = self.normalize_heading(stripped)
            elif (
                ShapeGrammar.KEY_VALUE.match(stripped)
                and not self._looks_like_heading(previous_nonempty)
                and not re.match(r"^[-*+]\s+", stripped)
                and not re.match(r"^\d+\.\s+", stripped)
            ):
                title, inline_text = re.split(r"[:\uff1a]", stripped, maxsplit=1)
                original_title = self._clean_heading_title(title)
                canonical_title = self.normalize_heading(f"{original_title}:")
                inline_text = inline_text.strip()
                # Strip leading bold markup from inline section content.
                inline_text = re.sub(r'^\*\*\s*', '', inline_text)
                inline_text = re.sub(r'^__\s*', '', inline_text)
            else:
                offset = line_end
                continue

            if canonical_title:
                headings.append(
                    (
                        index,
                        line_start,
                        line_end,
                        original_title,
                        canonical_title,
                        inline_text,
                    )
                )
            offset = line_end

        sections: list[RawSection] = []
        for order, heading in enumerate(headings):
            _index, _line_start, line_end, original_title, canonical_title, inline_text = heading
            next_start = headings[order + 1][1] if order + 1 < len(headings) else len(raw_text)
            following_text = raw_text[line_end:next_start].strip()
            text = "\n".join(part for part in [inline_text, following_text] if part).strip()
            section_id = self._section_id(canonical_title, order, headings)
            has_list = self._has_list_shape(text)
            structure_type = "list" if has_list else "paragraph"
            list_items = self._split_list_items(text) if has_list else None
            sections.append(
                RawSection(
                    section_id=section_id,
                    canonical_title=canonical_title,
                    original_title=original_title,
                    text=text,
                    order=order + 1,
                    start_offset=line_end,
                    end_offset=next_start,
                    structure_type=structure_type,
                    list_items=list_items,
                )
            )
        return sections, unexpected

    @staticmethod
    def normalize_heading(line: str) -> str:
        """Normalize a potential heading."""
        line = StructuralNLAdapter._clean_heading_title(line).lower()
        return " ".join(line.split())

    @staticmethod
    def _clean_heading_title(line: str) -> str:
        """Strip structural heading punctuation and Markdown emphasis markers."""
        title = line.strip().lstrip("#").strip().rstrip(":\uff1a").strip()
        changed = True
        while changed:
            changed = False
            for marker in ("**", "__"):
                if title.startswith(marker):
                    title = title[len(marker):].strip()
                    changed = True
                if title.endswith(marker):
                    title = title[:-len(marker)].strip()
                    changed = True
            title = title.rstrip(":\uff1a").strip()
        return title

    @staticmethod
    def _looks_like_heading(line: str) -> bool:
        return ShapeGrammar.is_heading(line)

    @staticmethod
    def _is_document_title_section(
        section: RawSection,
        sections: list[RawSection],
        raw_text: str,
    ) -> bool:
        """Return True for an empty leading H1 title before real sections."""
        if section.order != 1 or len(sections) <= 1:
            return False
        first_line = raw_text.lstrip().splitlines()[0].strip() if raw_text.strip() else ""
        return first_line.startswith("# ") and not first_line.startswith("## ")

    def _is_unexpected_heading(
        self,
        index: int,
        lines: list[str],
        stripped: str,
        normalized: str,
    ) -> bool:
        return False

    @staticmethod
    def _section_id(
        canonical_title: str,
        order: int,
        headings: list[tuple[int, int, int, str, str, str]],
    ) -> str:
        safe_title = re.sub(r"[^\w]+", "_", canonical_title, flags=re.UNICODE)
        safe_title = safe_title.strip("_") or f"section_{order + 1}"
        same_before = sum(1 for heading in headings[:order] if heading[4] == canonical_title)
        if same_before:
            return f"sec_{safe_title}_{same_before + 1}"
        same_total = sum(1 for heading in headings if heading[4] == canonical_title)
        if same_total > 1:
            return f"sec_{safe_title}_1"
        return f"sec_{safe_title}"

    def _warnings_from_detection(
        self, detection: AdapterDetectionResult
    ) -> list[AdapterWarning]:
        warnings: list[AdapterWarning] = []
        for section in detection.missing_sections:
            warnings.append(
                AdapterWarning(
                    code="MISSING_SECTION",
                    message=f"Expected structural_nl section '{section}' is missing.",
                )
            )
        for section in detection.empty_sections:
            warnings.append(
                AdapterWarning(
                    code="EMPTY_SECTION",
                    message=f"Section '{section}' is present but empty.",
                    source_section_id=f"sec_{section}",
                )
            )
        for section in detection.duplicate_sections:
            warnings.append(
                AdapterWarning(
                    code="DUPLICATE_SECTION",
                    message=f"Section '{section}' appears multiple times.",
                )
            )
        return warnings

    def _extract_variables(self, section: RawSection, source: str) -> list[VariableFact]:
        facts: list[VariableFact] = []
        for item in self._split_list_items(section.text):
            clean = self._clean_item(item)
            if not clean:
                continue
            name = self._variable_name(clean)
            required = False if source == "input" else True
            if source == "input":
                required = not clean.lower().startswith("optional ")
                if "connector" in clean.lower() or "repositories" in clean.lower():
                    required = False
            facts.append(
                VariableFact(
                    name=name,
                    description=clean[:1].upper() + clean[1:],
                    data_type=self._infer_data_type(clean),
                    required=required,
                    source_section_id=section.section_id,
                    evidence=[self._make_evidence(section)],
                )
            )
        return facts

    def _merge_variable_facts(
        self, facts: list[VariableFact], warnings: list[AdapterWarning]
    ) -> list[VariableFact]:
        merged: dict[str, VariableFact] = {}
        for fact in facts:
            existing = merged.get(fact.name)
            if existing is None:
                merged[fact.name] = fact
                continue
            if existing.data_type != fact.data_type:
                warnings.append(
                    AdapterWarning(
                        code="DUPLICATE_HARD_FACT_TYPE_CONFLICT",
                        message=f"Duplicate hard fact '{fact.name}' has conflicting data types.",
                        source_section_id=fact.source_section_id,
                    )
                )
            existing.required = existing.required or fact.required
        return list(merged.values())

    @staticmethod
    def _packet(
        packet_type: str,
        section: RawSection,
        text: str,
        modality: Literal["hard_fact", "hint"],
        compile_targets: list[str],
        suggested_name: str | None = None,
        required: bool | None = None,
    ) -> SemanticPacket:
        base_name = suggested_name or StructuralNLAdapter._variable_name(text)
        packet_id = f"p_{packet_type}_{base_name}"
        return SemanticPacket(
            packet_id=packet_id,
            source_section_id=section.section_id,
            packet_type=packet_type,
            text=text,
            modality=modality,
            compile_targets=compile_targets,
            suggested_name=suggested_name,
            required=required,
        )

    @staticmethod
    def _dedupe_packet_ids(packets: list[SemanticPacket]) -> list[SemanticPacket]:
        counts: dict[str, int] = {}
        for packet in packets:
            count = counts.get(packet.packet_id, 0)
            counts[packet.packet_id] = count + 1
            if count:
                packet.packet_id = f"{packet.packet_id}_{count + 1}"
        return packets

    @staticmethod
    def _make_evidence(section: RawSection) -> EvidenceRef:
        """Build a minimal EvidenceRef from a raw section."""
        return EvidenceRef(source_section_id=section.section_id)

    @staticmethod
    def _split_list_items(text: str) -> list[str]:
        """Split markdown, ordered, or comma-separated list items."""
        text = re.sub(r'\*\*[^*]+:\*\*\s*', '', text)
        text = re.sub(r'__[^_]+:__\s*', '', text)

        lines = text.splitlines()
        markdown_items: list[str] = []
        bullet_pattern = re.compile(r'^[-*+]\s+(.+)$')
        for line in lines:
            match = bullet_pattern.match(line.strip())
            if match:
                markdown_items.append(match.group(1).strip())
        if markdown_items:
            return markdown_items

        ordered_items: list[str] = []
        ordered_pattern = re.compile(r'^\d+\.\s+(.+)$')
        for line in lines:
            match = ordered_pattern.match(line.strip())
            if match:
                ordered_items.append(match.group(1).strip())
        if ordered_items:
            return ordered_items

        normalized = text.strip().rstrip('.')
        normalized = re.sub(r',\s+and\s+', ', ', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\s+and\s+a\s+', ', a ', normalized, flags=re.IGNORECASE)
        return [item.strip() for item in normalized.split(',') if item.strip()]

    @staticmethod
    def _has_list_shape(text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if any(
            re.match(r"^(\s*[-*]\s+|\s*\d+\.\s+)", line)
            for line in stripped.splitlines()
        ):
            return True
        normalized = re.sub(r",\s+and\s+", ", ", stripped, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+and\s+a\s+", ", a ", normalized, flags=re.IGNORECASE)
        return "," in normalized

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        normalized = text.strip()
        if not normalized:
            return []
        parts = re.split(r"(?<=[.!?])\s+", normalized)
        return [part.strip().rstrip(".") for part in parts if part.strip().rstrip(".")]

    @staticmethod
    def _clean_item(text: str) -> str:
        text = text.strip().rstrip(".")
        text = re.sub(r"^(and|or)\s+", "", text, flags=re.IGNORECASE)
        text = text.replace("**", "").replace("__", "")
        return text.strip()

    @staticmethod
    def _variable_name(text: str) -> str:
        normalized = text.strip().lower().rstrip(".")
        normalized = re.sub(r"\s+", " ", normalized)
        if normalized in VARIABLE_NAME_ALIASES:
            return VARIABLE_NAME_ALIASES[normalized]
        normalized = re.sub(r"^(a|an|the)\s+", "", normalized)
        normalized = re.sub(r"^optional\s+", "", normalized)
        normalized = normalized.replace("/", " ")
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
        normalized = normalized.strip("_")
        return normalized or "value"

    @staticmethod
    def _infer_data_type(text: str) -> str:
        lowered = text.lower()
        list_markers = ["topics", "connectors", "repositories", "items", "sources"]
        if any(word in lowered for word in list_markers):
            return "List [text]"
        if lowered.startswith("whether "):
            return "boolean"
        return "text"

    @staticmethod
    def _suggest_constraint_kind(text: str) -> str:
        lowered = text.lower()
        if "do not" in lowered or "deny" in lowered:
            return "prohibition" if "do not" in lowered else "gate"
        if "evidence" in lowered:
            return "evidence"
        return "requirement"
