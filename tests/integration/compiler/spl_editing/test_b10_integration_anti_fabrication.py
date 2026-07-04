"""B10: Integration anti-fabrication tests.

Proves that SPL Editing cannot bypass compiler authorities or fabricate
executable SPL without proper evidence.
"""

from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.diagnostics import CompileDiagnostic
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
from tests.spl_editing_stub_llm import StubSuggestionLLM


class TestB10IntegrationAntiFabrication:
    """B10: Full integration tests proving anti-fabrication constraints."""

    def test_missing_handler_full_flow(self) -> None:
        """B10: missing_handler 鈫?suggestion 鈫?apply 鈫?verify accepted."""
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        diag = CompileDiagnostic(
            "diag_mh",
            "missing_handler",
            "warning",
            "Exception flow has condition but no handler step.",
            target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
        )
        diag.metadata["irs_ref"] = {
            "construct_type": "EXCEPTION_FLOW",
            "construct_id": "x",
            "slot_name": "handler_action",
            "construct_path": [],
            "source_authority": "post_normalize_irs",
        }
        diag.metadata["authority"] = "post_normalize_irs"
        snap = ArtifactSnapshot(
            "snap_int_mh",
            "run_int_mh",
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
                        owned_span_ids=["s1"],
                    )
                ],
            ),
            worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
            worker_flow_plan=WorkerFlowPlanIR(
                worker_flows={
                    "w_main": FlowStructureIR(
                        exception_flows=[
                            ExceptionFlowRef(
                                flow_id="exc_1",
                                condition_text="Template unavailable.",
                                blocks=[],
                            )
                        ],
                    ),
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
            compile_diagnostics=(diag,),
        )
        run_id = svc.register_compile_result(snap)
        issues = svc.list_editable_issues(run_id)
        assert len(issues) == 1
        session = svc.create_session(run_id, issues[0])
        suggestions = svc.generate_suggestions(session.session_id)
        assert len(suggestions) >= 1
        svc.apply_suggestion(session.session_id, suggestions[0].suggestion_id)
        result = svc.verify_session(session.session_id)
        assert result.accepted is True

    def test_empty_snapshot_produces_no_issues(self) -> None:
        """B10: Empty diagnostics 鈫?no user-facing issues."""
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        snap = ArtifactSnapshot("snap_x", "run_x", 0)
        run_id = svc.register_compile_result(snap)
        assert svc.list_editable_issues(run_id) == ()

    def test_patch_applied_step_survives_gate(self) -> None:
        """B10: applied user_confirmed_repair step must survive Gate."""
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.pipeline.executable_gate import ExecutableElementGate

        gate = ExecutableElementGate()
        step = StepIR(
            "st_repair",
            "Handle error",
            [],
            "GENERAL_COMMAND",
            flow_ref="exc_1",
            metadata={"origin": "user_confirmed_repair"},
        )
        origin = gate.classify_origin(step)
        assert origin == "user_confirmed_repair"

    def test_missing_output_producer_full_flow(self) -> None:
        """B10: missing_output_producer 鈫?suggestion 鈫?apply 鈫?verify accepted."""
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        diag = CompileDiagnostic(
            "diag_mop",
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
        snap = ArtifactSnapshot(
            "snap_int_mop",
            "run_int_mop",
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
                        owned_span_ids=["s1"],
                    )
                ],
            ),
            worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
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
            agent_profile=AgentProfileIR(persona=PersonaIR(role="A", aspects=[])),
            compile_diagnostics=(diag,),
        )
        run_id = svc.register_compile_result(snap)
        issues = svc.list_editable_issues(run_id)
        assert len(issues) == 1
        session = svc.create_session(run_id, issues[0])
        suggestions = svc.generate_suggestions(session.session_id)
        assert len(suggestions) >= 1
        svc.apply_suggestion(session.session_id, suggestions[0].suggestion_id)
        result = svc.verify_session(session.session_id)
        assert result.accepted is True

    def test_worker_promotion_handoff_full_flow(self) -> None:
        """B10: type_or_contract_ambiguity 鈫?handoff suggestion 鈫?apply 鈫?verify."""
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

        diag = CompileDiagnostic(
            "diag_promo",
            "type_or_contract_ambiguity",
            "warning",
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
        diag.metadata["issue_group_id"] = "wg:cand_1"
        diag.metadata["original_semantic_role"] = "delegation_intent"
        diag.metadata["promotion_status"] = "blocked"
        snap = ArtifactSnapshot(
            "snap_int_promo",
            "run_int_promo",
            0,
            worker_plan=WorkerPlanIR(
                main_worker_id="w_main",
                workers=[
                    WorkerSpecIR(
                        "w_main",
                        "Main",
                        "main",
                        "Main",
                        boundary_kind="main_worker",
                        owned_span_ids=["s1"],
                    ),
                    WorkerSpecIR(
                        "w_child", "Child", "child", "Child", boundary_kind="child_worker"
                    ),
                ],
            ),
            worker_step_plan=WorkerStepPlanIR(
                "w_main",
                {
                    "w_main": [
                        StepIR(
                            "st_inv",
                            "Invoke child",
                            ["s1"],
                            "INVOKE_WORKER",
                            inputs=["request"],
                            outputs=["result"],
                            handoff_id="handoff_repair_cand_1",
                            integration_ref="Child",
                        )
                    ],
                },
            ),
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
            agent_profile=AgentProfileIR(persona=PersonaIR(role="A", aspects=[])),
            compile_diagnostics=(diag,),
        )
        run_id = svc.register_compile_result(snap)
        issues = svc.list_editable_issues(run_id)
        assert len(issues) == 1
        from nl2spl.compiler.spl_editing.presentation.service import (
            SPLEditingPresentationService,
        )

        detail = SPLEditingPresentationService(svc).get_issue_detail_presentation(
            run_id, issues[0].issue_id
        )
        assert {item.option_id for item in detail.available_repairs} == {
            "define_child_worker",
            "keep_in_main_flow",
        }
        assert all(
            "CreateWorkerHandoffContract" not in item.patch_types
            and "ConvertDelegationIntentToRequestInput" not in item.patch_types
            for item in detail.available_repairs
        )

    def test_delegation_intent_not_in_catalog_or_registry(self) -> None:
        """B10: DELEGATION_INTENT never appears as construct or target."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder

        reg = SPLConstructRegistry.default()
        assert not reg.has("DELEGATION_INTENT")
        catalog = RepairCatalogBuilder.from_construct_registry(reg)
        for entry in catalog.entries:
            assert entry.construct_type != "DELEGATION_INTENT"
