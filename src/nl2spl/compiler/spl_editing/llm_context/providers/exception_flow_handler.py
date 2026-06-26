"""ExceptionFlowHandlerContextProvider (Phase L4).

Extracts condition_text from structured artifact state (WorkerIR
exception flows), NEVER from raw diagnostic.message.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.llm_context.model import (
    ContextQuality,
    LLMRepairContextExtension,
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
        if artifact_snapshot is not None:
            span_index = _span_index(artifact_snapshot)
            # 1. Extract condition from structured exception flows (WorkerIR)
            final_worker = getattr(artifact_snapshot, "final_worker", None)
            flow_id = _flow_id_from_target(target, issue)
            if final_worker is not None and flow_id:
                condition_text, source_excerpt = _find_in_worker_exception_flows(
                    final_worker,
                    flow_id,
                    span_index,
                )

        # 5. Quality — condition_text is the critical fact
        has_primary_fact = bool(condition_text)
        quality = ContextQuality(
            confidence="medium" if has_primary_fact else "low",
            has_primary_business_fact=has_primary_fact,
            has_source_excerpt=bool(source_excerpt),
            missing_context_fields=(() if has_primary_fact else ("exception_condition_text",)),
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
                "allowed_handler_command_types": [
                    "GENERAL_COMMAND",
                    "REQUEST_INPUT",
                    "DISPLAY_MESSAGE",
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
    final_worker,
    flow_id: str,
    span_index: dict[str, str],
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
            for span_id in spans:
                span_text = span_index.get(str(span_id), "")
                if span_text:
                    excerpt = span_text
                    break
            break
    return cond, excerpt


def _span_index(artifact_snapshot) -> dict[str, str]:
    result: dict[str, str] = {}
    if artifact_snapshot is None:
        return result
    for span in getattr(artifact_snapshot, "spans", ()) or ():
        span_id = getattr(span, "span_id", "") or getattr(span, "id", "") or ""
        text = getattr(span, "text", "") or ""
        if span_id and text:
            result[str(span_id)] = str(text)
    return result
