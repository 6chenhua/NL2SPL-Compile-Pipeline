"""CLI entry point for deterministic IRS contract auditing."""

from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src").exists():
            relative = current.relative_to(parent).as_posix()
            if relative in {
                ".agents/skills/audit-irs-contract/scripts/audit_irs_contract.py",
                ".codex/skills/audit-irs-contract/scripts/audit_irs_contract.py",
            }:
                return parent
    raise RuntimeError("Could not locate repository root from audit skill path")


def _load_backend(repo_root: Path) -> Any:
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    return import_module("nl2spl.compiler.architecture_audit.irs_contract_audit")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit ConstructIRS contract and repair-runtime closure."
    )
    parser.add_argument("--construct", help="Construct type to audit; default is all")
    parser.add_argument(
        "--scope",
        choices=("registry", "runtime", "tests", "all"),
        default="all",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--waivers",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "waivers.json",
        help="Structured waiver JSON file",
    )
    parser.add_argument(
        "--no-waivers",
        action="store_true",
        help="Ignore all configured waivers",
    )
    return parser


def _render_text(report: Any) -> str:
    lines = [
        f"Verdict: {report.verdict}",
        f"Scope: {report.scope}",
        f"Construct: {report.construct or 'ALL'}",
        "",
    ]
    if not report.findings:
        lines.append("No findings.")
        return "\n".join(lines)

    for severity in ("P0", "P1", "P2"):
        selected = [item for item in report.findings if item.severity == severity]
        if not selected:
            continue
        lines.append(f"{severity} findings:")
        for finding in selected:
            lines.extend(_render_finding(finding))
        lines.append("")
    return "\n".join(lines).rstrip()


def _render_finding(finding: Any) -> list[str]:
    waiver = ""
    if finding.waived:
        waiver = f" [WAIVED until {finding.waiver_expires}]"
    lines = [
        f"- {finding.finding_id}{waiver}",
        f"  {finding.message}",
    ]
    lines.extend(f"  - {detail}" for detail in finding.details)
    if finding.waiver_reason:
        lines.append(f"  Waiver reason: {finding.waiver_reason}")
        lines.append(
            f"  Waiver owner: {finding.waiver_owner}; "
            f"issue: {finding.waiver_issue_ref}; "
            f"created: {finding.waiver_created_at}"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        repo_root = _find_repo_root()
        backend = _load_backend(repo_root)
    except (RuntimeError, ImportError) as exc:
        print(f"IRS audit configuration error: {exc}", file=sys.stderr)
        return 2
    try:
        waivers = () if args.no_waivers else backend.load_waivers(args.waivers)
    except (OSError, ValueError) as exc:
        print(f"IRS audit configuration error: {exc}", file=sys.stderr)
        return 2
    report = backend.audit_irs_contract(
        construct=args.construct,
        scope=args.scope,
        repo_root=repo_root,
        waivers=waivers,
    )
    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_render_text(report))
    return 1 if report.blocking_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
