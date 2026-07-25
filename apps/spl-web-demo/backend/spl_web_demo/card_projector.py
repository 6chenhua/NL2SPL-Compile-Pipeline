"""Structured initial-snapshot projection for SPL Construct cards."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
    JsonFileSnapshotRepository,
)
from nl2spl.compiler.artifacts.snapshot.persistence.loader import SnapshotLoader
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.core.snapshot_adapter import (
    artifact_snapshot_from_document,
)
from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import (
    AlternativeFlowRef,
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerIR,
)

SplConstructType = Literal[
    "WORKER",
    "FLOW",
    "EXCEPTION_FLOW",
    "BLOCK",
    "COMMAND",
    "REQUIRED_OUTPUT",
    "PROFILE",
    "CONSTRAINT",
    "AGENT",
    "PERSONA",
    "PERSONA_ASPECT",
    "AUDIENCE",
    "AUDIENCE_ASPECT",
    "CONCEPTS",
    "CONCEPT",
    "CONSTRAINTS",
    "RESOURCES",
    "TYPES",
    "TYPE",
    "VARIABLES",
    "VARIABLE",
    "FILES",
    "FILE",
    "APIS",
    "API",
    "API_FUNCTION",
    "WORKERS",
    "INPUTS",
    "INPUT",
    "OUTPUTS",
    "OUTPUT",
]
CardStatus = Literal["available", "partial", "review_only"]


@dataclass(frozen=True)
class CardProvenanceSummary:
    kind: str
    source_span_count: int


@dataclass(frozen=True)
class SplConstructCard:
    """Small, stable read-model for one initial SPL construct."""

    construct_ref: str
    construct_type: SplConstructType
    title: str
    status: CardStatus
    payload_summary: dict[str, Any]
    provenance_summary: CardProvenanceSummary
    source_span_ids: tuple[str, ...]
    parent_ref: str | None = None
    construct_path: tuple[str, ...] = ()
    trace_target_refs: tuple[str, ...] = ()


class CardProjector:
    """Project cards only from typed snapshot artifacts, never rendered text."""

    @staticmethod
    def load_snapshot_file(snapshot_path: Path) -> ArtifactSnapshot:
        document = SnapshotLoader(JsonFileSnapshotRepository()).load(snapshot_path)
        return artifact_snapshot_from_document(document)

    def project_snapshot_file(self, snapshot_path: Path) -> tuple[SplConstructCard, ...]:
        return self.project_snapshot(self.load_snapshot_file(snapshot_path))

    def project_snapshot(self, snapshot: ArtifactSnapshot) -> tuple[SplConstructCard, ...]:
        cards: list[SplConstructCard] = []
        seen_refs: set[str] = set()

        final_worker = snapshot.final_worker
        if isinstance(final_worker, WorkerIR):
            self._project_worker(cards, seen_refs, final_worker)
            for child_worker in final_worker.child_workers:
                self._project_worker(cards, seen_refs, child_worker)

        if isinstance(snapshot.agent_profile, AgentProfileIR):
            self._append(cards, seen_refs, self._profile_card(snapshot.agent_profile))

        for constraint in snapshot.constraints:
            if isinstance(constraint, ConstraintIR):
                self._append(cards, seen_refs, self._constraint_card(constraint))

        return tuple(cards)

    def _project_worker(
        self,
        cards: list[SplConstructCard],
        seen_refs: set[str],
        worker: WorkerIR | ChildWorkerIR,
    ) -> None:
        # Check duplicate step IDs to fail closed immediately
        step_ids = [step.step_id for step in worker.steps if isinstance(step, StepIR)]
        if len(step_ids) != len(set(step_ids)):
            seen = set()
            for sid in step_ids:
                if sid in seen:
                    ref = _command_ref(worker.worker_name, sid)
                    raise ValueError(f"duplicate construct_ref: {ref}")
                seen.add(sid)

        worker_ref = _worker_ref(worker.worker_name)
        self._append(cards, seen_refs, self._worker_card(worker))
        emitted_step_ids: set[str] = set()

        self._project_flow(
            cards,
            seen_refs,
            worker=worker,
            worker_ref=worker_ref,
            flow_kind="main",
            flow_id="main",
            flow=worker.main_flow,
            title="Main Flow",
            emitted_step_ids=emitted_step_ids,
        )

        for flow in worker.alternative_flows:
            self._project_flow(
                cards,
                seen_refs,
                worker=worker,
                worker_ref=worker_ref,
                flow_kind="alternative",
                flow_id=flow.flow_id,
                flow=flow,
                title=f"Alternative Flow: {flow.condition_text}",
                emitted_step_ids=emitted_step_ids,
            )

        for flow in worker.exception_flows:
            self._project_flow(
                cards,
                seen_refs,
                worker=worker,
                worker_ref=worker_ref,
                flow_kind="exception",
                flow_id=flow.flow_id,
                flow=flow,
                title=f"Exception Flow: {flow.condition_text}",
                emitted_step_ids=emitted_step_ids,
            )

        for step in worker.steps:
            if not isinstance(step, StepIR) or step.step_id in emitted_step_ids:
                continue
            self._append(
                cards,
                seen_refs,
                self._command_card(
                    worker.worker_name,
                    step,
                    parent_ref=worker_ref,
                    construct_path=(worker_ref, _command_ref(worker.worker_name, step.step_id)),
                    hierarchy_status="unplaced",
                ),
            )

        for output in worker.outputs:
            if not _is_required_output(output):
                continue
            output_ref = _construct_ref("required_output", worker.worker_name, output.name)
            self._append(
                cards,
                seen_refs,
                SplConstructCard(
                    construct_ref=output_ref,
                    construct_type="REQUIRED_OUTPUT",
                    title=f"Required output: {output.name}",
                    status="available",
                    payload_summary={
                        "worker_name": worker.worker_name,
                        "name": output.name,
                        "requiredness": output.requiredness,
                    },
                    provenance_summary=_provenance_summary((), fallback_kind="inferred"),
                    source_span_ids=(),
                    parent_ref=worker_ref,
                    construct_path=(worker_ref, output_ref),
                    trace_target_refs=(
                        f"worker:{worker.worker_name}.variable:{output.name}",
                        f"variable:{output.name}",
                    ),
                ),
            )

    def _project_flow(
        self,
        cards: list[SplConstructCard],
        seen_refs: set[str],
        *,
        worker: WorkerIR | ChildWorkerIR,
        worker_ref: str,
        flow_kind: Literal["main", "alternative", "exception"],
        flow_id: str,
        flow: FlowRef | AlternativeFlowRef | ExceptionFlowRef,
        title: str,
        emitted_step_ids: set[str],
    ) -> None:
        flow_ref = _flow_ref(worker.worker_name, flow_kind, flow_id)
        flow_spans = _flow_span_ids(flow)
        construct_type: SplConstructType = "EXCEPTION_FLOW" if flow_kind == "exception" else "FLOW"
        condition_text = getattr(flow, "condition_text", None)
        trace_target_refs = _flow_trace_target_refs(worker, flow_kind, flow_id)
        self._append(
            cards,
            seen_refs,
            SplConstructCard(
                construct_ref=flow_ref,
                construct_type=construct_type,
                title=title,
                status="available",
                payload_summary={
                    "worker_name": worker.worker_name,
                    "flow_id": flow_id,
                    "flow_kind": flow_kind,
                    "condition_text": condition_text,
                    "block_count": len(flow.blocks),
                },
                provenance_summary=_provenance_summary(flow_spans, fallback_kind="inferred"),
                source_span_ids=flow_spans,
                parent_ref=worker_ref,
                construct_path=(worker_ref, flow_ref),
                trace_target_refs=trace_target_refs,
            ),
        )

        for block in flow.blocks:
            if not isinstance(block, BlockIR):
                continue
            block_ref = _block_ref(worker.worker_name, flow_kind, flow_id, block.block_id)
            block_spans = _span_ids(block.spans)
            self._append(
                cards,
                seen_refs,
                SplConstructCard(
                    construct_ref=block_ref,
                    construct_type="BLOCK",
                    title=_block_title(block),
                    status="available",
                    payload_summary={
                        "worker_name": worker.worker_name,
                        "flow_id": flow_id,
                        "flow_kind": flow_kind,
                        "block_id": block.block_id,
                        "block_type": block.block_type,
                        "condition_text": block.condition_text,
                    },
                    provenance_summary=_provenance_summary(
                        block_spans,
                        fallback_kind="inferred",
                    ),
                    source_span_ids=block_spans,
                    parent_ref=flow_ref,
                    construct_path=(worker_ref, flow_ref, block_ref),
                    trace_target_refs=(
                        f"block:{block.block_id}",
                        f"worker:{worker.worker_name}.block:{block.block_id}",
                    ),
                ),
            )
            for step in worker.steps:
                if not isinstance(step, StepIR) or step.step_id in emitted_step_ids:
                    continue
                if not _step_belongs_to(step, flow_id=flow_id, block_id=block.block_id):
                    continue
                command_ref = _command_ref(worker.worker_name, step.step_id)
                self._append(
                    cards,
                    seen_refs,
                    self._command_card(
                        worker.worker_name,
                        step,
                        parent_ref=block_ref,
                        construct_path=(worker_ref, flow_ref, block_ref, command_ref),
                        hierarchy_status="placed",
                    ),
                )
                emitted_step_ids.add(step.step_id)

    @staticmethod
    def _worker_card(worker: WorkerIR | ChildWorkerIR) -> SplConstructCard:
        worker_kind = "child" if isinstance(worker, ChildWorkerIR) else "main"
        worker_ref = _worker_ref(worker.worker_name)
        return SplConstructCard(
            construct_ref=worker_ref,
            construct_type="WORKER",
            title=worker.worker_name,
            status="available",
            payload_summary={
                "worker_name": worker.worker_name,
                "worker_kind": worker_kind,
                "description": worker.description,
                "input_count": len(worker.inputs),
                "output_count": len(worker.outputs),
                "command_count": len(worker.steps),
                "alternative_flow_count": len(worker.alternative_flows),
                "exception_flow_count": len(worker.exception_flows),
            },
            provenance_summary=_provenance_summary((), fallback_kind="inferred"),
            source_span_ids=(),
            construct_path=(worker_ref,),
            trace_target_refs=(f"worker:{worker.worker_name}",),
        )

    @staticmethod
    def _command_card(
        worker_name: str,
        step: StepIR,
        *,
        parent_ref: str,
        construct_path: tuple[str, ...],
        hierarchy_status: Literal["placed", "unplaced"],
    ) -> SplConstructCard:
        spans = _span_ids(step.source_span_ids)
        return SplConstructCard(
            construct_ref=_command_ref(worker_name, step.step_id),
            construct_type="COMMAND",
            title=f"{step.step_id}: {_summary_text(step.text)}",
            status="available" if hierarchy_status == "placed" else "review_only",
            payload_summary={
                "worker_name": worker_name,
                "command_id": step.step_id,
                "text": _summary_text(step.text),
                "command_type": step.command_type,
                "flow_ref": step.flow_ref,
                "block_ref": step.block_ref,
                "hierarchy_status": hierarchy_status,
                "inputs": list(step.inputs),
                "outputs": list(step.outputs),
            },
            provenance_summary=_provenance_summary(spans, fallback_kind="inferred"),
            source_span_ids=spans,
            parent_ref=parent_ref,
            construct_path=construct_path,
            trace_target_refs=(
                f"step:{step.step_id}",
                f"worker:{worker_name}.step:{step.step_id}",
            ),
        )

    @staticmethod
    def _profile_card(profile: AgentProfileIR) -> SplConstructCard:
        persona = profile.persona
        source_span_ids = _span_ids(
            (
                *persona.source_span_ids,
                *(span for aspect in persona.aspects for span in aspect.source_span_ids),
                *(span for aspect in profile.audience_aspects for span in aspect.source_span_ids),
                *(span for concept in profile.concepts for span in concept.source_span_ids),
            )
        )
        fallback_kind = "assumed" if persona.provenance_relation == "assumed" else "inferred"
        profile_ref = _construct_ref("profile", "agent")
        return SplConstructCard(
            construct_ref=profile_ref,
            construct_type="PROFILE",
            title=f"Agent profile: {persona.role}",
            status="available",
            payload_summary={
                "role": persona.role,
                "persona_aspect_count": len(persona.aspects),
                "audience_aspect_count": len(profile.audience_aspects),
                "concept_count": len(profile.concepts),
                "persona_aspects": [
                    {"name": aspect.name, "text": aspect.text} for aspect in persona.aspects
                ],
                "audience_aspects": [
                    {"name": aspect.name, "text": aspect.text}
                    for aspect in profile.audience_aspects
                ],
                "concepts": [
                    {"term": concept.term, "definition": concept.definition}
                    for concept in profile.concepts
                ],
            },
            provenance_summary=_provenance_summary(
                source_span_ids,
                fallback_kind=fallback_kind,
            ),
            source_span_ids=source_span_ids,
            construct_path=(profile_ref,),
            trace_target_refs=_profile_trace_target_refs(profile),
        )

    @staticmethod
    def _constraint_card(constraint: ConstraintIR) -> SplConstructCard:
        spans = _span_ids(constraint.source_span_ids)
        constraint_ref = _construct_ref("constraint", constraint.constraint_id)
        return SplConstructCard(
            construct_ref=constraint_ref,
            construct_type="CONSTRAINT",
            title=f"Constraint {constraint.constraint_id}",
            status="available",
            payload_summary={
                "constraint_id": constraint.constraint_id,
                "text": _summary_text(constraint.text),
                "kind": constraint.kind,
                "targets": list(constraint.targets),
            },
            provenance_summary=_provenance_summary(spans, fallback_kind="inferred"),
            source_span_ids=spans,
            construct_path=(constraint_ref,),
            trace_target_refs=(f"constraint:{constraint.constraint_id}",),
        )

    @staticmethod
    def _append(
        cards: list[SplConstructCard],
        seen_refs: set[str],
        card: SplConstructCard,
    ) -> None:
        if card.construct_ref in seen_refs:
            raise ValueError(f"duplicate construct_ref: {card.construct_ref}")
        seen_refs.add(card.construct_ref)
        cards.append(card)


def _worker_ref(worker_name: str) -> str:
    return _construct_ref("worker", worker_name)


def _flow_ref(worker_name: str, flow_kind: str, flow_id: str) -> str:
    construct_type = "exception_flow" if flow_kind == "exception" else "flow"
    return _construct_ref(construct_type, worker_name, flow_kind, flow_id)


def _block_ref(worker_name: str, flow_kind: str, flow_id: str, block_id: str) -> str:
    return _construct_ref("block", worker_name, flow_kind, flow_id, block_id)


def _command_ref(worker_name: str, step_id: str) -> str:
    return _construct_ref("command", worker_name, step_id)


def _construct_ref(construct_type: str, *identity_parts: str) -> str:
    canonical_identity = "\x1f".join((construct_type, *identity_parts))
    digest = hashlib.sha256(canonical_identity.encode("utf-8")).hexdigest()[:16]
    return f"{construct_type}_{digest}"


def _flow_span_ids(flow: FlowRef | AlternativeFlowRef | ExceptionFlowRef) -> tuple[str, ...]:
    own_spans = getattr(flow, "spans", ())
    return _span_ids((*own_spans, *(span for block in flow.blocks for span in block.spans)))


def _flow_trace_target_refs(
    worker: WorkerIR | ChildWorkerIR,
    flow_kind: str,
    flow_id: str,
) -> tuple[str, ...]:
    if flow_kind == "main":
        return (f"worker:{worker.worker_name}.flow:main", "flow:main")
    if flow_kind == "alternative":
        return (
            f"worker:{worker.worker_name}.alternative_flow:{flow_id}",
            f"flow:{flow_id}",
        )
    return (
        (f"worker:{worker.worker_name}.exception_flow:{flow_id}",)
        if isinstance(worker, ChildWorkerIR)
        else (f"flow:{flow_id}",)
    )


def _step_belongs_to(step: StepIR, *, flow_id: str, block_id: str) -> bool:
    step_flow_ref = step.flow_ref or "main"
    normalized_flow_ref = "main" if step_flow_ref in {"main", "main_flow"} else step_flow_ref
    return normalized_flow_ref == flow_id and step.block_ref == block_id


def _block_title(block: BlockIR) -> str:
    suffix = f": {block.condition_text}" if block.condition_text else ""
    return f"{block.block_type} Block {block.block_id}{suffix}"


def _is_required_output(output: Any) -> bool:
    if getattr(output, "requiredness", "unspecified") == "required":
        return True
    return getattr(output, "required", None) is True


def _profile_trace_target_refs(profile: AgentProfileIR) -> tuple[str, ...]:
    return (
        "profile:persona",
        *(f"profile:persona.aspect:{index}" for index, _ in enumerate(profile.persona.aspects)),
        *(f"profile:audience:{index}" for index, _ in enumerate(profile.audience_aspects)),
        *(f"profile:concept:{index}" for index, _ in enumerate(profile.concepts)),
    )


def _span_ids(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value))


def _provenance_summary(
    source_span_ids: tuple[str, ...],
    *,
    fallback_kind: str,
) -> CardProvenanceSummary:
    return CardProvenanceSummary(
        kind="source_backed" if source_span_ids else fallback_kind,
        source_span_count=len(source_span_ids),
    )


def _summary_text(value: str, *, limit: int = 240) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"
