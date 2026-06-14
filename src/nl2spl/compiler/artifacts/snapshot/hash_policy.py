"""Hash policy for snapshot artifact integrity.

Defines the canonical hashing rules that distinguish two hash scopes:

``payload_hash``
    Storage integrity hash over the complete canonical JSON payload.
    Used to detect file corruption or DB tampering.

``artifact_set_hash``
    Semantic compiler artifact hash over the validation-normalized
    artifact set, excluding volatile fields (``created_at``, validation
    status/errors, runtime display fields, overlay editing history that
    does not change stage artifacts).

These hashes are computed by the S2 validator.  The S-1 contract only
defines the algorithm, canonical serialization parameters, and the
volatile field exclusion set.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Hash algorithm
# ---------------------------------------------------------------------------

HASH_ALGORITHM: str = "sha256"
"""Cryptographic hash algorithm used for both payload and artifact-set hashes."""

# ---------------------------------------------------------------------------
# Canonical JSON serialization for hashing
# ---------------------------------------------------------------------------

CANONICAL_JSON_SORT_KEYS: bool = True
CANONICAL_JSON_SEPARATORS: tuple[str, str] = (",", ":")
CANONICAL_JSON_ENSURE_ASCII: bool = False

CANONICAL_JSON_DUMPS_KWARGS: dict[str, object] = {
    "sort_keys": CANONICAL_JSON_SORT_KEYS,
    "separators": CANONICAL_JSON_SEPARATORS,
    "ensure_ascii": CANONICAL_JSON_ENSURE_ASCII,
}
"""Keyword arguments for ``json.dumps()`` when producing canonical hash input.

Includes ``ensure_ascii=False`` so that non-ASCII characters are preserved
rather than escaped into ``\\uXXXX`` sequences.  All hash callers MUST use
these kwargs unmodified to guarantee deterministic output.
"""


def canonical_json_dumps(obj: object) -> str:
    """Serialize *obj* to a canonical JSON string for hashing.

    Uses ``sort_keys=True``, compact separators, and ``ensure_ascii=False``.
    This is the single correct entry point for producing canonical JSON for
    hash computation.  Callers MUST NOT pass additional kwargs.

    Args:
        obj: A JSON-serializable object whose values have already been
            normalized to JSON-native types (no ``Path``, ``datetime``,
            ``Enum``, or ``tuple`` objects).

    Returns:
        Deterministic JSON string suitable for hashing.
    """
    return json.dumps(obj, **CANONICAL_JSON_DUMPS_KWARGS)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Hash scope definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HashPolicy:
    """Canonical hash policy for snapshot artifacts.

    Attributes:
        algorithm: Hash algorithm name (e.g. ``"sha256"``).
        payload_hash_description: What ``payload_hash`` covers.
        artifact_set_hash_description: What ``artifact_set_hash`` covers.
        artifact_set_excluded_paths: Dotted payload paths excluded from
            ``artifact_set_hash`` computation.  These are volatile fields
            that do not change compiler-state semantics.
    """

    algorithm: str = HASH_ALGORITHM
    payload_hash_description: str = (
        "Complete canonical JSON payload hash.  Covers the full normalized "
        "payload including all sections, volatile fields, and editing history.  "
        "Used to detect file corruption, DB tampering, or incomplete writes."
    )
    artifact_set_hash_description: str = (
        "Semantic compiler artifact hash.  Covers only the core compiler "
        "artifacts that affect issue extraction, replay, and verification.  "
        "Excludes volatile fields such as created_at, validation status/errors, "
        "and overlay editing history that does not modify stage artifacts."
    )
    artifact_set_excluded_paths: tuple[str, ...] = (
        "identity.created_at",
        "integrity.validation_status",
        "integrity.validation_errors",
        "payload.editing.overlay_events",
        "payload.editing.accepted_patches",
        "payload.editing.verification_history",
    )


# ---------------------------------------------------------------------------
# Default singleton
# ---------------------------------------------------------------------------

HASH_POLICY: HashPolicy = HashPolicy()
"""Default hash policy instance.  Import this unless you need an override."""

# ---------------------------------------------------------------------------
# Overlay MVP strategy
# ---------------------------------------------------------------------------

OVERLAY_STRATEGY: str = "full_json_document"
"""MVP overlay strategy.

Base snapshots and overlay snapshots are BOTH full JSON documents.
Compact JSON patch delta is a future optimization, not part of MVP.
"""

OVERLAY_FILENAME_PREFIX: str = "spl_editing_overlays"
"""Subdirectory name under ``output/<run_name>/`` for overlay snapshots."""

# ---------------------------------------------------------------------------
# Hash normalization constraints
# ---------------------------------------------------------------------------

# Hash input must already be serialized to canonical JSON values.
# The hash layer MUST NOT perform ad-hoc conversion of Path, datetime,
# Enum, or tuple objects.  If the serializer has not completed canonical
# normalization, the hash layer MUST fail fast.

HASH_INPUT_MUST_BE_NORMALIZED: str = (
    "Hash input must already be canonical JSON values (no Path, datetime, "
    "Enum, or tuple objects).  The serializer is responsible for converting "
    "all non-JSON-native types before the hash layer runs."
)
