"""S0 Neutral Snapshot Foundation tests.

Verifies:
    - All S0 models are importable and frozen.
    - Base identity invariants (overlay_version=0, no parent).
    - Overlay identity invariants (lineage preservation, version increment).
    - Identity validation catches invalid states.
    - Declared vs effective capability distinction.
    - SnapshotDocument base/overlay construction rules.
    - Editing history is empty for base snapshots.
    - Import boundary: no SPL Editing runtime imports.
    - All status/capability values are S-1 defined.
"""

from __future__ import annotations

import dataclasses

import pytest

# ===================================================================
# Import boundary — model must not import SPL Editing internals
# ===================================================================


class TestImportBoundary:
    """The S0 model package MUST NOT import SPL Editing runtime code."""

    @pytest.mark.parametrize(
        "module_path",
        [
            "nl2spl.compiler.artifacts.snapshot.model.errors",
            "nl2spl.compiler.artifacts.snapshot.model.identity",
            "nl2spl.compiler.artifacts.snapshot.model.artifact_ref",
            "nl2spl.compiler.artifacts.snapshot.model.integrity",
            "nl2spl.compiler.artifacts.snapshot.model.editing_history",
            "nl2spl.compiler.artifacts.snapshot.model.validation",
            "nl2spl.compiler.artifacts.snapshot.model.payload",
            "nl2spl.compiler.artifacts.snapshot.model.document",
        ],
    )
    def test_model_module_does_not_import_spl_editing(self, module_path: str) -> None:
        import importlib
        import sys

        mod = sys.modules.get(module_path)
        if mod is None:
            mod = importlib.import_module(module_path)

        forbidden_prefixes = (
            "nl2spl.compiler.spl_editing.patches",
            "nl2spl.compiler.spl_editing.handlers",
            "nl2spl.compiler.spl_editing.storage",
        )
        for key in dir(mod):
            obj = getattr(mod, key)
            if hasattr(obj, "__module__"):
                mod_name = getattr(obj, "__module__", "")
                for forbidden in forbidden_prefixes:
                    assert not mod_name.startswith(forbidden), (
                        f"{module_path} imports {mod_name} (forbidden: {forbidden})"
                    )


# ===================================================================
# Errors — typed hierarchy
# ===================================================================


class TestSnapshotErrors:
    def test_base_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotError

        err = SnapshotError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"

    def test_identity_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotError,
            SnapshotIdentityError,
        )

        err = SnapshotIdentityError("bad field")
        assert isinstance(err, SnapshotError)

    def test_lineage_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotError,
            SnapshotLineageError,
        )

        err = SnapshotLineageError("mismatch")
        assert isinstance(err, SnapshotError)

    def test_capability_error_carries_details(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotCapabilityError,
        )

        err = SnapshotCapabilityError("lane_b_replay", "missing normalizer input")
        assert err.capability == "lane_b_replay"
        assert err.reason == "missing normalizer input"
        assert "lane_b_replay" in str(err)

    def test_integrity_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotError,
            SnapshotIntegrityError,
        )

        err = SnapshotIntegrityError("hash mismatch")
        assert isinstance(err, SnapshotError)

    def test_schema_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotSchemaError,
        )

        err = SnapshotSchemaError("incompatible version")
        assert isinstance(err, Exception)

    def test_artifact_ref_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotArtifactRefError,
        )

        err = SnapshotArtifactRefError("broken ref")
        assert isinstance(err, Exception)


# ===================================================================
# SnapshotIdentity — base invariants
# ===================================================================


class TestBaseIdentity:
    def test_new_base_identity_has_overlay_version_zero(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity

        ident = new_base_identity(
            compile_run_id="run-001",
            snapshot_id="snap-001",
            created_at="2025-01-15T10:30:00Z",
        )
        assert ident.overlay_version == 0
        assert ident.is_base is True
        assert ident.is_overlay is False

    def test_base_identity_sets_base_snapshot_id_to_self(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity

        ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        assert ident.base_snapshot_id == ident.snapshot_id
        assert ident.base_snapshot_id == "snap-001"

    def test_base_identity_parent_is_none(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity

        ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        assert ident.parent_snapshot_id is None

    def test_base_identity_producer_is_nl2spl(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity

        ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        assert ident.producer == "nl2spl"

    def test_base_identity_is_frozen(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity

        ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        with pytest.raises(dataclasses.FrozenInstanceError):
            ident.overlay_version = 1  # type: ignore[misc]

    def test_base_identity_uses_imported_constant(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import BASE_OVERLAY_VERSION
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity

        ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        assert ident.overlay_version == BASE_OVERLAY_VERSION


# ===================================================================
# SnapshotIdentity — overlay invariants
# ===================================================================


class TestOverlayIdentity:
    def test_new_overlay_identity_increments_version(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        overlay = new_overlay_identity(
            base_identity=base,
            new_snapshot_id="snap-002",
            created_at="2025-01-15T10:35:00Z",
        )
        assert overlay.overlay_version == 1
        assert overlay.overlay_version > base.overlay_version
        assert overlay.is_overlay is True
        assert overlay.is_base is False

    def test_overlay_preserves_base_snapshot_id(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        overlay = new_overlay_identity(base, "snap-002", created_at="2025-01-15T10:35:00Z")
        assert overlay.base_snapshot_id == base.base_snapshot_id
        assert overlay.base_snapshot_id == "snap-001"

    def test_overlay_preserves_compile_run_id(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        overlay = new_overlay_identity(base, "snap-002", created_at="2025-01-15T10:35:00Z")
        assert overlay.compile_run_id == base.compile_run_id

    def test_overlay_has_parent_snapshot_id(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        overlay = new_overlay_identity(base, "snap-002", created_at="2025-01-15T10:35:00Z")
        assert overlay.parent_snapshot_id is not None
        assert overlay.parent_snapshot_id == base.snapshot_id

    def test_overlay_producer_is_nl2spl(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        overlay = new_overlay_identity(base, "snap-002", created_at="2025-01-15T10:35:00Z")
        assert overlay.producer == "nl2spl"

    def test_second_overlay_chains_correctly(self) -> None:
        """Second overlay should have parent = previous overlay, base = original."""
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        overlay1 = new_overlay_identity(base, "snap-002", created_at="2025-01-15T10:35:00Z")
        overlay2 = new_overlay_identity(
            base_identity=base,
            new_snapshot_id="snap-003",
            created_at="2025-01-15T10:40:00Z",
            parent_identity=overlay1,
        )

        assert overlay2.overlay_version == 2
        assert overlay2.base_snapshot_id == "snap-001"
        assert overlay2.parent_snapshot_id == "snap-002"
        assert overlay2.compile_run_id == "run-001"

    def test_overlay_identity_is_frozen(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        overlay = new_overlay_identity(base, "snap-002", created_at="2025-01-15T10:35:00Z")
        with pytest.raises(dataclasses.FrozenInstanceError):
            overlay.overlay_version = 5  # type: ignore[misc]

    def test_parent_from_different_run_raises(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotLineageError,
        )
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base_a = new_base_identity("run-A", "snap-001", created_at="2025-01-15T10:30:00Z")
        base_b = new_base_identity("run-B", "snap-002", created_at="2025-01-15T10:35:00Z")
        with pytest.raises(SnapshotLineageError, match="compile_run_id"):
            new_overlay_identity(
                base_identity=base_a,
                new_snapshot_id="snap-003",
                created_at="2025-01-15T10:40:00Z",
                parent_identity=base_b,
            )

    def test_parent_from_different_base_raises(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotLineageError,
        )
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base = new_base_identity("run-001", "snap-A", created_at="2025-01-15T10:30:00Z")
        other = new_base_identity("run-001", "snap-B", created_at="2025-01-15T10:35:00Z")
        with pytest.raises(SnapshotLineageError, match="base_snapshot_id"):
            new_overlay_identity(
                base_identity=base,
                new_snapshot_id="snap-C",
                created_at="2025-01-15T10:40:00Z",
                parent_identity=other,
            )

    def test_parent_with_same_snapshot_id_as_new_raises(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotLineageError,
        )
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        with pytest.raises(SnapshotLineageError, match="snapshot_id"):
            new_overlay_identity(
                base_identity=base,
                new_snapshot_id="snap-001",  # same as parent
                created_at="2025-01-15T10:35:00Z",
                parent_identity=base,
            )


# ===================================================================
# validate_base_identity
# ===================================================================


class TestValidateBaseIdentity:
    def test_valid_base_returns_no_errors(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            validate_base_identity,
        )

        ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        assert validate_base_identity(ident) == []

    def test_nonzero_overlay_version_is_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            SnapshotIdentity,
            validate_base_identity,
        )

        ident = SnapshotIdentity(
            compile_run_id="run-001",
            snapshot_id="snap-001",
            base_snapshot_id="snap-001",
            parent_snapshot_id=None,
            overlay_version=3,
            created_at="2025-01-15T10:30:00Z",
        )
        errors = validate_base_identity(ident)
        assert len(errors) >= 1
        assert any("overlay_version" in e for e in errors)

    def test_mismatched_base_snapshot_id_is_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            SnapshotIdentity,
            validate_base_identity,
        )

        ident = SnapshotIdentity(
            compile_run_id="run-001",
            snapshot_id="snap-001",
            base_snapshot_id="snap-OTHER",
            parent_snapshot_id=None,
            overlay_version=0,
            created_at="2025-01-15T10:30:00Z",
        )
        errors = validate_base_identity(ident)
        assert len(errors) >= 1
        assert any("base_snapshot_id" in e for e in errors)

    def test_non_null_parent_is_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            SnapshotIdentity,
            validate_base_identity,
        )

        ident = SnapshotIdentity(
            compile_run_id="run-001",
            snapshot_id="snap-001",
            base_snapshot_id="snap-001",
            parent_snapshot_id="snap-000",
            overlay_version=0,
            created_at="2025-01-15T10:30:00Z",
        )
        errors = validate_base_identity(ident)
        assert len(errors) >= 1
        assert any("parent_snapshot_id" in e for e in errors)

    def test_empty_compile_run_id_is_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            SnapshotIdentity,
            validate_base_identity,
        )

        ident = SnapshotIdentity(
            compile_run_id="",
            snapshot_id="snap-001",
            base_snapshot_id="snap-001",
            parent_snapshot_id=None,
            overlay_version=0,
            created_at="2025-01-15T10:30:00Z",
        )
        errors = validate_base_identity(ident)
        assert len(errors) >= 1
        assert any("compile_run_id" in e for e in errors)


# ===================================================================
# validate_overlay_lineage
# ===================================================================


class TestValidateOverlayLineage:
    def test_valid_overlay_returns_no_errors(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
            validate_overlay_lineage,
        )

        base = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        overlay = new_overlay_identity(base, "snap-002", created_at="2025-01-15T10:35:00Z")
        assert validate_overlay_lineage(overlay, base) == []

    def test_different_compile_run_id_is_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            validate_overlay_lineage,
        )

        parent = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        wrong = new_base_identity("run-002", "snap-002", created_at="2025-01-15T10:35:00Z")
        errors = validate_overlay_lineage(wrong, parent)
        assert len(errors) >= 1
        assert any("compile_run_id" in e for e in errors)

    def test_different_base_snapshot_id_is_error(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            validate_overlay_lineage,
        )

        parent = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        other = new_base_identity("run-001", "snap-OTHER", created_at="2025-01-15T10:35:00Z")
        errors = validate_overlay_lineage(other, parent)
        assert len(errors) >= 1
        assert any("base_snapshot_id" in e for e in errors)

    def test_overlay_version_not_exact_increment_is_error(self) -> None:
        """Version must be exactly parent + 1; same or skipped both fail."""
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            SnapshotIdentity,
            new_base_identity,
            validate_overlay_lineage,
        )

        parent = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")

        # Same version as parent (not strictly +1)
        same_version = SnapshotIdentity(
            compile_run_id="run-001",
            snapshot_id="snap-002",
            base_snapshot_id="snap-001",
            parent_snapshot_id="snap-001",
            overlay_version=0,
            created_at="2025-01-15T10:35:00Z",
        )
        errors = validate_overlay_lineage(same_version, parent)
        assert len(errors) >= 1
        assert any("overlay_version" in e for e in errors)

    def test_overlay_version_skip_is_error(self) -> None:
        """Version skipping (0 -> 5) must be rejected."""
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            SnapshotIdentity,
            new_base_identity,
            validate_overlay_lineage,
        )

        parent = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        skip = SnapshotIdentity(
            compile_run_id="run-001",
            snapshot_id="snap-skip",
            base_snapshot_id="snap-001",
            parent_snapshot_id="snap-001",
            overlay_version=5,
            created_at="2025-01-15T10:35:00Z",
        )
        errors = validate_overlay_lineage(skip, parent)
        assert len(errors) >= 1
        assert any("overlay_version" in e for e in errors)

    def test_null_parent_is_error_for_overlay(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            SnapshotIdentity,
            new_base_identity,
            validate_overlay_lineage,
        )

        parent = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        no_parent = SnapshotIdentity(
            compile_run_id="run-001",
            snapshot_id="snap-002",
            base_snapshot_id="snap-001",
            parent_snapshot_id=None,
            overlay_version=1,
            created_at="2025-01-15T10:35:00Z",
        )
        errors = validate_overlay_lineage(no_parent, parent)
        assert len(errors) >= 1
        assert any("parent_snapshot_id" in e for e in errors)

    def test_wrong_parent_snapshot_id_is_error(self) -> None:
        """overlay.parent_snapshot_id must equal parent.snapshot_id."""
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            SnapshotIdentity,
            new_base_identity,
            validate_overlay_lineage,
        )

        parent = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        wrong_parent = SnapshotIdentity(
            compile_run_id="run-001",
            snapshot_id="snap-002",
            base_snapshot_id="snap-001",
            parent_snapshot_id="snap-WRONG",
            overlay_version=1,
            created_at="2025-01-15T10:35:00Z",
        )
        errors = validate_overlay_lineage(wrong_parent, parent)
        assert len(errors) >= 1
        assert any("parent_snapshot_id" in e for e in errors)


# ===================================================================
# ArtifactRef / DerivedArtifactRef
# ===================================================================


class TestArtifactRef:
    def test_construction(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import ArtifactRef

        ref = ArtifactRef(
            ref="payload.stage_artifacts.worker_step_plan",
            artifact_hash="sha256:abc123",
        )
        assert ref.ref == "payload.stage_artifacts.worker_step_plan"
        assert ref.artifact_hash == "sha256:abc123"

    def test_is_frozen(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import ArtifactRef

        ref = ArtifactRef(ref="payload.stage_artifacts.worker_plan", artifact_hash="sha256:def")
        with pytest.raises(dataclasses.FrozenInstanceError):
            ref.artifact_hash = "sha256:xxx"  # type: ignore[misc]

    def test_empty_ref_raises(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import ArtifactRef
        from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotArtifactRefError

        with pytest.raises(SnapshotArtifactRefError, match="ref"):
            ArtifactRef(ref="", artifact_hash="sha256:abc")

    def test_empty_hash_raises(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import ArtifactRef
        from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotArtifactRefError

        with pytest.raises(SnapshotArtifactRefError, match="artifact_hash"):
            ArtifactRef(ref="payload.stage_artifacts.worker_plan", artifact_hash="")


class TestDerivedArtifactRef:
    def test_construction(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import DerivedArtifactRef

        ref = DerivedArtifactRef(
            derived_from="payload.stage_artifacts.worker_step_plan",
            derivation="stage9_5_normalized",
            artifact_hash="sha256:def456",
        )
        assert ref.derived_from == "payload.stage_artifacts.worker_step_plan"
        assert ref.derivation == "stage9_5_normalized"

    def test_empty_derived_from_raises(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import DerivedArtifactRef
        from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotArtifactRefError

        with pytest.raises(SnapshotArtifactRefError, match="derived_from"):
            DerivedArtifactRef(
                derived_from="",
                derivation="stage9_5_normalized",
                artifact_hash="sha256:abc",
            )

    def test_empty_derivation_raises(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import DerivedArtifactRef
        from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotArtifactRefError

        with pytest.raises(SnapshotArtifactRefError, match="derivation"):
            DerivedArtifactRef(
                derived_from="payload.stage_artifacts.worker_step_plan",
                derivation="",
                artifact_hash="sha256:abc",
            )


# ===================================================================
# SnapshotIntegrity
# ===================================================================


class TestSnapshotIntegrity:
    def test_construction(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.integrity import SnapshotIntegrity

        integ = SnapshotIntegrity(payload_hash="sha256:ph", artifact_set_hash="sha256:ah")
        assert integ.payload_hash == "sha256:ph"
        assert integ.artifact_set_hash == "sha256:ah"

    def test_empty_payload_hash_raises(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotIntegrityError
        from nl2spl.compiler.artifacts.snapshot.model.integrity import SnapshotIntegrity

        with pytest.raises(SnapshotIntegrityError, match="payload_hash"):
            SnapshotIntegrity(payload_hash="", artifact_set_hash="sha256:ah")

    def test_empty_artifact_set_hash_raises(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotIntegrityError
        from nl2spl.compiler.artifacts.snapshot.model.integrity import SnapshotIntegrity

        with pytest.raises(SnapshotIntegrityError, match="artifact_set_hash"):
            SnapshotIntegrity(payload_hash="sha256:ph", artifact_set_hash="")


# ===================================================================
# Editing history DTOs
# ===================================================================


class TestEditingHistoryDTOs:
    def test_overlay_event_dto_is_frozen(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotOverlayEventDTO,
        )

        dto = SnapshotOverlayEventDTO(
            overlay_id="ov-001",
            base_compile_run_id="run-001",
            base_artifact_snapshot_id="snap-001",
            overlay_version=1,
            patch_type="add_exception_handler_step",
            affordance_id="MISSING_HANDLER.ADD_HANDLER_STEP",
            patch_id="patch-001",
            accepted=True,
        )
        assert dto.accepted is True
        with pytest.raises(dataclasses.FrozenInstanceError):
            dto.accepted = False  # type: ignore[misc]

    def test_accepted_patch_dto_is_frozen(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotAcceptedPatchDTO,
        )

        dto = SnapshotAcceptedPatchDTO(
            patch_id="patch-001",
            patch_type="add_exception_handler_step",
            affordance_id="MISSING_HANDLER.ADD_HANDLER_STEP",
            overlay_id="ov-001",
        )
        assert dto.patch_id == "patch-001"

    def test_verification_record_dto_is_frozen(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotVerificationRecordDTO,
        )

        dto = SnapshotVerificationRecordDTO(
            verification_id="vrf-001",
            overlay_id="ov-001",
            lane="A",
            passed=True,
            diagnostic_count_before=3,
            diagnostic_count_after=1,
        )
        assert dto.passed is True
        assert dto.lane == "A"

    def test_empty_editing_history(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            empty_editing_history,
        )

        h = empty_editing_history()
        assert h.is_empty is True
        assert h.overlay_events == ()
        assert h.accepted_patches == ()
        assert h.verification_history == ()

    def test_non_empty_editing_history_is_not_empty(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotAcceptedPatchDTO,
            SnapshotEditingHistory,
        )

        h = SnapshotEditingHistory(
            accepted_patches=(
                SnapshotAcceptedPatchDTO(
                    patch_id="p1",
                    patch_type="add_exception_handler_step",
                    affordance_id="AFF",
                    overlay_id="ov-001",
                ),
            ),
        )
        assert h.is_empty is False

    def test_editing_history_is_frozen(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            empty_editing_history,
        )

        h = empty_editing_history()
        with pytest.raises(dataclasses.FrozenInstanceError):
            h.overlay_events = (None,)  # type: ignore[misc]


# ===================================================================
# SnapshotPayload — layers
# ===================================================================


class TestPayloadLayers:
    def test_source_layer_defaults(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.payload import SourceLayer

        layer = SourceLayer()
        assert layer.canonical_input is None
        assert layer.spans == ()
        assert layer.routes is None
        assert layer.construct_plan is None

    def test_stage_artifacts_layer_defaults(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.payload import StageArtifactsLayer

        layer = StageArtifactsLayer()
        assert layer.worker_plan is None
        assert layer.worker_step_plan is None
        assert layer.resources is None
        assert layer.constraints == ()

    def test_replay_artifacts_layer_defaults(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.payload import ReplayArtifactsLayer

        layer = ReplayArtifactsLayer()
        assert layer.normalizer_input is None
        assert layer.stage10_input is None
        assert layer.final_spl is None

    def test_diagnostics_layer_defaults(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.payload import DiagnosticsLayer

        layer = DiagnosticsLayer()
        assert layer.compile_diagnostics == ()

    def test_provenance_layer_defaults(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.payload import ProvenanceLayer

        layer = ProvenanceLayer()
        assert layer.traces == ()

    def test_editing_layer_defaults_are_empty(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.payload import EditingLayer

        layer = EditingLayer()
        assert layer.history.is_empty is True

    def test_full_payload_defaults(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.payload import SnapshotPayload

        payload = SnapshotPayload()
        assert payload.source.spans == ()
        assert payload.stage_artifacts.worker_plan is None
        assert payload.editing.history.is_empty is True

    def test_all_layers_are_frozen(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.payload import (
            DiagnosticsLayer,
            SourceLayer,
            StageArtifactsLayer,
        )

        for layer_cls in [SourceLayer, StageArtifactsLayer, DiagnosticsLayer]:
            layer = layer_cls()
            for field_info in dataclasses.fields(layer_cls):
                with pytest.raises(dataclasses.FrozenInstanceError):
                    setattr(layer, field_info.name, None)


# ===================================================================
# Capabilities — declared vs effective
# ===================================================================


class TestCapabilities:
    def test_declared_capabilities_empty_by_default(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotDeclaredCapabilities,
        )

        dc = SnapshotDeclaredCapabilities()
        assert dc.count == 0
        assert dc.capabilities == ()

    def test_declared_capabilities_has_method(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotDeclaredCapabilities,
        )

        dc = SnapshotDeclaredCapabilities(
            capabilities=(SnapshotCapability.ISSUE_EXTRACTION,)
        )
        assert dc.has(SnapshotCapability.ISSUE_EXTRACTION) is True
        assert dc.has(SnapshotCapability.LANE_A_REPLAY) is False

    def test_effective_capabilities_empty_by_default(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotEffectiveCapabilities,
        )

        ec = SnapshotEffectiveCapabilities()
        assert ec.count == 0

    def test_effective_capabilities_require_raises(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotCapabilityError,
        )
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotEffectiveCapabilities,
        )

        ec = SnapshotEffectiveCapabilities()
        with pytest.raises(SnapshotCapabilityError):
            ec.require(SnapshotCapability.LANE_A_REPLAY)

    def test_effective_capabilities_require_succeeds_when_present(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotEffectiveCapabilities,
        )

        ec = SnapshotEffectiveCapabilities(
            capabilities=(SnapshotCapability.LANE_A_REPLAY,)
        )
        # Should not raise
        ec.require(SnapshotCapability.LANE_A_REPLAY)

    def test_effective_capabilities_has(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotEffectiveCapabilities,
        )

        ec = SnapshotEffectiveCapabilities(
            capabilities=(
                SnapshotCapability.ISSUE_EXTRACTION,
                SnapshotCapability.FINAL_SPL_DISPLAY,
            )
        )
        assert ec.has(SnapshotCapability.ISSUE_EXTRACTION) is True
        assert ec.has(SnapshotCapability.FINAL_SPL_DISPLAY) is True
        assert ec.has(SnapshotCapability.LANE_B_REPLAY) is False

    def test_capability_failure_details(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotCapabilityFailure,
        )

        f = SnapshotCapabilityFailure(
            capability=SnapshotCapability.LANE_B_REPLAY,
            reason="missing_normalizer_input_bundle",
            missing_paths=("payload.replay_artifacts.normalizer_input",),
            unmet_conditions=("normalizer_input bundle is present and complete",),
        )
        assert f.capability == SnapshotCapability.LANE_B_REPLAY
        assert f.reason == "missing_normalizer_input_bundle"

    def test_effective_capabilities_includes_failures(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotCapabilityFailure,
            SnapshotEffectiveCapabilities,
        )

        ec = SnapshotEffectiveCapabilities(
            capabilities=(SnapshotCapability.ISSUE_EXTRACTION,),
            failures=(
                SnapshotCapabilityFailure(
                    capability=SnapshotCapability.LANE_B_REPLAY,
                    reason="missing normalizer input",
                ),
            ),
        )
        assert ec.count == 1
        assert ec.has(SnapshotCapability.LANE_B_REPLAY) is False
        assert len(ec.failures) == 1
        assert ec.failures[0].capability == SnapshotCapability.LANE_B_REPLAY


# ===================================================================
# SnapshotValidationResult
# ===================================================================


class TestSnapshotValidationResult:
    def test_valid_factory(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotEffectiveCapabilities,
            SnapshotValidationResult,
        )

        ec = SnapshotEffectiveCapabilities(
            capabilities=(SnapshotCapability.ISSUE_EXTRACTION,)
        )
        result = SnapshotValidationResult.valid(ec)
        assert result.is_valid is True
        assert result.errors == ()
        assert result.effective_capabilities is ec

    def test_invalid_factory(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotValidationResult,
        )

        result = SnapshotValidationResult.invalid(
            errors=("missing worker plan", "invalid schema version"),
        )
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert result.effective_capabilities.count == 0


# ===================================================================
# SnapshotDocument — base construction
# ===================================================================


class TestSnapshotDocument:
    def test_document_requires_explicit_identity(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument

        with pytest.raises(ValueError, match="identity"):
            SnapshotDocument()  # type: ignore[call-arg]

    def test_new_base_document(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.document import new_base_document
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity

        ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        doc = new_base_document(ident)
        assert doc.is_base is True
        assert doc.is_overlay is False
        assert doc.artifact_kind == "spl_editing_artifact_snapshot"
        assert doc.schema_version == "1.0.0"
        assert doc.has_base_editing_history is True

    def test_new_base_document_rejects_overlay_identity(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.document import new_base_document
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotIdentityError,
        )
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base_ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        overlay_ident = new_overlay_identity(
            base_ident, "snap-002", created_at="2025-01-15T10:35:00Z"
        )
        with pytest.raises(SnapshotIdentityError, match="is_base"):
            new_base_document(overlay_ident)

    def test_new_base_document_rejects_nonempty_editing_history(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.document import new_base_document
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotAcceptedPatchDTO,
            SnapshotEditingHistory,
        )
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotIdentityError,
        )
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity
        from nl2spl.compiler.artifacts.snapshot.model.payload import (
            EditingLayer,
            SnapshotPayload,
        )

        ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        payload = SnapshotPayload(
            editing=EditingLayer(
                history=SnapshotEditingHistory(
                    accepted_patches=(
                        SnapshotAcceptedPatchDTO(
                            patch_id="p1",
                            patch_type="add_exception_handler_step",
                            affordance_id="AFF",
                            overlay_id="ov-001",
                        ),
                    ),
                )
            )
        )
        with pytest.raises(SnapshotIdentityError, match="editing history"):
            new_base_document(ident, payload=payload)

    def test_document_with_declared_capabilities(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
        from nl2spl.compiler.artifacts.snapshot.model.document import new_base_document
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotDeclaredCapabilities,
        )

        ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        caps = SnapshotDeclaredCapabilities(
            capabilities=(SnapshotCapability.ISSUE_EXTRACTION,)
        )
        doc = new_base_document(ident, declared_capabilities=caps)
        assert doc.declared_capabilities.has(SnapshotCapability.ISSUE_EXTRACTION) is True
        assert doc.declared_capabilities.has(SnapshotCapability.LANE_A_REPLAY) is False

    def test_document_with_integrity(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.document import new_base_document
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity
        from nl2spl.compiler.artifacts.snapshot.model.integrity import SnapshotIntegrity

        ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        integ = SnapshotIntegrity(payload_hash="sha256:ph", artifact_set_hash="sha256:ah")
        doc = new_base_document(ident, integrity=integ)
        assert doc.integrity is integ
        assert doc.integrity.payload_hash == "sha256:ph"

    def test_document_is_frozen(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.document import new_base_document
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity

        ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        doc = new_base_document(ident)
        assert dataclasses.is_dataclass(doc)
        with pytest.raises(dataclasses.FrozenInstanceError):
            doc.artifact_kind = "other"  # type: ignore[misc]


# ===================================================================
# SnapshotDocument — overlay construction
# ===================================================================


class TestOverlayDocument:
    def test_new_overlay_document(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.document import (
            new_base_document,
            new_overlay_document,
        )
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base_ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        base_doc = new_base_document(base_ident)

        overlay_ident = new_overlay_identity(
            base_ident, "snap-002", created_at="2025-01-15T10:35:00Z"
        )
        # parent_document is the immediate predecessor
        overlay_doc = new_overlay_document(overlay_ident, base_doc)
        assert overlay_doc.is_overlay is True
        assert overlay_doc.is_base is False
        assert overlay_doc.identity.overlay_version == 1

    def test_overlay_chain_with_strict_parent(self) -> None:
        """Second overlay uses first overlay as parent, not base."""
        from nl2spl.compiler.artifacts.snapshot.model.document import (
            new_base_document,
            new_overlay_document,
        )
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            new_base_identity,
            new_overlay_identity,
        )

        base_ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        base_doc = new_base_document(base_ident)

        ov1_ident = new_overlay_identity(
            base_ident, "snap-002", created_at="2025-01-15T10:35:00Z"
        )
        ov1_doc = new_overlay_document(ov1_ident, base_doc)

        ov2_ident = new_overlay_identity(
            base_identity=base_ident,
            new_snapshot_id="snap-003",
            created_at="2025-01-15T10:40:00Z",
            parent_identity=ov1_ident,
        )
        ov2_doc = new_overlay_document(ov2_ident, ov1_doc)
        assert ov2_doc.identity.overlay_version == 2
        assert ov2_doc.identity.parent_snapshot_id == "snap-002"

    def test_new_overlay_document_rejects_base_identity(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.document import (
            new_base_document,
            new_overlay_document,
        )
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotIdentityError,
        )
        from nl2spl.compiler.artifacts.snapshot.model.identity import new_base_identity

        base_ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        base_doc = new_base_document(base_ident)

        with pytest.raises(SnapshotIdentityError, match="is_overlay"):
            new_overlay_document(base_ident, base_doc)

    def test_new_overlay_document_rejects_different_run_id(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.document import (
            new_base_document,
            new_overlay_document,
        )
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotLineageError,
        )
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            SnapshotIdentity,
            new_base_identity,
        )

        base_ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        base_doc = new_base_document(base_ident)

        wrong_ident = SnapshotIdentity(
            compile_run_id="run-DIFFERENT",
            snapshot_id="snap-002",
            base_snapshot_id="snap-001",
            parent_snapshot_id="snap-001",
            overlay_version=1,
            created_at="2025-01-15T10:35:00Z",
        )
        with pytest.raises(SnapshotLineageError, match="compile_run_id"):
            new_overlay_document(wrong_ident, base_doc)

    def test_new_overlay_document_rejects_wrong_parent(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.document import (
            new_base_document,
            new_overlay_document,
        )
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotLineageError,
        )
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            SnapshotIdentity,
            new_base_identity,
        )

        base_ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        base_doc = new_base_document(base_ident)

        wrong_parent = SnapshotIdentity(
            compile_run_id="run-001",
            snapshot_id="snap-002",
            base_snapshot_id="snap-001",
            parent_snapshot_id="snap-WRONG",
            overlay_version=1,
            created_at="2025-01-15T10:35:00Z",
        )
        with pytest.raises(SnapshotLineageError, match="parent_snapshot_id"):
            new_overlay_document(wrong_parent, base_doc)

    def test_new_overlay_document_rejects_version_skip(self) -> None:
        """Overlay version must be exactly parent + 1, no skipping allowed."""
        from nl2spl.compiler.artifacts.snapshot.model.document import (
            new_base_document,
            new_overlay_document,
        )
        from nl2spl.compiler.artifacts.snapshot.model.errors import (
            SnapshotLineageError,
        )
        from nl2spl.compiler.artifacts.snapshot.model.identity import (
            SnapshotIdentity,
            new_base_identity,
        )

        base_ident = new_base_identity("run-001", "snap-001", created_at="2025-01-15T10:30:00Z")
        base_doc = new_base_document(base_ident)

        skip_ident = SnapshotIdentity(
            compile_run_id="run-001",
            snapshot_id="snap-005",
            base_snapshot_id="snap-001",
            parent_snapshot_id="snap-001",
            overlay_version=5,  # skip from 0 -> 5
            created_at="2025-01-15T10:35:00Z",
        )
        with pytest.raises(SnapshotLineageError, match="overlay_version"):
            new_overlay_document(skip_ident, base_doc)


# ===================================================================
# Status / capability enums only allow S-1 values
# ===================================================================


class TestEnumValuesAreS1Defined:
    def test_snapshot_status_values_match_s1(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SnapshotStatus

        valid = {"not_requested", "available", "failed_best_effort", "failed_required"}
        actual = {s.value for s in SnapshotStatus}
        assert actual == valid

    def test_snapshot_mode_values_match_s1(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.constants import SnapshotMode

        valid = {"disabled", "best_effort", "required"}
        actual = {m.value for m in SnapshotMode}
        assert actual == valid

    def test_snapshot_capability_values_match_s1(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability

        valid = {
            "issue_extraction",
            "suggestion_generation",
            "lane_a_replay",
            "lane_b_replay",
            "final_spl_display",
        }
        actual = {c.value for c in SnapshotCapability}
        assert actual == valid

    def test_no_extra_enum_values_in_models(self) -> None:
        """All model code must use S-1 enums, not invent new values."""
        import inspect

        from nl2spl.compiler.artifacts.snapshot.model import editing_history

        source = inspect.getsource(editing_history)
        # Must not contain raw status strings
        assert '"available"' not in source
        assert '"failed_required"' not in source


# ===================================================================
# Model uses S-1 constants (not redefined strings)
# ===================================================================


class TestModelUsesS1Constants:
    def test_identity_uses_producer_name_constant(self) -> None:
        import inspect

        from nl2spl.compiler.artifacts.snapshot.model import identity

        source = inspect.getsource(identity)
        assert "PRODUCER_NAME" in source

    def test_identity_uses_schema_version_constant(self) -> None:
        import inspect

        from nl2spl.compiler.artifacts.snapshot.model import identity

        source = inspect.getsource(identity)
        assert "SNAPSHOT_SCHEMA_VERSION" in source

    def test_document_uses_artifact_kind_constant(self) -> None:
        import inspect

        from nl2spl.compiler.artifacts.snapshot.model import document

        source = inspect.getsource(document)
        assert "SNAPSHOT_ARTIFACT_KIND" in source

    def test_integrity_uses_integrity_field_constants(self) -> None:
        import inspect

        from nl2spl.compiler.artifacts.snapshot.model import integrity

        source = inspect.getsource(integrity)
        assert "INTEGRITY_PAYLOAD_HASH" in source
        assert "INTEGRITY_ARTIFACT_SET_HASH" in source


# ===================================================================
# No raw dict exposure — models are structured
# ===================================================================


class TestNoRawDictExposure:
    """Model types must be frozen dataclasses with typed fields, not raw dicts."""

    def test_snapshot_payload_is_dataclass_not_dict(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.payload import SnapshotPayload

        assert dataclasses.is_dataclass(SnapshotPayload)
        assert not isinstance(SnapshotPayload(), dict)

    def test_identity_is_not_dict(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.identity import SnapshotIdentity

        assert dataclasses.is_dataclass(SnapshotIdentity)

    def test_capabilities_are_not_dict(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.validation import (
            SnapshotDeclaredCapabilities,
            SnapshotEffectiveCapabilities,
        )

        assert dataclasses.is_dataclass(SnapshotDeclaredCapabilities)
        assert dataclasses.is_dataclass(SnapshotEffectiveCapabilities)

    def test_editing_dtos_are_dataclasses(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotAcceptedPatchDTO,
            SnapshotOverlayEventDTO,
            SnapshotVerificationRecordDTO,
        )

        assert dataclasses.is_dataclass(SnapshotOverlayEventDTO)
        assert dataclasses.is_dataclass(SnapshotAcceptedPatchDTO)
        assert dataclasses.is_dataclass(SnapshotVerificationRecordDTO)

    def test_editing_dto_fields_are_typed_not_raw_dict(self) -> None:
        """Verify editing DTOs don't have catch-all dict fields."""
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotOverlayEventDTO,
            SnapshotVerificationRecordDTO,
        )

        fields = {f.name: f.type for f in dataclasses.fields(SnapshotOverlayEventDTO)}
        required = ["overlay_id", "patch_type", "affordance_id", "patch_id"]
        for name in required:
            assert name in fields
            assert "dict" not in str(fields[name]).lower(), (
                f"{name} should not be 'dict' typed"
            )

        # Verify metadata is an immutable tuple, not a mutable dict
        vr_fields = {f.name: f.type for f in dataclasses.fields(SnapshotVerificationRecordDTO)}
        assert "metadata" in vr_fields
        assert "dict" not in str(vr_fields["metadata"]).lower(), (
            "metadata must not be a mutable dict"
        )

    def test_verification_record_metadata_is_immutable(self) -> None:
        """metadata must be a tuple so frozen=True actually prevents mutation."""
        from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
            SnapshotVerificationRecordDTO,
        )

        dto = SnapshotVerificationRecordDTO(
            verification_id="vrf-001",
            overlay_id="ov-001",
            lane="A",
            passed=True,
            diagnostic_count_before=3,
            diagnostic_count_after=1,
            metadata=(("irs_version", "1.0.0"),),
        )
        # The metadata field itself is a tuple — frozen=True protects it
        assert isinstance(dto.metadata, tuple)
        assert dto.metadata == (("irs_version", "1.0.0"),)
        # Attempting to reassign the field should raise
        with pytest.raises(dataclasses.FrozenInstanceError):
            dto.metadata = ()  # type: ignore[misc]
