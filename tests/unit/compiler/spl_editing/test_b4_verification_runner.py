"""B4: Verification runner, diagnostic diff, and predicates tests."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairEvidence, RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.verification.diagnostic_diff import (
    DiagnosticDiff,
    DiagnosticDiffResult,
)
from nl2spl.compiler.spl_editing.verification.lanes import (
    LaneAReplayAdapter,
    VerificationArtifacts,
)
from nl2spl.compiler.spl_editing.verification.predicates import (
    no_new_blocking_diagnostics,
    target_diagnostic_resolved,
)
from nl2spl.compiler.spl_editing.verification.runner import VerificationRunner
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef


def _diag(diag_id: str, blocks: bool = True) -> CompileDiagnostic:
    return CompileDiagnostic(
        diagnostic_id=diag_id,
        kind="missing_handler",
        severity="warning",
        message="test",
        target_ref="x",
        blocks_completion=blocks,
    )


# ===========================================================================
# B4-1: DiagnosticDiff
# ===========================================================================


class TestB4DiagnosticDiff:
    """B4: DiagnosticDiff compares before/after sets."""

    def test_resolved_diagnostic_detected(self) -> None:
        before = (_diag("d1"), _diag("d2"))
        after = (_diag("d2"),)  # d1 removed → resolved
        result = DiagnosticDiff().compare(before, after)
        assert result.resolved_ids == ("d1",)
        assert not result.has_new_blocking

    def test_new_blocking_detected(self) -> None:
        before = (_diag("d1"),)
        after = (_diag("d1"), _diag("d2", blocks=True))
        result = DiagnosticDiff().compare(before, after)
        assert result.new_blocking_ids == ("d2",)
        assert result.has_new_blocking

    def test_unchanged(self) -> None:
        before = (_diag("d1"), _diag("d2"))
        after = (_diag("d1"), _diag("d2"))
        result = DiagnosticDiff().compare(before, after)
        assert result.unchanged_count == 2
        assert result.resolved_ids == ()
        assert not result.has_new_blocking

    def test_non_blocking_new_is_not_blocked(self) -> None:
        before = (_diag("d1"),)
        after = (_diag("d1"), _diag("d2", blocks=False))
        result = DiagnosticDiff().compare(before, after)
        assert not result.has_new_blocking


# ===========================================================================
# B4-2: Predicates
# ===========================================================================


class TestB4Predicates:
    """B4: Common verification predicates."""

    def test_no_new_blocking_true(self) -> None:
        diff = DiagnosticDiffResult(resolved_ids=("d1",), new_blocking_ids=())
        assert no_new_blocking_diagnostics(diff)

    def test_no_new_blocking_false(self) -> None:
        diff = DiagnosticDiffResult(new_blocking_ids=("d2",))
        assert not no_new_blocking_diagnostics(diff)

    def test_target_resolved(self) -> None:
        diff = DiagnosticDiffResult(resolved_ids=("d1",))
        assert target_diagnostic_resolved(diff, "d1")

    def test_target_not_resolved(self) -> None:
        diff = DiagnosticDiffResult(resolved_ids=("d1",))
        assert not target_diagnostic_resolved(diff, "d2")


# ===========================================================================
# B4-3: VerificationRunner
# ===========================================================================


class _StubLane(LaneAReplayAdapter):
    def replay(self, snapshot):
        return VerificationArtifacts(
            consolidated_diagnostics=snapshot.compile_diagnostics,
            rendered_spl=snapshot.final_spl or "",
        )


class TestB4VerificationRunner:
    """B4: VerificationRunner orchestrates lane + diff + verifier."""

    @staticmethod
    def _runner() -> VerificationRunner:
        return VerificationRunner(lane_a=_StubLane())

    @staticmethod
    def _patch(**kw: object) -> RepairPatch:
        d: dict[str, object] = dict(
            patch_id="p1",
            affordance_id="a",
            patch_type="T",
            target_ref="x",
            irs_ref=DiagnosticIRSRef(
                construct_type="EXCEPTION_FLOW",
                construct_id="x",
                slot_name="handler_action",
            ),
            base_compile_run_id="run_1",
            artifact_snapshot_id="snap_1",
            overlay_version=0,
            payload={},
            verification_lane="A",
            evidence=RepairEvidence(related_diagnostic_id="diag_target"),
        )
        d.update(kw)
        return RepairPatch(**d)  # type: ignore[arg-type]

    def test_lane_a_success(self) -> None:
        runner = self._runner()
        diag = _diag("diag_target")
        base = ArtifactSnapshot("snap_1", "run_1", 0, compile_diagnostics=(diag,))
        patched = ArtifactSnapshot("snap_1", "run_1", 1, compile_diagnostics=())
        result = runner.verify(self._patch(), base, patched)
        assert result.accepted is True
        assert result.resolved_diagnostic_ids == ("diag_target",)

    def test_new_blocking_causes_rejection(self) -> None:
        runner = self._runner()
        base = ArtifactSnapshot("snap_1", "run_1", 0, compile_diagnostics=())
        patched = ArtifactSnapshot(
            "snap_1",
            "run_1",
            1,
            compile_diagnostics=(_diag("new_blocker"),),
        )
        result = runner.verify(self._patch(), base, patched)
        assert result.accepted is False
        assert "new_blocker" in result.failure_reasons[0]

    def test_target_not_resolved_causes_rejection(self) -> None:
        """B4: Target diagnostic still present → rejected."""
        runner = self._runner()
        diag = _diag("diag_target")
        base = ArtifactSnapshot("snap_1", "run_1", 0, compile_diagnostics=(diag,))
        patched = ArtifactSnapshot("snap_1", "run_1", 1, compile_diagnostics=(diag,))
        result = runner.verify(self._patch(), base, patched)
        assert result.accepted is False
        assert "diag_target" in result.failure_reasons[0]

    def test_injected_lane_adapter_is_used(self) -> None:
        """B4: Runner uses injected adapter, not new default instance."""
        called = []

        class SpyLane(LaneAReplayAdapter):
            def replay(self, snapshot):
                called.append("A")
                return VerificationArtifacts()

        runner = VerificationRunner(lane_a=SpyLane())
        base = ArtifactSnapshot("snap_1", "run_1", 0)
        patched = ArtifactSnapshot("snap_1", "run_1", 1)
        runner.verify(self._patch(), base, patched)
        assert called == ["A"], "Injected lane adapter must be called"

    def test_unknown_lane_raises_typed_error(self) -> None:
        """B4: Unknown lane 'C' raises PatchValidationError, not fallback to A."""
        runner = self._runner()
        base = ArtifactSnapshot("snap_1", "run_1", 0)
        patched = ArtifactSnapshot("snap_1", "run_1", 1)
        with pytest.raises(PatchValidationError, match="Unknown verification lane"):
            runner.verify(
                self._patch(verification_lane="C"),
                base,
                patched,
            )

    def test_missing_target_diagnostic_id_causes_rejection(self) -> None:
        """B4: Empty related_diagnostic_id → rejected (cannot prove fix)."""
        runner = self._runner()
        base = ArtifactSnapshot("snap_1", "run_1", 0)
        patched = ArtifactSnapshot("snap_1", "run_1", 1)
        patch = self._patch(
            evidence=RepairEvidence(related_diagnostic_id=""),
        )
        result = runner.verify(patch, base, patched)
        assert result.accepted is False
        assert "related_diagnostic_id" in result.failure_reasons[0]

    def test_patch_verifier_wrong_return_type(self) -> None:
        """B4: Verifier returning non-tuple is flagged as failure."""
        runner = self._runner()

        class BadVerifier:
            def verify(self, patch, base, patched, artifacts):
                return "not_a_tuple"

        diag = _diag("diag_target")
        base = ArtifactSnapshot("snap_1", "run_1", 0, compile_diagnostics=(diag,))
        patched = ArtifactSnapshot("snap_1", "run_1", 1, compile_diagnostics=())
        result = runner.verify(self._patch(), base, patched, BadVerifier())
        assert result.accepted is False
        assert "tuple" in result.failure_reasons[0]
