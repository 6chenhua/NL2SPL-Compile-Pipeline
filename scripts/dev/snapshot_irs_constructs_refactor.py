"""Generate Phase 0 snapshots for the IRS / Constructs refactor.

The snapshots are characterization artifacts. They should change only when a
phase explicitly approves behavior or registry-shape changes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "irs_constructs_refactor"


def _jsonable_patch_type_meta(meta: object) -> dict[str, Any]:
    return {
        "patch_type": getattr(meta, "patch_type", None),
        "label": getattr(meta, "label", None),
        "description": getattr(meta, "description", None),
        "verification_lane": getattr(meta, "verification_lane", None),
    }


def construct_registry_shape() -> list[dict[str, Any]]:
    from nl2spl.compiler.construct_registry import SPLConstructRegistry

    registry = SPLConstructRegistry.default()
    shape: list[dict[str, Any]] = []
    for construct_type in registry.list_constructs():
        irs = registry.get(construct_type)
        shape.append({
            "construct_type": irs.construct_type,
            "description": irs.description,
            "existence_policy": irs.existence_policy,
            "no_demand_behavior": irs.no_demand_behavior,
            "partial_rendering_allowed": irs.partial_rendering_allowed,
            "source_signals": list(irs.source_signals),
            "slots": [
                {
                    "slot_name": slot.slot_name,
                    "syntax_required": slot.syntax_required,
                    "required_for_partial": slot.required_for_partial,
                    "required_for_complete": slot.required_for_complete,
                    "renderable_without": slot.renderable_without,
                    "evidence_kinds": list(slot.evidence_kinds),
                    "missing_diagnostic": slot.missing_diagnostic,
                    "can_be_inferred": slot.can_be_inferred,
                    "can_be_suggested": slot.can_be_suggested,
                    "repair_affordance_ids": [
                        aff.affordance_id for aff in slot.repair_affordances
                    ],
                    "repair_strategy_ids": [
                        aff.repair_strategy_id
                        for aff in slot.repair_affordances
                        if aff.repair_strategy_id
                    ],
                    "supported_patch_types": [
                        list(aff.supported_patch_types)
                        for aff in slot.repair_affordances
                    ],
                    "actionability": (
                        slot.actionability_decision.actionability
                        if slot.actionability_decision else None
                    ),
                    "non_editable_disposition": (
                        slot.actionability_decision.non_editable_disposition
                        if slot.actionability_decision else None
                    ),
                    "actionability_rationale": (
                        slot.actionability_decision.rationale_code
                        if slot.actionability_decision else None
                    ),
                }
                for slot in irs.slots
            ],
        })
    return shape


def repair_catalog_entries() -> list[dict[str, Any]]:
    from nl2spl.compiler.construct_registry import SPLConstructRegistry
    from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder
    from nl2spl.compiler.spl_editing.strategy.defaults import (
        build_default_strategy_registry,
    )

    catalog = RepairCatalogBuilder.from_construct_registry(
        SPLConstructRegistry.default(),
        strategy_registry=build_default_strategy_registry(),
    )
    return [
        {
            "entry_id": entry.entry_id,
            "affordance_id": entry.affordance_id,
            "construct_type": entry.construct_type,
            "slot_name": entry.slot_name,
            "diagnostic_kind": entry.diagnostic_kind,
            "handler_id": entry.handler_id,
            "context_id": entry.context_id,
            "target_resolver_id": entry.target_resolver_id,
            "supported_patch_types": list(entry.supported_patch_types),
            "default_patch_type": entry.default_patch_type,
            "editable_artifacts": list(entry.editable_artifacts),
            "default_verification_lane": entry.default_verification_lane,
            "required_evidence_kind": entry.required_evidence_kind,
            "user_facing": entry.user_facing,
            "materialization_plan_id": entry.materialization_plan_id,
            "selectable_ref_policy_id": entry.selectable_ref_policy_id,
            "intent_schema_id": entry.intent_schema_id,
            "required_context_facts": list(entry.required_context_facts),
            "stage_authority": entry.stage_authority,
            "repair_strategy_id": entry.repair_strategy_id,
            "strategy_display_label": entry.strategy_display_label,
            "closure_summary": entry.closure_summary,
            "preview_required": entry.preview_required,
            "strategy_options": [
                {
                    "option_id": option.option_id,
                    "strategy_id": option.strategy_id,
                    "label_key": option.label_key,
                    "description_key": option.description_key,
                    "interaction_contract_id": option.interaction_contract_id,
                    "execution_patch_types": list(option.execution_patch_types),
                    "closure_policy_id": option.closure_policy_id,
                    "user_facing": option.user_facing,
                }
                for option in entry.strategy_options
            ],
            "patch_type_metadata": [
                _jsonable_patch_type_meta(meta)
                for meta in entry.patch_type_metadata
            ],
        }
        for entry in catalog.entries
    ]


def diagnostic_registry_kinds() -> dict[str, Any]:
    from nl2spl.compiler.diagnostic_registry import DiagnosticRegistry

    registry = DiagnosticRegistry.default()
    all_kinds = registry.list_kinds()
    enabled = registry.list_kinds(enabled_only=True)
    return {
        "all": all_kinds,
        "enabled": enabled,
        "reserved": sorted(set(all_kinds) - set(enabled)),
        "specs": [
            {
                "kind": kind,
                "default_severity": registry.get(kind).default_severity,
                "blocks_completion": registry.get(kind).blocks_completion,
                "description": registry.get(kind).description,
                "allowed_targets": list(registry.get(kind).allowed_targets),
                "enabled": registry.get(kind).enabled,
            }
            for kind in all_kinds
        ],
    }


def import_boundary_baseline() -> dict[str, Any]:
    rules = {
        "legacy_construct_registry_imports": r"from nl2spl\.compiler\.construct_registry",
        "legacy_diagnostic_registry_imports": r"from nl2spl\.compiler\.diagnostic_registry",
        "legacy_diagnostic_consolidator_imports": r"from nl2spl\.compiler\.diagnostic_consolidator",
        "legacy_report_renderer_imports": r"from nl2spl\.compiler\.report_renderer",
        "legacy_irs_prompt_builder_imports": r"from nl2spl\.compiler\.irs_prompt_builder",
        "irs_graph_frontier_patch_imports": (
            r"from nl2spl\.compiler\.irs\.(graph|frontier|patch_type_meta)"
        ),
        "reporting_depends_on_irs_feedback": r"irs\.feedback_projector",
    }
    compiled = {name: re.compile(pattern) for name, pattern in rules.items()}
    results = {name: [] for name in rules}
    for base in (ROOT / "src", ROOT / "tests"):
        for path in base.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for name, pattern in compiled.items():
                    if pattern.search(line):
                        results[name].append({
                            "path": rel,
                            "line": lineno,
                            "text": line.strip(),
                        })
    return {
        name: {
            "count": len(matches),
            "matches": matches,
        }
        for name, matches in results.items()
    }


def stage_prompt_snapshots() -> dict[str, str]:
    from nl2spl.compiler.construct_registry import SPLConstructRegistry
    from nl2spl.compiler.irs_prompt_builder import IRSDrivenPromptBuilder

    builder = IRSDrivenPromptBuilder(SPLConstructRegistry.default())
    return {
        stage: builder.render_for_stage(stage)
        for stage in ("stage3_5", "stage4", "stage7", "stage9_5")
    }


def report_renderer_snapshot() -> str:
    from nl2spl.compiler.compile_result import CompileAssumption, MissingSlot
    from nl2spl.compiler.report_renderer import render_report
    from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord

    diagnostic = CompileDiagnostic(
        "D_PHASE0_001",
        "missing_handler",
        "warning",
        "Exception flow 'exc_phase0' has no handler step.",
        target_ref="exception_flow:exc_phase0",
        source_span_ids=["span_phase0_failure"],
        suggested_resolution="Add a handler step for the failure condition.",
        missing_slot=MissingSlot(
            slot_name="handler_action",
            required_for="exception_flow:exc_phase0",
            reason="No handler specified.",
            suggested_question="What should happen on failure?",
        ),
    )
    assumption = CompileAssumption(
        assumption_id="ASM_PHASE0_001",
        target_ref="exception_flow:exc_phase0",
        text="Failure handler is missing.",
        reason="Source does not specify handler action.",
        suggested_resolution="Ask the user for a handler action.",
        related_diagnostic_id=diagnostic.diagnostic_id,
    )
    trace = TraceRecord(
        target_ref="exception_flow:exc_phase0",
        source_span_ids=["span_phase0_failure"],
        relation="direct",
        explanation="Failure condition is source-backed.",
    )
    return render_report(
        "[DEFINE_WORKER: MainWorker]",
        completeness="partial",
        diagnostics=[diagnostic],
        assumptions=[assumption],
        traces=[trace],
        adapter_warnings=["phase0 adapter warning"],
        validation_warnings=["phase0 validation warning"],
    )


def build_all_snapshots() -> dict[str, Any]:
    return {
        "construct_registry_shape.json": construct_registry_shape(),
        "repair_catalog_entries.json": repair_catalog_entries(),
        "diagnostic_registry_kinds.json": diagnostic_registry_kinds(),
        "import_boundary_baseline.json": import_boundary_baseline(),
        "stage_prompt_snapshots.json": stage_prompt_snapshots(),
        "report_renderer_snapshot.txt": report_renderer_snapshot(),
    }


def write_snapshots(fixture_dir: Path = FIXTURE_DIR) -> None:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    snapshots = build_all_snapshots()
    for filename, payload in snapshots.items():
        path = fixture_dir / filename
        if filename.endswith(".json"):
            path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(str(payload), encoding="utf-8")


def main() -> None:
    write_snapshots()


if __name__ == "__main__":
    main()
