from __future__ import annotations

from nl2spl.compiler.capability_intent.model import (
    CapabilityEvidenceCandidateIR,
    CapabilityEvidenceIR,
    EarlyCapabilityEvidenceView,
    ExternalCapabilityExtractionResult,
    ExternalCapabilityIntentCandidateIR,
)
from nl2spl.compiler.capability_intent.resolver import (
    ExternalCapabilityIntentResolver,
)
from nl2spl.compiler.resource_contract_demand_view.model import (
    DemandViewDemand,
    ResourceContractDemandView,
)


def _candidate(
    candidate_id: str = "c1",
    span_id: str = "s1",
) -> ExternalCapabilityIntentCandidateIR:
    evidence = tuple(
        CapabilityEvidenceIR(
            evidence_id=f"{candidate_id}_{claim}",
            source_span_id=span_id,
            claim=claim,
            surface_text=(
                "RecordsAPI"
                if claim in {"boundary", "identity"}
                else "retrieve records"
            ),
            relation="direct",
        )
        for claim in ("operation", "boundary", "identity", "invocation")
    )
    return ExternalCapabilityIntentCandidateIR(
        candidate_id=candidate_id,
        source_span_ids=(span_id,),
        operation_surface="retrieve records",
        operation_text="retrieve records",
        capability_surface="RecordsAPI",
        capability_ref_candidate="RecordsAPI",
        boundary_claim="external",
        identity_claim="explicit_name",
        invocation_claim="executable",
        evidence=evidence,
        source_section_id="section_process",
    )


def test_resolver_confirms_named_invocation_and_preserves_unbound_status() -> None:
    demand_view = ResourceContractDemandView(
        demands=(
            DemandViewDemand(
                demand_id="rcd_input_s1",
                direction="input",
                requiredness="required",
                required=True,
                evidence_text="records",
                source_span_ids=("s1",),
                resource_ref=None,
            ),
        )
    )
    plan = ExternalCapabilityIntentResolver().resolve(
        source_schema="generic_nl",
        extraction=ExternalCapabilityExtractionResult(candidates=(_candidate(),)),
        early_evidence=EarlyCapabilityEvidenceView(),
        demand_view=demand_view,
    )

    intent = plan.intents[0]
    assert intent.capability_admission_status == "confirmed_capability"
    assert intent.invocation_admission_status == "confirmed_invocation"
    assert intent.binding_status == "unbound"
    assert intent.unresolved_binding_claims == ("input:rcd_input_s1",)
    assert plan.candidate_resolution_map == {"c1": intent.intent_id}


def test_resolver_is_order_stable_and_exact_ref_merge_is_deterministic() -> None:
    first = _candidate("c1", "s1")
    second = _candidate("c2", "s2")
    resolver = ExternalCapabilityIntentResolver()

    left = resolver.resolve(
        source_schema="generic_nl",
        extraction=ExternalCapabilityExtractionResult(candidates=(first, second)),
        early_evidence=EarlyCapabilityEvidenceView(),
        demand_view=ResourceContractDemandView(),
    )
    right = resolver.resolve(
        source_schema="generic_nl",
        extraction=ExternalCapabilityExtractionResult(candidates=(second, first)),
        early_evidence=EarlyCapabilityEvidenceView(),
        demand_view=ResourceContractDemandView(),
    )

    assert left.to_payload() == right.to_payload()
    assert len(left.intents) == 1
    assert left.intents[0].source_candidate_ids == ("c1", "c2")


def test_policy_only_never_becomes_call_admission() -> None:
    candidate = _candidate()
    candidate = ExternalCapabilityIntentCandidateIR(
        **{
            **candidate.__dict__,
            "invocation_claim": "policy_only",
        }
    )
    plan = ExternalCapabilityIntentResolver().resolve(
        source_schema="generic_nl",
        extraction=ExternalCapabilityExtractionResult(candidates=(candidate,)),
        early_evidence=EarlyCapabilityEvidenceView(),
        demand_view=None,
    )

    assert plan.intents[0].capability_admission_status == "confirmed_capability"
    assert plan.intents[0].invocation_admission_status == "no_invocation"


def test_source_retrieval_output_ref_can_be_inferred_from_source_backed_demand() -> None:
    demand_view = ResourceContractDemandView(
        demands=(
            DemandViewDemand(
                demand_id="rcd_output_s1",
                direction="output",
                requiredness="required",
                required=True,
                evidence_text="a source/evidence set",
                source_span_ids=("s9",),
                source_packet_id="p_list_item_source_evidence_set",
                resource_ref=None,
            ),
        )
    )
    candidate = _candidate()
    candidate = ExternalCapabilityIntentCandidateIR(
        **{
            **candidate.__dict__,
            "operation_text": "retrieve them using approved source recipes",
            "operation_surface": "retrieve them using approved source recipes",
        }
    )

    plan = ExternalCapabilityIntentResolver().resolve(
        source_schema="generic_nl",
        extraction=ExternalCapabilityExtractionResult(candidates=(candidate,)),
        early_evidence=EarlyCapabilityEvidenceView(),
        demand_view=demand_view,
    )

    intent = plan.intents[0]
    assert intent.output_refs == ("source_evidence_set",)
    assert intent.binding_status == "fully_bound"
    assert intent.unresolved_binding_claims == ()


def test_extractor_unavailable_with_only_route_clue_does_not_create_intent() -> None:
    early = EarlyCapabilityEvidenceView(
        candidates=(
            CapabilityEvidenceCandidateIR(
                evidence_id="early1",
                source_span_id="s1",
                source_hint_ids=(),
                surface_text="Use RecordsAPI",
                claim_hint="possible_boundary",
                origin="stage2_annotation",
            ),
        )
    )
    plan = ExternalCapabilityIntentResolver().resolve(
        source_schema="generic_nl",
        extraction=ExternalCapabilityExtractionResult(
            status="unavailable",
            failure_reason="timeout",
        ),
        early_evidence=early,
        demand_view=None,
    )

    assert plan.intents == ()
    assert plan.diagnostics[0].kind == "capability_intent_extraction_unavailable"


def test_extractor_unavailable_without_early_clue_is_suppressed() -> None:
    plan = ExternalCapabilityIntentResolver().resolve(
        source_schema="generic_nl",
        extraction=ExternalCapabilityExtractionResult(
            status="unavailable",
            failure_reason="timeout",
        ),
        early_evidence=EarlyCapabilityEvidenceView(),
        demand_view=None,
    )

    assert plan.intents == ()
    assert plan.diagnostics == ()
    assert plan.metadata["suppressed_without_early_evidence"] is True
