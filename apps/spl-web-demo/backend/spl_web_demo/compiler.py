"""Live pipeline adapter for the SPL Web Demo."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

from dotenv import load_dotenv


@dataclass(frozen=True)
class CompileOutcome:
    run_name: str
    pipeline_result: Any
    elapsed_seconds: float


class CompilerFacade(Protocol):
    def compile(
        self,
        raw_text: str,
        *,
        language: str,
        precompute_issue_explanations: bool,
    ) -> CompileOutcome: ...


class PipelineCompilerFacade:
    """Build one pipeline per request while keeping stages outside the API layer."""

    def __init__(
        self,
        *,
        repo_root: Path,
        output_root: Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.output_root = output_root or (
            self.repo_root / "apps" / "spl-web-demo" / ".runtime-output"
        )

    def compile(
        self,
        raw_text: str,
        *,
        language: str,
        precompute_issue_explanations: bool,
    ) -> CompileOutcome:
        from nl2spl.pipeline.orchestrator import PipelineOrchestrator

        del language  # The current pipeline detects language from source text.
        run_name = _new_run_name()
        config = build_live_pipeline_config(
            repo_root=self.repo_root,
            output_root=self.output_root,
            run_name=run_name,
            precompute_issue_explanations=precompute_issue_explanations,
        )
        started = perf_counter()
        result = PipelineOrchestrator(config).run(raw_text)
        return CompileOutcome(
            run_name=run_name,
            pipeline_result=result,
            elapsed_seconds=perf_counter() - started,
        )


def build_live_pipeline_config(
    *,
    repo_root: Path,
    output_root: Path,
    run_name: str,
    precompute_issue_explanations: bool,
) -> Any:
    from nl2spl.compiler.artifacts.snapshot.config import SnapshotPersistenceConfig
    from nl2spl.config import LLMConfig, Stage1SegmentationConfig, load_config

    load_dotenv(Path(repo_root) / ".env")
    return load_config(
        llm=LLMConfig(
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "16000")),
        ),
        log_level="INFO",
        save_intermediate=True,
        output_dir=Path(output_root),
        run_name=run_name,
        snapshot=SnapshotPersistenceConfig(
            precompute_issue_explanations=precompute_issue_explanations
        ),
        stage1=Stage1SegmentationConfig(
            mode=os.getenv("NL2SPL_STAGE1_SEGMENTATION_MODE", "legacy_packet_passthrough")
        ),
    )


def _new_run_name() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"web_demo_{timestamp}_{uuid4().hex[:8]}"


__all__ = [
    "CompileOutcome",
    "CompilerFacade",
    "PipelineCompilerFacade",
    "build_live_pipeline_config",
]
