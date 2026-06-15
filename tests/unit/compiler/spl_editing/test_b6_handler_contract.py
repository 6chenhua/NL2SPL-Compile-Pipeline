"""B6 handler contract tests: generated suggestions must pass validator."""

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.spl_editing.context.required_output_context import (
    RequiredOutputContextBuilder,
)
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairEvidence,
    RepairTarget,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.handlers.missing_output_producer.handler import (
    MissingOutputProducerHandler,
)
from nl2spl.compiler.spl_editing.patches.insert_producer_step.validator import (
    InsertProducerStepValidator,
)
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR
from tests.spl_editing_stub_llm import StubSuggestionLLM


def test_missing_output_handler_generates_valid_payload() -> None:
    """B6 handler: generated InsertProducerStep suggestion passes validator."""
    catalog = RepairCatalogBuilder.from_construct_registry(
        SPLConstructRegistry.default())
    stub_llm = StubSuggestionLLM()
    handler = MissingOutputProducerHandler(stub_llm)
    issue = EditableIssue(
        issue_id="i1", primary_diagnostic_id="d1",
        related_diagnostic_ids=("d1",), issue_group_id=None,
        kind="missing_output_producer",
        target_ref="worker:w_main.output:draft",
        irs_ref=DiagnosticIRSRef(
            construct_type="REQUIRED_OUTPUT", construct_id="x",
            slot_name="producer",
        ),
        missing_slot="producer", source_span_ids=(),
        message="No producer for draft.",
        affordance_ids=("required_output.insert_or_bind_producer",),
        default_affordance_id="required_output.insert_or_bind_producer",
    )
    target = RepairTarget(
        target_ref="worker:w_main.output:draft",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=issue.irs_ref,
        affordance_id="required_output.insert_or_bind_producer",
        construct_path=(), worker_id="w_main",
    )
    context = RequiredOutputContextBuilder().build(
        issue, target, ArtifactSnapshot("snap_1", "run_1", 0))

    entries = catalog.find_by_construct_slot_kind(
        "REQUIRED_OUTPUT", "producer", "missing_output_producer")

    suggestions = handler.generate_suggestions(
        issue, target, context, entries,
        selected_patch_types=("InsertProducerStep",),
    )

    assert len(stub_llm.calls) >= 3
    assert len(suggestions) == 3

    from nl2spl.compiler.spl_editing.core.model import RepairPatch

    # Each suggestion must pass the corresponding validator
    for sug in suggestions:
        snap = ArtifactSnapshot(
            "snap_1", "run_1", 0,
            worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        )
        # Stamp revision + evidence (service does this)
        stamped = RepairPatch(
            patch_id=sug.patch.patch_id,
            affordance_id=sug.patch.affordance_id,
            patch_type=sug.patch.patch_type,
            target_ref=sug.patch.target_ref,
            irs_ref=sug.patch.irs_ref,
            base_compile_run_id=snap.compile_run_id,
            artifact_snapshot_id=snap.snapshot_id,
            overlay_version=snap.overlay_version,
            payload=sug.patch.payload,
            evidence=RepairEvidence(related_diagnostic_id=issue.primary_diagnostic_id),
            verification_lane=sug.patch.verification_lane,
        )
        if sug.patch.patch_type == "InsertProducerStep":
            InsertProducerStepValidator().validate(stamped, snap)
        elif sug.patch.patch_type == "BindExistingProducerStep":
            from nl2spl.compiler.spl_editing.patches.bind_existing_producer_step.validator import (
                BindExistingProducerStepValidator,
            )
            # Need a snap with the bound step existing
            step_snap = ArtifactSnapshot(
                "snap_1", "run_1", 0,
                worker_step_plan=WorkerStepPlanIR("w_main", {
                    "w_main": [StepIR(
                        stamped.payload["step_id"], "Existing", ["s1"],
                        "GENERAL_COMMAND",
                    )],
                }),
            )
            BindExistingProducerStepValidator().validate(stamped, step_snap)
        else:
            raise AssertionError(
                f"Unexpected patch type: {sug.patch.patch_type}")

