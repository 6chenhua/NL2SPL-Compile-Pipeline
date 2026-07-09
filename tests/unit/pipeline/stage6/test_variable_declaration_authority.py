"""S6V2.5: Declaration Authority Metadata / Sidecar tests.

Verify:
1. Sidecar can be created and serialized/deserialized.
2. Stage 3.5 candidate IO defaults to inadmissible.
3. Resource contract demand variables are admissible.
4. Adapter hard fact variables are admissible.
5. Worker handoff binding is only admissible when explicitly admitted.
6. No source_span_ids, no contract_demand_id, no explicit authority
   → not admissible.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from nl2spl.ir.variable_declaration_authority_ir import (
    ADMISSIBLE_AUTHORITIES,
    CONDITIONALLY_ADMISSIBLE_AUTHORITIES,
    INADMISSIBLE_AUTHORITIES,
    DeclarationAuthorityRegistry,
    DeclarationAuthoritySidecar,
    is_admissible_by_default,
    is_conditionally_admissible,
    is_inadmissible,
    sidecar_for_handoff_binding,
    sidecar_for_repair,
    sidecar_from_action_output_intent,
    sidecar_from_adapter_fact,
    sidecar_from_candidate_io,
    sidecar_from_resource_contract_demand,
    sidecar_from_worker_contract_field,
)
from nl2spl.ir.worker_plan_ir import ContractFieldIR
from nl2spl.pipeline.stages.stage6_resource_extractor.declaration_authority import (
    build_authority_registry_from_worker_spec,
    filter_admissible_fields,
)


# ---------------------------------------------------------------------------
# Authority classification
# ---------------------------------------------------------------------------


class TestS6V25AuthorityClassification:
    """Verify the three authority tiers are correct."""

    def test_adapter_hard_fact_is_admissible(self) -> None:
        assert is_admissible_by_default("adapter_hard_fact")

    def test_resource_contract_demand_is_admissible(self) -> None:
        assert is_admissible_by_default("resource_contract_demand")

    def test_explicit_action_output_intent_is_admissible(self) -> None:
        assert is_admissible_by_default("explicit_action_output_intent")

    def test_llm_candidate_io_is_inadmissible(self) -> None:
        assert is_inadmissible("llm_candidate_io")

    def test_control_predicate_guess_is_inadmissible(self) -> None:
        assert is_inadmissible("control_predicate_guess")

    def test_read_context_only_is_inadmissible(self) -> None:
        assert is_inadmissible("read_context_only")

    def test_worker_handoff_binding_is_conditional(self) -> None:
        assert is_conditionally_admissible("worker_handoff_binding")

    def test_api_contract_response_is_conditional(self) -> None:
        assert is_conditionally_admissible("api_contract_response")

    def test_user_confirmed_repair_is_conditional(self) -> None:
        assert is_conditionally_admissible("user_confirmed_repair")

    def test_no_overlap_between_tiers(self) -> None:
        """Every authority belongs to exactly one tier."""
        all_authorities = (
            ADMISSIBLE_AUTHORITIES
            | CONDITIONALLY_ADMISSIBLE_AUTHORITIES
            | INADMISSIBLE_AUTHORITIES
        )
        # Verify disjointness
        assert not (ADMISSIBLE_AUTHORITIES & INADMISSIBLE_AUTHORITIES)
        assert not (ADMISSIBLE_AUTHORITIES & CONDITIONALLY_ADMISSIBLE_AUTHORITIES)
        assert not (CONDITIONALLY_ADMISSIBLE_AUTHORITIES & INADMISSIBLE_AUTHORITIES)
        # All 10 authorities must be classified
        assert len(all_authorities) == 10


# ---------------------------------------------------------------------------
# Sidecar creation
# ---------------------------------------------------------------------------


class TestS6V25SidecarCreation:
    """Verify sidecar factory functions produce correct defaults."""

    def test_adapter_fact_sidecar_is_admissible(self) -> None:
        sc = sidecar_from_adapter_fact("user_request", "text")
        assert sc.admissible_as_symbol is True
        assert sc.declaration_authority == "adapter_hard_fact"

    def test_resource_contract_demand_sidecar_is_admissible(self) -> None:
        sc = sidecar_from_resource_contract_demand("draft", "text", "rcd_001")
        assert sc.admissible_as_symbol is True
        assert sc.declaration_authority == "resource_contract_demand"
        assert sc.contract_demand_id == "rcd_001"

    def test_action_output_intent_sidecar_is_admissible(self) -> None:
        sc = sidecar_from_action_output_intent("results", "List[text]")
        assert sc.admissible_as_symbol is True
        assert sc.declaration_authority == "explicit_action_output_intent"

    def test_candidate_io_sidecar_is_inadmissible(self) -> None:
        sc = sidecar_from_candidate_io("sources_needed", "boolean")
        assert sc.admissible_as_symbol is False
        assert sc.declaration_authority == "llm_candidate_io"

    def test_handoff_binding_not_admitted_by_default(self) -> None:
        sc = sidecar_for_handoff_binding("result", "text")
        assert sc.admissible_as_symbol is False

    def test_handoff_binding_admitted_when_flagged(self) -> None:
        sc = sidecar_for_handoff_binding("result", "text", admitted=True)
        assert sc.admissible_as_symbol is True

    def test_repair_sidecar_is_admissible(self) -> None:
        sc = sidecar_for_repair("new_var", "text")
        assert sc.admissible_as_symbol is True
        assert sc.declaration_authority == "user_confirmed_repair"


# ---------------------------------------------------------------------------
# ContractFieldIR → sidecar
# ---------------------------------------------------------------------------


class TestS6V25ContractFieldToSidecar:
    """Verify sidecar_from_worker_contract_field logic."""

    def test_field_with_demand_id_is_admissible(self) -> None:
        field = ContractFieldIR(
            "draft", "text", True, "A draft.", "output",
            contract_demand_id="rcd_output_draft",
        )
        sc = sidecar_from_worker_contract_field(field)
        assert sc.admissible_as_symbol is True
        assert sc.declaration_authority == "resource_contract_demand"

    def test_field_with_only_span_evidence_is_inadmissible(self) -> None:
        """P1 fix: span evidence alone is NOT declaration authority.
        Without contract_demand_id or producer_intent_id, the field
        is llm_candidate_io → inadmissible."""
        field = ContractFieldIR(
            "results", "List[text]", True, "Results.", "output",
            source_span_ids=["s5"],
            # no contract_demand_id
        )
        sc = sidecar_from_worker_contract_field(field)
        assert sc.admissible_as_symbol is False
        assert sc.declaration_authority == "llm_candidate_io"

    def test_field_with_no_evidence_is_inadmissible(self) -> None:
        field = ContractFieldIR(
            "sources_needed", "boolean", False, "Whether sources needed.", "input",
            # no contract_demand_id, no source_span_ids, no section, no packet
        )
        sc = sidecar_from_worker_contract_field(field)
        assert sc.admissible_as_symbol is False
        assert sc.declaration_authority == "llm_candidate_io"

    def test_field_with_empty_source_span_ids_is_inadmissible(self) -> None:
        field = ContractFieldIR(
            "sources_needed", "boolean", False, "Whether sources needed.", "input",
            source_span_ids=[],  # empty list
        )
        sc = sidecar_from_worker_contract_field(field)
        assert sc.admissible_as_symbol is False

    def test_has_any_evidence_detects_empty(self) -> None:
        sc = sidecar_from_candidate_io("x", "text")
        assert sc.has_any_evidence() is False

    def test_has_any_evidence_detects_span(self) -> None:
        sc = sidecar_from_adapter_fact("x", "text", source_span_ids=("s1",))
        assert sc.has_any_evidence() is True


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestS6V25Registry:
    """Verify DeclarationAuthorityRegistry behavior."""

    def test_registry_is_admissible_checks_sidecar(self) -> None:
        reg = DeclarationAuthorityRegistry()
        reg.register(sidecar_from_adapter_fact("a", "text"))
        reg.register(sidecar_from_candidate_io("b", "boolean"))
        assert reg.is_admissible("a") is True
        assert reg.is_admissible("b") is False

    def test_registry_unknown_name_is_inadmissible(self) -> None:
        reg = DeclarationAuthorityRegistry()
        assert reg.is_admissible("unknown") is False

    def test_registry_authority_of(self) -> None:
        reg = DeclarationAuthorityRegistry()
        reg.register(sidecar_from_adapter_fact("a", "text"))
        assert reg.authority_of("a") == "adapter_hard_fact"
        assert reg.authority_of("unknown") is None

    def test_get_admissible_names(self) -> None:
        reg = DeclarationAuthorityRegistry()
        reg.register(sidecar_from_adapter_fact("a", "text"))
        reg.register(sidecar_from_candidate_io("b", "boolean"))
        reg.register(sidecar_from_resource_contract_demand("c", "text", "d1"))
        assert reg.get_admissible_names() == {"a", "c"}

    def test_get_inadmissible_names(self) -> None:
        reg = DeclarationAuthorityRegistry()
        reg.register(sidecar_from_adapter_fact("a", "text"))
        reg.register(sidecar_from_candidate_io("b", "boolean"))
        assert reg.get_inadmissible_names() == {"b"}

    def test_registry_sidecar_can_roundtrip_via_dict(self) -> None:
        """Sidecar can be serialized and reconstructed (for artifact
        persistence)."""
        sc = sidecar_from_adapter_fact(
            "x", "text", source_section_id="sec1", source_span_ids=("s1",),
        )
        d = asdict(sc)
        # JSON roundtrip (tuples become lists in JSON)
        json_str = json.dumps(d)
        d2 = json.loads(json_str)
        sc2 = DeclarationAuthoritySidecar(**d2)
        assert sc2.variable_name == "x"
        assert sc2.admissible_as_symbol is True
        # JSON doesn't preserve tuples — lists are fine
        assert list(sc2.source_span_ids) == ["s1"]


# ---------------------------------------------------------------------------
# Registry from worker spec
# ---------------------------------------------------------------------------


class TestS6V25RegistryFromWorkerSpec:
    """Verify build_authority_registry_from_worker_spec."""

    def test_worker_spec_with_evidenced_fields(self) -> None:
        from unittest.mock import MagicMock

        worker = MagicMock()
        worker.input_contract = [
            ContractFieldIR("query", "text", True, "Q", "input",
                            contract_demand_id="rcd_001"),
        ]
        worker.output_contract = [
            ContractFieldIR("results", "List[text]", True, "R", "output",
                            contract_demand_id="rcd_002"),
        ]

        reg = build_authority_registry_from_worker_spec(worker)
        assert reg.is_admissible("query") is True
        assert reg.is_admissible("results") is True

    def test_worker_spec_with_candidate_io(self) -> None:
        from unittest.mock import MagicMock

        worker = MagicMock()
        worker.input_contract = [
            ContractFieldIR("sources_needed", "boolean", False,
                            "Whether needed.", "input"),
        ]
        worker.output_contract = []

        reg = build_authority_registry_from_worker_spec(worker)
        assert reg.is_admissible("sources_needed") is False
        assert reg.authority_of("sources_needed") == "llm_candidate_io"


# ---------------------------------------------------------------------------
# Filter admissible fields
# ---------------------------------------------------------------------------


class TestS6V25FilterAdmissibleFields:
    """Verify filter_admissible_fields."""

    def test_mixed_fields_filtered_correctly(self) -> None:
        fields = [
            ContractFieldIR("query", "text", True, "Q", "input",
                            contract_demand_id="rcd_001"),
            ContractFieldIR("sources_needed", "boolean", False, "Flag", "input"),
            ContractFieldIR("results", "List[text]", True, "R", "output",
                            contract_demand_id="rcd_003"),
        ]
        admissible = filter_admissible_fields(fields)
        names = {getattr(f, "name") for f in admissible}
        assert names == {"query", "results"}, (
            f"S6V2.5: only fields with contract_demand_id should be "
            f"admissible, got {names}"
        )

    def test_empty_fields(self) -> None:
        assert filter_admissible_fields([]) == []


# ---------------------------------------------------------------------------
# "Not a blacklist" — same name, different authority
# ---------------------------------------------------------------------------


class TestS6V25NotABlacklist:
    """Prove that admissibility depends on authority metadata, not the
    variable name.  The same name can be admissible or inadmissible
    depending on how it enters the system."""

    def test_same_name_can_be_admissible_with_demand_id(self) -> None:
        """sources_needed with contract_demand_id is admissible
        (resource contract demand authority). This proves we are not
        blacklisting by name."""
        field = ContractFieldIR(
            "sources_needed", "boolean", True, "Flag.", "input",
            contract_demand_id="rcd_input_sources_needed",
        )
        sc = sidecar_from_worker_contract_field(field)
        assert sc.admissible_as_symbol is True, (
            "S6V2.5: sources_needed WITH contract_demand_id must be "
            "admissible. This proves we are not blacklisting by name."
        )

    def test_same_name_is_inadmissible_without_evidence(self) -> None:
        """sources_needed without evidence is inadmissible."""
        field = ContractFieldIR(
            "sources_needed", "boolean", False, "Flag.", "input",
            # no evidence
        )
        sc = sidecar_from_worker_contract_field(field)
        assert sc.admissible_as_symbol is False, (
            "S6V2.5: sources_needed WITHOUT evidence must be inadmissible."
        )
