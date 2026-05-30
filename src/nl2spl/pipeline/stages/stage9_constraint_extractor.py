"""Stage 9: ConstraintExtractor - Extract constraints from rules spans."""

from __future__ import annotations

import json
from dataclasses import asdict

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.base import PipelineStage


class ConstraintExtractor(PipelineStage[
        tuple[
            list[SpanIR],
            FieldRouteIR,
            FlowStructureIR,
            BlockStructureIR,
            SymbolTable,
            list[StepIR],
        ]
        | tuple[
            list[SpanIR],
            FieldRouteIR,
            FlowStructureIR,
            BlockStructureIR,
            SymbolTable,
            list[StepIR],
            CanonicalCompileInput,
        ],
    list[ConstraintIR],
]):
    """Extract constraints from rules spans.

    This stage extracts constraint rules from rules spans,
    including requirements, prohibitions, gates, evidence requirements, etc.
    """

    @property
    def name(self) -> str:
        """Stage name for logging and checkpointing."""
        return "stage9_constraint_extractor"

    def execute(
        self,
        input_data: tuple[
            list[SpanIR],
            FieldRouteIR,
            FlowStructureIR,
            BlockStructureIR,
            SymbolTable,
            list[StepIR],
        ]
        | tuple[
            list[SpanIR],
            FieldRouteIR,
            FlowStructureIR,
            BlockStructureIR,
            SymbolTable,
            list[StepIR],
            CanonicalCompileInput,
        ],
    ) -> list[ConstraintIR]:
        """Execute constraint extraction.

        Args:
            input_data: Tuple of (spans, routes, flow, blocks, symbol_table, steps)

        Returns:
            List of ConstraintIR objects

        Raises:
            StageError: If extraction fails
        """
        canonical_input: CanonicalCompileInput | None = None
        if len(input_data) == 6:
            spans, routes, flow, blocks, symbol_table, steps = input_data
        else:
            spans, routes, flow, blocks, symbol_table, steps, canonical_input = input_data
        self.logger.info("Starting constraint extraction with %d spans", len(spans))

        # 1. Filter rules spans with annotation-driven candidate selection
        rules_spans = [s for s in spans if s.span_id in routes.rules]
        excluded_failure_ids: set[str] = set()
        if routes.annotations:
            excluded_failure_ids = {
                a.span_id for a in routes.annotations
                if a.semantic_role == "failure_mode"
                and a.construct_target == "EXCEPTION_FLOW"
                and a.executable is False
            }
            # Pure delegation intent (no constraint/rule semantics) excluded;
            # delegation boundary rules (only/must/when/unless/if patterns)
            # remain available as constraint candidates.
            pure_intent_ids: set[str] = set()
            boundary_rule_patterns = (
                "only delegate", "must delegate", "do not delegate",
                "must not delegate", "delegate only", "delegate when",
                "delegate unless", "delegate if",
            )
            for a in routes.annotations:
                if (a.semantic_role == "delegation_intent"
                        and a.route_family == "delegation_boundary"
                        and a.executable is False):
                    span = next((s for s in spans if s.span_id == a.span_id), None)
                    span_text = (span.text.lower() if span else "")
                    if any(p in span_text for p in boundary_rule_patterns):
                        continue  # boundary rule — keep as candidate
                    pure_intent_ids.add(a.span_id)
            excluded_failure_ids |= pure_intent_ids
            rules_spans = [s for s in rules_spans if s.span_id not in excluded_failure_ids]

        self.logger.info("Found %d rules spans", len(rules_spans))

        # 2. Build prompt
        rules_json = json.dumps([s.to_dict() for s in rules_spans], ensure_ascii=False)
        variable_list = symbol_table.get_variable_list_for_prompt()
        step_list = "\n".join([f"- {s.step_id}: {s.text}" for s in steps])
        hint_context = self._constraint_hint_context(canonical_input)

        system_prompt = load_prompt("stage9")

        user_prompt = f"""请从以下文本中提取约束：

rules spans：
---
{rules_json}
---

已知变量：
---
{variable_list}
---

已知 steps：
---
{step_list}
---

adapter constraint hints（仅作为提示，不是 ConstraintIR）：
---
{hint_context}
---

输出 JSON："""

        # 3. Call LLM
        try:
            result = self.client.call_json(
                stage_name=self.name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as e:
            self.logger.error("LLM call failed: %s", e)
            raise

        # 4. Parse constraints with D5 guard
        constraints = []
        constraints_data = result.get("constraints", [])

        for const_data in constraints_data:
            try:
                source_ids = set(const_data.get("source_span_ids", []))
                # D5: reject constraints sourced only from excluded failure/delegation spans
                if source_ids and excluded_failure_ids and source_ids.issubset(excluded_failure_ids):
                    self.logger.info(
                        "D5 guard: rejecting constraint '%s' sourced only from "
                        "excluded non-executable spans %s",
                        const_data.get("constraint_id", "?"), sorted(source_ids),
                    )
                    continue
                constraint = ConstraintIR(
                    constraint_id=const_data["constraint_id"],
                    text=const_data["text"],
                    kind=const_data["kind"],
                    targets=const_data.get("targets", []),
                    source_span_ids=const_data.get("source_span_ids", []),
                )
                constraints.append(constraint)
            except KeyError as e:
                self.logger.warning("Missing field in constraint data: %s", e)
                continue
            except ValueError as e:
                self.logger.warning("Invalid constraint data: %s", e)
                continue

        self.logger.info(
            "Extracted %d constraints from %d items",
            len(constraints),
            len(constraints_data),
        )

        # 5. Save checkpoint
        self.save_checkpoint({"constraints": [asdict(c) for c in constraints]})

        return constraints

    @staticmethod
    def _constraint_hint_context(canonical_input: CanonicalCompileInput | None) -> str:
        if canonical_input is None or canonical_input.source_schema == "generic_nl":
            return "(No adapter constraint hints)"
        hints = canonical_input.compile_hints.constraint_hints
        if not hints:
            return "(No adapter constraint hints)"
        return "\n".join(
            f"- {hint.text} (suggested_kind={hint.suggested_kind or 'unknown'})"
            for hint in hints
        )
