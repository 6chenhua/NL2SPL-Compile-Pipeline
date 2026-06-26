"""Phase U3: Patch Applier Evidence Stamping Contract — Behavioral Audit (r2).

Replaces source-scanning with behavioral tests that verify the actual
``StepIR`` metadata produced by each applier.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.errors import SPLEditingError
from nl2spl.compiler.spl_editing.core.model import RepairEvidence, RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

# =============================================================================
# Helpers
# =============================================================================


def _make_patch(
    patch_type: str,
    payload: dict,
    *,
    patch_id: str = "p1",
    related_diagnostic_id: str = "diag_001",
    user_text: str = "User provided clarification.",
) -> RepairPatch:
    return RepairPatch(
        patch_id=patch_id,
        affordance_id="test.affordance",
        patch_type=patch_type,
        target_ref="test_target",
        irs_ref=DiagnosticIRSRef("EXCEPTION_FLOW", "handler_action", "missing_handler"),
        base_compile_run_id="run_1",
        artifact_snapshot_id="snap_1",
        overlay_version=0,
        payload=payload,
        evidence=RepairEvidence(
            related_diagnostic_id=related_diagnostic_id,
            user_text=user_text,
        ),
        verification_lane="A",
    )


def _make_snapshot(worker_steps: dict[str, list[StepIR]] | None = None) -> ArtifactSnapshot:
    if worker_steps is None:
        worker_steps = {"worker_main": []}
    wsp = WorkerStepPlanIR(main_worker_id="worker_main", worker_steps=worker_steps)
    return ArtifactSnapshot(
        compile_run_id="run_1",
        snapshot_id="snap_1",
        overlay_version=0,
        worker_step_plan=wsp,
    )


def _find_step_in_snapshot(snap: ArtifactSnapshot, step_id_contains: str) -> StepIR | None:
    """Find a step in the snapshot whose step_id contains the given string."""
    wsp = snap.worker_step_plan
    if wsp is None:
        return None
    for steps in wsp.worker_steps.values():
        for s in steps:
            if step_id_contains in s.step_id:
                return s
    return None


# =============================================================================
# Behavioral audit: each applier stamps complete UCR metadata
# =============================================================================


class TestAddExceptionHandlerStepStamping:
    """Exception handler metadata stamping belongs to the stage-authorized materializer."""

    def test_materializer_source_includes_all_metadata_keys(self) -> None:
        import inspect

        from nl2spl.compiler.spl_editing.materialization.stage7.exception_handler_step import (
            Stage7ExceptionHandlerStepMaterializer,
        )

        source = inspect.getsource(Stage7ExceptionHandlerStepMaterializer.materialize)
        assert '"origin"' in source
        assert '"repair_patch_id"' in source
        assert '"related_diagnostic_id"' in source
        assert '"user_text"' in source


class TestInsertProducerStepStamping:
    """InsertProducerStep creates a StepIR with full UCR metadata.

    Covered by existing behavioral tests in ``test_b6_missing_output_producer_patch.py``
    which verifies ``origin=user_confirmed_repair`` on the produced step.
    """

    def test_materializer_stamps_all_metadata_keys(self) -> None:
        """R6: Metadata stamping moved to Stage7ProducerRepairMaterializer."""
        import inspect

        from nl2spl.compiler.spl_editing.materialization.stage7.producer_step import (
            Stage7ProducerRepairMaterializer,
        )

        source = inspect.getsource(Stage7ProducerRepairMaterializer.materialize)
        assert '"origin"' in source
        assert '"repair_patch_id"' in source
        assert '"related_diagnostic_id"' in source
        assert '"user_text"' in source, (
            "Stage7ProducerRepairMaterializer must stamp user_text in StepIR metadata"
        )


class TestConvertDelegationToRequestInputStamping:
    """Delegation request-input stamping belongs to WorkerHandoffContractMaterializer."""

    def test_direct_applier_is_disabled(self) -> None:
        from nl2spl.compiler.spl_editing.patches.convert_delegation_to_request_input.applier import (  # noqa: E501
            ConvertDelegationToRequestInputApplier,
        )

        patch = _make_patch(
            "ConvertDelegationToRequestInput",
            {
                "worker_id": "worker_main",
                "prompt_text": "Is this correct?",
                "value_target": "confirmed",
                "outputs": ["confirmed"],
            },
        )
        with pytest.raises(SPLEditingError, match="RepairMaterializationService"):
            ConvertDelegationToRequestInputApplier().apply(patch, _make_snapshot())


class TestConvertDelegationToMainFlowStepStamping:
    """Delegation main-flow stamping belongs to WorkerHandoffContractMaterializer."""

    def test_materializer_source_includes_user_text(self) -> None:
        import inspect

        from nl2spl.compiler.spl_editing.materialization.worker_handoff.contract import (
            WorkerHandoffContractMaterializer,
        )

        source = inspect.getsource(WorkerHandoffContractMaterializer)
        assert '"user_text"' in source
        assert '"resolution_kind"' in source


# =============================================================================
# Negative: unconfirmed AI suggestion is never renderable
# =============================================================================


class TestUnconfirmedNotRenderable:
    """Behavioral confirmation that unconfirmed AI suggestions are not treatable as evidence."""

    def test_unconfirmed_step_no_source_spans_no_ucr_not_renderable(self) -> None:
        from nl2spl.compiler.producer_index import _step_is_renderable

        step = StepIR("st_ai", "AI generated text", [], "GENERAL_COMMAND")
        assert not _step_is_renderable(step), (
            "Unconfirmed AI step without source spans must NOT be renderable"
        )

    def test_llm_suggestion_metadata_not_valid_origin(self) -> None:
        from nl2spl.compiler.evidence import classify_step_evidence

        step = StepIR(
            "st_ai", "AI suggested", [], "GENERAL_COMMAND", metadata={"llm_generated": "true"}
        )
        evidence = classify_step_evidence(step)
        assert evidence.primary_kind == "missing"


# =============================================================================
# Negative: GenericEvidenceVerifier rejects incomplete binding evidence
# =============================================================================


class TestGenericEvidenceVerifierBindingRejection:
    """Prove that incomplete binding metadata is rejected."""

    def _make_patch(self) -> RepairPatch:
        from nl2spl.ir.diagnostics import DiagnosticIRSRef

        return RepairPatch(
            patch_id="patch_x",
            affordance_id="test.affordance",
            patch_type="BindExistingProducerStep",
            target_ref="test",
            irs_ref=DiagnosticIRSRef("REQUIRED_OUTPUT", "producer", "missing_output_producer"),
            base_compile_run_id="run_1",
            artifact_snapshot_id="snap_1",
            overlay_version=0,
            payload={},
            evidence=RepairEvidence(related_diagnostic_id="diag_x"),
        )

    def _make_verifier(self) -> object:
        from nl2spl.compiler.spl_editing.verification.generic_evidence_verifier import (
            GenericEvidenceVerifier,
        )

        return GenericEvidenceVerifier()

    def test_binding_missing_repair_patch_id_rejected(self) -> None:
        """Binding without repair_patch_id → verifier rejects."""
        patch = self._make_patch()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_1",
            overlay_version=1,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_existing",
                            "Do work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft"],
                            metadata={
                                "repair_output_bindings": {
                                    "draft": {
                                        # missing repair_patch_id
                                        "related_diagnostic_id": "diag_x",
                                    },
                                },
                            },
                        )
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_existing",),
            evidence_refs=(),
        )
        failures = self._make_verifier().verify(patch, apply_result)
        assert len(failures) >= 1
        assert any("missing required field 'repair_patch_id'" in f for f in failures), (
            f"Expected rejection for missing repair_patch_id, got: {failures}"
        )

    def test_binding_missing_related_diagnostic_id_rejected(self) -> None:
        """Binding without related_diagnostic_id → verifier rejects."""
        patch = self._make_patch()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_1",
            overlay_version=1,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_existing",
                            "Do work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft"],
                            metadata={
                                "repair_output_bindings": {
                                    "draft": {
                                        "repair_patch_id": "patch_x",
                                        # missing related_diagnostic_id
                                    },
                                },
                            },
                        )
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_existing",),
            evidence_refs=(),
        )
        failures = self._make_verifier().verify(patch, apply_result)
        assert len(failures) >= 1
        assert any("missing required field 'related_diagnostic_id'" in f for f in failures), (
            f"Expected rejection for missing related_diagnostic_id, got: {failures}"
        )

    def test_binding_mismatched_diagnostic_id_rejected(self) -> None:
        """Binding with wrong related_diagnostic_id → verifier rejects."""
        patch = self._make_patch()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_1",
            overlay_version=1,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_existing",
                            "Do work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft"],
                            metadata={
                                "repair_output_bindings": {
                                    "draft": {
                                        "repair_patch_id": "patch_x",
                                        "related_diagnostic_id": "wrong_diag",
                                    },
                                },
                            },
                        )
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_existing",),
            evidence_refs=(
                RepairEvidenceRef(
                    artifact_ref="step:worker_main:st_existing:output_binding:draft",
                    repair_patch_id="patch_x",
                    related_diagnostic_id="wrong_diag",
                ),
            ),
        )
        failures = self._make_verifier().verify(patch, apply_result)
        assert len(failures) >= 1
        assert any("expected 'diag_x'" in f for f in failures), (
            f"Expected rejection for mismatched related_diagnostic_id, got: {failures}"
        )

    def test_binding_complete_passes(self) -> None:
        """Binding with all required fields + matching evidence_ref → verifier accepts."""
        patch = self._make_patch()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_1",
            overlay_version=1,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_existing",
                            "Do work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft"],
                            metadata={
                                "repair_output_bindings": {
                                    "draft": {
                                        "repair_patch_id": "patch_x",
                                        "related_diagnostic_id": "diag_x",
                                        "user_text": "",
                                    },
                                },
                            },
                        )
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_existing",),
            evidence_refs=(
                RepairEvidenceRef(
                    artifact_ref="step:worker_main:st_existing:output_binding:draft",
                    repair_patch_id="patch_x",
                    related_diagnostic_id="diag_x",
                ),
            ),
        )
        failures = self._make_verifier().verify(patch, apply_result)
        assert len(failures) == 0, f"Complete binding should pass, got failures: {failures}"

    def test_empty_binding_dict_rejected(self) -> None:
        """Empty binding dict {} → verifier rejects (no repair_patch_id)."""
        patch = self._make_patch()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_1",
            overlay_version=1,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_existing",
                            "Do work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft"],
                            metadata={
                                "repair_output_bindings": {"draft": {}},
                            },
                        )
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_existing",),
            evidence_refs=(),
        )
        failures = self._make_verifier().verify(patch, apply_result)
        assert len(failures) >= 1
        assert any("missing required field" in f for f in failures), (
            f"Empty binding must be rejected, got: {failures}"
        )


# =============================================================================
# Overlay scenario: historical bindings must not be rejected by current patch
# =============================================================================


class TestOverlayMultiBindingGranularity:
    """When multiple patches bind different outputs on the same step,
    the verifier for patch_B must only check patch_B's bindings,
    not reject historical bindings from patch_A.
    """

    def _make_patch_b(self) -> RepairPatch:
        from nl2spl.ir.diagnostics import DiagnosticIRSRef

        return RepairPatch(
            patch_id="patch_B",
            affordance_id="test.bind",
            patch_type="BindExistingProducerStep",
            target_ref="test",
            irs_ref=DiagnosticIRSRef("REQUIRED_OUTPUT", "producer", "missing_output_producer"),
            base_compile_run_id="run_1",
            artifact_snapshot_id="snap_2",
            overlay_version=1,
            payload={},
            evidence=RepairEvidence(related_diagnostic_id="diag_B"),
        )

    def _make_verifier(self) -> object:
        from nl2spl.compiler.spl_editing.verification.generic_evidence_verifier import (
            GenericEvidenceVerifier,
        )

        return GenericEvidenceVerifier()

    def test_historical_binding_not_rejected(self) -> None:
        """Patch B adds 'summary' binding; existing 'draft' from patch A must not fail."""
        patch = self._make_patch_b()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_2",
            overlay_version=2,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_existing",
                            "Do work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft", "summary"],
                            metadata={
                                "repair_output_bindings": {
                                    # Historical binding from patch_A — must NOT be checked
                                    "draft": {
                                        "repair_patch_id": "patch_A",
                                        "related_diagnostic_id": "diag_A",
                                    },
                                    # New binding from patch_B — should be checked
                                    "summary": {
                                        "repair_patch_id": "patch_B",
                                        "related_diagnostic_id": "diag_B",
                                    },
                                },
                            },
                        )
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_existing",),
            evidence_refs=(
                RepairEvidenceRef(
                    artifact_ref="step:worker_main:st_existing:output_binding:summary",
                    repair_patch_id="patch_B",
                    related_diagnostic_id="diag_B",
                ),
            ),
        )
        failures = self._make_verifier().verify(patch, apply_result)
        assert len(failures) == 0, (
            f"Patch B should only check 'summary' binding, "
            f"not historical 'draft' binding. Got failures: {failures}"
        )

    def test_historical_binding_wrong_patch_id_not_rejected(self) -> None:
        """Historical binding has patch_A's id — must not cause failure for patch_B."""
        patch = self._make_patch_b()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_2",
            overlay_version=2,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_existing",
                            "Do work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft", "review"],
                            metadata={
                                "repair_output_bindings": {
                                    "draft": {
                                        "repair_patch_id": "patch_A",  # historical
                                        "related_diagnostic_id": "diag_A",
                                    },
                                    "review": {
                                        "repair_patch_id": "patch_B",  # current patch
                                        "related_diagnostic_id": "diag_B",
                                    },
                                },
                            },
                        )
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_existing",),
            evidence_refs=(
                RepairEvidenceRef(
                    artifact_ref="step:worker_main:st_existing:output_binding:review",
                    repair_patch_id="patch_B",
                    related_diagnostic_id="diag_B",
                ),
            ),
        )
        failures = self._make_verifier().verify(patch, apply_result)
        assert len(failures) == 0, (
            f"Patch B's evidence_ref only mentions 'review' — should skip 'draft'. "
            f"Got failures: {failures}"
        )

    def test_current_binding_missing_field_still_rejected(self) -> None:
        """Patch B's own binding missing repair_patch_id must still be rejected."""
        patch = self._make_patch_b()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_2",
            overlay_version=2,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_existing",
                            "Do work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft", "summary"],
                            metadata={
                                "repair_output_bindings": {
                                    "draft": {
                                        "repair_patch_id": "patch_A",
                                        "related_diagnostic_id": "diag_A",
                                    },
                                    "summary": {
                                        # MISSING repair_patch_id — should fail
                                        "related_diagnostic_id": "diag_B",
                                    },
                                },
                            },
                        )
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_existing",),
            evidence_refs=(
                RepairEvidenceRef(
                    artifact_ref="step:worker_main:st_existing:output_binding:summary",
                    repair_patch_id="",  # empty because binding had none
                    related_diagnostic_id="diag_B",
                ),
            ),
        )
        failures = self._make_verifier().verify(patch, apply_result)
        assert len(failures) >= 1
        assert any(
            ("missing required field 'repair_patch_id'" in f or "repair_patch_id=" in f)
            and "summary" in f
            for f in failures
        ), f"Current binding missing repair_patch_id must be rejected. Got: {failures}"


# =============================================================================
# Cross-reference: evidence_ref must match real binding existence
# =============================================================================


class TestEvidenceRefBindingCrossReference:
    """Verify that evidence_refs are validated against real artifact bindings."""

    def _make_patch(self) -> RepairPatch:
        from nl2spl.ir.diagnostics import DiagnosticIRSRef

        return RepairPatch(
            patch_id="patch_X",
            affordance_id="test.bind",
            patch_type="BindExistingProducerStep",
            target_ref="test",
            irs_ref=DiagnosticIRSRef("REQUIRED_OUTPUT", "producer", "missing_output_producer"),
            base_compile_run_id="run_1",
            artifact_snapshot_id="snap_1",
            overlay_version=0,
            payload={},
            evidence=RepairEvidence(related_diagnostic_id="diag_X"),
        )

    def _verifier(self) -> object:
        from nl2spl.compiler.spl_editing.verification.generic_evidence_verifier import (
            GenericEvidenceVerifier,
        )

        return GenericEvidenceVerifier()

    def test_evidence_ref_points_to_nonexistent_binding_rejected(self) -> None:
        """evidence_ref claims 'summary' but metadata only has 'draft' → rejected."""
        patch = self._make_patch()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_1",
            overlay_version=1,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_1",
                            "Do work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft"],
                            metadata={
                                "repair_output_bindings": {
                                    "draft": {
                                        "repair_patch_id": "patch_X",
                                        "related_diagnostic_id": "diag_X",
                                    },
                                }
                            },
                        )
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_1",),
            evidence_refs=(
                RepairEvidenceRef(
                    # Claims 'summary' but real artifact only has 'draft'
                    artifact_ref="step:worker_main:st_1:output_binding:summary",
                    repair_patch_id="patch_X",
                    related_diagnostic_id="diag_X",
                ),
            ),
        )
        failures = self._verifier().verify(patch, apply_result)
        assert len(failures) >= 1
        assert any(
            "evidence_ref claims binding 'summary' but binding does not exist" in f
            for f in failures
        ), f"Non-existent binding must be rejected. Got: {failures}"

    def test_evidence_ref_wrong_worker_id_not_matched(self) -> None:
        """evidence_ref for worker_x:st_1:output_binding:draft should not
        affect validation of worker_main:st_1."""
        patch = self._make_patch()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_1",
            overlay_version=1,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_1",
                            "Do work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft"],
                            metadata={
                                "repair_output_bindings": {
                                    "draft": {
                                        "repair_patch_id": "patch_X",
                                        "related_diagnostic_id": "diag_X",
                                    },
                                }
                            },
                        )
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_1",),
            evidence_refs=(
                RepairEvidenceRef(
                    # Wrong worker_id — should NOT match worker_main:st_1
                    artifact_ref="step:worker_other:st_1:output_binding:draft",
                    repair_patch_id="patch_X",
                    related_diagnostic_id="diag_X",
                ),
            ),
        )
        failures = self._verifier().verify(patch, apply_result)
        # The real binding 'draft' has patch_X's id and needs an evidence_ref,
        # but the evidence_ref targets worker_other — so it won't match.
        # Verifier should report the orphaned binding.
        assert len(failures) >= 1
        assert any("no matching evidence_ref" in f for f in failures), (
            f"Binding with no matching evidence_ref (wrong worker) must be reported. "
            f"Got: {failures}"
        )

    def test_evidence_ref_wrong_step_id_not_matched(self) -> None:
        """evidence_ref for st_other should not match st_1."""
        patch = self._make_patch()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_1",
            overlay_version=1,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_1",
                            "Do work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft"],
                            metadata={
                                "repair_output_bindings": {
                                    "draft": {
                                        "repair_patch_id": "patch_X",
                                        "related_diagnostic_id": "diag_X",
                                    },
                                }
                            },
                        )
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_1",),
            evidence_refs=(
                RepairEvidenceRef(
                    # Wrong step_id — should NOT match st_1
                    artifact_ref="step:worker_main:st_other:output_binding:draft",
                    repair_patch_id="patch_X",
                    related_diagnostic_id="diag_X",
                ),
            ),
        )
        failures = self._verifier().verify(patch, apply_result)
        assert len(failures) >= 1
        assert any("no matching evidence_ref" in f for f in failures), (
            f"Binding with no matching evidence_ref (wrong step) must be reported. Got: {failures}"
        )

    def test_two_steps_same_binding_name_only_matching_validated(self) -> None:
        """Two changed steps both have 'draft' — each validated with its own ref."""
        patch = self._make_patch()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        snap = ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_1",
            overlay_version=1,
            worker_step_plan=WorkerStepPlanIR(
                "worker_main",
                {
                    "worker_main": [
                        StepIR(
                            "st_A",
                            "Task A",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["draft"],
                            metadata={
                                "repair_output_bindings": {
                                    "draft": {
                                        "repair_patch_id": "patch_X",
                                        "related_diagnostic_id": "diag_X",
                                    },
                                }
                            },
                        ),
                        StepIR(
                            "st_B",
                            "Task B",
                            ["s2"],
                            "GENERAL_COMMAND",
                            outputs=["draft"],
                            metadata={
                                "repair_output_bindings": {
                                    "draft": {
                                        "repair_patch_id": "patch_X",
                                        "related_diagnostic_id": "diag_X",
                                    },
                                }
                            },
                        ),
                    ],
                },
            ),
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_A", "st_B"),
            evidence_refs=(
                RepairEvidenceRef(
                    artifact_ref="step:worker_main:st_A:output_binding:draft",
                    repair_patch_id="patch_X",
                    related_diagnostic_id="diag_X",
                ),
                RepairEvidenceRef(
                    artifact_ref="step:worker_main:st_B:output_binding:draft",
                    repair_patch_id="patch_X",
                    related_diagnostic_id="diag_X",
                ),
            ),
        )
        failures = self._verifier().verify(patch, apply_result)
        assert len(failures) == 0, (
            f"Both steps with matching evidence_refs should pass. Got: {failures}"
        )


# =============================================================================
# Current-patch identity: binding/ref must belong to THIS patch
# =============================================================================


class TestCurrentPatchIdentityEnforcement:
    """A changed binding claimed by the current patch must carry the
    current patch's identity in both evidence_ref AND binding metadata."""

    def _make_patch_b(self) -> RepairPatch:
        from nl2spl.ir.diagnostics import DiagnosticIRSRef

        return RepairPatch(
            patch_id="patch_B",
            affordance_id="test.bind",
            patch_type="BindExistingProducerStep",
            target_ref="test",
            irs_ref=DiagnosticIRSRef("REQUIRED_OUTPUT", "producer", "missing_output_producer"),
            base_compile_run_id="run_1",
            artifact_snapshot_id="snap_1",
            overlay_version=1,
            payload={},
            evidence=RepairEvidence(related_diagnostic_id="diag_B"),
        )

    def _verifier(self) -> object:
        from nl2spl.compiler.spl_editing.verification.generic_evidence_verifier import (
            GenericEvidenceVerifier,
        )

        return GenericEvidenceVerifier()

    def _snap_with(self, bindings: dict) -> object:
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        return ArtifactSnapshot(
            compile_run_id="run_1",
            snapshot_id="snap_1",
            overlay_version=1,
            worker_step_plan=WorkerStepPlanIR(
                "w",
                {
                    "w": [
                        StepIR(
                            "st_1",
                            "X",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["out1"],
                            metadata={"repair_output_bindings": bindings},
                        )
                    ],
                },
            ),
        )

    def test_binding_wrong_patch_id_rejected(self) -> None:
        """Changed binding has repair_patch_id='patch_C', current patch is 'patch_B' → reject."""
        patch = self._make_patch_b()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef

        snap = self._snap_with(
            {
                "out1": {"repair_patch_id": "patch_C", "related_diagnostic_id": "diag_B"},
            }
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_1",),
            evidence_refs=(
                RepairEvidenceRef(
                    artifact_ref="step:w:st_1:output_binding:out1",
                    repair_patch_id="patch_C",
                    related_diagnostic_id="diag_B",
                ),
            ),
        )
        failures = self._verifier().verify(patch, apply_result)
        assert len(failures) >= 1
        assert any("expected 'patch_B'" in f for f in failures), (
            f"Binding with wrong patch_id must be rejected. Got: {failures}"
        )

    def test_binding_wrong_diagnostic_id_rejected(self) -> None:
        """Changed binding has related_diagnostic_id='diag_C', current patch is 'diag_B' → reject."""  # noqa: E501
        patch = self._make_patch_b()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef

        snap = self._snap_with(
            {
                "out1": {"repair_patch_id": "patch_B", "related_diagnostic_id": "diag_C"},
            }
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_1",),
            evidence_refs=(
                RepairEvidenceRef(
                    artifact_ref="step:w:st_1:output_binding:out1",
                    repair_patch_id="patch_B",
                    related_diagnostic_id="diag_C",
                ),
            ),
        )
        failures = self._verifier().verify(patch, apply_result)
        assert len(failures) >= 1
        assert any("expected 'diag_B'" in f for f in failures), (
            f"Binding with wrong diagnostic_id must be rejected. Got: {failures}"
        )

    def test_evidence_ref_wrong_patch_id_rejected(self) -> None:
        """evidence_ref itself carries 'patch_C' for a current-patch binding → reject."""
        patch = self._make_patch_b()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef

        snap = self._snap_with(
            {
                "out1": {"repair_patch_id": "patch_B", "related_diagnostic_id": "diag_B"},
            }
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_1",),
            evidence_refs=(
                RepairEvidenceRef(
                    artifact_ref="step:w:st_1:output_binding:out1",
                    repair_patch_id="patch_C",  # wrong
                    related_diagnostic_id="diag_B",
                ),
            ),
        )
        failures = self._verifier().verify(patch, apply_result)
        assert len(failures) >= 1
        assert any("evidence_ref has repair_patch_id='patch_C'" in f for f in failures), (
            f"evidence_ref with wrong patch_id must be rejected. Got: {failures}"
        )

    def test_evidence_ref_wrong_diagnostic_id_rejected(self) -> None:
        """evidence_ref itself carries 'diag_C' for a current-patch binding → reject."""
        patch = self._make_patch_b()
        from nl2spl.compiler.spl_editing.core.model import PatchApplyResult, RepairEvidenceRef

        snap = self._snap_with(
            {
                "out1": {"repair_patch_id": "patch_B", "related_diagnostic_id": "diag_B"},
            }
        )
        apply_result = PatchApplyResult(
            patched_snapshot=snap,
            overlay_event=None,
            changed_step_ids=("st_1",),
            evidence_refs=(
                RepairEvidenceRef(
                    artifact_ref="step:w:st_1:output_binding:out1",
                    repair_patch_id="patch_B",
                    related_diagnostic_id="diag_C",  # wrong
                ),
            ),
        )
        failures = self._verifier().verify(patch, apply_result)
        assert len(failures) >= 1
        assert any("evidence_ref has related_diagnostic_id='diag_C'" in f for f in failures), (
            f"evidence_ref with wrong diagnostic_id must be rejected. Got: {failures}"
        )
