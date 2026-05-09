"""Shared helpers for prompt debugging scripts."""

from __future__ import annotations

import difflib
import json
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nl2spl.config import load_config  # noqa: E402
from nl2spl.llm.client import LLMClient  # noqa: E402
from nl2spl.ir.symbol_table import SymbolTable  # noqa: E402


OUTPUT_DIR = REPO_ROOT / "examples" / "output" / "prompt_debug"


def make_config(stage_name: str):
    """Create config for a single prompt-debug run."""
    return load_config(
        env_file=REPO_ROOT / ".env",
        save_intermediate=False,
        output_dir=OUTPUT_DIR,
        run_name=stage_name,
    )


def make_client(config) -> LLMClient:
    """Create the real LLM client."""
    if not config.llm.api_key:
        raise RuntimeError("OPENAI_API_KEY is required. Set it in .env or the environment.")
    return LLMClient(config.llm)


def normalize(value: Any) -> Any:
    """Convert IR objects to JSON-friendly structures."""
    if isinstance(value, SymbolTable):
        return {
            name: normalize(symbol)
            for name, symbol in value.variables.items()
        }
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, tuple):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    return value


def pretty(value: Any) -> str:
    """Render JSON-friendly data with stable formatting."""
    return json.dumps(normalize(value), ensure_ascii=False, indent=2, sort_keys=True)


def print_comparison(stage_name: str, expected: Any, actual: Any) -> None:
    """Print expected, actual, and a unified diff."""
    expected_text = pretty(expected)
    actual_text = pretty(actual)

    print("=" * 80)
    print(f"{stage_name}: EXPECTED")
    print("=" * 80)
    print(expected_text)
    print("=" * 80)
    print(f"{stage_name}: ACTUAL")
    print("=" * 80)
    print(actual_text)

    if expected_text == actual_text:
        print("=" * 80)
        print(f"{stage_name}: MATCH")
        print("=" * 80)
        return

    print("=" * 80)
    print(f"{stage_name}: DIFF expected -> actual")
    print("=" * 80)
    diff = difflib.unified_diff(
        expected_text.splitlines(),
        actual_text.splitlines(),
        fromfile="expected",
        tofile="actual",
        lineterm="",
    )
    print("\n".join(diff))


def run_stage(stage_name: str, stage_factory, expected_input: Any, expected_output: Any) -> None:
    """Run one real stage and compare actual LLM output with expected output."""
    config = make_config(stage_name)
    client = make_client(config)
    stage = stage_factory(config, client)
    actual_output = stage.execute(expected_input)
    print_comparison(stage_name, expected_output, actual_output)
