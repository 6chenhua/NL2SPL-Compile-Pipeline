"""B6: InsertProducerStep and BindExistingProducerStep patch tests."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairEvidence, RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.insert_producer_step.applier import (
    InsertProducerStepApplier,
)
from nl2spl.compiler.spl_editing.patches.insert_producer_step.validator import (
    InsertProducerStepValidator,
)
from nl2spl.compiler.spl_editing.patches.insert_producer_step.verifier import (
    InsertProducerStepVerifier,
)
from nl2spl.compiler.spl_editing.patches.bind_existing_producer_step.applier import (
    BindExistingProducerStepApplier,
)
from nl2spl.compiler.spl_editing.patches.bind_existing_producer_step.validator import (
    BindExistingProducerStepValidator,
)
from nl2spl.compiler.spl_editing.patches.bind_existing_producer_step.verifier import (
    BindExistingProducerStepVerifier,
)
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR


def _snap(**kw: object) -> ArtifactSnapshot:
    d: dict[str, object] = dict(
        snapshot_id="snap_1", compile_run_id="run_1", overlay_version=0,
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
    )
    d.update(kw)
    return ArtifactSnapshot(**d)  # type: ignore[arg-type]


def _patch(patch_type: str, **kw: object) -> RepairPatch:
    d: dict[str, object] = dict(
        patch_id="p1", affordance_id="required_output.insert_or_bind_producer",
        patch_type=patch_type,
        target_ref="worker:w_main.output:draft",
        irs_ref=DiagnosticIRSRef(construct_type="REQUIRED_OUTPUT",
                                  construct_id="x", slot_name="producer"),
        base_compile_run_id="run_1", artifact_snapshot_id="snap_1",
        overlay_version=0, verification_lane="A",
        payload={
            "worker_id": "w_main", "output_name": "draft",
            "producer_text": "Draft the document.",
            "command_type": "GENERAL_COMMAND",
        },
        evidence=RepairEvidence(related_diagnostic_id="diag_target",
                                 user_text="Add producer."),
    )
    d.update(kw)
    return RepairPatch(**d)  # type: ignore[arg-type]


# ===========================================================================
# B6-1: InsertProducerStep
# ===========================================================================


class TestB6InsertProducerStep:
    def test_validator_passes(self) -> None:
        InsertProducerStepValidator().validate(
            _patch("InsertProducerStep"), _snap())

    def test_missing_output_name_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="output_name"):
            InsertProducerStepValidator().validate(
                _patch("InsertProducerStep", payload={
                    "worker_id": "w_main", "producer_text": "T",
                    "command_type": "GENERAL_COMMAND",
                }), _snap())

    def test_stale_revision_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="compile_run_id"):
            InsertProducerStepValidator().validate(
                _patch("InsertProducerStep", base_compile_run_id="other"),
                _snap())

    def test_applier_creates_step(self) -> None:
        snap = _snap()
        patched, _ = InsertProducerStepApplier().apply(
            _patch("InsertProducerStep"), snap)
        wsp = patched.worker_step_plan
        assert wsp is not None
        steps = wsp.worker_steps["w_main"]
        assert len(steps) == 1
        assert steps[0].metadata.get("origin") == "user_confirmed_repair"
        assert "draft" in steps[0].outputs

    def test_applier_does_not_mutate_base(self) -> None:
        snap = _snap()
        before = len(snap.worker_step_plan.worker_steps["w_main"])
        InsertProducerStepApplier().apply(_patch("InsertProducerStep"), snap)
        assert len(snap.worker_step_plan.worker_steps["w_main"]) == before

    def test_verifier_finds_producer(self) -> None:
        verifier = InsertProducerStepVerifier()
        patch = _patch("InsertProducerStep")

        class FakeGated:
            steps = [StepIR("st_x", "Draft", ["s1"], "GENERAL_COMMAND",
                             outputs=["draft"],
                             metadata={"origin": "user_confirmed_repair"})]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = "draft: [GENERAL_COMMAND] Draft the document."

        failures = verifier.verify(patch, _snap(), _snap(), FakeArtifacts())
        assert failures == ()

    def test_verifier_producer_index_rejects_non_renderable_step(self) -> None:
        """B6: Step without source spans or user_confirmed_repair
        → ProducerIndex rejects → verifier fails."""
        verifier = InsertProducerStepVerifier()

        class FakeGated:
            steps = [StepIR("st_x", "Draft", [], "GENERAL_COMMAND",
                             outputs=["draft"])]
            # No source_span_ids + no user_confirmed_repair → non-renderable

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        failures = verifier.verify(
            _patch("InsertProducerStep"), _snap(), _snap(), FakeArtifacts())
        assert len(failures) > 0
        assert "ProducerIndex" in failures[0]


# ===========================================================================
# B6-2: BindExistingProducerStep
# ===========================================================================


class TestB6BindExistingProducerStep:
    def test_validator_passes_with_renderable_step(self) -> None:
        snap = _snap(worker_step_plan=WorkerStepPlanIR(
            "w_main", {"w_main": [StepIR(
                "st_existing", "Existing work", ["s1"],
                "GENERAL_COMMAND", outputs=["other"],
            )]},
        ))
        BindExistingProducerStepValidator().validate(
            _patch("BindExistingProducerStep", payload={
                "worker_id": "w_main", "step_id": "st_existing",
                "output_name": "draft",
            }), snap)

    def test_validator_rejects_non_renderable_step(self) -> None:
        snap = _snap(worker_step_plan=WorkerStepPlanIR(
            "w_main", {"w_main": [StepIR(
                "st_synth", "Synthetic", [], "GENERAL_COMMAND",
            )]},
        ))
        with pytest.raises(PatchValidationError, match="no source evidence"):
            BindExistingProducerStepValidator().validate(
                _patch("BindExistingProducerStep", payload={
                    "worker_id": "w_main", "step_id": "st_synth",
                    "output_name": "draft",
                }), snap)

    def test_applier_binds_output(self) -> None:
        snap = _snap(worker_step_plan=WorkerStepPlanIR(
            "w_main", {"w_main": [StepIR(
                "st_existing", "Work", ["s1"], "GENERAL_COMMAND",
                outputs=["other"],
            )]},
        ))
        patched, _ = BindExistingProducerStepApplier().apply(
            _patch("BindExistingProducerStep", payload={
                "worker_id": "w_main", "step_id": "st_existing",
                "output_name": "draft",
            }), snap)
        step = patched.worker_step_plan.worker_steps["w_main"][0]
        assert "draft" in step.outputs
        # Bind does NOT change the step's executable origin — only adds binding provenance
        assert "repair_output_bindings" in step.metadata
        assert "draft" in step.metadata["repair_output_bindings"]

    def test_bind_validator_scoped_to_worker_id(self) -> None:
        """B6: Bind rejects step in different worker."""
        snap = _snap(worker_step_plan=WorkerStepPlanIR(
            "w_main", {
                "w_main": [],
                "child": [StepIR("st_child", "Child work", ["s1"],
                                  "GENERAL_COMMAND")],
            },
        ))
        with pytest.raises(PatchValidationError, match="not found"):
            BindExistingProducerStepValidator().validate(
                _patch("BindExistingProducerStep", payload={
                    "worker_id": "w_main", "step_id": "st_child",
                    "output_name": "draft",
                }), snap)


class TestB6InsertionTarget:
    """B6: insertion_target restriction enforced."""

    def test_block_insertion_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="insertion_target"):
            InsertProducerStepValidator().validate(
                _patch("InsertProducerStep", payload={
                    "worker_id": "w_main", "output_name": "draft",
                    "producer_text": "T", "command_type": "GENERAL_COMMAND",
                    "insertion_target": "block",
                }), _snap())

    def test_non_empty_block_ref_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="block_ref"):
            InsertProducerStepValidator().validate(
                _patch("InsertProducerStep", payload={
                    "worker_id": "w_main", "output_name": "draft",
                    "producer_text": "T", "command_type": "GENERAL_COMMAND",
                    "block_ref": "b1",
                }), _snap())

    def test_non_string_block_ref_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="block_ref"):
            InsertProducerStepValidator().validate(
                _patch("InsertProducerStep", payload={
                    "worker_id": "w_main", "output_name": "draft",
                    "producer_text": "T", "command_type": "GENERAL_COMMAND",
                    "block_ref": 0,
                }), _snap())


class TestB6BindVerifier:
    """B6: Bind verifier checks provenance."""

    def test_verifier_accepts_matching_provenance(self) -> None:
        verifier = BindExistingProducerStepVerifier()
        patch = _patch("BindExistingProducerStep", payload={
            "worker_id": "w_main", "step_id": "st_x",
            "output_name": "draft",
        })

        class FakeGated:
            steps = [StepIR("st_x", "Draft", ["s1"], "GENERAL_COMMAND",
                             outputs=["draft"],
                             metadata={"repair_output_bindings": {
                                 "draft": {
                                     "repair_patch_id": "p1",
                                     "related_diagnostic_id": "diag_target",
                                 },
                             }})]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        failures = verifier.verify(patch, _snap(), _snap(), FakeArtifacts())
        assert failures == ()

    def test_verifier_rejects_wrong_patch_id(self) -> None:
        verifier = BindExistingProducerStepVerifier()

        class FakeGated:
            steps = [StepIR("st_x", "Draft", ["s1"], "GENERAL_COMMAND",
                             outputs=["draft"],
                             metadata={"repair_output_bindings": {
                                 "draft": {
                                     "repair_patch_id": "other_patch",
                                     "related_diagnostic_id": "diag_target",
                                 },
                             }})]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        failures = verifier.verify(
            _patch("BindExistingProducerStep", payload={
                "worker_id": "w_main", "step_id": "st_x",
                "output_name": "draft",
            }), _snap(), _snap(), FakeArtifacts())
        assert len(failures) > 0
        assert "repair_patch_id" in failures[0]

    def test_verifier_rejects_wrong_diagnostic_id(self) -> None:
        verifier = BindExistingProducerStepVerifier()

        class FakeGated:
            steps = [StepIR("st_x", "Draft", ["s1"], "GENERAL_COMMAND",
                             outputs=["draft"],
                             metadata={"repair_output_bindings": {
                                 "draft": {
                                     "repair_patch_id": "p1",
                                     "related_diagnostic_id": "wrong_diag",
                                 },
                             }})]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        failures = verifier.verify(
            _patch("BindExistingProducerStep", payload={
                "worker_id": "w_main", "step_id": "st_x",
                "output_name": "draft",
            }), _snap(), _snap(), FakeArtifacts())
        assert len(failures) > 0
        assert "related_diagnostic_id" in failures[0]


class TestB6WorkerScope:
    """B6: Worker scope enforced."""

    def test_bind_applier_only_modifies_target_worker(self) -> None:
        """B6: Bind applier scoped to worker_id — doesn't modify other workers."""
        snap = _snap(worker_step_plan=WorkerStepPlanIR(
            "w_main", {
                "w_main": [StepIR("st_shared", "Main work", ["s1"],
                                    "GENERAL_COMMAND")],
                "child": [StepIR("st_shared", "Child work", ["s2"],
                                  "GENERAL_COMMAND")],
            },
        ))
        patched, _ = BindExistingProducerStepApplier().apply(
            _patch("BindExistingProducerStep", payload={
                "worker_id": "w_main", "step_id": "st_shared",
                "output_name": "draft",
            }), snap)
        # main worker step got binding
        main_step = patched.worker_step_plan.worker_steps["w_main"][0]
        assert "draft" in main_step.outputs
        # child worker step unchanged
        child_step = patched.worker_step_plan.worker_steps["child"][0]
        assert "draft" not in child_step.outputs
        assert "repair_output_bindings" not in child_step.metadata

    def test_insert_rejects_unknown_worker(self) -> None:
        snap = _snap(worker_step_plan=WorkerStepPlanIR(
            "w_main", {"w_known": []},
        ))
        with pytest.raises(PatchValidationError, match="not found"):
            InsertProducerStepValidator().validate(
                _patch("InsertProducerStep",
                       target_ref="worker:unknown_worker.output:draft",
                       payload={
                           "worker_id": "unknown_worker",
                           "output_name": "draft",
                           "producer_text": "T",
                           "command_type": "GENERAL_COMMAND",
                       }), snap)
