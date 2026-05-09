"""Unit tests for pipeline configuration."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nl2spl.config import LLMConfig, PipelineConfig


def test_default_run_name_creates_timestamped_run_dir(tmp_path: Path) -> None:
    """Default run_name creates a timestamped run directory under output_dir."""
    config = PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=tmp_path / "output",
    )

    assert config.run_name is not None
    assert re.fullmatch(r"run_\d{8}_\d{6}", config.run_name)
    assert config.run_dir == config.output_dir / config.run_name
    assert config.run_dir.exists()


def test_custom_run_name_creates_named_run_dir(tmp_path: Path) -> None:
    """Custom run_name is used as the run directory name."""
    config = PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=tmp_path / "output",
        run_name="example",
    )

    assert config.run_dir == tmp_path / "output" / "example"
    assert config.run_dir.exists()


def test_default_run_name_avoids_existing_run_dir(tmp_path: Path) -> None:
    """Default run_name adds a suffix when the timestamp directory already exists."""
    output_dir = tmp_path / "output"
    first = PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=output_dir,
    )
    second = PipelineConfig(
        llm=LLMConfig(api_key="test-key"),
        output_dir=output_dir,
    )

    assert second.run_name != first.run_name
    assert second.run_dir.exists()


def test_run_name_must_stay_inside_output_dir(tmp_path: Path) -> None:
    """run_name cannot escape output_dir."""
    with pytest.raises(ValueError, match="run_name"):
        PipelineConfig(
            llm=LLMConfig(api_key="test-key"),
            output_dir=tmp_path / "output",
            run_name="../outside",
        )
