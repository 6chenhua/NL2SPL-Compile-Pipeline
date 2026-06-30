"""Asynchronous issue-explanation precomputation and snapshot storage."""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nl2spl.compiler.artifacts.snapshot.hash_policy import (
    HASH_ALGORITHM,
    canonical_json_dumps,
)
from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
    JsonFileSnapshotRepository,
)
from nl2spl.compiler.spl_editing.presentation.ai_explainer import (
    IssueExplanationGenerator,
    IssueExplanationLLM,
)

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="issue-explanation-batch")
_JOBS: dict[tuple[str, str], Future[ExplanationPrecomputeResult]] = {}
_LOCK = threading.Lock()


@dataclass(frozen=True)
class ExplanationPrecomputeResult:
    snapshot_path: Path
    issue_count: int
    status: str
    cached_issue_ids: tuple[str, ...]


def schedule_issue_explanations(
    snapshot_path: Path,
    llm: IssueExplanationLLM,
    *,
    language: str = "zh-CN",
    max_workers: int = 4,
    force: bool = False,
) -> Future[ExplanationPrecomputeResult]:
    path = Path(snapshot_path).resolve()
    key = (str(path), language)
    with _LOCK:
        running = _JOBS.get(key)
        if running is not None and not running.done() and not force:
            return running
        cached = read_explanation_cache(path)
        if (
            not force
            and cached
            and cached.get("status") == "ready"
            and cached.get("language") == language
        ):
            future: Future[ExplanationPrecomputeResult] = Future()
            items = cached.get("items", {})
            ids = tuple(items) if isinstance(items, dict) else ()
            future.set_result(ExplanationPrecomputeResult(path, len(ids), "ready", ids))
            return future
        details = _issue_details(path, llm)
        _write_cache(
            path,
            {
                "schema_version": "issue_explanation_cache.v1",
                "status": "pending",
                "language": language,
                "started_at": _now(),
                "completed_at": None,
                "items": {
                    detail.issue_id: {"status": "pending", "explanation": None}
                    for detail in details
                },
            },
        )
        future = _EXECUTOR.submit(
            _generate_all, path, details, llm, language, max_workers
        )
        _JOBS[key] = future
        return future


def schedule_issue_explanations_for_pipeline(
    snapshot_path: Path,
    llm_client: Any,
    *,
    language: str = "zh-CN",
    max_workers: int = 4,
) -> Future[ExplanationPrecomputeResult]:
    from nl2spl.compiler.spl_editing.handlers.llm_adapter import LiveSuggestionLLM

    return schedule_issue_explanations(
        snapshot_path,
        LiveSuggestionLLM(llm_client),
        language=language,
        max_workers=max_workers,
    )


def read_explanation_cache(snapshot_path: Path) -> dict[str, Any] | None:
    data = JsonFileSnapshotRepository().load(Path(snapshot_path))
    presentation = data.get("presentation")
    if not isinstance(presentation, dict):
        return None
    value = presentation.get("issue_explanations")
    return value if isinstance(value, dict) else None


def read_cached_issue_explanation(
    snapshot_path: Path, issue_id: str
) -> dict[str, Any] | None:
    cache = read_explanation_cache(snapshot_path)
    items = cache.get("items") if cache else None
    item = items.get(issue_id) if isinstance(items, dict) else None
    if not isinstance(item, dict) or item.get("status") != "ready":
        return None
    value = item.get("explanation")
    return value if isinstance(value, dict) else None


def _issue_details(path: Path, llm: IssueExplanationLLM) -> tuple[Any, ...]:
    from nl2spl.compiler.spl_editing.cli import _build_default_service
    from nl2spl.compiler.spl_editing.presentation.service import (
        SPLEditingPresentationService,
    )

    service = _build_default_service(suggestion_llm=llm)
    run_id = service.register_snapshot_file(path)
    presentation = SPLEditingPresentationService(service)
    issue_list = presentation.list_issue_presentations(run_id)
    ids = tuple(
        card.issue_id
        for section in issue_list.sections
        if section.visible_by_default
        for card in section.items
    )
    return tuple(presentation.get_issue_detail_presentation(run_id, value) for value in ids)


def _generate_all(
    path: Path,
    details: tuple[Any, ...],
    llm: IssueExplanationLLM,
    language: str,
    max_workers: int,
) -> ExplanationPrecomputeResult:
    generator = IssueExplanationGenerator(llm)
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(details) or 1))) as pool:
        values = tuple(
            pool.map(lambda detail: generator.generate(detail, language=language), details)
        )
    items = {
        value.issue_id: {"status": "ready", "explanation": value.to_dict()}
        for value in values
    }
    current = read_explanation_cache(path) or {}
    _write_cache(
        path,
        {
            "schema_version": "issue_explanation_cache.v1",
            "status": "ready",
            "language": language,
            "started_at": current.get("started_at", _now()),
            "completed_at": _now(),
            "items": items,
        },
    )
    return ExplanationPrecomputeResult(path, len(items), "ready", tuple(items))


def _write_cache(path: Path, cache: dict[str, Any]) -> None:
    data = JsonFileSnapshotRepository().load(path)
    presentation = data.get("presentation")
    presentation = dict(presentation) if isinstance(presentation, dict) else {}
    presentation["issue_explanations"] = cache
    data["presentation"] = presentation
    data["integrity"] = _integrity(data)
    fd, temp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".explanation_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(canonical_json_dumps(data))
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def _integrity(data: dict[str, Any]) -> dict[str, str]:
    value = {key: item for key, item in data.items() if key != "integrity"}
    payload_hash = _hash(value)
    artifact_value = deepcopy(value)
    identity = artifact_value.get("identity")
    if isinstance(identity, dict):
        identity.pop("created_at", None)
    payload = artifact_value.get("payload")
    if isinstance(payload, dict):
        payload.pop("editing", None)
    return {"payload_hash": payload_hash, "artifact_set_hash": _hash(artifact_value)}


def _hash(value: dict[str, Any]) -> str:
    digest = hashlib.new(HASH_ALGORITHM, canonical_json_dumps(value).encode("utf-8"))
    return f"{HASH_ALGORITHM}:{digest.hexdigest()}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = [
    "ExplanationPrecomputeResult",
    "read_cached_issue_explanation",
    "read_explanation_cache",
    "schedule_issue_explanations",
    "schedule_issue_explanations_for_pipeline",
]
