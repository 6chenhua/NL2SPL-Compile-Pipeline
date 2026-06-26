"""R5 Stage7ProducerRepairMaterializer unit tests.

Coverage areas (per approved plan):
  [R5-T1] inputs/outputs mapping on StepIR
  [R5-T2] ID allocator produces st{N} and is collision-safe
  [R5-T3] audit metadata completeness (all 8 fields)
  [R5-T4] snapshot immutability --input snapshot.worker_step_plan unchanged
  [R5-T5] validation metadata --invalid payload type is rejected
  [R5-T6] validation metadata --empty producer_goal is rejected
  [R5-T7] validation metadata --REF tag in producer_goal is rejected
  [R5-T8] validation metadata --unknown worker_id is rejected
  [R5-T9] validation metadata --missing canonical_name is rejected
  [R5-T10] registry integration --build_default_materialization_registry registers the plan
  [R5-T11] registry integration --plan_id / materializer_id / authority all consistent
  [R5-T12] full happy-path via service (no handler / applier changes)
"""

from __future__ import annotations

import json

import pytest

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import (
    ConstructRepairIntent,
    InsertProducerStepIntentPayload,
    RepairEvidencePacket,
)
from nl2spl.compiler.spl_editing.materialization import (
    IdAllocator,
    MaterializationDependencyClosure,
    MaterializationInput,
    MaterializationPlan,
    MaterializationRequest,
    MaterializationResult,
    RefRoleConstraint,
    RepairMaterializationService,
    RequiredArtifactField,
    build_default_materialization_registry,
)
from nl2spl.compiler.spl_editing.materialization.errors import (
    DependencyClosureValidationError,
)
from nl2spl.compiler.spl_editing.materialization.stage7 import (
    Stage7ProducerRepairMaterializer,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import (
    ResolvedSelectableRef,
    SelectableRef,
    SelectableRefSet,
)
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

_PLAN_ID = "stage7.step_producer_repair.v1"
_AUTHORITY = "stage7.worker_step_plan"


def _make_irs_ref() -> DiagnosticIRSRef:
    return DiagnosticIRSRef(
        construct_type="REQUIRED_OUTPUT",
        construct_id="required_output_ctx",
        slot_name="producer",
    )


def _make_snapshot(
    *,
    worker_id: str = "w_main",
    existing_step_ids: list[str] | None = None,
) -> ArtifactSnapshot:
    """Minimal snapshot with worker_plan, worker_block_plan, and worker_step_plan."""
    existing = existing_step_ids or ["st1"]
    step_plan = WorkerStepPlanIR(
        main_worker_id=worker_id,
        worker_steps={
            worker_id: [
                StepIR(
                    step_id=sid,
                    text=f"Existing step {sid}",
                    source_span_ids=[],
                    command_type="GENERAL_COMMAND",
                )
                for sid in existing
            ]
        },
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            worker_id: BlockStructureIR(
                main_flow_blocks=[BlockIR(block_id="b1", block_type="main")]
            )
        }
    )
    worker_plan = WorkerPlanIR(
        main_worker_id=worker_id,
        workers=[
            WorkerSpecIR(
                worker_id=worker_id,
                worker_name="Main Worker",
                kind="main",
                purpose="Test",
            )
        ],
        handoffs=[
            WorkerHandoffIR(
                handoff_id="h1",
                from_worker=worker_id,
                to_worker=None,
                api_ref=None,
                mode="invoke",
                condition_text=None,
                ordering="before",
            )
        ],
    )
    return ArtifactSnapshot(
        snapshot_id="snap_r5",
        compile_run_id="run_r5",
        overlay_version=1,
        worker_step_plan=step_plan,
        worker_block_plan=block_plan,
        worker_plan=worker_plan,
    )


def _make_target(
    worker_id: str = "w_main",
    canonical_name: str = "report_summary",
) -> RepairTarget:
    return RepairTarget(
        target_ref=f"required_output:{worker_id}:ctx::{canonical_name}",
        target_kind="REQUIRED_OUTPUT",
        irs_ref=None,
        affordance_id="required_output.insert_or_bind_producer",
        construct_path=("required_output", canonical_name),
        worker_id=worker_id,
        canonical_name=canonical_name,
    )


def _make_issue(worker_id: str = "w_main") -> EditableIssue:
    return EditableIssue(
        issue_id="issue_r5",
        primary_diagnostic_id="diag_r5",
        related_diagnostic_ids=("diag_r5",),
        issue_group_id=None,
        kind="missing_output_producer",
        target_ref=f"required_output:{worker_id}:ctx::report_summary",
        irs_ref=None,
        missing_slot="producer",
        source_span_ids=(),
        message="Missing producer for required output.",
    )


def _make_catalog_entry() -> RepairCatalogEntry:
    return RepairCatalogEntry(
        entry_id="REQUIRED_OUTPUT.producer.missing_output_producer.required_output.insert_or_bind_producer",
        affordance_id="required_output.insert_or_bind_producer",
        construct_type="REQUIRED_OUTPUT",
        slot_name="producer",
        diagnostic_kind="missing_output_producer",
        supported_patch_types=("InsertProducerStep",),
        default_verification_lane="B",
        materialization_plan_id=_PLAN_ID,
        selectable_ref_policy_id="required_output.producer.selectable_refs.v1",
        intent_schema_id="intent.insert_producer_step.v1",
        required_context_facts=("target_output_name",),
        stage_authority=_AUTHORITY,
        editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        user_facing=True,
    )


_UNSET_PAYLOAD = object()  # sentinel


def _make_intent(
    producer_goal: str = "Summarize the final findings into report_summary.",
    selected_ref_ids: tuple[str, ...] = (),
    payload_override=_UNSET_PAYLOAD,
) -> ConstructRepairIntent:
    payload = (
        InsertProducerStepIntentPayload(
            target_output_ref_id="required_output:w_main:ctx::report_summary",
            selected_input_ref_ids=selected_ref_ids,
            producer_goal=producer_goal,
        )
        if payload_override is _UNSET_PAYLOAD
        else payload_override
    )
    return ConstructRepairIntent(
        intent_id="intent_r5",
        issue_id="issue_r5",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="required_output:w_main:ctx::report_summary",
        target_slot_name="producer",
        target_ref_id="required_output:w_main:ctx::report_summary",
        selected_ref_ids=selected_ref_ids,
        materialization_plan_id=_PLAN_ID,
        payload=payload,
    )


def _make_evidence(patch_id: str = "patch_r5") -> RepairEvidencePacket:
    return RepairEvidencePacket(
        evidence_packet_id=f"ep_{patch_id}",
        confirmed_intent_id="intent_r5",
        repair_patch_id=patch_id,
        related_diagnostic_id="diag_r5",
        user_text="Produce the report_summary output.",
    )


def _make_refset_with_target_output(
    worker_id: str = "w_main",
    canonical_name: str = "report_summary",
    input_refs: list[tuple[str, str]] | None = None,
) -> SelectableRefSet:
    """Build a SelectableRefSet with one target_output ref plus optional selectable_input refs."""
    target_ref = SelectableRef(
        ref_id=f"required_output:{worker_id}:ctx::{canonical_name}",
        ref_kind="required_output",
        ref_role="target_output",
        canonical_name=canonical_name,
        display_label=canonical_name,
        worker_id=worker_id,
    )
    refs: list[SelectableRef] = [target_ref]
    if input_refs:
        for ref_id, cname in input_refs:
            refs.append(
                SelectableRef(
                    ref_id=ref_id,
                    ref_kind="step_output",
                    ref_role="selectable_input",
                    canonical_name=cname,
                    display_label=cname,
                    worker_id=worker_id,
                )
            )
    return SelectableRefSet(
        set_id="set_r5",
        issue_id="issue_r5",
        snapshot_id="snap_r5",
        worker_scope=worker_id,
        refs=tuple(refs),
        policy_id="required_output.producer.selectable_refs.v1",
        is_available=True,
    )


def _make_resolved_refs(
    refset: SelectableRefSet,
    roles: dict[str, str] | None = None,
) -> tuple[ResolvedSelectableRef, ...]:
    """Build selected-input resolutions from a refset."""
    resolved = []
    for ref in refset.refs:
        if ref.ref_role == "selectable_input" and (roles is None or ref.ref_id in roles):
            resolved.append(
                ResolvedSelectableRef(
                    ref=ref,
                    resolved_role="selectable_input",
                    scope_matched=True,
                )
            )
    return tuple(resolved)


def _make_plan() -> MaterializationPlan:
    return MaterializationPlan(
        materialization_plan_id=_PLAN_ID,
        patch_type="InsertProducerStep",
        target_construct_type="REQUIRED_OUTPUT",
        target_slot_name="producer",
        stage_authority=_AUTHORITY,
        dependency_closure=MaterializationDependencyClosure(
            required_artifacts=("worker_plan", "worker_block_plan", "worker_step_plan"),
            required_artifact_fields=(
                RequiredArtifactField("worker_step_plan", ("worker_steps",)),
            ),
            required_ref_role_constraints=(
                RefRoleConstraint("target_output", 1, 1, "target"),
                RefRoleConstraint("selectable_input", 0, None, "target"),
            ),
            worker_scope_requirement="main",
            required_id_allocator_namespaces=("step",),
        ),
        editable_artifacts=("WorkerStepPlanIR", "WorkerBlockPlanIR"),
        output_artifacts=("WorkerStepPlanIR",),
        writes_to=("worker_step_plan_pre_normalize",),
        normalizer_required=True,
        stage10_rebuild_required=True,
        verification_lane="B",
        materializer_id=_PLAN_ID,
    )


def _make_allocator(snapshot: ArtifactSnapshot) -> IdAllocator:
    return IdAllocator.from_snapshot(snapshot, ("step",))


def _make_materializer() -> Stage7ProducerRepairMaterializer:
    return Stage7ProducerRepairMaterializer()


def _make_input(
    snapshot: ArtifactSnapshot | None = None,
    target: RepairTarget | None = None,
    intent: ConstructRepairIntent | None = None,
    evidence: RepairEvidencePacket | None = None,
    refset: SelectableRefSet | None = None,
    resolved_refs: tuple[ResolvedSelectableRef, ...] | None = None,
    plan: MaterializationPlan | None = None,
) -> MaterializationInput:
    snap = snapshot or _make_snapshot()
    t = target or _make_target()
    i = intent or _make_intent()
    ev = evidence or _make_evidence()
    rs = refset or _make_refset_with_target_output()
    plan_ = plan or _make_plan()
    alloc = _make_allocator(snap)
    rr = resolved_refs if resolved_refs is not None else _make_resolved_refs(rs)
    return MaterializationInput(
        snapshot=snap,
        issue=_make_issue(),
        target=t,
        catalog_entry=_make_catalog_entry(),
        intent=i,
        refset=rs,
        resolved_refs=rr,
        evidence_packet=ev,
        plan=plan_,
        id_allocator=alloc,
    )


# ---------------------------------------------------------------------------
# [R5-T1] StepIR inputs/outputs mapping
# ---------------------------------------------------------------------------


class TestStepIRInputsOutputs:
    """[R5-T1] Verify inputs and outputs are correctly mapped on the produced StepIR."""

    def test_outputs_contains_canonical_name(self) -> None:
        mat = _make_materializer()
        inp = _make_input(target=_make_target(canonical_name="report_summary"))
        result = mat.materialize(inp)

        new_steps = result.patched_snapshot.worker_step_plan.worker_steps["w_main"]
        produced = next(
            (s for s in new_steps if s.step_id not in {"st1"}),
            None,
        )
        assert produced is not None
        assert "report_summary" in produced.outputs

    def test_inputs_from_selectable_input_refs(self) -> None:
        refset = _make_refset_with_target_output(
            input_refs=[
                ("step_output:w_main:ctx::data_raw", "data_raw"),
                ("step_output:w_main:ctx::data_clean", "data_clean"),
            ]
        )
        resolved = _make_resolved_refs(refset)
        # Only the selectable_input refs (not the target_output) map to inputs
        inp = _make_input(refset=refset, resolved_refs=resolved)
        mat = _make_materializer()
        result = mat.materialize(inp)

        snap = result.patched_snapshot
        steps = snap.worker_step_plan.worker_steps["w_main"]
        produced = next(
            (s for s in steps if "report_summary" in (s.outputs or [])),
            None,
        )
        assert produced is not None
        assert produced.inputs == ["data_raw", "data_clean"]

    def test_no_selectable_inputs_yields_empty_inputs(self) -> None:
        refset = _make_refset_with_target_output()
        inp = _make_input(refset=refset, resolved_refs=())
        result = _make_materializer().materialize(inp)

        steps = result.patched_snapshot.worker_step_plan.worker_steps["w_main"]
        produced = next(
            (s for s in steps if "report_summary" in (s.outputs or [])),
            None,
        )
        assert produced is not None
        assert produced.inputs == []

    def test_target_output_ref_is_rejected_as_resolved_input(self) -> None:
        refset = _make_refset_with_target_output()
        target_ref = refset.refs[0]
        resolved = (
            ResolvedSelectableRef(
                ref=target_ref,
                resolved_role="target_output",
                scope_matched=True,
            ),
        )

        with pytest.raises(DependencyClosureValidationError, match="selectable_input"):
            _make_materializer().materialize(_make_input(refset=refset, resolved_refs=resolved))


# ---------------------------------------------------------------------------
# [R5-T2] ID allocator: allocates st{N}, collision-safe
# ---------------------------------------------------------------------------


class TestIdAllocator:
    """[R5-T2] Verify allocate_step_id yields unique st{N} IDs."""

    def test_allocates_step_id_format(self) -> None:
        mat = _make_materializer()
        inp = _make_input(snapshot=_make_snapshot(existing_step_ids=["st1"]))
        result = mat.materialize(inp)
        new_steps = result.patched_snapshot.worker_step_plan.worker_steps["w_main"]
        # New step is the one not named st1
        new_ids = [s.step_id for s in new_steps if s.step_id != "st1"]
        assert len(new_ids) == 1
        new_id = new_ids[0]
        assert new_id.startswith("st")
        assert new_id[2:].isdigit()

    def test_does_not_collide_with_existing_ids(self) -> None:
        existing = [f"st{i}" for i in range(1, 10)]
        snap = _make_snapshot(existing_step_ids=existing)
        mat = _make_materializer()
        inp = _make_input(snapshot=snap)
        result = mat.materialize(inp)

        all_step_ids = {
            s.step_id for s in result.patched_snapshot.worker_step_plan.worker_steps["w_main"]
        }
        new_id = next((sid for sid in all_step_ids if sid not in set(existing)), None)
        assert new_id is not None
        # Must be > st9 since st1..st9 already exist
        assert int(new_id[2:]) > 9

    def test_changed_step_ids_in_result(self) -> None:
        mat = _make_materializer()
        inp = _make_input()
        result = mat.materialize(inp)
        assert len(result.changed_step_ids) == 1
        assert result.changed_step_ids[0].startswith("st")

    def test_changed_handoff_ids_empty(self) -> None:
        mat = _make_materializer()
        inp = _make_input()
        result = mat.materialize(inp)
        assert result.changed_handoff_ids == ()


# ---------------------------------------------------------------------------
# [R5-T3] Audit metadata completeness
# ---------------------------------------------------------------------------


class TestAuditMetadata:
    """[R5-T3] Verify all 8 audit fields are present and non-empty in StepIR.metadata."""

    _REQUIRED_AUDIT_KEYS = {
        "origin",
        "repair_patch_id",
        "related_diagnostic_id",
        "evidence_packet_id",
        "materialization_authority",
        "materialization_plan_id",
        "consumed_selected_ref_ids",
        "user_text",
    }

    def _get_new_step(self, result: MaterializationResult) -> StepIR:
        steps = result.patched_snapshot.worker_step_plan.worker_steps["w_main"]
        return next(s for s in steps if s.step_id != "st1")

    def test_all_audit_keys_present(self) -> None:
        mat = _make_materializer()
        result = mat.materialize(_make_input())
        step = self._get_new_step(result)
        for key in self._REQUIRED_AUDIT_KEYS:
            assert key in step.metadata, f"Audit key missing: {key!r}"

    def test_origin_is_user_confirmed_repair(self) -> None:
        mat = _make_materializer()
        result = mat.materialize(_make_input())
        step = self._get_new_step(result)
        assert step.metadata["origin"] == "user_confirmed_repair"

    def test_repair_patch_id_matches_evidence(self) -> None:
        ev = _make_evidence(patch_id="my_patch_abc")
        mat = _make_materializer()
        result = mat.materialize(_make_input(evidence=ev))
        step = self._get_new_step(result)
        assert step.metadata["repair_patch_id"] == "my_patch_abc"

    def test_evidence_packet_id_matches(self) -> None:
        ev = _make_evidence(patch_id="ep_src")
        mat = _make_materializer()
        result = mat.materialize(_make_input(evidence=ev))
        step = self._get_new_step(result)
        assert step.metadata["evidence_packet_id"] == ev.evidence_packet_id

    def test_materialization_authority_is_stage7(self) -> None:
        mat = _make_materializer()
        result = mat.materialize(_make_input())
        step = self._get_new_step(result)
        assert step.metadata["materialization_authority"] == _AUTHORITY

    def test_materialization_plan_id_is_correct(self) -> None:
        mat = _make_materializer()
        result = mat.materialize(_make_input())
        step = self._get_new_step(result)
        assert step.metadata["materialization_plan_id"] == _PLAN_ID

    def test_consumed_selected_ref_ids_serialized(self) -> None:
        refset = _make_refset_with_target_output(input_refs=[("step_output:w_main:ctx::x", "x")])
        resolved = _make_resolved_refs(refset)
        mat = _make_materializer()
        result = mat.materialize(_make_input(refset=refset, resolved_refs=resolved))
        step = self._get_new_step(result)
        raw = step.metadata["consumed_selected_ref_ids"]
        parsed = json.loads(raw)
        assert isinstance(parsed, list)
        # Verify result.consumed_selected_ref_ids is also consistent
        assert set(result.consumed_selected_ref_ids) == set(parsed)

    def test_user_text_from_evidence_packet(self) -> None:
        ev = _make_evidence()
        mat = _make_materializer()
        result = mat.materialize(_make_input(evidence=ev))
        step = self._get_new_step(result)
        assert step.metadata["user_text"] == ev.user_text


# ---------------------------------------------------------------------------
# [R5-T4] Snapshot immutability
# ---------------------------------------------------------------------------


class TestSnapshotImmutability:
    """[R5-T4] Verify input snapshot is not mutated."""

    def test_input_snapshot_step_list_unchanged(self) -> None:
        snap = _make_snapshot(existing_step_ids=["st1", "st2"])
        original_steps = list(snap.worker_step_plan.worker_steps["w_main"])

        mat = _make_materializer()
        _result = mat.materialize(_make_input(snapshot=snap))

        # Input snapshot steps still the same objects and count
        actual = snap.worker_step_plan.worker_steps["w_main"]
        assert actual is original_steps or actual == original_steps
        assert len(actual) == 2, "Input snapshot must not gain extra steps"

    def test_patched_snapshot_has_one_more_step(self) -> None:
        snap = _make_snapshot(existing_step_ids=["st1"])
        mat = _make_materializer()
        result = mat.materialize(_make_input(snapshot=snap))

        new_steps = result.patched_snapshot.worker_step_plan.worker_steps["w_main"]
        old_steps = snap.worker_step_plan.worker_steps["w_main"]
        assert len(new_steps) == len(old_steps) + 1

    def test_patched_snapshot_overlay_version_incremented(self) -> None:
        snap = _make_snapshot()
        original_version = snap.overlay_version
        mat = _make_materializer()
        result = mat.materialize(_make_input(snapshot=snap))
        assert result.patched_snapshot.overlay_version == original_version + 1

    def test_final_spl_and_worker_cleared(self) -> None:
        """Materialization must clear final_spl and final_worker to force rebuild."""
        snap = _make_snapshot()
        # Inject a dummy final_spl and final_worker
        snap_with_final = ArtifactSnapshot(
            snapshot_id=snap.snapshot_id,
            compile_run_id=snap.compile_run_id,
            overlay_version=snap.overlay_version,
            worker_step_plan=snap.worker_step_plan,
            worker_block_plan=snap.worker_block_plan,
            worker_plan=snap.worker_plan,
            final_spl="SOME_OLD_SPL",
            final_worker=object(),
        )
        mat = _make_materializer()
        result = mat.materialize(_make_input(snapshot=snap_with_final))
        assert result.patched_snapshot.final_spl is None
        assert result.patched_snapshot.final_worker is None


# ---------------------------------------------------------------------------
# [R5-T5] Wrong payload type 鈫?DependencyClosureValidationError
# ---------------------------------------------------------------------------


class TestValidationBadPayload:
    """[R5-T5] Materializer rejects non-InsertProducerStepIntentPayload."""

    def test_wrong_payload_type_raises(self) -> None:
        intent = _make_intent(payload_override="this is not the right payload type")
        mat = _make_materializer()
        inp = _make_input(intent=intent)
        with pytest.raises(
            DependencyClosureValidationError, match="InsertProducerStepIntentPayload"
        ):
            mat.materialize(inp)

    def test_none_payload_raises(self) -> None:
        intent = _make_intent(payload_override=None)
        mat = _make_materializer()
        inp = _make_input(intent=intent)
        with pytest.raises(
            DependencyClosureValidationError, match="InsertProducerStepIntentPayload"
        ):
            mat.materialize(inp)


# ---------------------------------------------------------------------------
# [R5-T6] Empty producer_goal 鈫?DependencyClosureValidationError
# ---------------------------------------------------------------------------


class TestValidationEmptyGoal:
    """[R5-T6] Materializer rejects empty or whitespace-only producer_goal."""

    @pytest.mark.parametrize("goal", ["", "   ", "\t\n"])
    def test_empty_goal_raises(self, goal: str) -> None:
        intent = _make_intent(producer_goal=goal)
        mat = _make_materializer()
        with pytest.raises(DependencyClosureValidationError, match="producer_goal"):
            mat.materialize(_make_input(intent=intent))


# ---------------------------------------------------------------------------
# [R5-T7] REF tags in producer_goal 鈫?DependencyClosureValidationError
# ---------------------------------------------------------------------------


class TestValidationRefTags:
    """[R5-T7] REF tag variants must all be rejected."""

    @pytest.mark.parametrize(
        "goal",
        [
            "Use <REF id='x'> to produce the output.",
            "Use <ref id='x'> to produce the output.",
            "Use <REF/> to produce the output.",
            "Use <REF:id> to produce the output.",
            "Done </REF> here.",
            "Done </ref> here.",
        ],
    )
    def test_ref_tag_raises(self, goal: str) -> None:
        intent = _make_intent(producer_goal=goal)
        mat = _make_materializer()
        with pytest.raises(DependencyClosureValidationError, match="REF"):
            mat.materialize(_make_input(intent=intent))


# ---------------------------------------------------------------------------
# [R5-T8] Unknown worker_id 鈫?DependencyClosureValidationError
# ---------------------------------------------------------------------------


class TestValidationWorkerExistence:
    """[R5-T8] Materializer fails fast when target worker is not in snapshot."""

    def test_unknown_worker_id_raises(self) -> None:
        target = _make_target(worker_id="w_unknown")
        snap = _make_snapshot(worker_id="w_main")  # w_unknown not in snapshot
        mat = _make_materializer()
        with pytest.raises(DependencyClosureValidationError, match="w_unknown"):
            mat.materialize(_make_input(snapshot=snap, target=target))

    def test_known_worker_id_succeeds(self) -> None:
        target = _make_target(worker_id="w_main")
        snap = _make_snapshot(worker_id="w_main")
        mat = _make_materializer()
        result = mat.materialize(_make_input(snapshot=snap, target=target))
        assert result.patched_snapshot is not snap


# ---------------------------------------------------------------------------
# [R5-T9] Missing canonical_name 鈫?DependencyClosureValidationError
# ---------------------------------------------------------------------------


class TestValidationCanonicalName:
    """[R5-T9] Materializer rejects RepairTarget with empty canonical_name."""

    def test_none_canonical_name_raises(self) -> None:
        target = RepairTarget(
            target_ref="required_output:w_main:ctx::x",
            target_kind="REQUIRED_OUTPUT",
            irs_ref=None,
            affordance_id="required_output.insert_or_bind_producer",
            construct_path=("required_output", "x"),
            worker_id="w_main",
            canonical_name=None,
        )
        mat = _make_materializer()
        with pytest.raises(DependencyClosureValidationError, match="canonical_name"):
            mat.materialize(_make_input(target=target))

    def test_empty_string_canonical_name_raises(self) -> None:
        target = _make_target(canonical_name="")
        mat = _make_materializer()
        with pytest.raises(DependencyClosureValidationError, match="canonical_name"):
            mat.materialize(_make_input(target=target))


# ---------------------------------------------------------------------------
# [R5-T10] Registry integration: plan is registered by default
# ---------------------------------------------------------------------------


class TestRegistryIntegration:
    """[R5-T10] build_default_materialization_registry contains the stage7 plan."""

    def test_default_registry_contains_plan(self) -> None:
        registry = build_default_materialization_registry()
        plan = registry.get(_PLAN_ID)
        assert plan.materialization_plan_id == _PLAN_ID

    def test_default_registry_materializer_type(self) -> None:
        registry = build_default_materialization_registry()
        materializer = registry.get_materializer(_PLAN_ID)
        assert isinstance(materializer, Stage7ProducerRepairMaterializer)


# ---------------------------------------------------------------------------
# [R5-T11] Plan / materializer_id / authority consistency
# ---------------------------------------------------------------------------


class TestPlanConsistency:
    """[R5-T11] materializer_id and stage_authority are all consistent."""

    def test_materializer_id_matches_plan_id(self) -> None:
        registry = build_default_materialization_registry()
        plan = registry.get(_PLAN_ID)
        materializer = registry.get_materializer(_PLAN_ID)
        assert plan.materializer_id == materializer.materializer_id

    def test_stage_authority_matches(self) -> None:
        registry = build_default_materialization_registry()
        plan = registry.get(_PLAN_ID)
        materializer = registry.get_materializer(_PLAN_ID)
        assert plan.stage_authority == materializer.stage_authority == _AUTHORITY

    def test_result_fields_match_plan_and_materializer(self) -> None:
        mat = _make_materializer()
        result = mat.materialize(_make_input())
        assert result.materialization_plan_id == _PLAN_ID
        assert result.materializer_id == _PLAN_ID
        assert result.materialization_authority == _AUTHORITY


# ---------------------------------------------------------------------------
# [R5-T12] Full happy-path via RepairMaterializationService
# ---------------------------------------------------------------------------


class TestServiceHappyPath:
    """[R5-T12] Full service call with no mock materializer; uses real Stage7 materializer."""

    def _build_request_no_inputs(
        self,
        evidence_patch_id: str = "patch_r5",
    ) -> MaterializationRequest:
        """Build a valid MaterializationRequest with no selectable input refs.

        The service's ref lineage check requires:
          intent.selected_ref_ids == evidence.confirmed_selected_ref_ids == resolved_ref IDs

        For the no-inputs scenario, all three are empty (target_output is
        excluded from selected_ref_ids --it is identified by target_ref_id).
        """
        snap = _make_snapshot()
        refset = _make_refset_with_target_output(canonical_name="report_summary")

        return MaterializationRequest(
            snapshot=snap,
            issue=_make_issue(),
            target=_make_target(),
            catalog_entry=_make_catalog_entry(),
            # selected_ref_ids=() 鈫?no selectable input refs
            intent=_make_intent(selected_ref_ids=()),
            refset=refset,
            # resolved_refs=() 鈫?no user-selected input refs (target_output excluded)
            resolved_refs=(),
            evidence_packet=RepairEvidencePacket(
                evidence_packet_id=f"ep_{evidence_patch_id}",
                confirmed_intent_id="intent_r5",
                repair_patch_id=evidence_patch_id,
                related_diagnostic_id="diag_r5",
                user_text="Produce the report_summary output.",
                # confirmed_selected_ref_ids must match intent.selected_ref_ids
                confirmed_selected_ref_ids=(),
            ),
        )

    def test_service_returns_valid_result(self) -> None:
        registry = build_default_materialization_registry()
        service = RepairMaterializationService(registry)
        result = service.materialize(self._build_request_no_inputs())

        # Plan / authority match
        assert result.materialization_plan_id == _PLAN_ID
        assert result.materializer_id == _PLAN_ID
        assert result.materialization_authority == _AUTHORITY
        assert len(result.changed_step_ids) == 1

        # Snapshot integrity
        new_steps = result.patched_snapshot.worker_step_plan.worker_steps["w_main"]
        assert len(new_steps) == 2  # st1 (existing) + new step
        produced = next(s for s in new_steps if s.step_id != "st1")
        assert "report_summary" in produced.outputs
        assert produced.metadata["origin"] == "user_confirmed_repair"
        assert result.dependency_validation_metadata == {
            "plan_id": _PLAN_ID,
            "has_pre_normalize": True,
        }

    def test_service_result_evidence_packet_id_matches(self) -> None:
        registry = build_default_materialization_registry()
        service = RepairMaterializationService(registry)
        result = service.materialize(self._build_request_no_inputs(evidence_patch_id="xp_42"))
        assert result.evidence_packet_id == "ep_xp_42"
