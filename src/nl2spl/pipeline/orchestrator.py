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
    NoOpSemanticConflictAnalyzer,
)
from nl2spl.compiler.annotation_role_contract.projector import (
    project_stage2_to_compile_diagnostics,
)
from nl2spl.compiler.assumptions import AssumptionBuilder
from nl2spl.compiler.capability_intent.evidence_collector import (
    EarlyCapabilityEvidenceCollector,
)
from nl2spl.compiler.capability_intent.resolver import (
    ExternalCapabilityIntentResolver,
)
from nl2spl.compiler.compile_result import CompileAssumption, Completeness
from nl2spl.compiler.completeness import compute_completeness
from nl2spl.compiler.construct_plan import ConstructPlan, ConstructPlanner
from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.diagnostic_consolidator import (
    DiagnosticConsolidationInput,
    DiagnosticConsolidator,
)
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.factory import build_irs_subsystem
from nl2spl.compiler.irs.result_store import IRSResultStore
from nl2spl.compiler.irs.subsystem import IRSSubsystem
from nl2spl.config import PipelineConfig
from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.diagnostics import (
    METADATA_KEY_AUTHORITY,
    METADATA_KEY_IRS_REF,
    METADATA_KEY_ISSUE_GROUP_ID,
    METADATA_KEY_ISSUE_ROLE,
    METADATA_KEY_PRESENTATION_DISPOSITION,
    METADATA_KEY_PRIMARY_DIAGNOSTIC_ID,
    METADATA_KEY_RELATED_DIAGNOSTIC_IDS,
    METADATA_KEY_REPAIRABILITY,
    CompileDiagnostic,
)
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
from nl2spl.pipeline.capability_semantic_extractor import (
    ExternalCapabilitySemanticExtractor,
)
from nl2spl.pipeline.executable_gate import ExecutableElementGate
from nl2spl.pipeline.provenance import ProvenanceAggregator
from nl2spl.pipeline.resource_declaration_gate import ResourceDeclarationGate
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner import WorkerBoundaryPlanner
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.materializer import (
    _span_sort_key,
)
from nl2spl.pipeline.stages.stage3_ambiguity_resolver import AmbiguityResolver
from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler
from nl2spl.pipeline.stages.stage5_block_assembler import (
    BlockAssembler,
    project_api_call_placements,
)
from nl2spl.pipeline.stages.stage6_resource_extractor import (
    ResourceExtractor,
    materialize_api_declaration_skeletons,
)
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor
from nl2spl.pipeline.stages.stage8_profile_extractor import ProfileExtractor
from nl2spl.pipeline.stages.stage9_5_normalizer import IRNormalizer
from nl2spl.pipeline.stages.stage9_constraint_extractor import ConstraintExtractor
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler
from nl2spl.pipeline.stages.stage11_spl_renderer import SPLRenderer
from nl2spl.pipeline.worker_plan_validator import WorkerPlanValidator
from nl2spl.utils.logger import setup_logger
from nl2spl.utils.persistence import save_final_spl, save_intermediate_result


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
        completeness: Overall compile status 鈥?complete, partial, or blocked
        assumptions: Compiler assumptions that were NOT rendered into SPL
        readable_report: Deprecated MVP compatibility field. Human-readable
            compile reports are not generated in the MVP output path.
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

    # Snapshot persistence (S4)
    spl_editing_snapshot_path: Path | None = None
    spl_editing_snapshot_status: str = "not_requested"
    spl_editing_snapshot_error: str | None = None
    spl_editing_explanation_status: str = "not_requested"
    spl_editing_explanation_error: str | None = None

    @property
    def diagnostics(self) -> list[Any]:
        """Alias for compile_diagnostics 鈥?preferred for new callers."""
        return self.compile_diagnostics


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
        self._issue_explanation_futures: dict[Path, Any] = {}

    def run(self, raw_text: str) -> PipelineResult:
        """Run the complete pipeline.

        Args:
            raw_text: Input natural language text

        Returns:
            PipelineResult with SPL and diagnostics
        """
        self.logger.info("Starting NL2SPL pipeline")
        self.logger.info("Input text length: %d chars", len(raw_text))
        intermediate: dict[str, Any] = {}
        worker_stage_warnings: list[str] = []

        # IRS subsystem: stage-local construct satisfaction + post-normalize
        irs_subsystem: IRSSubsystem = build_irs_subsystem(self.config.irs)
        irs_store = IRSResultStore()

        adapter_registry = InputAdapterRegistry()
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

        early_capability_evidence = EarlyCapabilityEvidenceCollector().collect(
            canonical_input, spans, routes
        )
        intermediate["capability_evidence_candidates"] = early_capability_evidence
        intermediate["capability_evidence_candidates_payload"] = (
            early_capability_evidence.to_payload()
        )
        if self.config.save_intermediate:
            save_intermediate_result(
                stage_name="early_capability_evidence_collector",
                result=early_capability_evidence.to_payload(),
                output_dir=self.config.run_dir,
            )

        # Stage 3: Ambiguity Resolution
        self.logger.info("Stage 3: Ambiguity Resolution")
        resolved_spans, resolved_routes = self._run_stage3(spans, routes, ambiguity_updates)
        intermediate["stage3_resolved"] = {"spans": resolved_spans, "routes": resolved_routes}

        capability_extraction = ExternalCapabilitySemanticExtractor(
            self.client
        ).extract(resolved_spans, resolved_routes, early_capability_evidence)
        intermediate["external_capability_extraction"] = capability_extraction
        intermediate["external_capability_extraction_payload"] = (
            capability_extraction.to_payload()
        )
        if self.config.save_intermediate:
            save_intermediate_result(
                stage_name="external_capability_semantic_extractor",
                result=capability_extraction.to_payload(),
                output_dir=self.config.run_dir,
            )

        # Phase D: build canonical DemandView from Stage 2 confirmed annotations.
        # This replaces the old Stage 3.2 ResourceContractPlanner as the
        # production source of truth for resource contract demands.
        from nl2spl.compiler.resource_contract_demand_view.builder import (
            DemandViewBuilder,
        )
        from nl2spl.compiler.resource_contract_demand_view.projector import (
            ViewDiagnosticProjector,
        )
        demand_view = DemandViewBuilder().build(resolved_spans, resolved_routes)

        # Phase D: DemandView diagnostics enter compile diagnostics.
        view_diagnostics = ViewDiagnosticProjector.project(demand_view)

        # Save DemandView payload for checkpoint / debugging.
        intermediate["resource_contract_demand_view"] = demand_view
        intermediate["resource_contract_demand_view_payload"] = demand_view.to_payload()
        if self.config.save_intermediate:
            save_intermediate_result(
                stage_name="stage3_2_demand_view",
                result=demand_view.to_payload(),
                output_dir=self.config.run_dir,
            )

        capability_intent_plan = ExternalCapabilityIntentResolver().resolve(
            source_schema=canonical_input.source_schema,
            extraction=capability_extraction,
            early_evidence=early_capability_evidence,
            demand_view=demand_view,
        )
        intermediate["external_capability_intent_plan"] = capability_intent_plan
        intermediate["external_capability_intent_plan_payload"] = (
            capability_intent_plan.to_payload()
        )
        if self.config.save_intermediate:
            save_intermediate_result(
                stage_name="external_capability_intent_resolver",
                result=capability_intent_plan.to_payload(),
                output_dir=self.config.run_dir,
            )

        # Phase E: ResourceContractPlanner and ResourceContractPlanIR are
        # no longer part of the production path.  DemandView is the sole
        # authority.  Old intermediate keys removed.

        # Stage 3.25: Construct demand planning
        self.logger.info("Stage 3.25: Construct Demand Planning")
        construct_plan = ConstructPlanner().plan(
            resolved_spans,
            resolved_routes,
            source_schema=canonical_input.source_schema,
            capability_intent_plan=capability_intent_plan,
        )
        intermediate["construct_plan"] = construct_plan
        intermediate["construct_plan_payload"] = construct_plan.to_payload()
        if construct_plan.diagnostics:
            intermediate.setdefault("stage_local_diagnostics", {})
            intermediate["stage_local_diagnostics"]["construct_plan"] = (
                construct_plan.diagnostics
            )

        # Stage 3.5/3.6: Worker Boundary Planning and validation
        self.logger.info("Stage 3.5: Worker Boundary Planning")
        worker_plan = self._run_stage3_5(
            resolved_spans,
            resolved_routes,
            canonical_input,
            demand_view=demand_view,
            external_capability_intent_plan=capability_intent_plan,
        )
        pre_repair_validation = WorkerPlanValidator().validate(
            worker_plan,
            {span.span_id for span in resolved_spans},
        )
        if not pre_repair_validation.is_valid:
            raise ValueError(
                "WorkerPlanIR validation failed: "
                + "; ".join(pre_repair_validation.errors)
            )

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
            main_worker.owned_span_ids.extend(sorted(unassigned, key=_span_sort_key))
            self.logger.warning(
                "Stage 3.5 left %d behavior spans unassigned; "
                "reassigning to main worker %s: %s",
                len(unassigned), main_worker.worker_id,
                sorted(unassigned, key=_span_sort_key),
            )

        if construct_plan.demands:
            construct_plan.enforce_exception_flow_ownership(worker_plan)

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

        # Stage 3.5 IRS: construct satisfaction for worker/delegation
        if self.config.irs.stage_local_enabled:
            irs_ctx_35 = IRSCheckContext(
                stage_name="stage3_5",
                worker_plan=worker_plan,
                spans=tuple(resolved_spans),
                routes=resolved_routes,
            )
            irs_store.put_stage_result(
                irs_subsystem.run_stage_local("stage3_5", irs_ctx_35)
            )

        # Stage 4: Flow Assembly
        self.logger.info("Stage 4: Flow Assembly")
        active_construct_plan = construct_plan if construct_plan.demands else None
        if active_construct_plan is not None:
            flow_output = self._run_stage4(
                resolved_spans, resolved_routes, worker_plan, active_construct_plan,
            )
        else:
            flow_output = self._run_stage4(
                resolved_spans, resolved_routes, worker_plan,
            )
        if not isinstance(flow_output, WorkerFlowPlanIR):
            raise TypeError("Worker-aware Stage 4 must return WorkerFlowPlanIR")
        worker_flow_plan = flow_output
        worker_stage_warnings.extend(worker_flow_plan.warnings)
        intermediate["stage4_worker_flows"] = worker_flow_plan
        # Stage 9 compatibility placeholder; worker-aware path uses worker flows.
        flow_structure = FlowStructureIR()
        intermediate["stage4_flow"] = flow_structure

        # Stage 4 IRS: construct satisfaction for exception flows
        if self.config.irs.stage_local_enabled:
            irs_ctx_4 = IRSCheckContext(
                stage_name="stage4",
                worker_flows=worker_flow_plan,
                routes=resolved_routes,
                spans=tuple(resolved_spans),
            )
            irs_store.put_stage_result(
                irs_subsystem.run_stage_local("stage4", irs_ctx_4)
            )

        # Stage 5: Block Assembly
        self.logger.info("Stage 5: Block Assembly")
        if active_construct_plan is not None:
            block_output = self._run_stage5(
                resolved_spans,
                resolved_routes,
                worker_flow_plan,
                active_construct_plan,
            )
        else:
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
        # Stage 9 compatibility placeholder; worker-aware path uses worker blocks.
        block_structure = BlockStructureIR()
        intermediate["stage5_blocks"] = block_structure

        api_call_placements = project_api_call_placements(
            construct_plan,
            worker_plan,
            worker_flow_plan,
            worker_block_plan,
        )
        intermediate["api_call_placements"] = api_call_placements
        intermediate["api_call_placement_payload"] = [
            placement.to_payload() for placement in api_call_placements
        ]

        # Stage 6: Resource Extraction
        self.logger.info("Stage 6: Resource Extraction")
        # Phase D: reuse the canonical DemandView built after Stage 3.

        # Phase C: coverage audit using the same canonical DemandView.
        coverage_diagnostics: list[Any] = []
        if canonical_input is not None:
            from nl2spl.compiler.resource_contract_demand_view.coverage_validator import (
                ResourceContractAnnotationCoverageValidator,
            )
            from nl2spl.compiler.resource_contract_demand_view.projector import (
                ViewDiagnosticProjector,
            )
            validator = ResourceContractAnnotationCoverageValidator()
            cov_diags = validator.validate(
                canonical_input, resolved_spans, resolved_routes, demand_view,
            )
            coverage_diagnostics = ViewDiagnosticProjector.project_list(
                list(cov_diags)
            )
            intermediate["resource_contract_coverage_diagnostics"] = [
                {
                    "kind": d.kind, "severity": d.severity, "message": d.message,
                    "span_ids": sorted(d.span_ids),
                }
                for d in cov_diags
            ]
            intermediate["resource_contract_coverage_summary"] = {
                "total_hard_facts": (
                    len(canonical_input.hard_facts.inputs)
                    + len(canonical_input.hard_facts.outputs)
                ),
                "unmatched_count": len(cov_diags),
            }

        worker_scoped_resources, symbol_table, filter_warns = self._run_stage6_worker_scoped(
            resolved_spans,
            resolved_routes,
            worker_flow_plan,
            worker_block_plan,
            worker_plan,
            canonical_input,
            demand_view=demand_view,
        )
        resources = worker_scoped_resources.global_resources
        intermediate["stage6_worker_scoped_resources"] = worker_scoped_resources
        adapter_warnings.extend(filter_warns)
        api_materialization_plan = materialize_api_declaration_skeletons(
            resources,
            construct_plan,
        )
        intermediate["api_materialization_plan"] = api_materialization_plan
        intermediate["api_materialization_plan_payload"] = (
            api_materialization_plan.to_payload()
        )
        intermediate["stage6_resources"] = resources

        # Stage 7: Step Extraction
        self.logger.info("Stage 7: Step Extraction")
        if active_construct_plan is not None:
            worker_step_plan, symbol_table, stage7_diags = (
                self._run_stage7_worker_scoped(
                    resolved_spans,
                    resolved_routes,
                    worker_flow_plan,
                    worker_block_plan,
                    symbol_table,
                    worker_plan,
                    active_construct_plan,
                    api_materialization_plan,
                    api_call_placements,
                    resources,
                )
            )
        else:
            worker_step_plan, symbol_table, stage7_diags = (
                self._run_stage7_worker_scoped(
                    resolved_spans,
                    resolved_routes,
                    worker_flow_plan,
                    worker_block_plan,
                    symbol_table,
                    worker_plan,
                )
            )
        steps = worker_step_plan.get_all_steps()
        worker_stage_warnings.extend(worker_step_plan.warnings)
        intermediate["stage7_worker_step_plan"] = worker_step_plan
        intermediate["stage7_steps"] = steps

        # Stage 7 IRS: construct satisfaction for steps
        if self.config.irs.stage_local_enabled:
            irs_ctx_7 = IRSCheckContext(
                stage_name="stage7",
                worker_steps=worker_step_plan,
                routes=resolved_routes,
                spans=tuple(resolved_spans),
                symbol_table=symbol_table,
            )
            irs_store.put_stage_result(
                irs_subsystem.run_stage_local("stage7", irs_ctx_7)
            )

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
        # 鏇存柊 steps 涓烘墍鏈?worker 鐨?steps
        steps = worker_step_plan.get_all_steps()
        intermediate["stage9_5_normalization"] = norm_result
        # Store normalized symbol table for S4 snapshot persistence
        intermediate["symbol_table"] = symbol_table

        # Stage 10: Worker Assembly
        self.logger.info("Stage 10: Worker Assembly")
        worker = self._run_stage10_worker_scoped(
            worker_step_plan,
            resources,
            symbol_table,
            worker_plan,
            worker_flow_plan,
            worker_block_plan,
        )
        intermediate["stage10_worker"] = worker

        # Resource declaration gate: API declarations are renderable only
        # when authorized by post-normalize API_DECLARATION reports.
        api_decl_result = irs_subsystem.run_post_normalize_result(
            worker=None,
            worker_plan=worker_plan,
            symbol_table=symbol_table,
            resources=resources,
            worker_scoped_resources=intermediate.get(
                "stage6_worker_scoped_resources"
            ),
            demand_view=demand_view,
        )
        resource_gate = ResourceDeclarationGate()
        renderable_resources = resource_gate.apply(
            resources,
            api_decl_result.reports,
            authority="post_normalize_irs",
        )
        intermediate["renderable_resource_registry_view"] = renderable_resources
        intermediate["renderable_resource_registry_payload"] = (
            renderable_resources.to_payload()
        )

        # Post-normalize IRS check: final authority for construct-level
        # diagnostics from normalized, assembled IR.
        self.logger.info("Post-normalize IRS check")
        post_norm_result = irs_subsystem.run_post_normalize_result(
            worker=worker,
            worker_plan=worker_plan,
            symbol_table=symbol_table,
            resources=renderable_resources,
            worker_scoped_resources=intermediate.get(
                "stage6_worker_scoped_resources"
            ),
            demand_view=demand_view,
            renderable_resource_registry_view=renderable_resources,
        )
        post_norm_diags = list(post_norm_result.diagnostics)
        irs_store.put_post_normalize_diagnostics(post_norm_diags)
        irs_store.put_stage_result(post_norm_result)

        # Write IRS payload to intermediate (after all IRS checks complete)
        if self.config.irs.enabled:
            irs_payload = irs_store.to_intermediate_payload()
            intermediate["construct_satisfaction"] = irs_payload["construct_satisfaction"]
            intermediate["stage_local_diagnostics"] = {
                **intermediate.get("stage_local_diagnostics", {}),
                **irs_payload["stage_local_diagnostics"],
            }
            intermediate["irs_stage_results"] = irs_payload["irs_stage_results"]
            intermediate["irs_post_normalize_diagnostics"] = irs_payload[
                "irs_post_normalize_diagnostics"
            ]

        # Executable element gate 鈥?filter non-source-backed steps before
        # rendering so only verifiable commands reach Stage 11.
        self.logger.info("Executable element gate")
        gate = ExecutableElementGate()
        gate.renderable_resource_registry_view = renderable_resources
        worker, render_info, gate_diags = gate.apply(worker, worker_plan)
        intermediate["render_info"] = render_info
        # Mark steps as scoped so the renderer uses the filtered worker.steps
        # and does NOT fall back to the pre-gate flat steps list.
        worker.scoped_steps = True

        # Stage 11: SPL Rendering
        self.logger.info("Stage 11: SPL Rendering")
        spl_text, errors, warnings = self._run_stage11(
            worker, profile, renderable_resources, symbol_table, steps, constraints
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
        resources_for_prov = renderable_resources
        worker_var_scopes: dict[str, str] | None = None
        if ws_resources is not None:
            resources_for_prov = ResourceRegistryIR(
                variables=ws_resources.get_all_variables(),
                files=resources.files + [
                    f for wr in ws_resources.worker_resources.values()
                    for f in wr.files
                ],
                apis=list(renderable_resources.apis),
                types=resources.types + [
                    t for wr in ws_resources.worker_resources.values()
                    for t in wr.types
                ],
            )
            worker_var_scopes = {}
            for worker_id, wr in ws_resources.worker_resources.items():
                for v in wr.variables:
                    worker_var_scopes[v.name] = worker_id

        # Build post-gate flat step list 鈥?blocked steps must not
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

        promoted_irs_diags = self._promoted_irs_diagnostics(irs_store)

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
        consolidation = DiagnosticConsolidator().consolidate(
            DiagnosticConsolidationInput(
                stage2_diagnostics=project_stage2_to_compile_diagnostics(
                    intermediate["stage2_routes"].structured_route_diagnostics
                ),
                construct_plan_diagnostics=list(construct_plan.diagnostics),
                stage7_diagnostics=list(stage7_diags),
                irs_store=irs_store,
                post_normalize_diagnostics=list(post_norm_diags),
                gate_diagnostics=list(gate_diags),
                provenance_diagnostics=list(provenance_diags),
                irs_promoted_diagnostics=list(promoted_irs_diags),
                conflict_diagnostics=list(conflict_diags),
                include_stage_local_diagnostics=(
                    self.config.irs.include_stage_local_diagnostics_in_compile
                ),
            )
        )
        all_diagnostics = consolidation.final_diagnostics
        # Phase D: merge DemandView + coverage diagnostics into final output
        all_diagnostics = (
            list(all_diagnostics)
            + list(view_diagnostics)
            + coverage_diagnostics
        )
        self._annotate_editable_diagnostics_for_snapshot_contract(
            all_diagnostics
        )
        intermediate["suppressed_stage_local_diagnostics"] = (
            consolidation.suppressed_stage_local_diagnostics
        )
        if consolidation.warnings:
            intermediate["diagnostic_consolidation_warnings"] = (
                consolidation.warnings
            )
        completeness = compute_completeness(
            validation_errors=errors,
            diagnostics=all_diagnostics,
        )
        assumption_builder = AssumptionBuilder()
        assumptions = assumption_builder.build(all_diagnostics)
        readable_report = ""

        # S4: Snapshot persistence
        snapshot_path = None
        snapshot_status = "not_requested"
        snapshot_error: str | None = None
        explanation_status = "not_requested"
        explanation_error: str | None = None

        snap_config = getattr(self.config, "snapshot", None)
        if snap_config is not None and getattr(snap_config, "enabled", False):
            try:
                snapshot_path = self._persist_snapshot(
                    compile_run_id=self.config.run_name or "unknown",
                    output_dir=self.config.run_dir,
                    spl_text=spl_text,
                    final_spl_path=final_spl_path,
                    intermediate=intermediate,
                    all_diagnostics=all_diagnostics,
                    traces=traces,
                )
                snapshot_status = "available"
            except Exception as exc:
                snapshot_error = str(exc)
                mode = getattr(snap_config, "mode", None)
                if mode is not None and getattr(mode, "value", "") == "required":
                    snapshot_status = "failed_required"
                else:
                    snapshot_status = "failed_best_effort"

        if (
            snapshot_path is not None
            and snapshot_status == "available"
            and getattr(snap_config, "precompute_issue_explanations", True)
        ):
            try:
                from nl2spl.compiler.spl_editing.presentation.explanation_cache import (
                    schedule_issue_explanations_for_pipeline,
                )

                future = schedule_issue_explanations_for_pipeline(
                    snapshot_path,
                    self.client,
                    language=getattr(
                        snap_config,
                        "issue_explanation_language",
                        "zh-CN",
                    ),
                    max_workers=getattr(
                        snap_config,
                        "issue_explanation_max_workers",
                        4,
                    ),
                )
                self._issue_explanation_futures[snapshot_path] = future
                explanation_status = "scheduled"
            except Exception as exc:
                explanation_status = "schedule_failed"
                explanation_error = str(exc)

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
            spl_editing_snapshot_path=snapshot_path,
            spl_editing_snapshot_status=snapshot_status,
            spl_editing_snapshot_error=snapshot_error,
            spl_editing_explanation_status=explanation_status,
            spl_editing_explanation_error=explanation_error,
        )

    # ------------------------------------------------------------------
    # S4: Snapshot persistence
    # ------------------------------------------------------------------

    def _persist_snapshot(
        self,
        *,
        compile_run_id: str,
        output_dir: Path,
        spl_text: str,
        final_spl_path: Path | None,
        intermediate: dict[str, Any],
        all_diagnostics: list[Any],
        traces: list[Any],
    ) -> Path | None:
        """Build and persist a snapshot document if configured.

        Returns the written file path on success, or None if disabled.
        Raises on failure (caller decides best-effort vs required).
        """
        from nl2spl.compiler.artifacts.snapshot.build.builder import SnapshotBuilder
        from nl2spl.compiler.artifacts.snapshot.build.input import SnapshotBuildInput
        from nl2spl.compiler.artifacts.snapshot.capabilities import (
            SPL_EDITING_USER_FACING_DIAGNOSTIC_KINDS,
        )
        from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
            JsonFileSnapshotRepository,
        )

        snap_config = self.config.snapshot

        # Map pipeline intermediate keys to SnapshotBuildInput fields.
        # Keys match what the orchestrator writes into intermediate dict.

        # stage9_5_normalization is a tuple:
        #   (worker_flow_plan, worker_block_plan, worker_step_plan,
        #    symbol_table, errors, warnings)
        norm_result = intermediate.get("stage9_5_normalization")
        norm_flow = None
        norm_block = None
        norm_step = None
        norm_symbols = None
        if isinstance(norm_result, (list, tuple)) and len(norm_result) >= 4:
            norm_flow, norm_block, norm_step, norm_symbols = norm_result[:4]

        # Construct stage10_input as a dict of artifacts fed to WorkerAssembler
        stage10_raw = intermediate.get("stage10_input")
        if stage10_raw is None:
            stage10_raw = {
                "worker_step_plan": intermediate.get("stage7_worker_step_plan"),
                "resources": intermediate.get("stage6_resources"),
                "symbol_table": intermediate.get("symbol_table") or norm_symbols,
                "worker_plan": intermediate.get("stage3_5_worker_plan"),
                "worker_flow_plan": intermediate.get("stage4_worker_flows"),
                "worker_block_plan": intermediate.get("stage5_worker_blocks"),
            }

        build_input = SnapshotBuildInput(
            compile_run_id=compile_run_id,
            output_dir=output_dir,
            source_spans=tuple(intermediate.get("stage1_spans", ())),
            source_routes=intermediate.get("stage2_routes"),
            construct_plan=intermediate.get("construct_plan"),
            canonical_input=intermediate.get("canonical_input"),
            worker_plan=intermediate.get("stage3_5_worker_plan"),
            worker_flow_plan=intermediate.get("stage4_worker_flows"),
            worker_block_plan=intermediate.get("stage5_worker_blocks"),
            worker_step_plan=intermediate.get("stage7_worker_step_plan"),
            resources=intermediate.get("stage6_resources"),
            worker_scoped_resources=intermediate.get("stage6_worker_scoped_resources"),
            symbol_table=intermediate.get("symbol_table") or norm_symbols,
            constraints=tuple(intermediate.get("stage9_constraints", ())),
            agent_profile=intermediate.get("stage8_profile"),
            final_worker=intermediate.get("stage10_worker"),
            pre_gate_worker=intermediate.get("stage10_worker"),
            final_spl_text=spl_text,
            compile_diagnostics=tuple(
                diag for diag in all_diagnostics
                if (
                    getattr(diag, "kind", "")
                    in SPL_EDITING_USER_FACING_DIAGNOSTIC_KINDS
                    and isinstance(getattr(diag, "metadata", {}).get("repairability"), str)
                )
            ),
            traces=tuple(traces),
            normalizer_input={
                "worker_flow_plan": intermediate.get("stage4_worker_flows"),
                "worker_block_plan": intermediate.get("stage5_worker_blocks"),
                "worker_step_plan": intermediate.get("stage7_worker_step_plan"),
                "worker_plan": intermediate.get("stage3_5_worker_plan"),
                "resources": intermediate.get("stage6_resources"),
                "symbol_table": intermediate.get("symbol_table"),
            },
            normalizer_output={
                "worker_flow_plan": norm_flow,
                "worker_block_plan": norm_block,
                "worker_step_plan": norm_step,
                "symbol_table": norm_symbols,
            } if norm_flow is not None else None,
            stage10_input=stage10_raw,
            config=snap_config,
        )

        builder = SnapshotBuilder()
        document = builder.build(build_input)

        # Enforce required_capabilities via S2 validation
        required_caps = getattr(snap_config, "required_capabilities", ())
        if required_caps:
            from nl2spl.compiler.artifacts.snapshot.validation.validator import (
                SnapshotValidator,
            )

            validator = SnapshotValidator()
            result = validator.validate(document)
            missing = [
                c for c in required_caps
                if not result.effective_capabilities.has(c)
            ]
            if missing:
                names = ", ".join(c.value for c in missing)
                raise ValueError(
                    f"Required capabilities not effective: {names}"
                )

        repo = JsonFileSnapshotRepository()
        filename = getattr(snap_config, "filename", "spl_editing_snapshot.json")
        path = output_dir / filename
        repo.save(document, path)
        return path

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
        resource_contract_plan: Any = None,
        demand_view: Any = None,
        external_capability_intent_plan: Any = None,
    ) -> WorkerPlanIR:
        """Stage 3.5: Worker Boundary Planning."""
        stage = WorkerBoundaryPlanner(self.config, self.client)
        if demand_view is not None:
            return stage.execute(
                (
                    spans,
                    routes,
                    canonical_input,
                    demand_view,
                    external_capability_intent_plan,
                )
            )
        if resource_contract_plan is not None:
            return stage.execute(
                (
                    spans,
                    routes,
                    canonical_input,
                    resource_contract_plan,
                    external_capability_intent_plan,
                )
            )
        return stage.execute((spans, routes, canonical_input))

    def _run_stage4(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_plan: WorkerPlanIR | None = None,
        construct_plan: ConstructPlan | None = None,
    ) -> FlowStructureIR | WorkerFlowPlanIR:
        """Stage 4: Flow Assembly."""
        stage = FlowAssembler(self.config, self.client)
        if worker_plan is not None and construct_plan is not None:
            return stage.execute((spans, routes, worker_plan, construct_plan))
        if worker_plan is not None:
            return stage.execute((spans, routes, worker_plan))
        return stage.execute((spans, routes))

    def _run_stage5(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        flow_structure: FlowStructureIR | WorkerFlowPlanIR,
        construct_plan: ConstructPlan | None = None,
    ) -> BlockStructureIR | WorkerBlockPlanIR:
        """Stage 5: Block Assembly."""
        stage = BlockAssembler(self.config, self.client)
        if construct_plan is not None:
            return stage.execute((spans, routes, flow_structure, construct_plan))
        return stage.execute((spans, routes, flow_structure))

    def _run_stage6_worker_scoped(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        worker_plan: WorkerPlanIR,
        canonical_input: CanonicalCompileInput | None = None,
        resource_contract_plan: Any = None,
        demand_view: Any = None,
    ) -> tuple[WorkerScopedResourceIR, SymbolTable, list[str]]:
        """Stage 6: Worker-scoped Resource Extraction."""
        stage = ResourceExtractor(self.config, self.client)
        worker_scoped_resources, symbols = stage.execute_worker_scoped(
            spans, routes, worker_flow_plan, worker_block_plan, worker_plan,
            canonical_input, resource_contract_plan, demand_view=demand_view,
        )
        filter_warnings = getattr(stage, "resource_filter_warnings", [])
        return worker_scoped_resources, symbols, list(filter_warnings)

    def _run_stage7_worker_scoped(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        symbol_table: SymbolTable,
        worker_plan: WorkerPlanIR,
        construct_plan: ConstructPlan | None = None,
        api_materialization_plan: Any | None = None,
        api_call_placements: list[Any] | None = None,
        resources: ResourceRegistryIR | None = None,
    ) -> tuple[WorkerStepPlanIR, SymbolTable, list[Any]]:
        """Stage 7: Worker-scoped Step Extraction."""
        stage = StepExtractor(self.config, self.client)
        result = stage.execute_worker_scoped(
            spans, routes, worker_flow_plan, worker_block_plan, symbol_table,
            worker_plan, construct_plan, api_materialization_plan,
            api_call_placements, resources,
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
        return result

    @staticmethod
    def _promoted_irs_diagnostics(
        irs_store: IRSResultStore,
    ) -> list[CompileDiagnostic]:
        """Return stage-local IRS diagnostics allowed into final output.

        R10 Phase 4: promotion based on construct target + delegation
        source-signal provenance, not on delegation_intent:* target_ref.
        """
        _PROMOTABLE_PREFIXES = (  # noqa: N806
            "worker_promotion:",
            "worker_handoff:",
            "child_worker:",
            "invoke_worker:",
            "call_api:",
        )

        def _is_delegation_sourced_actionable(d: CompileDiagnostic) -> bool:
            return (
                d.kind == "type_or_contract_ambiguity"
                and d.target_ref is not None
                and d.target_ref.startswith(_PROMOTABLE_PREFIXES)
                and bool(d.source_span_ids)
                and d.metadata.get("original_semantic_role")
                == "delegation_intent"
            )

        promoted = [
            d
            for d in irs_store.get_stage_diagnostics("stage3_5")
            if _is_delegation_sourced_actionable(d)
        ]
        PipelineOrchestrator._annotate_promoted_irs_diagnostics(promoted)
        return promoted

    @staticmethod
    def _annotate_promoted_irs_diagnostics(
        diagnostics: list[CompileDiagnostic],
    ) -> None:
        """Annotate promoted IRS diagnostics with SPL Editing issue metadata.

        This keeps the compiler pipeline independent from ``spl_editing`` while
        still making promoted compiler diagnostics satisfy the snapshot
        diagnostic contract.
        """
        if not diagnostics:
            return

        authority = "selected_promoted_stage_local_irs"
        for diagnostic in diagnostics:
            diagnostic.metadata[METADATA_KEY_AUTHORITY] = authority
            irs_ref = diagnostic.metadata.get("irs_ref")
            if isinstance(irs_ref, dict):
                irs_ref["source_authority"] = authority

        groups: dict[str, list[CompileDiagnostic]] = {}
        for diagnostic in diagnostics:
            key = diagnostic.target_ref or diagnostic.diagnostic_id
            groups.setdefault(key, []).append(diagnostic)

        slot_order = {
            "promotion_input_contract": 0,
            "promotion_output_contract": 1,
            "promotion_invocation_point": 2,
            "promotion_result_handoff": 3,
        }
        for target_ref, group in groups.items():
            ordered = sorted(
                group,
                key=lambda d: (
                    slot_order.get(
                        d.missing_slot.slot_name if d.missing_slot else "",
                        99,
                    ),
                    d.diagnostic_id,
                ),
            )
            primary = ordered[0]
            related_ids = sorted(d.diagnostic_id for d in ordered)
            group_id = f"worker_promotion_group:{target_ref}"
            for diagnostic in ordered:
                diagnostic.metadata[METADATA_KEY_ISSUE_GROUP_ID] = group_id
                diagnostic.metadata[METADATA_KEY_PRIMARY_DIAGNOSTIC_ID] = (
                    primary.diagnostic_id
                )
                diagnostic.metadata[METADATA_KEY_RELATED_DIAGNOSTIC_IDS] = list(
                    related_ids
                )
                diagnostic.metadata[METADATA_KEY_REPAIRABILITY] = "editable"
                diagnostic.metadata[METADATA_KEY_ISSUE_ROLE] = (
                    "primary"
                    if diagnostic.diagnostic_id == primary.diagnostic_id
                    else "alias"
                )

    @staticmethod
    def _annotate_editable_diagnostics_for_snapshot_contract(
        diagnostics: list[CompileDiagnostic],
    ) -> None:
        """Fill required issue metadata for compiler-exposed user issues.

        Snapshot validation requires compiler-exposed diagnostics to carry
        grouping and repairability metadata for deterministic SPL Editing issue
        extraction.  Editability is capability-aware: a diagnostic becomes
        ``editable`` only when its IRS slot declares a repair affordance.  API
        placeholder diagnostics remain review-only deferred validation items.
        """
        registry = SPLConstructRegistry.default()
        groups: dict[tuple[str, str], list[CompileDiagnostic]] = {}
        for diagnostic in diagnostics:
            repairability = PipelineOrchestrator._issue_repairability_for_diagnostic(
                diagnostic,
                registry,
            )
            if repairability is None:
                continue
            key = PipelineOrchestrator._editable_issue_group_key(diagnostic)
            groups.setdefault((repairability, key), []).append(diagnostic)

        for (repairability, key), group in groups.items():
            ordered = sorted(
                group,
                key=PipelineOrchestrator._issue_group_sort_key,
            )
            primary = ordered[0]
            related_ids = sorted(
                diagnostic.diagnostic_id for diagnostic in ordered
            )
            group_id = (
                primary.metadata.get(METADATA_KEY_ISSUE_GROUP_ID)
                if isinstance(
                    primary.metadata.get(METADATA_KEY_ISSUE_GROUP_ID), str
                )
                else f"{repairability}_group:{key}"
            )
            for diagnostic in ordered:
                diagnostic.metadata[METADATA_KEY_REPAIRABILITY] = repairability
                diagnostic.metadata.setdefault(
                    METADATA_KEY_ISSUE_GROUP_ID, group_id
                )
                diagnostic.metadata.setdefault(
                    METADATA_KEY_PRIMARY_DIAGNOSTIC_ID,
                    primary.diagnostic_id,
                )
                diagnostic.metadata.setdefault(
                    METADATA_KEY_RELATED_DIAGNOSTIC_IDS,
                    list(related_ids),
                )
                diagnostic.metadata.setdefault(
                    METADATA_KEY_ISSUE_ROLE,
                    (
                        "primary"
                        if diagnostic.diagnostic_id == primary.diagnostic_id
                        else "alias"
                    ),
                )

    @staticmethod
    def _issue_repairability_for_diagnostic(
        diagnostic: CompileDiagnostic,
        registry: SPLConstructRegistry,
    ) -> str | None:
        metadata_repairability = diagnostic.metadata.get(METADATA_KEY_REPAIRABILITY)
        if metadata_repairability in {"review_only", "non_repairable", "developer_only"}:
            return str(metadata_repairability)
        if (
            diagnostic.kind == "deferred_api_contract_validation"
            or diagnostic.metadata.get(METADATA_KEY_PRESENTATION_DISPOSITION)
            == "deferred_validation"
        ):
            return "review_only"
        if PipelineOrchestrator._diagnostic_has_repair_affordance(diagnostic, registry):
            return "editable"
        return None

    @staticmethod
    def _diagnostic_has_repair_affordance(
        diagnostic: CompileDiagnostic,
        registry: SPLConstructRegistry,
    ) -> bool:
        irs_ref = diagnostic.metadata.get(METADATA_KEY_IRS_REF)
        if not isinstance(irs_ref, dict):
            return False
        construct_type = irs_ref.get("construct_type")
        slot_name = irs_ref.get("slot_name")
        if not isinstance(construct_type, str) or not isinstance(slot_name, str):
            return False
        if not registry.has(construct_type):
            return False
        slot = registry.get(construct_type).get_slot(slot_name)
        if slot is None:
            return False
        return bool(slot.repair_affordances)

    @staticmethod
    def _issue_group_sort_key(diagnostic: CompileDiagnostic) -> tuple[int, str]:
        slot_order = {
            "functions": 0,
            "openapi_schema": 1,
            "authentication": 2,
        }
        slot_name = diagnostic.missing_slot.slot_name if diagnostic.missing_slot else ""
        return (slot_order.get(slot_name, 99), diagnostic.diagnostic_id)

    @staticmethod
    def _editable_issue_group_key(diagnostic: CompileDiagnostic) -> str:
        if diagnostic.target_ref:
            return diagnostic.target_ref
        irs_ref = diagnostic.metadata.get("irs_ref")
        if isinstance(irs_ref, dict):
            construct_id = irs_ref.get("construct_id")
            if isinstance(construct_id, str) and construct_id:
                return construct_id
        return diagnostic.diagnostic_id

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

    def _make_semantic_conflict_analyzer(self) -> NoOpSemanticConflictAnalyzer:
        """Return the active semantic conflict analyzer."""
        return NoOpSemanticConflictAnalyzer()

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
