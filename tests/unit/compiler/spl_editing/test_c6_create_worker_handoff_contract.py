"""C6: CreateWorkerHandoffContract patch tests."""

import pytest

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue, RepairContext, RepairEvidence, RepairPatch, RepairTarget,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.handlers.type_or_contract_ambiguity.handler import (
    TypeOrContractAmbiguityHandler,
)
from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.applier import (
    CreateWorkerHandoffContractApplier,
)
from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.validator import (
    CreateWorkerHandoffContractValidator,
)
from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.verifier import (
    CreateWorkerHandoffContractVerifier,
)
from nl2spl.compiler.spl_editing.verification.lanes import LaneBReplayAdapter
from nl2spl.compiler.spl_editing.verification.runner import VerificationRunner
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
from nl2spl.ir.worker_plan_ir import (
    WorkerFlowPlanIR,
    WorkerBlockPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.symbol_table import SymbolTable


def _snap(**kw) -> ArtifactSnapshot:
    plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[
            WorkerSpecIR("w_main", "MainWorker", "main", "Main",
                          boundary_kind="main_worker", owned_span_ids=["s1"]),
            WorkerSpecIR("w_child", "ChildWorker", "child", "ChildWorker",
                          boundary_kind="child_worker", owned_span_ids=[]),
        ],
    )
    from nl2spl.ir.step_ir import StepIR
    diag = CompileDiagnostic(
        "diag_target", "type_or_contract_ambiguity", "warning",
        "Missing handoff contract.", target_ref="worker_promotion:cand_1",
        blocks_completion=True,
    )
    d = dict(
        snapshot_id="snap_1", compile_run_id="run_1", overlay_version=0,
        worker_plan=plan,
        compile_diagnostics=(diag,),
        worker_step_plan=WorkerStepPlanIR("w_main", {
            "w_main": [StepIR(
                "st_invoke", "Invoke child", ["s1"],
                "INVOKE_WORKER", handoff_id="handoff_repair_cand_1",
                integration_ref="ChildWorker",
                inputs=["req"], outputs=["parent_result"],
            )],
        }),
        worker_flow_plan=WorkerFlowPlanIR(worker_flows={
            "w_main": FlowStructureIR(),
        }),
        worker_block_plan=WorkerBlockPlanIR(worker_blocks={
            "w_main": BlockStructureIR(),
        }),
        resources=ResourceRegistryIR(),
        symbol_table=SymbolTable(),
        agent_profile=AgentProfileIR(
            persona=PersonaIR(role="Assistant", aspects=[]),
        ),
    )
    d.update(kw)
    return ArtifactSnapshot(**d)


def _patch(**kw) -> RepairPatch:
    d = dict(
        patch_id="p1",
        affordance_id="worker_promotion.resolve_contract",
        patch_type="CreateWorkerHandoffContract",
        target_ref="worker_promotion:cand_1",
        irs_ref=DiagnosticIRSRef(
            construct_type="WORKER_PROMOTION", construct_id="x",
            slot_name="promotion_input_contract",
        ),
        base_compile_run_id="run_1", artifact_snapshot_id="snap_1",
        overlay_version=0, verification_lane="B",
        payload={
            "worker_promotion_id": "cand_1",
            "parent_worker_id": "w_main",
            "child_worker_id": "w_child",
            "input_bindings": {"req": "child_req"},
            "output_bindings": {"result": "parent_result"},
            "invocation_point": "main",
            "result_handoff": "parent_result",
        },
        evidence=RepairEvidence(related_diagnostic_id="diag_target"),
    )
    d.update(kw)
    return RepairPatch(**d)


class TestC6Validator:
    def test_valid_payload_passes(self) -> None:
        CreateWorkerHandoffContractValidator().validate(_patch(), _snap())

    def test_missing_child_name_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="child_worker_id"):
            CreateWorkerHandoffContractValidator().validate(
                _patch(payload={"worker_promotion_id": "c", "parent_worker_id": "w"}),
                _snap())

    def test_wrong_affordance_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="Wrong affordance"):
            CreateWorkerHandoffContractValidator().validate(
                _patch(affordance_id="wrong"), _snap())


class TestC6Applier:
    def test_applier_creates_handoff(self) -> None:
        snap = _snap()
        patched, _ = CreateWorkerHandoffContractApplier().apply(_patch(), snap)
        plan = patched.worker_plan
        assert plan is not None
        handoffs = getattr(plan, "handoffs", [])
        assert any(
            getattr(h, "handoff_id", None) == "handoff_repair_cand_1"
            for h in handoffs)

    def test_applier_does_not_mutate_base(self) -> None:
        snap = _snap()
        base_count = len(snap.worker_plan.handoffs)
        CreateWorkerHandoffContractApplier().apply(_patch(), snap)
        assert len(snap.worker_plan.handoffs) == base_count


class TestC6Verifier:
    def test_verifier_finds_handoff(self) -> None:
        verifier = CreateWorkerHandoffContractVerifier()

        class FakeArtifacts:
            gated_worker = object()

        patched = _snap()
        patched, _ = CreateWorkerHandoffContractApplier().apply(
            _patch(), _snap())
        failures = verifier.verify(
            _patch(), _snap(), patched, FakeArtifacts())
        assert failures == ()

    def test_verifier_rejects_missing_handoff(self) -> None:
        verifier = CreateWorkerHandoffContractVerifier()

        class FakeArtifacts:
            gated_worker = object()

        failures = verifier.verify(
            _patch(), _snap(), _snap(), FakeArtifacts())
        assert len(failures) > 0


class TestC6LaneB:
    def test_validator_rejects_nonexistent_parent(self) -> None:
        with pytest.raises(PatchValidationError, match="parent_worker_id"):
            CreateWorkerHandoffContractValidator().validate(
                _patch(payload={
                    "worker_promotion_id": "cand_1",
                    "parent_worker_id": "ghost",
                    "child_worker_id": "w_child",
                }), _snap())

    def test_validator_rejects_nonexistent_child(self) -> None:
        with pytest.raises(PatchValidationError, match="child_worker_id"):
            CreateWorkerHandoffContractValidator().validate(
                _patch(payload={
                    "worker_promotion_id": "cand_1",
                    "parent_worker_id": "w_main",
                    "child_worker_id": "ghost",
                }), _snap())

class TestC6cHandlerContext:
    """C6c: context builder derives child_worker_id from snapshot."""

    def _issue(self):
        return EditableIssue(
            issue_id="i1", primary_diagnostic_id="d1",
            related_diagnostic_ids=("d1",), issue_group_id=None,
            kind="type_or_contract_ambiguity",
            target_ref="worker_promotion:cand_1",
            irs_ref=DiagnosticIRSRef(
                construct_type="WORKER_PROMOTION",
                construct_id="worker_promotion:cand_1",
                slot_name="promotion_input_contract",
            ),
            missing_slot="promotion_input_contract",
            source_span_ids=(), message="test",
            affordance_ids=("worker_promotion.resolve_contract",),
            default_affordance_id="worker_promotion.resolve_contract",
        )

    def _target(self):
        return RepairTarget(
            target_ref="worker_promotion:cand_1",
            target_kind="WORKER_PROMOTION",
            irs_ref=self._issue().irs_ref,
            affordance_id="worker_promotion.resolve_contract",
            construct_path=(), worker_id="w_main",
        )

    def _entries(self):
        return (RepairCatalogEntry(
            entry_id="x",
            affordance_id="worker_promotion.resolve_contract",
            construct_type="WORKER_PROMOTION",
            slot_name="promotion_input_contract",
            diagnostic_kind="type_or_contract_ambiguity",
            supported_patch_types=(
                "CreateWorkerHandoffContract",
                "ConvertDelegationIntentToMainFlowStep",
                "ConvertDelegationIntentToRequestInput",
            ),
        ),)

    def test_unique_child_derived_and_generates_handoff(self) -> None:
        """C6c: builder finds unique child → handler generates handoff."""
        from nl2spl.compiler.spl_editing.context.worker_promotion_context import (
            WorkerPromotionContextBuilder,
        )
        snap = _snap()  # has w_main + w_child
        ctx = WorkerPromotionContextBuilder().build(
            self._issue(), self._target(), snap)
        assert ctx.metadata.get("derived_child_worker_id") == "w_child"

        suggestions = TypeOrContractAmbiguityHandler().generate_suggestions(
            self._issue(), self._target(), ctx, self._entries())
        types = {s.patch.patch_type for s in suggestions}
        assert "CreateWorkerHandoffContract" in types

    def test_no_child_worker_skips_handoff(self) -> None:
        """C6c: no child worker → no handoff suggestion."""
        from nl2spl.compiler.spl_editing.context.worker_promotion_context import (
            WorkerPromotionContextBuilder,
        )
        plan = WorkerPlanIR(
            main_worker_id="w_main",
            workers=[WorkerSpecIR("w_main", "Main", "main", "Main",
                                   boundary_kind="main_worker",
                                   owned_span_ids=["s1"])],
        )
        snap = _snap(worker_plan=plan)
        ctx = WorkerPromotionContextBuilder().build(
            self._issue(), self._target(), snap)
        assert ctx.metadata.get("derived_child_worker_id") is None

        suggestions = TypeOrContractAmbiguityHandler().generate_suggestions(
            self._issue(), self._target(), ctx, self._entries())
        types = {s.patch.patch_type for s in suggestions}
        assert "CreateWorkerHandoffContract" not in types

    def test_multiple_children_skips_handoff(self) -> None:
        """C6c: 2+ child workers → ambiguous → no handoff."""
        from nl2spl.compiler.spl_editing.context.worker_promotion_context import (
            WorkerPromotionContextBuilder,
        )
        plan = WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR("w_main", "Main", "main", "Main",
                              boundary_kind="main_worker",
                              owned_span_ids=["s1"]),
                WorkerSpecIR("w_child_a", "ChildA", "child", "ChildA",
                              boundary_kind="child_worker"),
                WorkerSpecIR("w_child_b", "ChildB", "child", "ChildB",
                              boundary_kind="child_worker"),
            ],
        )
        snap = _snap(worker_plan=plan)
        ctx = WorkerPromotionContextBuilder().build(
            self._issue(), self._target(), snap)
        assert ctx.metadata.get("derived_child_worker_id") is None

        suggestions = TypeOrContractAmbiguityHandler().generate_suggestions(
            self._issue(), self._target(), ctx, self._entries())
        types = {s.patch.patch_type for s in suggestions}
        assert "CreateWorkerHandoffContract" not in types

    def test_generated_patch_passes_validator(self) -> None:
        """C6c: handler-generated handoff suggestion passes validator
        after revision/evidence stamp."""
        from nl2spl.compiler.spl_editing.context.worker_promotion_context import (
            WorkerPromotionContextBuilder,
        )
        snap = _snap()
        ctx = WorkerPromotionContextBuilder().build(
            self._issue(), self._target(), snap)
        suggestions = TypeOrContractAmbiguityHandler().generate_suggestions(
            self._issue(), self._target(), ctx, self._entries())
        hc = next(s for s in suggestions
                   if s.patch.patch_type == "CreateWorkerHandoffContract")
        stamped = RepairPatch(
            patch_id="p1",
            affordance_id=hc.patch.affordance_id,
            patch_type=hc.patch.patch_type,
            target_ref=hc.patch.target_ref,
            irs_ref=hc.patch.irs_ref,
            base_compile_run_id=snap.compile_run_id,
            artifact_snapshot_id=snap.snapshot_id,
            overlay_version=snap.overlay_version,
            payload=hc.patch.payload,
            evidence=RepairEvidence(related_diagnostic_id="diag_target"),
            verification_lane=hc.patch.verification_lane,
        )
        CreateWorkerHandoffContractValidator().validate(stamped, snap)


class TestC6dServiceLevel:
    """C6d: service-level issue → suggestion → apply → verify accepted."""

    def test_handoff_service_flow(self) -> None:
        from nl2spl.compiler.spl_editing.cli import _build_default_service

        svc = _build_default_service()
        # Snapshot with worker promotion diagnostic and unique child worker
        diag = CompileDiagnostic(
            "diag_promo", "type_or_contract_ambiguity", "warning",
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

        plan = WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR("w_main", "Main", "main", "Main",
                              boundary_kind="main_worker",
                              owned_span_ids=["s1"]),
                WorkerSpecIR("w_child", "Child", "child", "ChildWorker",
                              boundary_kind="child_worker"),
            ],
        )
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR
        snap = _snap(
            worker_plan=plan,
            compile_diagnostics=(diag,),
            worker_step_plan=WorkerStepPlanIR("w_main", {
                "w_main": [StepIR(
                    "st_invoke", "Invoke child", ["s1"],
                    "INVOKE_WORKER",
                    handoff_id="handoff_repair_cand_1",
                    integration_ref="Child",
                )],
            }),
        )

        run_id = svc.register_compile_result(snap)
        issues = svc.list_editable_issues(run_id)
        assert len(issues) >= 1
        assert issues[0].kind == "type_or_contract_ambiguity"

        session = svc.create_session(run_id, issues[0])
        suggestions = svc.generate_suggestions(session.session_id)

        hc_sugs = [s for s in suggestions
                    if s.patch.patch_type == "CreateWorkerHandoffContract"]
        assert len(hc_sugs) >= 1, (
            f"Expected CreateWorkerHandoffContract suggestion, "
            f"got {[s.patch.patch_type for s in suggestions]}")

        updated = svc.apply_suggestion(
            session.session_id, hc_sugs[0].suggestion_id)
        assert updated.overlay_version > 0

        result = svc.verify_session(session.session_id)
        assert result.accepted is True
        assert result.lane == "B"

    def test_lane_b_verification_accepted(self) -> None:
        """C6: Handoff patch with Lane B verification — accepted."""
        snap = _snap()
        patched, _ = CreateWorkerHandoffContractApplier().apply(_patch(), snap)
        runner = VerificationRunner(lane_b=LaneBReplayAdapter())
        result = runner.verify(
            _patch(), snap, patched,
            CreateWorkerHandoffContractVerifier(),
        )
        assert result.lane == "B"
        assert result.accepted is True
