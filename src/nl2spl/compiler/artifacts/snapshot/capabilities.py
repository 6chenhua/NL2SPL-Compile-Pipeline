"""Capability model for the SPL Editing artifact snapshot.

Defines the canonical capability enum and the derivation matrix that maps
each capability to its required payload fields and conditions.

.. important::

    ``SnapshotWriter`` may *declare* intended capabilities in the JSON
    document, but ``SnapshotValidator`` is the sole authority that
    *derives* effective capabilities by inspecting artifact presence,
    schema validity, diagnostic metadata, and replay bundle completeness.

    SPL Editing MUST only trust effective capabilities after validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Capability enum
# ---------------------------------------------------------------------------


class SnapshotCapability(str, Enum):  # noqa: UP042
    """Capabilities a snapshot may support.

    Each capability gates a specific SPL Editing operation.  A snapshot
    may support some capabilities but not others -- for example, it may
    support issue extraction but lack the normalizer input bundle required
    for Lane B replay.
    """

    ISSUE_EXTRACTION = "issue_extraction"
    """The snapshot supports extracting editable issues from diagnostics."""

    SUGGESTION_GENERATION = "suggestion_generation"
    """The snapshot supports generating repair suggestions for extracted issues."""

    LANE_A_REPLAY = "lane_a_replay"
    """The snapshot supports Lane A replay (patched Stage 10 input -> assemble -> gate)."""

    LANE_B_REPLAY = "lane_b_replay"
    """The snapshot supports Lane B replay (patched normalizer input -> normalize -> Lane A)."""

    FINAL_SPL_DISPLAY = "final_spl_display"
    """The snapshot includes the final rendered SPL for display."""


# ---------------------------------------------------------------------------
# Canonical capability ordering
# ---------------------------------------------------------------------------

CAPABILITIES_IN_ORDER: tuple[SnapshotCapability, ...] = (
    SnapshotCapability.ISSUE_EXTRACTION,
    SnapshotCapability.SUGGESTION_GENERATION,
    SnapshotCapability.LANE_A_REPLAY,
    SnapshotCapability.LANE_B_REPLAY,
    SnapshotCapability.FINAL_SPL_DISPLAY,
)
"""Capabilities in dependency order (upstream first, downstream last)."""

# ---------------------------------------------------------------------------
# Production flow required capabilities
# ---------------------------------------------------------------------------

PRODUCTION_REQUIRED_CAPABILITIES: tuple[SnapshotCapability, ...] = (
    SnapshotCapability.ISSUE_EXTRACTION,
    SnapshotCapability.SUGGESTION_GENERATION,
    SnapshotCapability.LANE_A_REPLAY,
    SnapshotCapability.LANE_B_REPLAY,
    SnapshotCapability.FINAL_SPL_DISPLAY,
)
"""Capabilities required for a production SPL Editing flow."""

SPL_EDITING_EDITABLE_DIAGNOSTIC_KINDS: tuple[str, ...] = (
    "missing_handler",
    "missing_output_producer",
    "type_or_contract_ambiguity",
)
"""Diagnostic kinds that can be used as SPL Editing repair targets."""

# ---------------------------------------------------------------------------
# Capability requirement specification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityRequirement:
    """Specification of what a capability depends on.

    Each capability has:
    - ``depends_on``: upstream capabilities that must also be effective.
    - ``required_payload_paths``: dotted JSON payload paths that must be
      present and non-null.
    - ``required_conditions``: human-readable semantic conditions that the
      validator checks (e.g., diagnostic metadata shape).
    """

    capability: SnapshotCapability
    """The capability this requirement describes."""

    depends_on: tuple[SnapshotCapability, ...] = ()
    """Upstream capabilities that must be effective for this one to work."""

    required_payload_paths: tuple[str, ...] = ()
    """Dotted paths into the JSON payload that must be present and non-null.

    Uses dot-notation: ``payload.diagnostics.compile_diagnostics``.
    """

    required_conditions: tuple[str, ...] = ()
    """Human-readable semantic conditions checked by the validator.

    Examples:
        - ``editable diagnostics have metadata.irs_ref``
        - ``replay artifact copies have source_ref or derived_from``
    """


# ---------------------------------------------------------------------------
# Capability derivation matrix
# ---------------------------------------------------------------------------

CAPABILITY_REQUIREMENTS: tuple[CapabilityRequirement, ...] = (
    CapabilityRequirement(
        capability=SnapshotCapability.ISSUE_EXTRACTION,
        required_payload_paths=(
            "payload.diagnostics.compile_diagnostics",
        ),
        required_conditions=(
            "at least one editable diagnostic is present",
            "editable diagnostics have metadata.irs_ref",
            "editable diagnostics have metadata.authority",
            "editable diagnostics have metadata.repairability",
            "editable diagnostics have metadata.issue_group_id",
        ),
    ),
    CapabilityRequirement(
        capability=SnapshotCapability.SUGGESTION_GENERATION,
        depends_on=(SnapshotCapability.ISSUE_EXTRACTION,),
        required_payload_paths=(
            "payload.source.spans",
            "payload.provenance.traces",
        ),
        required_conditions=(
            "source spans are present for context building",
            "provenance traces are present for target resolution",
        ),
    ),
    CapabilityRequirement(
        capability=SnapshotCapability.LANE_A_REPLAY,
        required_payload_paths=(
            "payload.replay_artifacts.stage10_input",
            "payload.stage_artifacts.worker_plan",
            "payload.stage_artifacts.worker_flow_plan",
            "payload.stage_artifacts.worker_block_plan",
            "payload.stage_artifacts.worker_step_plan",
            "payload.stage_artifacts.resources",
            "payload.stage_artifacts.symbol_table",
        ),
        required_conditions=(
            "stage10_input bundle is present and complete",
            "worker_flow_plan present -- required by WorkerAssembler.assemble_from_worker_scoped",
            "worker_block_plan present -- required by WorkerAssembler.assemble_from_worker_scoped",
        ),
    ),
    CapabilityRequirement(
        capability=SnapshotCapability.LANE_B_REPLAY,
        depends_on=(SnapshotCapability.LANE_A_REPLAY,),
        required_payload_paths=(
            "payload.replay_artifacts.normalizer_input",
            "payload.replay_artifacts.normalizer_output",
        ),
        required_conditions=(
            "normalizer_input bundle is present and complete",
            "normalizer_output is present for equivalence comparison",
        ),
    ),
    CapabilityRequirement(
        capability=SnapshotCapability.FINAL_SPL_DISPLAY,
        required_payload_paths=(
            "payload.replay_artifacts.final_spl",
        ),
        required_conditions=(
            "baseline final SPL is present for display",
            "patched SPL display must go through Lane A/B replay",
        ),
    ),
)
"""Capability derivation matrix.

Maps each ``SnapshotCapability`` to the payload paths and semantic
conditions that MUST be satisfied for the capability to be *effective*.

The ``SnapshotValidator`` (S2) uses this matrix to derive effective
capabilities from raw artifact presence.  If any required payload path
is missing or any condition is not met, the effective capability is
``False`` regardless of what the writer declared.

Hierarchical dependencies (``depends_on``) mean that if an upstream
capability is not effective, downstream capabilities are also
unavailable even if their own paths are present.
"""

# ---------------------------------------------------------------------------
# Derived lookup table
# ---------------------------------------------------------------------------

CAPABILITY_REQUIREMENT_BY_CAPABILITY: dict[SnapshotCapability, CapabilityRequirement] = {
    r.capability: r for r in CAPABILITY_REQUIREMENTS
}
"""O(1) lookup of capability requirements by capability enum value."""
