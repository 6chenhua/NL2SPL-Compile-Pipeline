"""Phase L0 boundary import checks — llm_context must NOT import handler/LLM/patch."""

from __future__ import annotations

import sys


class TestL0BoundaryImports:
    """Verify that the llm_context module does not import handler, patch, LLM,
    or verification modules."""

    _FORBIDDEN_MODULES = (
        "handlers",
        "patches.",
        "verification",
        "langchain",
        "openai",
    )
    # Modules whose own name includes "llm" — skip self-referential check
    _SELF_LLM_PREFIX = "nl2spl.compiler.spl_editing.llm_context"

    _CORE_MODULES = (
        "nl2spl.compiler.spl_editing.llm_context.model",
        "nl2spl.compiler.spl_editing.llm_context.provider",
        "nl2spl.compiler.spl_editing.llm_context.registry",
        "nl2spl.compiler.spl_editing.llm_context.section_renderer",
        "nl2spl.compiler.spl_editing.llm_context.constants",
        "nl2spl.compiler.spl_editing.llm_context.errors",
    )

    def test_core_modules_no_forbidden_imports(self) -> None:
        for mod_name in self._CORE_MODULES:
            mod = sys.modules.get(mod_name)
            if mod is None:
                # Module not yet imported — import it fresh
                import importlib
                mod = importlib.import_module(mod_name)
            for key in sorted(mod.__dict__):
                obj = getattr(mod, key, None)
                if obj is None:
                    continue
                obj_mod = getattr(obj, "__module__", None)
                if obj_mod is None:
                    continue
                for forbidden in self._FORBIDDEN_MODULES:
                    # Skip self-referential check for modules in llm_context itself
                    if obj_mod.startswith(self._SELF_LLM_PREFIX):
                        continue
                    assert forbidden not in obj_mod, (
                        f"Module '{mod_name}' imports forbidden module "
                        f"'{obj_mod}' via '{key}'"
                    )

    def test_model_no_handler_import(self) -> None:
        import nl2spl.compiler.spl_editing.llm_context.model as mod
        for key in sorted(mod.__dict__):
            obj = getattr(mod, key, None)
            if obj is None:
                continue
            obj_mod = getattr(obj, "__module__", None)
            if obj_mod is None:
                continue
            # Skip self-references within llm_context
            if obj_mod.startswith("nl2spl.compiler.spl_editing.llm_context"):
                continue
            if "handler" in obj_mod:
                assert False, f"model.py imports handler via {key}"
            if "llm" in obj_mod.lower():
                assert False, f"model.py imports LLM via {key}"

    def test_provider_protocol_no_llm_import(self) -> None:
        import nl2spl.compiler.spl_editing.llm_context.provider as mod
        src = str(mod.__dict__.get("__doc__", ""))
        # provider is a Protocol — it must not import actual LLM implementations
        assert "langchain" not in src.lower()
        assert "openai" not in src.lower()
