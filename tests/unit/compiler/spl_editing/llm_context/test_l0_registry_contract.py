"""Phase L0 registry contract tests."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.llm_context.registry import (
    LLMRepairContextExtensionRegistry,
)
from nl2spl.compiler.spl_editing.llm_context.section_renderer import (
    SectionRendererRegistry,
)


# ------------------------------------------------------------------
# Fake provider for testing
# ------------------------------------------------------------------


class _FakeProvider:
    provider_id = "test.exception_flow_handler"
    role = "primary"
    affordance_id = "exception_flow.add_handler_step"
    construct_type = "EXCEPTION_FLOW"
    slot_name = "handler_action"
    diagnostic_kinds = ("missing_handler",)
    supported_patch_types = ("AddExceptionHandlerStep",)
    facts_schema_id = "exception_flow.handler_action.add_exception_handler_step.v1"
    facts_schema_version = "1.0"
    facts_schema = {"type": "object"}
    renderer_id = "exception_flow_handler_section"
    required_fact_keys = ("exception_condition_text",)
    optional_fact_keys = ()

    def collect_facts(self, **kwargs):
        pass


class _FakeAuxiliaryProvider:
    provider_id = "test.producer_index_auxiliary"
    role = "auxiliary"
    affordance_id = None
    construct_type = None
    slot_name = None
    diagnostic_kinds = ("missing_output_producer",)
    supported_patch_types = ()
    facts_schema_id = "aux.producer_index.v1"
    facts_schema_version = "1.0"
    facts_schema = {"type": "object"}
    renderer_id = "producer_index_auxiliary_section"
    required_fact_keys = ()
    optional_fact_keys = ()

    def collect_facts(self, **kwargs):
        pass


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


class TestProviderRegistry:
    def test_register_and_resolve_primary_exact(self) -> None:
        reg = LLMRepairContextExtensionRegistry()
        reg.register(_FakeProvider())
        provider = reg.resolve_primary(
            affordance_id="exception_flow.add_handler_step",
            construct_type="EXCEPTION_FLOW",
            slot_name="handler_action",
            diagnostic_kind="missing_handler",
            patch_type="AddExceptionHandlerStep",
        )
        assert provider is not None
        assert provider.provider_id == "test.exception_flow_handler"

    def test_resolve_unsupported_returns_none(self) -> None:
        reg = LLMRepairContextExtensionRegistry()
        provider = reg.resolve_primary(
            affordance_id="nonexistent",
            construct_type="NONE",
            slot_name="n",
            diagnostic_kind="n",
            patch_type="n",
        )
        assert provider is None

    def test_duplicate_exact_key_same_provider_allowed(self) -> None:
        reg = LLMRepairContextExtensionRegistry()
        reg.register(_FakeProvider())
        # Same provider_id under the same key is allowed (re-registration)
        reg.register(_FakeProvider())
        assert len(reg) >= 1

    def test_different_provider_same_key_rejected(self) -> None:
        reg = LLMRepairContextExtensionRegistry()
        reg.register(_FakeProvider())
        class _Fake2(_FakeProvider):
            provider_id = "test.other"
        try:
            reg.register(_Fake2())
            assert False, "Different provider with same key should raise KeyError"
        except KeyError:
            pass

    def test_resolve_auxiliary(self) -> None:
        reg = LLMRepairContextExtensionRegistry()
        reg.register(_FakeProvider())
        reg.register(_FakeAuxiliaryProvider())
        from nl2spl.compiler.spl_editing.llm_context.model import (
            LLMRepairContextExtension,
        )
        primary_ext = LLMRepairContextExtension(
            extension_id="e1", provider_id="p1",
            role="primary",
            affordance_id="x", construct_type="x",
            slot_name="x", diagnostic_kind="missing_output_producer",
            patch_type="x",
            facts_schema_id="x", facts_schema_version="1.0",
        )
        aux = reg.resolve_auxiliary(
            primary_extension=primary_ext,
            issue=None, target=None, repair_context=None,
        )
        assert len(aux) >= 1
        assert any(
            getattr(p, "provider_id", "") == "test.producer_index_auxiliary"
            for p in aux
        )

    def test_list_provider_ids(self) -> None:
        reg = LLMRepairContextExtensionRegistry()
        reg.register(_FakeProvider())
        ids = reg.list_provider_ids()
        assert "test.exception_flow_handler" in ids


class TestSectionRendererRegistry:
    def test_register_and_get(self) -> None:
        class _FakeRenderer:
            renderer_id = "test_renderer"
            facts_schema_ids = ("schema.v1",)

            def render(self, *, extension):
                return ""

        reg = SectionRendererRegistry()
        reg.register(_FakeRenderer())
        r = reg.get(
            renderer_id="test_renderer",
            facts_schema_id="schema.v1",
            facts_schema_version="1.0",
        )
        assert r is not None

    def test_get_not_found_returns_none(self) -> None:
        reg = SectionRendererRegistry()
        r = reg.get(
            renderer_id="nonexistent",
            facts_schema_id="nonexistent",
            facts_schema_version="1.0",
        )
        assert r is None

    def test_duplicate_key_rejected(self) -> None:
        class _R:
            renderer_id = "dup"
            facts_schema_ids = ("s.v1",)
            def render(self, **kw): return ""

        reg = SectionRendererRegistry()
        reg.register(_R())
        try:
            reg.register(_R())
            assert False, "Should raise KeyError"
        except KeyError:
            pass

    def test_empty_facts_schema_ids_rejected(self) -> None:
        class _R:
            renderer_id = "no_schema"
            facts_schema_ids = ()
            def render(self, **kw): return ""

        reg = SectionRendererRegistry()
        try:
            reg.register(_R())
            assert False, "Should raise ValueError"
        except ValueError:
            pass
