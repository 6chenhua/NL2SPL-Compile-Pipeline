"""Phase 1: verify that contract/binding status fields survive parser +
serializer roundtrip and that helpers behave correctly.
"""

from __future__ import annotations

from nl2spl.ir.worker_contract_status import (
    binding_side_satisfied,
    contract_side_satisfied,
    derive_contract_status,
)
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    InputBindingIR,
    WorkerHandoffIR,
    WorkerSpecIR,
)


def _field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(name, "text", True, f"{name} field", source)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestContractSideSatisfied:
    def test_known_present_fields_satisfied(self) -> None:
        assert contract_side_satisfied([_field("x")], "known_present") is True

    def test_known_empty_satisfied(self) -> None:
        assert contract_side_satisfied([], "known_empty") is True

    def test_unknown_not_satisfied(self) -> None:
        assert contract_side_satisfied([], "unknown") is False

    def test_binding_side_known_present_satisfied(self) -> None:
        assert binding_side_satisfied([InputBindingIR("p", "c", True)], "known_present") is True

    def test_binding_side_unknown_not_satisfied(self) -> None:
        assert binding_side_satisfied([], "unknown") is False


class TestDeriveContractStatus:
    def test_non_empty_fields_are_known_present(self) -> None:
        assert derive_contract_status([_field("x")]) == "known_present"

    def test_empty_fields_no_declaration_is_unknown(self) -> None:
        assert derive_contract_status([]) == "unknown"

    def test_empty_fields_with_declared_known_empty_and_source(self) -> None:
        assert derive_contract_status(
            [], declared_status="known_empty", source="adapter_hard_fact",
        ) == "known_empty"

    def test_empty_fields_declared_known_empty_but_no_source_is_unknown(self) -> None:
        assert derive_contract_status(
            [], declared_status="known_empty", source=None,
        ) == "unknown"

    def test_empty_fields_declared_known_present_is_warned_unknown(self) -> None:
        assert derive_contract_status(
            [], declared_status="known_present",
        ) == "unknown"


# ---------------------------------------------------------------------------
# Serializer roundtrip
# ---------------------------------------------------------------------------


class TestWorkerSpecIRSerializerRoundtrip:
    def test_roundtrip_preserves_unknown_defaults(self) -> None:
        w = WorkerSpecIR(
            worker_id="w1", worker_name="Test", kind="child",
            purpose="Test", owned_span_ids=[],
        )
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
            WorkerSpecIRSerializer,
        )
        ser = WorkerSpecIRSerializer()
        data = ser.to_canonical(w)
        w2 = ser.from_canonical(data)
        assert w2.input_contract_status == "unknown"
        assert w2.output_contract_status == "unknown"
        assert w2.partial_reason is None

    def test_roundtrip_preserves_known_empty_with_source(self) -> None:
        w = WorkerSpecIR(
            worker_id="w1", worker_name="Test", kind="child",
            purpose="Test", owned_span_ids=[],
            input_contract_status="known_empty",
            output_contract_status="known_present",
            input_contract_status_source="adapter_hard_fact_explicit_empty",
            output_contract_status_source="user_confirmed_repair",
            partial_reason="missing_input_contract",
        )
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
            WorkerSpecIRSerializer,
        )
        ser = WorkerSpecIRSerializer()
        data = ser.to_canonical(w)
        w2 = ser.from_canonical(data)
        assert w2.input_contract_status == "known_empty"
        assert w2.output_contract_status == "known_present"
        assert w2.input_contract_status_source == "adapter_hard_fact_explicit_empty"
        assert w2.output_contract_status_source == "user_confirmed_repair"
        assert w2.partial_reason == "missing_input_contract"

    def test_old_payload_without_status_defaults_to_unknown(self) -> None:
        """Legacy payload without status fields should parse as unknown."""
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
            WorkerSpecIRSerializer,
        )
        legacy = {
            "$type": "WorkerSpecIR",
            "worker_id": "w1", "worker_name": "Old", "kind": "child",
            "purpose": "Old purpose", "owned_span_ids": [],
            "input_contract": [], "output_contract": [],
            "depends_on": [], "constraints": [], "boundary_kind": "bounded_subtask",
            # No status fields
        }
        w = WorkerSpecIRSerializer().from_canonical(legacy)
        assert w.input_contract_status == "unknown"
        assert w.output_contract_status == "unknown"


class TestWorkerHandoffIRSerializerRoundtrip:
    def test_roundtrip_preserves_binding_status(self) -> None:
        h = WorkerHandoffIR(
            handoff_id="h1", from_worker="w_main", to_worker="w_child",
            api_ref=None, mode="invoke", condition_text=None,
            ordering="after",
            input_binding_status="known_present",
            output_binding_status="known_empty",
            input_binding_status_source="user_confirmed_repair",
            output_binding_status_source="adapter_hard_fact_explicit_empty",
            materialization_status="confirmed_empty_contract",
        )
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
            WorkerHandoffIRSerializer,
        )
        ser = WorkerHandoffIRSerializer()
        data = ser.to_canonical(h)
        h2 = ser.from_canonical(data)
        assert h2.input_binding_status == "known_present"
        assert h2.output_binding_status == "known_empty"
        assert h2.input_binding_status_source == "user_confirmed_repair"
        assert h2.materialization_status == "confirmed_empty_contract"

    def test_old_payload_without_status_defaults(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
            WorkerHandoffIRSerializer,
        )
        legacy = {
            "$type": "WorkerHandoffIR",
            "handoff_id": "h1", "from_worker": "w_main", "to_worker": None,
            "api_ref": None, "mode": "invoke", "condition_text": None,
            "ordering": "after",
            "input_bindings": [], "output_bindings": [],
            # No status fields
        }
        h = WorkerHandoffIRSerializer().from_canonical(legacy)
        assert h.input_binding_status == "unknown"
        assert h.output_binding_status == "unknown"
        assert h.materialization_status == "partial_contract_unknown"


class TestCandidateTaskUnitIRSerializerRoundtrip:
    def test_roundtrip_preserves_contract_status(self) -> None:
        c = CandidateTaskUnitIR(
            candidate_id="c1", source_span_ids=["s1"],
            task_text="T", purpose="P", candidate_kind="bounded_subtask",
            input_contract_status="unknown",
            output_contract_status="known_present",
            input_contract_status_source=None,
            output_contract_status_source="adapter_hard_fact",
        )
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
            CandidateTaskUnitIRSerializer,
        )
        ser = CandidateTaskUnitIRSerializer()
        data = ser.to_canonical(c)
        c2 = ser.from_canonical(data)
        assert c2.input_contract_status == "unknown"
        assert c2.output_contract_status == "known_present"
        assert c2.output_contract_status_source == "adapter_hard_fact"

    def test_old_payload_without_status_defaults_to_unknown(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.serialization.serializers_plan import (
            CandidateTaskUnitIRSerializer,
        )
        legacy = {
            "$type": "CandidateTaskUnitIR",
            "candidate_id": "c1", "source_span_ids": [],
            "task_text": "T", "purpose": "P", "candidate_kind": "bounded_subtask",
            "possible_inputs": [], "possible_outputs": [],
            "signals": [], "risks": [],
        }
        c = CandidateTaskUnitIRSerializer().from_canonical(legacy)
        assert c.input_contract_status == "unknown"
        assert c.output_contract_status == "unknown"


# ---------------------------------------------------------------------------
# Parser roundtrip
# ---------------------------------------------------------------------------


class TestPlanParserReadsStatusFields:
    def test_parse_candidate_reads_status(self) -> None:
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.plan_parser import (
            PlanParserMixin,
        )

        class _P(PlanParserMixin):
            def _parse_contract_field(self, data): return data
            def _str_list(self, val, default=None): return list(val) if val else (default or [])
            def _parse_signal_values(self, v): return ([], [])
            def _parse_positive_signals(self, v): return []
            def _parse_invoke_location_hint(self, data): return None
            def _parse_failure_policy(self, data): return None

        raw = {
            "candidate_id": "c1", "source_span_ids": [], "task_text": "T",
            "purpose": "P", "candidate_kind": "bounded_subtask",
            "possible_inputs": [], "possible_outputs": [],
            "signals": [], "risks": [],
            "input_contract_status": "known_empty",
            "output_contract_status": "known_present",
            "input_contract_status_source": "adapter_hard_fact",
            "output_contract_status_source": "user_confirmed_repair",
        }
        c = _P()._parse_candidate(raw)
        assert c.input_contract_status == "known_empty"
        assert c.output_contract_status == "known_present"
        assert c.input_contract_status_source == "adapter_hard_fact"
        assert c.output_contract_status_source == "user_confirmed_repair"

    def test_parse_candidate_without_status_defaults_unknown(self) -> None:
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.plan_parser import (
            PlanParserMixin,
        )

        class _P(PlanParserMixin):
            def _parse_contract_field(self, data): return data
            def _str_list(self, val, default=None): return list(val) if val else (default or [])
            def _parse_signal_values(self, v): return ([], [])
            def _parse_positive_signals(self, v): return []
            def _parse_invoke_location_hint(self, data): return None
            def _parse_failure_policy(self, data): return None

        raw = {
            "candidate_id": "c1", "source_span_ids": [], "task_text": "T",
            "purpose": "P", "candidate_kind": "bounded_subtask",
            "possible_inputs": [], "possible_outputs": [],
            "signals": [], "risks": [],
        }
        c = _P()._parse_candidate(raw)
        assert c.input_contract_status == "unknown"

    def test_parse_worker_reads_status(self) -> None:
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.plan_parser import (
            PlanParserMixin,
        )

        class _P(PlanParserMixin):
            def _parse_contract_field(self, data): return data
            def _str_list(self, val, default=None): return list(val) if val else (default or [])
            def _parse_signal_values(self, v): return ([], [])
            def _parse_positive_signals(self, v): return []
            def _parse_invoke_location_hint(self, data): return None
            def _parse_failure_policy(self, data): return None
            def _parse_positive_signals(self, v): return []

        raw = {
            "worker_id": "w1", "worker_name": "W", "kind": "child",
            "purpose": "P", "owned_span_ids": [],
            "input_contract": [], "output_contract": [],
            "depends_on": [], "constraints": [], "boundary_kind": "bounded_subtask",
            "decision_evidence": [], "reason": "",
            "input_contract_status": "known_present",
            "output_contract_status": "known_empty",
            "partial_reason": "missing_output_contract",
        }
        w = _P()._parse_worker(raw)
        assert w.input_contract_status == "known_present"
        assert w.output_contract_status == "known_empty"
        assert w.partial_reason == "missing_output_contract"

    def test_parse_handoff_reads_status(self) -> None:
        from nl2spl.pipeline.stages.stage3_5_worker_boundary_planner.plan_parser import (
            PlanParserMixin,
        )

        class _P(PlanParserMixin):
            def _parse_invoke_location_hint(self, data): return None
            def _parse_failure_policy(self, data): return None

        raw = {
            "handoff_id": "h1", "from_worker": "w_main", "to_worker": "w_child",
            "api_ref": None, "mode": "invoke", "condition_text": None,
            "ordering": "after",
            "input_bindings": [], "output_bindings": [],
            "invoke_location_hint": {}, "failure_policy": {},
            "input_binding_status": "known_present",
            "output_binding_status": "unknown",
            "materialization_status": "complete",
        }
        h = _P()._parse_handoff(raw)
        assert h.input_binding_status == "known_present"
        assert h.output_binding_status == "unknown"
        assert h.materialization_status == "complete"


# ---------------------------------------------------------------------------
# SPL Editing patch writes status
# ---------------------------------------------------------------------------


class TestCreateWorkerHandoffContractPatchStatus:
    def test_applier_writes_known_present_binding_status(self) -> None:
        from nl2spl.compiler.spl_editing.core.model import RepairPatch
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.applier import (
            CreateWorkerHandoffContractApplier,
        )
        from nl2spl.ir.diagnostics import DiagnosticIRSRef
        from nl2spl.ir.worker_plan_ir import WorkerPlanIR

        patch = RepairPatch(
            patch_id="p1", affordance_id="worker_promotion.resolve_contract",
            patch_type="CreateWorkerHandoffContract",
            target_ref="worker_promotion:del_s30",
            irs_ref=DiagnosticIRSRef(
                construct_type="WORKER_PROMOTION", construct_id="del_s30",
                slot_name="promotion_input_contract",
            ),
            base_compile_run_id="run_1", artifact_snapshot_id="snap_1",
            overlay_version=0,
            payload={
                "parent_worker_id": "worker_main",
                "child_worker_id": "worker_child",
                "worker_promotion_id": "del_s30",
                "input_bindings": {"request": "source_list"},
                "output_bindings": {"evidence": "result"},
                "invocation_point": "main",
                "result_handoff": "return",
                "input_binding_status": "known_present",
                "output_binding_status": "known_present",
                "input_binding_status_source": "user_confirmed_repair",
                "output_binding_status_source": "user_confirmed_repair",
            },
            verification_lane="B",
        )
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            handoffs=[],
            candidates=[],
            decisions=[],
            rejected_candidates=[],
        )
        snap = ArtifactSnapshot(
            snapshot_id="snap_1", compile_run_id="run_1",
            overlay_version=0, worker_plan=plan,
        )
        applier = CreateWorkerHandoffContractApplier()
        import pytest

        from nl2spl.compiler.spl_editing.core.errors import SPLEditingError

        with pytest.raises(SPLEditingError, match="RepairMaterializationService"):
            applier.apply(patch, snap)

    def test_known_empty_with_empty_bindings_produces_confirmed_empty(self) -> None:
        """known_empty + empty bindings + source → confirmed_empty_contract."""
        from nl2spl.compiler.spl_editing.core.model import RepairPatch
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.ir.diagnostics import DiagnosticIRSRef
        from nl2spl.ir.worker_plan_ir import WorkerPlanIR

        patch = RepairPatch(
            patch_id="p1", affordance_id="worker_promotion.resolve_contract",
            patch_type="CreateWorkerHandoffContract",
            target_ref="worker_promotion:del_s30",
            irs_ref=DiagnosticIRSRef(
                construct_type="WORKER_PROMOTION", construct_id="del_s30",
                slot_name="promotion_input_contract",
            ),
            base_compile_run_id="run_1", artifact_snapshot_id="snap_1",
            overlay_version=0,
            payload={
                "parent_worker_id": "worker_main",
                "child_worker_id": "worker_child",
                "worker_promotion_id": "del_s30",
                "input_bindings": {},
                "output_bindings": {},
                "invocation_point": "main",
                "input_binding_status": "known_empty",
                "output_binding_status": "known_empty",
                "input_binding_status_source": "user_confirmed_repair",
                "output_binding_status_source": "user_confirmed_repair",
            },
            verification_lane="B",
        )
        plan = WorkerPlanIR(
            main_worker_id="worker_main", workers=[], handoffs=[],
            candidates=[], decisions=[], rejected_candidates=[],
        )
        snap = ArtifactSnapshot(
            snapshot_id="snap_1", compile_run_id="run_1",
            overlay_version=0, worker_plan=plan,
        )
        import pytest

        from nl2spl.compiler.spl_editing.core.errors import SPLEditingError
        from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.applier import (
            CreateWorkerHandoffContractApplier,
        )

        with pytest.raises(SPLEditingError, match="RepairMaterializationService"):
            CreateWorkerHandoffContractApplier().apply(patch, snap)

    def test_validator_rejects_known_empty_with_non_empty_bindings(self) -> None:
        """known_empty + non-empty bindings → validator rejects."""
        import pytest

        from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
        from nl2spl.compiler.spl_editing.core.model import RepairEvidence, RepairPatch
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.validator import (
            CreateWorkerHandoffContractValidator,
        )
        from nl2spl.ir.diagnostics import DiagnosticIRSRef
        from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR

        patch = RepairPatch(
            patch_id="p1", affordance_id="worker_promotion.resolve_contract",
            patch_type="CreateWorkerHandoffContract",
            target_ref="worker_promotion:del_s30",
            irs_ref=DiagnosticIRSRef(
                construct_type="WORKER_PROMOTION", construct_id="del_s30",
                slot_name="promotion_input_contract",
            ),
            base_compile_run_id="run_1", artifact_snapshot_id="snap_1",
            overlay_version=0,
            payload={
                "parent_worker_id": "worker_main",
                "child_worker_id": "worker_child",
                "worker_promotion_id": "del_s30",
                "input_bindings": {"req": "src"},
                "input_binding_status": "known_empty",
                "input_binding_status_source": "user_confirmed_repair",
                "output_binding_status": "known_present",
                "output_bindings": {"out": "res"},
                "invocation_point": "main",
            },
            evidence=RepairEvidence(related_diagnostic_id="diag_1"),
            verification_lane="B",
        )
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR("worker_main", "Main", "main", "Main"),
                WorkerSpecIR("worker_child", "Child", "child", "Child"),
            ],
            handoffs=[], candidates=[], decisions=[], rejected_candidates=[],
        )
        snap = ArtifactSnapshot(
            snapshot_id="snap_1", compile_run_id="run_1",
            overlay_version=0, worker_plan=plan,
            worker_step_plan=object(),
        )
        with pytest.raises(PatchValidationError, match="known_empty"):
            CreateWorkerHandoffContractValidator().validate(patch, snap)

    def test_validator_rejects_known_empty_without_source(self) -> None:
        """known_empty without source → validator rejects."""
        import pytest

        from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
        from nl2spl.compiler.spl_editing.core.model import RepairEvidence, RepairPatch
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.validator import (
            CreateWorkerHandoffContractValidator,
        )
        from nl2spl.ir.diagnostics import DiagnosticIRSRef
        from nl2spl.ir.worker_plan_ir import WorkerPlanIR, WorkerSpecIR

        patch = RepairPatch(
            patch_id="p1", affordance_id="worker_promotion.resolve_contract",
            patch_type="CreateWorkerHandoffContract",
            target_ref="worker_promotion:del_s30",
            irs_ref=DiagnosticIRSRef(
                construct_type="WORKER_PROMOTION", construct_id="del_s30",
                slot_name="promotion_input_contract",
            ),
            base_compile_run_id="run_1", artifact_snapshot_id="snap_1",
            overlay_version=0,
            payload={
                "parent_worker_id": "worker_main",
                "child_worker_id": "worker_child",
                "worker_promotion_id": "del_s30",
                "input_bindings": {},
                "output_bindings": {"out": "res"},
                "input_binding_status": "known_empty",
                "output_binding_status": "known_present",
                "invocation_point": "main",
            },
            evidence=RepairEvidence(related_diagnostic_id="diag_1"),
            verification_lane="B",
        )
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR("worker_main", "Main", "main", "Main"),
                WorkerSpecIR("worker_child", "Child", "child", "Child"),
            ],
            handoffs=[], candidates=[], decisions=[], rejected_candidates=[],
        )
        snap = ArtifactSnapshot(
            snapshot_id="snap_1", compile_run_id="run_1",
            overlay_version=0, worker_plan=plan,
            worker_step_plan=object(),
        )
        with pytest.raises(PatchValidationError, match="source"):
            CreateWorkerHandoffContractValidator().validate(patch, snap)


# ---------------------------------------------------------------------------
# Parser: known_empty + empty bindings + source
# ---------------------------------------------------------------------------


class TestParserKnownEmptyHandoff:
    """Parser must accept known_empty + empty bindings + source."""

    def test_known_empty_with_source_and_empty_bindings_accepted(self) -> None:
        from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload

        raw = (
            '{"patch_type":"CreateWorkerHandoffContract","title":"T",'
            '"explanation":"E",'
            '"payload":{"input_bindings":{},"output_bindings":{"a":"b"},'
            '"input_binding_status":"known_empty",'
            '"input_binding_status_source":"adapter_hard_fact",'
            '"output_binding_status":"known_present",'
            '"invocation_point":"main"}}'
        )
        data = parse_suggestion_payload(raw, ("CreateWorkerHandoffContract",))
        assert data["payload"]["input_binding_status"] == "known_empty"
        assert data["payload"]["input_bindings"] == {}

    def test_known_empty_without_source_rejected(self) -> None:
        import pytest

        from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
        from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload

        raw = (
            '{"patch_type":"CreateWorkerHandoffContract","title":"T",'
            '"explanation":"E",'
            '"payload":{"input_bindings":{},"output_bindings":{"a":"b"},'
            '"input_binding_status":"known_empty",'
            '"invocation_point":"main"}}'
        )
        with pytest.raises(PatchValidationError, match="source"):
            parse_suggestion_payload(raw, ("CreateWorkerHandoffContract",))

    def test_known_empty_with_non_empty_bindings_rejected(self) -> None:
        import pytest

        from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
        from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload

        raw = (
            '{"patch_type":"CreateWorkerHandoffContract","title":"T",'
            '"explanation":"E",'
            '"payload":{"input_bindings":{"req":"src"},"output_bindings":{"a":"b"},'
            '"input_binding_status":"known_empty",'
            '"input_binding_status_source":"user_confirmed_repair",'
            '"invocation_point":"main"}}'
        )
        with pytest.raises(PatchValidationError, match="known_empty"):
            parse_suggestion_payload(raw, ("CreateWorkerHandoffContract",))

    def test_unknown_status_rejected(self) -> None:
        import pytest

        from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
        from nl2spl.compiler.spl_editing.handlers.parser import parse_suggestion_payload

        raw = (
            '{"patch_type":"CreateWorkerHandoffContract","title":"T",'
            '"explanation":"E",'
            '"payload":{"input_bindings":{"req":"src"},"output_bindings":{"a":"b"},'
            '"input_binding_status":"unknown",'
            '"invocation_point":"main"}}'
        )
        with pytest.raises(PatchValidationError, match="known_present"):
            parse_suggestion_payload(raw, ("CreateWorkerHandoffContract",))

    def test_verifier_rejects_wrong_materialization_status(self) -> None:
        """Verifier must reject a mat_status that doesn't match the derivation."""
        from nl2spl.compiler.spl_editing.core.model import (
            RepairEvidence,
            RepairPatch,
        )
        from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
        from nl2spl.compiler.spl_editing.patches.create_worker_handoff_contract.verifier import (
            CreateWorkerHandoffContractVerifier,
        )
        from nl2spl.ir.diagnostics import DiagnosticIRSRef
        from nl2spl.ir.worker_plan_ir import (
            InputBindingIR,
            OutputBindingIR,
            WorkerHandoffIR,
            WorkerPlanIR,
        )

        # Build a handoff with known_present + non-empty bindings but
        # materialization_status="confirmed_empty_contract" (wrong).
        base = ArtifactSnapshot("snap_1", "run_1", 0)
        handoff = WorkerHandoffIR(
            handoff_id="handoff_repair_del_s30",
            from_worker="w_main", to_worker="w_child",
            api_ref=None, mode="invoke", condition_text=None,
            ordering="after",
            input_bindings=[InputBindingIR("req", "src", True)],
            output_bindings=[OutputBindingIR("out", "res", True, "set")],
            input_binding_status="known_present",
            output_binding_status="known_present",
            input_binding_status_source="user_confirmed_repair",
            output_binding_status_source="user_confirmed_repair",
            materialization_status="confirmed_empty_contract",
        )
        patched_plan = WorkerPlanIR(
            main_worker_id="w_main", workers=[],
            handoffs=[handoff], candidates=[], decisions=[],
            rejected_candidates=[],
        )
        patched = ArtifactSnapshot(
            "snap_2", "run_1", 1, worker_plan=patched_plan,
        )
        patch = RepairPatch(
            patch_id="p1", affordance_id="worker_promotion.resolve_contract",
            patch_type="CreateWorkerHandoffContract",
            target_ref="worker_promotion:del_s30",
            irs_ref=DiagnosticIRSRef(
                construct_type="WORKER_PROMOTION", construct_id="del_s30",
                slot_name="promotion_input_contract",
            ),
            base_compile_run_id="run_1", artifact_snapshot_id="snap_1",
            overlay_version=0,
            payload={
                "worker_promotion_id": "del_s30",
                "parent_worker_id": "w_main",
                "child_worker_id": "w_child",
                "input_bindings": {"req": "src"},
                "output_bindings": {"out": "res"},
                "input_binding_status": "known_present",
                "output_binding_status": "known_present",
                "input_binding_status_source": "user_confirmed_repair",
                "output_binding_status_source": "user_confirmed_repair",
            },
            evidence=RepairEvidence(related_diagnostic_id="diag_1"),
            verification_lane="B",
        )
        # The wrapper class that the verifier expects
        class _Artifacts:
            gated_worker = "any"
        failures = CreateWorkerHandoffContractVerifier().verify(
            patch, base, patched, _Artifacts(),
        )
        assert any("materialization_status" in f for f in failures), (
            f"Expected mat_status mismatch failure, got: {failures}")
