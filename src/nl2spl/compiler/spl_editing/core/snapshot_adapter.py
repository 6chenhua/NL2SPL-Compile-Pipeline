"""Adapters between compiler snapshot documents and SPL Editing runtime models."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from nl2spl.compiler.artifacts.snapshot.model.document import (
    SnapshotDocument,
    new_base_document,
    new_overlay_document,
)
from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
    SnapshotAcceptedPatchDTO,
    SnapshotEditingHistory,
    SnapshotOverlayEventDTO,
    SnapshotPromotionResolutionDTO,
    SnapshotVerificationRecordDTO,
)
from nl2spl.compiler.artifacts.snapshot.model.identity import (
    new_base_identity,
    new_overlay_identity,
)
from nl2spl.compiler.artifacts.snapshot.model.payload import (
    DiagnosticsLayer,
    EditingLayer,
    ProvenanceLayer,
    ReplayArtifactsLayer,
    SnapshotPayload,
    SourceLayer,
    StageArtifactsLayer,
)
from nl2spl.compiler.spl_editing.core.model import (
    VerificationResult,
)
from nl2spl.compiler.spl_editing.core.revision import (
    AcceptedRepairPatch,
    ArtifactSnapshot,
    OverlayEvent,
)
from nl2spl.compiler.spl_editing.resolution.model import PromotionResolutionMarker
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef


def artifact_snapshot_from_document(document: SnapshotDocument) -> ArtifactSnapshot:
    """Convert a validated compiler-owned ``SnapshotDocument`` to runtime state."""
    payload = document.payload
    identity = document.identity
    source = payload.source
    stage = payload.stage_artifacts
    replay = payload.replay_artifacts
    diagnostics = payload.diagnostics
    provenance = payload.provenance

    return ArtifactSnapshot(
        snapshot_id=identity.snapshot_id,
        compile_run_id=identity.compile_run_id,
        overlay_version=identity.overlay_version,
        canonical_input=source.canonical_input,
        spans=tuple(source.spans),
        routes=source.routes,
        worker_plan=stage.worker_plan,
        worker_flow_plan=stage.worker_flow_plan,
        worker_block_plan=stage.worker_block_plan,
        worker_step_plan=stage.worker_step_plan,
        resources=stage.resources,
        worker_scoped_resources=stage.worker_scoped_resources,
        symbol_table=stage.symbol_table,
        constraints=tuple(stage.constraints),
        agent_profile=stage.agent_profile,
        final_worker=replay.gated_worker,
        final_spl=replay.final_spl,
        compile_diagnostics=_runtime_diagnostics(diagnostics.compile_diagnostics),
        traces=tuple(provenance.traces),
        promotion_resolution_markers=tuple(
            PromotionResolutionMarker(
                marker_id=item.marker_id,
                target_worker_promotion_id=item.target_worker_promotion_id,
                resolved_diagnostic_group_id=item.resolved_diagnostic_group_id,
                resolution_kind=item.resolution_kind,
                normalized_directive_id=item.normalized_directive_id,
                materialized_construct_refs=tuple(item.materialized_construct_refs),
                evidence_ref=item.evidence_ref,
                repair_patch_id=item.repair_patch_id,
                user_confirmed=item.user_confirmed,
            )
            for item in payload.editing.history.promotion_resolutions
        ),
    )


def document_from_artifact_snapshot(
    snapshot: ArtifactSnapshot,
    *,
    parent_document: SnapshotDocument | None = None,
    overlay_event: OverlayEvent | None = None,
    accepted_patch: AcceptedRepairPatch | None = None,
    verification_result: VerificationResult | None = None,
) -> SnapshotDocument:
    """Convert SPL Editing runtime state into a neutral snapshot document."""
    payload = _payload_from_artifact_snapshot(
        snapshot,
        parent_document=parent_document,
        overlay_event=overlay_event,
        accepted_patch=accepted_patch,
        verification_result=verification_result,
    )
    created_at = _now_iso()

    if parent_document is None:
        identity = new_base_identity(
            snapshot.compile_run_id,
            snapshot.snapshot_id,
            created_at=created_at,
        )
        return new_base_document(identity, payload=payload)

    base_identity = _base_identity(parent_document)
    overlay_id = f"{parent_document.identity.base_snapshot_id}_ov{snapshot.overlay_version}"
    identity = new_overlay_identity(
        base_identity,
        overlay_id,
        created_at=created_at,
        parent_identity=parent_document.identity,
    )
    return new_overlay_document(identity, parent_document, payload=payload)


def document_with_verification_record(
    document: SnapshotDocument,
    result: VerificationResult,
    event: OverlayEvent | None,
) -> SnapshotDocument:
    """Return *document* with one appended neutral verification DTO."""
    payload = document.payload
    history = payload.editing.history
    updated_history = SnapshotEditingHistory(
        overlay_events=history.overlay_events,
        accepted_patches=history.accepted_patches,
        verification_history=(history.verification_history + _verification_dtos(result, event)),
        promotion_resolutions=history.promotion_resolutions,
    )
    updated_payload = replace(
        payload,
        editing=EditingLayer(history=updated_history),
    )
    return SnapshotDocument(
        artifact_kind=document.artifact_kind,
        schema_version=document.schema_version,
        identity=document.identity,
        declared_capabilities=document.declared_capabilities,
        payload=updated_payload,
        integrity=None,
    )


def _payload_from_artifact_snapshot(
    snapshot: ArtifactSnapshot,
    *,
    parent_document: SnapshotDocument | None,
    overlay_event: OverlayEvent | None,
    accepted_patch: AcceptedRepairPatch | None,
    verification_result: VerificationResult | None,
) -> SnapshotPayload:
    parent_history = (
        parent_document.editing_history if parent_document is not None else SnapshotEditingHistory()
    )
    history = SnapshotEditingHistory(
        overlay_events=parent_history.overlay_events + _overlay_dtos(overlay_event),
        accepted_patches=(parent_history.accepted_patches + _accepted_patch_dtos(accepted_patch)),
        verification_history=(
            parent_history.verification_history
            + _verification_dtos(verification_result, overlay_event)
        ),
        promotion_resolutions=tuple(
            SnapshotPromotionResolutionDTO(
                marker_id=item.marker_id,
                target_worker_promotion_id=item.target_worker_promotion_id,
                resolved_diagnostic_group_id=item.resolved_diagnostic_group_id,
                resolution_kind=item.resolution_kind,
                normalized_directive_id=item.normalized_directive_id,
                materialized_construct_refs=tuple(item.materialized_construct_refs),
                evidence_ref=item.evidence_ref,
                repair_patch_id=item.repair_patch_id,
                user_confirmed=item.user_confirmed,
            )
            for item in snapshot.promotion_resolution_markers
        ),
    )
    return SnapshotPayload(
        source=SourceLayer(
            canonical_input=snapshot.canonical_input,
            spans=tuple(snapshot.spans),
            routes=snapshot.routes,
        ),
        stage_artifacts=StageArtifactsLayer(
            worker_plan=snapshot.worker_plan,
            worker_flow_plan=snapshot.worker_flow_plan,
            worker_block_plan=snapshot.worker_block_plan,
            worker_step_plan=snapshot.worker_step_plan,
            resources=snapshot.resources,
            worker_scoped_resources=snapshot.worker_scoped_resources,
            symbol_table=snapshot.symbol_table,
            constraints=tuple(snapshot.constraints),
            agent_profile=snapshot.agent_profile,
        ),
        replay_artifacts=ReplayArtifactsLayer(
            gated_worker=snapshot.final_worker,
            final_spl=snapshot.final_spl,
        ),
        diagnostics=DiagnosticsLayer(
            compile_diagnostics=tuple(snapshot.compile_diagnostics),
        ),
        provenance=ProvenanceLayer(traces=tuple(snapshot.traces)),
        editing=EditingLayer(history=history),
    )


def _runtime_diagnostics(raw: tuple[object, ...]) -> tuple[CompileDiagnostic, ...]:
    result: list[CompileDiagnostic] = []
    for item in raw:
        if not isinstance(item, CompileDiagnostic):
            continue
        metadata = dict(item.metadata)
        irs_ref = metadata.get("irs_ref")
        if isinstance(irs_ref, DiagnosticIRSRef):
            metadata["irs_ref"] = irs_ref.to_dict()
        result.append(replace(item, metadata=metadata))
    return tuple(result)


def _base_identity(parent_document: SnapshotDocument):
    identity = parent_document.identity
    if parent_document.is_base:
        return identity
    return new_base_identity(
        identity.compile_run_id,
        identity.base_snapshot_id,
        created_at=identity.created_at,
        producer_version=identity.producer_version,
    )


def _overlay_dtos(event: OverlayEvent | None) -> tuple[SnapshotOverlayEventDTO, ...]:
    if event is None:
        return ()
    return (
        SnapshotOverlayEventDTO(
            overlay_id=event.overlay_id,
            base_compile_run_id=event.base_compile_run_id,
            base_artifact_snapshot_id=event.base_artifact_snapshot_id,
            overlay_version=event.overlay_version,
            patch_type=event.patch_type,
            affordance_id=event.affordance_id,
            patch_id=event.patch_id,
            accepted=event.accepted,
        ),
    )


def _accepted_patch_dtos(
    patch: AcceptedRepairPatch | None,
) -> tuple[SnapshotAcceptedPatchDTO, ...]:
    if patch is None:
        return ()
    return (
        SnapshotAcceptedPatchDTO(
            patch_id=patch.patch_id,
            patch_type=patch.patch_type,
            affordance_id=patch.affordance_id,
            overlay_id=patch.overlay_id,
        ),
    )


def _verification_dtos(
    result: VerificationResult | None,
    event: OverlayEvent | None,
) -> tuple[SnapshotVerificationRecordDTO, ...]:
    if result is None:
        return ()
    return (
        SnapshotVerificationRecordDTO(
            verification_id=f"verify_{result.session_id}_{result.patch_id}",
            overlay_id=event.overlay_id if event is not None else "",
            lane=result.lane,
            passed=result.accepted,
            diagnostic_count_before=0,
            diagnostic_count_after=0,
            error_messages=tuple(result.failure_reasons),
        ),
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
