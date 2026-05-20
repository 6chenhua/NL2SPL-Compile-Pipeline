"""LLM Adapter Engine -- parser and verifier for evidence-bound fact extraction.

The engine produces AdapterFactExtraction from LLM JSON responses.
Every fact must cite existing sections and (when provided) packets.
Uncited, malformed, or invalid facts are rejected with warnings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from nl2spl.canonical import (
    AdapterWarning,
    DelegationIntentFact,
    EvidenceRef,
    FailureModeFact,
    RawSection,
    SemanticPacket,
    VariableFact,
)


# ---------------------------------------------------------------------------
# Output DTO
# ---------------------------------------------------------------------------


@dataclass
class AdapterFactExtraction:
    """Validated facts extracted from LLM output."""

    inputs: list[VariableFact] = field(default_factory=list)
    outputs: list[VariableFact] = field(default_factory=list)
    failure_modes: list[FailureModeFact] = field(default_factory=list)
    delegation_intents: list[DelegationIntentFact] = field(default_factory=list)
    warnings: list[AdapterWarning] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class AdapterSemanticEngine(Protocol):
    """Optional LLM-backed engine for extracting evidence-bound facts.

    Implementations must return AdapterFactExtraction with every fact
    carrying at least one valid EvidenceRef.
    """

    def extract(
        self,
        raw_text: str,
        sections: list[RawSection],
        packets: list[SemanticPacket],
    ) -> AdapterFactExtraction:
        ...


# ---------------------------------------------------------------------------
# JSON schema keys (expected from LLM)
# ---------------------------------------------------------------------------

_KEY_INPUTS = "inputs"
_KEY_OUTPUTS = "outputs"
_KEY_FAILURE_MODES = "failure_modes"
_KEY_DELEGATION_INTENTS = "delegation_intents"
_KEY_WARNINGS = "warnings"

# Fields within each fact object
_F_NAME = "name"
_F_DESCRIPTION = "description"
_F_DATA_TYPE = "data_type"
_F_REQUIRED = "required"
_F_TEXT = "text"
_F_SOURCE_SECTION_ID = "source_section_id"
_F_SOURCE_PACKET_ID = "source_packet_id"
_F_INPUT_NAMES = "input_names"
_F_OUTPUT_NAMES = "output_names"
_F_SUGGESTED_WORKER_NAME = "suggested_worker_name"


def parse_llm_fact_json(
    raw_json: str,
    section_ids: set[str],
    packet_by_id: dict[str, SemanticPacket] | None = None,
) -> AdapterFactExtraction:
    """Parse and validate an LLM JSON response.

    Rules enforced:
    - JSON must be valid.
    - Every fact must have at least one EvidenceRef with a known
      ``source_section_id``.
    - ``source_packet_id``, if provided, must exist in *packet_by_id* and
      belong to the same section.
    - Missing ``name`` or ``text`` on a fact produces a warning and the
      fact is skipped.
    - Unknown top-level keys are ignored (forward-compatible).

    Args:
        raw_json: Raw JSON string from the LLM.
        section_ids: Known section IDs from the adapter.
        packet_by_id: Known packets, keyed by packet_id.

    Returns:
        AdapterFactExtraction with validated facts and any warnings.
    """
    packets = packet_by_id or {}
    warnings: list[AdapterWarning] = []
    extraction = AdapterFactExtraction()

    # 1. Parse JSON
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        warnings.append(
            AdapterWarning(
                code="LLM_JSON_PARSE_ERROR",
                message=f"Failed to parse LLM JSON response: {exc}",
                severity="error",
            )
        )
        extraction.warnings = warnings
        return extraction

    if not isinstance(data, dict):
        warnings.append(
            AdapterWarning(
                code="LLM_JSON_NOT_OBJECT",
                message="LLM JSON response is not a JSON object.",
                severity="error",
            )
        )
        extraction.warnings = warnings
        return extraction

    # 2. Parse each fact kind
    extraction.inputs = _parse_variable_facts(
        data.get(_KEY_INPUTS, []), section_ids, packets, warnings,
    )
    extraction.outputs = _parse_variable_facts(
        data.get(_KEY_OUTPUTS, []), section_ids, packets, warnings,
    )
    extraction.failure_modes = _parse_failure_modes(
        data.get(_KEY_FAILURE_MODES, []), section_ids, packets, warnings,
    )
    extraction.delegation_intents = _parse_delegation_intents(
        data.get(_KEY_DELEGATION_INTENTS, []), section_ids, packets, warnings,
    )
    # Preserve LLM-emitted warnings
    for w in data.get(_KEY_WARNINGS, []):
        if isinstance(w, dict) and "message" in w:
            warnings.append(
                AdapterWarning(
                    code=w.get("code", "LLM_WARNING"),
                    message=w["message"],
                    source_section_id=w.get("source_section_id"),
                    severity="warning",
                )
            )

    extraction.warnings = warnings
    return extraction


# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------


def _parse_variable_facts(
    items: Any,
    section_ids: set[str],
    packets: dict[str, SemanticPacket],
    warnings: list[AdapterWarning],
) -> list[VariableFact]:
    facts: list[VariableFact] = []
    if not isinstance(items, list):
        return facts

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            warnings.append(_warn(f"inputs/outputs[{i}] is not an object", item))
            continue

        name = _str(item, _F_NAME)
        if not name:
            warnings.append(_warn(f"Variable fact missing name", item))
            continue

        evidence = _build_evidence(item, section_ids, packets, warnings)
        if not evidence:
            warnings.append(_warn(
                f"Variable fact '{name}' has no valid evidence -- skipped",
                item,
            ))
            continue

        facts.append(
            VariableFact(
                name=name,
                description=_str(item, _F_DESCRIPTION, name),
                data_type=_str(item, _F_DATA_TYPE, "text"),
                required=bool(item.get(_F_REQUIRED, False)),
                source_section_id=evidence[0].source_section_id,
                evidence=evidence,
            )
        )
    return facts


def _parse_failure_modes(
    items: Any,
    section_ids: set[str],
    packets: dict[str, SemanticPacket],
    warnings: list[AdapterWarning],
) -> list[FailureModeFact]:
    facts: list[FailureModeFact] = []
    if not isinstance(items, list):
        return facts

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            warnings.append(_warn(f"failure_modes[{i}] is not an object", item))
            continue

        text = _str(item, _F_TEXT) or _str(item, _F_NAME)
        if not text:
            warnings.append(_warn("Failure mode missing text/name", item))
            continue

        evidence = _build_evidence(item, section_ids, packets, warnings)
        if not evidence:
            warnings.append(_warn(
                f"Failure mode has no valid evidence -- skipped", item,
            ))
            continue

        facts.append(
            FailureModeFact(
                name=_str(item, _F_NAME, text[:40].replace(" ", "_").lower()),
                text=text,
                source_section_id=evidence[0].source_section_id,
                evidence=evidence,
            )
        )
    return facts


def _parse_delegation_intents(
    items: Any,
    section_ids: set[str],
    packets: dict[str, SemanticPacket],
    warnings: list[AdapterWarning],
) -> list[DelegationIntentFact]:
    facts: list[DelegationIntentFact] = []
    if not isinstance(items, list):
        return facts

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            warnings.append(_warn(f"delegation_intents[{i}] is not an object", item))
            continue

        text = _str(item, _F_TEXT) or _str(item, _F_NAME)
        if not text:
            warnings.append(_warn("Delegation intent missing text/name", item))
            continue

        evidence = _build_evidence(item, section_ids, packets, warnings)
        if not evidence:
            warnings.append(_warn(
                f"Delegation intent has no valid evidence -- skipped", item,
            ))
            continue

        facts.append(
            DelegationIntentFact(
                name=_str(item, _F_NAME, text[:40].replace(" ", "_").lower()),
                text=text,
                suggested_worker_name=_str(item, _F_SUGGESTED_WORKER_NAME) or None,
                input_names=_str_list(item, _F_INPUT_NAMES),
                output_names=_str_list(item, _F_OUTPUT_NAMES),
                evidence=evidence,
            )
        )
    return facts


# ---------------------------------------------------------------------------
# Evidence validation
# ---------------------------------------------------------------------------


def _build_evidence(
    item: dict[str, Any],
    section_ids: set[str],
    packets: dict[str, SemanticPacket],
    warnings: list[AdapterWarning],
) -> list[EvidenceRef]:
    """Build EvidenceRef list from an LLM fact dict.

    Strict mode: a ``source_packet_id`` that does not exist or belongs to
    the wrong section invalidates that evidence entry.  If no evidence
    entries survive, the fact is skipped entirely (empty list returned).

    Accepts:
    - ``source_section_id`` (required) + optional ``source_packet_id``
    - ``evidence`` list of {source_section_id, source_packet_id} objects
    """
    # Prefer explicit evidence list
    evidence_list = item.get("evidence")
    if isinstance(evidence_list, list) and evidence_list:
        refs: list[EvidenceRef] = []
        for ev in evidence_list:
            if not isinstance(ev, dict):
                continue
            sid = _str(ev, _F_SOURCE_SECTION_ID)
            if not sid or sid not in section_ids:
                if sid:
                    warnings.append(_warn(
                        f"Evidence source_section_id '{sid}' is unknown",
                        item,
                    ))
                continue
            pid = _str(ev, _F_SOURCE_PACKET_ID) or None
            if pid:
                if pid not in packets:
                    warnings.append(_warn(
                        f"Evidence source_packet_id '{pid}' is unknown "
                        f"-- evidence entry rejected", item,
                    ))
                    continue
                pkt = packets[pid]
                if pkt.source_section_id != sid:
                    warnings.append(_warn(
                        f"Packet '{pid}' belongs to section "
                        f"'{pkt.source_section_id}', not '{sid}' "
                        f"-- evidence entry rejected", item,
                    ))
                    continue
            refs.append(EvidenceRef(
                source_section_id=sid,
                source_packet_id=pid,
            ))
        return refs

    # Fall back to top-level source_section_id / source_packet_id
    sid = _str(item, _F_SOURCE_SECTION_ID)
    if not sid or sid not in section_ids:
        if sid:
            warnings.append(_warn(
                f"source_section_id '{sid}' is unknown or missing", item,
            ))
        return []

    pid = _str(item, _F_SOURCE_PACKET_ID) or None
    if pid:
        if pid not in packets:
            warnings.append(_warn(
                f"source_packet_id '{pid}' is unknown "
                f"-- evidence rejected, fact skipped", item,
            ))
            return []
        pkt = packets[pid]
        if pkt.source_section_id != sid:
            warnings.append(_warn(
                f"Packet '{pid}' belongs to section "
                f"'{pkt.source_section_id}', not '{sid}' "
                f"-- evidence rejected, fact skipped", item,
            ))
            return []

    return [EvidenceRef(source_section_id=sid, source_packet_id=pid)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _str(obj: dict[str, Any], key: str, default: str = "") -> str:
    val = obj.get(key, default)
    return str(val).strip() if val else default


def _str_list(obj: dict[str, Any], key: str) -> list[str]:
    val = obj.get(key, [])
    if isinstance(val, list):
        return [str(v).strip() for v in val if v]
    return []


# ---------------------------------------------------------------------------
# Freeform context builder (Phase 6: GenericNLAdapter LLM extraction)
# ---------------------------------------------------------------------------


def build_freeform_context(
    raw_text: str,
) -> tuple[list[RawSection], list[SemanticPacket]]:
    """Build synthetic section + packets for freeform NL input.

    Creates a single synthetic ``sec_freeform_input`` section and splits
    the raw text into sentence-level packets so the LLM engine can cite
    evidence.
    """
    import re

    section = RawSection(
        section_id="sec_freeform_input",
        canonical_title="freeform_input",
        original_title="Freeform Input",
        text=raw_text,
        order=0,
    )

    # Split into sentence/paragraph chunks as packets
    chunks = re.split(r"(?<=[.!?\n])\s+", raw_text.strip())
    packets: list[SemanticPacket] = []
    for i, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if not chunk:
            continue
        packets.append(
            SemanticPacket(
                packet_id=f"p_freeform_{i:03d}",
                source_section_id="sec_freeform_input",
                packet_type="freeform_chunk",
                text=chunk[:200],
                modality="hint",
            )
        )

    return [section], packets


def _warn(message: str, raw_item: Any = None) -> AdapterWarning:
    return AdapterWarning(
        code="LLM_FACT_REJECTED",
        message=message,
        severity="warning",
    )
