from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src" / "nl2spl" / "compiler"
SHIM_ALLOWLIST = {
    "construct_registry.py",
    "diagnostic_registry.py",
    "diagnostic_consolidator.py",
    "irs/graph.py",
    "irs/frontier.py",
    "irs/patch_type_meta.py",
    "irs/feedback_projector.py",
    "irs/audit.py",
    "irs_prompt_builder.py",
    "report_renderer.py",
}
PUBLIC_API_ALLOWLIST = {
    "__init__.py",
}


def _imports(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _python_files(package: str) -> list[Path]:
    root = SRC / package
    if not root.exists():
        return []
    return sorted(root.rglob("*.py"))


def _relative(path: Path) -> str:
    return path.relative_to(SRC).as_posix()


def _is_shim(path: Path) -> bool:
    return _relative(path) in SHIM_ALLOWLIST


def test_constructs_package_has_no_forbidden_imports() -> None:
    violations: list[str] = []
    for path in _python_files("constructs"):
        imports = _imports(path)
        forbidden = [
            name for name in imports
            if name.startswith("nl2spl.compiler.irs")
            or name.startswith("nl2spl.compiler.spl_editing")
            or name.startswith("nl2spl.pipeline")
            or name.startswith("nl2spl.compiler.reporting")
            or name.startswith("nl2spl.compiler.construct_plan")
        ]
        if forbidden:
            violations.append(f"{_relative(path)}: {forbidden}")
    assert violations == []


def test_repair_contracts_package_has_no_runtime_imports() -> None:
    violations: list[str] = []
    for path in _python_files("repair_contracts"):
        imports = _imports(path)
        forbidden = [
            name for name in imports
            if name.startswith("nl2spl.compiler.irs")
            or name.startswith("nl2spl.compiler.spl_editing")
            or name.startswith("nl2spl.pipeline")
        ]
        if forbidden:
            violations.append(f"{_relative(path)}: {forbidden}")
    assert violations == []


def test_diagnostics_package_has_no_irs_imports() -> None:
    violations: list[str] = []
    for path in _python_files("diagnostics"):
        imports = _imports(path)
        forbidden = [
            name for name in imports
            if name.startswith("nl2spl.compiler.irs")
        ]
        if forbidden:
            violations.append(f"{_relative(path)}: {forbidden}")
    assert violations == []


def test_construct_plan_no_longer_imports_irs_graph() -> None:
    violations: list[str] = []
    for path in _python_files("construct_plan"):
        imports = _imports(path)
        if "nl2spl.compiler.irs.graph" in imports:
            violations.append(_relative(path))
    assert violations == []


def test_reporting_no_longer_imports_irs_feedback_projector() -> None:
    violations: list[str] = []
    for path in _python_files("reporting"):
        imports = _imports(path)
        if "nl2spl.compiler.irs.feedback_projector" in imports:
            violations.append(_relative(path))
    assert violations == []


def test_irs_runtime_does_not_import_reporting_or_spl_editing() -> None:
    violations: list[str] = []
    for path in _python_files("irs"):
        if _is_shim(path):
            continue
        imports = _imports(path)
        forbidden = [
            name for name in imports
            if name.startswith("nl2spl.compiler.reporting")
            or name.startswith("nl2spl.compiler.spl_editing")
        ]
        if forbidden:
            violations.append(f"{_relative(path)}: {forbidden}")
    assert violations == []


def test_production_code_uses_new_import_paths_except_shims_and_public_api() -> None:
    legacy_imports = {
        "nl2spl.compiler.construct_registry",
        "nl2spl.compiler.diagnostic_registry",
        "nl2spl.compiler.diagnostic_consolidator",
        "nl2spl.compiler.report_renderer",
        "nl2spl.compiler.irs_prompt_builder",
        "nl2spl.compiler.irs.graph",
        "nl2spl.compiler.irs.frontier",
        "nl2spl.compiler.irs.patch_type_meta",
        "nl2spl.compiler.irs.feedback_projector",
        "nl2spl.compiler.irs.audit",
    }
    violations: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        rel = _relative(path)
        if _is_shim(path) or rel in PUBLIC_API_ALLOWLIST:
            continue
        imports = _imports(path)
        bad = sorted(imports & legacy_imports)
        if bad:
            violations.append(f"{rel}: {bad}")
    assert violations == []
