"""ExceptionFlowHandlerContextProvider (Phase L4).

Extracts condition_text from structured artifact state (WorkerIR
exception flows), NEVER from raw diagnostic.message.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.llm_context.model import (
    ContextQuality,
    LLMRepairContextExtension,
    StepSummary,
)


class ExceptionFlowHandlerContextProvider:
    """Primary provider for missing_handler / AddExceptionHandlerStep."""

    provider_id = "exception_flow_handler"
    role = "primary"

    affordance_id = "exception_flow.add_handler_step"
    construct_type = "EXCEPTION_FLOW"
    slot_name = "handler_action"
    diagnostic_kinds = ("missing_handler",)
    supported_patch_types = ("AddExceptionHandlerStep",)

    facts_schema_id = "exception_flow.handler_action.add_exception_handler_step.v1"
    facts_schema_version = "1.0"
    facts_schema = {
        "type": "object",
        "required": [],
        "properties": {
            "exception_condition_text": {"type": "string"},
            "exception_source_excerpt": {"type": "string"},
            "parent_worker_purpose": {"type": "string"},
            "nearby_main_flow_steps": {"type": "array"},
            "available_variables_relevant_to_condition": {"type": "array"},
            "allowed_handler_command_types": {"type": "array"},
        },
    }

    renderer_id = "exception_flow_handler_section"
    # exception_condition_text is NOT listed as required — when missing
    # but target is reachable, the status is ready_low_confidence per §8.4.
    # Hard-block (generation_blocked) happens only when the target itself
    # cannot be resolved — handled by TargetResolver, not by this provider.
    required_fact_keys = ()
    optional_fact_keys = (
        "exception_condition_text",
        "exception_source_excerpt",
        "parent_worker_purpose",
        "nearby_main_flow_steps",
        "available_variables_relevant_to_condition",
        "allowed_handler_command_types",
    )

    def collect_facts(
        self,
        *,
        issue=None,
        target=None,
        repair_context=None,
        artifact_snapshot=None,
        presentation_view=None,
    ) -> LLMRepairContextExtension:
        condition_text = ""
        source_excerpt = ""
        parent_worker_purpose = ""
        available_vars: list[str] = []

        if artifact_snapshot is not None:
            # 1. Extract condition from structured exception flows (WorkerIR)
            final_worker = getattr(artifact_snapshot, "final_worker", None)
            flow_id = _flow_id_from_target(target, issue)
            if final_worker is not None and flow_id:
                condition_text, source_excerpt = _find_in_worker_exception_flows(
                    final_worker, flow_id,
                )

            # 2. Worker purpose from plan
            worker_plan = getattr(artifact_snapshot, "worker_plan", None)
            parent_wid = getattr(target, "worker_id", None) if target else None
            if worker_plan is not None and parent_wid:
                for w in getattr(worker_plan, "workers", []):
                    if getattr(w, "worker_id", None) == parent_wid:
                        parent_worker_purpose = getattr(w, "purpose", "") or ""
                        break

            # 3. Available variables from step plan
            step_plan = getattr(artifact_snapshot, "worker_step_plan", None)
            if step_plan is not None:
                wid = parent_wid or "worker_main"
                for s in getattr(step_plan, "worker_steps", {}).get(wid, []):
                    for o in getattr(s, "outputs", []):
                        if o and o not in available_vars:
                            available_vars.append(o)

        # 4. Build nearby step summaries
        nearby_steps = _build_nearby_steps(artifact_snapshot, target)

        # 5. Quality — condition_text is the critical fact
        has_primary_fact = bool(condition_text)
        quality = ContextQuality(
            confidence="medium" if has_primary_fact else "low",
            has_primary_business_fact=has_primary_fact,
            has_source_excerpt=bool(source_excerpt),
            missing_context_fields=(
                () if has_primary_fact else ("exception_condition_text",)
            ),
        )

        return LLMRepairContextExtension(
            extension_id="exception_flow_handler_primary",
            provider_id=self.provider_id,
            role="primary",
            affordance_id=self.affordance_id or "",
            construct_type=self.construct_type or "",
            slot_name=self.slot_name or "",
            diagnostic_kind="missing_handler",
            patch_type="AddExceptionHandlerStep",
            facts_schema_id=self.facts_schema_id,
            facts_schema_version=self.facts_schema_version,
            facts_schema=self.facts_schema,
            facts={
                "exception_condition_text": condition_text,
                "exception_source_excerpt": source_excerpt or None,
                "parent_worker_purpose": parent_worker_purpose or None,
                "nearby_main_flow_steps": [
                    {
                        "text": s.text,
                        "outputs": list(s.outputs),
                        "command_type": s.command_type,
                    }
                    for s in nearby_steps
                ],
                "available_variables_relevant_to_condition": available_vars[:10],
                "allowed_handler_command_types": [
                    "GENERAL_COMMAND", "REQUEST_INPUT", "DISPLAY_MESSAGE",
                ],
            },
            required_fact_keys=self.required_fact_keys,
            optional_fact_keys=self.optional_fact_keys,
            renderer_id=self.renderer_id,
            quality=quality,
        )


# ============================================================================
# Internal helpers
# ============================================================================


def _flow_id_from_target(target, issue) -> str | None:
    """Extract flow_id from the repair target (typed fields first).

    Prefers typed target identity fields; falls back to target_ref
    parsing only when typed fields are unavailable.
    """
    # Priority 1: typed flow_id on target
    if target is not None:
        typed_fid = getattr(target, "flow_id", None)
        if typed_fid:
            return str(typed_fid)

    # Priority 2: construct_path (last segment = flow_id)
    if target is not None:
        cpath = getattr(target, "construct_path", None) or ()
        if cpath and len(cpath) >= 4 and cpath[-2] == "exception_flows":
            return str(cpath[-1])

    # Priority 3: target_ref parsing (internal routing fallback)
    if target is not None:
        target_ref = getattr(target, "target_ref", "") or ""
        if ".exception_flow:" in target_ref:
            return target_ref.rsplit(".exception_flow:", 1)[-1] or None

    # Priority 4: issue target_ref (last resort)
    if issue is not None:
        target_ref = getattr(issue, "target_ref", "") or ""
        if ".exception_flow:" in target_ref:
            return target_ref.rsplit(".exception_flow:", 1)[-1] or None

    return None


def _find_in_worker_exception_flows(
    final_worker, flow_id: str,
) -> tuple[str, str]:
    """Find condition_text and source excerpt from WorkerIR.exception_flows."""
    cond = ""
    excerpt = ""
    exc_flows = getattr(final_worker, "exception_flows", [])
    for ef in exc_flows:
        fid = getattr(ef, "flow_id", "")
        if fid == flow_id:
            cond = getattr(ef, "condition_text", "") or ""
            spans = getattr(ef, "spans", []) or []
            if spans:
                excerpt = str(spans[0]) if hasattr(spans[0], "__str__") else ""
            break
    return cond, excerpt


def _build_nearby_steps(
    artifact_snapshot,
    target,
) -> list[StepSummary]:
    result: list[StepSummary] = []
    if artifact_snapshot is None:
        return result
    step_plan = getattr(artifact_snapshot, "worker_step_plan", None)
    if step_plan is None:
        return result
    parent_wid = getattr(target, "worker_id", None) or "worker_main" if target else "worker_main"
    steps = getattr(step_plan, "worker_steps", {}).get(parent_wid, [])
    for s in steps[:5]:
        flow_ref = getattr(s, "flow_ref", None) or ""
        if flow_ref == "main" or flow_ref == "":
            result.append(StepSummary(
                step_id_internal=getattr(s, "step_id", ""),
                text=getattr(s, "text", ""),
                command_type=getattr(s, "command_type", "GENERAL_COMMAND"),
                outputs=tuple(getattr(s, "outputs", [])),
                evidence_status=(
                    "source_backed" if getattr(s, "source_span_ids", None)
                    else "assumed"
                ),
            ))
    return result
