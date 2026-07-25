"""Source excerpt resolver from snapshot spans."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import EditableIssue, UserFacingIssue
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot


def source_excerpt_for_issue(
    issue: EditableIssue | UserFacingIssue,
    snapshot: ArtifactSnapshot,
    related_diagnostics: tuple[object, ...] = (),
    *,
    max_chars: int = 280,
) -> str | None:
    span_ids = list(issue.source_span_ids)
    for diagnostic in related_diagnostics:
        span_ids.extend(getattr(diagnostic, "source_span_ids", []) or [])
    seen: set[str] = set()
    texts: list[str] = []
    for span_id in span_ids:
        if span_id in seen:
            continue
        seen.add(span_id)
        text = _span_text(snapshot, span_id)
        if text:
            texts.append(text)
    if not texts:
        return None
    joined = " ".join(texts)
    return joined if len(joined) <= max_chars else joined[: max_chars - 3] + "..."


def _span_text(snapshot: ArtifactSnapshot, span_id: str) -> str | None:
    for span in snapshot.spans:
        if getattr(span, "span_id", None) == span_id:
            text = getattr(span, "text", None)
            return text if isinstance(text, str) and text.strip() else None
    base_span_id = _route_annotation_base_span_id(span_id)
    if base_span_id is not None:
        for span in snapshot.spans:
            if getattr(span, "span_id", None) == base_span_id:
                text = getattr(span, "text", None)
                return text if isinstance(text, str) and text.strip() else None
    return None


def _route_annotation_base_span_id(span_id: str) -> str | None:
    if len(span_id) < 3 or not span_id.startswith("s"):
        return None
    suffix = span_id[-1]
    candidate = span_id[:-1]
    if suffix.isalpha() and candidate[1:].isdigit():
        return candidate
    return None


__all__ = ["source_excerpt_for_issue"]
