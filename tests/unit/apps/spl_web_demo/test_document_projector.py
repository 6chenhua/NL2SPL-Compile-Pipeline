"""Unit tests for SplDocumentProjector and `/spl-document` API."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "apps" / "spl-web-demo" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from spl_web_demo.card_projector import CardProjector  # noqa: E402
from spl_web_demo.document_projector import SplDocumentProjector  # noqa: E402
from spl_web_demo.provenance_projector import ProvenanceProjector  # noqa: E402

from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot  # noqa: E402
from nl2spl.compiler.spl_render_contract import (  # noqa: E402
    is_renderable_optional_profile_item,
)
from nl2spl.ir.agent_profile_ir import (  # noqa: E402
    AgentProfileIR,
    Aspect,
    Concept,
    PersonaIR,
)
from nl2spl.ir.block_structure_ir import BlockIR  # noqa: E402
from nl2spl.ir.constraint_ir import ConstraintIR  # noqa: E402
from nl2spl.ir.resource_registry_ir import (  # noqa: E402
    ResourceRegistryIR,
    VariableSpec,
)
from nl2spl.ir.step_ir import StepIR  # noqa: E402
from nl2spl.ir.symbol_table import SymbolTable  # noqa: E402
from nl2spl.ir.worker_ir import FlowRef, WorkerIR, WorkerOutput  # noqa: E402


def _snapshot() -> ArtifactSnapshot:
    steps = [
        StepIR(
            step_id="st1",
            text="Collect the approved source material.",
            source_span_ids=["span-step"],
            command_type="GENERAL_COMMAND",
            flow_ref="main",
            block_ref="b1",
            outputs=["source_material"],
        )
    ]
    return ArtifactSnapshot(
        snapshot_id="snap-test",
        compile_run_id="run-test",
        overlay_version=0,
        final_worker=WorkerIR(
            worker_name="MainWorker",
            description="Coordinate the workflow.",
            outputs=[
                WorkerOutput(
                    name="newsletter",
                    required=True,
                    requiredness="required",
                ),
                WorkerOutput(
                    name="delivery_notes",
                    required=False,
                    requiredness="optional",
                ),
            ],
            main_flow=FlowRef(
                blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="SEQUENTIAL",
                        spans=["span-step"],
                    )
                ]
            ),
            steps=steps,
        ),
        agent_profile=AgentProfileIR(
            persona=PersonaIR(
                role="Internal communications specialist",
                source_span_ids=["span-profile"],
                provenance_relation="direct",
                aspects=[
                    Aspect(
                        name="Tone",
                        text="Professional and helpful",
                        source_span_ids=["span-aspect"],
                        provenance_relation="direct",
                    ),
                ],
            ),
            audience_aspects=[
                Aspect(
                    name="InternalUsers",
                    text="Internal communications team",
                    source_span_ids=["span-audience"],
                    provenance_relation="direct",
                )
            ],
            concepts=[
                Concept(
                    term="InternalNewsletters",
                    definition="Weekly briefing newsletter",
                    source_span_ids=["span-concept"],
                    provenance_relation="direct",
                )
            ],
        ),
        constraints=(
            ConstraintIR(
                constraint_id="c1",
                text="Use only approved evidence.",
                kind="evidence",
                source_span_ids=["span-constraint"],
            ),
        ),
        resources=ResourceRegistryIR(
            variables=[
                VariableSpec(
                    name="source_material",
                    data_type="text",
                    required=True,
                    source="inferred",
                    description="Approved source material",
                ),
            ],
        ),
    )


# ── Source-backed filtering ────────────────────────────────────────────


def test_is_source_backed_with_spans_and_valid_relation() -> None:
    aspect = Aspect(
        name="Tone",
        text="Professional",
        source_span_ids=["s1"],
    )
    aspect.provenance_relation = "direct"
    assert is_renderable_optional_profile_item(aspect) is True


def test_is_source_backed_no_spans() -> None:
    aspect = Aspect(
        name="GhostAspect",
        text="No evidence",
        source_span_ids=[],
    )
    aspect.provenance_relation = "direct"
    assert is_renderable_optional_profile_item(aspect) is False


def test_is_source_backed_assumed_relation() -> None:
    aspect = Aspect(
        name="AssumedAspect",
        text="Has spans but assumed provenance",
        source_span_ids=["s1"],
    )
    aspect.provenance_relation = "assumed"
    assert is_renderable_optional_profile_item(aspect) is False


# ── Document hierarchy ──────────────────────────────────────────────────


def test_project_document_hierarchy() -> None:
    snapshot = _snapshot()
    card_projector = CardProjector()
    base_cards = card_projector.project_snapshot(snapshot)

    projector = SplDocumentProjector()
    result = projector.project_document(snapshot, base_cards)

    assert result.fidelity == "render_aligned"
    assert len(result.nodes) > 0

    base_refs = {card.construct_ref for card in base_cards}
    extra_refs = [card.construct_ref for card in result.extra_cards]
    assert len(extra_refs) == len(set(extra_refs))
    assert base_refs.isdisjoint(extra_refs)

    node_types = {node.node_type for node in result.nodes}
    assert "AGENT" in node_types

    # Grammar-level sections are present (no artificial wrappers)
    assert "PERSONA" in node_types
    assert "PERSONA_ASPECT" in node_types
    assert "AUDIENCE" in node_types
    assert "AUDIENCE_ASPECT" in node_types
    assert "CONCEPTS" in node_types
    assert "CONCEPT" in node_types
    assert "CONSTRAINTS" in node_types
    assert "CONSTRAINT" in node_types
    assert "WORKER" in node_types

    # PROFILE, RESOURCES, WORKERS must NOT appear as visible nodes
    assert "PROFILE" not in node_types
    assert "RESOURCES" not in node_types
    assert "WORKERS" not in node_types

    # PERSONA is a direct child of AGENT (not wrapped in PROFILE)
    persona_node = next(node for node in result.nodes if node.node_type == "PERSONA")
    assert persona_node.parent_node_ref == "agent:main"

    persona_card = next(
        card for card in result.extra_cards if card.construct_ref == persona_node.construct_ref
    )
    assert persona_card.construct_type == "PERSONA"
    assert persona_card.trace_target_refs == ("profile:persona",)

    # Persona aspect — only source-backed items appear
    aspect_node = next(node for node in result.nodes if node.node_type == "PERSONA_ASPECT")
    assert aspect_node.title == "Tone"
    assert aspect_node.summary == "Professional and helpful"
    assert aspect_node.node_kind == "construct"
    assert aspect_node.construct_ref is not None
    assert aspect_node.provenance_summary == {"kind": "source_backed", "source_span_count": 1}

    # Audience aspect
    aud_node = next(node for node in result.nodes if node.node_type == "AUDIENCE_ASPECT")
    assert aud_node.title == "InternalUsers"
    assert aud_node.summary == "Internal communications team"

    # Concept
    concept_node = next(node for node in result.nodes if node.node_type == "CONCEPT")
    assert concept_node.title == "InternalNewsletters"
    assert concept_node.summary == "Weekly briefing newsletter"

    # Optional output
    optional_output = next(
        node
        for node in result.nodes
        if node.node_type == "OUTPUT" and node.title == "delivery_notes"
    )
    assert optional_output.construct_ref is not None

    # Constraint shows grammar-visible kind as title, not internal targets
    constraint_node = next(node for node in result.nodes if node.node_type == "CONSTRAINT")
    assert constraint_node.title == "Evidence"  # kind.capitalize()
    assert constraint_node.summary == "Use only approved evidence."
    # Internal targets are preserved in attributes for Inspector
    assert "targets" in constraint_node.attributes

    # COMMAND has structured RESULT
    command_node = next(node for node in result.nodes if node.node_type == "COMMAND")
    assert "result" in command_node.attributes
    assert isinstance(command_node.attributes["result"], list)
    assert len(command_node.attributes["result"]) == 1
    result_item = command_node.attributes["result"][0]
    assert result_item["keyword"] == "RESULT"
    assert result_item["name"] == "source_material"
    assert result_item["data_type"] == "text"
    assert result_item["assignment"] == "SET"


# ── Unrendered items are excluded ───────────────────────────────────────


def test_unrendered_aspects_are_excluded() -> None:
    """Aspects without source spans must not appear in the document."""
    snapshot = _snapshot()
    # Insert before the source-backed aspect to prove trace indexes are not compacted.
    snapshot.agent_profile.persona.aspects.insert(
        0,
        Aspect(
            name="GhostTrait",
            text="No evidence for this trait",
            source_span_ids=[],
            provenance_relation="assumed",
        ),
    )

    card_projector = CardProjector()
    base_cards = card_projector.project_snapshot(snapshot)
    projector = SplDocumentProjector()
    result = projector.project_document(snapshot, base_cards)

    aspect_nodes = [n for n in result.nodes if n.node_type == "PERSONA_ASPECT"]
    aspect_titles = {n.title for n in aspect_nodes}
    assert "Tone" in aspect_titles  # source-backed → present
    assert "GhostTrait" not in aspect_titles  # no spans → excluded
    tone_card = next(card for card in result.extra_cards if card.title == "Tone")
    assert tone_card.trace_target_refs == ("profile:persona.aspect:1",)


def test_unrendered_concepts_are_excluded() -> None:
    """Concepts without source spans must not appear in the document."""
    snapshot = _snapshot()
    snapshot.agent_profile.concepts.insert(
        0,
        Concept(
            term="GhostConcept",
            definition="No evidence",
            source_span_ids=[],
            provenance_relation="assumed",
        ),
    )

    card_projector = CardProjector()
    base_cards = card_projector.project_snapshot(snapshot)
    projector = SplDocumentProjector()
    result = projector.project_document(snapshot, base_cards)

    concept_nodes = [n for n in result.nodes if n.node_type == "CONCEPT"]
    concept_titles = {n.title for n in concept_nodes}
    assert "InternalNewsletters" in concept_titles  # source-backed → present
    assert "GhostConcept" not in concept_titles  # no spans → excluded
    concept_card = next(card for card in result.extra_cards if card.title == "InternalNewsletters")
    assert concept_card.trace_target_refs == ("profile:concept:1",)


def test_command_without_outputs_has_no_result() -> None:
    """COMMAND nodes without StepIR.outputs must not carry a result attribute."""
    snapshot = _snapshot()
    # Replace the step with one that has no outputs
    snapshot.final_worker.steps[0] = StepIR(
        step_id="st_no_out",
        text="Just do something.",
        source_span_ids=["span-step"],
        command_type="GENERAL_COMMAND",
        flow_ref="main",
        block_ref="b1",
        outputs=[],
    )

    card_projector = CardProjector()
    base_cards = card_projector.project_snapshot(snapshot)
    projector = SplDocumentProjector()
    result = projector.project_document(snapshot, base_cards)

    command_node = next(node for node in result.nodes if node.node_type == "COMMAND")
    assert "result" not in command_node.attributes


@pytest.mark.parametrize(
    ("command_type", "expected_keyword"),
    [
        ("GENERAL_COMMAND", "RESULT"),
        ("CALL_API", "RESPONSE"),
        ("INVOKE_WORKER", "RESPONSE"),
        ("REQUEST_INPUT", "VALUE"),
    ],
)
def test_command_result_keyword_matches_stage11(
    command_type: str,
    expected_keyword: str,
) -> None:
    snapshot = _snapshot()
    step = snapshot.final_worker.steps[0]
    step.command_type = command_type
    step.integration_ref = "Target" if command_type != "GENERAL_COMMAND" else None

    base_cards = CardProjector().project_snapshot(snapshot)
    result = SplDocumentProjector().project_document(snapshot, base_cards)

    command_node = next(node for node in result.nodes if node.node_type == "COMMAND")
    assert command_node.attributes["result"][0]["keyword"] == expected_keyword


def test_request_input_without_output_uses_stage11_default_value() -> None:
    snapshot = _snapshot()
    step = snapshot.final_worker.steps[0]
    step.command_type = "REQUEST_INPUT"
    step.outputs = []

    base_cards = CardProjector().project_snapshot(snapshot)
    result = SplDocumentProjector().project_document(snapshot, base_cards)

    command_node = next(node for node in result.nodes if node.node_type == "COMMAND")
    assert command_node.attributes["result"] == [
        {
            "keyword": "VALUE",
            "name": "user_input",
            "data_type": "text",
            "assignment": "SET",
        }
    ]


def test_command_result_type_includes_symbol_table_declarations() -> None:
    snapshot = _snapshot()
    snapshot.final_worker.steps[0].outputs = ["symbol_only_result"]
    symbols = SymbolTable()
    symbols.declare(
        name="symbol_only_result",
        data_type="number",
        source="step",
        description="Declared by normalization.",
    )
    snapshot = replace(snapshot, symbol_table=symbols)

    base_cards = CardProjector().project_snapshot(snapshot)
    result = SplDocumentProjector().project_document(snapshot, base_cards)

    command_node = next(node for node in result.nodes if node.node_type == "COMMAND")
    assert command_node.attributes["result"][0]["data_type"] == "number"


def test_multiword_constraint_kind_uses_grammar_aspect_name() -> None:
    snapshot = _snapshot()
    snapshot.constraints[0].kind = "delegation_boundary"

    base_cards = CardProjector().project_snapshot(snapshot)
    result = SplDocumentProjector().project_document(snapshot, base_cards)

    constraint_node = next(node for node in result.nodes if node.node_type == "CONSTRAINT")
    assert constraint_node.title == "DelegationBoundary"


def test_multiple_command_outputs_fail_closed() -> None:
    snapshot = _snapshot()
    snapshot.final_worker.steps[0].outputs = ["one", "two"]

    base_cards = CardProjector().project_snapshot(snapshot)
    with pytest.raises(ValueError, match="requires at most one output"):
        SplDocumentProjector().project_document(snapshot, base_cards)


def test_duplicate_node_ref_is_rejected() -> None:
    """The buildTree function in the frontend is the authority, but the
    backend must not emit duplicate node_refs."""
    snapshot = _snapshot()
    card_projector = CardProjector()
    base_cards = card_projector.project_snapshot(snapshot)
    projector = SplDocumentProjector()
    result = projector.project_document(snapshot, base_cards)

    refs = [node.node_ref for node in result.nodes]
    assert len(refs) == len(set(refs)), f"Duplicate node_refs: {refs}"


def test_canonical_document_keeps_rendered_profile_trace_indexes() -> None:
    snapshot_path = REPO_ROOT / "examples" / "output" / "demo" / "spl_editing_snapshot.json"
    card_projector = CardProjector()
    snapshot = card_projector.load_snapshot_file(snapshot_path)
    base_cards = card_projector.project_snapshot(snapshot)

    document = SplDocumentProjector().project_document(snapshot, base_cards)
    assert sum(node.node_type == "PERSONA_ASPECT" for node in document.nodes) == 1
    assert sum(node.node_type == "CONCEPT" for node in document.nodes) == 5

    structured_card = next(
        card for card in document.extra_cards if card.title == "StructuredCompletion"
    )
    assert structured_card.trace_target_refs == ("profile:persona.aspect:3",)

    provenance = ProvenanceProjector().project_snapshot(
        snapshot,
        base_cards + document.extra_cards,
    )
    structured_provenance = provenance.get_construct(structured_card.construct_ref)
    assert structured_provenance is not None
    assert structured_provenance.provenance_kind == "derived"
    assert structured_provenance.source_span_ids == ("s24",)
    assert structured_provenance.traces[0].explanation == ("Persona aspect: StructuredCompletion")

    request_input = next(
        node
        for node in document.nodes
        if node.node_type == "COMMAND" and node.attributes["step_id"] == "st_3"
    )
    assert request_input.attributes["result"][0]["keyword"] == "VALUE"

    delegation_constraint = next(
        node
        for node in document.nodes
        if node.node_type == "CONSTRAINT" and node.attributes["kind"] == "delegation_boundary"
    )
    assert delegation_constraint.title == "DelegationBoundary"
