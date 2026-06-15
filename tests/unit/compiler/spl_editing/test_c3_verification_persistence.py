"""C3: Verification result persistence tests."""

import pytest

from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    VerificationResult,
)
from nl2spl.compiler.spl_editing.core.registry import SPLEditingRuntimeRegistry
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.core.service import SPLEditingService
from nl2spl.compiler.spl_editing.storage.verification_result_store import (
    VerificationResultStore,
)
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef


class TestC3VerificationResultStore:
    """C3: Store persists and queries results."""

    def test_append_and_get_latest(self) -> None:
        store = VerificationResultStore()
        r1 = VerificationResult("s1", "p1", False, "A")
        r2 = VerificationResult("s1", "p2", True, "A")
        store.append("s1", r1)
        store.append("s1", r2)
        assert store.get_latest("s1") is r2

    def test_list_all_returns_history(self) -> None:
        store = VerificationResultStore()
        r1 = VerificationResult("s1", "p1", False, "A")
        r2 = VerificationResult("s1", "p2", True, "A")
        store.append("s1", r1)
        store.append("s1", r2)
        assert store.list_all("s1") == (r1, r2)

    def test_rejected_is_stored(self) -> None:
        store = VerificationResultStore()
        r = VerificationResult("s1", "p1", False, "A",
                                failure_reasons=("bad",))
        store.append("s1", r)
        assert store.get_latest("s1").accepted is False

    def test_unknown_session_raises(self) -> None:
        store = VerificationResultStore()
        with pytest.raises(KeyError, match="no_such"):
            store.get_latest("no_such")

    def test_list_all_unknown_raises(self) -> None:
        store = VerificationResultStore()
        with pytest.raises(KeyError, match="no_such"):
            store.list_all("no_such")

    def test_multiple_sessions_independent(self) -> None:
        store = VerificationResultStore()
        store.append("a", VerificationResult("a", "p1", True, "A"))
        store.append("b", VerificationResult("b", "p2", False, "A"))
        assert store.get_latest("a").accepted is True
        assert store.get_latest("b").accepted is False

    def test_mismatched_session_id_raises(self) -> None:
        store = VerificationResultStore()
        with pytest.raises(ValueError, match="does not match"):
            store.append("s1", VerificationResult("other", "p1", True, "A"))


class TestC3ServiceLevelPersistence:
    """C3: Service-level persistence tests 鈥?verify_session stores results."""

    def _make_mh_service(self):
        reg = SPLEditingRuntimeRegistry()
        from nl2spl.compiler.spl_editing.context.exception_flow_context import (
            ExceptionFlowContextBuilder,
        )
        from nl2spl.compiler.spl_editing.handlers.missing_handler.handler import (
            MissingHandlerRepairHandler,
        )
        from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.applier import (
            AddExceptionHandlerStepApplier,
        )
        from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.preview import (
            AddExceptionHandlerStepPreviewer,
        )
        from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.validator import (
            AddExceptionHandlerStepValidator,
        )
        from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.verifier import (
            AddExceptionHandlerStepVerifier,
        )
        from nl2spl.compiler.spl_editing.patches.registry import PatchBundle
        from nl2spl.compiler.spl_editing.targets.exception_flow import (
            ExceptionFlowTargetResolver,
        )
        from nl2spl.compiler.spl_editing.verification.lanes import (
            LaneAReplayAdapter,
            VerificationArtifacts,
        )
        from tests.spl_editing_stub_llm import StubSuggestionLLM

        class _StubLane(LaneAReplayAdapter):
            def replay(self, snapshot):
                return VerificationArtifacts()

        reg.target_resolvers.register("exception_flow_target", ExceptionFlowTargetResolver())
        reg.context_builders.register("exception_flow_context", ExceptionFlowContextBuilder())
        reg.handlers.register("missing_handler", MissingHandlerRepairHandler(StubSuggestionLLM()))
        from nl2spl.compiler.spl_editing.cli import (
            _build_missing_handler_context_builder,
            _build_missing_handler_prompt_renderer,
        )
        reg.llm_context_builders.register(
            "missing_handler",
            _build_missing_handler_context_builder(),
        )
        reg.prompt_renderers.register(
            "missing_handler",
            _build_missing_handler_prompt_renderer(),
        )
        from nl2spl.compiler.spl_editing.core.model import PatchTypeContract
        reg.patches.register("AddExceptionHandlerStep", PatchBundle(
            patch_type="AddExceptionHandlerStep",
            validator=AddExceptionHandlerStepValidator(),
            applier=AddExceptionHandlerStepApplier(),
            verifier=AddExceptionHandlerStepVerifier(),
            previewer=AddExceptionHandlerStepPreviewer(),
            contract=PatchTypeContract(
                patch_type="AddExceptionHandlerStep",
                produces_step_ir=True,
                evidence_targets=("step",),
            ),
        ))
        return SPLEditingService(reg, lane_a=_StubLane())

    def _make_mh_issue(self):
        return EditableIssue(
            issue_id="i1", primary_diagnostic_id="d1",
            related_diagnostic_ids=("d1",), issue_group_id=None,
            kind="missing_handler",
            target_ref="worker:w_main.exception_flow:exc_1",
            irs_ref=DiagnosticIRSRef(
                construct_type="EXCEPTION_FLOW", construct_id="x",
                slot_name="handler_action",
            ),
            missing_slot="handler_action", source_span_ids=(),
            message="No handler.", authority="post_normalize_irs",
            affordance_ids=("exception_flow.add_handler_step",),
            default_affordance_id="exception_flow.add_handler_step",
        )

    def test_verify_session_persists_result(self) -> None:
        svc = self._make_mh_service()
        diag = CompileDiagnostic(
            "d1", "missing_handler", "warning", "No handler.",
            target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
        )
        diag.metadata["irs_ref"] = {
            "construct_type": "EXCEPTION_FLOW", "construct_id": "x",
            "slot_name": "handler_action", "construct_path": [],
            "source_authority": "post_normalize_irs",
        }
        diag.metadata["authority"] = "post_normalize_irs"
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
        from nl2spl.ir.symbol_table import SymbolTable
        from nl2spl.ir.worker_ir import ExceptionFlowRef
        from nl2spl.ir.worker_plan_ir import (
            WorkerBlockPlanIR,
            WorkerFlowPlanIR,
            WorkerPlanIR,
            WorkerSpecIR,
            WorkerStepPlanIR,
        )
        snap = ArtifactSnapshot(
            "snap_1", "run_1", 0,
            worker_plan=WorkerPlanIR(
                main_worker_id="w_main",
                workers=[WorkerSpecIR("w_main", "MainWorker", "main", "Main",
                                       boundary_kind="main_worker")],
            ),
            worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
            worker_flow_plan=WorkerFlowPlanIR(worker_flows={
                "w_main": FlowStructureIR(
                    exception_flows=[ExceptionFlowRef(
                        flow_id="exc_1", condition_text="Error.", blocks=[],
                    )],
                ),
            }),
            worker_block_plan=WorkerBlockPlanIR(worker_blocks={
                "w_main": BlockStructureIR(),
            }),
            resources=ResourceRegistryIR(),
            symbol_table=SymbolTable(),
            agent_profile=AgentProfileIR(persona=PersonaIR(role="A", aspects=[])),
            compile_diagnostics=(diag,),
        )
        run_id = svc.register_compile_result(snap)
        session = svc.create_session(run_id, self._make_mh_issue())
        suggestions = svc.generate_suggestions(session.session_id)
        svc.apply_suggestion(session.session_id, suggestions[0].suggestion_id)
        svc.verify_session(session.session_id)

        result = svc.get_latest_verification(session.session_id)
        assert isinstance(result, VerificationResult)

    def test_no_verification_raises(self) -> None:
        svc = self._make_mh_service()
        diag = CompileDiagnostic(
            "d1", "missing_handler", "warning", "No handler.",
            target_ref="x", blocks_completion=True,
        )
        diag.metadata["irs_ref"] = {
            "construct_type": "EXCEPTION_FLOW", "construct_id": "x",
            "slot_name": "handler_action", "construct_path": [],
            "source_authority": "post_normalize_irs",
        }
        diag.metadata["authority"] = "post_normalize_irs"
        snap = ArtifactSnapshot("snap_1", "run_1", 0, compile_diagnostics=(diag,))
        svc.register_compile_result(snap)
        session = svc.create_session("run_1", self._make_mh_issue())
        with pytest.raises(KeyError, match="session"):
            svc.get_latest_verification(session.session_id)

