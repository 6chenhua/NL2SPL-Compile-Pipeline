"""R8 missing-output producer end-to-end guardrails."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from tests.spl_editing_stub_llm import StubSuggestionLLM

_TARGET_OUTPUT_REF_ID = "required_output:w_main:required_output_context::draft"
_CUSTOMER_REF_ID = "step_output:w_main:st_source::customer_profile"
_HALLUCINATED_REF_ID = "variable:w_main:symbol_table:worker:project_data"


def _missing_output_diag() -> CompileDiagnostic:
    diag = CompileDiagnostic(
        "diag_mop_r8",
        "missing_output_producer",
        "warning",
        "Required output 'draft' has no source-backed producer step.",
        target_ref="worker:w_main.output:draft",
        blocks_completion=True,
    )
    diag.metadata["irs_ref"] = {
        "construct_type": "REQUIRED_OUTPUT",
        "construct_id": "x",
        "slot_name": "producer",
        "construct_path": [],
        "source_authority": "post_normalize_irs",
    }
    diag.metadata["authority"] = "post_normalize_irs"
    diag.metadata["repairability"] = "editable"
    diag.metadata["issue_group_id"] = "g_mop_r8"
    diag.metadata["issue_role"] = "primary"
    return diag


def _snapshot(*, with_source_output: bool) -> ArtifactSnapshot:
    source_steps = []
    if with_source_output:
        source_steps.append(
            StepIR(
                "st_source",
                "Collect customer profile.",
                [],
                "GENERAL_COMMAND",
                outputs=["customer_profile"],
            )
        )
    return ArtifactSnapshot(
        "snap_mop_r8",
        "run_mop_r8",
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
                )
            ],
        ),
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": source_steps}),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={
                "w_main": FlowStructureIR(),
            }
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={
                "w_main": BlockStructureIR(),
            }
        ),
        resources=ResourceRegistryIR(),
        symbol_table=SymbolTable(),
        agent_profile=AgentProfileIR(
            persona=PersonaIR(role="Assistant", aspects=[]),
        ),
        compile_diagnostics=(_missing_output_diag(),),
    )


def _insert_response(selected_ref_ids: list[str], goal: str = "Produce draft.") -> dict:
    return {
        "patch_type": "InsertProducerStep",
        "title": "Add producer step",
        "explanation": "Create a bounded producer from selected refs.",
        "payload": {
            "target_output_ref_id": _TARGET_OUTPUT_REF_ID,
            "selected_input_ref_ids": selected_ref_ids,
            "producer_goal": goal,
        },
    }


def test_hallucinated_project_data_ref_rejected_before_overlay_or_stepir() -> None:
    llm = StubSuggestionLLM(_insert_response([_HALLUCINATED_REF_ID]))
    svc = _build_default_service(suggestion_llm=llm)
    snap = _snapshot(with_source_output=False)
    run_id = svc.register_compile_result(snap)
    issue = svc.list_editable_issues(run_id)[0]
    session = svc.create_session(run_id, issue)

    with pytest.raises(PatchValidationError, match="did not produce a valid"):
        svc.generate_suggestions(session.session_id)

    stored = svc._get_snapshot(run_id)
    assert stored.overlay_version == 0
    assert stored.worker_step_plan.worker_steps["w_main"] == []


def test_valid_selected_ref_materializes_input_and_target_output_e2e() -> None:
    llm = StubSuggestionLLM(
        _insert_response(
            [_CUSTOMER_REF_ID],
            goal="Draft the response from customer_profile.",
        )
    )
    svc = _build_default_service(suggestion_llm=llm)
    snap = _snapshot(with_source_output=True)
    run_id = svc.register_compile_result(snap)
    issue = svc.list_editable_issues(run_id)[0]
    session = svc.create_session(run_id, issue)

    suggestions = svc.generate_suggestions(session.session_id)
    assert len(suggestions) == 1
    updated = svc.apply_suggestion(session.session_id, suggestions[0].suggestion_id)

    patched = svc._get_snapshot(run_id)
    steps = patched.worker_step_plan.worker_steps["w_main"]
    new_step = next(step for step in steps if step.step_id != "st_source")
    assert updated.overlay_version == 1
    assert new_step.inputs == ["customer_profile"]
    assert new_step.outputs == ["draft"]
    assert new_step.metadata["target_output_ref_id"] == _TARGET_OUTPUT_REF_ID

    result = svc.verify_session(session.session_id)
    assert result.accepted is True
