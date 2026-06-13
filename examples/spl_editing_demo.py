r"""Runnable SPL Editing backend demo.

Run from the repository root:

    .\.venv\Scripts\python.exe examples\spl_editing_demo.py --auto

The script builds an in-memory ArtifactSnapshot, lists editable issues,
generates repair suggestions, applies one suggestion, verifies through the
compiler replay lane, and prints the patched SPL.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nl2spl.compiler.spl_editing.cli import _build_default_service, _run_demo
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import ExceptionFlowRef
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)


def _base_profile() -> AgentProfileIR:
    return AgentProfileIR(persona=PersonaIR(role="Assistant", aspects=[]))


def build_missing_handler_snapshot() -> ArtifactSnapshot:
    diag = CompileDiagnostic(
        "diag_mh",
        "missing_handler",
        "warning",
        "Exception flow has condition but no handler step.",
        target_ref="worker:w_main.exception_flow:exc_1",
        blocks_completion=True,
    )
    diag.metadata["irs_ref"] = {
        "construct_type": "EXCEPTION_FLOW",
        "construct_id": "worker:w_main.exception_flow:exc_1",
        "slot_name": "handler_action",
        "construct_path": [],
        "source_authority": "post_normalize_irs",
    }
    diag.metadata["authority"] = "post_normalize_irs"
    return ArtifactSnapshot(
        "snap_demo_mh",
        "run_demo_mh",
        0,
        worker_plan=WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(
                    "w_main",
                    "MainWorker",
                    "main",
                    "Main worker",
                    boundary_kind="main_worker",
                    owned_span_ids=["s1"],
                )
            ],
        ),
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={
                "w_main": FlowStructureIR(
                    exception_flows=[
                        ExceptionFlowRef(
                            flow_id="exc_1",
                            condition_text="Template unavailable.",
                            blocks=[],
                        )
                    ]
                )
            }
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={"w_main": BlockStructureIR()}
        ),
        resources=ResourceRegistryIR(),
        symbol_table=SymbolTable(),
        agent_profile=_base_profile(),
        compile_diagnostics=(diag,),
    )


def build_missing_output_snapshot() -> ArtifactSnapshot:
    diag = CompileDiagnostic(
        "diag_mop",
        "missing_output_producer",
        "warning",
        "Required output 'draft' has no source-backed producer step.",
        target_ref="worker:w_main.output:draft",
        blocks_completion=True,
    )
    diag.metadata["irs_ref"] = {
        "construct_type": "REQUIRED_OUTPUT",
        "construct_id": "worker:w_main.output:draft",
        "slot_name": "producer",
        "construct_path": [],
        "source_authority": "post_normalize_irs",
    }
    diag.metadata["authority"] = "post_normalize_irs"
    return ArtifactSnapshot(
        "snap_demo_mop",
        "run_demo_mop",
        0,
        worker_plan=WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(
                    "w_main",
                    "MainWorker",
                    "main",
                    "Main worker",
                    boundary_kind="main_worker",
                    owned_span_ids=["s1"],
                )
            ],
        ),
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"w_main": FlowStructureIR()}
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={"w_main": BlockStructureIR()}
        ),
        resources=ResourceRegistryIR(),
        symbol_table=SymbolTable(),
        agent_profile=_base_profile(),
        compile_diagnostics=(diag,),
    )


def build_worker_handoff_snapshot() -> ArtifactSnapshot:
    diag = CompileDiagnostic(
        "diag_promo",
        "type_or_contract_ambiguity",
        "warning",
        "Missing handoff contract.",
        target_ref="worker_promotion:cand_1",
        blocks_completion=True,
    )
    diag.metadata["irs_ref"] = {
        "construct_type": "WORKER_PROMOTION",
        "construct_id": "worker_promotion:cand_1",
        "slot_name": "promotion_input_contract",
        "construct_path": [],
        "source_authority": "selected_promoted_stage_local_irs",
    }
    diag.metadata["authority"] = "selected_promoted_stage_local_irs"
    diag.metadata["repairability"] = "editable"
    diag.metadata["issue_role"] = "primary"
    diag.metadata["issue_group_id"] = "worker_promotion_group:worker_promotion:cand_1"
    diag.metadata["original_semantic_role"] = "delegation_intent"
    diag.metadata["promotion_status"] = "blocked"
    return ArtifactSnapshot(
        "snap_demo_handoff",
        "run_demo_handoff",
        0,
        worker_plan=WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(
                    "w_main",
                    "Main",
                    "main",
                    "Main",
                    boundary_kind="main_worker",
                    owned_span_ids=["s1"],
                ),
                WorkerSpecIR(
                    "w_child",
                    "Child",
                    "child",
                    "ChildWorker",
                    boundary_kind="child_worker",
                ),
            ],
        ),
        worker_step_plan=WorkerStepPlanIR(
            "w_main",
            {
                "w_main": [
                    StepIR(
                        "st_invoke",
                        "Invoke child",
                        ["s1"],
                        "INVOKE_WORKER",
                        handoff_id="handoff_repair_cand_1",
                        integration_ref="Child",
                    )
                ]
            },
        ),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"w_main": FlowStructureIR()}
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={"w_main": BlockStructureIR()}
        ),
        resources=ResourceRegistryIR(),
        symbol_table=SymbolTable(),
        agent_profile=_base_profile(),
        compile_diagnostics=(diag,),
    )


SNAPSHOT_BUILDERS = {
    "missing-handler": build_missing_handler_snapshot,
    "missing-output": build_missing_output_snapshot,
    "handoff": build_worker_handoff_snapshot,
}


def run_auto(snapshot: ArtifactSnapshot, preferred_patch_type: str | None = None) -> None:
    svc = _build_default_service()
    run_id = svc.register_compile_result(snapshot)
    issues = svc.list_editable_issues(run_id)
    if not issues:
        raise RuntimeError("No editable issues found.")

    issue = issues[0]
    print(f"Selected issue: {issue.kind}")
    print(f"Target: {issue.target_ref}")

    session = svc.create_session(run_id, issue)
    suggestions = svc.generate_suggestions(session.session_id)
    if not suggestions:
        raise RuntimeError("No repair suggestions generated.")

    suggestion = suggestions[0]
    if preferred_patch_type is not None:
        matches = [
            item for item in suggestions
            if item.patch.patch_type == preferred_patch_type
        ]
        if not matches:
            raise RuntimeError(
                f"No suggestion found for patch type {preferred_patch_type}."
            )
        suggestion = matches[0]

    print(f"Selected suggestion: {suggestion.title}")
    print(f"Patch type: {suggestion.patch.patch_type}")
    if suggestion.spl_preview:
        print("\n--- Preview ---")
        print(suggestion.spl_preview)

    updated = svc.apply_suggestion(session.session_id, suggestion.suggestion_id)
    print(f"\nApplied overlay version: {updated.overlay_version}")

    result = svc.verify_session(session.session_id)
    print(f"Verification: {'accepted' if result.accepted else 'rejected'}")
    print(f"Lane: {result.lane}")
    if result.resolved_diagnostic_ids:
        print(f"Resolved diagnostics: {', '.join(result.resolved_diagnostic_ids)}")
    if result.failure_reasons:
        print(f"Failures: {'; '.join(result.failure_reasons)}")

    if result.accepted:
        print("\n--- Patched SPL ---")
        print(svc.get_patched_spl(run_id) or "(no SPL produced)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a self-contained SPL Editing backend demo."
    )
    parser.add_argument(
        "--case",
        choices=tuple(SNAPSHOT_BUILDERS),
        default="missing-handler",
        help="Demo scenario to run.",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Apply the first valid suggestion without interactive prompts.",
    )
    args = parser.parse_args()

    snapshot = SNAPSHOT_BUILDERS[args.case]()
    if args.auto:
        preferred = None
        if args.case == "handoff":
            preferred = "CreateWorkerHandoffContract"
        run_auto(snapshot, preferred_patch_type=preferred)
        return

    _run_demo(snapshot)


if __name__ == "__main__":
    main()
