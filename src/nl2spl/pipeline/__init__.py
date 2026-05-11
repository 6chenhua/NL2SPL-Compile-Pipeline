"""Pipeline module."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nl2spl.pipeline.orchestrator import PipelineOrchestrator, PipelineResult

__all__ = ["PipelineOrchestrator", "PipelineResult"]


def __getattr__(name: str) -> object:
    """Load orchestrator exports lazily so helper modules can import standalone."""
    if name in __all__:
        from nl2spl.pipeline.orchestrator import PipelineOrchestrator, PipelineResult

        exports = {
            "PipelineOrchestrator": PipelineOrchestrator,
            "PipelineResult": PipelineResult,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
