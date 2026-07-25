"""DTO serializers for SPL Web Demo API handlers."""

from __future__ import annotations

import dataclasses
import enum
from pathlib import Path
from typing import Any

from nl2spl.compiler.spl_editing.interaction.model import RepairInteractionView
from nl2spl.compiler.spl_editing.presentation.model.issue import (
    IssueCardView,
    IssueDetailPresentationView,
    RepairOptionView,
)
from nl2spl.compiler.spl_editing.presentation.model.run import RunPresentationView
from nl2spl.compiler.spl_editing.presentation.model.sections import (
    IssueListPresentationView,
    IssueSectionView,
)
from spl_web_demo.card_projector import SplConstructCard
from spl_web_demo.document_projector import SplDocumentNode
from spl_web_demo.provenance_projector import (
    ConstructProvenancePresentation,
    SpanPresentation,
    TracePresentation,
)


def construct_card_to_api(card: SplConstructCard) -> dict[str, Any]:
    return {
        "construct_ref": card.construct_ref,
        "construct_type": card.construct_type,
        "title": card.title,
        "status": card.status,
        "payload_summary": _safe(card.payload_summary),
        "provenance_summary": _safe(card.provenance_summary),
        "source_span_ids": list(card.source_span_ids),
        "parent_ref": card.parent_ref,
        "construct_path": list(card.construct_path),
    }


def construct_provenance_to_api(
    value: ConstructProvenancePresentation,
) -> dict[str, Any]:
    return {
        "construct_ref": value.construct_ref,
        "construct_type": value.construct_type,
        "title": value.title,
        "trace_status": value.trace_status,
        "provenance_kind": value.provenance_kind,
        "matched_target_refs": list(value.matched_target_refs),
        "source_span_ids": list(value.source_span_ids),
        "unresolved_span_ids": list(value.unresolved_span_ids),
        "traces": [trace_provenance_to_api(item) for item in value.traces],
        "spans": [span_to_api(item) for item in value.spans],
    }


def trace_provenance_to_api(value: TracePresentation) -> dict[str, Any]:
    repair = value.repair
    return {
        "target_ref": value.target_ref,
        "relation": value.relation,
        "explanation": value.explanation,
        "needs_confirmation": value.needs_confirmation,
        "source_section_id": value.source_section_id,
        "source_packet_id": value.source_packet_id,
        "source_span_ids": list(value.source_span_ids),
        "repair": (
            {
                "repair_patch_id": repair.repair_patch_id,
                "related_diagnostic_id": repair.related_diagnostic_id,
                "user_text": repair.user_text,
            }
            if repair is not None
            else None
        ),
    }


def span_to_api(value: SpanPresentation) -> dict[str, Any]:
    return {
        "span_id": value.span_id,
        "text": value.text,
        "source_section_id": value.source_section_id,
        "source_packet_id": value.source_packet_id,
        "section_context": value.section_context,
        "is_placeholder": value.is_placeholder,
        "ambiguity": {
            "is_ambiguous": value.ambiguity_is_ambiguous,
            "reasons": list(value.ambiguity_reasons),
            "needs_split": value.ambiguity_needs_split,
        },
    }


def run_view_to_api(
    view: RunPresentationView,
    *,
    api_run_id: str,
    editing_available: bool,
) -> dict[str, Any]:
    return {
        "run_id": api_run_id,
        "editing_run_id": view.run_id,
        "snapshot_id": view.snapshot_id,
        "snapshot_status": view.snapshot_status,
        "overlay_version": view.overlay_version,
        "editing_available": editing_available,
        "issue_count": view.issue_count,
        "issue_summary": [category_summary_to_api(item) for item in view.issue_summary],
    }


def issue_list_to_api(view: IssueListPresentationView) -> dict[str, Any]:
    return {
        "run_id": view.run_id,
        "snapshot_id": view.snapshot_id,
        "summary": [category_summary_to_api(item) for item in view.summary],
        "sections": [issue_section_to_api(section) for section in view.sections],
    }


def issue_section_to_api(section: IssueSectionView) -> dict[str, Any]:
    return {
        "section_id": _value(section.section_key),
        "title": section.label,
        "section_kind": _value(section.section_kind),
        "visible_by_default": section.visible_by_default,
        "items": [issue_card_to_api(item) for item in section.items],
    }


def category_summary_to_api(summary: Any) -> dict[str, Any]:
    return {
        "category": _value(summary.category),
        "label": summary.label,
        "count": summary.count,
    }


def issue_card_to_api(card: IssueCardView) -> dict[str, Any]:
    return {
        "display_id": card.display_id,
        "issue_id": card.issue_id,
        "category": _value(card.category),
        "title": card.title,
        "impact": card.impact,
        "fix_label": card.fix_label,
        "suggested_resolution": card.suggested_resolution,
        "source_excerpt": card.source_excerpt,
        "missing_items": list(card.missing_items),
        "repairability": card.repairability,
        "can_fix": card.can_fix,
        "presentation_quality": _value(card.presentation_quality),
    }


def issue_detail_to_api(
    detail: IssueDetailPresentationView,
    *,
    explanation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "issue": {
            "issue_id": detail.issue_id,
            "title": detail.title,
            "what_was_detected": detail.what_was_detected,
            "missing_items": list(detail.missing_items),
            "why_it_matters": detail.why_it_matters,
            "suggested_resolution": detail.suggested_resolution,
            "source_context": detail.source_context,
            "presentation_quality": _value(detail.presentation_quality),
            "available_repairs": [repair_option_to_api(item) for item in detail.available_repairs],
        },
        "explanation": explanation,
    }


def repair_option_to_api(option: RepairOptionView) -> dict[str, Any]:
    return {
        "label": option.label,
        "description": option.description,
        "option_id": option.option_id,
        "strategy_id": option.strategy_id,
        "interaction_contract_id": option.interaction_contract_id,
        "interaction_summary": option.interaction_summary,
        "patch_types": list(option.patch_types),
        "verification_lane": option.verification_lane,
        "availability": _value(option.availability),
        "unavailable_reason": option.unavailable_reason,
    }


def interaction_to_api(view: RepairInteractionView) -> dict[str, Any]:
    fields = [repair_field_to_api(field) for field in view.fields]
    unsupported = sorted(
        {
            field["input_type"]
            for field in fields
            if field["input_type"]
            not in {"short_text", "long_text", "single_choice", "multi_choice"}
        }
    )
    result = {
        "issue_id": view.issue_id,
        "strategy_id": view.strategy_id,
        "option_id": view.option_id,
        "contract_id": view.contract_id,
        "contract_version": view.contract_version,
        "revision_token": view.revision_token,
        "interaction_kind": view.interaction_kind,
        "availability": view.availability,
        "input_readiness": view.input_readiness,
        "fields": fields,
        "schemas": [_safe(schema) for schema in view.schemas],
        "validation_errors": [_safe(error) for error in view.validation_errors],
    }
    if unsupported:
        result["demo_availability"] = "unsupported_in_mvp"
        result["unsupported_fields"] = unsupported
    return result


def repair_field_to_api(field: Any) -> dict[str, Any]:
    return {
        "field_id": field.field_id,
        "label": field.label,
        "input_type": field.input_type,
        "required": field.required,
        "description": field.description,
        "value": field.value,
        "options": [_safe(option) for option in field.options],
        "ref_role": field.ref_role,
        "object_schema_id": field.object_schema_id,
        "fact_schema_id": field.fact_schema_id,
    }


def preview_handle_to_api(handle: Any) -> dict[str, Any]:
    preview = handle.preview
    typed = getattr(preview, "typed_artifact", None)
    construct_nodes = getattr(typed, "construct_nodes", ()) if typed is not None else ()
    return {
        "directive_id": handle.directive_id,
        "session_id": handle.session_id,
        "suggestion_id": handle.suggestion_id,
        "preview": {
            "preview_id": getattr(preview, "preview_id", None),
            "base_snapshot_id": getattr(preview, "base_snapshot_id", None),
            "rendered_preview": getattr(preview, "rendered_preview", None),
            "typed_artifact_summary": {
                "type": type(typed).__name__ if typed is not None else None,
                "construct_node_count": len(construct_nodes or ()),
                "construct_roles": sorted(
                    {getattr(node, "role", "") for node in construct_nodes or ()}
                ),
            },
            "spl_cards": [],
        },
    }


def verification_to_api(value: Any) -> dict[str, Any]:
    return {
        "accepted": getattr(value, "accepted", None),
        "lane": getattr(value, "lane", None),
        "failure_reasons": list(getattr(value, "failure_reasons", ()) or ()),
        "diagnostic_diff_summary": getattr(value, "diagnostic_diff_summary", None),
        "resolved_diagnostic_ids": list(getattr(value, "resolved_diagnostic_ids", ()) or ()),
        "new_blocking_diagnostic_ids": list(
            getattr(value, "new_blocking_diagnostic_ids", ()) or ()
        ),
    }


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value):
        return {
            field.name: _safe(getattr(value, field.name)) for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(_safe(key)): _safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_safe(item) for item in value]
    return repr(value)


def _value(value: Any) -> Any:
    return value.value if isinstance(value, enum.Enum) else value


def spl_document_node_to_api(node: SplDocumentNode) -> dict[str, Any]:
    return {
        "node_ref": node.node_ref,
        "node_kind": node.node_kind,
        "node_type": node.node_type,
        "construct_ref": node.construct_ref,
        "parent_node_ref": node.parent_node_ref,
        "order": node.order,
        "title": node.title,
        "summary": node.summary,
        "status": node.status,
        "attributes": _safe(node.attributes),
        "provenance_summary": _safe(node.provenance_summary),
    }


def spl_document_response_to_api(
    run_id: str,
    snapshot_id: str | None,
    overlay_version: int,
    revision_token: str | None,
    projection_status: str,
    projection_fidelity: str,
    nodes: tuple[SplDocumentNode, ...],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "overlay_version": overlay_version,
        "revision_token": revision_token,
        "projection_status": projection_status,
        "projection_fidelity": projection_fidelity,
        "nodes": [spl_document_node_to_api(node) for node in nodes],
    }
