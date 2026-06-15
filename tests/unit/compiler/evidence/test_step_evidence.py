"""Phase U0: Unified Step Evidence Model tests.

Per implementation plan §7.5, covers:
1. source span evidence
2. valid handoff evidence
3. compiler unpack evidence
4. user-confirmed repair evidence
5. unconfirmed AI-like step without source spans → missing
6. handoff id present but invalid → does not become user-confirmed by accident
7. source span priority doesn't erase UCR metadata, but evidence kind is stable

Plus import isolation tests per §7.7 boundary requirements.
"""

from __future__ import annotations

from nl2spl.compiler.evidence import StepEvidence, StepEvidenceKind, classify_step_evidence
from nl2spl.ir.step_ir import StepIR


# =============================================================================
# Helpers
# =============================================================================


def _step(
    *,
    step_id: str = "st_1",
    command_type: str = "GENERAL_COMMAND",
    text: str = "Do something.",
    source_span_ids: tuple[str, ...] = (),
    handoff_id: str | None = None,
    origin: str | None = None,
    repair_patch_id: str | None = None,
    related_diagnostic_id: str | None = None,
    user_text: str | None = None,
) -> StepIR:
    metadata: dict[str, str] = {}
    if origin is not None:
        metadata["origin"] = origin
    if repair_patch_id is not None:
        metadata["repair_patch_id"] = repair_patch_id
    if related_diagnostic_id is not None:
        metadata["related_diagnostic_id"] = related_diagnostic_id
    if user_text is not None:
        metadata["user_text"] = user_text

    return StepIR(
        step_id=step_id,
        text=text,
        source_span_ids=list(source_span_ids),
        command_type=command_type,
        handoff_id=handoff_id,
        metadata=metadata,
    )


# =============================================================================
# 1. Source span evidence
# =============================================================================


class TestSourceSpanEvidence:
    def test_source_span_non_empty(self) -> None:
        step = _step(source_span_ids=("s1", "s2"))
        evidence = classify_step_evidence(step)
        assert evidence.primary_kind == StepEvidenceKind.SOURCE_SPAN
        assert evidence.satisfied is True
        assert evidence.has_source_span is True
        assert evidence.source_span_ids == ("s1", "s2")
        assert evidence.relation == "direct"

    def test_source_span_priority_over_ucr(self) -> None:
        """Source spans win as primary_kind but UCR metadata is preserved (multi-dimensional)."""
        step = _step(source_span_ids=("s1",), origin="user_confirmed_repair")
        evidence = classify_step_evidence(step)
        assert evidence.primary_kind == StepEvidenceKind.SOURCE_SPAN
        assert evidence.has_source_span is True
        # UCR metadata is STILL preserved as a dimensional fact
        assert evidence.has_user_confirmed_repair is True
        assert evidence.satisfied is True


# =============================================================================
# 2. Valid handoff evidence
# =============================================================================


class TestHandoffEvidence:
    def test_handoff_in_valid_ids(self) -> None:
        step = _step(handoff_id="h1")
        evidence = classify_step_evidence(step, valid_handoff_ids={"h1", "h2"})
        assert evidence.primary_kind == StepEvidenceKind.VALID_HANDOFF
        assert evidence.satisfied is True
        assert evidence.has_handoff_id is True
        assert evidence.valid_handoff is True
        assert evidence.relation == "handoff"

    def test_handoff_priority_over_ucr(self) -> None:
        """Handoff in valid IDs wins over UCR metadata."""
        step = _step(handoff_id="h1", origin="user_confirmed_repair")
        evidence = classify_step_evidence(step, valid_handoff_ids={"h1"})
        assert evidence.primary_kind == StepEvidenceKind.VALID_HANDOFF
        assert evidence.requires_handoff_authority() is True

    def test_handoff_not_in_valid_ids_with_index(self) -> None:
        """When index exists but handoff is NOT in it, fall through to UCR."""
        step = _step(handoff_id="h99", origin="user_confirmed_repair")
        evidence = classify_step_evidence(step, valid_handoff_ids={"h1", "h2"})
        # Not in index → skip handoff match → hit UCR
        assert evidence.primary_kind == StepEvidenceKind.USER_CONFIRMED_REPAIR
        assert evidence.has_handoff_id is True
        assert evidence.valid_handoff is False

    def test_handoff_no_index_allow_unknown(self) -> None:
        """Compat path: handoff present, no index (None), allow_unknown=True."""
        step = _step(handoff_id="h_any")
        evidence = classify_step_evidence(
            step,
            valid_handoff_ids=None,  # None = no index available (compat)
            allow_unknown_handoff_when_no_index=True,
        )
        assert evidence.primary_kind == StepEvidenceKind.VALID_HANDOFF
        assert evidence.satisfied is True
        assert evidence.valid_handoff is False  # not confirmed by index


# =============================================================================
# 3. Compiler unpack evidence
# =============================================================================


class TestCompilerUnpackEvidence:
    def test_compiler_unpack_origin(self) -> None:
        step = _step(origin="compiler_unpack")
        evidence = classify_step_evidence(step)
        assert evidence.primary_kind == StepEvidenceKind.COMPILER_UNPACK
        assert evidence.satisfied is True
        assert evidence.has_compiler_unpack is True
        assert evidence.relation == "generated"


# =============================================================================
# 4. User-confirmed repair evidence
# =============================================================================


class TestUserConfirmedRepairEvidence:
    def test_ucr_origin(self) -> None:
        step = _step(origin="user_confirmed_repair")
        evidence = classify_step_evidence(step)
        assert evidence.primary_kind == StepEvidenceKind.USER_CONFIRMED_REPAIR
        assert evidence.satisfied is True
        assert evidence.has_user_confirmed_repair is True
        assert evidence.is_user_confirmed() is True
        assert evidence.relation == "inferred"

    def test_ucr_with_metadata(self) -> None:
        step = _step(
            origin="user_confirmed_repair",
            repair_patch_id="patch_1",
            related_diagnostic_id="diag_abc",
            user_text="Please fix this.",
        )
        evidence = classify_step_evidence(step)
        assert evidence.repair_patch_id == "patch_1"
        assert evidence.related_diagnostic_id == "diag_abc"
        assert evidence.user_text == "Please fix this."
        assert evidence.repair_metadata_complete() is True

    def test_ucr_without_repair_metadata_not_complete(self) -> None:
        step = _step(origin="user_confirmed_repair")
        evidence = classify_step_evidence(step)
        assert evidence.is_user_confirmed() is True
        assert evidence.repair_metadata_complete() is False  # missing patch id

    def test_ucr_satisfies_source_evidence_slot(self) -> None:
        step = _step(origin="user_confirmed_repair")
        evidence = classify_step_evidence(step)
        assert evidence.satisfies_source_evidence_slot() is True

    def test_ucr_does_not_require_handoff_authority(self) -> None:
        step = _step(origin="user_confirmed_repair")
        evidence = classify_step_evidence(step)
        assert evidence.requires_handoff_authority() is False


# =============================================================================
# 5. Unconfirmed AI-like step → missing
# =============================================================================


class TestMissingEvidence:
    def test_no_source_no_handoff_no_origin(self) -> None:
        step = _step()
        evidence = classify_step_evidence(step)
        assert evidence.primary_kind == StepEvidenceKind.MISSING
        assert evidence.satisfied is False
        assert evidence.satisfies_source_evidence_slot() is False

    def test_random_origin_not_ucr(self) -> None:
        """An origin that is not in the recognized set → missing."""
        step = _step(origin="some_random_value")
        evidence = classify_step_evidence(step)
        assert evidence.primary_kind == StepEvidenceKind.MISSING

    def test_handoff_invalid_no_ucr(self) -> None:
        """Handoff present, not in index, and NO UCR → missing (no fallback)."""
        step = _step(handoff_id="h99", origin="other")
        evidence = classify_step_evidence(step, valid_handoff_ids={"h1"})
        # h99 not in valid_handoff_ids, origin is not recognized → missing
        assert evidence.primary_kind == StepEvidenceKind.MISSING
        assert evidence.satisfied is False


# =============================================================================
# 6. Semantic accessor boundary tests
# =============================================================================


class TestSemanticAccessors:
    def test_source_span_accessors(self) -> None:
        evidence = classify_step_evidence(_step(source_span_ids=("s1",)))
        assert evidence.satisfies_source_evidence_slot() is True
        assert evidence.requires_handoff_authority() is False
        assert evidence.is_user_confirmed() is False
        assert evidence.repair_metadata_complete() is False

    def test_handoff_accessors(self) -> None:
        evidence = classify_step_evidence(
            _step(handoff_id="h1"), valid_handoff_ids={"h1"}
        )
        assert evidence.satisfies_source_evidence_slot() is True
        assert evidence.requires_handoff_authority() is True
        assert evidence.is_user_confirmed() is False

    def test_missing_accessors(self) -> None:
        evidence = classify_step_evidence(_step())
        assert evidence.satisfies_source_evidence_slot() is False
        assert evidence.requires_handoff_authority() is False
        assert evidence.is_user_confirmed() is False


# =============================================================================
# Import isolation tests (per §7.7)
# =============================================================================


class TestImportIsolation:
    """``compiler.evidence`` must NOT import ``spl_editing``, LLM, handlers,
    or renderer."""

    def test_no_spl_editing_import(self) -> None:
        import nl2spl.compiler.evidence.step_evidence as mod
        import sys
        for name in sorted(mod.__dict__):
            obj = getattr(mod, name)
            if hasattr(obj, "__module__"):
                module_name = obj.__module__
                assert "spl_editing" not in module_name, (
                    f"module {mod.__name__} imports spl_editing via {name}"
                )
            elif hasattr(obj, "__name__"):
                if "spl_editing" in obj.__name__:
                    assert False, f"module {mod.__name__} references spl_editing via {name}"

    def test_no_llm_import(self) -> None:
        """Evidence predicate must not import the LLM client module."""
        import sys
        import nl2spl.compiler.evidence.step_evidence as mod
        for name in sorted(mod.__dict__):
            obj = getattr(mod, name)
            if hasattr(obj, "__module__") and "llm" in obj.__module__:
                assert False, f"module imports LLM via {name}"

    def test_no_renderer_import(self) -> None:
        """Evidence predicate must not import renderer."""
        import nl2spl.compiler.evidence.step_evidence as mod
        import sys
        for name in sorted(mod.__dict__):
            obj = getattr(mod, name)
            if hasattr(obj, "__module__") and "renderer" in obj.__module__:
                assert False, f"module imports renderer via {name}"
