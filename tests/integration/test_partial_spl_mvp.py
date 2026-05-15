"""Integration tests for Partial SPL MVP - 6 core scenarios (Phase 10).

Each test builds IR fixtures, runs through the deterministic post-compilation
stages, and asserts on SPL text, diagnostics, completeness, report, and
provenance traces.
"""

from __future__ import annotations

from nl2spl.compiler.assumptions import AssumptionBuilder
from nl2spl.compiler.completeness import compute_completeness
from nl2spl.compiler.diagnostic_analyzer import AnalyzeInput, DiagnosticAnalyzer
from nl2spl.compiler.producer_index import ProducerIndex
from nl2spl.compiler.report_renderer import render_report
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.pipeline.provenance import ProvenanceAggregator
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler
from nl2spl.pipeline.stages.stage11_spl_renderer import SPLRenderer
from nl2spl.pipeline.stages.stage9_5_normalizer import IRNormalizer

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

    # Stage 9.5: normalize
    normalizer = IRNormalizer()
    norm_result = normalizer.normalize(
        flow, blocks, resources, symbols, list(steps), [], None,
    )
    n_flow, n_blocks, n_steps, _nc, n_symbols, n_errors, n_warnings = norm_result

    # Stage 10: assemble
    assembler = WorkerAssembler()
    worker = assembler.assemble(n_flow, n_blocks, n_steps, resources, n_symbols, None)

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

    # Post-compile analysis
    all_diags = list(normalizer.diagnostics) + gate_diags + provenance_diags
    analyzer = DiagnosticAnalyzer()
    analyzer_diags = analyzer.analyze(AnalyzeInput(
        worker=worker, resources=resources, symbol_table=n_symbols,
        producer_index=ProducerIndex(steps=n_steps),
        steps=n_steps,
    ))
    all_diags.extend(analyzer_diags)

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
            "REQUEST_INPUT", flow_ref="exc_1",
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
    analyzer = DiagnosticAnalyzer()
    analyzer_diags = analyzer.analyze(AnalyzeInput(
        worker=worker, resources=resources, symbol_table=symbols,
        producer_index=ProducerIndex(steps=prov_steps, handoffs=worker_plan.handoffs),
        steps=prov_steps,
    ))
    all_diags.extend(analyzer_diags)

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

    all_diags = gate_diags + provenance_diags
    analyzer = DiagnosticAnalyzer()
    analyzer_diags = analyzer.analyze(AnalyzeInput(
        worker=worker, steps=prov_steps,
    ))
    all_diags.extend(analyzer_diags)

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
