"""Stage 7 direct CALL_API materialization from bound and placed demands.

Short-term API residual fix: remove after P6/P7.
"""

from __future__ import annotations

import hashlib

from nl2spl.compiler.construct_plan import (
    APICallArgumentBindingIR,
    APICallDemand,
    APICallPlacementIR,
    ConstructPlan,
)
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR
from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
    APICallBindingIR,
    APIMaterializationPlanIR,
)
from nl2spl.pipeline.stages.stage7_step_extractor.action_model import (
    ExecutableActionIR,
)
from nl2spl.pipeline.stages.stage7_step_extractor.action_projection import (
    APIResidualActionProjection,
    APIResidualActionProjector,
)


def materialize_direct_api_calls(
    worker_step_plan: WorkerStepPlanIR,
    construct_plan: ConstructPlan,
    api_materialization_plan: APIMaterializationPlanIR,
    api_call_placements: list[APICallPlacementIR],
    resources: ResourceRegistryIR,
    spans: list[SpanIR] | None = None,
    projections_by_call_id: dict[str, APIResidualActionProjection] | None = None,
) -> list[CompileDiagnostic]:
    """Append direct CALL_API steps for bound + placed API call demands.

    Short-term residual fix shim, remove after P6/P7.
    """
    diagnostics: list[CompileDiagnostic] = []
    bindings = {
        binding.declaration_demand_id: binding
        for binding in api_materialization_plan.bindings
    }
    placements = {placement.call_demand_id: placement for placement in api_call_placements}
    argument_bindings: dict[str, list[APICallArgumentBindingIR]] = {}
    for argument_binding in construct_plan.api_call_argument_bindings:
        argument_bindings.setdefault(argument_binding.call_demand_id, []).append(
            argument_binding
        )
    apis = {api.api_id: api for api in resources.apis}
    span_by_id = _span_by_id(spans, construct_plan)

    projector = APIResidualActionProjector()

    for call in construct_plan.api_call_demands():
        if call.behavior_lowering_policy == "ambiguous":
            cov_id = (
                call.operation_coverage[0].coverage_id
                if call.operation_coverage
                else ""
            )
            diagnostics.append(
                CompileDiagnostic(
                    diagnostic_id=_warning_id(call.demand_id, "ambiguous_coverage"),
                    kind="stage7_api_residual_coverage_ambiguous",
                    severity="warning",
                    message=(
                        f"API call demand {call.demand_id} has ambiguous "
                        f"operation coverage: ambiguous_lowering_policy"
                    ),
                    target_ref=f"api_call_demand:{call.demand_id}",
                    source_span_ids=list(call.source_span_ids),
                    metadata={
                        "call_demand_id": call.demand_id,
                        "coverage_id": cov_id,
                        "source_span_ids": list(call.source_span_ids),
                        "reason": "ambiguous_lowering_policy",
                    },
                    blocks_rendering=False,
                    blocks_completion=True,
                )
            )
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

        # Project actions
        projection = projector.project(
            call=call,
            span_by_id=span_by_id,
            placement=placement,
        )
        if projections_by_call_id is not None:
            projections_by_call_id[call.demand_id] = projection
        if projection.diagnostics:
            diagnostics.extend(projection.diagnostics)
            continue

        # Sanitize fallback general commands and add residual commands
        diagnostics.extend(
            _sanitize_general_command_fallbacks(worker_step_plan, call, projection)
        )

        if projection.call_action is None:
            diagnostics.append(_unresolved_warning(call, "call_action_missing"))
            continue

        step = _step_from_call_action(
            projection.call_action,
            call,
            binding,
            placement,
            api,
            argument_binding,
        )
        worker_steps = worker_step_plan.worker_steps.setdefault(
            placement.owner_worker_id,
            [],
        )
        conflict = _find_call_api_conflict(worker_steps, call, step)
        if conflict is not None:
            diagnostics.append(_duplicate_api_action_claim(call, step, conflict))
            continue

        if not any(existing.step_id == step.step_id for existing in worker_steps):
            worker_steps.append(step)

        # Materialize residual GENERAL_COMMAND steps if they exist
        for res_action in projection.residual_actions:
            guard_diag = _guard_only_residual_diagnostic(res_action, call)
            if guard_diag is not None:
                diagnostics.append(guard_diag)
                continue
            if _has_existing_non_fallback_general_step(worker_steps, res_action, call):
                continue

            res_step_id = res_action.action_id
            if not res_step_id.startswith("st"):
                res_step_id = f"st_{res_step_id}"

            already_exists = False
            for existing in worker_steps:
                existing_action_id = (
                    existing.metadata.get("action_id") if existing.metadata else None
                )
                if existing.step_id == res_step_id or existing_action_id == res_action.action_id:
                    already_exists = True
                    break

            if already_exists:
                continue

            res_step = StepIR(
                step_id=res_step_id,
                text=res_action.action_text,
                source_span_ids=list(res_action.source_span_ids),
                command_type="GENERAL_COMMAND",
                inputs=[],
                outputs=[],  # no-output residual
                flow_ref=res_action.flow_ref,
                block_ref=res_action.block_ref,
                kind="normal",
                metadata={
                    "origin": "residual_generated",
                    "action_id": res_action.action_id,
                    "owning_authority": res_action.owning_authority,
                    "api_call_demand_id": call.demand_id,
                },
            )
            if not any(existing.step_id == res_step.step_id for existing in worker_steps):
                worker_steps.append(res_step)

    return diagnostics


def _binding_for_call(
    call: APICallDemand,
    bindings: dict[str, APICallBindingIR],
) -> APICallBindingIR | None:
    if call.declaration_demand_id is None:
        return None
    return bindings.get(call.declaration_demand_id)


def _step_from_call_action(
    action: ExecutableActionIR,
    call: APICallDemand,
    binding: APICallBindingIR,
    placement: APICallPlacementIR,
    api: APISpec,
    argument_binding: APICallArgumentBindingIR,
) -> StepIR:
    inputs = _binding_values(argument_binding.input_bindings)
    output_bindings = dict(sorted(argument_binding.output_bindings.items()))
    outputs = _binding_values(output_bindings) if _api_response_contract_known(api) else []
    metadata = {
        "origin": "source_backed",
        "action_id": action.action_id,
        "owning_authority": action.owning_authority,
        "construct_demand_ids": [call.demand_id],
        "api_id": api.api_id,
        "declaration_demand_id": binding.declaration_demand_id,
        "api_binding_id": binding.api_binding_id,
        "placement_ref": placement.placement_ref,
        "capability_intent_id": call.capability_intent_id or "",
        "argument_binding_status": argument_binding.binding_status,
        "argument_binding_source_span_ids": list(argument_binding.source_span_ids),
        "api_functions_status": api.functions_status,
        "api_schema_status": api.schema_status,
    }
    if output_bindings and not outputs:
        metadata["pending_response_bindings"] = output_bindings
        metadata["api_response_binding_status"] = "deferred_until_api_return_contract_known"
    elif output_bindings:
        metadata["api_response_binding_status"] = "known_present"
    return StepIR(
        step_id=_step_id(call.demand_id),
        text=call.action_text or action.action_text or f"Call {api.api_name}.",
        source_span_ids=list(action.source_span_ids),
        command_type="CALL_API",
        inputs=inputs,
        outputs=outputs,
        integration_ref=api.api_name,
        flow_ref=placement.flow_ref,
        block_ref=placement.block_ref,
        kind="tool",
        metadata=metadata,
    )


def _api_response_contract_known(api: APISpec) -> bool:
    if api.functions_status != "known_present":
        return False
    return any(
        function.return_spec is not None or function.return_type for function in api.functions
    )


def _sanitize_general_command_fallbacks(
    worker_step_plan: WorkerStepPlanIR,
    call: APICallDemand,
    projection: APIResidualActionProjection,
) -> list[CompileDiagnostic]:
    diagnostics: list[CompileDiagnostic] = []
    consumed_spans = set(call.consumes_behavior_span_ids or call.source_span_ids)
    has_residual = len(projection.residual_actions) > 0

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
                if _is_fallback_step(step, call):
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

            if call.behavior_lowering_policy in (
                "api_call_augments_behavior",
                "keep_residual_behavior_only",
            ):
                if _is_fallback_step(step, call):
                    diagnostics.append(
                        _sanitized_warning(
                            call,
                            step,
                            "covered_operation_general_command_removed"
                            if not has_residual
                            else "general_command_trimmed_to_residual_behavior",
                        )
                    )
                    continue
                kept.append(step)
                continue

            kept.append(step)
        worker_step_plan.worker_steps[worker_id] = kept
    return diagnostics


def _is_fallback_step(step: StepIR, call: APICallDemand) -> bool:
    if _is_same_demand_general_command_fallback(step, call):
        return True
    return False


def _has_existing_non_fallback_general_step(
    steps: list[StepIR],
    action: ExecutableActionIR,
    call: APICallDemand,
) -> bool:
    action_span_ids = set(action.source_span_ids)
    if not action_span_ids:
        return False
    for step in steps:
        if step.command_type != "GENERAL_COMMAND":
            continue
        if _is_same_demand_general_command_fallback(step, call):
            continue
        if action_span_ids.intersection(step.source_span_ids):
            return True
    return False



def _coverage_by_span(
    call: APICallDemand,
) -> dict[str, list[tuple[str, int | None, int | None]]]:
    grouped: dict[str, list[tuple[str, int | None, int | None]]] = {}
    for coverage in call.operation_coverage:
        grouped.setdefault(coverage.source_span_id, []).append(
            (coverage.operation_surface, coverage.char_start, coverage.char_end)
        )
    return grouped


def _binding_values(bindings: dict[str, str]) -> list[str]:
    return [value for _key, value in sorted(bindings.items()) if value]


def _span_by_id(
    spans: list[SpanIR] | None,
    construct_plan: ConstructPlan,
) -> dict[str, SpanIR]:
    """Return resolved spans, with a compatibility fallback for legacy callers.

    Production Stage 7 passes resolved spans. Older vertical-slice tests call
    this materializer directly; for those callers we synthesize a minimal span
    from source-backed operation coverage rather than reading StepIR/rendered
    text.
    """

    if spans is not None:
        return {span.span_id: span for span in spans}

    result: dict[str, SpanIR] = {}
    for call in construct_plan.api_call_demands():
        for coverage in call.operation_coverage:
            if coverage.source_span_id and coverage.operation_surface:
                result.setdefault(
                    coverage.source_span_id,
                    SpanIR(coverage.source_span_id, coverage.operation_surface),
                )
        for span_id in call.source_span_ids:
            if span_id not in result and call.action_text:
                result[span_id] = SpanIR(span_id, call.action_text)
    return result


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


def _find_call_api_conflict(
    steps: list[StepIR],
    call: APICallDemand,
    candidate: StepIR,
) -> StepIR | None:
    candidate_spans = set(candidate.source_span_ids)
    for step in steps:
        if step.command_type != "CALL_API":
            continue
        if step.step_id == candidate.step_id:
            return None
        metadata = step.metadata or {}
        existing_demands = metadata.get("construct_demand_ids")
        if isinstance(existing_demands, (list, tuple)) and call.demand_id in existing_demands:
            return None
        has_same_span = bool(candidate_spans and candidate_spans.intersection(step.source_span_ids))
        has_same_api = (
            candidate.integration_ref is not None
            and step.integration_ref == candidate.integration_ref
        )
        if has_same_span and has_same_api:
            return step
    return None


def _duplicate_api_action_claim(
    call: APICallDemand,
    candidate: StepIR,
    existing: StepIR,
) -> CompileDiagnostic:
    conflict_key = "|".join(
        [
            ",".join(sorted(candidate.source_span_ids)),
            canonical_conflict_text(call.action_text or candidate.text),
            "CALL_API",
        ]
    )
    return CompileDiagnostic(
        diagnostic_id=_warning_id(call.demand_id, f"duplicate:{existing.step_id}"),
        kind="duplicate_api_action_claim",
        severity="warning",
        message=(
            "Direct API call demand and an existing API handoff claim the same "
            f"CALL_API action for {call.demand_id}."
        ),
        target_ref=f"api_call_demand:{call.demand_id}",
        source_span_ids=list(candidate.source_span_ids),
        metadata={
            "conflict_key": conflict_key,
            "direct_api_demand_id": call.demand_id,
            "existing_step_id": existing.step_id,
            "handoff_id": existing.handoff_id or "",
        },
        blocks_rendering=False,
        blocks_completion=True,
    )


def _guard_only_residual_diagnostic(
    action: ExecutableActionIR,
    call: APICallDemand,
) -> CompileDiagnostic | None:
    guard_words = (
        "when",
        "if",
        "unless",
        "once",
        "as long as",
        "provided that",
        "in case",
        "on condition that",
    )
    text = action.action_text.strip()
    lowered = text.lower()
    if not any(lowered == word or lowered.startswith(word + " ") for word in guard_words):
        return None
    if "," in text or " then " in lowered:
        return None
    return CompileDiagnostic(
        diagnostic_id=_warning_id(call.demand_id, f"guard_only_residual_{action.action_id}"),
        kind="stage7_guard_residual_not_materialized",
        severity="warning",
        message=(
            f"Guard-only residual action for API call '{call.demand_id}' "
            f"was not materialized: {text}"
        ),
        target_ref=f"api_call_demand:{call.demand_id}",
        source_span_ids=list(action.source_span_ids),
        metadata={
            "api_call_demand_id": call.demand_id,
            "action_id": action.action_id,
            "reason": "guard_only_residual",
        },
        blocks_rendering=False,
        blocks_completion=True,
    )


def canonical_conflict_text(value: str) -> str:
    return " ".join(value.lower().strip(" ,;.?!").split())


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


def _warning_id(call_demand_id: str, suffix: str) -> str:
    digest = hashlib.sha1(f"{call_demand_id}|{suffix}".encode()).hexdigest()[:10]
    return f"diag_stage7_api_{digest}"
