"""Stage 6 resource context builder (V2).

Produces a semi-structured resource extraction view instead of raw IR JSON
dumps.  Reduces schema noise (flow_id, block_id, source_span_ids, etc.)
and mis-extracted variables while preserving the information that resource
extraction actually needs.
"""

from __future__ import annotations

from typing import Literal

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_contract_ir import ResourceContractPlanIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerSpecIR

EXTRACTION_POLICY = """\
- Do not redeclare authoritative contract variables with a different type.
- Do not extract span_id, block_id, flow_id, worker_id, source_section_id,
  or source_packet_id as domain variables.
- Do not extract compiler schema fields.
- Write descriptions in concise English ASCII. Translate non-English source
  wording instead of copying it.
- Return JSON only with variables, files, apis, and types."""


def build_resource_context(
    spans: list[SpanIR],
    routes: FieldRouteIR,
    flow: FlowStructureIR | None = None,
    blocks: BlockStructureIR | None = None,
    symbol_table: SymbolTable | None = None,
    canonical_input: CanonicalCompileInput | None = None,
    worker_spec: WorkerSpecIR | None = None,
    scope_kind: Literal["global", "worker", "handoff"] = "global",
    scope_id: str | None = None,
    resource_contract_plan: ResourceContractPlanIR | None = None,
) -> str:
    """Build a semi-structured resource extraction prompt context.

    All sections use bullet format, never raw JSON IR.

    Args:
        spans: All SpanIR objects for this scope.
        routes: FieldRouteIR classifying spans.
        flow: FlowStructureIR for this scope (may be None).
        blocks: BlockStructureIR for this scope (may be None).
        symbol_table: SymbolTable with known variables (may be None).
        canonical_input: Adapter output for hard facts (legacy path).
        worker_spec: WorkerSpecIR for contract IO (worker-scoped path).
        scope_kind: "global", "worker", or "handoff".
        scope_id: Worker ID when scope_kind is "worker".
    """
    sections: list[str] = [
        "Extract resource declarations for this scope.",
        "",
        _build_scope_section(worker_spec, scope_kind, scope_id),
        _build_contract_section(worker_spec, canonical_input),
        _build_resource_contract_plan_section(resource_contract_plan),
        _build_source_spans_section(spans, routes),
        _build_flow_summary_section(flow),
        _build_block_summary_section(blocks),
        _build_known_variables_section(symbol_table, scope_id),
        _build_extraction_policy_section(),
    ]
    return "\n".join(sections)


def _build_scope_section(
    worker_spec: WorkerSpecIR | None,
    scope_kind: str,
    scope_id: str | None,
) -> str:
    lines = ["Resource extraction scope"]
    if worker_spec is not None:
        lines.append(f"- kind: {scope_kind}")
        lines.append(f"- worker_id: {worker_spec.worker_id}")
        lines.append(f"- worker_name: {worker_spec.worker_name}")
        lines.append(f"- purpose: {worker_spec.purpose}")
    else:
        lines.append(f"- kind: {scope_kind}")
        if scope_id:
            lines.append(f"- scope_id: {scope_id}")
        lines.append("- scope: global/main")
    return "\n".join(lines)


def _build_contract_section(
    worker_spec: WorkerSpecIR | None,
    canonical_input: CanonicalCompileInput | None,
) -> str:
    lines = ["Authoritative contract"]
    has_inputs = False
    has_outputs = False

    if worker_spec is not None:
        if worker_spec.input_contract:
            lines.append("- Inputs:")
            for f in worker_spec.input_contract:
                lines.append(f"  - {f.name}: {f.data_type}, "
                             f"{'required' if f.required else 'optional'}"
                             f"{f' - {f.description}' if f.description else ''}")
            has_inputs = True
        if worker_spec.output_contract:
            lines.append("- Outputs:")
            for f in worker_spec.output_contract:
                lines.append(f"  - {f.name}: {f.data_type}, "
                             f"{'required' if f.required else 'optional'}"
                             f"{f' - {f.description}' if f.description else ''}")
            has_outputs = True

    if canonical_input is not None and not has_inputs and not has_outputs:
        hf_inputs = canonical_input.hard_facts.inputs
        hf_outputs = canonical_input.hard_facts.outputs
        if hf_inputs:
            lines.append("- Inputs:")
            for vf in hf_inputs:
                lines.append(f"  - {vf.name}: {vf.data_type}, "
                             f"{'required' if vf.required else 'optional'}"
                             f"{f' - {vf.description}' if vf.description else ''}")
            has_inputs = True
        if hf_outputs:
            lines.append("- Outputs:")
            for vf in hf_outputs:
                lines.append(f"  - {vf.name}: {vf.data_type}, "
                             f"{'required' if vf.required else 'optional'}"
                             f"{f' - {vf.description}' if vf.description else ''}")
            has_outputs = True

    if not has_inputs and not has_outputs:
        lines.append("- none")

    return "\n".join(lines)


def _build_resource_contract_plan_section(
    resource_contract_plan: ResourceContractPlanIR | None,
) -> str:
    if resource_contract_plan is None or not resource_contract_plan.demands:
        return "Resource contract demands\n- none"

    lines = [
        "Resource contract demands",
        "You MUST examine each demand and output a resource_contracts array.",
        "For output demands that describe document/file artifacts",
        "(Word, Google Doc, PDF, file upload, document), use resource_kind=file",
        "with path='< >'. For ordinary text/data outputs, use resource_kind=variable.",
        "Include the demand_id in each resource_contracts entry for traceability.",
        "",
    ]
    for demand in resource_contract_plan.demands:
        provenance_parts = []
        if demand.source_span_ids:
            provenance_parts.append(f"span={','.join(demand.source_span_ids)}")
        if demand.source_section_id:
            provenance_parts.append(f"section={demand.source_section_id}")
        if demand.source_packet_id:
            provenance_parts.append(f"packet={demand.source_packet_id}")
        provenance = ", ".join(provenance_parts) if provenance_parts else "no provenance"
        lines.append(
            f"- demand_id: {demand.demand_id}"
        )
        lines.append(f"  direction: {demand.direction}")
        lines.append(f"  required: {demand.required}")
        lines.append(f"  evidence: \"{demand.evidence_text[:200]}\"")
        lines.append(f"  provenance: {provenance}")
    return "\n".join(lines)


def _build_source_spans_section(
    spans: list[SpanIR],
    routes: FieldRouteIR,
) -> str:
    lines = ["Source spans"]
    behavior = [s for s in spans if s.span_id in routes.behavior]
    integrations = [s for s in spans if s.span_id in routes.integrations]

    if behavior:
        lines.append("- Behavior:")
        for s in behavior:
            lines.append(f"  - {s.span_id}: {s.text}")
    else:
        lines.append("- Behavior: none")

    if integrations:
        lines.append("- Integrations:")
        for s in integrations:
            lines.append(f"  - {s.span_id}: {s.text}")
    else:
        lines.append("- Integrations: none")

    return "\n".join(lines)


def _build_flow_summary_section(flow: FlowStructureIR | None) -> str:
    lines = ["Flow summary"]
    if flow is None:
        lines.append("- No flow structure available.")
        return "\n".join(lines)

    if flow.main_flow_spans:
        lines.append(f"- Main flow spans: {', '.join(flow.main_flow_spans)}")
    else:
        lines.append("- Main flow spans: none")

    alt_conditions = [af.condition_text for af in flow.alternative_flows if af.condition_text]
    if alt_conditions:
        lines.append(f"- Alternative conditions: {'; '.join(alt_conditions)}")
    else:
        lines.append("- Alternative conditions: none")

    exc_conditions = [ef.condition_text for ef in flow.exception_flows if ef.condition_text]
    if exc_conditions:
        lines.append(f"- Exception conditions: {'; '.join(exc_conditions)}")
    else:
        lines.append("- Exception conditions: none")

    return "\n".join(lines)


def _build_block_summary_section(blocks: BlockStructureIR | None) -> str:
    lines = ["Block summary"]
    if blocks is None:
        lines.append("- No block structure available.")
        return "\n".join(lines)

    main_blocks = blocks.main_flow_blocks
    alt_blocks = blocks.alternative_flow_blocks
    exc_blocks = blocks.exception_flow_blocks

    if not main_blocks and not alt_blocks and not exc_blocks:
        lines.append("- No blocks defined.")
        return "\n".join(lines)

    if main_blocks:
        lines.append("- Main blocks:")
        lines.extend(_format_block_items(main_blocks, indent="  "))

    if alt_blocks:
        for flow_id, flow_blocks in alt_blocks.items():
            lines.append(f"- Alternative flow {flow_id}:")
            lines.extend(_format_block_items(flow_blocks, indent="  "))

    if exc_blocks:
        for flow_id, flow_blocks in exc_blocks.items():
            lines.append(f"- Exception flow {flow_id}:")
            lines.extend(_format_block_items(flow_blocks, indent="  "))

    return "\n".join(lines)


def _format_block_items(block_list: list[BlockIR], indent: str = "") -> list[str]:
    lines: list[str] = []
    for b in block_list:
        span_list = ", ".join(b.spans) if b.spans else "none"
        if b.condition_text:
            lines.append(f"{indent}- {b.block_type} ({b.condition_text}): spans={span_list}")
        else:
            lines.append(f"{indent}- {b.block_type}: spans={span_list}")
    return lines


def _build_known_variables_section(
    symbol_table: SymbolTable | None,
    scope_id: str | None,
) -> str:
    lines = ["Known variables"]
    if symbol_table is None:
        lines.append("- No known variables.")
        return "\n".join(lines)

    # Get scoped variables for this worker, plus any globals
    vars_text = symbol_table.get_variable_list_for_worker_prompt(
        scope_id or "main"
    )
    if vars_text == "No variables available.":
        lines.append("- none")
    else:
        for vline in vars_text.strip().split("\n"):
            if vline.strip():
                lines.append(f"  {vline.strip()}")
    return "\n".join(lines)


def _build_extraction_policy_section() -> str:
    return f"Extraction policy\n{EXTRACTION_POLICY}"
