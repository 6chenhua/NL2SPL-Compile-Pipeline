"""R7 materialization verification hardening tests."""

from __future__ import annotations

import json

from nl2spl.compiler.spl_editing.core.model import (
    PatchApplyResult,
    RepairEvidence,
    RepairPatch,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import (
    ConstructRepairIntent,
    InsertProducerStepIntentPayload,
)
from nl2spl.compiler.spl_editing.verification.lanes import (
    LaneBReplayAdapter,
    VerificationArtifacts,
)
from nl2spl.compiler.spl_editing.verification.materialization_authority_verifier import (
    MaterializationAuthorityVerifier,
)
from nl2spl.compiler.spl_editing.verification.runner import VerificationRunner
from nl2spl.compiler.spl_editing.verification.selected_ref_verifier import (
    SelectedRefVerifier,
)
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

_PLAN_ID = "stage7.step_producer_repair.v1"
_AUTHORITY = "stage7.worker_step_plan"
_EVIDENCE_PACKET_ID = "ev_patch_r7"
_REF_ID = "step_output:w_main:ctx::customer_profile"
_TARGET_REF_ID = "required_output:w_main:ctx::report_summary"


class _StubLane(LaneBReplayAdapter):
    def replay(self, snapshot):
        return VerificationArtifacts(
            consolidated_diagnostics=snapshot.compile_diagnostics,
            rendered_spl=snapshot.final_spl or "",
        )


def _diag() -> CompileDiagnostic:
    return CompileDiagnostic(
        diagnostic_id="diag_r7",
        kind="missing_output_producer",
        severity="warning",
        message="Missing output producer",
        target_ref="required_output:w_main:ctx::report_summary",
        blocks_completion=True,
    )


def _intent(selected: tuple[str, ...] = (_REF_ID,)) -> ConstructRepairIntent:
    return ConstructRepairIntent(
        intent_id="intent_r7",
        issue_id="issue_r7",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="required_output_ctx",
        target_slot_name="producer",
        target_ref_id=_TARGET_REF_ID,
        selected_ref_ids=selected,
        materialization_plan_id=_PLAN_ID,
        payload=InsertProducerStepIntentPayload(
            target_output_ref_id=_TARGET_REF_ID,
            selected_input_ref_ids=selected,
            producer_goal="Summarize the selected customer profile.",
        ),
    )


def _patch(payload: object | None = None) -> RepairPatch:
    return RepairPatch(
        patch_id="patch_r7",
        affordance_id="required_output.insert_or_bind_producer",
        patch_type="InsertProducerStep",
        target_ref="required_output:w_main:ctx::report_summary",
        irs_ref=DiagnosticIRSRef(
            construct_type="REQUIRED_OUTPUT",
            construct_id="required_output_ctx",
            slot_name="producer",
        ),
        base_compile_run_id="run_r7",
        artifact_snapshot_id="snap_r7",
        overlay_version=0,
        payload=payload if payload is not None else _intent(),
        verification_lane="B",
        evidence=RepairEvidence(
            related_diagnostic_id="diag_r7",
            user_text="Confirmed producer repair.",
        ),
    )


def _step(
    *,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    metadata_overrides: dict[str, str] | None = None,
) -> StepIR:
    metadata = {
        "origin": "user_confirmed_repair",
        "repair_patch_id": "patch_r7",
        "related_diagnostic_id": "diag_r7",
        "evidence_packet_id": _EVIDENCE_PACKET_ID,
        "materialization_authority": _AUTHORITY,
        "materialization_plan_id": _PLAN_ID,
        "consumed_selected_ref_ids": json.dumps([_REF_ID]),
        "selected_ref_canonical_names": json.dumps(["customer_profile"]),
        "target_output_ref_id": _TARGET_REF_ID,
        "target_output_name": "report_summary",
        "user_text": "Confirmed producer repair.",
    }
    if metadata_overrides:
        metadata.update(metadata_overrides)
    return StepIR(
        step_id="st2",
        text="Summarize the selected customer profile.",
        source_span_ids=[],
        command_type="GENERAL_COMMAND",
        inputs=inputs if inputs is not None else ["customer_profile"],
        outputs=outputs if outputs is not None else ["report_summary"],
        metadata=metadata,
    )


def _snapshot(step: StepIR | None = None, *, diagnostics=()) -> ArtifactSnapshot:
    steps = [] if step is None else [step]
    return ArtifactSnapshot(
        snapshot_id="snap_r7",
        compile_run_id="run_r7",
        overlay_version=1,
        compile_diagnostics=tuple(diagnostics),
        worker_step_plan=WorkerStepPlanIR(
            main_worker_id="w_main",
            worker_steps={"w_main": steps},
        ),
    )


def _apply_result(step: StepIR, *, audit_overrides: dict | None = None) -> PatchApplyResult:
    audit = {
        "materialization_plan_id": _PLAN_ID,
        "materializer_id": _PLAN_ID,
        "materialization_authority": _AUTHORITY,
        "evidence_packet_id": _EVIDENCE_PACKET_ID,
        "consumed_selected_ref_ids": (_REF_ID,),
    }
    if audit_overrides:
        audit.update(audit_overrides)
    return PatchApplyResult(
        patched_snapshot=_snapshot(step),
        overlay_event=None,
        changed_refs=("step:w_main:st2",),
        changed_step_ids=("st2",),
        audit_metadata=audit,
    )


def test_runner_accepts_materialized_step_with_matching_ref_and_authority_lineage() -> None:
    patch = _patch()
    base = ArtifactSnapshot(
        snapshot_id="snap_r7",
        compile_run_id="run_r7",
        overlay_version=0,
        compile_diagnostics=(_diag(),),
    )
    step = _step()
    result = VerificationRunner(lane_b=_StubLane()).verify(
        patch,
        base,
        _snapshot(step),
        apply_result=_apply_result(step),
    )
    assert result.accepted is True


def test_selected_ref_verifier_rejects_hallucinated_step_input() -> None:
    step = _step(inputs=["customer_profile", "project_data"])
    failures = SelectedRefVerifier().verify(_patch(), _apply_result(step))
    assert any("do not match selected ref canonical names" in f for f in failures)


def test_selected_ref_verifier_rejects_consumed_ref_not_declared_by_intent() -> None:
    step = _step(
        metadata_overrides={
            "consumed_selected_ref_ids": json.dumps([_REF_ID, "resource:w_main::::project_data"]),
            "selected_ref_canonical_names": json.dumps(["customer_profile", "project_data"]),
        },
        inputs=["customer_profile", "project_data"],
    )
    failures = SelectedRefVerifier().verify(
        _patch(),
        _apply_result(
            step,
            audit_overrides={
                "consumed_selected_ref_ids": (_REF_ID, "resource:w_main::::project_data"),
            },
        ),
    )
    assert any("not declared in intent.selected_ref_ids" in f for f in failures)


def test_selected_ref_verifier_rejects_wrong_target_output() -> None:
    step = _step(outputs=["project_data"])
    failures = SelectedRefVerifier().verify(_patch(), _apply_result(step))
    assert any("do not match target output" in f for f in failures)


def test_authority_verifier_rejects_step_authority_mismatch() -> None:
    step = _step(metadata_overrides={"materialization_authority": "stage9.fake"})
    failures = MaterializationAuthorityVerifier().verify(_patch(), _apply_result(step))
    assert any("materialization_authority" in f for f in failures)


def test_materialization_verifiers_skip_non_materialized_apply_result() -> None:
    step = _step(inputs=["direct_binding_input"])
    apply_result = _apply_result(
        step,
        audit_overrides={
            "materialization_plan_id": None,
            "materializer_id": None,
            "materialization_authority": None,
            "evidence_packet_id": None,
            "consumed_selected_ref_ids": None,
        },
    )
    apply_result.audit_metadata.clear()
    assert SelectedRefVerifier().verify(_patch(payload={}), apply_result) == ()
    assert MaterializationAuthorityVerifier().verify(_patch(payload={}), apply_result) == ()


def test_authority_verifier_allows_explicit_empty_consumed_refs() -> None:
    step = _step(
        inputs=[],
        metadata_overrides={
            "consumed_selected_ref_ids": json.dumps([]),
            "selected_ref_canonical_names": json.dumps([]),
        },
    )
    failures = MaterializationAuthorityVerifier().verify(
        _patch(payload=_intent(selected=())),
        _apply_result(step, audit_overrides={"consumed_selected_ref_ids": ()}),
    )
    assert failures == ()
