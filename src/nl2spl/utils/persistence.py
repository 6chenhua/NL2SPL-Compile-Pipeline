"""Intermediate result persistence for NL2SPL pipeline."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from nl2spl.utils.logger import get_stage_logger


def save_intermediate_result(
    stage_name: str,
    result: dict[str, Any],
    output_dir: Path,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Save intermediate result to JSON file.

    Args:
        stage_name: Name of the pipeline stage
        result: Result data to save
        output_dir: Output directory
        metadata: Optional metadata

    Returns:
        Path to saved file
    """
    logger = get_stage_logger("persistence")

    filename = f"{stage_name}.json"
    filepath = output_dir / filename

    output = {
        "stage": stage_name,
        "timestamp": datetime.now().isoformat(),
        "metadata": metadata or {},
        "result": result,
    }

    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Saved intermediate result: %s", filepath)
    return filepath


def load_intermediate_result(filepath: Path) -> dict[str, Any]:
    """Load intermediate result from JSON file.

    Args:
        filepath: Path to JSON file

    Returns:
        Loaded data
    """
    with open(filepath, encoding="utf-8") as f:
        result: dict[str, Any] = json.load(f)
        return result


def save_final_spl(
    spl_text: str,
    output_dir: Path,
    filename: str = "final_spl.txt",
) -> Path:
    """Save final SPL text to a plain text file.

    Args:
        spl_text: Final SPL text
        output_dir: Output directory
        filename: Final SPL filename

    Returns:
        Path to saved file
    """
    logger = get_stage_logger("persistence")

    filepath = output_dir / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(spl_text, encoding="utf-8")

    logger.info("Saved final SPL: %s", filepath)
    return filepath


def save_ir_snapshot(
    stage_name: str,
    ir_data: Any,
    output_dir: Path,
) -> Path:
    """Save IR snapshot for debugging.

    Args:
        stage_name: Name of the pipeline stage
        ir_data: IR data to save
        output_dir: Output directory

    Returns:
        Path to saved file
    """
    if hasattr(ir_data, "__dataclass_fields__"):
        data = asdict(ir_data)
    elif isinstance(ir_data, dict):
        data = ir_data
    else:
        data = {"value": str(ir_data)}

    return save_intermediate_result(stage_name, data, output_dir)
