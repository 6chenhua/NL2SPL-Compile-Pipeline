"""JSON file-backed snapshot repository (MVP).

Reads and writes ``spl_editing_snapshot.json`` files from the local
filesystem.  Validates every loaded document through S2 before returning.
"""

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from nl2spl.compiler.artifacts.snapshot.hash_policy import canonical_json_dumps
from nl2spl.compiler.artifacts.snapshot.model.document import (
    SnapshotDocument,
)
from nl2spl.compiler.artifacts.snapshot.model.identity import SnapshotIdentity
from nl2spl.compiler.artifacts.snapshot.model.payload import (
    DiagnosticsLayer,
    SnapshotPayload,
)
from nl2spl.compiler.artifacts.snapshot.persistence.repository import (
    SnapshotRepository,
)
from nl2spl.compiler.artifacts.snapshot.validation.validator import (
    SnapshotValidator,
)


class JsonFileSnapshotRepository(SnapshotRepository):
    """File-backed snapshot repository using canonical JSON files.

    File naming convention (MVP):
    - Base: ``<run_dir>/spl_editing_snapshot.json``
    - Overlay: ``<run_dir>/spl_editing_overlays/<snapshot_id>.json``
    """

    def __init__(self) -> None:
        self._validator = SnapshotValidator()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, document: SnapshotDocument, path: Path) -> None:
        """Validate and persist *document* as canonical JSON at *path*.

        Computes integrity hashes if *document* has no stored hashes.
        Writes atomically: temp file + rename.
        """
        # Validate before writing
        result = self._validator.validate(document)
        if not result.is_valid:
            raise ValueError(f"Cannot save invalid snapshot: {', '.join(result.errors[:5])}")

        # If integrity hashes are missing, compute them from the full
        # persistence dict (not the hash summary view).
        doc_to_save = document
        if document.integrity is None:
            from nl2spl.compiler.artifacts.snapshot.hash_policy import HASH_ALGORITHM
            from nl2spl.compiler.artifacts.snapshot.model.integrity import (
                SnapshotIntegrity,
            )

            full_dict = self._document_to_dict(document)
            # payload_hash: full dict minus integrity
            ph_dict = {k: v for k, v in full_dict.items() if k != "integrity"}
            ph = _compute_hash(ph_dict, HASH_ALGORITHM)
            # artifact_set_hash: exclude volatile fields
            ash_dict = deepcopy(ph_dict)
            if "identity" in ash_dict and isinstance(ash_dict["identity"], dict):
                ai = dict(ash_dict["identity"])
                ai.pop("created_at", None)
                ash_dict["identity"] = ai
            if "payload" in ash_dict and isinstance(ash_dict["payload"], dict):
                ash_dict["payload"].pop("editing", None)
            ash = _compute_hash(ash_dict, HASH_ALGORITHM)
            doc_to_save = SnapshotDocument(
                artifact_kind=document.artifact_kind,
                schema_version=document.schema_version,
                identity=document.identity,
                declared_capabilities=document.declared_capabilities,
                payload=document.payload,
                integrity=SnapshotIntegrity(
                    payload_hash=ph,
                    artifact_set_hash=ash,
                ),
            )

        # Serialize using the full persistence format (all payload sections)
        canonical = self._document_to_dict(doc_to_save)
        json_text = canonical_json_dumps(canonical)

        # Atomic write
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".snapshot_tmp_",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json_text)
            os.replace(tmp_path, str(path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def save_overlay(
        self,
        document: SnapshotDocument,
        path: Path,
    ) -> None:
        """Persist an overlay snapshot (same atomic semantics as ``save``)."""
        self.save(document, path)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self, path: Path) -> dict[str, Any]:
        """Load and validate a snapshot JSON file from *path*.

        Returns the validated canonical dict.  The dict is guaranteed to
        have passed full S2 validation (envelope, identity, diagnostics,
        capability derivation, integrity hashes).

        Raises:
            FileNotFoundError: *path* does not exist.
            ValueError: JSON is malformed or S2 validation fails.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Snapshot file not found: {path}")
        if not path.is_file():
            raise ValueError(f"Not a file: {path}")

        # Stage debug JSON must not be loaded as snapshot
        if path.name.startswith("stage") and path.suffix == ".json":
            raise ValueError(
                f"Refusing to load stage debug JSON as snapshot: {path.name}. "
                f"Stage JSON is not a canonical snapshot."
            )

        with open(path, encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in {path}: {e}") from e

        if not isinstance(data, dict):
            raise ValueError(f"Snapshot JSON must be a dict, got {type(data).__name__}")

        # Check required top-level sections before reconstruction
        from nl2spl.compiler.artifacts.snapshot.constants import TOP_LEVEL_SECTIONS

        for section in TOP_LEVEL_SECTIONS:
            if section not in data:
                raise ValueError(f"Snapshot JSON missing required section: {section!r}")

        # Check artifact_kind and schema_version (lightweight, before hash)
        from nl2spl.compiler.artifacts.snapshot.constants import (
            SNAPSHOT_ARTIFACT_KIND,
            SNAPSHOT_SCHEMA_VERSION,
        )
        from nl2spl.compiler.artifacts.snapshot.schema import is_schema_compatible

        if data.get("artifact_kind") != SNAPSHOT_ARTIFACT_KIND:
            raise ValueError(
                f"artifact_kind must be {SNAPSHOT_ARTIFACT_KIND!r}, "
                f"got {data.get('artifact_kind')!r}"
            )
        sv = data.get("schema_version", "")
        if not is_schema_compatible(sv):
            raise ValueError(
                f"Schema version {sv!r} is not compatible. Expected {SNAPSHOT_SCHEMA_VERSION!r}."
            )

        # Persisted snapshots MUST carry integrity hashes
        integ = data.get("integrity")
        if (
            not isinstance(integ, dict)
            or not integ.get("payload_hash")
            or not integ.get("artifact_set_hash")
        ):
            raise ValueError(
                "Persisted snapshot must have non-empty integrity.payload_hash "
                "and integrity.artifact_set_hash"
            )

        # Verify integrity hashes from the loaded JSON dict.
        stored_ph = integ.get("payload_hash", "")
        stored_ah = integ.get("artifact_set_hash", "")
        if stored_ph or stored_ah:
            from nl2spl.compiler.artifacts.snapshot.hash_policy import HASH_ALGORITHM

            ph_dict = {k: v for k, v in data.items() if k != "integrity"}
            if stored_ph:
                computed_ph = _compute_hash(ph_dict, HASH_ALGORITHM)
                if computed_ph != stored_ph:
                    raise ValueError(
                        f"payload_hash mismatch: stored={stored_ph}, computed={computed_ph}"
                    )
            if stored_ah:
                ash_dict = deepcopy(ph_dict)
                if "identity" in ash_dict and isinstance(ash_dict["identity"], dict):
                    ai = dict(ash_dict["identity"])
                    ai.pop("created_at", None)
                    ash_dict["identity"] = ai
                if "payload" in ash_dict and isinstance(ash_dict["payload"], dict):
                    ash_dict["payload"].pop("editing", None)
                computed_ah = _compute_hash(ash_dict, HASH_ALGORITHM)
                if computed_ah != stored_ah:
                    raise ValueError(
                        f"artifact_set_hash mismatch: stored={stored_ah}, computed={computed_ah}"
                    )

        # Reconstruct a SnapshotDocument and run S2 validation
        # (identity, diagnostics, capability derivation — skip integrity).
        doc = self._dict_to_document(data)
        doc = SnapshotDocument(
            artifact_kind=doc.artifact_kind,
            schema_version=doc.schema_version,
            identity=doc.identity,
            declared_capabilities=doc.declared_capabilities,
            payload=doc.payload,
            integrity=None,
        )
        result = self._validator.validate(doc)
        if not result.is_valid:
            raise ValueError(f"S2 validation failed: {'; '.join(result.errors[:5])}")

        return data

    @staticmethod
    def document_from_dict(data: dict[str, Any]) -> SnapshotDocument:
        """Reconstruct a typed ``SnapshotDocument`` from validated JSON data."""
        return JsonFileSnapshotRepository._dict_to_document(data)

    # ------------------------------------------------------------------
    # Internal: document ↔ dict
    # ------------------------------------------------------------------

    @staticmethod
    def _document_to_dict(document: SnapshotDocument) -> dict[str, Any]:
        """Convert a SnapshotDocument to a canonical dict for JSON output."""
        from nl2spl.compiler.artifacts.snapshot.validation.integrity import (
            _serialize_if_present,
        )

        ident = document.identity
        payload = document.payload
        sa = payload.stage_artifacts
        ra = payload.replay_artifacts

        return {
            "artifact_kind": document.artifact_kind,
            "schema_version": document.schema_version,
            "identity": {
                "compile_run_id": ident.compile_run_id,
                "snapshot_id": ident.snapshot_id,
                "base_snapshot_id": ident.base_snapshot_id,
                "parent_snapshot_id": ident.parent_snapshot_id,
                "overlay_version": ident.overlay_version,
                "created_at": ident.created_at,
                "producer": ident.producer,
                "producer_version": ident.producer_version,
            },
            "capabilities": {
                "declared": [c.value for c in document.declared_capabilities.capabilities],
            },
            "payload": {
                "source": {
                    "spans": _serialize_if_present(payload.source.spans),
                    "routes": _serialize_if_present(payload.source.routes),
                    "canonical_input": _serialize_if_present(
                        payload.source.canonical_input,
                    ),
                    "construct_plan": _serialize_if_present(
                        payload.source.construct_plan,
                    ),
                },
                "stage_artifacts": {
                    "worker_plan": _serialize_if_present(sa.worker_plan),
                    "worker_flow_plan": _serialize_if_present(sa.worker_flow_plan),
                    "worker_block_plan": _serialize_if_present(sa.worker_block_plan),
                    "worker_step_plan": _serialize_if_present(sa.worker_step_plan),
                    "resources": _serialize_if_present(sa.resources),
                    "worker_scoped_resources": _serialize_if_present(
                        sa.worker_scoped_resources,
                    ),
                    "symbol_table": _serialize_if_present(sa.symbol_table),
                    "constraints": _serialize_if_present(sa.constraints),
                    "agent_profile": _serialize_if_present(sa.agent_profile),
                },
                "replay_artifacts": {
                    "normalizer_input": _serialize_if_present(ra.normalizer_input),
                    "normalizer_output": _serialize_if_present(ra.normalizer_output),
                    "stage10_input": _serialize_if_present(ra.stage10_input),
                    "assembled_worker_pre_gate": _serialize_if_present(
                        ra.assembled_worker_pre_gate,
                    ),
                    "gated_worker": _serialize_if_present(ra.gated_worker),
                    "final_spl": ra.final_spl,
                },
                "diagnostics": {
                    "compile_diagnostics": _serialize_if_present(
                        payload.diagnostics.compile_diagnostics,
                    ),
                    "post_normalize_diagnostics": _serialize_if_present(
                        payload.diagnostics.post_normalize_diagnostics,
                    ),
                    "gate_diagnostics": _serialize_if_present(
                        payload.diagnostics.gate_diagnostics,
                    ),
                    "render_diagnostics": _serialize_if_present(
                        payload.diagnostics.render_diagnostics,
                    ),
                },
                "provenance": {
                    "traces": _serialize_if_present(payload.provenance.traces),
                    "assumptions": _serialize_if_present(
                        payload.provenance.assumptions,
                    ),
                },
                "editing": {
                    "overlay_events": _serialize_if_present(
                        payload.editing.history.overlay_events,
                    ),
                    "accepted_patches": _serialize_if_present(
                        payload.editing.history.accepted_patches,
                    ),
                    "verification_history": _serialize_if_present(
                        payload.editing.history.verification_history,
                    ),
                    "promotion_resolutions": _serialize_if_present(
                        payload.editing.history.promotion_resolutions,
                    ),
                },
            },
            "integrity": (
                {
                    "payload_hash": document.integrity.payload_hash,
                    "artifact_set_hash": document.integrity.artifact_set_hash,
                }
                if document.integrity
                else None
            ),
        }

    @staticmethod
    def _dict_to_document(data: dict[str, Any]) -> SnapshotDocument:
        """Reconstruct a SnapshotDocument from a loaded JSON dict.

        Deserializes identity, payload layers (source, diagnostics, etc.)
        via S1 registry so that S2 validation — including integrity hash
        verification — can run on the loaded document.
        """
        # Identity
        id_data = data.get("identity", {})
        identity = SnapshotIdentity(
            compile_run_id=id_data.get("compile_run_id", ""),
            snapshot_id=id_data.get("snapshot_id", ""),
            base_snapshot_id=id_data.get("base_snapshot_id", ""),
            parent_snapshot_id=id_data.get("parent_snapshot_id"),
            overlay_version=id_data.get("overlay_version", 0),
            created_at=id_data.get("created_at", ""),
            producer=id_data.get("producer", "nl2spl"),
            producer_version=id_data.get("producer_version", "1.0.0"),
        )

        # Payload — deserialize ALL sections via S1 registry
        payload_data = data.get("payload", {})

        # Source
        src = payload_data.get("source", {})
        source_spans = _deserialize_list(src.get("spans"))
        source_routes = _deserialize_value(src.get("routes"))
        source_input = _deserialize_value(src.get("canonical_input"))
        source_cp = _deserialize_value(src.get("construct_plan"))

        # Stage artifacts
        sa = payload_data.get("stage_artifacts", {})
        sa_worker_plan = _deserialize_value(sa.get("worker_plan"))
        sa_worker_flow = _deserialize_value(sa.get("worker_flow_plan"))
        sa_worker_block = _deserialize_value(sa.get("worker_block_plan"))
        sa_worker_step = _deserialize_value(sa.get("worker_step_plan"))
        sa_resources = _deserialize_value(sa.get("resources"))
        sa_ws_resources = _deserialize_value(sa.get("worker_scoped_resources"))
        sa_symbol_table = _deserialize_value(sa.get("symbol_table"))
        sa_constraints = _deserialize_list(sa.get("constraints"))
        sa_agent_profile = _deserialize_value(sa.get("agent_profile"))

        # Replay artifacts
        ra = payload_data.get("replay_artifacts", {})
        ra_ni = _deserialize_value(ra.get("normalizer_input"))
        ra_no = _deserialize_value(ra.get("normalizer_output"))
        ra_s10 = _deserialize_value(ra.get("stage10_input"))
        ra_pre_gate = _deserialize_value(ra.get("assembled_worker_pre_gate"))
        ra_gated = _deserialize_value(ra.get("gated_worker"))
        ra_final_spl = ra.get("final_spl")

        # Diagnostics
        diag = payload_data.get("diagnostics", {})
        diag_compile = _deserialize_list(diag.get("compile_diagnostics"))
        diag_post_norm = _deserialize_list(diag.get("post_normalize_diagnostics"))
        diag_gate = _deserialize_list(diag.get("gate_diagnostics"))
        diag_render = _deserialize_list(diag.get("render_diagnostics"))

        # Provenance
        prov = payload_data.get("provenance", {})
        prov_traces = _deserialize_list(prov.get("traces"))
        prov_assumptions = _deserialize_list(prov.get("assumptions"))

        # Editing
        edit = payload_data.get("editing", {})
        edit_overlay = _deserialize_list(edit.get("overlay_events"))
        edit_patches = _deserialize_list(edit.get("accepted_patches"))
        edit_verify = _deserialize_list(edit.get("verification_history"))
        edit_resolutions = _deserialize_list(edit.get("promotion_resolutions"))

        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotEditingHistory,
        )
        from nl2spl.compiler.artifacts.snapshot.model.payload import (
            EditingLayer,
            ProvenanceLayer,
            ReplayArtifactsLayer,
            SourceLayer,
            StageArtifactsLayer,
        )

        payload = SnapshotPayload(
            source=SourceLayer(
                spans=tuple(source_spans) if source_spans else (),
                routes=source_routes,
                canonical_input=source_input,
                construct_plan=source_cp,
            ),
            stage_artifacts=StageArtifactsLayer(
                worker_plan=sa_worker_plan,
                worker_flow_plan=sa_worker_flow,
                worker_block_plan=sa_worker_block,
                worker_step_plan=sa_worker_step,
                resources=sa_resources,
                worker_scoped_resources=sa_ws_resources,
                symbol_table=sa_symbol_table,
                constraints=tuple(sa_constraints) if sa_constraints else (),
                agent_profile=sa_agent_profile,
            ),
            replay_artifacts=ReplayArtifactsLayer(
                normalizer_input=ra_ni,
                normalizer_output=ra_no,
                stage10_input=ra_s10,
                assembled_worker_pre_gate=ra_pre_gate,
                gated_worker=ra_gated,
                final_spl=ra_final_spl,
            ),
            diagnostics=DiagnosticsLayer(
                compile_diagnostics=tuple(diag_compile) if diag_compile else (),
                post_normalize_diagnostics=tuple(diag_post_norm) if diag_post_norm else (),
                gate_diagnostics=tuple(diag_gate) if diag_gate else (),
                render_diagnostics=tuple(diag_render) if diag_render else (),
            ),
            provenance=ProvenanceLayer(
                traces=tuple(prov_traces) if prov_traces else (),
                assumptions=tuple(prov_assumptions) if prov_assumptions else (),
            ),
            editing=EditingLayer(
                history=SnapshotEditingHistory(
                    overlay_events=tuple(edit_overlay) if edit_overlay else (),
                    accepted_patches=tuple(edit_patches) if edit_patches else (),
                    verification_history=tuple(edit_verify) if edit_verify else (),
                    promotion_resolutions=(tuple(edit_resolutions) if edit_resolutions else ()),
                ),
            ),
        )

        # Integrity
        integ_data = data.get("integrity")
        integrity = None
        if isinstance(integ_data, dict) and integ_data.get("payload_hash"):
            from nl2spl.compiler.artifacts.snapshot.model.integrity import (
                SnapshotIntegrity,
            )

            integrity = SnapshotIntegrity(
                payload_hash=integ_data.get("payload_hash", ""),
                artifact_set_hash=integ_data.get("artifact_set_hash", ""),
            )

        # Declared capabilities
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotDeclaredCapabilities,
        )

        cap_data = data.get("capabilities", {})
        declared_raw = cap_data.get("declared", ()) if isinstance(cap_data, dict) else ()
        declared = SnapshotDeclaredCapabilities(
            capabilities=tuple(SnapshotCapability(c) for c in declared_raw),
        )

        return SnapshotDocument(
            artifact_kind=data.get("artifact_kind", ""),
            schema_version=data.get("schema_version", ""),
            identity=identity,
            declared_capabilities=declared,
            integrity=integrity,
            payload=payload,
        )


# ---------------------------------------------------------------------------
# Deserialization helpers (lazy S1 registry dispatch)
# ---------------------------------------------------------------------------


def _compute_hash(data: dict, algorithm: str) -> str:
    """Compute a hash string from a canonical dict."""
    import hashlib

    from nl2spl.compiler.artifacts.snapshot.hash_policy import canonical_json_dumps

    digest = hashlib.new(algorithm, canonical_json_dumps(data).encode("utf-8"))
    return f"{algorithm}:{digest.hexdigest()}"


def _deserialize_value(raw: object) -> object:
    """Deserialize a single value via S1 registry if it's a typed dict.

    Unknown ``$type`` values propagate ``ValueError`` from the registry
    (no fallback — must fail fast per S1 contract).
    """
    if raw is None:
        return None
    if isinstance(raw, dict) and "$type" in raw:
        from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
            get_default_registry,
        )

        return get_default_registry().deserialize(raw)
    if isinstance(raw, dict):
        return {str(k): _deserialize_value(v) for k, v in raw.items()}
    return raw


def _deserialize_list(raw: object) -> list:
    """Deserialize a list of typed dicts via S1 registry."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    return [_deserialize_value(item) for item in raw]
