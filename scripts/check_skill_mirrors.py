"""Check or synchronize repository skill mirrors."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

IGNORED_DIRS = {"__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _files(root: Path) -> dict[Path, str]:
    if not root.exists():
        return {}
    result: dict[Path, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        if path.suffix in IGNORED_SUFFIXES:
            continue
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _skills(canonical_root: Path, requested: tuple[str, ...]) -> tuple[str, ...]:
    if requested:
        return tuple(sorted(set(requested)))
    return tuple(sorted(path.name for path in canonical_root.iterdir() if path.is_dir()))


def _sync_skill(source: Path, target: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Canonical skill does not exist: {source}")
    target.mkdir(parents=True, exist_ok=True)
    source_files = _files(source)
    target_files = _files(target)

    for relative in sorted(target_files.keys() - source_files.keys()):
        stale = (target / relative).resolve()
        if target.resolve() not in stale.parents:
            raise RuntimeError(f"Refusing to remove path outside mirror: {stale}")
        stale.unlink()

    for relative in sorted(source_files):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or source_files[relative] != _files(target).get(relative):
            shutil.copy2(source / relative, destination)

    directories = sorted(
        (path for path in target.rglob("*") if path.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for directory in directories:
        if not any(directory.iterdir()):
            directory.rmdir()


def _differences(source: Path, target: Path) -> list[str]:
    source_files = _files(source)
    target_files = _files(target)
    differences: list[str] = []
    for relative in sorted(source_files.keys() | target_files.keys()):
        if relative not in source_files:
            differences.append(f"extra in mirror: {relative}")
        elif relative not in target_files:
            differences.append(f"missing from mirror: {relative}")
        elif source_files[relative] != target_files[relative]:
            differences.append(f"content differs: {relative}")
    return differences


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--skill", action="append", default=[])
    args = parser.parse_args()

    root = _repo_root()
    canonical_root = root / ".agents" / "skills"
    mirror_root = root / ".codex" / "skills"
    names = _skills(canonical_root, tuple(args.skill))

    failed = False
    for name in names:
        source = canonical_root / name
        target = mirror_root / name
        if args.sync:
            _sync_skill(source, target)
        differences = _differences(source, target)
        if differences:
            failed = True
            print(f"{name}: mirror mismatch")
            for difference in differences:
                print(f"  - {difference}")
        else:
            print(f"{name}: mirror matches")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
