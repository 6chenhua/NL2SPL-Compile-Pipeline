"""Pipeline orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nl2spl.adapters import InputAdapterRegistry
from nl2spl.canonical import CanonicalCompileInput, CanonicalCompileInputValidator
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
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner import WorkerBoundaryPlanner
from nl2spl.pipeline.stages.stage3_ambiguity_resolver import AmbiguityResolver
from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler
from nl2spl.pipeline.stages.stage5_block_assembler import BlockAssembler
from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor
from nl2spl.pipeline.stages.stage8_profile_extractor import ProfileExtractor
from nl2spl.pipeline.stages.stage9_5_normalizer import IRNormalizer
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
        intermediate_results: Intermediate stage results
        final_spl_path: Path to saved final SPL file
    """

    spl_text: str
    validation_errors: list[str]
    validation_warnings: list[str]
    intermediate_results: dict[str, Any]
    final_spl_path: Path | None = None


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

        intermediate: dict[str, Any] = {}
        worker_stage_warnings: list[str] = []

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

            # 防御性修复：确保所有 span 都被分配给至少一个 worker。
            # Stage 3.5 LLM 偶尔会漏掉 behavior span（observed: s18-s24, s37）。
            all_span_ids = {span.span_id for span in resolved_spans}
            assigned_ids: set[str] = set()
            for w in worker_plan.workers:
                assigned_ids.update(w.owned_span_ids)
            unassigned = all_span_ids - assigned_ids
            if unassigned:
                main_worker = worker_plan.main_worker
                main_worker.owned_span_ids.extend(sorted(unassigned, key=lambda sid: int(sid[1:])))
                self.logger.warning(
                    "Stage 3.5 left %d spans unassigned; reassigning to main worker %s: %s",
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
            worker_scoped_resources, symbol_table = self._run_stage6_worker_scoped(
                resolved_spans,
                resolved_routes,
                worker_flow_plan,
                worker_block_plan,
                worker_plan,
                canonical_input,
            )
            resources = worker_scoped_resources.global_resources
            intermediate["stage6_worker_scoped_resources"] = worker_scoped_resources
        else:
            # Legacy path
            resources, symbol_table = self._run_stage6(
                resolved_spans,
                resolved_routes,
                flow_structure,
                block_structure,
                canonical_input,
            )
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
            worker_step_plan, symbol_table = self._run_stage7_worker_scoped(
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
            steps, symbol_table = self._run_stage7(
                resolved_spans,
                resolved_routes,
                flow_structure,
                block_structure,
                symbol_table,
                worker_plan,
            )
        intermediate["stage7_steps"] = steps

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

        # Stage 11: SPL Rendering
        self.logger.info("Stage 11: SPL Rendering")
        spl_text, errors, warnings = self._run_stage11(
            worker, profile, resources, symbol_table, steps, constraints
        )
        errors = normalization_errors + errors
        warnings = adapter_warnings + worker_stage_warnings + normalization_warnings + warnings
        intermediate["stage11_spl"] = spl_text
        final_spl_path = save_final_spl(
            spl_text=spl_text,
            output_dir=self.config.run_dir,
            filename=self.config.final_spl_filename,
        )

        self.logger.info("Pipeline complete. SPL length: %d chars", len(spl_text))

        return PipelineResult(
            spl_text=spl_text,
            validation_errors=errors,
            validation_warnings=warnings,
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
    ) -> tuple[ResourceRegistryIR, SymbolTable]:
        """Stage 6: Resource Extraction."""
        stage = ResourceExtractor(self.config, self.client)
        if canonical_input is not None:
            return stage.execute((spans, routes, flow, blocks, canonical_input))
        return stage.execute((spans, routes, flow, blocks))

    def _run_stage6_worker_scoped(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        worker_plan: WorkerPlanIR,
        canonical_input: CanonicalCompileInput | None = None,
    ) -> tuple[WorkerScopedResourceIR, SymbolTable]:
        """Stage 6: Worker-scoped Resource Extraction."""
        stage = ResourceExtractor(self.config, self.client)
        return stage.execute_worker_scoped(
            spans, routes, worker_flow_plan, worker_block_plan, worker_plan, canonical_input
        )

    def _run_stage7(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        symbols: SymbolTable,
        worker_plan: WorkerPlanIR | None = None,
    ) -> tuple[list[StepIR], SymbolTable]:
        """Stage 7: Step Extraction."""
        stage = StepExtractor(self.config, self.client)
        if worker_plan is not None:
            return stage.execute((spans, routes, flow, blocks, symbols, worker_plan))
        return stage.execute((spans, routes, flow, blocks, symbols))

    def _run_stage7_worker_scoped(
        self,
        spans: list[SpanIR],
        routes: FieldRouteIR,
        worker_flow_plan: WorkerFlowPlanIR,
        worker_block_plan: WorkerBlockPlanIR,
        symbol_table: SymbolTable,
        worker_plan: WorkerPlanIR,
    ) -> tuple[WorkerStepPlanIR, SymbolTable]:
        """Stage 7: Worker-scoped Step Extraction."""
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        stage = StepExtractor(self.config, self.client)
        return stage.execute_worker_scoped(
            spans, routes, worker_flow_plan, worker_block_plan, symbol_table, worker_plan
        )

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
        return normalizer.normalize(
            flow,
            blocks,
            resources,
            symbols,
            steps,
            constraints,
            worker_plan,
        )

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
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        normalizer = IRNormalizer()
        return normalizer.normalize_worker_scoped(
            worker_flow_plan,
            worker_block_plan,
            worker_step_plan,
            worker_plan,
            resources,
            symbol_table,
        )

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
