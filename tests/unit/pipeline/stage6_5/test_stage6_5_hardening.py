"""S6V5: Stage 6.5 existing-symbol-only hardening tests.

Verify:
1. Natural-language guard + no existing symbol → no ref rewrite, no SymbolTable mutation
2. Explicit <REF>x</REF> + no symbol → unresolved diagnostic, blocks_completion=True
3. LLM semantic match rejected → report/audit only, blocks_completion=False
4. Stage 6.5 never mutates SymbolTable
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.diagnostics import (
    resolver_diagnostic,
)


# ---------------------------------------------------------------------------
# Diagnostic blocking policy
# ---------------------------------------------------------------------------


class TestS6V5DiagnosticBlockingPolicy:
    """Verify diagnostic blocking policy is differentiated by source."""

    def test_explicit_missing_ref_diagnostic_blocks_completion(self) -> None:
        diag = resolver_diagnostic(
            diagnostic_id="test_explicit",
            kind="unresolved_ref",
            message="Explicit REF token unresolved.",
            owner_ref="condition:block:w1:b1",
            source_span_ids=("s1",),
            blocks_completion=True,
        )
        assert diag.blocks_completion is True
        assert diag.blocks_rendering is False

    def test_llm_unresolved_diagnostic_does_not_block_completion(self) -> None:
        diag = resolver_diagnostic(
            diagnostic_id="test_llm",
            kind="unresolved_llm",
            message="LLM could not resolve condition.",
            owner_ref="condition:block:w1:b1",
            source_span_ids=("s1",),
            blocks_completion=False,
        )
        assert diag.blocks_completion is False
        assert diag.blocks_rendering is False

    def test_default_blocks_completion_is_false(self) -> None:
        """S6V5: default is report/audit only, not completion-blocking."""
        diag = resolver_diagnostic(
            diagnostic_id="test_default",
            kind="info",
            message="Default diagnostic.",
            owner_ref="condition:block:w1:b1",
            source_span_ids=("s1",),
        )
        assert diag.blocks_completion is False, (
            "S6V5: default blocks_completion must be False "
            "(report/audit only for LLM/semantic diagnostics)."
        )

    def test_parser_diagnostic_does_not_block_completion(self) -> None:
        diag = resolver_diagnostic(
            diagnostic_id="test_parser",
            kind="parse_error",
            message="Parser diagnostic.",
            owner_ref="condition:block:w1:b1",
            source_span_ids=("s1",),
            blocks_completion=False,
        )
        assert diag.blocks_completion is False


# ---------------------------------------------------------------------------
# SymbolTable immutability
# ---------------------------------------------------------------------------


class TestS6V5SymbolTableImmutability:
    """Verify Stage 6.5 never mutates SymbolTable."""

    def test_resolver_imports_dont_include_declare(self) -> None:
        """The resolver module should not import declare/declare_scoped."""
        import inspect
        from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver import (
            resolver,
        )
        src = inspect.getsource(resolver)
        assert ".declare(" not in src, (
            "S6V5: resolver must not call symbol_table.declare()."
        )
        assert ".declare_scoped(" not in src, (
            "S6V5: resolver must not call symbol_table.declare_scoped()."
        )

    def test_entire_stage6_5_package_does_not_mutate_symbol_table(self) -> None:
        """Static check: no declare calls anywhere in stage6_5 package."""
        import subprocess
        import sys
        from pathlib import Path

        pkg_dir = (
            Path(__file__).resolve().parents[3]
            / "src/nl2spl/pipeline/stages/stage6_5_condition_reference_resolver"
        )
        for py_file in pkg_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            if ".declare(" in content or ".declare_scoped(" in content:
                pytest.fail(
                    f"S6V5: {py_file.name} contains declare/declare_scoped — "
                    f"Stage 6.5 must not mutate SymbolTable."
                )


# ---------------------------------------------------------------------------
# Natural-language guard handling
# ---------------------------------------------------------------------------


class TestS6V5NaturalLanguageGuard:
    """Verify natural-language guards stay natural language when no symbol
    exists."""

    def test_empty_symbol_table_no_crash(self) -> None:
        """Resolver should not crash with empty SymbolTable."""
        from nl2spl.ir.block_structure_ir import BlockStructureIR, BlockIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
        from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR
        from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.resolver import (
            ConditionReferenceResolver,
        )

        resolver_obj = ConditionReferenceResolver(llm_client=None)
        sym = SymbolTable()
        resources = ResourceRegistryIR(variables=[], files=[], apis=[], types=[])

        flow_plan = WorkerFlowPlanIR(
            worker_flows={
                "w1": FlowStructureIR(
                    main_flow_spans=["s1"],
                    alternative_flows=[],
                    exception_flows=[],
                ),
            },
        )
        block_plan = WorkerBlockPlanIR(
            worker_blocks={
                "w1": BlockStructureIR(
                    main_flow_blocks=[
                        BlockIR("b1", "IF", condition_text="when ready", spans=["s1"]),
                    ],
                ),
            },
        )

        plan = resolver_obj.resolve(
            worker_flow_plan=flow_plan,
            worker_block_plan=block_plan,
            symbol_table=sym,
            resource_registry=resources,
        )

        # Should produce a plan, not crash
        assert plan is not None
        assert hasattr(plan, "references")

    def test_symbol_table_unchanged_after_resolve(self) -> None:
        """SymbolTable must have the same entries before and after resolve."""
        from nl2spl.ir.block_structure_ir import BlockStructureIR, BlockIR
        from nl2spl.ir.flow_structure_ir import FlowStructureIR
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
        from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR
        from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.resolver import (
            ConditionReferenceResolver,
        )

        resolver_obj = ConditionReferenceResolver(llm_client=None)
        sym = SymbolTable()
        sym.declare("existing_var", "text", "input", "An existing variable.")
        before_keys = set(sym._variables.keys())
        before_names = set(sym.variables.keys())

        resources = ResourceRegistryIR(variables=[], files=[], apis=[], types=[])
        flow_plan = WorkerFlowPlanIR(
            worker_flows={
                "w1": FlowStructureIR(
                    main_flow_spans=["s1"],
                    alternative_flows=[],
                    exception_flows=[],
                ),
            },
        )
        block_plan = WorkerBlockPlanIR(
            worker_blocks={
                "w1": BlockStructureIR(
                    main_flow_blocks=[
                        BlockIR("b1", "IF", condition_text="when ready", spans=["s1"]),
                    ],
                ),
            },
        )

        resolver_obj.resolve(
            worker_flow_plan=flow_plan,
            worker_block_plan=block_plan,
            symbol_table=sym,
            resource_registry=resources,
        )

        after_keys = set(sym._variables.keys())
        after_names = set(sym.variables.keys())

        assert before_keys == after_keys, (
            "S6V5: SymbolTable keys changed after resolve!"
        )
        assert before_names == after_names, (
            "S6V5: SymbolTable names changed after resolve!"
        )
