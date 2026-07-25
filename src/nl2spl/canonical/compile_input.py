"""Canonical input contract shared by input adapters and the compile pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class AdapterDetectionResult:
    """Result of adapter detection without confidence scores."""

    matched: bool
    schema_name: str
    schema_version: str
    matched_sections: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    unexpected_sections: list[str] = field(default_factory=list)
    duplicate_sections: list[str] = field(default_factory=list)
    empty_sections: list[str] = field(default_factory=list)
    parse_errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RawSection:
    """Parsed source section with provenance offsets."""

    section_id: str
    canonical_title: str
    original_title: str
    text: str
    order: int
    start_offset: int | None = None
    end_offset: int | None = None
    structure_type: str = "paragraph"
    list_items: list[str] | None = None


@dataclass
class SemanticPacket:
    """Adapter-produced semantic unit with provenance."""

    packet_id: str
    source_section_id: str
    packet_type: str
    text: str
    modality: Literal["hard_fact", "hint"]
    compile_targets: list[str] = field(default_factory=list)
    suggested_name: str | None = None
    required: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceRef:
    """Provenance anchor for a canonical fact.

    Every fact produced by the adapter or LLM engine must cite at least
    one EvidenceRef so the verifier can validate it against known
    sections and packets.  The verifier rejects uncited facts.
    """

    source_section_id: str
    source_packet_id: str | None = None
    source_span_ids: list[str] = field(default_factory=list)
    quoted_text: str | None = None


@dataclass
class VariableFact:
    """Input or output variable fact extracted deterministically."""

    name: str
    description: str
    data_type: str
    required: bool
    source_section_id: str
    evidence: list[EvidenceRef] = field(default_factory=list)


@dataclass
class DelegationIntentFact:
    """Non-executable delegation intent extracted from input structure.

    Records that the source describes delegation but does NOT claim the
    delegation is renderable.  The compiler must still decide whether a
    valid handoff contract exists before producing INVOKE_WORKER.
    """

    name: str
    text: str
    suggested_worker_name: str | None = None
    input_names: list[str] = field(default_factory=list)
    output_names: list[str] = field(default_factory=list)
    evidence: list[EvidenceRef] = field(default_factory=list)


@dataclass
class HardFacts:
    """Facts that downstream stages should not reinterpret away."""

    inputs: list[VariableFact] = field(default_factory=list)
    outputs: list[VariableFact] = field(default_factory=list)
    delegation_intents: list[DelegationIntentFact] = field(default_factory=list)


@dataclass
class CompileHint:
    """Soft hint for downstream semantic stages."""

    source_section_id: str
    text: str
    target: str | None = None
    suggested_kind: str | None = None
    suggested_flow: str | None = None
    suggested_block_type: str | None = None
    suggested_step_type: str | None = None
    suggested_condition: str | None = None
    suggested_type: str | None = None
    suggested_worker_name: str | None = None
    evidence: list[EvidenceRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompileHints:
    """Grouped soft hints for downstream compiler stages."""

    profile_hints: list[CompileHint] = field(default_factory=list)
    process_hints: list[CompileHint] = field(default_factory=list)
    constraint_hints: list[CompileHint] = field(default_factory=list)
    flow_hints: list[CompileHint] = field(default_factory=list)
    resource_hints: list[CompileHint] = field(default_factory=list)
    delegation_hints: list[CompileHint] = field(default_factory=list)


@dataclass
class AdapterWarning:
    """Non-fatal adapter diagnostic unless emitted by contract validation."""

    code: str
    message: str
    source_section_id: str | None = None
    severity: Literal["info", "warning", "error"] = "warning"


@dataclass
class CanonicalCompileInput:
    """Uniform adapter output consumed by the compile pipeline."""

    source_schema: str
    schema_version: str
    raw_text: str
    raw_sections: list[RawSection] = field(default_factory=list)
    semantic_packets: list[SemanticPacket] = field(default_factory=list)
    hard_facts: HardFacts = field(default_factory=HardFacts)
    compile_hints: CompileHints = field(default_factory=CompileHints)
    warnings: list[AdapterWarning] = field(default_factory=list)
    detection: AdapterDetectionResult | None = None
    route_priors: list[Any] = field(default_factory=list)  # list[RoutePrior]


class CanonicalCompileInputValidator:
    """Validate the adapter contract before pipeline stages consume it."""

    @classmethod
    def validate(cls, canonical_input: CanonicalCompileInput) -> list[str]:
        """Return contract validation errors."""
        errors: list[str] = []

        if not canonical_input.source_schema.strip():
            errors.append("CanonicalCompileInput.source_schema must be non-empty.")
        if not canonical_input.raw_text.strip():
            errors.append("CanonicalCompileInput.raw_text must be non-empty.")

        section_ids = [section.section_id for section in canonical_input.raw_sections]
        errors.extend(cls._duplicates(section_ids, "RawSection.section_id"))
        section_id_set = set(section_ids)

        packet_ids = [packet.packet_id for packet in canonical_input.semantic_packets]
        errors.extend(cls._duplicates(packet_ids, "SemanticPacket.packet_id"))
        for packet in canonical_input.semantic_packets:
            if packet.source_section_id and packet.source_section_id not in section_id_set:
                errors.append(
                    "SemanticPacket "
                    f"{packet.packet_id} references unknown source_section_id "
                    f"{packet.source_section_id}."
                )

        input_names = [fact.name for fact in canonical_input.hard_facts.inputs]
        output_names = [fact.name for fact in canonical_input.hard_facts.outputs]
        intent_names = [fact.name for fact in canonical_input.hard_facts.delegation_intents]
        errors.extend(cls._duplicates(input_names, "HardFacts.inputs.name"))
        errors.extend(cls._duplicates(output_names, "HardFacts.outputs.name"))
        errors.extend(cls._duplicates(intent_names, "HardFacts.delegation_intents.name"))

        packet_by_id = {
            packet.packet_id: packet for packet in canonical_input.semantic_packets
        }

        for fact in [
            *canonical_input.hard_facts.inputs,
            *canonical_input.hard_facts.outputs,
            *canonical_input.hard_facts.delegation_intents,
        ]:
            sid = getattr(fact, 'source_section_id', '')
            if sid and sid not in section_id_set:
                errors.append(
                    f"Hard fact {getattr(fact, 'name', sid)} "
                    f"references unknown source_section_id {sid}."
                )
            # Validate evidence references
            errors.extend(
                cls._validate_evidence_refs(
                    fact.evidence, getattr(fact, 'name', 'fact'),
                    section_id_set, packet_by_id,
                )
            )

        # Validate hint source_section_id and evidence
        for hint in cls._all_hints(canonical_input.compile_hints):
            if hint.source_section_id and hint.source_section_id not in section_id_set:
                errors.append(
                    f"Compile hint references unknown source_section_id "
                    f"{hint.source_section_id}."
                )
            errors.extend(
                cls._validate_evidence_refs(
                    hint.evidence, "CompileHint",
                    section_id_set, packet_by_id,
                )
            )

        if cls._contains_key(asdict(canonical_input), "confidence"):
            errors.append("CanonicalCompileInput must not contain a confidence field.")

        return errors

    @staticmethod
    def _all_hints(hints: CompileHints) -> list[CompileHint]:
        return [
            *hints.profile_hints,
            *hints.process_hints,
            *hints.constraint_hints,
            *hints.flow_hints,
            *hints.resource_hints,
            *hints.delegation_hints,
        ]

    @staticmethod
    def _validate_evidence_refs(
        evidence: list[Any],
        owner: str,
        section_id_set: set[str],
        packet_by_id: dict[str, Any],
    ) -> list[str]:
        """Validate evidence_refs: section must exist, packet must exist and
        belong to the referenced section."""
        errors: list[str] = []
        for ev in evidence:
            if ev.source_section_id not in section_id_set:
                errors.append(
                    f"EvidenceRef in {owner} references unknown "
                    f"source_section_id {ev.source_section_id}."
                )
            if ev.source_packet_id:
                packet = packet_by_id.get(ev.source_packet_id)
                if packet is None:
                    errors.append(
                        f"EvidenceRef in {owner} references unknown "
                        f"source_packet_id {ev.source_packet_id}."
                    )
                elif packet.source_section_id != ev.source_section_id:
                    errors.append(
                        f"EvidenceRef in {owner}: source_packet_id "
                        f"{ev.source_packet_id} belongs to section "
                        f"'{packet.source_section_id}', not "
                        f"'{ev.source_section_id}'."
                    )
        return errors

    @staticmethod
    def _duplicates(values: list[str], field_name: str) -> list[str]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for value in values:
            if value in seen and value not in duplicates:
                duplicates.append(value)
            seen.add(value)
        return [f"{field_name} must be unique; duplicate value: {value}." for value in duplicates]

    @classmethod
    def _contains_key(cls, value: object, key: str) -> bool:
        if isinstance(value, dict):
            return key in value or any(cls._contains_key(item, key) for item in value.values())
        if isinstance(value, list):
            return any(cls._contains_key(item, key) for item in value)
        return False
