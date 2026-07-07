"""Tests for Phase R1 Stage 11 compatibility wrapper."""

from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import FlowRef, WorkerIR
from nl2spl.rendering import RenderedDocument, render_full_spl_from_legacy_inputs


def test_r1_compat_wrapper_behaves_identically_to_renderer() -> None:
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

    # 2. Render via the new wrapper
    res = render_full_spl_from_legacy_inputs(
        worker=worker,
        profile=profile,
        resources=resources,
        symbol_table=symbol_table,
        steps=[],
        constraints=[],
    )

    # 3. Assert on output structure
    assert isinstance(res, RenderedDocument)
    assert res.renderer_id == "stage11_compat"
    assert res.format == "spl_text"
    assert "[DEFINE_AGENT: Coord" in res.text
    assert "[DEFINE_PERSONA:]" in res.text
