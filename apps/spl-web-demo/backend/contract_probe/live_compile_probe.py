"""CLI entrypoint for the live_compile_smoke contract-probe case."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from contract_probe.live_compile_smoke import run_live_compile_smoke_case  # noqa: E402
from contract_probe.probe import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    ProbeReport,
    _make_output_dir,
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = _make_output_dir(args.output_root)
    report = ProbeReport(output_dir)
    report.record("output_dir", str(output_dir))
    try:
        status = run_live_compile_smoke_case(
            args,
            output_dir,
            report,
            repo_root=REPO_ROOT,
        )
        report.record("live_compile_smoke_status", status)
        return report.finish()
    except Exception as exc:  # noqa: BLE001 - probe captures contract failures.
        report.fail("live_compile_smoke", f"{type(exc).__name__}: {exc}")
        (output_dir / "exception.txt").write_text(traceback.format_exc(), encoding="utf-8")
        return report.finish()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the SPL Web Demo live_compile_smoke contract probe."
    )
    parser.add_argument(
        "--raw-text",
        help="Natural-language input. The checked-in smoke input is used when omitted.",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        help="File containing natural-language input for the live compile.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Root directory for timestamped probe output.",
    )
    parser.add_argument(
        "--compile-attempts",
        type=int,
        default=1,
        help="Number of real compile attempts used to calculate the smoke success rate.",
    )
    parser.add_argument(
        "--sync-budget-seconds",
        type=float,
        default=120.0,
        help="HTTP latency budget used only to recommend sync versus async transport.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
