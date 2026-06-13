"""R1 Diagnostic Metadata Foundation: post-implementation tests.

Verifies that after R1 changes:
  1. DiagnosticProjector writes irs_ref + authority into CompileDiagnostic.metadata
  2. source_authority derives correctly from stage_name
  3. Same diagnostic kind + different construct slot are distinguishable
  4. DiagnosticConsolidator preserves irs_ref / authority through dedup
  5. Renderers do not strip or alter metadata

IMPORTANT: These tests describe the POST-R1 target behavior.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.construct_registry import (
    ConstructSatisfactionReport,
    SlotSatisfaction,
    SPLConstructRegistry,
)
from nl2spl.compiler.diagnostic_consolidator import (
    DiagnosticConsolidationInput,
    DiagnosticConsolidator,
)
from nl2spl.compiler.irs.checkers.post_normalize import PostNormalizeIRSCheckerV6
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.projector import DiagnosticProjector
from nl2spl.compiler.irs.runner import IRSRunner
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import FlowRef, WorkerIR


# ===========================================================================
# R1-1: Projector writes irs_ref + authority into metadata
# ===========================================================================


class TestR1ProjectorWritesIRSRef:
    """R1: DiagnosticProjector populates metadata["irs_ref"] and
    metadata["authority"] on every projected diagnostic.
    """

    def test_post_normalize_authority_is_post_normalize_irs(self) -> None:
        """R1: post_normalize stage → authority='post_normalize_irs'."""
        projector = DiagnosticProjector()
        report = ConstructSatisfactionReport(
            construct_id="worker:w_main.exception_flow:exc_1",
            construct_type="EXCEPTION_FLOW",
            slots=[
                SlotSatisfaction(
                    slot_name="handler_action",
                    status="missing",
                    diagnostic_kind="missing_handler",
                    explanation="No handler step.",
                ),
            ],
            completeness="partial",
            renderable=True,
            construct_path=("worker", "w_main", "exception_flows", "exc_1"),
        )
        context = IRSCheckContext(stage_name="post_normalize")
        result = projector.project([report], context)

        assert len(result.diagnostics) == 1
        diag = result.diagnostics[0]

        # metadata["irs_ref"] is present and populated
        irs_ref = diag.metadata.get("irs_ref")
        assert irs_ref is not None, "R1: irs_ref must be written into metadata"
        assert irs_ref["construct_type"] == "EXCEPTION_FLOW"
        assert irs_ref["construct_id"] == "worker:w_main.exception_flow:exc_1"
        assert irs_ref["slot_name"] == "handler_action"
        assert irs_ref["construct_path"] == ["worker", "w_main", "exception_flows", "exc_1"]
        assert irs_ref["source_authority"] == "post_normalize_irs"

        # metadata["authority"] is a shorthand alias
        assert diag.metadata.get("authority") == "post_normalize_irs"

    def test_stage_local_authority_is_stage_local_irs(self) -> None:
        """R1: non-post_normalize stage → authority='stage_local_irs'."""
        projector = DiagnosticProjector()
        report = ConstructSatisfactionReport(
            construct_id="worker_promotion:del_s1",
            construct_type="WORKER_PROMOTION",
            slots=[
                SlotSatisfaction(
                    slot_name="promotion_input_contract",
                    status="missing",
                    diagnostic_kind="type_or_contract_ambiguity",
                    diagnostic_blocks_rendering=False,
                ),
            ],
            completeness="partial",
            renderable=False,
            construct_path=("routes", "annotations", "s1"),
        )
        context = IRSCheckContext(stage_name="stage3_5")
        result = projector.project([report], context)

        assert len(result.diagnostics) == 1
        diag = result.diagnostics[0]

        irs_ref = diag.metadata.get("irs_ref")
        assert irs_ref is not None
        assert irs_ref["source_authority"] == "stage_local_irs"
        assert diag.metadata.get("authority") == "stage_local_irs"

    def test_construct_path_preserved_as_list(self) -> None:
        """R1: construct_path tuple is serialized to list in irs_ref dict."""
        projector = DiagnosticProjector()
        report = ConstructSatisfactionReport(
            construct_id="worker:w_main.output:draft",
            construct_type="REQUIRED_OUTPUT",
            slots=[
                SlotSatisfaction(
                    slot_name="producer",
                    status="missing",
                    diagnostic_kind="missing_output_producer",
                    explanation="No producer.",
                ),
            ],
            completeness="partial",
            renderable=True,
            construct_path=("worker_plan", "w_main", "output_contract", "draft"),
        )
        context = IRSCheckContext(stage_name="post_normalize")
        result = projector.project([report], context)

        diag = result.diagnostics[0]
        irs_ref = diag.metadata["irs_ref"]
        # construct_path stored as list (JSON-serializable)
        assert isinstance(irs_ref["construct_path"], list)
        assert irs_ref["construct_path"] == ["worker_plan", "w_main", "output_contract", "draft"]

    def test_diagnostics_without_slot_diagnostic_kind_get_no_irs_ref(
        self,
    ) -> None:
        """R1: Only slots with diagnostic_kind produce diagnostics.
        Slots without diagnostic_kind are not projected at all,
        so the question of irs_ref on them is moot.
        """
        projector = DiagnosticProjector()
        report = ConstructSatisfactionReport(
            construct_id="worker:w_main.exception_flow:exc_1",
            construct_type="EXCEPTION_FLOW",
            slots=[
                SlotSatisfaction(
                    slot_name="condition",
                    status="satisfied",
                    # No diagnostic_kind → will not be projected
                ),
            ],
            completeness="complete",
            renderable=True,
        )
        context = IRSCheckContext(stage_name="post_normalize")
        result = projector.project([report], context)
        assert len(result.diagnostics) == 0


# ===========================================================================
# R1-2: Same diagnostic kind + different construct slot → distinguishable
# ===========================================================================


class TestR1ConstructSlotDifferentiation:
    """R1: Same diagnostic_kind on different construct_type+slot_name pairs
    produces distinguishable irs_ref metadata.
    """

    def test_missing_handler_has_exception_flow_irs_ref(self) -> None:
        """R1: missing_handler diagnostic carries
        construct_type=EXCEPTION_FLOW, slot_name=handler_action.
        """
        projector = DiagnosticProjector()
        report = ConstructSatisfactionReport(
            construct_id="worker:w_main.exception_flow:exc_1",
            construct_type="EXCEPTION_FLOW",
            slots=[
                SlotSatisfaction(
                    slot_name="handler_action",
                    status="missing",
                    diagnostic_kind="missing_handler",
                ),
            ],
            completeness="partial",
            renderable=True,
            construct_path=("worker", "w_main", "exception_flows", "exc_1"),
        )
        context = IRSCheckContext(stage_name="post_normalize")
        result = projector.project([report], context)

        diag = result.diagnostics[0]
        assert diag.kind == "missing_handler"
        irs_ref = diag.metadata["irs_ref"]
        assert irs_ref["construct_type"] == "EXCEPTION_FLOW"
        assert irs_ref["slot_name"] == "handler_action"

    def test_missing_output_producer_from_required_output(self) -> None:
        """R1: missing_output_producer from REQUIRED_OUTPUT.producer
        is distinguishable from RESOURCE_CONTRACT_DEMAND.producer.
        """
        projector = DiagnosticProjector()
        report = ConstructSatisfactionReport(
            construct_id="worker:w_main.output:draft",
            construct_type="REQUIRED_OUTPUT",
            slots=[
                SlotSatisfaction(
                    slot_name="producer",
                    status="missing",
                    diagnostic_kind="missing_output_producer",
                ),
            ],
            completeness="partial",
            renderable=True,
            construct_path=("worker_plan", "w_main", "output_contract", "draft"),
        )
        context = IRSCheckContext(stage_name="post_normalize")
        result = projector.project([report], context)

        diag = result.diagnostics[0]
        irs_ref = diag.metadata["irs_ref"]
        assert irs_ref["construct_type"] == "REQUIRED_OUTPUT"
        assert irs_ref["slot_name"] == "producer"

    def test_missing_output_producer_from_resource_contract_demand(self) -> None:
        """R1: missing_output_producer from RESOURCE_CONTRACT_DEMAND.producer
        has a different construct_type than REQUIRED_OUTPUT.producer.
        """
        projector = DiagnosticProjector()
        report = ConstructSatisfactionReport(
            construct_id="resource_contract_demand:rcd_001",
            construct_type="RESOURCE_CONTRACT_DEMAND",
            slots=[
                SlotSatisfaction(
                    slot_name="producer",
                    status="missing",
                    diagnostic_kind="missing_output_producer",
                ),
            ],
            completeness="partial",
            renderable=True,
            construct_path=("resource_contract", "rcd_001"),
        )
        context = IRSCheckContext(stage_name="post_normalize")
        result = projector.project([report], context)

        diag = result.diagnostics[0]
        irs_ref = diag.metadata["irs_ref"]
        assert irs_ref["construct_type"] == "RESOURCE_CONTRACT_DEMAND"
        assert irs_ref["slot_name"] == "producer"

    def test_same_kind_different_constructs_are_distinguishable(self) -> None:
        """R1: Two missing_output_producer diagnostics from different
        construct types can be disambiguated via irs_ref.
        """
        projector = DiagnosticProjector()
        reports = [
            ConstructSatisfactionReport(
                construct_id="worker:w_main.output:draft",
                construct_type="REQUIRED_OUTPUT",
                slots=[
                    SlotSatisfaction(
                        slot_name="producer",
                        status="missing",
                        diagnostic_kind="missing_output_producer",
                    ),
                ],
                completeness="partial",
                renderable=True,
                construct_path=("worker_plan", "w_main", "output_contract", "draft"),
            ),
            ConstructSatisfactionReport(
                construct_id="resource_contract_demand:rcd_output",
                construct_type="RESOURCE_CONTRACT_DEMAND",
                slots=[
                    SlotSatisfaction(
                        slot_name="producer",
                        status="missing",
                        diagnostic_kind="missing_output_producer",
                    ),
                ],
                completeness="partial",
                renderable=True,
                construct_path=("resource_contract", "rcd_output"),
            ),
        ]
        context = IRSCheckContext(stage_name="post_normalize")
        result = projector.project(reports, context)

        assert len(result.diagnostics) == 2
        types = {d.metadata["irs_ref"]["construct_type"] for d in result.diagnostics}
        assert types == {"REQUIRED_OUTPUT", "RESOURCE_CONTRACT_DEMAND"}

    def test_type_or_contract_ambiguity_from_different_slots(self) -> None:
        """R1: type_or_contract_ambiguity from different construct+slot
        pairs maps to different irs_ref entries.
        """
        projector = DiagnosticProjector()
        reports = [
            ConstructSatisfactionReport(
                construct_id="worker:w_main.step:st_api",
                construct_type="CALL_API",
                slots=[
                    SlotSatisfaction(
                        slot_name="api_name",
                        status="missing",
                        diagnostic_kind="type_or_contract_ambiguity",
                    ),
                ],
                completeness="partial",
                renderable=False,
                construct_path=("worker", "w_main", "steps", "st_api"),
            ),
            ConstructSatisfactionReport(
                construct_id="worker_promotion:del_s1",
                construct_type="WORKER_PROMOTION",
                slots=[
                    SlotSatisfaction(
                        slot_name="promotion_input_contract",
                        status="missing",
                        diagnostic_kind="type_or_contract_ambiguity",
                        diagnostic_blocks_rendering=False,
                    ),
                ],
                completeness="partial",
                renderable=False,
                construct_path=("routes", "annotations", "s1"),
            ),
            ConstructSatisfactionReport(
                construct_id="worker:w_main.step:st_req",
                construct_type="REQUEST_INPUT",
                slots=[
                    SlotSatisfaction(
                        slot_name="value_target",
                        status="missing",
                        diagnostic_kind="type_or_contract_ambiguity",
                    ),
                ],
                completeness="partial",
                renderable=False,
                construct_path=("worker", "w_main", "steps", "st_req"),
            ),
        ]
        context = IRSCheckContext(stage_name="post_normalize")
        result = projector.project(reports, context)

        assert len(result.diagnostics) == 3
        # Each diagnostic's irs_ref points to a different construct+slot
        combos = {
            (d.metadata["irs_ref"]["construct_type"], d.metadata["irs_ref"]["slot_name"])
            for d in result.diagnostics
        }
        assert combos == {
            ("CALL_API", "api_name"),
            ("WORKER_PROMOTION", "promotion_input_contract"),
            ("REQUEST_INPUT", "value_target"),
        }


# ===========================================================================
# R1-3: DiagnosticConsolidator preserves irs_ref and authority
# ===========================================================================


class TestR1ConsolidatorPreservesMetadata:
    """R1: DiagnosticConsolidator does not strip irs_ref or authority
    from diagnostics during dedup.
    """

    def test_consolidator_preserves_irs_ref_on_final(self) -> None:
        """R1: After consolidation, irs_ref is still present on final diagnostics."""
        diag = CompileDiagnostic(
            diagnostic_id="diag_001",
            kind="missing_handler",
            severity="warning",
            message="No handler",
            target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
            metadata={
                "irs_ref": {
                    "construct_type": "EXCEPTION_FLOW",
                    "construct_id": "worker:w_main.exception_flow:exc_1",
                    "slot_name": "handler_action",
                    "construct_path": ["worker", "w_main", "exception_flows", "exc_1"],
                    "source_authority": "post_normalize_irs",
                },
                "authority": "post_normalize_irs",
            },
        )

        result = DiagnosticConsolidator().consolidate(
            DiagnosticConsolidationInput(post_normalize_diagnostics=[diag])
        )

        assert len(result.final_diagnostics) == 1
        final = result.final_diagnostics[0]
        assert final.metadata.get("irs_ref") is not None
        assert final.metadata["irs_ref"]["construct_type"] == "EXCEPTION_FLOW"
        assert final.metadata.get("authority") == "post_normalize_irs"

    def test_consolidator_does_not_strip_irs_ref_during_dedup(self) -> None:
        """R1: When dedup suppresses a duplicate, the surviving diagnostic
        retains its irs_ref metadata.
        """
        post_diag = CompileDiagnostic(
            diagnostic_id="irs_abc123",
            kind="missing_handler",
            severity="warning",
            message="No handler [construct=worker:w_main.exception_flow:exc_1, slot=handler_action]",
            target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
            missing_slot=None,
            metadata={
                "irs_ref": {
                    "construct_type": "EXCEPTION_FLOW",
                    "construct_id": "worker:w_main.exception_flow:exc_1",
                    "slot_name": "handler_action",
                    "construct_path": ["worker", "w_main", "exception_flows", "exc_1"],
                    "source_authority": "post_normalize_irs",
                },
                "authority": "post_normalize_irs",
            },
        )
        # Duplicate from stage-local (should be suppressed)
        stage_diag = CompileDiagnostic(
            diagnostic_id="irs_xyz789",
            kind="missing_handler",
            severity="warning",
            message="No handler",
            target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
            metadata={
                "irs_ref": {
                    "construct_type": "EXCEPTION_FLOW",
                    "construct_id": "worker:w_main.exception_flow:exc_1",
                    "slot_name": "handler_action",
                    "construct_path": ["worker", "w_main", "exception_flows", "exc_1"],
                    "source_authority": "stage_local_irs",
                },
                "authority": "stage_local_irs",
            },
        )

        result = DiagnosticConsolidator().consolidate(
            DiagnosticConsolidationInput(
                post_normalize_diagnostics=[post_diag],
                irs_promoted_diagnostics=[stage_diag],
            )
        )

        # The post_normalize diagnostic survives (higher authority)
        assert len(result.final_diagnostics) == 1
        final = result.final_diagnostics[0]
        assert final.metadata.get("irs_ref") is not None
        assert final.metadata.get("authority") == "post_normalize_irs"

    def test_consolidator_does_not_mutate_irs_ref(self) -> None:
        """R1: Consolidator passes diagnostics through without mutating
        the irs_ref dict.
        """
        original_irs_ref = {
            "construct_type": "EXCEPTION_FLOW",
            "construct_id": "worker:w_main.exception_flow:exc_1",
            "slot_name": "handler_action",
            "construct_path": ["worker", "w_main", "exception_flows", "exc_1"],
            "source_authority": "post_normalize_irs",
        }
        diag = CompileDiagnostic(
            diagnostic_id="diag_001",
            kind="missing_handler",
            severity="warning",
            message="Test",
            blocks_completion=True,
            metadata={
                "irs_ref": dict(original_irs_ref),
                "authority": "post_normalize_irs",
            },
        )

        DiagnosticConsolidator().consolidate(
            DiagnosticConsolidationInput(post_normalize_diagnostics=[diag])
        )

        # Original diagnostic's irs_ref is unchanged
        assert diag.metadata["irs_ref"] == original_irs_ref


# ===========================================================================
# R1-4: DiagnosticIRSRef structured helper round-trips correctly
# ===========================================================================


class TestR1DiagnosticIRSRefHelper:
    """R1: DiagnosticIRSRef to_dict / from_dict round-trip."""

    def test_round_trip_preserves_all_fields(self) -> None:
        """R1: to_dict() → from_dict() returns an equivalent object."""
        original = DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="worker:w_main.exception_flow:exc_1",
            slot_name="handler_action",
            construct_path=("worker", "w_main", "exception_flows", "exc_1"),
            source_authority="post_normalize_irs",
        )
        d = original.to_dict()
        restored = DiagnosticIRSRef.from_dict(d)
        assert restored == original

    def test_from_dict_with_minimal_fields(self) -> None:
        """R1: from_dict with only required keys uses defaults."""
        d = {
            "construct_type": "GENERAL_COMMAND",
            "construct_id": "step:st1",
            "slot_name": "source_evidence",
        }
        ref = DiagnosticIRSRef.from_dict(d)
        assert ref.construct_type == "GENERAL_COMMAND"
        assert ref.construct_id == "step:st1"
        assert ref.slot_name == "source_evidence"
        assert ref.construct_path == ()
        assert ref.source_authority == "post_normalize_irs"

    def test_to_dict_produces_json_serializable_output(self) -> None:
        """R1: to_dict() output is JSON-safe (no tuples, only lists)."""
        ref = DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="exc_1",
            slot_name="handler_action",
            construct_path=("a", "b", "c"),
            source_authority="post_normalize_irs",
        )
        d = ref.to_dict()
        # construct_path must be a list, not a tuple
        assert isinstance(d["construct_path"], list)
        # All keys present
        assert set(d.keys()) == {
            "construct_type", "construct_id", "slot_name",
            "construct_path", "source_authority",
        }


# ===========================================================================
# R1-5: Feedback renderer does not break when metadata contains irs_ref
# ===========================================================================


class TestR1RendererMetadataTransparency:
    """R1: Renderers do not break or alter user-visible output when
    diagnostics carry irs_ref metadata.
    """

    def test_report_renderer_handles_irs_ref_metadata(self) -> None:
        """R1: report_renderer produces output without error when
        diagnostics have irs_ref metadata.
        """
        from nl2spl.compiler.report_renderer import render_report

        diag = CompileDiagnostic(
            diagnostic_id="diag_001",
            kind="missing_handler",
            severity="warning",
            message="No handler step for exception flow.",
            target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
            metadata={
                "irs_ref": {
                    "construct_type": "EXCEPTION_FLOW",
                    "construct_id": "worker:w_main.exception_flow:exc_1",
                    "slot_name": "handler_action",
                    "construct_path": ["worker", "w_main", "exception_flows", "exc_1"],
                    "source_authority": "post_normalize_irs",
                },
                "authority": "post_normalize_irs",
            },
        )

        report = render_report(
            spl_text="[WORKER MainWorker] ...",
            diagnostics=[diag],
        )
        # Renders without crashing
        assert "missing_handler" in report
        assert "diag_001" in report

    def test_feedback_report_renderer_handles_irs_ref_metadata(self) -> None:
        """R1: feedback_report_renderer produces output without error when
        diagnostics have irs_ref metadata.
        """
        from nl2spl.compiler.feedback_report_renderer import render_feedback_report

        diag = CompileDiagnostic(
            diagnostic_id="diag_001",
            kind="missing_handler",
            severity="warning",
            message="No handler step for exception flow.",
            target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
            metadata={
                "irs_ref": {
                    "construct_type": "EXCEPTION_FLOW",
                    "construct_id": "worker:w_main.exception_flow:exc_1",
                    "slot_name": "handler_action",
                    "construct_path": ["worker", "w_main", "exception_flows", "exc_1"],
                    "source_authority": "post_normalize_irs",
                },
                "authority": "post_normalize_irs",
            },
        )

        report = render_feedback_report(
            spl_text="[WORKER MainWorker] ...",
            diagnostics=[diag],
        )
        # Renders without crashing
        assert "missing_handler" in report
        assert "diag_001" in report

    def test_report_renderer_does_not_expose_raw_irs_ref(self) -> None:
        """R1: The report renderer does NOT dump raw irs_ref dict into
        human-readable output. Metadata is machine-readable only.
        """
        from nl2spl.compiler.report_renderer import render_report

        diag = CompileDiagnostic(
            diagnostic_id="diag_001",
            kind="missing_handler",
            severity="warning",
            message="Test message",
            blocks_completion=True,
            metadata={
                "irs_ref": {
                    "construct_type": "EXCEPTION_FLOW",
                    "construct_id": "exc_1",
                    "slot_name": "handler_action",
                    "construct_path": [],
                    "source_authority": "post_normalize_irs",
                },
            },
        )

        report = render_report(spl_text="SPL", diagnostics=[diag])
        # The raw dict should not leak into the report text
        assert "construct_type" not in report
        assert "source_authority" not in report
