"""NL2SPL main entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nl2spl.config import load_config
from nl2spl.compiler.feedback_report_renderer import render_feedback_report
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

        # Write compile report
        report_path = config.run_dir / "compile_report.txt"
        report_path.write_text(result.readable_report, encoding="utf-8")
        print(f"Compile report saved to: {report_path}", file=sys.stderr)

        # Write user-facing feedback report
        feedback_report = render_feedback_report(
            spl_text=result.spl_text,
            completeness=result.completeness,
            diagnostics=result.compile_diagnostics,
            assumptions=result.assumptions,
            traces=result.traces,
            adapter_warnings=result.adapter_warnings,
            validation_errors=result.validation_errors,
            validation_warnings=result.validation_warnings,
        )
        feedback_path = config.run_dir / "feedback_report.md"
        feedback_path.write_text(feedback_report, encoding="utf-8")
        print(f"Feedback report saved to: {feedback_path}", file=sys.stderr)

        # Compile status summary
        diag_count = len(result.compile_diagnostics)
        asm_count = len(result.assumptions)
        trace_count = len(result.traces)
        print(
            f"\nCompile status: {result.completeness}",
            file=sys.stderr,
        )
        print(
            f"  Diagnostics: {diag_count}  "
            f"Assumptions: {asm_count}  "
            f"Traces: {trace_count}  "
            f"Adapter warnings: {len(result.adapter_warnings)}",
            file=sys.stderr,
        )

        # Output diagnostics to stderr
        if result.adapter_warnings:
            print(
                f"\nAdapter ({len(result.adapter_warnings)}):",
                file=sys.stderr,
            )
            for a_warn in result.adapter_warnings:
                print(f"  - {a_warn}", file=sys.stderr)

        if result.validation_errors:
            print(f"\nErrors ({len(result.validation_errors)}):", file=sys.stderr)
            for error in result.validation_errors:
                print(f"  - {error}", file=sys.stderr)

        if result.validation_warnings:
            print(f"\nWarnings ({len(result.validation_warnings)}):", file=sys.stderr)
            for warning in result.validation_warnings:
                print(f"  - {warning}", file=sys.stderr)

        if result.compile_diagnostics:
            print(
                f"\nCompile Diagnostics ({len(result.compile_diagnostics)}):",
                file=sys.stderr,
            )
            for diag in result.compile_diagnostics:
                print(
                    f"  [{diag.kind}] {diag.message}",
                    file=sys.stderr,
                )
                if diag.suggested_resolution:
                    print(f"    => {diag.suggested_resolution}", file=sys.stderr)

        if result.traces:
            print(
                f"\nProvenance Traces ({len(result.traces)}):",
                file=sys.stderr,
            )
            for trace in result.traces:
                span_info = f" spans={trace.source_span_ids}" if trace.source_span_ids else ""
                confirm = " [needs confirmation]" if trace.needs_confirmation else ""
                print(
                    f"  [{trace.relation}] {trace.target_ref}{span_info}"
                    f"{confirm}",
                    file=sys.stderr,
                )

    except Exception as e:
        print(f"Pipeline error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
