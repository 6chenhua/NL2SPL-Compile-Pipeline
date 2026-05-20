"""Pipeline orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nl2spl.adapters import InputAdapterRegistry
from nl2spl.canonical import CanonicalCompileInput, CanonicalCompileInputValidator
from nl2spl.compiler.analyzers.semantic_conflict import (
    ConflictAnalysisContext,
    LLMConflictDiagnosticVerifier,
    LLMSemanticConflictAnalyzer,
    NoOpSemanticConflictAnalyzer,
)
from nl2spl.compiler.assumptions import AssumptionBuilder
from nl2spl.compiler.compile_result import CompileAssumption, Completeness
from nl2spl.compiler.completeness import compute_completeness
from nl2spl.compiler.report_renderer import render_report
from nl2spl.config import PipelineConfig
from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, WorkerScopedResourceIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerStepPlanIR,
)
from nl2spl.llm.client import LLMClient
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.pipeline.fact_bridges import (
    bridge_delegation_intents,
    bridge_failure_modes,
    bridge_failure_modes_worker_scoped,
)
from nl2spl.pipeline.provenance import ProvenanceAggregator
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner import WorkerBoundaryPlanner
from nl2spl.pipeline.stages.stage3_ambiguity_resolver import AmbiguityResolver
from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler
from nl2spl.pipeline.stages.stage4_flow_assembler.irs_checker import (
    check_exception_flows_irs,
    check_worker_flow_plan_exception_flows_irs,
)
from nl2spl.pipeline.stages.stage5_block_assembler import BlockAssembler
from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor
from nl2spl.pipeline.stages.stage7_step_extractor.irs_checker import (
    check_steps_irs,
    check_worker_step_plan_irs,
)
from nl2spl.pipeline.stages.stage8_profile_extractor import ProfileExtractor
from nl2spl.pipeline.stages.stage9_5_normalizer import IRNormalizer
from nl2spl.pipeline.stages.stage9_5_normalizer.final_irs_checker import (
    PostNormalizeIRSChecker,
)
from nl2spl.pipeline.stages.stage9_constraint_extractor import ConstraintExtractor
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler
from nl2spl.pipeline.stages.stage11_spl_renderer import SPLRenderer
from nl2spl.pipeline.worker_plan_validator import WorkerPlanValidator
from nl2spl.utils.logger import setup_logger
from nl2spl.utils.persistence import save_final_spl


@dataclass
class PipelineResult:
    """Pipeline execution result.

    Attributes:
        spl_text: Generated SPL text
        validation_errors: Validation errors
        validation_warnings: Validation warnings
        compile_diagnostics: Structured compiler diagnostics
        diagnostics: Alias for compile_diagnostics (preferred for new callers)
        traces: Provenance TraceRecords linking SPL elements to source
        adapter_warnings: Adapter-level warnings
        completeness: Overall compile status — complete, partial, or blocked
        assumptions: Compiler assumptions that were NOT rendered into SPL
        readable_report: Human-readable compile report (deterministic, no LLM)
        intermediate_results: Intermediate stage results
        final_spl_path: Path to saved final SPL file
    """

    spl_text: str
    validation_errors: list[str]
    validation_warnings: list[str]
    compile_diagnostics: list[Any] = field(default_factory=list)
    traces: list[Any] = field(default_factory=list)
    adapter_warnings: list[str] = field(default_factory=list)
    completeness: Completeness = "complete"
    assumptions: list[CompileAssumption] = field(default_factory=list)
    readable_report: str = ""
    intermediate_results: dict[str, Any] = field(default_factory=dict)
    final_spl_path: Path | None = None

    @property
    def diagnostics(self) -> list[Any]:
        """Alias for compile_diagnostics — preferred for new callers."""
        return self.compile_diagnostics


def _missing_slot_name(diagnostic: Any) -> str | None:
    """Extract the missing slot name from a diagnostic, if present."""
    missing_slot = getattr(diagnostic, "missing_slot", None)
    if missing_slot is not None:
        return getattr(missing_slot, "slot_name", None)
    metadata = getattr(diagnostic, "metadata", None)
    if isinstance(metadata, dict):
        return metadata.get("missing_slot")
    return None


DiagnosticDedupKey = tuple[Any, Any, tuple[Any, ...], str | None]


def _dedup_key(diagnostic: Any) -> DiagnosticDedupKey:
    """Deterministic dedup key: (kind, target_ref, sorted source_span_ids, missing_slot_name)."""
    return (
        getattr(diagnostic, "kind", ""),
        getattr(diagnostic, "target_ref", None),
        tuple(sorted(getattr(diagnostic, "source_span_ids", []) or [])),
        _missing_slot_name(diagnostic),
    )


class PipelineOrchestrator:
    """Orchestrates the NL2SPL pipeline.

    Manages stage execution, error handling, and result collection.
    """

    def __init__(self, config: PipelineConfig) -> None:
        """Initialize orchestrator.

        Args:
            config: Pipeline configuration
        """
        self.config = config
        self.client = LLMClient(config.llm)
        self.logger = setup_logger(
            level=config.log_level,
            log_file=config.log_file,
        )

    def run(self, raw_text: str) -> PipelineResult:
        """Run the complete pipeline.

        Args:
            raw_text: Input natural language text

        Returns:
            PipelineResult with SPL and diagnostics
        """
        self.logger.info("Starting NL2SPL pipeline")
        self.logger.info("Input text length: %d chars", len(raw_text))
        # Reset per-run state so stale findings never leak between calls.
        self._pending_construct_findings: dict[str, list[dict]] = {}

        intermediate: dict[str, Any] = {}
        worker_stage_warnings: list[str] = []

        adapter_registry = InputAdapterRegistry(
            llm_client=self.client,
            adapter_llm_engine=self.config.adapter_llm_engine,
        )
        canonical_input = adapter_registry.adapt(raw_text)
        contract_errors = CanonicalCompileInputValidator.validate(canonical_input)
        if contract_errors:
            raise ValueError(
                "CanonicalCompileInput contract validation failed: "
                + "; ".join(contract_errors)
            )
        adapter_warnings = [
            f"{warning.code}: {warning.message}" for warning in canonical_input.warnings
        ]
        intermediate["adapter_detection"] = canonical_input.detection
        intermediate["canonical_input"] = canonical_input
        intermediate["adapter_diagnostics"] = {
            "warnings": adapter_warnings,
            "contract_errors": contract_errors,
        }

        # Stage 1: Span Slicing
        self.logger.info("Stage 1: Span Slicing")
        spans = self._run_stage1(canonical_input)
        intermediate["stage1_spans"] = spans

        # Stage 2: Field Routing
        self.logger.info("Stage 2: Field Routing")
        routes, ambiguity_updates = self._run_stage2(spans, canonical_input)
        intermediate["stage2_routes"] = routes

        # Stage 3: Ambiguity Resolution
        self.logger.info("Stage 3: Ambiguity Resolution")
        resolved_spans, resolved_routes = self._run_stage3(spans, routes, ambiguity_updates)
        intermediate["stage3_resolved"] = {"spans": resolved_spans, "routes": resolved_routes}

        worker_plan: WorkerPlanIR | None = None
        if self.config.enable_worker_boundary_planner:
            # Stage 3.5/3.6: Worker Boundary Planning and validation
            self.logger.info("Stage 3.5: Worker Boundary Planning")
            worker_plan = self._run_stage3_5(resolved_spans, resolved_routes, canonical_input)
            self.logger.info("Stage 3.6: Worker Plan Validation")
            worker_validation = WorkerPlanValidator().validate(
                worker_plan,
                {span.span_id for span in resolved_spans},
            )
            if not worker_validation.is_valid:
                raise ValueError(
                    "WorkerPlanIR validation failed: "
                    + "; ".join(worker_validation.errors)
                )
            intermediate["stage3_5_worker_plan"] = worker_plan
            intermediate["stage3_6_worker_plan_validation"] = worker_validation

            # Defensive repair: worker ownership is required for behavior spans.
            # Non-behavior spans remain global/hint context and must not be
            # forced into a worker ownership set.
            behavior_span_ids = set(resolved_routes.behavior)
            assigned_ids: set[str] = set()
            for w in worker_plan.workers:
                assigned_ids.update(w.owned_span_ids)
            unassigned = behavior_span_ids - assigned_ids
            if unassigned:
                main_worker = worker_plan.main_worker
                main_worker.owned_span_ids.extend(sorted(unassigned, key=lambda sid: int(sid[1:])))
                self.logger.warning(
                    "Stage 3.5 left %d behavior spans unassigned; "
                    "reassigning to main worker %s: %s",
                    len(unassigned), main_worker.worker_id,
                    sorted(unassigned, key=lambda sid: int(sid[1:])),
                )

        # Stage 4: Flow Assembly
        self.logger.info("Stage 4: Flow Assembly")
        worker_flow_plan: WorkerFlowPlanIR | None = None
        if worker_plan is not None:
            flow_output = self._run_stage4(resolved_spans, resolved_routes, worker_plan)
            if not isinstance(flow_output, WorkerFlowPlanIR):
                raise TypeError("Worker-aware Stage 4 must return WorkerFlowPlanIR")
            worker_flow_plan = flow_output
            worker_stage_warnings.extend(worker_flow_plan.warnings)
            intermediate["stage4_worker_flows"] = worker_flow_plan
            # Stage 9 compat: 创建空 FlowStructureIR（Stage 9 不使用 flow/blocks 参数）
            flow_structure = FlowStructureIR()
        else:
            flow_structure = self._run_stage4(resolved_spans, resolved_routes)
        intermediate["stage4_flow"] = flow_structure

        # FailureModeFact bridge: create partial ExceptionFlow skeletons
        # from adapter hard facts before Stage 5 block assembly runs.
        # Only applies when the adapter produced failure modes that
        # Stage 4 did not already convert to exception flows.
        if canonical_input.hard_facts.failure_modes:
            if worker_flow_plan is not None and worker_plan is not None:
                worker_flow_plan = bridge_failure_modes_worker_scoped(
                    canonical_input.hard_facts.failure_modes,
                    resolved_spans,
                    worker_flow_plan,
                    worker_plan,
                )
                intermediate["stage4_worker_flows"] = worker_flow_plan
            else:
                flow_structure = bridge_failure_modes(
                    canonical_input.hard_facts.failure_modes,
                    resolved_spans,
                    flow_structure,
                )
                intermediate["stage4_flow"] = flow_structure

        # Stage 4 IRS check: exception flow slot satisfaction (Phase 3).
        if self.config.enable_irs_stage4_exception_flow_check:
            intermediate.setdefault("construct_satisfaction", {})
            intermediate.setdefault("stage_local_diagnostics", {})
            if worker_flow_plan is not None:
                reports, diags = check_worker_flow_plan_exception_flows_irs(
                    worker_flow_plan,
                )
            else:
                reports, diags = check_exception_flows_irs(flow_structure)
            intermediate["construct_satisfaction"]["stage4"] = reports
            intermediate["stage_local_diagnostics"]["stage4"] = diags

        # Stage 5: Block Assembly
        self.logger.info("Stage 5: Block Assembly")
        worker_block_plan: WorkerBlockPlanIR | None = None
        if worker_flow_plan is not None and worker_plan is not None:
            block_output = self._run_stage5(
                resolved_spans,
                resolved_routes,
                worker_flow_plan,
            )
            if not isinstance(block_output, WorkerBlockPlanIR):
                raise TypeError("Worker-aware Stage 5 must return WorkerBlockPlanIR")
            worker_block_plan = block_output
            worker_stage_warnings.extend(worker_block_plan.warnings)
            intermediate["stage5_worker_blocks"] = worker_block_plan
            # Stage 9 compat: 创建空 BlockStructureIR（Stage 9 不使用 flow/blocks 参数）
            block_structure = BlockStructureIR()
        else:
            block_structure = self._run_stage5(
                resolved_spans,
                resolved_routes,
                flow_structure,
            )
        intermediate["stage5_blocks"] = block_structure

        # Stage 6: Resource Extraction
        self.logger.info("Stage 6: Resource Extraction")
        if (
            self.config.enable_worker_boundary_planner
            and worker_flow_plan is not None
            and worker_block_plan is not None
            and worker_plan is not None
        ):
            # Worker-aware path
            worker_scoped_resources, symbol_table, filter_warns = self._run_stage6_worker_scoped(
                resolved_spans,
                resolved_routes,
                worker_flow_plan,
                worker_block_plan,
                worker_plan,
                canonical_input,
            )
            resources = worker_scoped_resources.global_resources
            intermediate["stage6_worker_scoped_resources"] = worker_scoped_resources
            adapter_warnings.extend(filter_warns)
        else:
            # Legacy path
            resources, symbol_table, filter_warns = self._run_stage6(
                resolved_spans,
                resolved_routes,
                flow_structure,
                block_structure,
                canonical_input,
            )
            adapter_warnings.extend(filter_warns)
        intermediate["stage6_resources"] = resources

        # Stage 7: Step Extraction
        self.logger.info("Stage 7: Step Extraction")
        if (
            self.config.enable_worker_boundary_planner
            and worker_flow_plan is not None
            and worker_block_plan is not None
            and worker_plan is not None
        ):
            # Worker-aware path
            worker_step_plan, symbol_table, stage7_diags = self._run_stage7_worker_scoped(
                resolved_spans,
                resolved_routes,
                worker_flow_plan,
                worker_block_plan,
                symbol_table,
                worker_plan,
            )
            steps = worker_step_plan.get_all_steps()
            worker_stage_warnings.extend(worker_step_plan.warnings)
            intermediate["stage7_worker_step_plan"] = worker_step_plan
        else:
            # Legacy path
            steps, symbol_table, stage7_diags = self._run_stage7(
                resolved_spans,
                resolved_routes,
                flow_structure,
                block_structure,
                symbol_table,
                worker_plan,
            )
        intermediate["stage7_steps"] = steps

        # Stage 7 IRS check: step-level slot satisfaction (Phase 4).
        if self.config.enable_irs_stage7_step_check:
            intermediate.setdefault("construct_satisfaction", {})
            intermediate.setdefault("stage_local_diagnostics", {})
            if worker_step_plan is not None:
                reports, diags = check_worker_step_plan_irs(worker_step_plan)
            else:
                reports, diags = check_steps_irs(steps)
            intermediate["construct_satisfaction"]["stage7"] = reports
            intermediate["stage_local_diagnostics"]["stage7"] = diags

        # Stage 8: Profile Extraction
        self.logger.info("Stage 8: Profile Extraction")
        profile = self._run_stage8(resolved_spans, resolved_routes, symbol_table)
        intermediate["stage8_profile"] = profile

        # Stage 9: Constraint Extraction
        self.logger.info("Stage 9: Constraint Extraction")
        constraints = self._run_stage9(
            resolved_spans,
            resolved_routes,
            flow_structure,
            block_structure,
            symbol_table,
            steps,
            canonical_input,
        )
        intermediate["stage9_constraints"] = constraints

        # Stage 9.5: IR Normalization
        self.logger.info("Stage 9.5: IR Normalization")
        if (
            self.config.enable_worker_boundary_planner
            and worker_flow_plan is not None
            and worker_block_plan is not None
            and worker_step_plan is not None
            and worker_plan is not None
        ):
            # Worker-aware path
            norm_result = self._run_normalization_worker_scoped(
                worker_flow_plan,
                worker_block_plan,
                worker_step_plan,
                worker_plan,
                resources,
                symbol_table,
            )
            (
                worker_flow_plan,
                worker_block_plan,
                worker_step_plan,
                symbol_table,
                normalization_errors,
                normalization_warnings,
            ) = norm_result
            # 更新 steps 为所有 worker 的 steps
            steps = worker_step_plan.get_all_steps()
        else:
            # Legacy path
            norm_result = self._run_normalization(
                flow_structure,
                block_structure,
                resources,
                symbol_table,
                steps,
                constraints,
                worker_plan,
            )
            (
                flow_structure,
                block_structure,
                steps,
                constraints,
                symbol_table,
                normalization_errors,
                normalization_warnings,
            ) = norm_result
        intermediate["stage9_5_normalization"] = norm_result
        # Forward construct findings from Stage 9.5 to post-normalize IRS pass.
        # Always assign (even empty) so a previous run's findings never leak.
        intermediate["stage9_5_construct_findings"] = getattr(
            self, "_pending_construct_findings", {}
        )
        self._pending_construct_findings = {}

        # Stage 10: Worker Assembly
        self.logger.info("Stage 10: Worker Assembly")
        if (
            self.config.enable_worker_boundary_planner
            and worker_flow_plan is not None
            and worker_block_plan is not None
            and worker_step_plan is not None
            and worker_plan is not None
        ):
            # Worker-aware path
            worker = self._run_stage10_worker_scoped(
                worker_step_plan,
                resources,
                symbol_table,
                worker_plan,
                worker_flow_plan,
                worker_block_plan,
            )
        else:
            # Legacy path
            worker = self._run_stage10(
                flow_structure,
                block_structure,
                steps,
                resources,
                symbol_table,
                worker_plan,
            )
        intermediate["stage10_worker"] = worker

        # Post-normalize IRS check: final authority for construct-level
        # diagnostics from normalized, assembled IR.
        post_norm_diags: list[Any] = []
        if self.config.enable_irs_post_normalize_check:
            self.logger.info("Post-normalize IRS check")
            checker = PostNormalizeIRSChecker()
            post_norm_diags = checker.check(
                worker=worker,
                worker_plan=worker_plan,
                symbol_table=symbol_table,
                resources=resources,
                worker_scoped_resources=intermediate.get(
                    "stage6_worker_scoped_resources"
                ),
                construct_findings=intermediate.get(
                    "stage9_5_construct_findings"
                ),
            )

        # Executable element gate — filter non-source-backed steps before
        # rendering so only verifiable commands reach Stage 11.
        self.logger.info("Executable element gate")
        gate = ExecutableElementGate()
        worker, render_info, gate_diags = gate.apply(worker, worker_plan)
        intermediate["render_info"] = render_info
        # Mark steps as scoped so the renderer uses the filtered worker.steps
        # and does NOT fall back to the pre-gate flat steps list.
        worker.scoped_steps = True

        # Stage 11: SPL Rendering
        self.logger.info("Stage 11: SPL Rendering")
        spl_text, errors, warnings = self._run_stage11(
            worker, profile, resources, symbol_table, steps, constraints
        )
        errors = normalization_errors + errors
        warnings = worker_stage_warnings + normalization_warnings + warnings
        intermediate["stage11_spl"] = spl_text
        final_spl_path = save_final_spl(
            spl_text=spl_text,
            output_dir=self.config.run_dir,
            filename=self.config.final_spl_filename,
        )

        self.logger.info("Pipeline complete. SPL length: %d chars", len(spl_text))

        # Provenance aggregation (post-compilation)
        # Merge global + worker-scoped resources so worker-local variables
        # are included in traces.  Track which variables are worker-local
        # so the aggregator can emit scoped target_refs.
        ws_resources: WorkerScopedResourceIR | None = intermediate.get(
            "stage6_worker_scoped_resources"
        )
        resources_for_prov = resources
        worker_var_scopes: dict[str, str] | None = None
        if ws_resources is not None:
            resources_for_prov = ResourceRegistryIR(
                variables=ws_resources.get_all_variables(),
                files=resources.files + [
                    f for wr in ws_resources.worker_resources.values()
                    for f in wr.files
                ],
                apis=ws_resources.get_all_apis(),
                types=resources.types + [
                    t for wr in ws_resources.worker_resources.values()
                    for t in wr.types
                ],
            )
            worker_var_scopes = {}
            for worker_id, wr in ws_resources.worker_resources.items():
                for v in wr.variables:
                    worker_var_scopes[v.name] = worker_id

        # Build post-gate flat step list — blocked steps must not
        # participate in provenance traces or variable producer detection.
        prov_steps = list(worker.steps)
        for child in worker.child_workers:
            prov_steps.extend(child.steps)
        # Compute child worker IDs and declared APIs for handoff validation
        prov_child_ids: set[str] | None = None
        prov_declared_apis: set[str] = {a.api_name for a in resources_for_prov.apis}
        prov_worker_owned_spans: dict[str, list[str]] = {}
        prov_variable_facts: list[Any] = []
        if worker_plan is not None:
            prov_child_ids = {
                w.worker_id for w in worker_plan.workers
                if w.boundary_kind != "main_worker"
                and w.boundary_kind != "not_a_worker"
            }
            prov_worker_owned_spans = {
                w.worker_name: list(w.owned_span_ids)
                for w in worker_plan.workers
            }
        # Gather adapter hard facts for variable provenance
        prov_variable_facts = (
            list(canonical_input.hard_facts.inputs)
            + list(canonical_input.hard_facts.outputs)
        )
        prov_delegation_intents = list(
            canonical_input.hard_facts.delegation_intents
        )

        aggregator = ProvenanceAggregator()
        traces, provenance_diags = aggregator.aggregate(
            worker=worker,
            steps=prov_steps,
            constraints=constraints,
            resources=resources_for_prov,
            symbol_table=symbol_table,
            spans=resolved_spans,
            profile=profile,
            worker_var_scopes=worker_var_scopes,
            handoffs=worker_plan.handoffs if worker_plan else None,
            known_child_worker_ids=prov_child_ids,
            declared_apis=prov_declared_apis,
            worker_owned_spans=prov_worker_owned_spans,
            variable_facts=prov_variable_facts,
            delegation_intents=prov_delegation_intents,
        )

        # Delegation intent diagnostics: emit type_or_contract_ambiguity
        # for intents without a valid handoff contract.
        delegation_diags = bridge_delegation_intents(
            list(canonical_input.hard_facts.delegation_intents),
            worker_plan.handoffs if worker_plan else None,
            resolved_spans,
            known_child_worker_ids=prov_child_ids,
            declared_apis=prov_declared_apis,
        )

        # Semantic conflict analysis (Phase 6) -- before consolidation.
        conflict_context = ConflictAnalysisContext(
            spans=resolved_spans,
            canonical_input=canonical_input,
            worker_plan=worker_plan,
        )
        conflict_analyzer = self._make_semantic_conflict_analyzer()
        raw_conflict_diags = conflict_analyzer.analyze(
            constraints=constraints,
            steps=steps,
            flows=(
                worker_flow_plan
                if worker_flow_plan is not None
                else flow_structure
            ),
            symbols=symbol_table,
            context=conflict_context,
        )
        verifier = LLMConflictDiagnosticVerifier()
        conflict_diags, conflict_warnings = verifier.verify(raw_conflict_diags)
        adapter_warnings.extend(conflict_warnings)

        # Assemble final diagnostics and compute result fields.
        # post_norm_diags replaces the old compile_diagnostics from Stage 9.5.
        # stage7_diags carries unmapped_behavior_span and other LLM-stage
        # diagnostics that are not covered by the post-normalize IRS pass.
        all_diagnostics = (
            stage7_diags + post_norm_diags + conflict_diags + gate_diags
            + provenance_diags + delegation_diags
        )
        # IRS consolidation only runs when the post-normalize checker is
        # disabled; otherwise Stage 4/7 IRS diagnostics stay as reports only.
        if (
            self.config.enable_irs_diagnostic_consolidation
            and not self.config.enable_irs_post_normalize_check
        ):
            all_diagnostics = self._consolidate_compile_diagnostics(
                all_diagnostics,
                intermediate,
            )
        completeness = compute_completeness(
            validation_errors=errors,
            diagnostics=all_diagnostics,
        )
        assumption_builder = AssumptionBuilder()
        assumptions = assumption_builder.build(all_diagnostics)
        readable_report = render_report(
            spl_text=spl_text,
            completeness=completeness,
            diagnostics=all_diagnostics,
            assumptions=assumptions,
            traces=traces,
            adapter_warnings=adapter_warnings,
            validation_errors=errors,
            validation_warnings=warnings,
        )

        return PipelineResult(
            spl_text=spl_text,
            validation_errors=errors,
            validation_warnings=warnings,
            compile_diagnostics=all_diagnostics,
            traces=traces,
            adapter_warnings=adapter_warnings,
            completeness=completeness,
            assumptions=assumptions,
            readable_report=readable_report,
            intermediate_results=intermediate,
            final_spl_path=final_spl_path,
        )

    # Stage implementations
    def _run_stage1(self, raw_text: str | CanonicalCompileInput) -> list[SpanIR]:
        """Stage 1: Span Slicing."""
        stage = SpanSlicer(self.config, self.client)
        return stage.execute(raw_text)

    def _run_stage2(
        self,
        spans: list[SpanIR],
        canonical_input: CanonicalCompileInput | None = None,
    ) -> tuple[FieldRouteIR, list[dict[str, Any]]]:
        """Stage 2: Field Routing."""
        stage = FieldRouter(self.config, self.client)
        if canonical_input is None:
            return stage.execute(spans)
        return stage.execute((spans, canonical_input))

    def _run_stage3(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        ambiguity_updates: list[dict[str, Any]],
    ) -> tuple[list[SpanIR], FieldRouteIR]:
        """Stage 3: Ambiguity Resolution."""
        stage = AmbiguityResolver(self.config, self.client)
        return stage.execute((spans, routes, ambiguity_updates))

    def _run_stage3_5(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        canonical_input: CanonicalCompileInput | None = None,
    ) -> WorkerPlanIR:
        """Stage 3.5: Worker Boundary Planning."""
        stage = WorkerBoundaryPlanner(self.config, self.client)
        return stage.execute((spans, routes, canonical_input))

    def _run_stage4(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_plan: WorkerPlanIR | None = None,
    ) -> FlowStructureIR | WorkerFlowPlanIR:
        """Stage 4: Flow Assembly."""
        stage = FlowAssembler(self.config, self.client)
        if worker_plan is not None:
            return stage.execute((spans, routes, worker_plan))
        return stage.execute((spans, routes))

    def _run_stage5(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        flow_structure: FlowStructureIR | WorkerFlowPlanIR,
    ) -> BlockStructureIR | WorkerBlockPlanIR:
        """Stage 5: Block Assembly."""
        stage = BlockAssembler(self.config, self.client)
        return stage.execute((spans, routes, flow_structure))

    def _run_stage6(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        canonical_input: CanonicalCompileInput | None = None,
    ) -> tuple[ResourceRegistryIR, SymbolTable, list[str]]:
        """Stage 6: Resource Extraction."""
        stage = ResourceExtractor(self.config, self.client)
        if canonical_input is not None:
            resources, symbols = stage.execute((spans, routes, flow, blocks, canonical_input))
        else:
            resources, symbols = stage.execute((spans, routes, flow, blocks))
        filter_warnings = getattr(stage, "resource_filter_warnings", [])
        return resources, symbols, list(filter_warnings)

    def _run_stage6_worker_scoped(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        worker_plan: WorkerPlanIR,
        canonical_input: CanonicalCompileInput | None = None,
    ) -> tuple[WorkerScopedResourceIR, SymbolTable, list[str]]:
        """Stage 6: Worker-scoped Resource Extraction."""
        stage = ResourceExtractor(self.config, self.client)
        worker_scoped_resources, symbols = stage.execute_worker_scoped(
            spans, routes, worker_flow_plan, worker_block_plan, worker_plan, canonical_input
        )
        filter_warnings = getattr(stage, "resource_filter_warnings", [])
        return worker_scoped_resources, symbols, list(filter_warnings)

    def _run_stage7(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        symbols: SymbolTable,
        worker_plan: WorkerPlanIR | None = None,
    ) -> tuple[list[StepIR], SymbolTable, list[Any]]:
        """Stage 7: Step Extraction."""
        stage = StepExtractor(self.config, self.client)
        if worker_plan is not None:
            result = stage.execute((spans, routes, flow, blocks, symbols, worker_plan))
        else:
            result = stage.execute((spans, routes, flow, blocks, symbols))
        return (*result, getattr(stage, "stage7_diagnostics", []))

    def _run_stage7_worker_scoped(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        symbol_table: SymbolTable,
        worker_plan: WorkerPlanIR,
    ) -> tuple[WorkerStepPlanIR, SymbolTable, list[Any]]:
        """Stage 7: Worker-scoped Step Extraction."""
        stage = StepExtractor(self.config, self.client)
        result = stage.execute_worker_scoped(
            spans, routes, worker_flow_plan, worker_block_plan, symbol_table, worker_plan
        )
        return (*result, getattr(stage, "stage7_diagnostics", []))

    def _run_stage8(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        symbols: SymbolTable,
    ) -> AgentProfileIR:
        """Stage 8: Profile Extraction."""
        stage = ProfileExtractor(self.config, self.client)
        return stage.execute((spans, routes, symbols))

    def _run_stage9(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        symbols: SymbolTable,
        steps: list[StepIR],
        canonical_input: CanonicalCompileInput | None = None,
    ) -> list[ConstraintIR]:
        """Stage 9: Constraint Extraction."""
        stage = ConstraintExtractor(self.config, self.client)
        if canonical_input is not None:
            return stage.execute(
                (spans, routes, flow, blocks, symbols, steps, canonical_input)
            )
        return stage.execute((spans, routes, flow, blocks, symbols, steps))

    def _run_normalization(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        resources: ResourceRegistryIR,
        symbols: SymbolTable,
        steps: list[StepIR],
        constraints: list[ConstraintIR],
        worker_plan: WorkerPlanIR | None = None,
    ) -> tuple[
        FlowStructureIR,
        BlockStructureIR,
        list[StepIR],
        list[ConstraintIR],
        SymbolTable,
        list[str],
        list[str],
    ]:
        """Stage 9.5: IR Normalization."""
        normalizer = IRNormalizer()
        result = normalizer.normalize(
            flow,
            blocks,
            resources,
            symbols,
            steps,
            constraints,
            worker_plan,
        )
        # Collect structured findings for post-normalize IRS pass.
        findings = getattr(normalizer, "construct_findings", None)
        if findings:
            self._pending_construct_findings = findings
        return result

    def _run_normalization_worker_scoped(
        self,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        worker_step_plan: WorkerStepPlanIR,
        worker_plan: WorkerPlanIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
    ) -> tuple[
        WorkerFlowPlanIR,
        WorkerBlockPlanIR,
        WorkerStepPlanIR,
        SymbolTable,
        list[str],
        list[str],
    ]:
        """Stage 9.5: Worker-scoped IR Normalization."""
        normalizer = IRNormalizer()
        result = normalizer.normalize_worker_scoped(
            worker_flow_plan,
            worker_block_plan,
            worker_step_plan,
            worker_plan,
            resources,
            symbol_table,
        )
        # Collect structured findings for post-normalize IRS pass.
        findings = getattr(normalizer, "construct_findings", None)
        if findings:
            self._pending_construct_findings = findings
        return result

    def _run_stage10(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        steps: list[StepIR],
        resources: ResourceRegistryIR,
        symbols: SymbolTable,
        worker_plan: WorkerPlanIR | None = None,
    ) -> WorkerIR:
        """Stage 10: Worker Assembly (legacy path)."""
        assembler = WorkerAssembler()
        return assembler.assemble(flow, blocks, steps, resources, symbols, worker_plan)

    def _run_stage10_worker_scoped(
        self,
        worker_step_plan: WorkerStepPlanIR,
        resources: ResourceRegistryIR,
        symbols: SymbolTable,
        worker_plan: WorkerPlanIR,
        worker_flow_plan: WorkerFlowPlanIR | None = None,
        worker_block_plan: WorkerBlockPlanIR | None = None,
    ) -> WorkerIR:
        """Stage 10: Worker Assembly (worker-aware path).

        Uses worker-scoped IRs directly instead of legacy adapter.
        """
        assembler = WorkerAssembler()
        return assembler.assemble_from_worker_scoped(
            worker_step_plan,
            resources,
            symbols,
            worker_plan,
            worker_flow_plan,
            worker_block_plan,
        )

    def _make_semantic_conflict_analyzer(
        self,
    ) -> NoOpSemanticConflictAnalyzer | LLMSemanticConflictAnalyzer:
        """Return the active semantic conflict analyzer (Phase 6)."""
        if self.config.enable_llm_conflict_analyzer:
            return LLMSemanticConflictAnalyzer(call_json=self.client.call_json)
        return NoOpSemanticConflictAnalyzer()

    def _consolidate_compile_diagnostics(
        self,
        existing: list[Any],
        intermediate: dict[str, Any],
    ) -> list[Any]:
        """Merge stage-local IRS diagnostics into *existing* diagnostics.

        Existing diagnostics take priority.  Stage-local diagnostics with
        the same ``(kind, target_ref, sorted source_span_ids)`` key are
        skipped as duplicates.
        """
        stage_local: dict[str, list[Any]] = intermediate.get(
            "stage_local_diagnostics", {}
        )
        if not stage_local:
            return list(existing)

        seen: set[DiagnosticDedupKey] = set()
        for diag in existing:
            seen.add(_dedup_key(diag))

        consolidated = list(existing)
        for _stage_name, diags in stage_local.items():
            if not isinstance(diags, list):
                continue
            for diag in diags:
                key = _dedup_key(diag)
                if key not in seen:
                    seen.add(key)
                    consolidated.append(diag)

        return consolidated

    def _run_stage11(
        self,
        worker: WorkerIR,
        profile: AgentProfileIR,
        resources: ResourceRegistryIR,
        symbols: SymbolTable,
        steps: list[StepIR],
        constraints: list[ConstraintIR],
    ) -> tuple[str, list[str], list[str]]:
        """Stage 11: SPL Rendering."""
        renderer = SPLRenderer()
        return renderer.render(worker, profile, resources, symbols, steps, constraints)
