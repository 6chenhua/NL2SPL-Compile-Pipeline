"""R3 DiagnosticProjector tests — slot diagnostic_kind projection to CompileDiagnostic.

R3 test coverage:
    - Basic projection from slot.diagnostic_kind
    - DiagnosticRegistry integration (severity, blocks_completion)
    - Source evidence fallback (slot -> report)
    - Unknown/disabled diagnostic kind handling
    - Deterministic diagnostic_id generation
    - Deduplication within projection
    - blocks_rendering from report.renderable
    - Runner integration with projector
    - No semantic inference (no diagnostic without diagnostic_kind)
"""

from __future__ import annotations

import pytest
from typing import Any

from nl2spl.compiler.construct_registry import (
    ConstructSatisfactionReport,
    SlotSatisfaction,
    SPLConstructRegistry,
)
from nl2spl.compiler.diagnostic_registry import DiagnosticRegistry, DiagnosticSpec
from nl2spl.compiler.irs.checker import IRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.instance import ConstructInstance
from nl2spl.compiler.irs.projector import DiagnosticProjector
from nl2spl.compiler.irs.registry import IRSCheckerRegistry
from nl2spl.compiler.irs.runner import IRSRunner


# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def diagnostic_registry() -> DiagnosticRegistry:
    """Minimal diagnostic registry for testing."""
    registry = DiagnosticRegistry()
    registry.register(DiagnosticSpec(
        kind="missing_handler",
        default_severity="warning",
        blocks_completion=True,
        description="Exception flow has a condition but no handler action.",
        allowed_targets=["exception_flow"],
        enabled=True,
    ))
    registry.register(DiagnosticSpec(
        kind="type_or_contract_ambiguity",
        default_severity="warning",
        blocks_completion=True,
        description="A construct references an incomplete or ambiguous type / API / worker contract.",
        allowed_targets=["step", "api", "worker", "handoff"],
        enabled=True,
    ))
    registry.register(DiagnosticSpec(
        kind="disabled_kind",
        default_severity="info",
        blocks_completion=False,
        description="This diagnostic kind is disabled.",
        allowed_targets=["step"],
        enabled=False,
    ))
    return registry


@pytest.fixture
def projector(diagnostic_registry: DiagnosticRegistry) -> DiagnosticProjector:
    """DiagnosticProjector with test registry."""
    return DiagnosticProjector(diagnostic_registry=diagnostic_registry)


@pytest.fixture
def context() -> IRSCheckContext:
    """Minimal IRS check context."""
    return IRSCheckContext(
        stage_name="test_stage",
    )


# ============================================================================
# Basic projection tests
# ============================================================================


def test_projector_projects_slot_diagnostic_kind(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector generates CompileDiagnostic from slot.diagnostic_kind."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
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
    )
    
    result = projector.project([report], context)
    
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.kind == "missing_handler"
    assert diagnostic.target_ref == "exception_flow:ef_1"
    assert "handler_action" in diagnostic.message
    assert "exception_flow:ef_1" in diagnostic.message


def test_projector_uses_diagnostic_registry_defaults(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector uses severity and blocks_completion from DiagnosticRegistry."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
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
    )
    
    result = projector.project([report], context)
    
    diagnostic = result.diagnostics[0]
    assert diagnostic.severity == "warning"
    assert diagnostic.blocks_completion is True


def test_projector_uses_slot_explanation_before_spec_description(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector prefers slot.explanation over spec.description."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                explanation="Custom explanation for this specific case",
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    result = projector.project([report], context)
    
    diagnostic = result.diagnostics[0]
    assert "Custom explanation for this specific case" in diagnostic.message
    assert "Exception flow has a condition" not in diagnostic.message


def test_projector_uses_report_construct_id_as_target_ref(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector uses report.construct_id as target_ref without modification."""
    report = ConstructSatisfactionReport(
        construct_id="worker_candidate_1",
        construct_type="WORKER_CANDIDATE",
        slots=[
            SlotSatisfaction(
                slot_name="promotion_input_contract",
                status="missing",
                diagnostic_kind="type_or_contract_ambiguity",
            ),
        ],
        completeness="partial",
        renderable=False,
    )
    
    result = projector.project([report], context)
    
    diagnostic = result.diagnostics[0]
    assert diagnostic.target_ref == "worker_candidate_1"


# ============================================================================
# Source evidence tests
# ============================================================================


def test_projector_uses_slot_source_spans_before_report_source_spans(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector prefers slot.source_span_ids over report.source_span_ids."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=["span_slot_1", "span_slot_2"],
            ),
        ],
        completeness="partial",
        renderable=True,
        source_span_ids=["span_report_1"],
    )
    
    result = projector.project([report], context)
    
    diagnostic = result.diagnostics[0]
    assert diagnostic.source_span_ids == ["span_slot_1", "span_slot_2"]


def test_projector_falls_back_to_report_source_spans(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector uses report.source_span_ids when slot.source_span_ids is empty."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=[],
            ),
        ],
        completeness="partial",
        renderable=True,
        source_span_ids=["span_report_1", "span_report_2"],
    )
    
    result = projector.project([report], context)
    
    diagnostic = result.diagnostics[0]
    assert diagnostic.source_span_ids == ["span_report_1", "span_report_2"]


def test_projector_allows_empty_source_spans(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector allows empty source_span_ids when both slot and report are empty."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=[],
            ),
        ],
        completeness="partial",
        renderable=True,
        source_span_ids=[],
    )
    
    result = projector.project([report], context)
    
    diagnostic = result.diagnostics[0]
    assert diagnostic.source_span_ids == []


# ============================================================================
# Unknown / disabled kind tests
# ============================================================================


def test_projector_warns_and_skips_unknown_diagnostic_kind(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector warns and skips unknown diagnostic kinds."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="unknown_kind",
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    result = projector.project([report], context)
    
    assert len(result.diagnostics) == 0
    assert len(result.warnings) == 1
    assert "unknown_kind" in result.warnings[0]
    assert "exception_flow:ef_1" in result.warnings[0]
    assert "handler_action" in result.warnings[0]


def test_projector_warns_and_skips_disabled_diagnostic_kind(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector warns and skips disabled diagnostic kinds."""
    report = ConstructSatisfactionReport(
        construct_id="step:st_1",
        construct_type="GENERAL_COMMAND",
        slots=[
            SlotSatisfaction(
                slot_name="action_text",
                status="satisfied",
                diagnostic_kind="disabled_kind",
            ),
        ],
        completeness="complete",
        renderable=True,
    )
    
    result = projector.project([report], context)
    
    assert len(result.diagnostics) == 0
    assert len(result.warnings) == 1
    assert "disabled_kind" in result.warnings[0]
    assert "step:st_1" in result.warnings[0]
    assert "action_text" in result.warnings[0]


# ============================================================================
# Determinism / dedup tests
# ============================================================================


def test_projector_diagnostic_id_is_deterministic(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector generates same diagnostic_id for same input."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=["span_1", "span_2"],
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    result1 = projector.project([report], context)
    result2 = projector.project([report], context)
    
    assert result1.diagnostics[0].diagnostic_id == result2.diagnostics[0].diagnostic_id
    assert result1.diagnostics[0].diagnostic_id.startswith("irs_")


def test_projector_diagnostic_id_ignores_source_span_order(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector generates same diagnostic_id regardless of source_span_ids order."""
    report1 = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=["span_1", "span_2"],
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    report2 = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=["span_2", "span_1"],
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    result1 = projector.project([report1], context)
    result2 = projector.project([report2], context)
    
    assert result1.diagnostics[0].diagnostic_id == result2.diagnostics[0].diagnostic_id


def test_projector_deduplicates_same_kind_target_slot_source(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector deduplicates diagnostics with same kind/target/slot/source."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=["span_1"],
            ),
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=["span_1"],
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    result = projector.project([report], context)
    
    assert len(result.diagnostics) == 1


def test_projector_keeps_different_slots_separate(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector keeps diagnostics for different slots separate."""
    report = ConstructSatisfactionReport(
        construct_id="worker_candidate_1",
        construct_type="WORKER_CANDIDATE",
        slots=[
            SlotSatisfaction(
                slot_name="promotion_input_contract",
                status="missing",
                diagnostic_kind="type_or_contract_ambiguity",
            ),
            SlotSatisfaction(
                slot_name="promotion_output_contract",
                status="missing",
                diagnostic_kind="type_or_contract_ambiguity",
            ),
        ],
        completeness="partial",
        renderable=False,
    )
    
    result = projector.project([report], context)
    
    assert len(result.diagnostics) == 2
    slot_names = {d.message for d in result.diagnostics}
    assert any("promotion_input_contract" in msg for msg in slot_names)
    assert any("promotion_output_contract" in msg for msg in slot_names)


def test_projector_keeps_different_sources_separate(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector keeps diagnostics with different source_span_ids separate."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=["span_1"],
            ),
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=["span_2"],
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    result = projector.project([report], context)
    
    assert len(result.diagnostics) == 2


# ============================================================================
# Blocks rendering tests
# ============================================================================


def test_projector_blocks_rendering_when_report_not_renderable(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector sets blocks_rendering=True when report.renderable=False."""
    report = ConstructSatisfactionReport(
        construct_id="worker_candidate_1",
        construct_type="WORKER_CANDIDATE",
        slots=[
            SlotSatisfaction(
                slot_name="promotion_input_contract",
                status="missing",
                diagnostic_kind="type_or_contract_ambiguity",
            ),
        ],
        completeness="partial",
        renderable=False,
    )
    
    result = projector.project([report], context)
    
    diagnostic = result.diagnostics[0]
    assert diagnostic.blocks_rendering is True
    assert diagnostic.blocks_completion is True


def test_projector_does_not_block_rendering_when_report_renderable(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector sets blocks_rendering=False when report.renderable=True."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
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
    )
    
    result = projector.project([report], context)
    
    diagnostic = result.diagnostics[0]
    assert diagnostic.blocks_rendering is False
    assert diagnostic.blocks_completion is True


# ============================================================================
# Runner integration tests
# ============================================================================


class FakeDiagnosticChecker(IRSChecker):
    """Fake checker that produces reports with diagnostic_kind."""
    
    checker_id = "fake_diagnostic_checker"
    supported_construct_types = ("EXCEPTION_FLOW",)
    supported_stages = ("test_stage",)
    
    def extract_instances(
        self,
        context: IRSCheckContext,
    ) -> list[ConstructInstance]:
        return [
            ConstructInstance(
                construct_id="exception_flow:ef_1",
                construct_type="EXCEPTION_FLOW",
                materialized=True,
            ),
        ]
    
    def check_instance(
        self,
        instance: ConstructInstance,
        irs: Any,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=[
                SlotSatisfaction(
                    slot_name="handler_action",
                    status="missing",
                    diagnostic_kind="missing_handler",
                    source_span_ids=["span_1"],
                ),
            ],
            completeness="partial",
            renderable=True,
        )


def test_runner_with_projector_returns_projected_diagnostics(
    diagnostic_registry: DiagnosticRegistry,
    context: IRSCheckContext,
) -> None:
    """Runner with projector returns projected diagnostics."""
    checker_registry = IRSCheckerRegistry()
    checker_registry.register(FakeDiagnosticChecker())
    
    projector = DiagnosticProjector(diagnostic_registry=diagnostic_registry)
    runner = IRSRunner(
        registry=checker_registry,
        construct_registry=SPLConstructRegistry.default(),
        projector=projector,
    )
    
    result = runner.run_stage("test_stage", context)
    
    assert len(result.reports) == 1
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.kind == "missing_handler"
    assert diagnostic.target_ref == "exception_flow:ef_1"


def test_runner_projector_warning_is_preserved(
    diagnostic_registry: DiagnosticRegistry,
    context: IRSCheckContext,
) -> None:
    """Runner preserves projector warnings."""
    
    class FakeUnknownKindChecker(IRSChecker):
        checker_id = "fake_unknown_kind_checker"
        supported_construct_types = ("EXCEPTION_FLOW",)
        supported_stages = ("test_stage",)
        
        def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
            return [
                ConstructInstance(
                    construct_id="exception_flow:ef_1",
                    construct_type="EXCEPTION_FLOW",
                    materialized=True,
                ),
            ]
        
        def check_instance(
            self,
            instance: ConstructInstance,
            irs: Any,
            context: IRSCheckContext,
        ) -> ConstructSatisfactionReport:
            return ConstructSatisfactionReport(
                construct_id=instance.construct_id,
                construct_type=instance.construct_type,
                slots=[
                    SlotSatisfaction(
                        slot_name="handler_action",
                        status="missing",
                        diagnostic_kind="unknown_kind",
                    ),
                ],
                completeness="partial",
                renderable=True,
            )
    
    checker_registry = IRSCheckerRegistry()
    checker_registry.register(FakeUnknownKindChecker())
    
    projector = DiagnosticProjector(diagnostic_registry=diagnostic_registry)
    runner = IRSRunner(
        registry=checker_registry,
        construct_registry=SPLConstructRegistry.default(),
        projector=projector,
    )
    
    result = runner.run_stage("test_stage", context)
    
    assert len(result.diagnostics) == 0
    assert len(result.warnings) > 0
    assert any("unknown_kind" in w for w in result.warnings)


def test_runner_without_projector_preserves_r2_no_diagnostic_behavior(
    context: IRSCheckContext,
) -> None:
    """Runner without projector does not generate diagnostics (R2 behavior)."""
    checker_registry = IRSCheckerRegistry()
    checker_registry.register(FakeDiagnosticChecker())
    
    runner = IRSRunner(
        registry=checker_registry,
        construct_registry=SPLConstructRegistry.default(),
        projector=None,
    )
    
    result = runner.run_stage("test_stage", context)
    
    assert len(result.reports) == 1
    assert len(result.diagnostics) == 0


# ============================================================================
# No semantic logic tests
# ============================================================================


def test_projector_does_not_create_diagnostic_without_diagnostic_kind(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector does not create diagnostic when diagnostic_kind is None."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind=None,
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    result = projector.project([report], context)
    
    assert len(result.diagnostics) == 0
    assert len(result.warnings) == 0


def test_projector_does_not_infer_from_missing_slot_status(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector does not infer diagnostic from status='missing' alone."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind=None,
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    result = projector.project([report], context)
    
    assert len(result.diagnostics) == 0


def test_projector_does_not_infer_from_report_completeness(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector does not infer diagnostic from completeness='partial' alone."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="condition",
                status="satisfied",
                diagnostic_kind=None,
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    result = projector.project([report], context)
    
    assert len(result.diagnostics) == 0


# ============================================================================
# P1: missing_slot structure tests
# ============================================================================


def test_projector_populates_missing_slot_structure(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector populates missing_slot with slot_name and reason."""
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                explanation="Custom explanation",
                source_span_ids=["span_1"],
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    result = projector.project([report], context)
    
    diagnostic = result.diagnostics[0]
    assert diagnostic.missing_slot is not None
    assert diagnostic.missing_slot.slot_name == "handler_action"
    assert diagnostic.missing_slot.required_for == "complete"
    assert diagnostic.missing_slot.reason == "Custom explanation"
    assert diagnostic.missing_slot.source_span_ids == ["span_1"]


def test_projector_different_slots_have_different_missing_slot_names(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector ensures different slots have different missing_slot.slot_name."""
    report = ConstructSatisfactionReport(
        construct_id="worker_candidate_1",
        construct_type="WORKER_CANDIDATE",
        slots=[
            SlotSatisfaction(
                slot_name="promotion_input_contract",
                status="missing",
                diagnostic_kind="type_or_contract_ambiguity",
            ),
            SlotSatisfaction(
                slot_name="promotion_output_contract",
                status="missing",
                diagnostic_kind="type_or_contract_ambiguity",
            ),
        ],
        completeness="partial",
        renderable=False,
    )
    
    result = projector.project([report], context)
    
    assert len(result.diagnostics) == 2
    slot_names = {d.missing_slot.slot_name for d in result.diagnostics}
    assert slot_names == {"promotion_input_contract", "promotion_output_contract"}


# ============================================================================
# P2: source_span_ids immutability tests
# ============================================================================


def test_projector_copies_source_span_ids_from_slot(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector copies source_span_ids to avoid sharing mutable list."""
    slot_spans = ["span_1", "span_2"]
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=slot_spans,
            ),
        ],
        completeness="partial",
        renderable=True,
    )
    
    result = projector.project([report], context)
    
    # Modify original slot spans
    slot_spans.append("span_3")
    
    # Diagnostic should not be affected
    diagnostic = result.diagnostics[0]
    assert diagnostic.source_span_ids == ["span_1", "span_2"]
    assert "span_3" not in diagnostic.source_span_ids


def test_projector_copies_source_span_ids_from_report(
    projector: DiagnosticProjector,
    context: IRSCheckContext,
) -> None:
    """Projector copies source_span_ids from report when slot has none."""
    report_spans = ["span_report_1", "span_report_2"]
    report = ConstructSatisfactionReport(
        construct_id="exception_flow:ef_1",
        construct_type="EXCEPTION_FLOW",
        slots=[
            SlotSatisfaction(
                slot_name="handler_action",
                status="missing",
                diagnostic_kind="missing_handler",
                source_span_ids=[],
            ),
        ],
        completeness="partial",
        renderable=True,
        source_span_ids=report_spans,
    )
    
    result = projector.project([report], context)
    
    # Modify original report spans
    report_spans.append("span_report_3")
    
    # Diagnostic should not be affected
    diagnostic = result.diagnostics[0]
    assert diagnostic.source_span_ids == ["span_report_1", "span_report_2"]
    assert "span_report_3" not in diagnostic.source_span_ids
