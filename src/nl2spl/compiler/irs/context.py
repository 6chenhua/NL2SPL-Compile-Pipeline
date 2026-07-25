"""IRS v6 Check Context — read-only input container for IRS checking.

IRSCheckContext provides a unified view of pipeline artifacts at a given stage,
allowing checkers to extract construct instances without directly coupling to
orchestrator internals.

Context is designed to be read-only. Checkers must not mutate context fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IRSCheckContext:
    """Read-only context for IRS checking at a specific pipeline stage.

    Attributes:
        stage_name: Pipeline stage identifier (e.g., "stage4", "stage7")
        spans: Source spans from NL input
        routes: Route structure IR (Stage 2)
        flow: Flow structure IR (Stage 4)
        block_plan: Block plan IR (Stage 5)
        resources: Resource registry IR (Stage 6)
        steps: Step IRs (Stage 7)
        worker_plan: Worker plan IR (Stage 8)
        worker_flows: Worker-scoped flow structures
        worker_blocks: Worker-scoped block plans
        worker_steps: Worker-scoped steps
        profile: Execution profile constraints
        constraints: Additional constraints
        normalized_ir: Post-normalization IR (Stage 9.5)
        symbol_table: Symbol table for variable resolution
        metadata: Stage-local or test-specific metadata

    Design notes:
        - frozen=True enforces read-only semantics
        - Most fields are optional to support different stages
        - Checkers must not modify context or its contained IRs
        - metadata is for test fixtures or future stage-local info
    """

    stage_name: str
    spans: tuple[Any, ...] = ()
    routes: Any | None = None
    flow: Any | None = None
    block_plan: Any | None = None
    resources: Any | None = None
    steps: tuple[Any, ...] = ()
    worker_plan: Any | None = None
    worker_flows: Any | None = None
    worker_blocks: Any | None = None
    worker_steps: Any | None = None
    profile: Any | None = None
    constraints: Any | None = None
    normalized_ir: Any | None = None
    symbol_table: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
