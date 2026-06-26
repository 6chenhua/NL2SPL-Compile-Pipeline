"""Verification lane adapters.

Lane A replays through Stage 10 (WorkerAssembler) + Gate + Post-normalize IRS + Renderer.
Lane B replays through Stage 9.5 (IRNormalizer) + Stage 10 + Gate + Renderer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.ir.diagnostics import CompileDiagnostic, StepRenderInfo


@dataclass(frozen=True)
class VerificationArtifacts:
    """Output of a replay lane — everything needed for verification."""

    pre_gate_worker: Any | None = None
    gated_worker: Any | None = None
    render_info: tuple[StepRenderInfo, ...] = ()
    post_normalize_diagnostics: tuple[CompileDiagnostic, ...] = ()
    gate_diagnostics: tuple[CompileDiagnostic, ...] = ()
    consolidated_diagnostics: tuple[CompileDiagnostic, ...] = ()
    rendered_spl: str = ""


class LaneReplayAdapter(ABC):
    """Replay a compiler pass from a snapshot."""

    @abstractmethod
    def replay(self, snapshot: ArtifactSnapshot) -> VerificationArtifacts: ...


class LaneAReplayAdapter(LaneReplayAdapter):
    """Lane A: Stage 10 WorkerAssembler → Gate → Post-normalize IRS → Render.

    Required snapshot artifacts:
        - worker_step_plan (WorkerStepPlanIR)
        - worker_plan (WorkerPlanIR)
        - resources (ResourceRegistryIR)
        - symbol_table (SymbolTable)
        - agent_profile (AgentProfileIR) — optional, uses default if missing

    Raises ``PatchValidationError`` if required artifacts are missing.
    """

    def replay(self, snapshot: ArtifactSnapshot) -> VerificationArtifacts:
        from nl2spl.compiler.spl_editing.core.errors import PatchValidationError

        missing: list[str] = []
        if snapshot.worker_step_plan is None:
            missing.append("worker_step_plan")
        if snapshot.worker_plan is None:
            missing.append("worker_plan")
        if snapshot.resources is None:
            missing.append("resources")
        if snapshot.symbol_table is None:
            missing.append("symbol_table")
        if missing:
            raise PatchValidationError(f"Lane A replay requires artifacts: {', '.join(missing)}")
        return self._replay_real(snapshot)

    @staticmethod
    def _replay_real(snapshot: ArtifactSnapshot) -> VerificationArtifacts:
        from nl2spl.compiler.diagnostic_consolidator import (
            DiagnosticConsolidationInput,
            DiagnosticConsolidator,
        )
        from nl2spl.compiler.irs.factory import build_irs_subsystem
        from nl2spl.compiler.irs.policy import IRSRuntimeConfig
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
        from nl2spl.pipeline.executable_gate import ExecutableElementGate
        from nl2spl.pipeline.stages.stage10_worker_assembler.assembler import (
            WorkerAssembler,
        )
        from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import (
            SPLRenderer,
        )

        # 1. Stage 10: Assemble WorkerIR
        assembler = WorkerAssembler()
        pre_gate = assembler.assemble_from_worker_scoped(
            worker_step_plan=snapshot.worker_step_plan,
            resources=snapshot.resources,
            symbol_table=snapshot.symbol_table,
            worker_plan=snapshot.worker_plan,
            worker_flow_plan=snapshot.worker_flow_plan,
            worker_block_plan=snapshot.worker_block_plan,
        )

        # 2. Gate
        gate = ExecutableElementGate()
        gated, render_info_list, gate_diags = gate.apply(
            pre_gate,
            snapshot.worker_plan,
        )
        render_info = tuple(render_info_list)
        gate_diagnostics = tuple(gate_diags)

        # 3. Post-normalize IRS
        irs = build_irs_subsystem(IRSRuntimeConfig(enabled=True))
        post_diags = irs.run_post_normalize(
            gated,
            worker_plan=snapshot.worker_plan,
            symbol_table=snapshot.symbol_table,
            resources=snapshot.resources,
            worker_scoped_resources=snapshot.worker_scoped_resources,
        )
        post_diagnostics = tuple(post_diags)

        # 4. Consolidate
        consolidator = DiagnosticConsolidator()
        consolidated = consolidator.consolidate(
            DiagnosticConsolidationInput(
                post_normalize_diagnostics=list(post_diagnostics),
                gate_diagnostics=list(gate_diagnostics),
            )
        )
        consolidated_diagnostics = tuple(consolidated.final_diagnostics)

        # 5. Render SPL
        profile = snapshot.agent_profile
        if profile is None:
            profile = AgentProfileIR(
                persona=PersonaIR(role="Assistant", aspects=[]),
            )
        resources = snapshot.resources
        if resources is None:
            resources = ResourceRegistryIR()
        symbol_table = snapshot.symbol_table

        renderer = SPLRenderer()
        spl_text, _errors, _warnings = renderer.render(
            gated,
            profile,
            resources,
            symbol_table,
            list(gated.steps),
            list(snapshot.constraints),
        )

        return VerificationArtifacts(
            pre_gate_worker=pre_gate,
            gated_worker=gated,
            render_info=render_info,
            post_normalize_diagnostics=post_diagnostics,
            gate_diagnostics=gate_diagnostics,
            consolidated_diagnostics=consolidated_diagnostics,
            rendered_spl=spl_text,
        )


class LaneBReplayAdapter(LaneReplayAdapter):
    """Lane B: Stage 9.5 Normalizer → Stage 10 → Gate → Render.

    Required artifacts:
        - worker_plan (WorkerPlanIR)
        - worker_step_plan (WorkerStepPlanIR)
        - worker_flow_plan (WorkerFlowPlanIR)
        - worker_block_plan (WorkerBlockPlanIR)
        - resources (ResourceRegistryIR)
        - symbol_table (SymbolTable)

    Raises ``PatchValidationError`` if required artifacts are missing.
    """

    def replay(self, snapshot: ArtifactSnapshot) -> VerificationArtifacts:
        from nl2spl.compiler.spl_editing.core.errors import PatchValidationError

        missing: list[str] = []
        if snapshot.worker_plan is None:
            missing.append("worker_plan")
        if snapshot.worker_step_plan is None:
            missing.append("worker_step_plan")
        if snapshot.worker_flow_plan is None:
            missing.append("worker_flow_plan")
        if snapshot.worker_block_plan is None:
            missing.append("worker_block_plan")
        if snapshot.resources is None:
            missing.append("resources")
        if snapshot.symbol_table is None:
            missing.append("symbol_table")
        if missing:
            raise PatchValidationError(f"Lane B replay requires artifacts: {', '.join(missing)}")
        return self._replay_real(snapshot)

    @staticmethod
    def _replay_real(snapshot: ArtifactSnapshot) -> VerificationArtifacts:
        from nl2spl.compiler.diagnostic_consolidator import (
            DiagnosticConsolidationInput,
            DiagnosticConsolidator,
        )
        from nl2spl.compiler.irs.factory import build_irs_subsystem
        from nl2spl.compiler.irs.policy import IRSRuntimeConfig
        from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
        from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
        from nl2spl.pipeline.executable_gate import ExecutableElementGate
        from nl2spl.pipeline.stages.stage9_5_normalizer.normalizer import (
            IRNormalizer,
        )
        from nl2spl.pipeline.stages.stage10_worker_assembler.assembler import (
            WorkerAssembler,
        )
        from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import (
            SPLRenderer,
        )

        # 1. Stage 9.5: Normalize worker-scoped IRs
        normalizer = IRNormalizer()
        nf_flow, nf_block, nf_step, nf_symbols, errors, warnings = (
            normalizer.normalize_worker_scoped(
                snapshot.worker_flow_plan,
                snapshot.worker_block_plan,
                snapshot.worker_step_plan,
                snapshot.worker_plan,
                snapshot.resources,
                snapshot.symbol_table,
            )
        )
        if errors:
            from nl2spl.compiler.spl_editing.core.errors import (
                PatchValidationError,
            )

            raise PatchValidationError(
                f"Lane B normalizer returned {len(errors)} error(s): {'; '.join(errors[:3])}"
            )

        # 2. Stage 10: Assemble WorkerIR from normalized IRs
        assembler = WorkerAssembler()
        pre_gate = assembler.assemble_from_worker_scoped(
            worker_step_plan=nf_step,
            resources=snapshot.resources,
            symbol_table=nf_symbols,
            worker_plan=snapshot.worker_plan,
            worker_flow_plan=nf_flow,
            worker_block_plan=nf_block,
        )

        # 3. Gate
        gate = ExecutableElementGate()
        gated, render_info_list, gate_diags = gate.apply(
            pre_gate,
            snapshot.worker_plan,
        )
        render_info = tuple(render_info_list)
        gate_diagnostics = tuple(gate_diags)

        # 4. Post-normalize IRS
        irs = build_irs_subsystem(IRSRuntimeConfig(enabled=True))
        post_diags = irs.run_post_normalize(
            gated,
            worker_plan=snapshot.worker_plan,
            symbol_table=nf_symbols,
            resources=snapshot.resources,
            worker_scoped_resources=snapshot.worker_scoped_resources,
        )
        post_diagnostics = tuple(post_diags)

        # 5. Consolidate
        consolidator = DiagnosticConsolidator()
        consolidated = consolidator.consolidate(
            DiagnosticConsolidationInput(
                post_normalize_diagnostics=list(post_diagnostics),
                gate_diagnostics=list(gate_diagnostics),
            )
        )
        consolidated_diagnostics = tuple(consolidated.final_diagnostics)

        # 6. Render SPL
        profile = snapshot.agent_profile
        if profile is None:
            profile = AgentProfileIR(
                persona=PersonaIR(role="Assistant", aspects=[]),
            )
        resources = snapshot.resources
        if resources is None:
            resources = ResourceRegistryIR()

        renderer = SPLRenderer()
        spl_text, _r_errs, _r_warns = renderer.render(
            gated,
            profile,
            resources,
            nf_symbols,
            list(gated.steps),
            list(snapshot.constraints),
        )

        return VerificationArtifacts(
            pre_gate_worker=pre_gate,
            gated_worker=gated,
            render_info=render_info,
            post_normalize_diagnostics=post_diagnostics,
            gate_diagnostics=gate_diagnostics,
            consolidated_diagnostics=consolidated_diagnostics,
            rendered_spl=spl_text,
        )
