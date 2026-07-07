from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import WorkerIR


@dataclass
class NumberingState:
    """Mutable numbering tracking for command and decision indices."""

    command_index: int = 1
    decision_index: int = 1


@dataclass(frozen=True)
class SPLRenderContext:
    symbol_table: SymbolTable | None = None
    resources: ResourceRegistryIR | None = None
    profile: AgentProfileIR | None = None
    parent_worker: WorkerIR | None = None
    numbering: NumberingState | None = None
    render_scope: Literal[
        "full_document",
        "worker",
        "block",
        "step",
        "repair_preview",
    ] = "repair_preview"
