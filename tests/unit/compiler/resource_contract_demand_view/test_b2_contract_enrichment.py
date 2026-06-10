"""Phase B2 tests — structural requiredness enrichment on RouteAnnotation."""

from __future__ import annotations

import pytest

from nl2spl.canonical.compile_input import (
    CanonicalCompileInput,
    EvidenceRef,
    HardFacts,
    SemanticPacket,
    VariableFact,
)
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage2_field_router import (
    _build_hard_fact_required_lookup,
    _normalize_to_variable_name,
)


# =============================================================================
# Test _normalize_to_variable_name
# =============================================================================


def test_normalize_simple_text() -> None:
    assert _normalize_to_variable_name("Topic summary") == "topic_summary"


def test_normalize_with_optional_prefix() -> None:
    assert _normalize_to_variable_name("Optional known topics") == "known_topics"


def test_normalize_with_slash() -> None:
    assert _normalize_to_variable_name("Word/Google Doc") == "word_google_doc"


def test_normalize_with_punctuation() -> None:
    assert _normalize_to_variable_name(
        "Finished draft (Word or Google Doc, 200-500 words)"
    ) == "finished_draft_word_or_google_doc_200_500_words"


# =============================================================================
# Test _build_hard_fact_required_lookup
# =============================================================================


def test_lookup_from_input_facts() -> None:
    facts = [
        VariableFact(
            name="topic_summary",
            description="Topic summary",
            data_type="text",
            required=True,
            source_section_id="sec_inputs",
            evidence=[
                EvidenceRef(
                    source_section_id="sec_inputs",
                    source_packet_id="p_list_item_topic_summary",
                ),
            ],
        ),
        VariableFact(
            name="known_topics",
            description="Known topics",
            data_type="text",
            required=False,
            source_section_id="sec_inputs",
            evidence=[
                EvidenceRef(
                    source_section_id="sec_inputs",
                    source_packet_id="p_list_item_known_topics",
                ),
            ],
        ),
    ]
    lookup = _build_hard_fact_required_lookup(facts)
    assert lookup == {
        "p_list_item_topic_summary": True,
        "p_list_item_known_topics": False,
    }


def test_lookup_empty() -> None:
    assert _build_hard_fact_required_lookup([]) == {}


# =============================================================================
# Test FieldRouter._enrich_contract_requiredness (integration-style)
# =============================================================================


def _span(sid: str, text: str) -> SpanIR:
    return SpanIR(span_id=sid, text=text, source_section_id="sec_inputs")


def _input_ann(sid: str) -> RouteAnnotation:
    return RouteAnnotation(
        span_id=sid,
        field="resources",
        semantic_role="input_contract",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="input",
        executable=False,
        source_section_id="sec_inputs",
    )


def _output_ann(sid: str) -> RouteAnnotation:
    return RouteAnnotation(
        span_id=sid,
        field="resources",
        semantic_role="output_contract",
        route_family="resource_contract",
        construct_target="RESOURCE_CONTRACT",
        slot_target="output",
        executable=False,
        source_section_id="sec_outputs",
    )


def _hard_fact_var(name: str, required: bool, packet_id: str) -> VariableFact:
    return VariableFact(
        name=name,
        description=name.replace("_", " ").title(),
        data_type="text",
        required=required,
        source_section_id="sec_inputs",
        evidence=[
            EvidenceRef(
                source_section_id="sec_inputs",
                source_packet_id=packet_id,
            ),
        ],
    )


def test_enrich_sets_requiredness_from_hard_facts() -> None:
    """Hard-fact VariableFact with provenance-aligned packet_id → requiredness."""
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [
        SpanIR(
            span_id="s1", text="Topic summary",
            source_section_id="sec_inputs",
            source_packet_id="p_list_item_topic",
        ),
    ]
    annotations = [_input_ann("s1")]

    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="",
        semantic_packets=[],  # no packet — falls through to hard_facts
        hard_facts=HardFacts(
            inputs=[_hard_fact_var("topic_summary", True, "p_list_item_topic")],
            outputs=[],
        ),
    )

    FieldRouter._enrich_contract_requiredness(annotations, spans, ci)

    assert annotations[0].metadata.get("requiredness") == "required"


def test_enrich_sets_optional_from_hard_facts() -> None:
    """Hard fact with required=False + packet_id match → requiredness=optional."""
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [
        SpanIR(
            span_id="s2", text="Optional known topics",
            source_section_id="sec_inputs",
            source_packet_id="p_list_item_known",
        ),
    ]
    annotations = [_input_ann("s2")]

    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="",
        semantic_packets=[],
        hard_facts=HardFacts(
            inputs=[_hard_fact_var("known_topics", False, "p_list_item_known")],
            outputs=[],
        ),
    )

    FieldRouter._enrich_contract_requiredness(annotations, spans, ci)

    assert annotations[0].metadata.get("requiredness") == "optional"


def test_hard_fact_same_text_different_packet_no_enrichment() -> None:
    """Same text but different packet_id → no enrichment (provenance mismatch)."""
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [
        SpanIR(
            span_id="s9", text="Topic summary",
            source_section_id="sec_inputs",
            source_packet_id="p_different_packet",  # not in evidence
        ),
    ]
    annotations = [_input_ann("s9")]

    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="",
        semantic_packets=[],  # no primary match
        hard_facts=HardFacts(
            inputs=[_hard_fact_var("topic_summary", True, "p_list_item_topic")],
            outputs=[],
        ),
    )

    FieldRouter._enrich_contract_requiredness(annotations, spans, ci)

    assert "requiredness" not in annotations[0].metadata


def test_enrich_leaves_unmatched_span_unspecified() -> None:
    """Span text has no matching VariableFact → requiredness not set."""
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [_span("s3", "Unlisted input")]
    annotations = [_input_ann("s3")]

    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="",
        hard_facts=HardFacts(inputs=[], outputs=[]),
    )

    FieldRouter._enrich_contract_requiredness(annotations, spans, ci)

    assert "requiredness" not in annotations[0].metadata


def test_enrich_skips_non_contract_annotations() -> None:
    """Only input_contract/output_contract annotations are enriched."""
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [_span("s4", "Some step")]
    annotations = [
        RouteAnnotation(
            span_id="s4",
            field="behavior",
            semantic_role="process_step",
            executable=True,
        ),
    ]

    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="",
        hard_facts=HardFacts(
            inputs=[
                VariableFact(
                    name="some_step",
                    description="Some step",
                    data_type="text",
                    required=True,
                    source_section_id="sec_inputs",
                ),
            ],
            outputs=[],
        ),
    )

    FieldRouter._enrich_contract_requiredness(annotations, spans, ci)

    # Non-contract annotation should remain untouched
    assert "requiredness" not in annotations[0].metadata


def test_enrich_output_contract() -> None:
    """Output contract annotations enriched from hard_facts via packet_id."""
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [
        SpanIR(
            span_id="s5", text="Finished draft",
            source_section_id="sec_outputs",
            source_packet_id="p_list_item_draft",
        ),
    ]
    annotations = [_output_ann("s5")]

    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="",
        semantic_packets=[],
        hard_facts=HardFacts(
            inputs=[],
            outputs=[
                VariableFact(
                    name="finished_draft",
                    description="Finished draft",
                    data_type="text",
                    required=True,
                    source_section_id="sec_outputs",
                    evidence=[
                        EvidenceRef(
                            source_section_id="sec_outputs",
                            source_packet_id="p_list_item_draft",
                        ),
                    ],
                ),
            ],
        ),
    )

    FieldRouter._enrich_contract_requiredness(annotations, spans, ci)

    assert annotations[0].metadata.get("requiredness") == "required"


def test_enrich_no_hard_facts_no_enrichment() -> None:
    """Empty hard facts and no matching packet → no enrichment."""
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [_span("s6", "Topic summary")]
    annotations = [_input_ann("s6")]

    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="",
        semantic_packets=[],  # no packet match
        hard_facts=HardFacts(inputs=[], outputs=[]),
    )

    FieldRouter._enrich_contract_requiredness(annotations, spans, ci)

    assert "requiredness" not in annotations[0].metadata


# =============================================================================
# Test: real _execute_canonical path with default adapter output
# =============================================================================


def test_real_execute_enrichment_from_packet_required() -> None:
    """Default structural NL path: adapter creates list_item packets with
    required=True for Required Outputs items.  Enrichment reads packet.required
    via provenance-aligned packet_id match."""
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [
        SpanIR(
            span_id="s1",
            text="Finished draft (Word or Google Doc)",
            source_section_id="sec_outputs",
            source_packet_id="p_list_item_finished_draft",
        ),
        SpanIR(
            span_id="s2",
            text="Topic summary",
            source_section_id="sec_inputs",
            source_packet_id="p_list_item_topic_summary",
        ),
    ]

    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Inputs:\n- Topic summary\n\nRequired Outputs:\n- Finished draft",
        raw_sections=[],
        semantic_packets=[
            SemanticPacket(
                packet_id="p_list_item_finished_draft",
                source_section_id="sec_outputs",
                packet_type="list_item",
                text="Finished draft (Word or Google Doc)",
                modality="hint",
                required=True,
            ),
            SemanticPacket(
                packet_id="p_list_item_topic_summary",
                source_section_id="sec_inputs",
                packet_type="list_item",
                text="Topic summary",
                modality="hint",
                required=True,
            ),
        ],
        hard_facts=HardFacts(inputs=[], outputs=[]),
    )

    annotations = [
        RouteAnnotation(
            span_id="s1",
            field="resources",
            semantic_role="output_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="output",
            executable=False,
            source_section_id="sec_outputs",
            source_packet_id="p_list_item_finished_draft",
        ),
        RouteAnnotation(
            span_id="s2",
            field="resources",
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
            source_section_id="sec_inputs",
            source_packet_id="p_list_item_topic_summary",
        ),
    ]

    FieldRouter._enrich_contract_requiredness(annotations, spans, ci)

    assert annotations[0].metadata.get("requiredness") == "required"
    assert annotations[1].metadata.get("requiredness") == "required"


def test_real_execute_enrichment_optional_input() -> None:
    """Adapter sets required=False for input starting with 'Optional'."""
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [
        SpanIR(
            span_id="s3",
            text="Optional known topics",
            source_section_id="sec_inputs",
            source_packet_id="p_list_item_known_topics",
        ),
    ]
    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Inputs:\n- Optional known topics",
        raw_sections=[],
        semantic_packets=[
            SemanticPacket(
                packet_id="p_list_item_known_topics",
                source_section_id="sec_inputs",
                packet_type="list_item",
                text="Optional known topics",
                modality="hint",
                required=False,
            ),
        ],
        hard_facts=HardFacts(inputs=[], outputs=[]),
    )

    annotations = [
        RouteAnnotation(
            span_id="s3",
            field="resources",
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
            source_section_id="sec_inputs",
            source_packet_id="p_list_item_known_topics",
        ),
    ]

    FieldRouter._enrich_contract_requiredness(annotations, spans, ci)

    assert annotations[0].metadata.get("requiredness") == "optional"


def test_no_packet_match_no_enrichment_real_path() -> None:
    """When the span's source_packet_id has no matching packet, no enrichment."""
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [
        SpanIR(
            span_id="s4",
            text="Unmapped item",
            source_section_id="sec_unknown",
            source_packet_id="p_nonexistent",
        ),
    ]
    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="",
        raw_sections=[],
        semantic_packets=[],
        hard_facts=HardFacts(inputs=[], outputs=[]),
    )

    annotations = [
        RouteAnnotation(
            span_id="s4",
            field="resources",
            semantic_role="input_contract",
            route_family="resource_contract",
            construct_target="RESOURCE_CONTRACT",
            slot_target="input",
            executable=False,
            source_section_id="sec_unknown",
            source_packet_id="p_nonexistent",
        ),
    ]

    FieldRouter._enrich_contract_requiredness(annotations, spans, ci)

    assert "requiredness" not in annotations[0].metadata


# =============================================================================
# Test: FieldRouter.execute() with mocked LLM (true integration path)
# =============================================================================


def test_execute_with_mocked_llm_produces_requiredness() -> None:
    """FieldRouter.execute() with mocked LLM → annotation.metadata["requiredness"]
    must be populated from packet.required."""
    from unittest.mock import MagicMock

    from nl2spl.ir.field_route_ir import RouteAnnotation
    from nl2spl.config import PipelineConfig
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [
        SpanIR(
            span_id="s1",
            text="Finished draft",
            source_section_id="sec_outputs",
            source_packet_id="p_list_item_finished_draft",
        ),
    ]
    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Required Outputs:\n- Finished draft",
        raw_sections=[],
        semantic_packets=[
            SemanticPacket(
                packet_id="p_list_item_finished_draft",
                source_section_id="sec_outputs",
                packet_type="list_item",
                text="Finished draft",
                modality="hint",
                required=True,
            ),
        ],
        hard_facts=HardFacts(inputs=[], outputs=[]),
    )

    config = PipelineConfig()
    mock_client = MagicMock()
    mock_client.call_json.return_value = {
        "annotations": [
            {
                "span_id": "s1",
                "semantic_role": "output_contract",
                "field": "resources",
                "route_family": "resource_contract",
                "construct_target": "RESOURCE_CONTRACT",
                "slot_target": "output",
                "executable": False,
            },
        ],
    }

    router = FieldRouter(config, mock_client)
    routes, _amb = router.execute((spans, ci))

    # Find the output_contract annotation
    contract_anns = [
        a for a in routes.annotations
        if a.semantic_role == "output_contract"
    ]
    assert len(contract_anns) == 1, f"Expected 1 contract ann, got {len(contract_anns)}"
    assert contract_anns[0].metadata.get("requiredness") == "required", (
        f"Expected requiredness=required, got {contract_anns[0].metadata}"
    )


def test_execute_with_optional_input_llm_annotation() -> None:
    """FieldRouter.execute() with mocked LLM and optional input → requiredness=optional."""
    from unittest.mock import MagicMock

    from nl2spl.config import PipelineConfig
    from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

    spans = [
        SpanIR(
            span_id="s3",
            text="Optional known topics",
            source_section_id="sec_inputs",
            source_packet_id="p_list_item_known_topics",
        ),
    ]
    ci = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0",
        raw_text="Inputs:\n- Optional known topics",
        raw_sections=[],
        semantic_packets=[
            SemanticPacket(
                packet_id="p_list_item_known_topics",
                source_section_id="sec_inputs",
                packet_type="list_item",
                text="Optional known topics",
                modality="hint",
                required=False,
            ),
        ],
        hard_facts=HardFacts(inputs=[], outputs=[]),
    )

    config = PipelineConfig()
    mock_client = MagicMock()
    mock_client.call_json.return_value = {
        "annotations": [
            {
                "span_id": "s3",
                "semantic_role": "input_contract",
                "field": "resources",
                "route_family": "resource_contract",
                "construct_target": "RESOURCE_CONTRACT",
                "slot_target": "input",
                "executable": False,
            },
        ],
    }

    router = FieldRouter(config, mock_client)
    routes, _amb = router.execute((spans, ci))

    contract_anns = [
        a for a in routes.annotations
        if a.semantic_role == "input_contract"
    ]
    assert len(contract_anns) == 1
    assert contract_anns[0].metadata.get("requiredness") == "optional"
