"""Structured document projection for SPL Web Demo.

Projects a render-aligned structured SPL document from ArtifactSnapshot IR.
Only constructs that Stage 11 would render appear as document nodes; unrendered
Stage IR inventory items are excluded.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_render_contract import (
    REQUEST_INPUT_DEFAULT_RESULT_NAME,
    REQUEST_INPUT_DEFAULT_RESULT_TYPE,
    build_result_type_lookup,
    command_result_keyword,
    grammar_aspect_name,
    is_renderable_optional_profile_item,
)
from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import (
    AlternativeFlowRef,
    BlockIR,
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerIR,
)
from spl_web_demo.card_projector import (
    CardProvenanceSummary,
    SplConstructCard,
    _block_ref,
    _command_ref,
    _construct_ref,
    _flow_ref,
    _flow_span_ids,
    _is_required_output,
    _span_ids,
    _worker_ref,
)


@dataclass(frozen=True)
class SplDocumentNode:
    node_ref: str
    node_kind: Literal["section", "construct"]
    node_type: str
    construct_ref: str | None
    parent_node_ref: str | None
    order: int
    title: str
    summary: str | None
    status: Literal["available", "partial", "review_only"]
    attributes: dict[str, Any]
    provenance_summary: dict[str, Any] | None


@dataclass(frozen=True)
class SplDocumentReadModel:
    nodes: tuple[SplDocumentNode, ...]
    fidelity: Literal["structured", "render_aligned", "partial"]
    extra_cards: tuple[SplConstructCard, ...]


def _summary_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


class SplDocumentProjector:
    """Project the render-aligned SPL document hierarchy from ArtifactSnapshot IR.

    Only constructs that Stage 11 would render appear as document nodes.
    Layout-only grouping nodes (PROFILE, RESOURCES, WORKERS) are not emitted.
    """

    def project_document(
        self, snapshot: ArtifactSnapshot, base_cards: tuple[SplConstructCard, ...]
    ) -> SplDocumentReadModel:
        nodes: list[SplDocumentNode] = []
        extra_cards: list[SplConstructCard] = []

        result_types = build_result_type_lookup(snapshot.resources, snapshot.symbol_table)

        # 1. AGENT node (root)
        agent_title = "Agent"
        agent_desc = None
        if isinstance(snapshot.final_worker, WorkerIR):
            agent_title = snapshot.final_worker.worker_name
            agent_desc = snapshot.final_worker.description

        nodes.append(
            SplDocumentNode(
                node_ref="agent:main",
                node_kind="section",
                node_type="AGENT",
                construct_ref=None,
                parent_node_ref=None,
                order=1,
                title=agent_title,
                summary=agent_desc,
                status="available",
                attributes={},
                provenance_summary=None,
            )
        )

        def _prov_summary(
            spans: Iterable[str], fallback: str = "inferred"
        ) -> dict[str, Any] | None:
            ids = tuple(dict.fromkeys(s for s in spans if isinstance(s, str) and s))
            if ids:
                return {"kind": "source_backed", "source_span_count": len(ids)}
            return {"kind": fallback, "source_span_count": 0}

        # ── Profile-derived nodes (direct children of AGENT) ────────────
        if isinstance(snapshot.agent_profile, AgentProfileIR):
            profile = snapshot.agent_profile
            persona = profile.persona
            persona_ref = _construct_ref("persona", "agent")

            # Filter to source-backed aspects only (Stage 11 renderability gate)
            renderable_aspects = [
                (source_index, aspect)
                for source_index, aspect in enumerate(persona.aspects)
                if is_renderable_optional_profile_item(aspect)
            ]
            renderable_audience = [
                (source_index, aspect)
                for source_index, aspect in enumerate(profile.audience_aspects)
                if is_renderable_optional_profile_item(aspect)
            ]
            renderable_concepts = [
                (source_index, concept)
                for source_index, concept in enumerate(profile.concepts)
                if is_renderable_optional_profile_item(concept)
            ]

            # PERSONA construct
            nodes.append(
                SplDocumentNode(
                    node_ref=persona_ref,
                    node_kind="construct",
                    node_type="PERSONA",
                    construct_ref=persona_ref,
                    parent_node_ref="agent:main",
                    order=10,
                    title="Persona",
                    summary=persona.role,
                    status="available",
                    attributes={"role": persona.role},
                    provenance_summary=_prov_summary(
                        persona.source_span_ids,
                        fallback=persona.provenance_relation,
                    ),
                )
            )

            extra_cards.append(
                SplConstructCard(
                    construct_ref=persona_ref,
                    construct_type="PERSONA",
                    title="Persona",
                    status="available",
                    payload_summary={"role": persona.role},
                    provenance_summary=CardProvenanceSummary(
                        kind=(
                            "source_backed"
                            if persona.source_span_ids
                            else persona.provenance_relation
                        ),
                        source_span_count=len(persona.source_span_ids),
                    ),
                    source_span_ids=tuple(persona.source_span_ids),
                    parent_ref=None,
                    construct_path=(persona_ref,),
                    trace_target_refs=("profile:persona",),
                )
            )

            # PERSONA_ASPECT constructs (source-backed only)
            for display_index, (source_index, aspect) in enumerate(renderable_aspects):
                aspect_ref = _construct_ref("persona_aspect", aspect.name)
                extra_cards.append(
                    SplConstructCard(
                        construct_ref=aspect_ref,
                        construct_type="PERSONA_ASPECT",
                        title=aspect.name,
                        status="available",
                        payload_summary={"name": aspect.name, "text": aspect.text},
                        provenance_summary=CardProvenanceSummary(
                            kind="source_backed",
                            source_span_count=len(aspect.source_span_ids),
                        ),
                        source_span_ids=tuple(aspect.source_span_ids),
                        parent_ref=persona_ref,
                        construct_path=(persona_ref, aspect_ref),
                        trace_target_refs=(f"profile:persona.aspect:{source_index}",),
                    )
                )

                nodes.append(
                    SplDocumentNode(
                        node_ref=aspect_ref,
                        node_kind="construct",
                        node_type="PERSONA_ASPECT",
                        construct_ref=aspect_ref,
                        parent_node_ref=persona_ref,
                        order=11 + display_index,
                        title=aspect.name,
                        summary=aspect.text,
                        status="available",
                        attributes={"name": aspect.name, "text": aspect.text},
                        provenance_summary=_prov_summary(aspect.source_span_ids),
                    )
                )

            # AUDIENCE section (only if source-backed aspects exist)
            if renderable_audience:
                nodes.append(
                    SplDocumentNode(
                        node_ref="section:audience",
                        node_kind="section",
                        node_type="AUDIENCE",
                        construct_ref=None,
                        parent_node_ref="agent:main",
                        order=20,
                        title="Audience",
                        summary=None,
                        status="available",
                        attributes={},
                        provenance_summary=None,
                    )
                )

                for display_index, (source_index, aspect) in enumerate(renderable_audience):
                    aspect_ref = _construct_ref("audience_aspect", aspect.name)
                    extra_cards.append(
                        SplConstructCard(
                            construct_ref=aspect_ref,
                            construct_type="AUDIENCE_ASPECT",
                            title=aspect.name,
                            status="available",
                            payload_summary={"name": aspect.name, "text": aspect.text},
                            provenance_summary=CardProvenanceSummary(
                                kind="source_backed",
                                source_span_count=len(aspect.source_span_ids),
                            ),
                            source_span_ids=tuple(aspect.source_span_ids),
                            parent_ref=None,
                            construct_path=(aspect_ref,),
                            trace_target_refs=(f"profile:audience:{source_index}",),
                        )
                    )

                    nodes.append(
                        SplDocumentNode(
                            node_ref=aspect_ref,
                            node_kind="construct",
                            node_type="AUDIENCE_ASPECT",
                            construct_ref=aspect_ref,
                            parent_node_ref="section:audience",
                            order=21 + display_index,
                            title=aspect.name,
                            summary=aspect.text,
                            status="available",
                            attributes={"name": aspect.name, "text": aspect.text},
                            provenance_summary=_prov_summary(aspect.source_span_ids),
                        )
                    )

            # CONCEPTS section (only if source-backed concepts exist)
            if renderable_concepts:
                nodes.append(
                    SplDocumentNode(
                        node_ref="section:concepts",
                        node_kind="section",
                        node_type="CONCEPTS",
                        construct_ref=None,
                        parent_node_ref="agent:main",
                        order=30,
                        title="Concepts",
                        summary=None,
                        status="available",
                        attributes={},
                        provenance_summary=None,
                    )
                )

                for display_index, (source_index, concept) in enumerate(renderable_concepts):
                    concept_ref = _construct_ref("concept", concept.term)
                    extra_cards.append(
                        SplConstructCard(
                            construct_ref=concept_ref,
                            construct_type="CONCEPT",
                            title=concept.term,
                            status="available",
                            payload_summary={
                                "term": concept.term,
                                "definition": concept.definition,
                            },
                            provenance_summary=CardProvenanceSummary(
                                kind="source_backed",
                                source_span_count=len(concept.source_span_ids),
                            ),
                            source_span_ids=tuple(concept.source_span_ids),
                            parent_ref=None,
                            construct_path=(concept_ref,),
                            trace_target_refs=(f"profile:concept:{source_index}",),
                        )
                    )

                    nodes.append(
                        SplDocumentNode(
                            node_ref=concept_ref,
                            node_kind="construct",
                            node_type="CONCEPT",
                            construct_ref=concept_ref,
                            parent_node_ref="section:concepts",
                            order=31 + display_index,
                            title=concept.term,
                            summary=concept.definition,
                            status="available",
                            attributes={
                                "term": concept.term,
                                "definition": concept.definition,
                            },
                            provenance_summary=_prov_summary(concept.source_span_ids),
                        )
                    )

        # ── Constraints (direct children of AGENT) ──────────────────────
        if snapshot.constraints:
            nodes.append(
                SplDocumentNode(
                    node_ref="section:constraints",
                    node_kind="section",
                    node_type="CONSTRAINTS",
                    construct_ref=None,
                    parent_node_ref="agent:main",
                    order=40,
                    title="Constraints",
                    summary=None,
                    status="available",
                    attributes={},
                    provenance_summary=None,
                )
            )

            for idx, constraint in enumerate(snapshot.constraints):
                if isinstance(constraint, ConstraintIR):
                    constraint_ref = _construct_ref("constraint", constraint.constraint_id)
                    # Keep internal targets in attributes for Inspector;
                    # canvas shows only grammar-visible kind + text.
                    nodes.append(
                        SplDocumentNode(
                            node_ref=constraint_ref,
                            node_kind="construct",
                            node_type="CONSTRAINT",
                            construct_ref=constraint_ref,
                            parent_node_ref="section:constraints",
                            order=41 + idx,
                            title=grammar_aspect_name(constraint.kind),
                            summary=constraint.text,
                            status="available",
                            attributes={
                                "constraint_id": constraint.constraint_id,
                                "text": constraint.text,
                                "kind": constraint.kind,
                                "targets": list(constraint.targets),
                            },
                            provenance_summary=_prov_summary(constraint.source_span_ids),
                        )
                    )

        # ── Resources (direct children of AGENT, no RESOURCES wrapper) ──
        if isinstance(snapshot.resources, ResourceRegistryIR):
            registry = snapshot.resources

            # TYPES
            if registry.types:
                nodes.append(
                    SplDocumentNode(
                        node_ref="section:types",
                        node_kind="section",
                        node_type="TYPES",
                        construct_ref=None,
                        parent_node_ref="agent:main",
                        order=50,
                        title="Types",
                        summary=None,
                        status="available",
                        attributes={},
                        provenance_summary=None,
                    )
                )

                for idx, type_spec in enumerate(registry.types):
                    type_ref = _construct_ref("type", type_spec.type_name)
                    extra_cards.append(
                        SplConstructCard(
                            construct_ref=type_ref,
                            construct_type="TYPE",
                            title=type_spec.type_name,
                            status="available",
                            payload_summary={
                                "type_name": type_spec.type_name,
                                "type_kind": type_spec.type_kind,
                                "definition": type_spec.definition,
                            },
                            provenance_summary=CardProvenanceSummary(
                                kind="inferred", source_span_count=0
                            ),
                            source_span_ids=(),
                            parent_ref=None,
                            construct_path=(type_ref,),
                        )
                    )

                    nodes.append(
                        SplDocumentNode(
                            node_ref=type_ref,
                            node_kind="construct",
                            node_type="TYPE",
                            construct_ref=type_ref,
                            parent_node_ref="section:types",
                            order=51 + idx,
                            title=type_spec.type_name,
                            summary=_summary_text(type_spec.definition),
                            status="available",
                            attributes={
                                "type_name": type_spec.type_name,
                                "type_kind": type_spec.type_kind,
                                "definition": type_spec.definition,
                            },
                            provenance_summary=None,
                        )
                    )

            # VARIABLES
            if registry.variables:
                nodes.append(
                    SplDocumentNode(
                        node_ref="section:variables",
                        node_kind="section",
                        node_type="VARIABLES",
                        construct_ref=None,
                        parent_node_ref="agent:main",
                        order=60,
                        title="Variables",
                        summary=None,
                        status="available",
                        attributes={},
                        provenance_summary=None,
                    )
                )

                for idx, var_spec in enumerate(registry.variables):
                    var_ref = _construct_ref("variable", var_spec.name)
                    extra_cards.append(
                        SplConstructCard(
                            construct_ref=var_ref,
                            construct_type="VARIABLE",
                            title=var_spec.name,
                            status="available",
                            payload_summary={
                                "name": var_spec.name,
                                "data_type": var_spec.data_type,
                                "required": var_spec.required,
                                "source": var_spec.source,
                                "description": var_spec.description,
                            },
                            provenance_summary=CardProvenanceSummary(
                                kind="inferred", source_span_count=0
                            ),
                            source_span_ids=(),
                            parent_ref=None,
                            construct_path=(var_ref,),
                            trace_target_refs=(f"variable:{var_spec.name}",),
                        )
                    )

                    nodes.append(
                        SplDocumentNode(
                            node_ref=var_ref,
                            node_kind="construct",
                            node_type="VARIABLE",
                            construct_ref=var_ref,
                            parent_node_ref="section:variables",
                            order=61 + idx,
                            title=var_spec.name,
                            summary=var_spec.description,
                            status="available",
                            attributes={
                                "name": var_spec.name,
                                "data_type": var_spec.data_type,
                                "required": var_spec.required,
                                "source": var_spec.source,
                                "description": var_spec.description,
                            },
                            provenance_summary=None,
                        )
                    )

            # FILES
            if registry.files:
                nodes.append(
                    SplDocumentNode(
                        node_ref="section:files",
                        node_kind="section",
                        node_type="FILES",
                        construct_ref=None,
                        parent_node_ref="agent:main",
                        order=70,
                        title="Files",
                        summary=None,
                        status="available",
                        attributes={},
                        provenance_summary=None,
                    )
                )

                for idx, file_spec in enumerate(registry.files):
                    file_ref = _construct_ref("file", file_spec.name)
                    extra_cards.append(
                        SplConstructCard(
                            construct_ref=file_ref,
                            construct_type="FILE",
                            title=file_spec.name,
                            status="available",
                            payload_summary={
                                "name": file_spec.name,
                                "path": file_spec.path,
                                "data_type": file_spec.data_type,
                                "description": file_spec.description,
                            },
                            provenance_summary=CardProvenanceSummary(
                                kind="inferred", source_span_count=0
                            ),
                            source_span_ids=(),
                            parent_ref=None,
                            construct_path=(file_ref,),
                        )
                    )

                    nodes.append(
                        SplDocumentNode(
                            node_ref=file_ref,
                            node_kind="construct",
                            node_type="FILE",
                            construct_ref=file_ref,
                            parent_node_ref="section:files",
                            order=71 + idx,
                            title=file_spec.name,
                            summary=file_spec.description,
                            status="available",
                            attributes={
                                "name": file_spec.name,
                                "path": file_spec.path,
                                "data_type": file_spec.data_type,
                                "description": file_spec.description,
                            },
                            provenance_summary=None,
                        )
                    )

            # APIS
            if registry.apis:
                nodes.append(
                    SplDocumentNode(
                        node_ref="section:apis",
                        node_kind="section",
                        node_type="APIS",
                        construct_ref=None,
                        parent_node_ref="agent:main",
                        order=80,
                        title="APIs",
                        summary=None,
                        status="available",
                        attributes={},
                        provenance_summary=None,
                    )
                )

                for idx, api_spec in enumerate(registry.apis):
                    api_identity = api_spec.api_id or api_spec.api_name
                    api_ref = _construct_ref("api", api_identity)
                    extra_cards.append(
                        SplConstructCard(
                            construct_ref=api_ref,
                            construct_type="API",
                            title=api_spec.api_name,
                            status="available"
                            if api_spec.declaration_status == "complete"
                            else "partial",
                            payload_summary={
                                "api_name": api_spec.api_name,
                                "auth": api_spec.auth,
                                "description": api_spec.description,
                            },
                            provenance_summary=CardProvenanceSummary(
                                kind=("source_backed" if api_spec.source_span_ids else "inferred"),
                                source_span_count=len(api_spec.source_span_ids),
                            ),
                            source_span_ids=tuple(api_spec.source_span_ids),
                            parent_ref=None,
                            construct_path=(api_ref,),
                            trace_target_refs=(f"api:{api_spec.api_id or api_spec.api_name}",),
                        )
                    )

                    nodes.append(
                        SplDocumentNode(
                            node_ref=api_ref,
                            node_kind="construct",
                            node_type="API",
                            construct_ref=api_ref,
                            parent_node_ref="section:apis",
                            order=81 + idx * 10,
                            title=api_spec.api_name,
                            summary=api_spec.description,
                            status="available"
                            if api_spec.declaration_status == "complete"
                            else "partial",
                            attributes={
                                "api_name": api_spec.api_name,
                                "auth": api_spec.auth,
                                "description": api_spec.description,
                            },
                            provenance_summary=_prov_summary(api_spec.source_span_ids),
                        )
                    )

                    for f_idx, function in enumerate(api_spec.functions):
                        func_ref = _construct_ref(
                            "api_function",
                            api_identity,
                            function.function_id or function.name,
                        )
                        function_spans = tuple(function.source_span_ids)
                        extra_cards.append(
                            SplConstructCard(
                                construct_ref=func_ref,
                                construct_type="API_FUNCTION",
                                title=function.name,
                                status="available",
                                payload_summary={
                                    "name": function.name,
                                    "description": function.description,
                                    "parameters": function.parameters,
                                    "return_type": function.return_type,
                                },
                                provenance_summary=CardProvenanceSummary(
                                    kind=("source_backed" if function_spans else "inferred"),
                                    source_span_count=len(function_spans),
                                ),
                                source_span_ids=function_spans,
                                parent_ref=api_ref,
                                construct_path=(api_ref, func_ref),
                                trace_target_refs=(),
                            )
                        )

                        nodes.append(
                            SplDocumentNode(
                                node_ref=func_ref,
                                node_kind="construct",
                                node_type="API_FUNCTION",
                                construct_ref=func_ref,
                                parent_node_ref=api_ref,
                                order=81 + idx * 10 + f_idx + 1,
                                title=function.name,
                                summary=function.description,
                                status="available",
                                attributes={
                                    "name": function.name,
                                    "description": function.description,
                                    "parameters": function.parameters,
                                    "return_type": function.return_type,
                                },
                                provenance_summary=_prov_summary(function_spans),
                            )
                        )

        # ── Workers (direct children of AGENT, no WORKERS wrapper) ──────
        emitted_worker_refs: set[str] = set()

        def _project_worker_node(
            worker: WorkerIR | ChildWorkerIR,
            is_main: bool,
            order: int,
        ) -> None:
            worker_ref = _worker_ref(worker.worker_name)
            if worker_ref in emitted_worker_refs:
                return
            emitted_worker_refs.add(worker_ref)

            nodes.append(
                SplDocumentNode(
                    node_ref=worker_ref,
                    node_kind="construct",
                    node_type="WORKER",
                    construct_ref=worker_ref,
                    parent_node_ref="agent:main",
                    order=order,
                    title=worker.worker_name,
                    summary=worker.description,
                    status="available",
                    attributes={
                        "worker_name": worker.worker_name,
                        "worker_kind": "main" if is_main else "child",
                        "description": worker.description,
                    },
                    provenance_summary=None,
                )
            )

            # INPUTS section
            inputs_ref = f"inputs:{worker.worker_name}"
            nodes.append(
                SplDocumentNode(
                    node_ref=inputs_ref,
                    node_kind="section",
                    node_type="INPUTS",
                    construct_ref=None,
                    parent_node_ref=worker_ref,
                    order=1,
                    title="Inputs",
                    summary=None,
                    status="available",
                    attributes={},
                    provenance_summary=None,
                )
            )

            for idx, inp in enumerate(worker.inputs):
                input_ref = _construct_ref("input", worker.worker_name, inp.name)
                extra_cards.append(
                    SplConstructCard(
                        construct_ref=input_ref,
                        construct_type="INPUT",
                        title=inp.name,
                        status="available",
                        payload_summary={
                            "name": inp.name,
                            "required": getattr(inp, "required", True),
                        },
                        provenance_summary=CardProvenanceSummary(
                            kind="inferred", source_span_count=0
                        ),
                        source_span_ids=(),
                        parent_ref=None,
                        construct_path=(input_ref,),
                        trace_target_refs=(
                            f"worker:{worker.worker_name}.variable:{inp.name}",
                            f"variable:{inp.name}",
                        ),
                    )
                )

                nodes.append(
                    SplDocumentNode(
                        node_ref=input_ref,
                        node_kind="construct",
                        node_type="INPUT",
                        construct_ref=input_ref,
                        parent_node_ref=inputs_ref,
                        order=2 + idx,
                        title=inp.name,
                        summary=getattr(inp, "description", None),
                        status="available",
                        attributes={
                            "name": inp.name,
                            "required": getattr(inp, "required", True),
                        },
                        provenance_summary=None,
                    )
                )

            # OUTPUTS section
            outputs_ref = f"outputs:{worker.worker_name}"
            nodes.append(
                SplDocumentNode(
                    node_ref=outputs_ref,
                    node_kind="section",
                    node_type="OUTPUTS",
                    construct_ref=None,
                    parent_node_ref=worker_ref,
                    order=3,
                    title="Outputs",
                    summary=None,
                    status="available",
                    attributes={},
                    provenance_summary=None,
                )
            )

            for idx, out in enumerate(worker.outputs):
                is_req = _is_required_output(out)
                out_ref = (
                    _construct_ref("required_output", worker.worker_name, out.name)
                    if is_req
                    else _construct_ref("output", worker.worker_name, out.name)
                )
                if not is_req:
                    extra_cards.append(
                        SplConstructCard(
                            construct_ref=out_ref,
                            construct_type="OUTPUT",
                            title=out.name,
                            status="available",
                            payload_summary={
                                "name": out.name,
                                "required": getattr(out, "required", True),
                            },
                            provenance_summary=CardProvenanceSummary(
                                kind="inferred", source_span_count=0
                            ),
                            source_span_ids=(),
                            parent_ref=None,
                            construct_path=(out_ref,),
                            trace_target_refs=(
                                f"worker:{worker.worker_name}.variable:{out.name}",
                                f"variable:{out.name}",
                            ),
                        )
                    )

                nodes.append(
                    SplDocumentNode(
                        node_ref=out_ref,
                        node_kind="construct",
                        node_type="OUTPUT",
                        construct_ref=out_ref,
                        parent_node_ref=outputs_ref,
                        order=4 + idx,
                        title=out.name,
                        summary=getattr(out, "description", None),
                        status="available",
                        attributes={
                            "name": out.name,
                            "required": getattr(out, "required", True),
                        },
                        provenance_summary=None,
                    )
                )

            # FLOWS
            emitted_step_ids: set[str] = set()

            def _project_flow_node(
                flow: FlowRef | AlternativeFlowRef | ExceptionFlowRef,
                flow_kind: Literal["main", "alternative", "exception"],
                flow_id: str,
                flow_title: str,
                flow_order: int,
            ) -> None:
                flow_ref = _flow_ref(worker.worker_name, flow_kind, flow_id)
                flow_spans = _flow_span_ids(flow)
                nodes.append(
                    SplDocumentNode(
                        node_ref=flow_ref,
                        node_kind="construct",
                        node_type="EXCEPTION_FLOW" if flow_kind == "exception" else "FLOW",
                        construct_ref=flow_ref,
                        parent_node_ref=worker_ref,
                        order=flow_order,
                        title=flow_title,
                        summary=getattr(flow, "condition_text", None),
                        status="available",
                        attributes={
                            "worker_name": worker.worker_name,
                            "flow_id": flow_id,
                            "flow_kind": flow_kind,
                            "condition_text": getattr(flow, "condition_text", None),
                            "block_count": len(flow.blocks),
                        },
                        provenance_summary=_prov_summary(flow_spans),
                    )
                )

                for b_idx, block in enumerate(flow.blocks):
                    if not isinstance(block, BlockIR):
                        continue
                    block_ref = _block_ref(worker.worker_name, flow_kind, flow_id, block.block_id)
                    block_spans = _span_ids(block.spans)
                    block_title_str = getattr(block, "block_type", "Block")
                    if block.condition_text:
                        block_title_str = f"{block_title_str} ({block.condition_text})"

                    nodes.append(
                        SplDocumentNode(
                            node_ref=block_ref,
                            node_kind="construct",
                            node_type="BLOCK",
                            construct_ref=block_ref,
                            parent_node_ref=flow_ref,
                            order=flow_order + 1 + b_idx * 10,
                            title=block_title_str,
                            summary=block.condition_text,
                            status="available",
                            attributes={
                                "worker_name": worker.worker_name,
                                "flow_id": flow_id,
                                "flow_kind": flow_kind,
                                "block_id": block.block_id,
                                "block_type": block.block_type,
                                "condition_text": block.condition_text,
                            },
                            provenance_summary=_prov_summary(block_spans),
                        )
                    )

                    # COMMANDS inside block — include structured RESULT
                    c_idx = 0
                    for step in worker.steps:
                        if not isinstance(step, StepIR) or step.step_id in emitted_step_ids:
                            continue
                        step_flow_ref = step.flow_ref or "main"
                        normalized_flow_ref = (
                            "main" if step_flow_ref in {"main", "main_flow"} else step_flow_ref
                        )
                        if normalized_flow_ref == flow_id and step.block_ref == block.block_id:
                            command_ref = _command_ref(worker.worker_name, step.step_id)
                            command_attrs: dict[str, Any] = {
                                "step_id": step.step_id,
                                "text": step.text,
                                "command_type": step.command_type,
                            }
                            output_names = [name for name in step.outputs if name]
                            if len(output_names) > 1:
                                raise ValueError(
                                    "render-aligned command projection requires at most "
                                    f"one output: {step.step_id} has {output_names!r}"
                                )

                            result_name = output_names[0] if output_names else None
                            result_type = (
                                result_types.get(result_name, "text")
                                if result_name is not None
                                else None
                            )
                            if step.command_type == "REQUEST_INPUT" and result_name is None:
                                result_name = REQUEST_INPUT_DEFAULT_RESULT_NAME
                                result_type = REQUEST_INPUT_DEFAULT_RESULT_TYPE

                            if result_name is not None and result_type is not None:
                                command_attrs["result"] = [
                                    {
                                        "keyword": command_result_keyword(step.command_type),
                                        "name": result_name,
                                        "data_type": result_type,
                                        "assignment": "SET",
                                    }
                                ]

                            nodes.append(
                                SplDocumentNode(
                                    node_ref=command_ref,
                                    node_kind="construct",
                                    node_type="COMMAND",
                                    construct_ref=command_ref,
                                    parent_node_ref=block_ref,
                                    order=(flow_order + 1 + b_idx * 10 + c_idx + 1),
                                    title=step.text,
                                    summary=None,
                                    status="available",
                                    attributes=command_attrs,
                                    provenance_summary=_prov_summary(step.source_span_ids),
                                )
                            )
                            emitted_step_ids.add(step.step_id)
                            c_idx += 1

            # Project Flows
            _project_flow_node(worker.main_flow, "main", "main", "Main Flow", 10)

            for alt_idx, alt_flow in enumerate(worker.alternative_flows):
                _project_flow_node(
                    alt_flow,
                    "alternative",
                    alt_flow.flow_id,
                    f"Alternative Flow: {alt_flow.condition_text}",
                    20 + alt_idx * 10,
                )

            for exc_idx, exc_flow in enumerate(worker.exception_flows):
                _project_flow_node(
                    exc_flow,
                    "exception",
                    exc_flow.flow_id,
                    f"Exception Flow: {exc_flow.condition_text}",
                    50 + exc_idx * 10,
                )

        # Project Main Worker and Child Workers
        worker_order = 90
        if isinstance(snapshot.final_worker, WorkerIR):
            _project_worker_node(snapshot.final_worker, is_main=True, order=worker_order)
            worker_order += 1
            for c_idx, child in enumerate(snapshot.final_worker.child_workers):
                _project_worker_node(child, is_main=False, order=worker_order + c_idx)

        # Determine Projection Fidelity
        fidelity: Literal["structured", "render_aligned", "partial"] = "render_aligned"
        if snapshot.overlay_version > 0 and snapshot.final_spl is None:
            fidelity = "partial"

        return SplDocumentReadModel(
            nodes=tuple(nodes), fidelity=fidelity, extra_cards=tuple(extra_cards)
        )
