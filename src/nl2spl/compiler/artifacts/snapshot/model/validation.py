"""Snapshot validation and capability model.

Defines:
    - ``SnapshotDeclaredCapabilities``: what the writer claims.
    - ``SnapshotEffectiveCapabilities``: what the validator confirms.
    - ``SnapshotValidationResult``: aggregate validation outcome.
    - ``SnapshotCapabilityFailure``: per-capability failure detail.

.. important::

    SPL Editing MUST only trust ``SnapshotEffectiveCapabilities`` after
    validation.  ``SnapshotDeclaredCapabilities`` is the writer's claim
    and may be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability

# ---------------------------------------------------------------------------
# Declared capabilities — writer's claim
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotDeclaredCapabilities:
    """The capabilities the snapshot writer *claims* are available.

    These are stored in the JSON document but MUST NOT be trusted by
    SPL Editing until the validator derives effective capabilities.
    """

    capabilities: tuple[SnapshotCapability, ...] = ()
    """Set of declared capabilities."""

    def has(self, capability: SnapshotCapability) -> bool:
        """Return ``True`` if *capability* is declared."""
        return capability in self.capabilities

    @property
    def count(self) -> int:
        """Number of declared capabilities."""
        return len(self.capabilities)


# ---------------------------------------------------------------------------
# Effective capabilities — validator's authority
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotEffectiveCapabilities:
    """The capabilities the validator *confirms* are available.

    These are derived by inspecting actual artifact presence, schema
    validity, diagnostic metadata, and replay bundle completeness.
    SPL Editing MUST gate all operations on these values.
    """

    capabilities: tuple[SnapshotCapability, ...] = ()
    """Set of confirmed (effective) capabilities."""

    failures: tuple[SnapshotCapabilityFailure, ...] = ()
    """Details for each capability that was declared but not effective."""

    def has(self, capability: SnapshotCapability) -> bool:
        """Return ``True`` if *capability* is confirmed effective."""
        return capability in self.capabilities

    def require(self, capability: SnapshotCapability) -> None:
        """Raise ``SnapshotCapabilityError`` if *capability* is not effective.

        This is the gate that SPL Editing operations call before proceeding.
        """
        if not self.has(capability):
            failure = _find_failure(self.failures, capability)
            reason = failure.reason if failure else "not in effective set"
            from nl2spl.compiler.artifacts.snapshot.model.errors import (
                SnapshotCapabilityError,
            )

            raise SnapshotCapabilityError(capability.value, reason)

    @property
    def count(self) -> int:
        """Number of effective capabilities."""
        return len(self.capabilities)

    @classmethod
    def none(cls) -> SnapshotEffectiveCapabilities:
        """Return an instance with no effective capabilities."""
        return cls()


# ---------------------------------------------------------------------------
# Capability failure detail
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotCapabilityFailure:
    """Describes why a declared capability is not effective.

    Attributes:
        capability: The capability that failed.
        reason: Human-readable explanation (e.g. ``"missing_normalizer_input_bundle"``).
        missing_paths: Dotted payload paths that were missing or null.
        unmet_conditions: Semantic conditions that were not satisfied.
    """

    capability: SnapshotCapability
    reason: str
    missing_paths: tuple[str, ...] = ()
    unmet_conditions: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotValidationResult:
    """Aggregate result of validating a snapshot document.

    Attributes:
        is_valid: ``True`` when the document passes all checks.
        errors: Top-level validation errors (schema, identity, integrity).
        effective_capabilities: Validator-derived capabilities.
        capability_failures: Per-capability failure details.
    """

    is_valid: bool
    errors: tuple[str, ...] = ()
    effective_capabilities: SnapshotEffectiveCapabilities = field(
        default_factory=SnapshotEffectiveCapabilities.none,
    )
    capability_failures: tuple[SnapshotCapabilityFailure, ...] = ()

    @classmethod
    def valid(
        cls,
        effective: SnapshotEffectiveCapabilities,
    ) -> SnapshotValidationResult:
        """Create a successful validation result."""
        return cls(
            is_valid=True,
            effective_capabilities=effective,
            capability_failures=effective.failures,
        )

    @classmethod
    def invalid(
        cls,
        errors: tuple[str, ...],
        *,
        effective: SnapshotEffectiveCapabilities | None = None,
        failures: tuple[SnapshotCapabilityFailure, ...] = (),
    ) -> SnapshotValidationResult:
        """Create a failed validation result."""
        return cls(
            is_valid=False,
            errors=errors,
            effective_capabilities=effective or SnapshotEffectiveCapabilities.none(),
            capability_failures=failures,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_failure(
    failures: tuple[SnapshotCapabilityFailure, ...],
    capability: SnapshotCapability,
) -> SnapshotCapabilityFailure | None:
    for f in failures:
        if f.capability == capability:
            return f
    return None
