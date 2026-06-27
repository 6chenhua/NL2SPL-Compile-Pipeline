"""R12.0 characterization tests for missing_handler default path and R0-R11 safety boundaries."""

from __future__ import annotations

import json

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent
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


def _missing_handler_diag() -> CompileDiagnostic:
    diag = CompileDiagnostic(
        "diag_mh",
        "missing_handler",
        "warning",
        "No handler action defined.",
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
    diag.metadata["repairability"] = "editable"
    diag.metadata["issue_group_id"] = "g_mh"
    diag.metadata["issue_role"] = "primary"
    return diag


def _snapshot() -> ArtifactSnapshot:
    return ArtifactSnapshot(
        "snap_mh",
        "run_mh",
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
        compile_diagnostics=(_missing_handler_diag(),),
    )


class TestR12ContractBaseline:
    def test_missing_handler_uses_legacy_patch_types_in_catalog(self) -> None:
        """Verify that the default catalog (built without a strategy registry) uses
        legacy patch_type semantics and does not carry R12+ strategy metadata.

        R12.0 characterization: supported_patch_types is the semantic source.
        When R12.2 adds optional strategy fields to RepairCatalogEntry, those
        fields must default to None/False when no strategy_registry is supplied
        to RepairCatalogBuilder — this test locks in that backward-compatible
        contract.
        """
        registry = SPLConstructRegistry.default()
        # Build without strategy_registry — this is the default R0-R11 path
        catalog = RepairCatalogBuilder.from_construct_registry(registry)
        entries = catalog.find_by_construct_slot_kind(
            "EXCEPTION_FLOW",
            "handler_action",
            "missing_handler",
        )
        assert len(entries) == 1
        entry = entries[0]
        assert entry.affordance_id == "exception_flow.add_handler_step"
        assert entry.supported_patch_types == ("AddExceptionHandlerStep",)

        # R12.0 characterization: no active R12+ strategy metadata on this entry.
        # If RepairCatalogEntry later gains optional strategy fields (R12.2+),
        # those fields must be None/falsy when no strategy registry is supplied.
        # We check values, not field existence, so this test remains valid after R12.2.
        repair_strategy_id = getattr(entry, "repair_strategy_id", None)
        strategy_display_label = getattr(entry, "strategy_display_label", None)
        preview_required = getattr(entry, "preview_required", False)
        assert repair_strategy_id is None, (
            f"R12.0 baseline: entry must have no repair_strategy_id, got {repair_strategy_id!r}"
        )
        assert strategy_display_label is None, (
            f"R12.0 baseline: entry must have no strategy_display_label, got {strategy_display_label!r}"
        )
        assert not preview_required, (
            f"R12.0 baseline: entry must not require preview, got {preview_required!r}"
        )

    def test_missing_handler_characterization_flow(self) -> None:
        """Verify that missing_handler suggestion generation and materialization apply succeed on R0-R11 default paths."""
        llm = StubSuggestionLLM(
            {
                "patch_type": "AddExceptionHandlerStep",
                "title": "Stub suggestion",
                "explanation": "This is stub option.",
                "payload": {
                    "handler_text": "Handle error",
                    "command_type": "GENERAL_COMMAND",
                },
            }
        )
        svc = _build_default_service(suggestion_llm=llm)
        snap = _snapshot()
        run_id = svc.register_compile_result(snap)
        issue = svc.list_editable_issues(run_id)[0]
        session = svc.create_session(run_id, issue)

        suggestions = svc.generate_suggestions(session.session_id)
        assert len(suggestions) == 1
        assert suggestions[0].patch.patch_type == "AddExceptionHandlerStep"

        # Assert 1: Suggestion payload is ConstructRepairIntent
        patch = suggestions[0].patch
        assert isinstance(patch.payload, ConstructRepairIntent)

        # Apply succeeds because the R0-R11 materialization service is fully integrated
        # for AddExceptionHandlerStep and runs successfully under valid evidence inputs.
        updated_session = svc.apply_suggestion(session.session_id, suggestions[0].suggestion_id)
        assert updated_session.overlay_version == 1

        patched_snapshot = svc._get_snapshot(run_id)
        assert patched_snapshot.overlay_version == 1

        # Assert 2: Verify materialized step text, command type and metadata fields
        steps = patched_snapshot.worker_step_plan.worker_steps["w_main"]
        assert len(steps) == 1
        step = steps[0]
        assert step.text == "Handle error"
        assert step.command_type == "GENERAL_COMMAND"
        assert step.metadata["origin"] == "user_confirmed_repair"
        assert step.metadata["repair_patch_id"] == patch.patch_id
        assert step.metadata["related_diagnostic_id"] == "diag_mh"
        assert step.metadata["evidence_packet_id"].startswith("ev_")
        assert step.metadata["materialization_authority"] == "stage7.worker_step_plan"
        assert step.metadata["materialization_plan_id"] == "stage7.exception_handler_step_repair.v1"
        assert json.loads(step.metadata["consumed_selected_ref_ids"]) == []

        # Assert 3: Verify block plan updates
        block_plan = patched_snapshot.worker_block_plan
        assert "w_main" in block_plan.worker_blocks
        exc_flow_blocks = block_plan.worker_blocks["w_main"].exception_flow_blocks
        assert "exc_1" in exc_flow_blocks
        assert len(exc_flow_blocks["exc_1"]) == 1
        block = exc_flow_blocks["exc_1"][0]
        assert block.block_type == "SEQUENTIAL"

        # Assert 4: Verify OverlayEvent log
        events = svc._overlays.list_for_snapshot(run_id, snap.snapshot_id)
        assert len(events) == 1
        event = events[0]
        assert event.overlay_version == 1
        assert event.patch_type == "AddExceptionHandlerStep"
        assert event.affordance_id == "exception_flow.add_handler_step"
        assert event.patch_id == patch.patch_id
        assert event.accepted is True

        # Assert 5: Verify verification result
        verify_result = svc.verify_session(session.session_id)
        assert verify_result.accepted is True
        assert verify_result.lane == "B"
        assert verify_result.patch_id == patch.patch_id
        assert verify_result.failure_reasons == ()
