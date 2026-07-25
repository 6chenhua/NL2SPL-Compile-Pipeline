"""Deterministic annotation normalization from canonical role contract.

Provides the single entry point for building a ``RouteAnnotation`` from
a ``semantic_role`` using the canonical role contract registry.  All
annotation generation paths (LLM refinement, deterministic packet,
route-prior, legacy compatibility) MUST use this API so that
compiler-facing fields are always contract-derived.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from nl2spl.compiler.annotation_role_contract.registry import (
    ROLE_CONTRACT_REGISTRY,
)
from nl2spl.ir.field_route_ir import RouteAnnotation


@dataclass
class NormalizedAnnotation:
    """Result of deterministic annotation normalization.

    ``annotation`` carries the confirmed ``RouteAnnotation`` with every
    compiler-facing field derived from the canonical role contract.

    ``diagnostics`` records every field that was corrected from a raw
    LLM/hint value to its contract value.

    ``raw_*`` fields preserve the original LLM/hint values for debug
    and audit visibility.
    """

    annotation: RouteAnnotation
    """Confirmed annotation with contract-derived fields."""

    diagnostics: list[str] = field(default_factory=list)
    """Human-readable corrections: 'field: LLM gave X, contract requires Y'."""

    # Raw LLM/hint values before normalization (debug/audit only)
    raw_field: str | None = None
    raw_route_family: str | None = None
    raw_construct_target: str | None = None
    raw_slot_target: str | None = None
    raw_executable: bool | None = None


def normalize_annotation_from_role(
    span_id: str,
    semantic_role: str,
    *,
    source_section_id: str | None = None,
    source_packet_id: str | None = None,
    source_hint_ids: Iterable[str] = (),
    primary: bool = True,
    metadata: Mapping[str, Any] | None = None,
    # ── raw LLM/hint values (preserved for diagnostics) ───────────
    raw_field: str | None = None,
    raw_route_family: str | None = None,
    raw_construct_target: str | None = None,
    raw_slot_target: str | None = None,
    raw_executable: bool | None = None,
) -> NormalizedAnnotation:
    """Build a confirmed ``RouteAnnotation`` from a ``semantic_role``.

    Every compiler-facing field (``field``, ``route_family``,
    ``construct_target``, ``slot_target``, ``executable``) is derived
    from the canonical role contract.  Raw LLM/hint values are preserved
    for diagnostic visibility but are NEVER authoritative.

    Args:
        span_id: The span this annotation describes.
        semantic_role: Canonical semantic role (after alias resolution).
        source_section_id: Adapter section provenance.
        source_packet_id: Adapter packet provenance.
        source_hint_ids: CompileHint ids that informed this annotation.
        primary: Whether this is the primary annotation for the span.
        metadata: Additional metadata (e.g. ``requiredness``).
            Requiredness is carried through untouched — it is NOT derived
            by role contract.
        raw_field: Raw ``field`` from LLM/hint (diagnostic only).
        raw_route_family: Raw ``route_family`` from LLM/hint.
        raw_construct_target: Raw ``construct_target`` from LLM/hint.
        raw_slot_target: Raw ``slot_target`` from LLM/hint.
        raw_executable: Raw ``executable`` from LLM/hint.

    Returns:
        ``NormalizedAnnotation`` with confirmed annotation and diagnostics.
    """
    contract = ROLE_CONTRACT_REGISTRY.require_role_contract(semantic_role)
    diagnostics: list[str] = []

    def _check(name: str, raw_value: Any, contract_value: Any) -> None:
        if raw_value is not None and raw_value != contract_value:
            diagnostics.append(
                f"Role contract correction for span '{span_id}' "
                f"({semantic_role}): {name} was {raw_value!r}, "
                f"contract requires {contract_value!r}"
            )

    _check("field", raw_field, contract.field)
    _check("route_family", raw_route_family, contract.route_family)
    _check("construct_target", raw_construct_target, contract.construct_target)
    _check("slot_target", raw_slot_target, contract.slot_target)
    _check("executable", raw_executable, contract.executable)

    ann = RouteAnnotation(
        span_id=span_id,
        field=contract.field,
        semantic_role=contract.semantic_role,
        route_family=contract.route_family,
        construct_target=contract.construct_target,
        slot_target=contract.slot_target,
        executable=contract.executable,
        source_section_id=source_section_id,
        source_packet_id=source_packet_id,
        source_hint_ids=list(source_hint_ids),
        primary=primary,
    )

    # Requiredness passes through untouched
    if metadata:
        ann.metadata.update(metadata)
    if _is_explicit_api_action_override(contract.semantic_role, ann.metadata):
        ann.construct_target = "CALL_API"
        ann.slot_target = "call_action"
        ann.executable = True
    # Store raw values in metadata for downstream diagnostic projection
    ann.metadata.setdefault("_raw_", {})
    if raw_field is not None and raw_field != contract.field:
        ann.metadata["_raw_"]["field"] = raw_field  # type: ignore[index]
    if raw_route_family is not None and raw_route_family != contract.route_family:
        ann.metadata["_raw_"]["route_family"] = raw_route_family  # type: ignore[index]
    if raw_construct_target is not None and raw_construct_target != contract.construct_target:
        ann.metadata["_raw_"]["construct_target"] = raw_construct_target  # type: ignore[index]
    if raw_slot_target is not None and raw_slot_target != contract.slot_target:
        ann.metadata["_raw_"]["slot_target"] = raw_slot_target  # type: ignore[index]
    if raw_executable is not None and raw_executable != contract.executable:
        ann.metadata["_raw_"]["executable"] = raw_executable  # type: ignore[index]

    return NormalizedAnnotation(
        annotation=ann,
        diagnostics=diagnostics,
        raw_field=raw_field,
        raw_route_family=raw_route_family,
        raw_construct_target=raw_construct_target,
        raw_slot_target=raw_slot_target,
        raw_executable=raw_executable,
    )


def _is_explicit_api_action_override(
    semantic_role: str,
    metadata: Mapping[str, Any],
) -> bool:
    return (
        semantic_role == "process_step"
        and metadata.get("api_action") is True
        and metadata.get("api_group_id") not in (None, "")
    )
