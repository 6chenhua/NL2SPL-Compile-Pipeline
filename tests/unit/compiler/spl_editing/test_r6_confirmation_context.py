"""Tests for ConfirmationContextStore state machine."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.confirmation_context import (
    ConfirmationContextStore,
    RepairConfirmationContext,
)
from nl2spl.compiler.spl_editing.core.errors import SPLEditingError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(context_id: str = "ctx_sess_1_sug_0") -> RepairConfirmationContext:
    return RepairConfirmationContext(
        context_id=context_id,
        session_id="sess_1",
        suggestion_id="sug_0",
        patch_id="patch_0",
        compile_run_id="run_1",
        intent_id="int_001",
        issue=None,
        target=None,
        catalog_entry=None,
        refset=None,
        selected_ref_ids=(),
        resolved_refs=(),
        snapshot_id="snap_1",
        overlay_version=0,
        created_at="2026-06-26T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# seal
# ---------------------------------------------------------------------------


class TestSeal:
    def test_seal_then_get_returns_context(self):
        store = ConfirmationContextStore()
        ctx = _make_ctx()
        store.seal(ctx)
        assert store.get("ctx_sess_1_sug_0") is ctx

    def test_duplicate_seal_raises(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        with pytest.raises(SPLEditingError, match="Duplicate"):
            store.seal(_make_ctx())

    def test_seal_with_previous_tombstone_raises(self):
        store = ConfirmationContextStore()
        ctx = _make_ctx()
        store.seal(ctx)
        store.begin_apply("ctx_sess_1_sug_0")
        store.commit_consumed("ctx_sess_1_sug_0")
        with pytest.raises(SPLEditingError, match="terminal"):
            store.seal(_make_ctx())


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestGet:
    def test_get_sealed_returns_context(self):
        store = ConfirmationContextStore()
        ctx = _make_ctx()
        store.seal(ctx)
        assert store.get("ctx_sess_1_sug_0") is ctx

    def test_get_unknown_raises(self):
        store = ConfirmationContextStore()
        with pytest.raises(SPLEditingError, match="Unknown"):
            store.get("nonexistent")

    def test_get_consumed_raises_with_tombstone(self):
        store = ConfirmationContextStore()
        ctx = _make_ctx()
        store.seal(ctx)
        store.begin_apply("ctx_sess_1_sug_0")
        store.commit_consumed("ctx_sess_1_sug_0")
        with pytest.raises(SPLEditingError, match="consumed"):
            store.get("ctx_sess_1_sug_0")

    def test_get_expired_raises_with_tombstone(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.expire("ctx_sess_1_sug_0", "stale revision")
        with pytest.raises(SPLEditingError, match="expired"):
            store.get("ctx_sess_1_sug_0")

    def test_get_rejected_raises_with_tombstone(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.reject("ctx_sess_1_sug_0", "cross-session")
        with pytest.raises(SPLEditingError, match="rejected"):
            store.get("ctx_sess_1_sug_0")


# ---------------------------------------------------------------------------
# begin_apply
# ---------------------------------------------------------------------------


class TestBeginApply:
    def test_begin_apply_transitions_sealed_to_applying(self):
        store = ConfirmationContextStore()
        ctx = _make_ctx()
        store.seal(ctx)
        result = store.begin_apply("ctx_sess_1_sug_0")
        assert result is ctx
        # After begin_apply, get() should fail (not SEALED)
        with pytest.raises(SPLEditingError, match="applying"):
            store.get("ctx_sess_1_sug_0")

    def test_begin_apply_twice_raises(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.begin_apply("ctx_sess_1_sug_0")
        with pytest.raises(SPLEditingError, match="already being applied"):
            store.begin_apply("ctx_sess_1_sug_0")

    def test_begin_apply_on_terminal_raises(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.expire("ctx_sess_1_sug_0", "test")
        with pytest.raises(SPLEditingError, match="expired"):
            store.begin_apply("ctx_sess_1_sug_0")

    def test_begin_apply_unknown_context_raises(self):
        store = ConfirmationContextStore()
        with pytest.raises(SPLEditingError, match="Unknown"):
            store.begin_apply("nonexistent")


# ---------------------------------------------------------------------------
# abort_apply
# ---------------------------------------------------------------------------


class TestAbortApply:
    def test_abort_apply_returns_applying_to_sealed(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.begin_apply("ctx_sess_1_sug_0")
        store.abort_apply("ctx_sess_1_sug_0")
        # Should be retrievable again
        assert store.get("ctx_sess_1_sug_0") is not None

    def test_abort_apply_on_sealed_is_noop(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.abort_apply("ctx_sess_1_sug_0")  # no-op
        assert store.get("ctx_sess_1_sug_0") is not None

    def test_abort_apply_on_terminal_is_noop(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.begin_apply("ctx_sess_1_sug_0")
        store.commit_consumed("ctx_sess_1_sug_0")
        store.abort_apply("ctx_sess_1_sug_0")  # no-op, already terminal


# ---------------------------------------------------------------------------
# commit_consumed
# ---------------------------------------------------------------------------


class TestCommitConsumed:
    def test_commit_consumed_succeeds(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.begin_apply("ctx_sess_1_sug_0")
        ctx = store.commit_consumed("ctx_sess_1_sug_0")
        assert ctx.context_id == "ctx_sess_1_sug_0"

    def test_commit_consumed_without_begin_apply_raises(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        with pytest.raises(SPLEditingError, match="not applying"):
            store.commit_consumed("ctx_sess_1_sug_0")

    def test_commit_consumed_twice_raises(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.begin_apply("ctx_sess_1_sug_0")
        store.commit_consumed("ctx_sess_1_sug_0")
        with pytest.raises(SPLEditingError, match="not applying"):
            store.commit_consumed("ctx_sess_1_sug_0")

    def test_commit_consumed_after_abort_raises(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.begin_apply("ctx_sess_1_sug_0")
        store.abort_apply("ctx_sess_1_sug_0")
        with pytest.raises(SPLEditingError, match="not applying"):
            store.commit_consumed("ctx_sess_1_sug_0")


# ---------------------------------------------------------------------------
# expire / reject
# ---------------------------------------------------------------------------


class TestExpire:
    def test_expire_from_sealed(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.expire("ctx_sess_1_sug_0", "stale")
        with pytest.raises(SPLEditingError, match="expired"):
            store.get("ctx_sess_1_sug_0")
        assert store.active_count() == 0

    def test_expire_from_applying(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.begin_apply("ctx_sess_1_sug_0")
        store.expire("ctx_sess_1_sug_0", "stale during apply")
        with pytest.raises(SPLEditingError, match="expired"):
            store.get("ctx_sess_1_sug_0")
        assert store.active_count() == 0

    def test_expire_unknown_is_noop(self):
        store = ConfirmationContextStore()
        store.expire("nonexistent", "test")  # no-op


class TestReject:
    def test_reject_from_sealed(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.reject("ctx_sess_1_sug_0", "cross-session")
        with pytest.raises(SPLEditingError, match="rejected"):
            store.get("ctx_sess_1_sug_0")
        assert store.active_count() == 0

    def test_reject_from_applying(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.begin_apply("ctx_sess_1_sug_0")
        store.reject("ctx_sess_1_sug_0", "payload contract violation")
        with pytest.raises(SPLEditingError, match="rejected"):
            store.get("ctx_sess_1_sug_0")
        assert store.active_count() == 0

    def test_reject_unknown_is_noop(self):
        store = ConfirmationContextStore()
        store.reject("nonexistent", "test")  # no-op


# ---------------------------------------------------------------------------
# is_sealed / active_count
# ---------------------------------------------------------------------------


class TestQuery:
    def test_is_sealed_true(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        assert store.is_sealed("ctx_sess_1_sug_0") is True

    def test_is_sealed_false_when_applying(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.begin_apply("ctx_sess_1_sug_0")
        assert store.is_sealed("ctx_sess_1_sug_0") is False

    def test_is_sealed_false_when_terminal(self):
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.begin_apply("ctx_sess_1_sug_0")
        store.commit_consumed("ctx_sess_1_sug_0")
        assert store.is_sealed("ctx_sess_1_sug_0") is False

    def test_active_count(self):
        store = ConfirmationContextStore()
        assert store.active_count() == 0
        store.seal(_make_ctx("ctx_1"))
        assert store.active_count() == 1
        store.seal(_make_ctx("ctx_2"))
        assert store.active_count() == 2
        store.begin_apply("ctx_1")
        store.commit_consumed("ctx_1")
        assert store.active_count() == 1


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    def test_seal_begin_abort_seal_begin_commit(self):
        """Full retry lifecycle: seal → apply fail → abort → retry → commit."""
        store = ConfirmationContextStore()
        store.seal(_make_ctx())

        # First attempt fails
        store.begin_apply("ctx_sess_1_sug_0")
        store.abort_apply("ctx_sess_1_sug_0")

        # Retry — should be back to SEALED
        assert store.is_sealed("ctx_sess_1_sug_0")
        store.begin_apply("ctx_sess_1_sug_0")
        store.commit_consumed("ctx_sess_1_sug_0")

        # Terminal
        with pytest.raises(SPLEditingError, match="consumed"):
            store.get("ctx_sess_1_sug_0")

    def test_seal_begin_expire_during_apply(self):
        """Stale revision detected during apply — expire, no retry."""
        store = ConfirmationContextStore()
        store.seal(_make_ctx())
        store.begin_apply("ctx_sess_1_sug_0")
        store.expire("ctx_sess_1_sug_0", "stale revision during apply")
        # Cannot retry
        with pytest.raises(SPLEditingError, match="expired"):
            store.begin_apply("ctx_sess_1_sug_0")
