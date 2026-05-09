"""Configuration management for NL2SPL pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


@dataclass
class LLMConfig:
    """LLM configuration."""

    model: str = "gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.0
    api_key: str | None = None
    base_url: str | None = None

    def __post_init__(self) -> None:
        """Load from environment if not set."""
        if self.api_key is None:
            self.api_key = os.getenv("OPENAI_API_KEY")
        if self.base_url is None:
            self.base_url = os.getenv("OPENAI_BASE_URL")


@dataclass
class PipelineConfig:
    """Pipeline configuration."""

    # LLM settings
    llm: LLMConfig = field(default_factory=LLMConfig)

    # Output settings
    output_dir: Path = Path("output")
    run_name: str | None = None
    final_spl_filename: str = "final_spl.txt"
    run_dir: Path = field(init=False)
    save_intermediate: bool = True
    trace_dir: Path | None = None

    # Logging settings
    log_level: str = "INFO"
    log_file: Path | None = None

    # Validation settings
    validate_spl: bool = True
    strict_mode: bool = False

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0

    def __post_init__(self) -> None:
        """Ensure directories exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if self.run_name is None:
            base_run_name = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.run_name = base_run_name
            suffix = 2
            while (self.output_dir / self.run_name).exists():
                self.run_name = f"{base_run_name}_{suffix}"
                suffix += 1

        run_name_path = Path(self.run_name)
        if run_name_path.is_absolute() or ".." in run_name_path.parts:
            raise ValueError("run_name must be a relative directory name inside output_dir")

        self.run_dir = self.output_dir / run_name_path
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.trace_dir:
            self.trace_dir.mkdir(parents=True, exist_ok=True)


def load_config(
    env_file: Path | None = None,
    **kwargs: Any,
) -> PipelineConfig:
    """Load configuration from environment and overrides.

    Args:
        env_file: Path to .env file
        **kwargs: Override values for PipelineConfig fields

    Returns:
        PipelineConfig instance
    """
    if env_file and env_file.exists():
        load_dotenv(env_file)

    return PipelineConfig(**kwargs)
