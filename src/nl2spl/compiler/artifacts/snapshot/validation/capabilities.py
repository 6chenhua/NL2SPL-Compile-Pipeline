"""Effective capability derivation from artifact presence.

Uses the S-1 ``CAPABILITY_REQUIREMENTS`` matrix to determine which
capabilities are actually effective based on what artifacts exist
in the document payload.
"""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.capabilities import (
    CAPABILITY_REQUIREMENTS,
    SPL_EDITING_EDITABLE_DIAGNOSTIC_KINDS,
    SnapshotCapability,
)
from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument
from nl2spl.compiler.artifacts.snapshot.model.validation import (
    SnapshotCapabilityFailure,
    SnapshotEffectiveCapabilities,
)


def derive_effective_capabilities(
    document: SnapshotDocument,
) -> SnapshotEffectiveCapabilities:
    """Derive which capabilities are actually effective for *document*.

    For each capability in ``CAPABILITY_REQUIREMENTS``:
    1. Check that all ``depends_on`` capabilities are effective.
    2. Check that all ``required_payload_paths`` resolve to non-None values.
    3. Check that ``required_conditions`` are met.

    Returns ``SnapshotEffectiveCapabilities`` with the effective set
    and failure details for unmet capabilities.
    """
    effective_set: set[SnapshotCapability] = set()
    failures: list[SnapshotCapabilityFailure] = []

    # Process in dependency order (CAPABILITY_REQUIREMENTS is already ordered)
    for req in CAPABILITY_REQUIREMENTS:
        missing_paths: list[str] = []
        unmet_conditions: list[str] = []

        # 1. Check dependencies are effective
        deps_ok = True
        for dep in req.depends_on:
            if dep not in effective_set:
                deps_ok = False
                missing_paths.append(f"depends_on:{dep.value} (not effective)")
                unmet_conditions.append(f"upstream capability {dep.value} is not effective")

        if not deps_ok:
            failures.append(
                SnapshotCapabilityFailure(
                    capability=req.capability,
                    reason="Upstream dependency not effective",
                    missing_paths=tuple(missing_paths),
                    unmet_conditions=tuple(unmet_conditions),
                )
            )
            continue

        # 2. Check required payload paths
        for path in req.required_payload_paths:
            if not _resolve_path(document, path):
                missing_paths.append(path)

        # 3. Check required conditions
        for condition in req.required_conditions:
            if not _check_condition(document, condition):
                unmet_conditions.append(condition)

        if missing_paths or unmet_conditions:
            failures.append(
                SnapshotCapabilityFailure(
                    capability=req.capability,
                    reason=_build_reason(missing_paths, unmet_conditions),
                    missing_paths=tuple(missing_paths),
                    unmet_conditions=tuple(unmet_conditions),
                )
            )
        else:
            effective_set.add(req.capability)

    return SnapshotEffectiveCapabilities(
        capabilities=tuple(effective_set),
        failures=tuple(failures),
    )


# ---------------------------------------------------------------------------
# Path resolution — walk S0 model attributes
# ---------------------------------------------------------------------------


def _resolve_path(document: SnapshotDocument, path: str) -> bool:
    """Return ``True`` if *path* resolves to a non-None, non-empty value.

    Paths use dot notation rooted at the document, e.g.:
    ``payload.diagnostics.compile_diagnostics``
    """
    parts = path.split(".")
    current: object = document
    for part in parts:
        if current is None:
            return False
        if hasattr(current, part):
            current = getattr(current, part)
        else:
            return False

    # Non-None and non-empty check
    if current is None:
        return False
    if isinstance(current, (list, tuple, str, dict, set)):
        return len(current) > 0  # type: ignore[arg-type]
    return True


# ---------------------------------------------------------------------------
# Condition checking
# ---------------------------------------------------------------------------


def _check_condition(document: SnapshotDocument, condition: str) -> bool:
    """Check a human-readable condition against *document*.

    MVP: conditions are descriptive strings.  The validator checks known
    patterns and returns ``True`` for unknown conditions (future-proof).
    """
    payload = document.payload
    diags = payload.diagnostics.compile_diagnostics

    if "at least one editable diagnostic" in condition:
        return len(_editable_diagnostics(diags)) > 0

    # Condition: editable diagnostics have metadata.irs_ref
    if "irs_ref" in condition and "editable diagnostic" in condition:
        return _all_editable_diags_satisfy(
            diags,
            lambda meta: (
                "irs_ref" in meta
                and _irs_ref_has_valid_values(meta["irs_ref"])
            ),
        )

    # Condition: editable diagnostics have metadata.authority
    if "authority" in condition:
        return _all_editable_diags_satisfy(
            diags,
            lambda meta: (
                "authority" in meta
                and isinstance(meta["authority"], str)
                and meta["authority"].strip() != ""
            ),
        )

    # Condition: editable diagnostics have metadata.repairability
    if "repairability" in condition:
        return _all_editable_diags_satisfy(
            diags,
            lambda meta: (
                "repairability" in meta
                and isinstance(meta["repairability"], str)
                and meta["repairability"].strip() != ""
            ),
        )

    # Condition: editable diagnostics have metadata.issue_group_id
    if "issue_group_id" in condition:
        return _all_editable_diags_satisfy(
            diags,
            lambda meta: (
                "issue_group_id" in meta
                and isinstance(meta["issue_group_id"], str)
                and meta["issue_group_id"].strip() != ""
            ),
        )

    # Condition: source spans are present
    if "source spans" in condition:
        return len(payload.source.spans) > 0

    # Condition: provenance traces are present
    if "provenance traces" in condition:
        return len(payload.provenance.traces) > 0

    # Condition: stage10_input / normalizer_input bundle present
    if "stage10_input" in condition:
        return payload.replay_artifacts.stage10_input is not None
    if "normalizer_input" in condition:
        return payload.replay_artifacts.normalizer_input is not None
    if "normalizer_output" in condition:
        return payload.replay_artifacts.normalizer_output is not None

    # Condition: baseline final SPL is present
    if "final SPL" in condition or "final_spl" in condition:
        return payload.replay_artifacts.final_spl is not None

    # Condition: worker_flow_plan / worker_block_plan present
    if "worker_flow_plan" in condition:
        return payload.stage_artifacts.worker_flow_plan is not None
    if "worker_block_plan" in condition:
        return payload.stage_artifacts.worker_block_plan is not None

    # Condition: WorkerAssembler dependencies available
    if "WorkerAssembler" in condition:
        sa = payload.stage_artifacts
        return (
            sa.worker_plan is not None
            and sa.worker_step_plan is not None
            and sa.resources is not None
            and sa.symbol_table is not None
        )

    # Condition: patched SPL display goes through Lane A/B replay
    if "patched SPL" in condition or "Lane A/B" in condition:
        # This is a design constraint, not a checkable condition
        return True

    # Unknown condition: return True (don't block on future conditions)
    return True


def _all_editable_diags_satisfy(
    diags: tuple, predicate: object,
) -> bool:
    """Return True if all editable diagnostics satisfy *predicate*."""
    editable = _editable_diagnostics(diags)
    if not editable:
        return False
    return all(
        d.metadata and predicate(d.metadata)  # type: ignore[operator]
        for d in editable
    )


def _editable_diagnostics(diags: tuple) -> list:
    from nl2spl.ir.diagnostics import CompileDiagnostic

    return [
        d for d in diags
        if isinstance(d, CompileDiagnostic)
        and getattr(d, "kind", "") in SPL_EDITING_EDITABLE_DIAGNOSTIC_KINDS
    ]


def _irs_ref_has_valid_values(irs_ref: object) -> bool:
    """Return True if irs_ref has non-empty construct_type, construct_id, slot_name."""
    from nl2spl.ir.diagnostics import DiagnosticIRSRef

    if isinstance(irs_ref, DiagnosticIRSRef):
        return bool(
            irs_ref.construct_type.strip()
            and irs_ref.construct_id.strip()
            and irs_ref.slot_name.strip()
        )
    if isinstance(irs_ref, dict):
        for key in ("construct_type", "construct_id", "slot_name"):
            val = irs_ref.get(key, "")
            if not isinstance(val, str) or not val.strip():
                return False
        return True
    return False


def _build_reason(missing_paths: list[str], unmet_conditions: list[str]) -> str:
    parts: list[str] = []
    if missing_paths:
        parts.append(f"missing: {', '.join(missing_paths)}")
    if unmet_conditions:
        parts.append(f"unmet: {', '.join(unmet_conditions)}")
    return "; ".join(parts) if parts else "unknown"
