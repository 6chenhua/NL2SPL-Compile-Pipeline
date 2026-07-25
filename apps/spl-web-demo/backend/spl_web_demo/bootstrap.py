"""Local/debug bootstrap for the framework-agnostic SPL Web Demo handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nl2spl.compiler.spl_editing.demo import _build_default_service
from spl_web_demo.card_api import SplWebDemoCardApi
from spl_web_demo.compiler import CompilerFacade, PipelineCompilerFacade
from spl_web_demo.explanation_scheduler import (
    ExplanationScheduler,
    SnapshotExplanationScheduler,
)
from spl_web_demo.store import DemoRunStore


def build_local_demo_api(
    *,
    repo_root: Path | None = None,
    store: DemoRunStore | None = None,
    suggestion_llm: Any | None = None,
    explanation_scheduler: ExplanationScheduler | None = None,
    compiler: CompilerFacade | None = None,
) -> SplWebDemoCardApi:
    """Build the debug-only service graph without coupling it to the handler."""

    editing_service = _build_default_service(
        suggestion_llm=suggestion_llm if suggestion_llm is not None else object()
    )
    resolved_scheduler = explanation_scheduler
    if resolved_scheduler is None and suggestion_llm is not None:
        resolved_scheduler = SnapshotExplanationScheduler(suggestion_llm)
    resolved_repo_root = repo_root or Path(__file__).resolve().parents[4]
    return SplWebDemoCardApi(
        editing_service=editing_service,
        store=store,
        explanation_scheduler=resolved_scheduler,
        compiler=compiler or PipelineCompilerFacade(repo_root=resolved_repo_root),
        repo_root=resolved_repo_root,
    )
