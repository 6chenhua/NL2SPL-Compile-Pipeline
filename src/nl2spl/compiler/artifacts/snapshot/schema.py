"""Schema version and compatibility policy for snapshot documents.

Defines the canonical schema version string, the compatibility gate,
and the list of supported versions.  The S2 validator uses these to
reject documents with an incompatible schema version before any
further validation is attempted.
"""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.artifacts.snapshot.constants import SNAPSHOT_SCHEMA_VERSION

# ---------------------------------------------------------------------------
# Re-export for convenience
# ---------------------------------------------------------------------------

__all__ = [
    "SNAPSHOT_SCHEMA_VERSION",
    "SchemaVersionInfo",
    "is_schema_compatible",
    "supported_versions",
]

# ---------------------------------------------------------------------------
# Schema version info
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchemaVersionInfo:
    """Canonical schema version and compatibility metadata.

    Attributes:
        current: The current schema version string (e.g. ``"1.0.0"``).
        supported: Tuple of all schema versions that are compatible with
            the current loader.
        compatibility_policy: How version matching works.  MVP uses
            ``"exact_match"`` -- only the exact current version is accepted.
    """

    current: str = SNAPSHOT_SCHEMA_VERSION
    supported: tuple[str, ...] = (SNAPSHOT_SCHEMA_VERSION,)
    compatibility_policy: str = "exact_match"


# ---------------------------------------------------------------------------
# Compatibility check
# ---------------------------------------------------------------------------


def is_schema_compatible(version: str, *, info: SchemaVersionInfo | None = None) -> bool:
    """Return ``True`` if *version* is compatible with the current loader.

    MVP policy: exact match only.  ``"1.0.0"`` accepts only ``"1.0.0"``.

    The ``compatibility_policy`` field on *info* controls the matching
    strategy.  Unknown policies raise ``ValueError`` (fail-fast).

    Args:
        version: The schema version string from a snapshot document.
        info: Optional ``SchemaVersionInfo`` override (for testing).

    Returns:
        ``True`` if the version is compatible.

    Raises:
        ValueError: If *info* has an unknown ``compatibility_policy``.
    """
    if info is None:
        info = _DEFAULT_INFO
    if info.compatibility_policy == "exact_match":
        return version == info.current
    raise ValueError(
        f"Unknown compatibility_policy: {info.compatibility_policy!r}. "
        f"Supported policies: exact_match"
    )


def supported_versions(*, info: SchemaVersionInfo | None = None) -> tuple[str, ...]:
    """Return the tuple of all supported schema version strings.

    Args:
        info: Optional ``SchemaVersionInfo`` override (for testing).

    Returns:
        Tuple of supported version strings.
    """
    if info is None:
        info = _DEFAULT_INFO
    return info.supported


# ---------------------------------------------------------------------------
# Default singleton -- cached to avoid repeated construction
# ---------------------------------------------------------------------------

_DEFAULT_INFO = SchemaVersionInfo()
