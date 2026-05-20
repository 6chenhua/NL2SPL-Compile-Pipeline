"""FactVerifier -- merge and validate adapter facts against LLM extraction.

Deterministic structural facts always take priority over LLM-produced
facts.  LLM facts with duplicate names are rejected.  Failure modes are
sanity-checked; delegation intents are accepted but never marked
renderable.

Rejected facts become AdapterWarning records, not silent drops.
"""

from __future__ import annotations

from typing import Any

from nl2spl.adapters.llm_engine import AdapterFactExtraction
from nl2spl.canonical import (
    AdapterWarning,
    DelegationIntentFact,
    FailureModeFact,
    HardFacts,
    VariableFact,
)


class FactVerifier:
    """Validate and merge LLM-extracted facts into the deterministic set.

    Merge policy (in priority order):
    1. Deterministic structural facts (VariableFact, FailureModeFact)
       are kept unchanged -- the LLM cannot overwrite them.
    2. LLM facts with names that already exist in the deterministic set
       are rejected with a warning.
    3. LLM failure modes are sanity-checked: condition text must not be
       a bare noun or empty.
    4. LLM delegation intents are accepted but do NOT imply
       renderability.
    5. All LLM facts must have at least one valid EvidenceRef (enforced
       by the parser before this point).

    The verifier is deterministic: given the same inputs it always
    produces the same merged facts and warnings.
    """

    def verify_and_merge(
        self,
        deterministic: HardFacts,
        llm_extraction: AdapterFactExtraction,
    ) -> tuple[HardFacts, list[AdapterWarning]]:
        """Merge LLM facts into the deterministic set.

        Args:
            deterministic: Facts from the structural adapter (authoritative).
            llm_extraction: Facts parsed from LLM output (candidate set).

        Returns:
            (merged_facts, warnings) -- merged facts plus any rejection
            warnings.  The deterministic input is NOT mutated.
        """
        warnings: list[AdapterWarning] = []

        # Start with copies of deterministic facts
        inputs = list(deterministic.inputs)
        outputs = list(deterministic.outputs)
        failure_modes = list(deterministic.failure_modes)
        delegation_intents = list(deterministic.delegation_intents)

        # Build name sets for duplicate detection
        det_input_names = {f.name for f in inputs}
        det_output_names = {f.name for f in outputs}
        det_failure_names = {f.name for f in failure_modes}
        det_intent_names = {f.name for f in delegation_intents}

        # Merge LLM variable facts
        for fact in llm_extraction.inputs:
            if not _has_evidence(fact):
                warnings.append(_no_evidence_warn("input", fact.name))
                continue
            if _is_reserved_llm_variable_name(fact.name):
                warnings.append(_reserved_variable_warn("input", fact.name))
                continue
            if fact.name in det_input_names:
                warnings.append(_duplicate_warn("input", fact.name))
                continue
            inputs.append(fact)
            det_input_names.add(fact.name)

        for fact in llm_extraction.outputs:
            if not _has_evidence(fact):
                warnings.append(_no_evidence_warn("output", fact.name))
                continue
            if _is_reserved_llm_variable_name(fact.name):
                warnings.append(_reserved_variable_warn("output", fact.name))
                continue
            if fact.name in det_output_names:
                warnings.append(_duplicate_warn("output", fact.name))
                continue
            if fact.name in det_input_names:
                warnings.append(_duplicate_warn("output (collides with input)", fact.name))
                continue
            outputs.append(fact)
            det_output_names.add(fact.name)

        # Merge LLM failure modes (with evidence + sanity check)
        for fact in llm_extraction.failure_modes:
            if not _has_evidence(fact):
                warnings.append(_no_evidence_warn("failure_mode", fact.name))
                continue
            if fact.name in det_failure_names:
                warnings.append(_duplicate_warn("failure_mode", fact.name))
                continue
            if not self._is_valid_failure_text(fact.text):
                warnings.append(_rejected_warn(
                    "failure_mode", fact.name,
                    f"non-condition text: '{fact.text[:80]}'",
                ))
                continue
            failure_modes.append(fact)
            det_failure_names.add(fact.name)

        # Merge LLM delegation intents
        for fact in llm_extraction.delegation_intents:
            if not _has_evidence(fact):
                warnings.append(_no_evidence_warn("delegation_intent", fact.name))
                continue
            if fact.name in det_intent_names:
                warnings.append(_duplicate_warn("delegation_intent", fact.name))
                continue
            # Delegation intents are never marked renderable --
            # the compiler decides whether a valid handoff exists.
            delegation_intents.append(fact)
            det_intent_names.add(fact.name)

        # Preserve LLM-emitted warnings
        for w in llm_extraction.warnings:
            warnings.append(w)

        merged = HardFacts(
            inputs=inputs,
            outputs=outputs,
            failure_modes=failure_modes,
            delegation_intents=delegation_intents,
        )
        return merged, warnings

    @staticmethod
    def _is_valid_failure_text(text: str) -> bool:
        """Reject failure mode text that is a bare noun or empty.

        A valid failure condition describes a situation (e.g. "Missing
        timeframe"), not a bare concept (e.g. "timeframe").
        """
        if not text or not text.strip():
            return False
        # Reject single-word "failure modes" (likely noun extraction errors)
        if len(text.split()) <= 1:
            return False
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RESERVED_LLM_VARIABLE_NAMES = {
    "alternative_flow_blocks",
    "alternative_flows",
    "block_id",
    "block_type",
    "condition_text",
    "delegation_candidates",
    "end_offset",
    "exception_flow_blocks",
    "exception_flows",
    "flow_id",
    "is_ambiguous",
    "main_flow_blocks",
    "main_flow_spans",
    "needs_split",
    "order",
    "packet_id",
    "packet_type",
    "reasons",
    "source_packet_id",
    "source_section_id",
    "span_id",
    "spans",
    "start_offset",
    "text",
}


def _has_evidence(fact: Any) -> bool:
    """Return True if *fact* carries at least one EvidenceRef."""
    evidence = getattr(fact, "evidence", None)
    return bool(evidence)


def _is_reserved_llm_variable_name(name: str) -> bool:
    """Return True for compiler/schema fields that are not domain variables."""
    return name.strip().lower() in _RESERVED_LLM_VARIABLE_NAMES


def _no_evidence_warn(kind: str, name: str) -> AdapterWarning:
    return AdapterWarning(
        code="LLM_FACT_WITHOUT_EVIDENCE",
        message=f"LLM {kind} fact '{name}' has no evidence -- rejected.",
        severity="warning",
    )


def _rejected_warn(kind: str, name: str, reason: str) -> AdapterWarning:
    return AdapterWarning(
        code="LLM_FACT_REJECTED",
        message=f"LLM {kind} fact '{name}' rejected: {reason}",
        severity="warning",
    )


def _reserved_variable_warn(kind: str, name: str) -> AdapterWarning:
    return AdapterWarning(
        code="LLM_RESERVED_VARIABLE_REJECTED",
        message=(
            f"LLM {kind} fact '{name}' looks like an internal compiler "
            "schema field -- rejected."
        ),
        severity="warning",
    )


def _duplicate_warn(kind: str, name: str) -> AdapterWarning:
    return AdapterWarning(
        code="LLM_DUPLICATE_FACT",
        message=f"LLM {kind} fact '{name}' duplicates deterministic fact -- rejected.",
        severity="warning",
    )
