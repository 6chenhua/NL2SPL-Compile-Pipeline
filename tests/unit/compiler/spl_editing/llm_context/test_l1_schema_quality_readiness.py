"""Phase L1 tests — schema validation, quality, readiness."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.llm_context.schema import validate_facts, check_renderer_compatibility
from nl2spl.compiler.spl_editing.llm_context.quality import evaluate_quality
from nl2spl.compiler.spl_editing.llm_context.readiness import evaluate_readiness
from nl2spl.compiler.spl_editing.llm_context.errors import SchemaValidationError


class TestSchemaValidation:
    def test_required_keys_present_passes(self) -> None:
        missing = validate_facts(
            facts={"a": 1, "b": 2},
            required_keys=("a",),
            optional_keys=("b",),
            facts_schema_id="test.v1",
        )
        assert missing == []

    def test_missing_required_key_detected(self) -> None:
        missing = validate_facts(
            facts={"b": 2},
            required_keys=("a",),
            optional_keys=("b",),
            facts_schema_id="test.v1",
        )
        assert "a" in missing

    def test_unknown_key_rejected(self) -> None:
        try:
            validate_facts(
                facts={"a": 1, "unknown": 99},
                required_keys=("a",),
                optional_keys=(),
                facts_schema_id="test.v1",
                allow_unknown=False,
            )
            assert False, "Should raise"
        except SchemaValidationError:
            pass

    def test_allow_unknown(self) -> None:
        missing = validate_facts(
            facts={"a": 1, "unknown": 99},
            required_keys=("a",),
            optional_keys=(),
            facts_schema_id="test.v1",
            allow_unknown=True,
        )
        assert missing == []

    def test_empty_value_treated_as_missing(self) -> None:
        missing = validate_facts(
            facts={"a": ""},
            required_keys=("a",),
            optional_keys=(),
            facts_schema_id="test.v1",
        )
        assert "a" in missing

    def test_renderer_compatibility_match(self) -> None:
        ok = check_renderer_compatibility(
            facts_schema_id="s.v1",
            facts_schema_version="1.0",
            renderer_schema_ids=("s.v1", "s.v2"),
            renderer_supported_versions=("1.0", "2.0"),
        )
        assert ok is True

    def test_renderer_compatibility_mismatch(self) -> None:
        ok = check_renderer_compatibility(
            facts_schema_id="s.v3",
            facts_schema_version="1.0",
            renderer_schema_ids=("s.v1", "s.v2"),
        )
        assert ok is False


class TestQuality:
    def test_all_facts_high_confidence(self) -> None:
        q = evaluate_quality(
            has_primary_business_fact=True,
            has_source_excerpt=True,
            has_workflow_context=True,
        )
        assert q.confidence == "high"

    def test_one_fact_medium_confidence(self) -> None:
        q = evaluate_quality(has_primary_business_fact=True)
        assert q.confidence == "medium"

    def test_no_facts_low_confidence(self) -> None:
        q = evaluate_quality()
        assert q.confidence == "low"


class TestReadiness:
    def test_repair_unavailable(self) -> None:
        r = evaluate_readiness(repair_available=False)
        assert r.status == "repair_unavailable"

    def test_generation_blocked_missing_facts(self) -> None:
        r = evaluate_readiness(
            repair_available=True,
            required_facts_missing=("child_worker_id",),
        )
        assert r.status == "generation_blocked"

    def test_ready(self) -> None:
        r = evaluate_readiness(repair_available=True)
        assert r.status == "ready"

    def test_low_confidence_from_quality(self) -> None:
        from nl2spl.compiler.spl_editing.llm_context.model import ContextQuality
        q = ContextQuality(confidence="low", missing_context_fields=("source_excerpt",))
        r = evaluate_readiness(repair_available=True, quality=q)
        assert r.status == "ready_low_confidence"
