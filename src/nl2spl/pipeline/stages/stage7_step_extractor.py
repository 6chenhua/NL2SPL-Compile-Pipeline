"""Stage 7: StepExtractor - Extract atomic actions from spans."""

from __future__ import annotations

import json
from dataclasses import asdict

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


class StepExtractor(
    PipelineStage[
        tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable],
        tuple[list[StepIR], SymbolTable],
    ]
):
    """Extract atomic actions (steps) from behavior spans.

    This stage takes behavior spans, field routes, flow structure,
    block structure, and symbol table, then extracts steps with
    their input/output variables.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage7_step_extractor"

    def execute(
        self,
        input_data: tuple[
            list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable
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
        spans, routes, flow_structure, block_structure, symbol_table = input_data
        self.logger.info(
            "Starting step extraction with %d spans and %d known variables",
            len(spans),
            len(symbol_table.variables),
        )

        # 1. Build prompts with variable list
        behavior_spans = [s for s in spans if s.span_id in routes.behavior]
        behavior_json = json.dumps(
            [asdict(s) for s in behavior_spans], ensure_ascii=False
        )
        flow_json = json.dumps(asdict(flow_structure), ensure_ascii=False)
        blocks_json = json.dumps(asdict(block_structure), ensure_ascii=False)
        variable_list = symbol_table.get_variable_list_for_prompt()

        system_prompt = load_prompt("stage7").format(variable_list=variable_list)
        user_prompt = f"""请从以下文本中提取 step：

behavior spans：
---
{behavior_json}
---

Flow 结构：
---
{flow_json}
---

Block 结构：
---
{blocks_json}
---

已知变量：
---
{variable_list}
---

输出 JSON："""

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
                )
                steps.append(step)
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid step: %s", e)
                continue

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
                    symbol_table.add_producer(
                        new_var_name, new_var_data.get("producer_step", "")
                    )
            except (KeyError, ValueError, TypeError) as e:
                self.logger.warning("Skipping invalid new variable: %s", e)
                continue

        # 5. Update SymbolTable with producer/consumer (after new_variables are declared)
        for step in steps:
            for var_name in step.inputs:
                symbol_table.add_consumer(var_name, step.step_id)
            for var_name in step.outputs:
                symbol_table.add_producer(var_name, step.step_id)

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
