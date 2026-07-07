"""Stage 7: StepExtractor - Extract atomic actions from spans."""

from __future__ import annotations

import json
from dataclasses import asdict

from nl2spl.compiler.construct_plan import ConstructPlan
from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerPlanIR
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage
from nl2spl.pipeline.stages.stage7_step_extractor.legacy import LegacyMethodsMixin
from nl2spl.pipeline.stages.stage7_step_extractor.worker_scoped import WorkerScopedMethodsMixin


class StepExtractor(
    LegacyMethodsMixin,
    WorkerScopedMethodsMixin,
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable]
        | tuple[
            list[SpanIR],
            FieldRouteIR,
            FlowStructureIR,
            BlockStructureIR,
            SymbolTable,
            WorkerPlanIR,
            ConstructPlan,
        ],
        tuple[list[StepIR], SymbolTable],
    ],
):
    """Extract atomic actions (steps) from behavior spans.

    This stage takes behavior spans, field routes, flow structure,
    block structure, and symbol table, then extracts steps with
    their input/output variables.
    """

    def __init__(self, config: any, client: any) -> None:
        super().__init__(config, client)
        self.last_action_plan = None

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage7_step_extractor"

    def execute(
        self,
        input_data: tuple[
            list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable
        ]
        | tuple[
            list[SpanIR],
            FieldRouteIR,
            FlowStructureIR,
            BlockStructureIR,
            SymbolTable,
            WorkerPlanIR,
        ],
    ) -> tuple[list[StepIR], SymbolTable]:
        """Execute step extraction.

        Args:
            input_data: Tuple of (spans, field routes, flow structure,
                       block structure, symbol table)

        Returns:
            Tuple of (list of StepIR, updated SymbolTable)

        Raises:
            StageError: If step extraction fails
        """
        worker_plan = input_data[5] if len(input_data) >= 6 else None
        construct_plan = input_data[6] if len(input_data) == 7 else None
        spans, routes, flow_structure, block_structure, symbol_table = input_data[:5]
        self.logger.info(
            "Starting step extraction with %d spans and %d known variables",
            len(spans),
            len(symbol_table.variables),
        )

        # 1. Build prompts with variable list
        non_exec_span_ids: set[str] = set()
        if routes.annotations:
            behavior_span_ids = routes.get_executable_behavior_span_ids()
            non_exec_span_ids = set(routes.get_non_executable_behavior_span_ids())
        else:
            behavior_span_ids = list(routes.behavior)
        if construct_plan is not None:
            reserved = construct_plan.reserved_without_dual_role()
            behavior_span_ids = [
                span_id for span_id in behavior_span_ids
                if span_id not in reserved
            ]
        if worker_plan is not None:
            self._assert_legacy_main_view_excludes_child_spans(
                flow_structure,
                worker_plan,
            )
            main_view_span_ids = flow_structure.get_all_flow_spans()
            if main_view_span_ids:
                behavior_span_ids = [
                    span_id for span_id in behavior_span_ids if span_id in main_view_span_ids
                ]
        behavior_spans = [s for s in spans if s.span_id in set(behavior_span_ids)]
        behavior_json = json.dumps(
            [s.to_dict() for s in behavior_spans], ensure_ascii=False
        )
        prompt_flow_structure = self._flow_for_step_prompt(flow_structure, worker_plan)
        flow_json = json.dumps(asdict(prompt_flow_structure), ensure_ascii=False)
        blocks_json = json.dumps(asdict(block_structure), ensure_ascii=False)
        variable_list = symbol_table.get_variable_list_for_prompt()

        system_prompt = load_prompt("stage7").replace(
            "{variable_list}", variable_list
        )

        non_exec_context = ""
        if non_exec_span_ids:
            non_exec_spans = [s for s in spans if s.span_id in non_exec_span_ids]
            non_exec_json = json.dumps(
                [s.to_dict() for s in non_exec_spans], ensure_ascii=False
            )
            non_exec_context = (
                "Non-executable context only (failure conditions, "
                "delegation boundaries — do NOT create COMMAND, REQUEST_INPUT, "
                "INVOKE_WORKER, or CALL_API from these spans):\n"
                f"---\n{non_exec_json}\n---\n\n"
            )

        user_prompt = f"""Extract steps from the following text:

behavior spans:
---
{behavior_json}
---

{non_exec_context}Flow structure:
---
{flow_json}
---

Block structure:
---
{blocks_json}
---

Known variables:
---
{variable_list}
---

Output JSON:"""

        # 2. Call LLM
        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed: %s", e)
            raise StageError(
                message=f"LLM call failed in {self.name}: {e}",
                stage=self.name,
            ) from e

        self.stage7_diagnostics: list[CompileDiagnostic] = []

        # 3. Parse steps (just parse, don't update symbol table yet)
        steps: list[StepIR] = []
        for step_data in result.get("steps", []):
            try:
                step = StepIR(
                    step_id=step_data["step_id"],
                    text=step_data["text"],
                    source_span_ids=step_data["source_span_ids"],
                    command_type=step_data["command_type"],
                    inputs=step_data.get("inputs", []),
                    outputs=step_data.get("outputs", []),
                    integration_ref=step_data.get("integration_ref"),
                    flow_ref=step_data.get("flow_ref", "main"),
                    block_ref=step_data.get("block_ref", ""),
                    kind=step_data.get("kind", "normal"),
                    handoff_id=step_data.get("handoff_id"),
                )
                steps.append(step)
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid step: %s", e)
                continue

        # Stage 7 fail-closed: guard-only residual step detection (Phase F)
        steps = self._filter_guard_only_residual_steps(steps)

        self._validate_step_type_contracts(steps)

        # 3.5 D6 guard: drop steps sourced only from non-executable spans
        if non_exec_span_ids:
            kept_steps: list[StepIR] = []
            for step in steps:
                source_ids = set(step.source_span_ids)
                if source_ids and source_ids.issubset(non_exec_span_ids):
                    self.stage7_diagnostics.append(
                        CompileDiagnostic(
                            diagnostic_id=f"diag_s7_{len(self.stage7_diagnostics):04d}",
                            kind="non_executable_route_material_excluded",
                            severity="warning",
                            message=(
                                f"Step '{step.step_id}' ({step.text[:80]}) "
                                f"dropped: all source spans {sorted(source_ids)} "
                                f"are non-executable route material."
                            ),
                            target_ref=f"step:{step.step_id}",
                            source_span_ids=list(source_ids),
                            blocks_rendering=False,
                            blocks_completion=False,
                        )
                    )
                    self.logger.info(
                        "D6 guard: dropped non-executable step %s (%s)",
                        step.step_id, step.text[:60],
                    )
                    continue
                kept_steps.append(step)
            steps = kept_steps

        # 4. Handle new_variables (declare before updating producers/consumers)
        for new_var_data in result.get("new_variables", []):
            try:
                new_var_name = new_var_data["name"]
                if new_var_name not in symbol_table.variables:
                    symbol_table.declare(
                        name=new_var_name,
                        data_type=new_var_data.get("data_type", "text"),
                        source="step",
                        description=new_var_data.get("description", ""),
                    )
                    symbol_table.variables[new_var_name].declared = False
            except (KeyError, TypeError) as e:
                self.logger.warning("Skipping invalid new variable: %s", e)

        # 5. Apply worker plan handoffs if worker_plan is present
        if worker_plan is not None:
            steps = self._apply_worker_plan_handoffs(
                steps, worker_plan, flow_structure, block_structure, symbol_table
            )

        # Update producers/consumers
        for step in steps:
            for var_name in step.inputs:
                symbol_table.add_consumer(var_name, step.step_id)
            for var_name in step.outputs:
                symbol_table.add_producer(var_name, step.step_id)

        # 5.5 Detect unmapped behavior spans — run AFTER handoff materialization
        # so source-backed INVOKE_WORKER / CALL_API steps count as coverage.
        covered_span_ids = {
            span_id
            for step in steps
            for span_id in step.source_span_ids
        }
        llm_unmapped: dict[str, str] = {}
        for item in (result.get("unmapped_spans") or []):
            if not isinstance(item, dict):
                self.logger.warning("Skipping non-dict unmapped_span item: %s", item)
                continue
            span_id = item.get("span_id")
            if span_id:
                llm_unmapped[span_id] = item.get("reason", "No reason given")
        for span_id in behavior_span_ids:
            if span_id in covered_span_ids:
                continue
            if span_id in non_exec_span_ids:
                continue  # D6: non-executable spans are not expected to map to steps
            reason = llm_unmapped.get(span_id, "Behavior span not mapped to any step")
            span_text = next(
                (s.text for s in behavior_spans if s.span_id == span_id), span_id
            )
            self.stage7_diagnostics.append(
                CompileDiagnostic(
                    diagnostic_id=f"diag_s7_{len(self.stage7_diagnostics):04d}",
                    kind="unmapped_behavior_span",
                    severity="warning",
                    message=(
                        f"Behavior span '{span_id}' ({span_text[:80]}) "
                        f"was not mapped to a step: {reason}"
                    ),
                    target_ref=f"span:{span_id}",
                    source_span_ids=[span_id],
                    blocks_rendering=False,
                    blocks_completion=True,
                )
            )

        self.logger.info(
            "Extracted %d steps, %d new variables",
            len(steps),
            len(result.get("new_variables", [])),
        )

        # 6. Save checkpoint
        self.save_checkpoint({
            "steps": [asdict(s) for s in steps],
            "new_variables": result.get("new_variables", []),
        })

        return steps, symbol_table

    def _validate_step_type_contracts(
        self,
        steps: list[StepIR],
        worker_id: str | None = None,
    ) -> None:
        """Fail fast when LLM output violates command-type contracts."""
        display_with_outputs = [
            step for step in steps
            if step.command_type == "DISPLAY_MESSAGE" and step.outputs
        ]
        if not display_with_outputs:
            return

        details = [
            f"{step.step_id}:outputs={list(step.outputs)}"
            for step in display_with_outputs
        ]
        worker_context = f" for worker {worker_id}" if worker_id else ""
        raise StageError(
            message=(
                f"LLM emitted DISPLAY_MESSAGE step(s) with outputs{worker_context}: "
                f"{details}. DISPLAY_MESSAGE may read inputs but must not declare "
                "outputs; use GENERAL_COMMAND for steps that produce or update data."
            ),
            stage=self.name,
        )

    def _filter_guard_only_residual_steps(self, steps: list[StepIR]) -> list[StepIR]:
        guard_words = {
            "when",
            "if",
            "unless",
            "once",
            "as long as",
            "provided that",
            "in case",
            "on condition that",
        }
        filtered_steps = []
        for step in steps:
            text_clean = step.text.strip()
            text_lower = text_clean.lower()
            starts_with_guard = False
            for gw in guard_words:
                if text_lower.startswith(gw + " ") or text_lower == gw:
                    starts_with_guard = True
                    break
            if starts_with_guard:
                has_separator = "," in text_clean or " then " in text_lower
                if not has_separator:
                    msg = (
                        f"Guard-only residual step detected: '{text_clean}'. "
                        "Action clause is missing."
                    )
                    self.logger.warning(msg)
                    diag = CompileDiagnostic(
                        diagnostic_id=(
                            f"diag_s7_guard_residual_not_materialized_{step.step_id}"
                        ),
                        kind="stage7_guard_residual_not_materialized",
                        severity="warning",
                        message=msg,
                        target_ref=f"step:{step.step_id}",
                        source_span_ids=step.source_span_ids,
                        blocks_rendering=False,
                        blocks_completion=True,
                    )
                    self.stage7_diagnostics.append(diag)
                    continue
            filtered_steps.append(step)
        return filtered_steps
