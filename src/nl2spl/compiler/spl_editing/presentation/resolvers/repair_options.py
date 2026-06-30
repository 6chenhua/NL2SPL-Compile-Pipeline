"""Repair option availability resolver."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.model import EditableIssue, UserFacingIssue
from nl2spl.compiler.spl_editing.core.registry import SPLEditingRuntimeRegistry
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.presentation.contract.availability import (
    RepairOptionAvailability,
)
from nl2spl.compiler.spl_editing.presentation.model.issue import RepairOptionView
from nl2spl.compiler.spl_editing.presentation.templates.repair_option_copy import (
    option_copy,
    option_label,
    patch_description,
)
from nl2spl.compiler.spl_editing.presentation.templates.unavailable_reasons import (
    unavailable_reason,
)


def repair_options_for_issue(
    issue: EditableIssue | UserFacingIssue,
    entries: tuple[RepairCatalogEntry, ...],
    runtime: SPLEditingRuntimeRegistry,
    snapshot: ArtifactSnapshot,
) -> tuple[RepairOptionView, ...]:
    if issue.repairability != "editable":
        return (
            _option(
                (),
                "",
                RepairOptionAvailability.REVIEW_ONLY,
            ),
        )

    result: list[RepairOptionView] = []
    for entry in entries:
        if entry.strategy_options:
            for option in entry.strategy_options:
                availability = _option_availability(entry, option, runtime, snapshot)
                result.append(
                    RepairOptionView(
                        option_id=option.option_id,
                        strategy_id=option.strategy_id,
                        interaction_contract_id=option.interaction_contract_id,
                        interaction_summary=option_copy(option.description_key),
                        label=option_copy(option.label_key),
                        description=option_copy(option.description_key),
                        patch_types=option.execution_patch_types,
                        verification_lane=entry.default_verification_lane,
                        availability=availability,
                        unavailable_reason=unavailable_reason(availability),
                    )
                )
            continue
        availability = _availability(entry, runtime, snapshot)
        if entry.patch_type_metadata:
            for meta in entry.patch_type_metadata:
                result.append(
                    _option_single(
                        patch_type=meta.patch_type,
                        label=meta.label,
                        description=meta.description,
                        verification_lane=meta.verification_lane,
                        availability=availability,
                    )
                )
        else:
            result.append(
                _option(
                    entry.supported_patch_types,
                    entry.default_verification_lane,
                    availability,
                )
            )
    if result:
        return tuple(result)
    return (
        _option(
            (),
            "",
            RepairOptionAvailability.UNAVAILABLE_UNSUPPORTED_PATCH_TYPE,
        ),
    )


def _availability(
    entry: RepairCatalogEntry,
    runtime: SPLEditingRuntimeRegistry,
    snapshot: ArtifactSnapshot,
    *,
    check_patch_types: bool = True,
) -> RepairOptionAvailability:
    if not entry.user_facing:
        return RepairOptionAvailability.REVIEW_ONLY
    if not _snapshot_supports_lane(snapshot, entry.default_verification_lane):
        return RepairOptionAvailability.UNAVAILABLE_SNAPSHOT_CAPABILITY
    if entry.handler_id is None or not runtime.handlers.has(entry.handler_id):
        return RepairOptionAvailability.UNAVAILABLE_MISSING_HANDLER
    if entry.target_resolver_id is None or not runtime.target_resolvers.has(
        entry.target_resolver_id
    ):
        return RepairOptionAvailability.UNAVAILABLE_MISSING_TARGET_RESOLVER
    if entry.context_id is None or not runtime.context_builders.has(entry.context_id):
        return RepairOptionAvailability.UNAVAILABLE_MISSING_CONTEXT_BUILDER
    if not check_patch_types:
        return RepairOptionAvailability.AVAILABLE
    if not entry.supported_patch_types:
        return RepairOptionAvailability.UNAVAILABLE_UNSUPPORTED_PATCH_TYPE
    if not any(runtime.patches.has(patch_type) for patch_type in entry.supported_patch_types):
        return RepairOptionAvailability.UNAVAILABLE_UNSUPPORTED_PATCH_TYPE
    return RepairOptionAvailability.AVAILABLE


def _option_availability(entry, option, runtime, snapshot) -> RepairOptionAvailability:
    base = _availability(entry, runtime, snapshot, check_patch_types=False)
    if base != RepairOptionAvailability.AVAILABLE:
        return base
    if not option.user_facing:
        return RepairOptionAvailability.REVIEW_ONLY
    if not option.execution_patch_types or not all(
        runtime.patches.has(patch_type) for patch_type in option.execution_patch_types
    ):
        return RepairOptionAvailability.UNAVAILABLE_UNSUPPORTED_PATCH_TYPE
    return RepairOptionAvailability.AVAILABLE


def _snapshot_supports_lane(snapshot: ArtifactSnapshot, lane: str) -> bool:
    if lane not in {"A", "B"}:
        return True
    required = (
        snapshot.worker_plan,
        snapshot.worker_flow_plan,
        snapshot.worker_block_plan,
        snapshot.worker_step_plan,
        snapshot.resources,
        snapshot.symbol_table,
    )
    return all(value is not None for value in required)


def _option(
    patch_types: tuple[str, ...],
    verification_lane: str,
    availability: RepairOptionAvailability,
) -> RepairOptionView:
    label = option_label(patch_types)
    first_patch = patch_types[0] if patch_types else ""
    reason = unavailable_reason(availability)
    return RepairOptionView(
        label=label,
        description=patch_description(first_patch) if first_patch else (reason or ""),
        patch_types=patch_types,
        verification_lane=verification_lane,
        availability=availability,
        unavailable_reason=reason,
    )


def _option_single(
    *,
    patch_type: str,
    label: str,
    description: str,
    verification_lane: str,
    availability: RepairOptionAvailability,
) -> RepairOptionView:
    reason = unavailable_reason(availability)
    return RepairOptionView(
        label=label,
        description=description,
        patch_types=(patch_type,),
        verification_lane=verification_lane,
        availability=availability,
        unavailable_reason=reason,
    )


__all__ = ["repair_options_for_issue"]
