"""Exception-flow facts exposed to drafting providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ExceptionFlowTargetViewSource(Protocol):
    target_ref: str
    worker_id: str
    canonical_name: str


class ExceptionFlowContextViewSource(Protocol):
    metadata: dict


@dataclass(frozen=True)
class ExceptionFlowDraftingView:
    target_ref: str
    worker_id: str | None
    flow_id: str | None
    condition_text: str | None = None

    @classmethod
    def from_target_and_context(
        cls,
        target: ExceptionFlowTargetViewSource,
        context: ExceptionFlowContextViewSource | None,
    ) -> ExceptionFlowDraftingView:
        metadata = context.metadata if context is not None else {}
        return cls(
            target_ref=target.target_ref,
            worker_id=target.worker_id,
            flow_id=target.canonical_name,
            condition_text=metadata.get("condition_text"),
        )
