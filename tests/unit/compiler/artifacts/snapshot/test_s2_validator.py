"""S2 Snapshot Validator tests — schema, identity, capabilities, hashes."""

from __future__ import annotations

import pytest

from nl2spl.compiler.artifacts.snapshot.capabilities import SnapshotCapability
from nl2spl.compiler.artifacts.snapshot.model.document import (
    SnapshotDocument,
    new_base_document,
    new_overlay_document,
)
from nl2spl.compiler.artifacts.snapshot.model.identity import (
    new_base_identity,
    new_overlay_identity,
)
from nl2spl.compiler.artifacts.snapshot.model.integrity import SnapshotIntegrity
from nl2spl.compiler.artifacts.snapshot.model.payload import (
    DiagnosticsLayer,
    ReplayArtifactsLayer,
    SnapshotPayload,
    SourceLayer,
    StageArtifactsLayer,
)
from nl2spl.compiler.artifacts.snapshot.model.validation import (
    SnapshotDeclaredCapabilities,
    SnapshotEffectiveCapabilities,
)
from nl2spl.compiler.artifacts.snapshot.validation.validator import SnapshotValidator
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef


def _base_doc(**kwargs: object) -> SnapshotDocument:
    ident = new_base_identity("run-001", "snap-001", created_at="2025-06-15T10:00:00Z")
    return new_base_document(ident, **kwargs)  # type: ignore[arg-type]


# ===================================================================
# Envelope & schema
# ===================================================================


class TestEnvelopeValidation:
    def test_valid_envelope_passes(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc()
        result = v.validate(doc)
        assert result.is_valid is True

    def test_wrong_artifact_kind_fails(self) -> None:
        v = SnapshotValidator()
        ident = new_base_identity("run-001", "snap-001", created_at="2025-06-15T10:00:00Z")
        doc = SnapshotDocument(
            artifact_kind="wrong_kind",
            identity=ident,
        )
        result = v.validate(doc)
        assert result.is_valid is False
        assert any("artifact_kind" in e for e in result.errors)

    def test_incompatible_schema_version_fails(self) -> None:
        v = SnapshotValidator()
        ident = new_base_identity("run-001", "snap-001", created_at="2025-06-15T10:00:00Z")
        doc = SnapshotDocument(
            schema_version="0.0.1",
            identity=ident,
        )
        result = v.validate(doc)
        assert result.is_valid is False
        assert any("schema" in e.lower() for e in result.errors)


# ===================================================================
# Identity
# ===================================================================


class TestIdentityValidation:
    def test_base_identity_passes(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc()
        result = v.validate(doc)
        assert result.is_valid is True

    def test_base_with_nonzero_overlay_version_fails(self) -> None:
        v = SnapshotValidator()
        from nl2spl.compiler.artifacts.snapshot.model.identity import SnapshotIdentity

        ident = SnapshotIdentity(
            compile_run_id="run-001", snapshot_id="snap-001",
            base_snapshot_id="snap-001", parent_snapshot_id=None,
            overlay_version=3, created_at="t",
        )
        doc = SnapshotDocument(identity=ident)
        result = v.validate(doc)
        assert result.is_valid is False
        # Identity with overlay_version=3 but no parent: invalid state caught
        # by either overlay_version or parent_snapshot_id check
        assert any(
            "overlay_version" in e or "parent_snapshot_id" in e
            for e in result.errors
        )

    def test_base_with_parent_fails(self) -> None:
        v = SnapshotValidator()
        from nl2spl.compiler.artifacts.snapshot.model.identity import SnapshotIdentity

        ident = SnapshotIdentity(
            compile_run_id="run-001", snapshot_id="snap-001",
            base_snapshot_id="snap-001", parent_snapshot_id="snap-000",
            overlay_version=0, created_at="t",
        )
        doc = SnapshotDocument(identity=ident)
        result = v.validate(doc)
        assert result.is_valid is False

    def test_wrong_producer_fails(self) -> None:
        v = SnapshotValidator()
        from nl2spl.compiler.artifacts.snapshot.model.identity import SnapshotIdentity

        ident = SnapshotIdentity(
            compile_run_id="run-001", snapshot_id="snap-001",
            base_snapshot_id="snap-001", parent_snapshot_id=None,
            overlay_version=0, created_at="t", producer="other_tool",
        )
        doc = SnapshotDocument(identity=ident)
        result = v.validate(doc)
        assert result.is_valid is False
        assert any("producer" in e for e in result.errors)

    def test_empty_created_at_fails(self) -> None:
        v = SnapshotValidator()
        ident = new_base_identity("run-001", "snap-001", created_at="")
        doc = new_base_document(ident)
        result = v.validate(doc)
        assert result.is_valid is False
        assert any("created_at" in e for e in result.errors)

    def test_overlay_without_parent_fails(self) -> None:
        v = SnapshotValidator()
        from nl2spl.compiler.artifacts.snapshot.model.identity import SnapshotIdentity

        ident = SnapshotIdentity(
            compile_run_id="run-001", snapshot_id="snap-002",
            base_snapshot_id="snap-001", parent_snapshot_id=None,
            overlay_version=1, created_at="t",
        )
        doc = SnapshotDocument(identity=ident)
        result = v.validate(doc)
        assert result.is_valid is False
        assert any("parent_snapshot_id" in e for e in result.errors)


# ===================================================================
# Capability derivation
# ===================================================================


class TestCapabilityDerivation:
    def test_empty_document_has_no_capabilities(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc()
        result = v.validate(doc)
        caps = result.effective_capabilities
        assert caps.has(SnapshotCapability.ISSUE_EXTRACTION) is False
        assert caps.has(SnapshotCapability.LANE_A_REPLAY) is False

    def test_issue_extraction_requires_compile_diagnostics(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D1", kind="missing_handler",
                            severity="warning", message="test",
                            metadata={
                                "irs_ref": DiagnosticIRSRef("T", "id", "slot"),
                                "authority": "post_normalize_irs",
                                "repairability": "editable",
                                "issue_group_id": "g1",
                            },
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        assert result.effective_capabilities.has(SnapshotCapability.ISSUE_EXTRACTION) is True

    def test_issue_extraction_without_irs_ref_fails_capability(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D1", kind="missing_handler",
                            severity="warning", message="test",
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        # Missing metadata → capability not effective AND diagnostic validation errors
        assert result.effective_capabilities.has(SnapshotCapability.ISSUE_EXTRACTION) is False

    def test_non_editable_diagnostics_do_not_enable_issue_extraction(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="stage2_route_refinement_rejected_s4",
                            kind="route_refinement_rejected",
                            severity="warning",
                            message="Rejected route refinement",
                            target_ref="span:s4",
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        assert result.effective_capabilities.has(
            SnapshotCapability.ISSUE_EXTRACTION
        ) is False

    def test_declared_vs_effective_distinction(self) -> None:
        """Writer-declared capabilities must NOT be blindly trusted."""
        v = SnapshotValidator()
        doc = _base_doc(
            declared_capabilities=SnapshotDeclaredCapabilities(
                capabilities=(
                    SnapshotCapability.LANE_A_REPLAY,
                    SnapshotCapability.LANE_B_REPLAY,
                ),
            ),
        )
        result = v.validate(doc)
        # Writer declared them, but artifacts are missing → effective is empty
        assert result.effective_capabilities.has(SnapshotCapability.LANE_A_REPLAY) is False
        assert result.effective_capabilities.has(SnapshotCapability.LANE_B_REPLAY) is False

    def test_lane_a_replay_when_artifacts_present(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                stage_artifacts=StageArtifactsLayer(
                    worker_plan="wp", worker_flow_plan="wfp",
                    worker_block_plan="wbp", worker_step_plan="wsp",
                    resources="res", symbol_table="st",
                ),
                replay_artifacts=ReplayArtifactsLayer(
                    stage10_input="s10",
                ),
            ),
        )
        result = v.validate(doc)
        assert result.effective_capabilities.has(SnapshotCapability.LANE_A_REPLAY) is True

    def test_lane_b_replay_blocked_without_normalizer_input(self) -> None:
        v = SnapshotValidator()
        # Lane A artifacts present, but no normalizer_input → Lane B blocked
        doc = _base_doc(
            payload=SnapshotPayload(
                stage_artifacts=StageArtifactsLayer(
                    worker_plan="wp", worker_flow_plan="wfp",
                    worker_block_plan="wbp", worker_step_plan="wsp",
                    resources="res", symbol_table="st",
                ),
                replay_artifacts=ReplayArtifactsLayer(
                    stage10_input="s10",
                ),
            ),
        )
        result = v.validate(doc)
        assert result.effective_capabilities.has(SnapshotCapability.LANE_A_REPLAY) is True
        assert result.effective_capabilities.has(SnapshotCapability.LANE_B_REPLAY) is False
        assert any(
            f.capability == SnapshotCapability.LANE_B_REPLAY
            for f in result.capability_failures
        )

    def test_issue_extraction_without_authority_fails_capability(self) -> None:
        """Missing metadata.authority must block issue_extraction."""
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D1", kind="missing_handler",
                            severity="warning", message="test",
                            metadata={
                                "irs_ref": DiagnosticIRSRef("T", "id", "slot"),
                                "repairability": "editable",
                                "issue_group_id": "g1",
                                # authority MISSING
                            },
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        assert result.effective_capabilities.has(
            SnapshotCapability.ISSUE_EXTRACTION
        ) is False

    def test_issue_extraction_without_repairability_fails_capability(self) -> None:
        """Missing metadata.repairability must block issue_extraction."""
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D1", kind="missing_handler",
                            severity="warning", message="test",
                            metadata={
                                "irs_ref": DiagnosticIRSRef("T", "id", "slot"),
                                "authority": "post_normalize_irs",
                                "issue_group_id": "g1",
                                # repairability MISSING
                            },
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        assert result.effective_capabilities.has(
            SnapshotCapability.ISSUE_EXTRACTION
        ) is False

    def test_empty_authority_blocks_capability(self) -> None:
        """Empty string authority must block issue_extraction."""
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D1", kind="missing_handler",
                            severity="warning", message="test",
                            metadata={
                                "irs_ref": DiagnosticIRSRef("T", "id", "slot"),
                                "authority": "",
                                "repairability": "editable",
                                "issue_group_id": "g1",
                            },
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        assert result.effective_capabilities.has(
            SnapshotCapability.ISSUE_EXTRACTION
        ) is False

    def test_empty_irs_ref_values_block_capability(self) -> None:
        """irs_ref with empty construct_type must block issue_extraction."""
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D1", kind="missing_handler",
                            severity="warning", message="test",
                            metadata={
                                "irs_ref": DiagnosticIRSRef("", "id", "slot"),
                                "authority": "post_normalize_irs",
                                "repairability": "editable",
                                "issue_group_id": "g1",
                            },
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        assert result.effective_capabilities.has(
            SnapshotCapability.ISSUE_EXTRACTION
        ) is False

    def test_empty_irs_ref_slot_name_blocks_capability(self) -> None:
        """irs_ref with empty slot_name must block issue_extraction too."""
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D1", kind="missing_handler",
                            severity="warning", message="test",
                            metadata={
                                "irs_ref": DiagnosticIRSRef("T", "id", ""),
                                "authority": "post_normalize_irs",
                                "repairability": "editable",
                                "issue_group_id": "g1",
                            },
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        assert result.effective_capabilities.has(
            SnapshotCapability.ISSUE_EXTRACTION
        ) is False

    def test_hierarchical_dependency_lane_b_needs_lane_a(self) -> None:
        """Lane B depends on Lane A.  If Lane A fails, Lane B auto-fails."""
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                replay_artifacts=ReplayArtifactsLayer(
                    normalizer_input="ni",
                    normalizer_output="no",
                ),
            ),
        )
        result = v.validate(doc)
        # Lane A artifacts missing → Lane A fails
        assert result.effective_capabilities.has(SnapshotCapability.LANE_A_REPLAY) is False
        # Lane B depends_on Lane A → also fails
        assert result.effective_capabilities.has(SnapshotCapability.LANE_B_REPLAY) is False


# ===================================================================
# Diagnostic validation
# ===================================================================


class TestDiagnosticValidation:
    def test_editable_diag_with_irs_ref_passes(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D1", kind="missing_handler",
                            severity="warning", message="test",
                            metadata={
                                "irs_ref": DiagnosticIRSRef(
                                    "EXCEPTION_FLOW", "exc_1", "handler_action"
                                ),
                                "authority": "post_normalize_irs",
                                "repairability": "editable",
                                "issue_group_id": "g1",
                            },
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        # Should NOT have diagnostic-related errors
        diag_errors = [e for e in result.errors if "irs_ref" in e.lower()]
        assert len(diag_errors) == 0

    def test_editable_diag_missing_irs_ref_reported(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D2", kind="missing_handler",
                            severity="warning", message="test",
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        errors = [e for e in result.errors if "irs_ref" in e.lower()]
        assert len(errors) >= 1

    def test_irs_ref_empty_construct_type_rejected(self) -> None:
        """irs_ref with empty construct_type must fail validation."""
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D1", kind="missing_handler",
                            severity="warning", message="test",
                            metadata={
                                "irs_ref": DiagnosticIRSRef("", "id", "slot"),
                                "authority": "post_normalize_irs",
                                "repairability": "editable",
                                "issue_group_id": "g1",
                            },
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        assert any(
            "construct_type" in e and "non-empty" in e
            for e in result.errors
        )

    def test_irs_ref_empty_slot_name_rejected(self) -> None:
        """irs_ref with empty slot_name must fail validation."""
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D1", kind="missing_handler",
                            severity="warning", message="test",
                            metadata={
                                "irs_ref": DiagnosticIRSRef("T", "id", ""),
                                "authority": "post_normalize_irs",
                                "repairability": "editable",
                                "issue_group_id": "g1",
                            },
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        assert any(
            "slot_name" in e and "non-empty" in e
            for e in result.errors
        )

    def test_non_editable_diag_skips_irs_ref_check(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D3", kind="semantic_conflict",
                            severity="warning", message="test",
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        errors = [e for e in result.errors if "irs_ref" in e.lower()]
        assert len(errors) == 0


# ===================================================================
# Artifact refs
# ===================================================================


class TestArtifactRefValidation:
    def test_derived_artifact_ref_empty_derivation_rejected_by_model(self) -> None:
        """Model __post_init__ rejects empty derivation at construction time."""
        from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import DerivedArtifactRef
        from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotArtifactRefError

        with pytest.raises(SnapshotArtifactRefError, match="derivation"):
            DerivedArtifactRef(
                derived_from="payload.stage_artifacts.worker_step_plan",
                derivation="",
                artifact_hash="sha256:abc",
            )

    def test_artifact_ref_empty_ref_rejected_by_model(self) -> None:
        """Model __post_init__ rejects empty ref at construction time."""
        from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import ArtifactRef
        from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotArtifactRefError

        with pytest.raises(SnapshotArtifactRefError, match="ref"):
            ArtifactRef(ref="", artifact_hash="sha256:abc")


# ===================================================================
# Integrity hashes
# ===================================================================


class TestIntegrityHashes:
    def test_payload_hash_computation(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.validation.integrity import (
            compute_payload_hash,
        )

        doc1 = _base_doc()
        doc2 = _base_doc()
        h1 = compute_payload_hash(doc1)
        h2 = compute_payload_hash(doc2)
        assert h1 == h2, "Identical documents must have identical payload hashes"

    def test_artifact_set_hash_ignores_volatile_fields(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.validation.integrity import (
            compute_artifact_set_hash,
        )

        ident1 = new_base_identity("run-001", "snap-001", created_at="2025-01-01T00:00:00Z")
        ident2 = new_base_identity("run-001", "snap-001", created_at="2025-12-31T23:59:59Z")
        doc1 = new_base_document(ident1)
        doc2 = new_base_document(ident2)
        h1 = compute_artifact_set_hash(doc1)
        h2 = compute_artifact_set_hash(doc2)
        assert h1 == h2, "artifact_set_hash must be unchanged by created_at difference"

    def test_artifact_set_hash_changes_with_stage_artifact(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.validation.integrity import (
            compute_artifact_set_hash,
        )

        doc1 = _base_doc()
        doc2 = _base_doc(
            payload=SnapshotPayload(
                stage_artifacts=StageArtifactsLayer(worker_plan="present"),
            ),
        )
        h1 = compute_artifact_set_hash(doc1)
        h2 = compute_artifact_set_hash(doc2)
        assert h1 != h2, "artifact_set_hash must change when stage artifacts change"

    def test_artifact_content_changes_hash(self) -> None:
        """Two documents with different artifact content MUST have different hashes."""
        from nl2spl.compiler.artifacts.snapshot.validation.integrity import (
            compute_payload_hash,
        )
        from nl2spl.ir.span_ir import SpanIR

        doc1 = _base_doc(
            payload=SnapshotPayload(
                source=SourceLayer(spans=(SpanIR(span_id="s1", text="A"),)),
            ),
        )
        doc2 = _base_doc(
            payload=SnapshotPayload(
                source=SourceLayer(spans=(SpanIR(span_id="s1", text="B"),)),
            ),
        )
        h1 = compute_payload_hash(doc1)
        h2 = compute_payload_hash(doc2)
        assert h1 != h2, (
            "payload_hash must differ when serialized artifact content differs"
        )

    def test_integrity_mismatch_detected(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc(
            integrity=SnapshotIntegrity(
                payload_hash="sha256:wronghash",
                artifact_set_hash="sha256:alsowrong",
            ),
        )
        result = v.validate(doc)
        assert any("payload_hash mismatch" in e for e in result.errors)
        assert any("artifact_set_hash mismatch" in e for e in result.errors)


# ===================================================================
# Overlay document validation
# ===================================================================


class TestOverlayValidation:
    def test_valid_overlay_passes_identity_checks(self) -> None:
        v = SnapshotValidator()
        base_ident = new_base_identity("run-001", "snap-001", created_at="t")
        base_doc = new_base_document(base_ident)
        overlay_ident = new_overlay_identity(base_ident, "snap-002", created_at="t2")
        overlay_doc = new_overlay_document(overlay_ident, base_doc)
        result = v.validate(overlay_doc)
        # Overlay identity should pass (no lineage check against base_doc needed
        # for the in-memory validator since we only check basic invariants)
        # Identity validation for overlay: overlay_version > 0, parent not None
        ident_errors = [e for e in result.errors if "parent" in e.lower() or "overlay_version" in e]
        assert len(ident_errors) == 0


# ===================================================================
# Validator result structure
# ===================================================================


class TestValidatorResultStructure:
    def test_valid_result_has_no_errors(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc()
        result = v.validate(doc)
        assert result.is_valid is True
        assert result.errors == ()

    def test_invalid_result_has_errors(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc(
            payload=SnapshotPayload(
                diagnostics=DiagnosticsLayer(
                    compile_diagnostics=(
                        CompileDiagnostic(
                            diagnostic_id="D1", kind="missing_handler",
                            severity="warning", message="test",
                        ),
                    ),
                ),
            ),
        )
        result = v.validate(doc)
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_effective_capabilities_in_result(self) -> None:
        v = SnapshotValidator()
        doc = _base_doc()
        result = v.validate(doc)
        assert isinstance(result.effective_capabilities, SnapshotEffectiveCapabilities)
        assert isinstance(result.capability_failures, tuple)

    def test_capability_require_raises_on_missing(self) -> None:
        from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotCapabilityError

        caps = SnapshotEffectiveCapabilities()
        with pytest.raises(SnapshotCapabilityError):
            caps.require(SnapshotCapability.LANE_A_REPLAY)


# ===================================================================
# Boundary
# ===================================================================


class TestImportBoundary:
    def test_validator_does_not_import_spl_editing(self) -> None:
        import importlib
        import sys

        mod_path = "nl2spl.compiler.artifacts.snapshot.validation.validator"
        mod = sys.modules.get(mod_path)
        if mod is None:
            mod = importlib.import_module(mod_path)

        forbidden = (
            "nl2spl.compiler.spl_editing.patches",
            "nl2spl.compiler.spl_editing.handlers",
            "nl2spl.compiler.spl_editing.storage",
        )
        for key in dir(mod):
            obj = getattr(mod, key)
            if hasattr(obj, "__module__"):
                mod_name = getattr(obj, "__module__", "")
                for f in forbidden:
                    assert not mod_name.startswith(f)
