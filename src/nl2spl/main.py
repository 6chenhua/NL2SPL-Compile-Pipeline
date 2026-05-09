"""NL2SPL main entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nl2spl.config import load_config
from nl2spl.pipeline.orchestrator import PipelineOrchestrator


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Convert natural language text to SPL.")
    parser.add_argument(
        "input_file",
        nargs="?",
        help="Input text file. Reads stdin when omitted.",
    )
    parser.add_argument(
        "--input",
        dest="input_option",
        help="Input text file. Kept for compatibility with documented usage.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Root directory for run output.",
    )
    parser.add_argument(
        "--run-name",
        help="Run directory name under output-dir.",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point for NL2SPL pipeline."""
    args = parse_args()

    # Load configuration
    config = load_config(
        env_file=Path(".env"),
        log_level="INFO",
        output_dir=args.output_dir,
        run_name=args.run_name,
    )

    # Create orchestrator
    orchestrator = PipelineOrchestrator(config)

    # Read input from stdin or file
    input_arg = args.input_option or args.input_file
    if input_arg:
        input_file = Path(input_arg)
        if not input_file.exists():
            print(f"Error: File not found: {input_file}", file=sys.stderr)
            sys.exit(1)
        raw_text = input_file.read_text(encoding="utf-8")
    else:
        print("Reading from stdin (Ctrl+D to end):", file=sys.stderr)
        raw_text = sys.stdin.read()

    # Run pipeline
    try:
        result = orchestrator.run(raw_text)

        # Output SPL
        print(result.spl_text)
        if result.final_spl_path:
            print(f"Final SPL saved to: {result.final_spl_path}", file=sys.stderr)

        # Output diagnostics to stderr
        if result.validation_errors:
            print(f"\nErrors ({len(result.validation_errors)}):", file=sys.stderr)
            for error in result.validation_errors:
                print(f"  - {error}", file=sys.stderr)

        if result.validation_warnings:
            print(f"\nWarnings ({len(result.validation_warnings)}):", file=sys.stderr)
            for warning in result.validation_warnings:
                print(f"  - {warning}", file=sys.stderr)

    except Exception as e:
        print(f"Pipeline error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
