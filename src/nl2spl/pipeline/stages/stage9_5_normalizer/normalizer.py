"""Stage 9.5: IRNormalizer - Normalize and validate IRs."""

from __future__ import annotations

import re

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.flow_structure_ir import DelegationCandidate, FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, TypeSpec, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.stages.stage9_5_normalizer.flow_classification import FlowClassificationMixin
from nl2spl.pipeline.stages.stage9_5_normalizer.helpers import HelpersMixin
from nl2spl.pipeline.stages.stage9_5_normalizer.normalization import NormalizationMixin
from nl2spl.pipeline.stages.stage9_5_normalizer.validation import ValidationMixin
from nl2spl.pipeline.stages.stage9_5_normalizer.worker_handoffs import WorkerHandoffsMixin
from nl2spl.pipeline.stages.stage9_5_normalizer.worker_scoped import WorkerScopedMixin
from nl2spl.pipeline.worker_plan_validator import WorkerPlanValidator


class IRNormalizer(
    FlowClassificationMixin,
    HelpersMixin,
    NormalizationMixin,
    ValidationMixin,
    WorkerHandoffsMixin,
    WorkerScopedMixin,
):
    """IR Normalization and validation.

    This stage normalizes all IRs and validates consistency across
    steps, constraints, and resources.
    """

    def normalize(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
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
        """Normalize all IRs and validate consistency.

        Args:
            flow: Flow structure IR
            blocks: Block structure IR
            resources: Resource registry IR
            symbol_table: Symbol table
            steps: List of step IRs
            constraints: List of constraint IRs

        Returns:
            Tuple of (flow, blocks, steps, constraints, symbol_table, errors, warnings)
        """
        errors: list[str] = []
        warnings: list[str] = []
        self._step_replacements: dict[str, str] = {}

        # 1. Move ordinary conditional work out of exception flows.
        flow, blocks, moved_warnings = self._normalize_flow_classification(flow, blocks)
        warnings.extend(moved_warnings)

        # 2. Reconcile step flow_ref/block_ref before validations that depend on path.
        steps = self._reconcile_steps(steps, flow, blocks)
        self._sync_symbol_table_from_steps(steps, symbol_table)

        # 3. Materialize child worker invocations.
        if worker_plan is not None:
            worker_validation = WorkerPlanValidator().validate(worker_plan)
            errors.extend(worker_validation.errors)
            warnings.extend(worker_validation.warnings)
            warnings.extend(
                self._materialize_worker_plan_handoffs(
                    worker_plan,
                    flow,
                    blocks,
                    symbol_table,
                    steps,
                )
            )
        else:
            warnings.extend(
                self._materialize_child_worker_invocations(flow, blocks, symbol_table, steps)
            )
        blocks.main_flow_blocks.sort(key=self._block_sort_key)
        blocks.main_flow_blocks = self._deduplicate_blocks(blocks.main_flow_blocks)
        steps = self._reconcile_steps(steps, flow, blocks)
        self._sync_symbol_table_from_steps(steps, symbol_table)

        # 4. Normalize obvious dataflow gaps and resolve delegation targets.
        warnings.extend(self._normalize_source_retrieval_inputs(steps, symbol_table))
        errors.extend(self._resolve_worker_invocations(flow, steps, warnings, worker_plan))
        warnings.extend(
            self._normalize_multi_output_steps(resources, symbol_table, steps)
        )
        warnings.extend(self._ensure_required_main_outputs(blocks, resources, symbol_table, steps))

        # 5. Reconcile again for any synthetic steps.
        steps = self._reconcile_steps(steps, flow, blocks)
        self._sync_symbol_table_from_steps(steps, symbol_table)
        warnings.extend(self._prune_unused_step_variables(resources, symbol_table, steps))

        # 6. Reconcile constraint targets before reference validation.
        constraints = self._reconcile_constraints(constraints, steps, blocks)

        # 7. Validate references
        errors.extend(self._validate_references(steps, constraints, symbol_table, resources))

        if worker_plan is not None:
            errors.extend(
                self._validate_worker_plan_handoffs(
                    worker_plan,
                    steps,
                    resources,
                    symbol_table,
                )
            )

        # 8. Validate coverage
        warnings.extend(self._validate_coverage(flow, steps))

        # 9. Validate path consistency
        warnings.extend(self._validate_path_dataflow(steps, resources))

        # 10. Update SymbolTable with new_variables
        # (already done in Stage 7)

        return flow, blocks, steps, constraints, symbol_table, errors, warnings
