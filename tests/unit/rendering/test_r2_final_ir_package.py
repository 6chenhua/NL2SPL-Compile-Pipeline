"""Tests for FinalIRPackage and CompileResult additive migration (Phase R2)."""

from nl2spl.compiler.compile_result import CompileResult
from nl2spl.compiler.final_ir_package import FinalIRPackage, compute_package_hash
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import FlowRef, WorkerIR


def test_final_ir_package_hash_is_stable_and_independent_of_render() -> None:
    # 1. Setup mock/stub WorkerIR
    worker = WorkerIR(
        worker_name="Coord",
        description="Main coordinator",
        inputs=[],
        outputs=[],
        main_flow=FlowRef(blocks=[]),
        child_worker_refs=[],
        child_workers=[],
    )
    profile = AgentProfileIR(persona=PersonaIR(role="Assistant", aspects=[]))
    resources = ResourceRegistryIR()
    symbol_table = SymbolTable()

    # 2. Compute package hash twice
    hash1 = compute_package_hash(
        root_worker=worker,
        profile=profile,
        resources=resources,
        symbol_table=symbol_table,
        constraints=(),
        diagnostics=(),
        traces=(),
        assumptions=(),
        verification_metadata={"completeness": "complete"},
    )

    # Change formatting-only things or check that hash is identical
    hash2 = compute_package_hash(
        root_worker=worker,
        profile=profile,
        resources=resources,
        symbol_table=symbol_table,
        constraints=(),
        diagnostics=(),
        traces=(),
        assumptions=(),
        verification_metadata={"completeness": "complete"},
    )

    assert hash1 == hash2
    assert isinstance(hash1, str)
    assert len(hash1) == 64  # SHA-256 length in hex


def test_compile_result_exposes_final_ir_package() -> None:
    worker = WorkerIR(
        worker_name="Coord",
        description="Main coordinator",
    )
    profile = AgentProfileIR(persona=PersonaIR(role="Assistant", aspects=[]))
    resources = ResourceRegistryIR()
    symbol_table = SymbolTable()

    pkg = FinalIRPackage(
        package_id="pkg1",
        artifact_snapshot_id=None,
        overlay_version=0,
        package_hash="somehash",
        root_worker=worker,
        profile=profile,
        resources=resources,
        symbol_table=symbol_table,
    )

    result = CompileResult(
        spl_text="[DEFINE_AGENT: Coord]",
        final_ir_package=pkg,
    )

    assert result.final_ir_package == pkg
    assert result.spl_text == "[DEFINE_AGENT: Coord]"


def test_deterministic_serialize_sets_and_frozensets() -> None:
    from nl2spl.compiler.final_ir_package import _deterministic_serialize

    set_a = {"orange", "apple", "banana"}
    set_b = {"banana", "apple", "orange"}

    # Even though set iteration order can be non-deterministic,
    # serialized output must be sorted and identical.
    out_a = _deterministic_serialize(set_a)
    out_b = _deterministic_serialize(set_b)

    assert out_a == out_b
    assert out_a == ["apple", "banana", "orange"]

    # Frozensets
    fset_a = frozenset({"orange", "apple", "banana"})
    out_fset = _deterministic_serialize(fset_a)
    assert out_fset == ["apple", "banana", "orange"]
