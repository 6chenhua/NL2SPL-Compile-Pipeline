"""Integrity hash computation and validation.

Computes ``payload_hash`` (full document) and ``artifact_set_hash``
(semantic artifacts only, excluding volatile fields).  Uses S1 serializer
registry to produce canonical JSON of actual artifact content, not just
presence/count summaries.
"""

from __future__ import annotations

import hashlib

from nl2spl.compiler.artifacts.snapshot.hash_policy import (
    HASH_ALGORITHM,
    canonical_json_dumps,
)
from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument


def compute_payload_hash(document: SnapshotDocument) -> str:
    """Compute the full payload hash over the complete canonical document.

    Uses ``HASH_ALGORITHM`` (sha256) over the canonical JSON of the
    entire document, with artifacts serialized via S1 registry.
    The ``integrity`` section is excluded from the hash input to avoid
    self-reference.
    """
    canonical = document_to_canonical(document, exclude_volatile=False)
    canonical.pop("integrity", None)
    json_str = canonical_json_dumps(canonical)
    h = hashlib.new(HASH_ALGORITHM, json_str.encode("utf-8"))
    return f"{HASH_ALGORITHM}:{h.hexdigest()}"


def compute_artifact_set_hash(document: SnapshotDocument) -> str:
    """Compute the semantic artifact hash excluding volatile fields.

    Excludes paths listed in ``HashPolicy.artifact_set_excluded_paths``.
    """
    canonical = document_to_canonical(document, exclude_volatile=True)
    canonical.pop("integrity", None)
    json_str = canonical_json_dumps(canonical)
    h = hashlib.new(HASH_ALGORITHM, json_str.encode("utf-8"))
    return f"{HASH_ALGORITHM}:{h.hexdigest()}"


def validate_integrity(
    document: SnapshotDocument,
    payload_hash: str,
    artifact_set_hash: str,
) -> list[str]:
    """Validate stored integrity hashes against computed values.

    Only checks if the document has stored hashes (``integrity`` field
    is not None).  Documents without stored hashes are not validated.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    stored = document.integrity
    if stored is None:
        return errors

    if stored.payload_hash and stored.payload_hash != payload_hash:
        errors.append(
            f"payload_hash mismatch: stored={stored.payload_hash}, "
            f"computed={payload_hash}"
        )
    if stored.artifact_set_hash and stored.artifact_set_hash != artifact_set_hash:
        errors.append(
            f"artifact_set_hash mismatch: stored={stored.artifact_set_hash}, "
            f"computed={artifact_set_hash}"
        )
    return errors


# ---------------------------------------------------------------------------
# Canonical dict conversion — uses S1 serializer for artifact content
# ---------------------------------------------------------------------------


def document_to_canonical(
    document: SnapshotDocument,
    *,
    exclude_volatile: bool,
) -> dict:
    ident = document.identity
    result: dict = {
        "artifact_kind": document.artifact_kind,
        "schema_version": document.schema_version,
        "identity": {
            "compile_run_id": ident.compile_run_id,
            "snapshot_id": ident.snapshot_id,
            "base_snapshot_id": ident.base_snapshot_id,
            "parent_snapshot_id": ident.parent_snapshot_id,
            "overlay_version": ident.overlay_version,
            "producer": ident.producer,
            "producer_version": ident.producer_version,
        },
        "capabilities": {
            "declared": [
                c.value for c in document.declared_capabilities.capabilities
            ],
        },
        "payload": _payload_to_canonical(document, exclude_volatile),
        "integrity": (
            {
                "payload_hash": document.integrity.payload_hash,
                "artifact_set_hash": document.integrity.artifact_set_hash,
            }
            if document.integrity else None
        ),
    }

    if not exclude_volatile:
        result["identity"]["created_at"] = ident.created_at

    return result


def _payload_to_canonical(document: SnapshotDocument, exclude_volatile: bool) -> dict:
    payload = document.payload
    sa = payload.stage_artifacts
    ra = payload.replay_artifacts

    # Serialize stage artifacts using S1 registry (lazy import to avoid circular)
    result: dict = {
        "source": {
            "spans": _serialize_if_present(payload.source.spans),
            "routes": _serialize_if_present(payload.source.routes),
            "canonical_input": _serialize_if_present(payload.source.canonical_input),
            "construct_plan": _serialize_if_present(payload.source.construct_plan),
        },
        "stage_artifacts": {
            "worker_plan": _serialize_if_present(sa.worker_plan),
            "worker_flow_plan": _serialize_if_present(sa.worker_flow_plan),
            "worker_block_plan": _serialize_if_present(sa.worker_block_plan),
            "worker_step_plan": _serialize_if_present(sa.worker_step_plan),
            "resources": _serialize_if_present(sa.resources),
            "worker_scoped_resources": _serialize_if_present(
                sa.worker_scoped_resources
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
                ra.assembled_worker_pre_gate
            ),
            "gated_worker": _serialize_if_present(ra.gated_worker),
            "final_spl": ra.final_spl,
        },
        "diagnostics": {
            "compile_diagnostics": _serialize_if_present(
                payload.diagnostics.compile_diagnostics
            ),
            "post_normalize_diagnostics": _serialize_if_present(
                payload.diagnostics.post_normalize_diagnostics
            ),
            "gate_diagnostics": _serialize_if_present(
                payload.diagnostics.gate_diagnostics
            ),
            "render_diagnostics": _serialize_if_present(
                payload.diagnostics.render_diagnostics
            ),
        },
        "provenance": {
            "traces": _serialize_if_present(payload.provenance.traces),
            "assumptions": _serialize_if_present(payload.provenance.assumptions),
        },
    }

    if not exclude_volatile:
        result["editing"] = {
            "overlay_events": _serialize_if_present(
                payload.editing.history.overlay_events,
            ),
            "accepted_patches": _serialize_if_present(
                payload.editing.history.accepted_patches,
            ),
            "verification_history": _serialize_if_present(
                payload.editing.history.verification_history,
            ),
        }

    return result


def _serialize_if_present(value: object) -> object:
    """Return serialized form of *value* if non-None, else None.

    Uses S1 registry for dataclass/IR objects.  For types not registered
    in S1, passes through as-is (assumed JSON-native primitive).  Does NOT
    fall back to ``__dict__`` or ``str()`` — unknown types must fail fast.
    """
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        items = [_serialize_if_present(v) for v in value]
        return items if isinstance(value, list) else items
    if isinstance(value, dict):
        return {
            str(k): _serialize_if_present(v)
            for k, v in value.items()
        }

    from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
        get_default_registry,
    )

    registry = get_default_registry()
    try:
        registry.get_by_class(type(value))
    except ValueError:
        return value

    return registry.serialize(value)
