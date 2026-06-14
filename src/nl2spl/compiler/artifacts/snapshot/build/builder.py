"""SnapshotBuilder — constructs a SnapshotDocument from build input.

Reads from ``SnapshotBuildInput`` (frozen typed contract), never from
raw ``intermediate`` dict.  Produces a ``SnapshotDocument`` ready for
validation and persistence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from nl2spl.compiler.artifacts.snapshot.build.input import SnapshotBuildInput
from nl2spl.compiler.artifacts.snapshot.constants import SNAPSHOT_SCHEMA_VERSION
from nl2spl.compiler.artifacts.snapshot.model.document import (
    SnapshotDocument,
    new_base_document,
)
from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
    SnapshotEditingHistory,
)
from nl2spl.compiler.artifacts.snapshot.model.identity import (
    SnapshotIdentity,
    new_base_identity,
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
from nl2spl.compiler.artifacts.snapshot.model.validation import (
    SnapshotDeclaredCapabilities,
)


class SnapshotBuilder:
    """Builds a ``SnapshotDocument`` from a ``SnapshotBuildInput``.

    The builder collects artifacts from the typed input, constructs
    identity, payload layers, and declared capabilities.  It does NOT
    write to disk or call the validator — those are separate concerns.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self, build_input: SnapshotBuildInput) -> SnapshotDocument:
        """Build a base ``SnapshotDocument`` from *build_input*.

        Returns a ``SnapshotDocument`` with ``is_base=True`` and an
        empty editing history.
        """
        identity = self._build_identity(build_input)
        payload = self._build_payload(build_input)
        declared = self._build_declared_capabilities(build_input)

        return new_base_document(
            identity,
            payload=payload,
            declared_capabilities=declared,
        )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @staticmethod
    def _build_identity(build_input: SnapshotBuildInput) -> SnapshotIdentity:
        snapshot_id = _generate_snapshot_id()
        created_at = datetime.now(UTC).isoformat()
        return new_base_identity(
            compile_run_id=build_input.compile_run_id,
            snapshot_id=snapshot_id,
            created_at=created_at,
            producer_version=SNAPSHOT_SCHEMA_VERSION,
        )

    # ------------------------------------------------------------------
    # Payload
    # ------------------------------------------------------------------

    @staticmethod
    def _build_payload(build_input: SnapshotBuildInput) -> SnapshotPayload:
        inp = build_input
        config = inp.config

        return SnapshotPayload(
            source=SourceLayer(
                spans=inp.source_spans,
                routes=inp.source_routes,
                canonical_input=inp.canonical_input,
                construct_plan=inp.construct_plan,
            ),
            stage_artifacts=StageArtifactsLayer(
                worker_plan=inp.worker_plan,
                worker_flow_plan=inp.worker_flow_plan,
                worker_block_plan=inp.worker_block_plan,
                worker_step_plan=inp.worker_step_plan,
                resources=inp.resources,
                worker_scoped_resources=inp.worker_scoped_resources,
                symbol_table=inp.symbol_table,
                constraints=inp.constraints,
                agent_profile=inp.agent_profile,
            ),
            replay_artifacts=ReplayArtifactsLayer(
                normalizer_input=inp.normalizer_input,
                normalizer_output=inp.normalizer_output,
                stage10_input=inp.stage10_input,
                assembled_worker_pre_gate=(
                    inp.pre_gate_worker
                    if (config and getattr(config, "include_pre_gate_worker", False))
                    else None
                ),
                gated_worker=inp.final_worker,
                final_spl=inp.final_spl_text or None,
            ),
            diagnostics=DiagnosticsLayer(
                compile_diagnostics=inp.compile_diagnostics,
            ),
            provenance=ProvenanceLayer(
                traces=inp.traces if (
                    not config or getattr(config, "include_traces", True)
                ) else (),
            ),
            editing=EditingLayer(
                history=SnapshotEditingHistory(),
            ),
        )

    # ------------------------------------------------------------------
    # Declared capabilities
    # ------------------------------------------------------------------

    @staticmethod
    def _build_declared_capabilities(
        build_input: SnapshotBuildInput,
    ) -> SnapshotDeclaredCapabilities:
        """Declare capabilities based on what artifacts are present.

        The validator (S2) will derive effective capabilities from
        actual artifact content.  This is the writer's best-effort
        declaration.
        """
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            SPL_EDITING_EDITABLE_DIAGNOSTIC_KINDS,
            SnapshotCapability,
        )

        caps: list[SnapshotCapability] = []
        inp = build_input
        has_editable_diagnostics = any(
            getattr(diag, "kind", "") in SPL_EDITING_EDITABLE_DIAGNOSTIC_KINDS
            for diag in inp.compile_diagnostics
        )

        # Issue extraction: SPL Editing repair-target diagnostics present
        if has_editable_diagnostics:
            caps.append(SnapshotCapability.ISSUE_EXTRACTION)

        # Suggestion generation: issue extraction + source/provenance data
        if has_editable_diagnostics and inp.source_spans and inp.traces:
            caps.append(SnapshotCapability.SUGGESTION_GENERATION)

        # Lane A replay: stage10_input + stage artifacts present
        if (
            inp.stage10_input is not None
            and inp.worker_plan is not None
            and inp.worker_flow_plan is not None
            and inp.worker_block_plan is not None
            and inp.worker_step_plan is not None
            and inp.resources is not None
            and inp.symbol_table is not None
        ):
            caps.append(SnapshotCapability.LANE_A_REPLAY)

        # Lane B replay: Lane A + normalizer input/output
        if (
            SnapshotCapability.LANE_A_REPLAY in caps
            and inp.normalizer_input is not None
            and inp.normalizer_output is not None
        ):
            caps.append(SnapshotCapability.LANE_B_REPLAY)

        # Final SPL display
        if inp.final_spl_text:
            caps.append(SnapshotCapability.FINAL_SPL_DISPLAY)

        return SnapshotDeclaredCapabilities(capabilities=tuple(caps))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_snapshot_id() -> str:
    """Generate a unique snapshot identifier."""
    return f"snap_{uuid.uuid4().hex[:12]}"
