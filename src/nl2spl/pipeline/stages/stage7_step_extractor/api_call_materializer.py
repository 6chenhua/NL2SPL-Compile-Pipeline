"""Stage 7 direct CALL_API materialization from bound and placed demands."""

from __future__ import annotations

import hashlib
import re

from nl2spl.compiler.construct_plan import (
    APICallArgumentBindingIR,
    APICallDemand,
    APICallPlacementIR,
    ConstructPlan,
)
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR
from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
    APICallBindingIR,
    APIMaterializationPlanIR,
)


def materialize_direct_api_calls(
    worker_step_plan: WorkerStepPlanIR,
    construct_plan: ConstructPlan,
    api_materialization_plan: APIMaterializationPlanIR,
    api_call_placements: list[APICallPlacementIR],
    resources: ResourceRegistryIR,
) -> list[CompileDiagnostic]:
    """Append direct CALL_API steps for bound + placed API call demands."""
    diagnostics: list[CompileDiagnostic] = []
    bindings = {
        binding.declaration_demand_id: binding for binding in api_materialization_plan.bindings
    }
    placements = {placement.call_demand_id: placement for placement in api_call_placements}
    argument_bindings: dict[str, list[APICallArgumentBindingIR]] = {}
    for argument_binding in construct_plan.api_call_argument_bindings:
        argument_bindings.setdefault(argument_binding.call_demand_id, []).append(argument_binding)
    apis = {api.api_id: api for api in resources.apis}

    for call in construct_plan.api_call_demands():
        if call.behavior_lowering_policy == "ambiguous":
            diagnostics.append(_unresolved_warning(call, "ambiguous_operation_coverage"))
            continue
        binding = _binding_for_call(call, bindings)
        placement = placements.get(call.demand_id)
        if binding is None:
            diagnostics.append(_unresolved_warning(call, "binding_not_resolved"))
            continue
        if placement is None:
            diagnostics.append(_unresolved_warning(call, "placement_missing"))
            continue
        if placement.status != "placed":
            diagnostics.append(
                _unresolved_warning(
                    call,
                    f"placement_{placement.status}",
                    placement.reason,
                )
            )
            continue
        missing_placement_fields = [
            field_name
            for field_name, value in (
                ("owner_worker_id", placement.owner_worker_id),
                ("flow_ref", placement.flow_ref),
                ("block_ref", placement.block_ref),
            )
            if not value
        ]
        if missing_placement_fields:
            diagnostics.append(
                _unresolved_warning(
                    call,
                    "placement_incomplete",
                    ", ".join(missing_placement_fields),
                )
            )
            continue
        api = apis.get(binding.api_id)
        if api is None:
            diagnostics.append(_unresolved_warning(call, "api_spec_missing"))
            continue
        call_argument_bindings = argument_bindings.get(call.demand_id, [])
        if len(call_argument_bindings) != 1:
            diagnostics.append(
                _unresolved_warning(
                    call,
                    "argument_binding_missing"
                    if not call_argument_bindings
                    else "argument_binding_duplicate",
                    f"binding_artifact_count={len(call_argument_bindings)}",
                )
            )
            continue
        argument_binding = call_argument_bindings[0]
        if argument_binding.binding_status in {
            "partially_bound",
            "unbound",
        }:
            diagnostics.append(
                _unresolved_warning(
                    call,
                    f"argument_binding_{argument_binding.binding_status}",
                    ", ".join(argument_binding.unresolved_binding_claims),
                )
            )
            continue
        if argument_binding.binding_status == "not_required" and (
            argument_binding.input_bindings or argument_binding.output_bindings
        ):
            diagnostics.append(
                _unresolved_warning(
                    call,
                    "argument_binding_not_required_has_bindings",
                )
            )
            continue
        coverage_issue = _operation_coverage_issue(call)
        if coverage_issue is not None:
            diagnostics.append(
                _unresolved_warning(call, "operation_coverage_ambiguous", coverage_issue)
            )
            continue
        diagnostics.extend(_sanitize_general_command_fallbacks(worker_step_plan, call))
        step = _step_from_call(call, binding, placement, api, argument_binding)
        worker_steps = worker_step_plan.worker_steps.setdefault(
            placement.owner_worker_id,
            [],
        )
        if not any(existing.step_id == step.step_id for existing in worker_steps):
            worker_steps.append(step)

    return diagnostics


def _binding_for_call(
    call: APICallDemand,
    bindings: dict[str, APICallBindingIR],
) -> APICallBindingIR | None:
    if call.declaration_demand_id is None:
        return None
    return bindings.get(call.declaration_demand_id)


def _step_from_call(
    call: APICallDemand,
    binding: APICallBindingIR,
    placement: APICallPlacementIR,
    api: APISpec,
    argument_binding: APICallArgumentBindingIR,
) -> StepIR:
    inputs = _binding_values(argument_binding.input_bindings)
    outputs = _binding_values(argument_binding.output_bindings)
    return StepIR(
        step_id=_step_id(call.demand_id),
        text=call.action_text or f"Call {api.api_name}.",
        source_span_ids=list(call.source_span_ids),
        command_type="CALL_API",
        inputs=inputs,
        outputs=outputs,
        integration_ref=api.api_name,
        flow_ref=placement.flow_ref,
        block_ref=placement.block_ref,
        kind="tool",
        metadata={
            "origin": "source_backed",
            "construct_demand_ids": [call.demand_id],
            "api_id": api.api_id,
            "declaration_demand_id": binding.declaration_demand_id,
            "api_binding_id": binding.api_binding_id,
            "placement_ref": placement.placement_ref,
            "capability_intent_id": call.capability_intent_id or "",
            "argument_binding_status": argument_binding.binding_status,
            "argument_binding_source_span_ids": list(argument_binding.source_span_ids),
        },
    )


def _sanitize_general_command_fallbacks(
    worker_step_plan: WorkerStepPlanIR,
    call: APICallDemand,
) -> list[CompileDiagnostic]:
    diagnostics: list[CompileDiagnostic] = []
    consumed_spans = set(call.consumes_behavior_span_ids or call.source_span_ids)
    coverage_by_span = _coverage_by_span(call)

    for worker_id, steps in list(worker_step_plan.worker_steps.items()):
        kept: list[StepIR] = []
        for step in steps:
            if step.command_type != "GENERAL_COMMAND":
                kept.append(step)
                continue

            if _is_same_demand_general_command_fallback(step, call):
                diagnostics.append(
                    _sanitized_warning(
                        call,
                        step,
                        "same_demand_general_command_fallback_removed",
                    )
                )
                continue

            if not consumed_spans.intersection(step.source_span_ids):
                kept.append(step)
                continue

            if call.behavior_lowering_policy == "api_call_replaces_behavior":
                if _step_covers_operation(step, coverage_by_span):
                    diagnostics.append(
                        _sanitized_warning(
                            call,
                            step,
                            "covered_operation_general_command_removed",
                        )
                    )
                    continue
                kept.append(step)
                continue

            if call.behavior_lowering_policy in {
                "api_call_augments_behavior",
                "keep_residual_behavior_only",
            }:
                residual = _residual_text(step, coverage_by_span)
                if residual is None:
                    kept.append(step)
                    continue
                if residual:
                    original_text = step.text
                    step.text = residual
                    step.metadata = dict(step.metadata or {})
                    step.metadata["api_call_residual_for_demand_id"] = call.demand_id
                    step.metadata["api_call_removed_operation_text"] = original_text
                    diagnostics.append(
                        _sanitized_warning(
                            call,
                            step,
                            "general_command_trimmed_to_residual_behavior",
                        )
                    )
                    kept.append(step)
                    continue
                diagnostics.append(
                    _sanitized_warning(
                        call,
                        step,
                        "covered_operation_general_command_removed",
                    )
                )
                continue

            kept.append(step)
        worker_step_plan.worker_steps[worker_id] = kept
    return diagnostics


def _coverage_by_span(call: APICallDemand) -> dict[str, list[tuple[str, int | None, int | None]]]:
    grouped: dict[str, list[tuple[str, int | None, int | None]]] = {}
    for coverage in call.operation_coverage:
        grouped.setdefault(coverage.source_span_id, []).append(
            (coverage.operation_surface, coverage.char_start, coverage.char_end)
        )
    return grouped


def _binding_values(bindings: dict[str, str]) -> list[str]:
    return [value for _key, value in sorted(bindings.items()) if value]


def _step_covers_operation(
    step: StepIR,
    coverage_by_span: dict[str, list[tuple[str, int | None, int | None]]],
) -> bool:
    for span_id in step.source_span_ids:
        for surface, start, end in coverage_by_span.get(span_id, []):
            if (
                surface
                and start is not None
                and end is not None
                and 0 <= start < end <= len(step.text)
                and step.text[start:end] == surface
            ):
                return True
    return False


def _residual_text(
    step: StepIR,
    coverage_by_span: dict[str, list[tuple[str, int | None, int | None]]],
) -> str | None:
    text = step.text
    removals: list[tuple[int, int]] = []
    for span_id in step.source_span_ids:
        for surface, start, end in coverage_by_span.get(span_id, []):
            if not surface:
                continue
            if (
                start is not None
                and end is not None
                and 0 <= start < end <= len(text)
                and text[start:end] == surface
            ):
                removals.append((start, end))
                continue
    if not removals:
        return None
    removals = _merge_ranges(removals)
    pieces: list[str] = []
    cursor = 0
    for start, end in removals:
        pieces.append(text[cursor:start])
        cursor = end
    pieces.append(text[cursor:])
    return _cleanup_residual("".join(pieces))


def _operation_coverage_issue(
    call: APICallDemand,
) -> str | None:
    """Return why exact Stage 3 coverage is unsafe for Stage 7 lowering."""
    if not call.operation_coverage:
        return "operation_coverage_missing"
    for coverage in call.operation_coverage:
        if coverage.char_start is None or coverage.char_end is None:
            return f"coverage_offsets_missing:{coverage.coverage_id}"
        if coverage.char_start < 0 or coverage.char_end <= coverage.char_start:
            return f"coverage_offsets_invalid:{coverage.coverage_id}"
    return None


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _cleanup_residual(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^(and|then|,|;|\.)\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+(and|then|,|;)$", "", value, flags=re.IGNORECASE)
    value = value.strip(" ,;.")
    if value and value[-1] not in ".!?":
        value = f"{value}."
    return value


def _is_same_demand_general_command_fallback(
    step: StepIR,
    call: APICallDemand,
) -> bool:
    metadata = step.metadata or {}
    if metadata.get("api_call_demand_id") == call.demand_id:
        return True
    if metadata.get("fallback_for_api_call_demand_id") == call.demand_id:
        return True
    construct_demand_ids = metadata.get("construct_demand_ids")
    if isinstance(construct_demand_ids, list) and call.demand_id in construct_demand_ids:
        return True
    if isinstance(construct_demand_ids, tuple) and call.demand_id in construct_demand_ids:
        return True
    return False


def _sanitized_warning(
    call: APICallDemand,
    step: StepIR,
    reason: str,
) -> CompileDiagnostic:
    return CompileDiagnostic(
        diagnostic_id=_warning_id(call.demand_id, f"{step.step_id}:{reason}"),
        kind="stage7_sanitized_general_command_fallback",
        severity="warning",
        message=(
            "Sanitized GENERAL_COMMAND fallback for source-backed API call "
            f"demand {call.demand_id}: {reason}."
        ),
        target_ref=f"api_call_demand:{call.demand_id}",
        source_span_ids=list(call.source_span_ids),
        metadata={
            "api_call_demand_id": call.demand_id,
            "step_id": step.step_id,
            "reason": reason,
        },
        blocks_rendering=False,
        blocks_completion=False,
    )


def _unresolved_warning(
    call: APICallDemand,
    reason: str,
    detail: str | None = None,
) -> CompileDiagnostic:
    return CompileDiagnostic(
        diagnostic_id=_warning_id(call.demand_id, reason),
        kind="stage7_unresolved_api_call_materialization",
        severity="warning",
        message=(
            f"API call demand {call.demand_id} was not materialized: {reason}"
            + (f" ({detail})" if detail else "")
        ),
        target_ref=f"api_call_demand:{call.demand_id}",
        source_span_ids=list(call.source_span_ids),
        metadata={
            "api_call_demand_id": call.demand_id,
            "declaration_demand_id": call.declaration_demand_id,
            "reason": reason,
            "detail": detail or "",
        },
        blocks_rendering=False,
        blocks_completion=True,
    )


def _step_id(call_demand_id: str) -> str:
    digest = hashlib.sha1(call_demand_id.encode("utf-8")).hexdigest()[:10]
    return f"st_api_{digest}"


def _warning_id(call_demand_id: str, step_id: str) -> str:
    digest = hashlib.sha1(f"{call_demand_id}|{step_id}".encode()).hexdigest()[:10]
    return f"diag_stage7_api_{digest}"
