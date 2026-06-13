"""B4: Patch registry and bundle tests."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.registry import PatchRegistry
from nl2spl.compiler.spl_editing.patches.registry import PatchBundle


class _FakeValidator:
    def validate(self, patch, snapshot):
        pass


class _FakeApplier:
    def apply(self, patch, snapshot):
        return snapshot, None


class _FakeVerifier:
    def verify(self, patch, base, patched, artifacts):
        return ()


class _FakePreviewer:
    def preview(self, payload):
        return ""


class TestB4PatchRegistry:
    """B4: PatchRegistry stores and retrieves PatchBundles."""

    def test_register_and_get(self) -> None:
        reg = PatchRegistry()
        bundle = PatchBundle(
            patch_type="AddExceptionHandlerStep",
            validator=_FakeValidator(),
            applier=_FakeApplier(),
            verifier=_FakeVerifier(),
            previewer=_FakePreviewer(),
        )
        reg.register("AddExceptionHandlerStep", bundle)
        assert reg.has("AddExceptionHandlerStep")
        assert reg.get("AddExceptionHandlerStep") is bundle

    def test_unknown_raises(self) -> None:
        import pytest
        reg = PatchRegistry()
        with pytest.raises(KeyError):
            reg.get("NoSuchPatch")

    def test_duplicate_registration_raises(self) -> None:
        import pytest
        reg = PatchRegistry()
        bundle = PatchBundle("T", _FakeValidator(), _FakeApplier(), _FakeVerifier(), _FakePreviewer())
        reg.register("T", bundle)
        with pytest.raises(KeyError):
            reg.register("T", bundle)

    def test_key_mismatch_raises(self) -> None:
        """B4: Registering bundle with mismatched patch_type raises ValueError."""
        import pytest
        reg = PatchRegistry()
        bundle = PatchBundle("WrongType", _FakeValidator(), _FakeApplier(), _FakeVerifier(), _FakePreviewer())
        with pytest.raises(ValueError, match="WrongType"):
            reg.register("AddExceptionHandlerStep", bundle)
