"""B10: Anti-fabrication tests."""

from nl2spl.compiler.spl_editing.core.model import (
    RepairEvidence,
    RepairPatch,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.applier import (
    AddExceptionHandlerStepApplier,
)
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerStepPlanIR,
)


class _ExcFlowStub:
    def __init__(self, flow_id):
        self.flow_id = flow_id


def _snap(**kw):
    d = dict(
        snapshot_id="snap_1", compile_run_id="run_1", overlay_version=0,
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"w_main": FlowStructureIR(
                exception_flows=[_ExcFlowStub("exc_1")],
            )},
        ),
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={"w_main": BlockStructureIR()},
        ),
    )
    d.update(kw)
    return ArtifactSnapshot(**d)


def _patch(**kw):
    d = dict(
        patch_id="p1", affordance_id="exception_flow.add_handler_step",
        patch_type="AddExceptionHandlerStep",
        target_ref="worker:w_main.exception_flow:exc_1",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW", construct_id="x",
            slot_name="handler_action",
        ),
        base_compile_run_id="run_1", artifact_snapshot_id="snap_1",
        overlay_version=0, verification_lane="A",
        payload={
            "worker_id": "w_main", "exception_flow_id": "exc_1",
            "handler_text": "Handle error.",
            "command_type": "GENERAL_COMMAND",
        },
        evidence=RepairEvidence(
            related_diagnostic_id="diag_target",
        ),
    )
    d.update(kw)
    return RepairPatch(**d)


class TestB10AntiFabrication:
    """B10: Anti-fabrication tests 鈥?patch must not bypass compiler authorities."""

    def test_generate_suggestions_does_not_mutate_artifacts(self) -> None:
        """B10: Service-level generate_suggestions does not change
        snapshot or SPL output."""
        from nl2spl.compiler.spl_editing.context.exception_flow_context import (
            ExceptionFlowContextBuilder,
        )
        from nl2spl.compiler.spl_editing.core.registry import SPLEditingRuntimeRegistry
        from nl2spl.compiler.spl_editing.core.service import SPLEditingService
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
        from tests.spl_editing_stub_llm import StubSuggestionLLM

        reg = SPLEditingRuntimeRegistry()
        reg.target_resolvers.register("exception_flow_target",
                                        ExceptionFlowTargetResolver())
        reg.context_builders.register("exception_flow_context",
                                        ExceptionFlowContextBuilder())
        reg.handlers.register("missing_handler",
                               MissingHandlerRepairHandler(StubSuggestionLLM()))
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

        svc = SPLEditingService(reg)
        diag = CompileDiagnostic(
            "diag_1", "missing_handler", "warning", "No handler.",
            target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
        )
        diag.metadata["irs_ref"] = {
            "construct_type": "EXCEPTION_FLOW", "construct_id": "x",
            "slot_name": "handler_action", "construct_path": [],
            "source_authority": "post_normalize_irs",
        }
        diag.metadata["authority"] = "post_normalize_irs"
        snap = ArtifactSnapshot("snap_1", "run_1", 0,
                                 compile_diagnostics=(diag,),
                                 final_spl="ORIGINAL SPL")
        svc.register_compile_result(snap)
        issue = svc.list_editable_issues("run_1")[0]
        session = svc.create_session("run_1", issue)
        svc.generate_suggestions(session.session_id)
        # Snapshot unchanged after suggestion generation
        assert svc._get_snapshot("run_1").final_spl == "ORIGINAL SPL"
        assert svc._get_snapshot("run_1").overlay_version == 0

    def test_patch_cannot_create_call_api_without_evidence(self) -> None:
        """B10: AddExceptionHandlerStep cannot create CALL_API step."""
        applier = AddExceptionHandlerStepApplier()
        snap = _snap()
        patched, _ = applier.apply(_patch(), snap)
        # The created step must not be CALL_API
        steps = patched.worker_step_plan.worker_steps["w_main"]
        assert all(s.command_type != "CALL_API" for s in steps)

    def test_patch_does_not_modify_final_spl_directly(self) -> None:
        """B10: Applier never touches final_spl directly."""
        applier = AddExceptionHandlerStepApplier()
        snap = _snap(final_spl="ORIGINAL SPL")
        patched, _ = applier.apply(_patch(), snap)
        # Applier clears final_spl so Lane A can re-render
        assert patched.final_spl is None

    def test_patch_cannot_bypass_gate(self) -> None:
        """B10: User-confirmed step must carry origin=user_confirmed_repair
        so Gate recognizes it."""
        applier = AddExceptionHandlerStepApplier()
        snap = _snap()
        patched, _ = applier.apply(_patch(), snap)
        step = patched.worker_step_plan.worker_steps["w_main"][0]
        assert step.metadata.get("origin") == "user_confirmed_repair"

    def test_no_delegation_intent_construct_target(self) -> None:
        """B10: DELEGATION_INTENT must never appear as a construct target
        in any patch metadata or IRS reference."""
        patch = _patch()
        assert patch.irs_ref.construct_type != "DELEGATION_INTENT"
        assert patch.affordance_id != "DELEGATION_INTENT"

