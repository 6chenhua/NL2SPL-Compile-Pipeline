"""ARC7: Diagnostics and Report Projection.

Verifies that ARC4 typed diagnostics project correctly into CompileDiagnostic
with structured metadata, deduplication, and end-to-end visibility through
the orchestrator.
"""

from __future__ import annotations

# ===========================================================================
# Test 1: Typed diagnostic projection with structured metadata
# ===========================================================================


class TestTypedDiagnosticStructuredMetadata:
    """ARC4 typed diagnostics carry structured payload in CompileDiagnostic.metadata."""

    def test_metadata_contains_semantic_role_and_field_name(self):
        from nl2spl.compiler.annotation_role_contract.projector import (
            project_stage2_to_compile_diagnostics,
        )

        typed = [{
            "kind": "annotation_invalid_construct_target_for_role",
            "span_id": "sp_pd",
            "semantic_role": "profile_domain",
            "field_name": "construct_target",
            "expected": None,
            "actual": "RESOURCE_CONTRACT",
            "source_section_id": "sec_profile",
            "source_packet_id": "pkt_1",
            "message": "conflict",
        }]
        result = project_stage2_to_compile_diagnostics(typed)
        assert len(result) == 1
        d = result[0]

        # Structured fields in metadata
        assert d.metadata["semantic_role"] == "profile_domain"
        assert d.metadata["field_name"] == "construct_target"
        assert d.metadata["expected"] is None
        assert d.metadata["actual"] == "RESOURCE_CONTRACT"

        # Top-level provenance fields
        assert d.source_section_id == "sec_profile"
        assert d.source_packet_id == "pkt_1"
        assert d.source_span_ids == ["sp_pd"]

    def test_requiredness_metadata(self):
        from nl2spl.compiler.annotation_role_contract.projector import (
            project_stage2_to_compile_diagnostics,
        )

        typed = [{
            "kind": "annotation_missing_requiredness",
            "span_id": "sp_rc",
            "semantic_role": "input_contract",
            "field_name": "requiredness",
            "expected": "required | optional | unspecified",
            "actual": None,
            "source_section_id": None,
            "source_packet_id": None,
            "message": "missing requiredness",
        }]
        result = project_stage2_to_compile_diagnostics(typed)
        assert len(result) == 1
        d = result[0]
        assert d.metadata["semantic_role"] == "input_contract"
        assert d.metadata["field_name"] == "requiredness"
        assert d.severity == "info"


# ===========================================================================
# Test 2: Deduplication — typed wins, legacy skipped
# ===========================================================================


class TestDeduplication:
    """When both legacy string and typed diagnostics cover the same event,
    the projector keeps only the typed entry."""

    def test_legacy_skipped_when_typed_covers_same_event(self):
        from nl2spl.compiler.annotation_role_contract.projector import (
            project_stage2_to_compile_diagnostics,
        )

        # Same event described by legacy string + typed diagnostic
        mixed = [
            {  # Legacy string entry
                "span_id": "sp_rc",
                "kind": "route_refinement_diagnostic",
                "message": "Post-enrichment: span 'sp_rc' (input_contract) has no requiredness metadata",
            },
            {  # Typed entry (same event)
                "kind": "annotation_missing_requiredness",
                "span_id": "sp_rc",
                "semantic_role": "input_contract",
                "field_name": "requiredness",
                "expected": "required | optional | unspecified",
                "actual": None,
                "message": "Post-enrichment: span 'sp_rc' (input_contract) has no requiredness metadata",
            },
        ]
        result = project_stage2_to_compile_diagnostics(mixed)
        # Only the typed entry should survive
        assert len(result) == 1, (
            f"Expected 1 diagnostic after dedup, got {len(result)}"
        )
        d = result[0]
        assert "field_name" in d.metadata, "Surviving entry must be the typed diagnostic"

    def test_different_span_legacy_not_skipped(self):
        from nl2spl.compiler.annotation_role_contract.projector import (
            project_stage2_to_compile_diagnostics,
        )

        mixed = [
            {
                "span_id": "sp_other",
                "kind": "route_refinement_rejected",
                "message": "Rejected: invalid semantic_role",
            },
            {
                "kind": "annotation_missing_requiredness",
                "span_id": "sp_rc",
                "semantic_role": "input_contract",
                "field_name": "requiredness",
                "expected": "required | optional | unspecified",
                "actual": None,
                "message": "missing requiredness",
            },
        ]
        result = project_stage2_to_compile_diagnostics(mixed)
        # Both survive — different spans
        assert len(result) == 2

    def test_different_fields_not_collapsed(self):
        from nl2spl.compiler.annotation_role_contract.projector import (
            project_stage2_to_compile_diagnostics,
        )

        typed = [
            {
                "kind": "annotation_invalid_construct_target_for_role",
                "span_id": "sp_1",
                "semantic_role": "profile_domain",
                "field_name": "construct_target",
                "expected": None,
                "actual": "RESOURCE_CONTRACT",
                "message": "",
            },
            {
                "kind": "annotation_invalid_slot_target_for_role",
                "span_id": "sp_1",
                "semantic_role": "profile_domain",
                "field_name": "slot_target",
                "expected": None,
                "actual": "input",
                "message": "",
            },
        ]
        result = project_stage2_to_compile_diagnostics(typed)
        assert len(result) == 2, "Different fields must not be collapsed"

    def test_different_semantic_roles_have_unique_diagnostic_ids(self):
        """Two diagnostics for the same span + kind + field_name but
        different semantic_roles must have distinct diagnostic_ids."""
        from nl2spl.compiler.annotation_role_contract.projector import (
            project_stage2_to_compile_diagnostics,
        )

        typed = [
            {
                "kind": "annotation_invalid_construct_target_for_role",
                "span_id": "sp_1",
                "semantic_role": "profile_domain",
                "field_name": "construct_target",
                "expected": None,
                "actual": "RESOURCE_CONTRACT",
                "message": "",
            },
            {
                "kind": "annotation_invalid_construct_target_for_role",
                "span_id": "sp_1",
                "semantic_role": "constraint",
                "field_name": "construct_target",
                "expected": None,
                "actual": "RESOURCE_CONTRACT",
                "message": "",
            },
        ]
        result = project_stage2_to_compile_diagnostics(typed)
        assert len(result) == 2, "Different roles must not be collapsed"
        ids = {d.diagnostic_id for d in result}
        assert len(ids) == 2, (
            f"Different roles must have unique diagnostic_ids: {ids}"
        )


# ===========================================================================
# Test 3: E2E — profile_domain + RESOURCE_CONTRACT/input conflict visible
# ===========================================================================


class TestEndToEndProfileDomainConflict:
    """A profile_domain + RESOURCE_CONTRACT/input conflict must be visible
    in Stage 2 structured diagnostics, compile_diagnostics, and feedback."""

    def test_conflict_in_stage2_structured_diagnostics(self):
        """Build a profile_domain + RESOURCE_CONTRACT/input annotation,
        normalize it, and verify the conflict appears in Stage 2 output."""
        from nl2spl.compiler.annotation_role_contract.normalize import (
            normalize_annotation_from_role,
        )

        result = normalize_annotation_from_role(
            span_id="sp_conflict",
            semantic_role="profile_domain",
            raw_construct_target="RESOURCE_CONTRACT",
            raw_slot_target="input",
            source_section_id="sec_profile",
            source_packet_id="pkt_pd",
        )

        # Normalization corrects the fields (expected None enforced)
        assert result.annotation.construct_target is None
        assert result.annotation.slot_target is None

        # Raw values preserved in metadata for diagnostics
        raw_meta = result.annotation.metadata.get("_raw_", {})
        assert raw_meta.get("construct_target") == "RESOURCE_CONTRACT"
        assert raw_meta.get("slot_target") == "input"

    def test_conflict_projects_to_compile_diagnostic(self):
        """The conflict projects through the projector into a CompileDiagnostic
        with structured metadata."""
        from nl2spl.compiler.annotation_role_contract.diagnostics import (
            AnnotationValidationDiagnostic,
        )

        diag = AnnotationValidationDiagnostic(
            kind="annotation_invalid_construct_target_for_role",
            span_id="sp_conflict",
            semantic_role="profile_domain",
            field_name="construct_target",
            expected=None,
            actual="RESOURCE_CONTRACT",
            source_section_id="sec_profile",
            source_packet_id="pkt_pd",
            message="Rejected: profile_domain requires construct_target=None, got 'RESOURCE_CONTRACT'",
        )

        from nl2spl.compiler.annotation_role_contract.projector import (
            project_stage2_to_compile_diagnostics,
        )

        result = project_stage2_to_compile_diagnostics([diag.to_dict()])
        assert len(result) == 1
        d = result[0]

        # Structured metadata
        assert d.metadata["semantic_role"] == "profile_domain"
        assert d.metadata["field_name"] == "construct_target"
        assert d.metadata["expected"] is None
        assert d.metadata["actual"] == "RESOURCE_CONTRACT"
        assert d.source_section_id == "sec_profile"
        assert d.source_packet_id == "pkt_pd"
        assert d.severity == "warning"

    def test_conflict_survives_feedback_rendering(self):
        """The projected CompileDiagnostic is renderable through
        render_feedback_report."""
        from nl2spl.compiler.annotation_role_contract.diagnostics import (
            AnnotationValidationDiagnostic,
        )
        from nl2spl.compiler.annotation_role_contract.projector import (
            project_stage2_to_compile_diagnostics,
        )
        from nl2spl.compiler.feedback_report_renderer import render_feedback_report

        diag = AnnotationValidationDiagnostic(
            kind="annotation_invalid_construct_target_for_role",
            span_id="sp_conflict",
            semantic_role="profile_domain",
            field_name="construct_target",
            expected=None,
            actual="RESOURCE_CONTRACT",
            message="conflict",
        )

        projected = project_stage2_to_compile_diagnostics([diag.to_dict()])
        feedback = render_feedback_report(
            spl_text="// empty",
            completeness="blocked",
            diagnostics=projected,
            traces=[],
            adapter_warnings=[],
            validation_errors=[],
            validation_warnings=[],
        )

        assert "profile_domain" in feedback
        assert "construct_target" in feedback
        assert "RESOURCE_CONTRACT" in feedback

    def test_full_projection_chain_conflict_visible(self):
        """End-to-end chain: Stage 2 structured diagnostics → projector →
        consolidator → report.  profile_domain + RESOURCE_CONTRACT/input
        conflict must be visible at every step."""
        from nl2spl.compiler.annotation_role_contract.diagnostics import (
            AnnotationValidationDiagnostic,
        )
        from nl2spl.compiler.annotation_role_contract.projector import (
            project_stage2_to_compile_diagnostics,
        )
        from nl2spl.compiler.diagnostic_consolidator import (
            DiagnosticConsolidationInput,
            DiagnosticConsolidator,
        )
        from nl2spl.compiler.feedback_report_renderer import render_feedback_report

        diag = AnnotationValidationDiagnostic(
            kind="annotation_invalid_construct_target_for_role",
            span_id="sp_conflict",
            semantic_role="profile_domain",
            field_name="construct_target",
            expected=None,
            actual="RESOURCE_CONTRACT",
            source_section_id="sec_profile",
            source_packet_id="pkt_pd",
            message="Rejected: profile_domain requires construct_target=None, got 'RESOURCE_CONTRACT'",
        )
        structured = [diag.to_dict()]

        # Step 1: Project
        projected = project_stage2_to_compile_diagnostics(structured)
        assert len(projected) == 1
        assert projected[0].metadata["semantic_role"] == "profile_domain"

        # Step 2: Consolidate
        consolidation = DiagnosticConsolidator().consolidate(
            DiagnosticConsolidationInput(stage2_diagnostics=list(projected))
        )
        compile_diags = consolidation.final_diagnostics
        assert len(compile_diags) >= 1

        # Step 3: Render
        feedback = render_feedback_report(
            spl_text="// empty", completeness="blocked",
            diagnostics=list(compile_diags), traces=[],
            adapter_warnings=[], validation_errors=[], validation_warnings=[],
        )
        assert "profile_domain" in feedback

    def test_stage2_path_profile_domain_conflict_enters_structured_diagnostics(self):
        """Real Stage2 path: _execute_canonical() with LLM returning
        profile_domain + RESOURCE_CONTRACT/input.  The validator rejects
        it (construct_target/slot_target conflict), and the conflict
        appears in structured_route_diagnostics."""
        from unittest.mock import MagicMock as M

        from nl2spl.canonical.compile_input import (
            CanonicalCompileInput,
            CompileHints,
            HardFacts,
            RawSection,
            SemanticPacket,
        )
        from nl2spl.ir.span_ir import SpanIR
        from nl2spl.pipeline.stages.stage2_field_router import FieldRouter

        router = FieldRouter(config=M(), client=M())
        # Use task_family packet — NOT a hard-fact type, so it goes
        # through LLM refinement where we inject the bad response.
        section = RawSection(
            "sec_task", "task_family", "Task Family", "Profile task text.", 1,
        )
        packet = SemanticPacket(
            "p_task_0", "sec_task", "task_family",
            "Profile task text.", "hint", compile_targets=[],
        )
        span = SpanIR(
            "sp_task", text="Profile task text.",
            source_section_id="sec_task", source_packet_id="p_task_0",
        )
        canonical = CanonicalCompileInput(
            source_schema="structural_nl", schema_version="1.0",
            raw_text="Task Family:\nProfile task text.",
            raw_sections=[section],
            semantic_packets=[packet],
            compile_hints=CompileHints(), hard_facts=HardFacts(),
        )

        # Mock LLM returning profile_domain + RESOURCE_CONTRACT/input
        router.client.call_json.return_value = {
            "annotations": [{
                "span_id": "sp_task",
                "field": "domain",
                "semantic_role": "profile_domain",
                "construct_target": "RESOURCE_CONTRACT",
                "slot_target": "input",
                "executable": False,
            }],
            "split_recommendations": [],
            "diagnostics": [],
        }

        routes, _ = router._execute_canonical([span], canonical)

        # Find the conflict diagnostic in structured output
        sd = routes.structured_route_diagnostics
        construct_diags = [
            d for d in sd
            if d.get("kind") == "annotation_invalid_construct_target_for_role"
        ]
        assert len(construct_diags) >= 1, (
            f"profile_domain construct_target conflict must appear in "
            f"structured_route_diagnostics. Got kinds: {[d.get('kind') for d in sd]}"
        )
        # ARC7: typed diagnostic must carry provenance from the span
        cd = construct_diags[0]
        assert cd.get("source_section_id") == "sec_task", (
            f"Typed diagnostic must carry source_section_id from span. Got: {cd}"
        )
        assert cd.get("source_packet_id") == "p_task_0", (
            f"Typed diagnostic must carry source_packet_id from span. Got: {cd}"
        )

        # Full chain: project → consolidate → render
        from nl2spl.compiler.annotation_role_contract.projector import (
            project_stage2_to_compile_diagnostics,
        )
        from nl2spl.compiler.diagnostic_consolidator import (
            DiagnosticConsolidationInput,
            DiagnosticConsolidator,
        )
        from nl2spl.compiler.feedback_report_renderer import render_feedback_report

        projected = project_stage2_to_compile_diagnostics(sd)
        consolidation = DiagnosticConsolidator().consolidate(
            DiagnosticConsolidationInput(stage2_diagnostics=list(projected))
        )
        compile_diags = consolidation.final_diagnostics
        profile_diags = [
            d for d in compile_diags
            if "profile_domain" in d.message
        ]
        assert len(profile_diags) >= 1, (
            f"profile_domain conflict must survive consolidator. "
            f"Got: {[(d.kind, d.message[:80]) for d in compile_diags]}"
        )
        # Projected CompileDiagnostic must retain provenance
        pd = profile_diags[0]
        assert pd.source_section_id == "sec_task", (
            f"Projected diagnostic must carry source_section_id. Got: {pd.source_section_id}"
        )
        assert pd.source_packet_id == "p_task_0", (
            f"Projected diagnostic must carry source_packet_id. Got: {pd.source_packet_id}"
        )

        feedback = render_feedback_report(
            spl_text="// empty", completeness="blocked",
            diagnostics=list(compile_diags), traces=[],
            adapter_warnings=[], validation_errors=[], validation_warnings=[],
        )
        assert "profile_domain" in feedback


# ===========================================================================
# Test 4: No bare strings in output
# ===========================================================================


class TestNoBareStrings:
    """All projected diagnostics are CompileDiagnostic objects."""

    def test_all_entries_are_compilediagnostic(self):
        from nl2spl.compiler.annotation_role_contract.projector import (
            project_stage2_to_compile_diagnostics,
        )
        from nl2spl.ir.diagnostics import CompileDiagnostic

        mixed = [
            {"kind": "route_refinement_corrected", "span_id": "sp_1", "message": "x"},
            {
                "kind": "annotation_missing_requiredness",
                "span_id": "sp_2",
                "semantic_role": "input_contract",
                "field_name": "requiredness",
                "expected": "required | optional | unspecified",
                "actual": None,
                "message": "missing",
            },
        ]
        result = project_stage2_to_compile_diagnostics(mixed)
        for d in result:
            assert isinstance(d, CompileDiagnostic)


# ===========================================================================
# Test 5: Orchestrator wiring
# ===========================================================================


class TestOrchestratorWiring:
    """The orchestrator imports and uses the projector."""

    def test_projector_imported_in_orchestrator(self):
        import inspect

        from nl2spl.pipeline import orchestrator as orch

        source = inspect.getsource(orch)
        assert "project_stage2_to_compile_diagnostics" in source

    def test_stage2_diagnostics_not_hardcoded_empty(self):
        import inspect

        from nl2spl.pipeline import orchestrator as orch

        source = inspect.getsource(orch)
        assert "stage2_diagnostics=[]" not in source
