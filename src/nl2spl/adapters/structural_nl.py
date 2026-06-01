"""Adapter for stable section-based natural language specifications."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Literal

from nl2spl.adapters.morphology import ShapeGrammar
from nl2spl.adapters.base import InputAdapter
from nl2spl.canonical.compile_input import (
    AdapterDetectionResult,
    AdapterWarning,
    CanonicalCompileInput,
    CompileHints,
    DelegationIntentFact,
    EvidenceRef,
    FailureModeFact,
    HardFacts,
    RawSection,
    SemanticPacket,
    VariableFact,
)
from nl2spl.llm.prompts import load_prompt

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
    """检查文本是否为空值标记（如 'None', 'N/A'）。
    
    用于识别用户用来表示"无内容"的占位符，避免将其当作有效的
    failure condition、constraint 或 process step。
    
    Args:
        text: 待检查的文本
    
    Returns:
        True 如果文本是空值标记
    
    Examples:
        >>> _is_empty_marker("None")
        True
        >>> _is_empty_marker("** None")
        True
        >>> _is_empty_marker("N/A")
        True
        >>> _is_empty_marker("Missing inputs")
        False
    """
    candidate = text.strip()
    candidate = re.sub(r"^\s*[-*+]\s+", "", candidate)
    candidate = re.sub(r"^\s*\d+\.\s+", "", candidate)
    if ":" in candidate or "：" in candidate:
        _label, candidate = re.split(r"[:：]", candidate, maxsplit=1)
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


class StructuralNLAdapter(InputAdapter):
    """Parse known structural NL section headings into canonical input.

    When *llm_client* is provided and enrichment is enabled, the adapter
    may use the LLM engine to add missing descriptions or discover
    additional facts.  Deterministic section facts always take priority.
    """

    name = "structural_nl"
    schema_version = "1.0"

    def __init__(self, llm_client: object | None = None) -> None:
        self._llm_client = llm_client

    def detect(self, raw_text: str) -> AdapterDetectionResult:
        """Detect structural_nl by section evidence."""
        sections, unexpected = self._parse_sections(raw_text)
        matched_titles = [section.original_title for section in sections]
        counts = Counter(matched_titles)
        matched_unique = list(dict.fromkeys(matched_titles))
        duplicate_sections = sorted(title for title, count in counts.items() if count > 1)
        empty_sections = [
            section.original_title for section in sections if not section.text.strip()
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
            # Unconditionally output neutral structural packets
            items = self._split_list_items(section.text)
            has_lists = self._has_list_shape(section.text)

            if has_lists:
                for item in items:
                    clean = self._clean_item(item)
                    if clean:
                        # 跳过空标记
                        if _is_empty_marker(clean):
                            continue
                        
                        packet = self._packet(
                            "list_item",
                            section,
                            clean,
                            "hint",
                            [],
                        )
                        # Neutral structural unit: no executable commitment.
                        # Stage 2 LLM/RoutePrior determines executability.
                        packet.metadata.setdefault("executable", False)
                        semantic_packets.append(packet)
            else:
                for text in self._split_sentences(section.text):
                    if text.strip():
                        # 跳过空标记
                        if _is_empty_marker(text.strip()):
                            continue
                        
                        packet = self._packet(
                            "sentence",
                            section,
                            text,
                            "hint",
                            [],
                        )
                        # Neutral structural unit: no executable commitment.
                        packet.metadata.setdefault("executable", False)
                        semantic_packets.append(packet)

            # Legacy compatibility path for exact-schema inputs and outputs
            title = section.canonical_title
            if title in ("inputs for each run", "inputs_for_each_run"):
                inputs = self._extract_variables(section, source="input")
                for fact in inputs:
                    fact.source_packet_id = f"adapter_compat_exact_schema_{fact.name}"
                    # No construct_target generated here.
                hard_facts.inputs.extend(self._merge_variable_facts(inputs, warnings))
            elif title in ("required outputs", "required_outputs"):
                outputs = self._extract_variables(section, source="output")
                for fact in outputs:
                    fact.source_packet_id = f"adapter_compat_exact_schema_{fact.name}"
                    # No construct_target generated here.
                hard_facts.outputs.extend(self._merge_variable_facts(outputs, warnings))
            elif title in ("failure handling", "anticipated failures", "blocking failures"):
                # Extract failure modes for bridge fallback
                failure_modes = self._extract_failure_modes(section)
                hard_facts.failure_modes.extend(failure_modes)
            elif title in ("delegation policy", "delegable work", "non-delegable work"):
                # Extract delegation intents for bridge fallback
                delegation_intents = self._extract_delegation_intents(section)
                hard_facts.delegation_intents.extend(delegation_intents)

        from nl2spl.adapters.section_semantic_mapper import SectionSemanticMapper
        mapper = SectionSemanticMapper(self._llm_client)
        route_priors, mapper_warnings = mapper.map_sections(sections, semantic_packets)
        warnings.extend(mapper_warnings)

        # Optional LLM enrichment (Phase 7)
        if self._llm_client is not None:
            try:
                hard_facts, llm_warns = self._enrich_with_llm(
                    raw_text, sections, semantic_packets, hard_facts,
                )
                warnings.extend(llm_warns)
            except Exception as exc:
                warnings.append(
                    AdapterWarning(
                        code="LLM_ENRICHMENT_FAILED",
                        message=(
                            f"LLM enrichment failed: {exc}. "
                            f"Deterministic facts preserved."
                        ),
                        severity="warning",
                    )
                )

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
            route_priors=route_priors,
        )

    def _enrich_with_llm(
        self,
        raw_text: str,
        sections: list[Any],
        packets: list[Any],
        deterministic: Any,
    ) -> tuple[Any, list[Any]]:
        """Run LLM enrichment and merge with deterministic facts."""
        import json as _json

        from nl2spl.adapters.fact_verifier import FactVerifier
        from nl2spl.adapters.llm_engine import parse_llm_fact_json

        section_ids = {s.section_id for s in sections}
        packet_by_id = {p.packet_id: p for p in packets}

        packet_lines = []
        for p in packets:
            packet_lines.append(
                f"  {p.packet_id} ({p.packet_type}, "
                f"section={p.source_section_id}): {p.text}"
            )

        user_prompt = (
            "Enrich the following structural input with additional "
            "facts if any are missing. Cite the appropriate "
            "source_section_id and source_packet_id for every fact.\n\n"
            "Available packets:\n" + "\n".join(packet_lines) + "\n\n"
            f"Raw text:\n{raw_text}"
        )

        system_prompt = load_prompt("input_adapter_fact_extractor")
        result_dict = self._llm_client.call_json(  # type: ignore[union-attr]
            stage_name="structural_enrich",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=4096,
        )

        extraction = parse_llm_fact_json(
            _json.dumps(result_dict), section_ids, packet_by_id,
        )
        verifier = FactVerifier()
        return verifier.verify_and_merge(deterministic, extraction)

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
                original_title = stripped.lstrip("#").strip().rstrip(":：").strip()
                canonical_title = self.normalize_heading(stripped)
            elif (
                ShapeGrammar.KEY_VALUE.match(stripped)
                and not self._looks_like_heading(previous_nonempty)
            ):
                title, inline_text = re.split(r"[:：]", stripped, maxsplit=1)
                original_title = title.strip()
                canonical_title = self.normalize_heading(f"{original_title}:")
                # 清理 inline_text：移除 bold 标记（** 或 __）
                inline_text = inline_text.strip()
                # 移除开头的 bold 标记，如 "**Anticipated Failures:** ..." 中的 "**"
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
            sections.append(
                RawSection(
                    section_id=section_id,
                    canonical_title=canonical_title,
                    original_title=original_title,
                    text=text,
                    order=order + 1,
                    start_offset=line_end,
                    end_offset=next_start,
                )
            )
        return sections, unexpected

    @staticmethod
    def normalize_heading(line: str) -> str:
        """Normalize a potential heading."""
        line = line.strip().lstrip("#").strip().rstrip(":：").lower()
        return " ".join(line.split())

    @staticmethod
    def _looks_like_heading(line: str) -> bool:
        return ShapeGrammar.is_heading(line)

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
        safe_title = canonical_title.replace(" ", "_")
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

    def _extract_failure_modes(self, section: RawSection) -> list[FailureModeFact]:
        """Extract failure modes from a section, filtering empty markers."""
        modes = []
        for item in self._split_list_items(section.text):
            clean = self._clean_item(item)
            if clean and not _is_empty_marker(clean):  # 过滤空标记
                modes.append(
                    FailureModeFact(
                        name=self._variable_name(clean),
                        text=clean[:1].upper() + clean[1:],
                        source_section_id=section.section_id,
                        evidence=[self._make_evidence(section)],
                    )
                )
        return modes

    def _extract_delegation_intents(self, section: RawSection) -> list[DelegationIntentFact]:
        """Extract delegation intents from a section."""
        intents = []
        for item in self._split_list_items(section.text):
            clean = self._clean_item(item)
            if clean and not _is_empty_marker(clean):
                intents.append(
                    DelegationIntentFact(
                        name=self._variable_name(clean),
                        text=clean[:1].upper() + clean[1:],
                        evidence=[self._make_evidence(section)],
                    )
                )
        return intents



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
        """拆分列表项（markdown bullets、有序列表或逗号分隔）。
        
        策略：
        1. 清理文本中的 bold 标记
        2. 优先尝试 markdown bullet 拆分 (-, *, +)
        3. 尝试有序列表拆分 (1. 2. 3.)
        4. 如果没有 bullets，回退到逗号拆分
        5. Header 行（如 "**Anticipated Failures:**"）不包含在结果中
        
        Args:
            text: 可能包含 markdown bullets、有序列表或逗号分隔列表的文本
        
        Returns:
            拆分后的 item 文本列表（不包含 header）
        """
        # 清理 bold 标记（** 或 __）和 heading 标记
        # 移除类似 "**Failures:**" 这样的 bold heading
        text = re.sub(r'\*\*[^*]+:\*\*\s*', '', text)  # **Heading:** 格式
        text = re.sub(r'__[^_]+:__\s*', '', text)      # __Heading:__ 格式
        
        # 优先尝试 markdown bullet 拆分（只匹配顶层，不匹配缩进的）
        lines = text.split('\n')
        bullet_pattern = re.compile(r'^[-*+]\s+(.+)$')  # 不匹配开头有空格的
        
        markdown_items = []
        for line in lines:
            match = bullet_pattern.match(line)
            if match:
                markdown_items.append(match.group(1).strip())
        
        # 如果找到 markdown bullets，返回 items（不包含 header）
        if markdown_items:
            return markdown_items
        
        # 尝试有序列表拆分 (1. 2. 3.)
        ordered_pattern = re.compile(r'^\d+\.\s+(.+)$')  # 不匹配开头有空格的
        
        ordered_items = []
        for line in lines:
            match = ordered_pattern.match(line)
            if match:
                ordered_items.append(match.group(1).strip())
        
        # 如果找到有序列表，返回 items
        if ordered_items:
            return ordered_items
        
        # 回退到逗号拆分（现有逻辑）
        normalized = text.strip().rstrip(".")
        normalized = re.sub(r",\s+and\s+", ", ", normalized, flags=re.IGNORECASE)  # "x, and y" → "x, y"
        normalized = re.sub(r"\s+and\s+a\s+", ", a ", normalized, flags=re.IGNORECASE)  # "x and a y" → "x, a y"
        return [item.strip() for item in normalized.split(",") if item.strip()]

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
