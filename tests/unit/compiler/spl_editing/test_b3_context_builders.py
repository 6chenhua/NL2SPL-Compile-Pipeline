"""B3: Context builder tests."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.context.exception_flow_context import (
    ExceptionFlowContextBuilder,
)
from nl2spl.compiler.spl_editing.context.required_output_context import (
    RequiredOutputContextBuilder,
)
from nl2spl.compiler.spl_editing.context.worker_handoff_context import (
    WorkerHandoffContextBuilder,
)
from nl2spl.compiler.spl_editing.context.worker_promotion_context import (
    WorkerPromotionContextBuilder,
)
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.ir.diagnostics import DiagnosticIRSRef


def _snap() -> ArtifactSnapshot:
    return ArtifactSnapshot("snap_1", "run_1", 0)


def _issue(**kw: object) -> EditableIssue:
    d: dict[str, object] = dict(
        issue_id="i1",
        primary_diagnostic_id="d1",
        related_diagnostic_ids=("d1",),
        issue_group_id=None,
        kind="missing_handler",
        target_ref="x",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW", construct_id="x", slot_name="handler_action"
        ),
        missing_slot="handler_action",
        source_span_ids=(),
        message="test",
    )
    d.update(kw)
    return EditableIssue(**d)  # type: ignore[arg-type]


def _target(**kw: object) -> RepairTarget:
    d: dict[str, object] = dict(
        target_ref="x",
        target_kind="EXCEPTION_FLOW",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW", construct_id="x", slot_name="handler_action"
        ),
        affordance_id="exception_flow.add_handler_step",
        construct_path=(),
        worker_id="w_main",
    )
    d.update(kw)
    return RepairTarget(**d)  # type: ignore[arg-type]


class TestB3ContextBuilders:
    """B3: All context builders construct and return RepairContext."""

    def test_exception_flow_context(self) -> None:
        ctx = ExceptionFlowContextBuilder().build(
            _issue(),
            _target(),
            _snap(),
        )
        assert ctx.worker_scope == "w_main"

    def test_required_output_context(self) -> None:
        ctx = RequiredOutputContextBuilder().build(
            _issue(
                kind="missing_output_producer",
                missing_slot="draft",
                irs_ref=DiagnosticIRSRef(
                    construct_type="REQUIRED_OUTPUT", construct_id="x", slot_name="producer"
                ),
            ),
            _target(
                target_kind="REQUIRED_OUTPUT",
                canonical_name="draft",
                irs_ref=DiagnosticIRSRef(
                    construct_type="REQUIRED_OUTPUT", construct_id="x", slot_name="producer"
                ),
            ),
            _snap(),
        )
        assert "draft" in ctx.related_outputs

    def test_worker_promotion_context(self) -> None:
        ctx = WorkerPromotionContextBuilder().build(
            _issue(
                kind="type_or_contract_ambiguity",
                target_ref="worker_promotion:cand_1",
                irs_ref=DiagnosticIRSRef(
                    construct_type="WORKER_PROMOTION",
                    construct_id="x",
                    slot_name="promotion_input_contract",
                ),
            ),
            _target(target_kind="WORKER_PROMOTION"),
            _snap(),
        )
        assert "worker_promotion:cand_1" in ctx.related_worker_plan_refs

    def test_worker_handoff_context(self) -> None:
        ctx = WorkerHandoffContextBuilder().build(
            _issue(
                kind="type_or_contract_ambiguity",
                target_ref="worker_handoff:h1",
                irs_ref=DiagnosticIRSRef(
                    construct_type="WORKER_HANDOFF", construct_id="x", slot_name="target"
                ),
            ),
            _target(target_kind="WORKER_HANDOFF"),
            _snap(),
        )
        assert ctx.issue.kind == "type_or_contract_ambiguity"
