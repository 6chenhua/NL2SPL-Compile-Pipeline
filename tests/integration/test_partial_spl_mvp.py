"""Integration tests for Partial SPL MVP - 6 core scenarios (Phase 10).

Each test builds IR fixtures, runs through the deterministic post-compilation
stages, and asserts on SPL text, diagnostics, completeness, report, and
provenance traces.
"""

from __future__ import annotations

from nl2spl.compiler.assumptions import AssumptionBuilder
from nl2spl.compiler.completeness import compute_completeness
from nl2spl.compiler.irs.factory import build_irs_subsystem
from nl2spl.compiler.irs.policy import IRSRuntimeConfig
from nl2spl.compiler.report_renderer import render_report
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.pipeline.provenance import ProvenanceAggregator
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler
from nl2spl.pipeline.stages.stage11_spl_renderer import SPLRenderer

_MIN_PROFILE = AgentProfileIR(persona=PersonaIR(role="Assistant"))


# -- helpers -------------------------------------------------------------


def _run_post_compile(
    flow: FlowStructureIR | None = None,
    blocks: BlockStructureIR | None = None,
    steps: list[StepIR] | None = None,
    resources: ResourceRegistryIR | None = None,
    symbol_table: SymbolTable | None = None,
    spans: list | None = None,
) -> dict:
    """Run deterministic stages and return all output layers including traces."""
    flow = flow or FlowStructureIR()
    blocks = blocks or BlockStructureIR()
    steps = steps or []
    resources = resources or ResourceRegistryIR()
    symbols = symbol_table or SymbolTable()
    spans = spans or []

    # These fixtures exercise post-compile behavior from already assembled
    # flat IR fragments. Stage 9.5 no longer exposes a flat legacy normalizer.
    n_flow = flow
    n_blocks = blocks
    n_steps = list(steps)
    n_symbols = symbols
    n_errors: list[str] = []
    n_warnings: list[str] = []

    # Stage 10: assemble
    assembler = WorkerAssembler()
    worker = assembler.assemble(n_flow, n_blocks, n_steps, resources, n_symbols, None)

    # Post-normalize IRS check
    post_norm_diags = build_irs_subsystem(IRSRuntimeConfig()).run_post_normalize(
        worker=worker, resources=resources, symbol_table=n_symbols,
    )

    # Gate
    gate = ExecutableElementGate()
    worker, render_info, gate_diags = gate.apply(worker)

    # Build post-gate flat steps for provenance
    prov_steps = list(worker.steps)
    for child in worker.child_workers:
        prov_steps.extend(child.steps)

    # Stage 11: render
    renderer = SPLRenderer()
    spl_text, spl_errors, spl_warnings = renderer.render(
        worker, _MIN_PROFILE, resources, n_symbols, n_steps, [],
    )

    # Provenance aggregation
    aggregator = ProvenanceAggregator()
    traces, provenance_diags = aggregator.aggregate(
        worker=worker, steps=prov_steps, constraints=[],
        resources=resources, symbol_table=n_symbols, spans=spans,
    )

    all_diags = list(post_norm_diags) + gate_diags + provenance_diags

    completeness = compute_completeness(
        validation_errors=n_errors + spl_errors,
        diagnostics=all_diags,
    )
    assumptions = AssumptionBuilder().build(all_diags)
    report = render_report(
        spl_text=spl_text, completeness=completeness,
        diagnostics=all_diags, assumptions=assumptions,
        traces=traces,
        validation_errors=n_errors + spl_errors,
        validation_warnings=n_warnings + spl_warnings,
    )

    return dict(
        spl=spl_text, completeness=completeness,
        diagnostics=all_diags, assumptions=assumptions,
        traces=traces, report=report, worker=worker,
    )


# -- Scenario 1: failure condition only ----------------------------------


def test_failure_condition_only() -> None:
    """Source describes a failure but no handler -> partial SPL.
    No invented handler.  missing_handler diagnostic emitted."""

    flow = FlowStructureIR(
        exception_flows=[
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Missing timeframe.",
                spans=["s_time"],
            )
        ]
    )
    steps = [
        StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
    ]

    out = _run_post_compile(flow=flow, steps=steps)

    assert "[EXCEPTION_FLOW:" in out["spl"]
    assert "Missing timeframe" in out["spl"]
    assert "REQUEST_INPUT" not in out["spl"]
    mh = [d for d in out["diagnostics"] if d.kind == "missing_handler"]
    assert len(mh) >= 1
    assert out["completeness"] == "partial"
    assert "missing_handler" in out["report"]
    assert "Status: partial" in out["report"]
    # Provenance closed loop
    assert len(out["traces"]) > 0, "Must produce trace records"
    assert "Provenance Traces" in out["report"]


# -- Scenario 2: required output without producer ------------------------


def test_required_output_without_producer() -> None:
    """Required output declared but no source-backed producer.
    No synthetic producer command.  missing_output_producer diagnostic."""

    resources = ResourceRegistryIR(
        variables=[
            VariableSpec("draft", "text", False, "Input", "input"),
            VariableSpec("final_report", "text", True, "Final report", "output"),
        ]
    )
    symbols = SymbolTable()
    symbols.declare("draft", "text", "input", "Input draft")
    symbols.declare("final_report", "text", "output", "Final report")
    steps = [
        StepIR("st1", "Read input", ["s1"], "GENERAL_COMMAND", inputs=["draft"]),
    ]

    out = _run_post_compile(steps=steps, resources=resources, symbol_table=symbols)

    assert "Produce required output" not in out["spl"]
    mp = [d for d in out["diagnostics"] if d.kind == "missing_output_producer"]
    assert len(mp) >= 1
    assert "final_report" in mp[0].message
    assert out["completeness"] == "partial"
    assert "missing_output_producer" in out["report"]
    assert len(out["traces"]) > 0
    assert "Provenance Traces" in out["report"]


# -- Scenario 3: complete failure handling -------------------------------


def test_complete_failure_handling() -> None:
    """Failure condition + source-backed handler -> complete SPL."""

    flow = FlowStructureIR(
        exception_flows=[
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Missing timeframe.",
                spans=["s_time"],
            )
        ]
    )
    steps = [
        StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
        StepIR(
            "st_handler", "Ask user for timeframe", ["s_time"],
            "REQUEST_INPUT", flow_ref="exc_1", outputs=["timeframe"],
        ),
    ]

    out = _run_post_compile(flow=flow, steps=steps)

    assert "Ask user" in out["spl"] or "timeframe" in out["spl"]
    mh = [d for d in out["diagnostics"] if d.kind == "missing_handler"]
    assert len(mh) == 0
    assert out["completeness"] == "complete"
    assert "Status: complete" in out["report"]
    assert len(out["traces"]) > 0
    assert "Provenance Traces" in out["report"]


# -- Scenario 4: vague policy --------------------------------------------


def test_vague_policy() -> None:
    """Vague policy -> no concrete exception flow, clean run."""

    steps = [
        StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
    ]

    out = _run_post_compile(steps=steps)

    assert "EXCEPTION_FLOW" not in out["spl"]
    mh = [d for d in out["diagnostics"] if d.kind == "missing_handler"]
    assert len(mh) == 0
    assert out["completeness"] == "complete"
    assert len(out["traces"]) > 0
    assert "Provenance Traces" in out["report"]


# -- Scenario 5: complete single-level delegation ------------------------


def test_complete_delegation() -> None:
    """Source-backed child worker + valid invoke handoff.
    INVOKE_WORKER rendered, completeness=complete, no assumptions."""

    from nl2spl.ir.block_structure_ir import BlockIR
    from nl2spl.ir.worker_ir import ChildWorkerIR, FlowRef, WorkerInput, WorkerOutput
    from nl2spl.ir.worker_plan_ir import (
        InputBindingIR,
        OutputBindingIR,
        WorkerHandoffIR,
        WorkerPlanIR,
        WorkerSpecIR,
    )

    # Build post-assembly WorkerIR directly: main worker has source-backed
    # steps + INVOKE_WORKER with valid handoff.  Child worker is declared.
    worker = WorkerIR(
        worker_name="MainWorker",
        description="Main processing",
        main_flow=FlowRef(blocks=[
            BlockIR("b1", "SEQUENTIAL", spans=["s1", "s_invoke"]),
        ]),
        steps=[
            StepIR("st1", "Prepare request", ["s1"], "GENERAL_COMMAND",
                   outputs=["req"]),
            StepIR(
                "st_invoke", "Invoke child worker", ["s_invoke"],
                "INVOKE_WORKER", handoff_id="h1",
                integration_ref="ChildWorker",
                inputs=["req"], outputs=["result"],
            ),
        ],
        inputs=[WorkerInput("req", True)],
        outputs=[WorkerOutput("result", True)],
        child_workers=[
            ChildWorkerIR(
                worker_name="ChildWorker",
                description="Subtask processing",
                task_text="Process subtask",
                inputs=[WorkerInput("child_req", True)],
                outputs=[WorkerOutput("child_out", True)],
            ),
        ],
    )

    # Worker plan with valid invoke handoff
    worker_plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[
            WorkerSpecIR(
                worker_id="w_main", worker_name="MainWorker",
                kind="main", purpose="Main",
                owned_span_ids=["s1"],
            ),
            WorkerSpecIR(
                worker_id="w_child", worker_name="ChildWorker",
                kind="child", purpose="Subtask",
                owned_span_ids=["s_child"],
                boundary_kind="explicit_delegation",
            ),
        ],
        handoffs=[
            WorkerHandoffIR(
                handoff_id="h1", from_worker="w_main", to_worker="w_child",
                api_ref=None, mode="invoke", condition_text=None,
                ordering="after",
                input_bindings=[InputBindingIR("req", "child_req", True)],
                output_bindings=[OutputBindingIR("child_out", "result", True, "set")],
            ),
        ],
    )

    resources = ResourceRegistryIR()
    symbols = SymbolTable()
    symbols.declare("req", "text", "input", "Request")
    symbols.declare("result", "text", "output", "Result")
    symbols.declare("child_req", "text", "input", "Child input")
    symbols.declare("child_out", "text", "output", "Child output")

    # Gate validates handoff and passes INVOKE_WORKER through
    gate = ExecutableElementGate()
    worker, render_info, gate_diags = gate.apply(worker, worker_plan)

    prov_steps = list(worker.steps)
    for child in worker.child_workers:
        prov_steps.extend(child.steps)

    renderer = SPLRenderer()
    spl_text, spl_errors, spl_warnings = renderer.render(
        worker, _MIN_PROFILE, resources, symbols, prov_steps, [],
    )

    aggregator = ProvenanceAggregator()
    traces, provenance_diags = aggregator.aggregate(
        worker=worker, steps=prov_steps, constraints=[],
        resources=resources, symbol_table=symbols, spans=[],
        handoffs=worker_plan.handoffs,
    )

    all_diags = gate_diags + provenance_diags

    validation_errors = spl_errors
    assert validation_errors == [], (
        f"Delegation happy path must have zero validation errors: {validation_errors}"
    )
    completeness = compute_completeness(
        validation_errors=validation_errors,
        diagnostics=all_diags,
    )
    assumptions = AssumptionBuilder().build(all_diags)
    report = render_report(
        spl_text=spl_text, completeness=completeness,
        diagnostics=all_diags, assumptions=assumptions,
        traces=traces,
        validation_errors=validation_errors,
        validation_warnings=spl_warnings,
    )

    # Happy path assertions
    assert "[INVOKE" in spl_text and "ChildWorker" in spl_text, (
        f"SPL must contain [INVOKE ...]: {spl_text[:600]}"
    )
    assert "ChildWorker" in spl_text
    assert completeness == "complete", (
        f"Expected complete, got {completeness}. "
        f"Diags: {[(d.kind, d.message) for d in all_diags if d.blocks_completion]}"
    )
    assert "Status: complete" in report
    assert assumptions == [], (
        f"Unexpected assumptions: {[a.text for a in assumptions]}"
    )
    assert len(traces) > 0
    assert "Provenance Traces" in report


# -- Scenario 6: incomplete delegation -----------------------------------


def test_incomplete_delegation() -> None:
    """Delegation without valid handoff -> no executable INVOKE_WORKER.
    assumed_command_not_renderable diagnostic, partial status."""

    from nl2spl.ir.block_structure_ir import BlockIR
    from nl2spl.ir.worker_ir import ChildWorkerIR, FlowRef

    # Post-assembly WorkerIR: INVOKE_WORKER step exists but has no
    # handoff_id and no valid handoff contract in the plan.
    worker = WorkerIR(
        worker_name="MainWorker",
        description="Main processing",
        main_flow=FlowRef(blocks=[
            BlockIR("b1", "SEQUENTIAL", spans=["s1", "s_delegate"]),
        ]),
        steps=[
            StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
            StepIR(
                "st_delegate", "Delegate work", ["s_delegate"],
                "INVOKE_WORKER", integration_ref="ChildWorker",
            ),
        ],
        child_workers=[
            ChildWorkerIR(
                worker_name="ChildWorker",
                description="Subtask processing",
                task_text="Process subtask",
            ),
        ],
    )

    # Worker plan with no handoffs -> incomplete delegation
    from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR
    worker_plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[
            WorkerSpecIR(
                worker_id="w_main", worker_name="MainWorker",
                kind="main", purpose="Main",
                owned_span_ids=["s1"],
            ),
            WorkerSpecIR(
                worker_id="w_child", worker_name="ChildWorker",
                kind="child", purpose="Subtask",
                owned_span_ids=[],
                boundary_kind="explicit_delegation",
            ),
        ],
        handoffs=[],
    )

    # Post-normalize IRS check runs before gate.
    post_norm_diags = build_irs_subsystem(IRSRuntimeConfig()).run_post_normalize(
        worker=worker, worker_plan=worker_plan,
    )

    # Gate blocks the INVOKE_WORKER: no handoff_id, classified as
    # source_backed but INVOKE_WORKER without handoff is blocked.
    gate = ExecutableElementGate()
    worker, render_info, gate_diags = gate.apply(worker, worker_plan)

    prov_steps = list(worker.steps)
    for child in worker.child_workers:
        prov_steps.extend(child.steps)

    renderer = SPLRenderer()
    spl_text, spl_errors, spl_warnings = renderer.render(
        worker, _MIN_PROFILE, ResourceRegistryIR(), SymbolTable(), prov_steps, [],
    )

    aggregator = ProvenanceAggregator()
    traces, provenance_diags = aggregator.aggregate(
        worker=worker, steps=prov_steps, constraints=[],
        resources=ResourceRegistryIR(), symbol_table=SymbolTable(), spans=[],
    )

    all_diags = post_norm_diags + gate_diags + provenance_diags

    completeness = compute_completeness(
        validation_errors=spl_errors,
        diagnostics=all_diags,
    )
    assumptions = AssumptionBuilder().build(all_diags)
    report = render_report(
        spl_text=spl_text, completeness=completeness,
        diagnostics=all_diags, assumptions=assumptions,
        traces=traces,
    )

    # No executable INVOKE_WORKER
    assert "[INVOKE" not in spl_text, "SPL must NOT contain [INVOKE"
    # Specific diagnostic kinds expected
    diag_kinds = {d.kind for d in all_diags}
    assert {"assumed_command_not_renderable", "type_or_contract_ambiguity"} & diag_kinds, (
        f"Expected assumed_command_not_renderable or type_or_contract_ambiguity, "
        f"got {diag_kinds}"
    )
    assert completeness == "partial", (
        f"Expected partial, got {completeness}. "
        f"Diags: {[(d.kind,) for d in all_diags]}"
    )
    assert "Status: partial" in report
    assert "assumed_command_not_renderable" in report or "type_or_contract_ambiguity" in report
    assert len(traces) > 0
    assert "Provenance Traces" in report


# =====================================================================
# MVP+ Phase 2: Structural NL integration fixtures
# =====================================================================


def _adapt_and_slice(text: str) -> list:
    """Run the real adapter + Stage 1 to produce SpanIRs with section/packet."""
    from nl2spl.adapters import InputAdapterRegistry
    from nl2spl.config import PipelineConfig
    from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer

    registry = InputAdapterRegistry()
    canonical = registry.adapt(text)
    cfg = PipelineConfig(save_intermediate=False)
    slicer = SpanSlicer(cfg, _MagicLLM())
    return slicer.execute(canonical)


class _MagicLLM:
    """Fake LLM client -- SpanSlicer won't call it for structured input."""
    call_json = None  # type: ignore[assignment]
    call_text = None  # type: ignore[assignment]


# -- MVP+ Fixture 1: required output section ---------------------------------


def test_structural_required_output_section_provenance() -> None:
    """Required output section -> variable trace shows section provenance."""

    text = (
        "Task family: Internal reporting\n"
        "\n"
        "Inputs for each run:\n"
        "- user request: The user's question.\n"
        "\n"
        "Required outputs:\n"
        "- final_report: A compiled report of gathered sources.\n"
    )

    spans = _adapt_and_slice(text)
    out_spans = [s for s in spans if s.source_section_id == "sec_required_outputs"]
    assert out_spans, "Must have spans from required_outputs section"

    resources = ResourceRegistryIR(
        variables=[VariableSpec("final_report", "text", True, "Report", "output")]
    )
    symbols = SymbolTable()
    symbols.declare("final_report", "text", "output", "Final report")
    out_span_id = out_spans[0].span_id
    steps = [
        StepIR("st1", "Produce report", [out_span_id], "GENERAL_COMMAND",
               outputs=["final_report"]),
    ]

    out = _run_post_compile(
        steps=steps, resources=resources, symbol_table=symbols,
        spans=spans,
    )

    vt = next(
        t for t in out["traces"]
        if t.target_ref == "variable:final_report"
    )
    assert vt.source_section_id == "sec_required_outputs", (
        f"Expected sec_required_outputs on variable:final_report, "
        f"got {vt.source_section_id}"
    )
    assert "section=sec_required_outputs" in out["report"]


# -- MVP+ Fixture 2: failure handling section ---------------------------------


def test_structural_failure_section_provenance() -> None:
    """Failure handling section -> flow trace shows section provenance."""

    text = (
        "Task family: Internal reporting\n"
        "\n"
        "Inputs for each run:\n"
        "- user request: The user's question.\n"
        "\n"
        "Required outputs:\n"
        "- final_report: A compiled report.\n"
        "\n"
        "Failure handling:\n"
        "- Missing timeframe: The user did not provide a timeframe.\n"
    )

    spans = _adapt_and_slice(text)
    fail_spans = [s for s in spans if s.source_section_id == "sec_failure_handling"]
    assert fail_spans, "Must have spans from failure_handling section"

    fail_span_id = fail_spans[0].span_id
    flow = FlowStructureIR(
        exception_flows=[
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Missing timeframe.",
                spans=[fail_span_id],
            )
        ]
    )
    # Place the span in a block so _trace_flows can collect it
    blocks = BlockStructureIR()
    blocks.exception_flow_blocks["exc_1"] = [
        BlockIR("b_exc", "SEQUENTIAL", spans=[fail_span_id]),
    ]

    out = _run_post_compile(flow=flow, blocks=blocks, steps=[], spans=spans)

    ft = next(
        t for t in out["traces"]
        if t.target_ref == "flow:exc_1"
    )
    assert ft.source_section_id == "sec_failure_handling", (
        f"Expected sec_failure_handling on flow:exc_1, "
        f"got {ft.source_section_id}"
    )
    assert "section=sec_failure_handling" in out["report"]


# -- MVP+ Fixture 3: delegation policy section --------------------------------


def test_structural_delegation_section_provenance() -> None:
    """Delegation policy section -> handoff trace shows section provenance.
    Uses real adapter + SpanSlicer for spans; post-assembly WorkerIR
    construction for gate/renderer/provenance/report."""

    text = (
        "Task family: Internal reporting\n"
        "\n"
        "Inputs for each run:\n"
        "- user request: The user's question.\n"
        "\n"
        "Required outputs:\n"
        "- final_report: A compiled report.\n"
        "\n"
        "Delegation policy:\n"
        "- Source gathering: Delegate to a specialized source gathering agent.\n"
    )

    spans = _adapt_and_slice(text)
    del_spans = [s for s in spans if s.source_section_id == "sec_delegation_policy"]
    assert del_spans, "Must have spans from delegation_policy section"

    del_span_id = del_spans[0].span_id

    from nl2spl.ir.worker_ir import ChildWorkerIR, FlowRef, WorkerInput, WorkerOutput
    from nl2spl.ir.worker_plan_ir import (
        InputBindingIR,
        InvokeLocationHintIR,
        OutputBindingIR,
        WorkerHandoffIR,
        WorkerPlanIR,
        WorkerSpecIR,
    )

    worker = WorkerIR(
        worker_name="MainWorker",
        description="Main",
        main_flow=FlowRef(blocks=[
            BlockIR("b1", "SEQUENTIAL", spans=[del_span_id]),
        ]),
        steps=[
            StepIR("st1", "Delegate source gathering", [del_span_id],
                   "GENERAL_COMMAND"),
        ],
        inputs=[WorkerInput("user_request", True)],
        outputs=[WorkerOutput("final_report", True)],
        child_workers=[
            ChildWorkerIR(
                worker_name="SourceGatherer",
                description="Gather sources",
                task_text="Gather approved sources.",
            ),
        ],
    )

    worker_plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[
            WorkerSpecIR(
                worker_id="w_main", worker_name="MainWorker",
                kind="main", purpose="Main",
                owned_span_ids=[del_span_id],
            ),
            WorkerSpecIR(
                worker_id="w_child", worker_name="SourceGatherer",
                kind="child", purpose="Gather",
                owned_span_ids=[],
                boundary_kind="explicit_delegation",
            ),
        ],
        handoffs=[
            WorkerHandoffIR(
                handoff_id="h1", from_worker="w_main",
                to_worker="w_child", api_ref=None, mode="invoke",
                condition_text=None, ordering="after",
                input_bindings=[InputBindingIR("user_request", "child_req", True)],
                output_bindings=[OutputBindingIR("sources", "result", True, "set")],
                invoke_location_hint=InvokeLocationHintIR(
                    flow_kind="main", flow_id=None,
                    after_span_id=del_span_id, before_span_id=None,
                    block_hint="unknown",
                ),
            ),
        ],
    )

    gate = ExecutableElementGate()
    worker, render_info, gate_diags = gate.apply(worker, worker_plan)

    prov_steps = list(worker.steps)
    for child in worker.child_workers:
        prov_steps.extend(child.steps)

    renderer = SPLRenderer()
    spl_text, spl_errors, spl_warnings = renderer.render(
        worker, _MIN_PROFILE, ResourceRegistryIR(), SymbolTable(), prov_steps, [],
    )

    aggregator = ProvenanceAggregator()
    traces, provenance_diags = aggregator.aggregate(
        worker=worker, steps=prov_steps, constraints=[],
        resources=ResourceRegistryIR(), symbol_table=SymbolTable(),
        spans=spans,
        handoffs=worker_plan.handoffs,
        worker_owned_spans={
            "MainWorker": [del_span_id],
        },
    )

    all_diags = gate_diags + provenance_diags
    completeness = compute_completeness(
        validation_errors=spl_errors, diagnostics=all_diags,
    )
    assumptions = AssumptionBuilder().build(all_diags)
    report = render_report(
        spl_text=spl_text, completeness=completeness,
        diagnostics=all_diags, assumptions=assumptions,
        traces=traces,
    )

    ht = next(
        t for t in traces
        if t.target_ref == "handoff:h1"
    )
    assert ht.source_section_id == "sec_delegation_policy", (
        f"Expected sec_delegation_policy on handoff:h1, "
        f"got {ht.source_section_id}"
    )
    assert "section=sec_delegation_policy" in report
    assert len(traces) > 0
