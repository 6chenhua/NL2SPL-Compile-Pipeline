"""In-memory store for PreviewMaterializationResult instances."""

from __future__ import annotations

import copy
import time
from typing import Any, Dict

from nl2spl.compiler.spl_editing.preview.model import PreviewMaterializationResult


class PreviewStoreError(ValueError):
    """Exception raised by PreviewStore for validation or lookup failures."""
    pass


class PreviewStore:
    """In-memory store for managing SPL Editing preview results.

    Supports put, get, validate_applicable, and manual/TTL-based expiration.
    Guarantees validation of session, issue, and base snapshot IDs, and
    prevents mutation pollution through deepcopy.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    def put(
        self,
        session_id: str,
        issue_id: str,
        base_snapshot_id: str,
        preview: PreviewMaterializationResult,
        ttl_seconds: float | None = None,
    ) -> None:
        """Store a preview result with associated session, issue, base snapshot IDs and TTL."""
        if not session_id or not session_id.strip():
            raise PreviewStoreError("session_id must not be empty.")
        if not issue_id or not issue_id.strip():
            raise PreviewStoreError("issue_id must not be empty.")
        if not base_snapshot_id or not base_snapshot_id.strip():
            raise PreviewStoreError("base_snapshot_id must not be empty.")
        if not preview or not isinstance(preview, PreviewMaterializationResult):
            raise TypeError("preview must be a PreviewMaterializationResult instance.")
        if preview.base_snapshot_id != base_snapshot_id:
            raise PreviewStoreError(
                f"Snapshot mismatch: preview base_snapshot_id '{preview.base_snapshot_id}' "
                f"does not match scope base_snapshot_id '{base_snapshot_id}'."
            )

        # Deep copy to prevent caller mutation from affecting stored state
        preview_copy = copy.deepcopy(preview)

        self._store[preview.preview_id] = {
            "preview": preview_copy,
            "session_id": session_id,
            "issue_id": issue_id,
            "base_snapshot_id": base_snapshot_id,
            "created_at": time.time(),
            "ttl": ttl_seconds,
            "expired": False,
        }

    def get(self, preview_id: str) -> PreviewMaterializationResult:
        """Retrieve a stored preview. Raises PreviewStoreError if not found or expired."""
        record = self._get_record(preview_id)
        return copy.deepcopy(record["preview"])

    def expire(self, preview_id: str) -> None:
        """Manually mark a preview as expired."""
        if preview_id in self._store:
            self._store[preview_id]["expired"] = True

    def validate_applicable(
        self,
        preview_id: str,
        session_id: str,
        issue_id: str,
        base_snapshot_id: str,
    ) -> bool:
        """Validate if the preview is applicable. Raises PreviewStoreError if validation fails."""
        record = self._get_record(preview_id)

        if record["session_id"] != session_id:
            raise PreviewStoreError(
                f"Session mismatch: preview has '{record['session_id']}', got '{session_id}'"
            )
        if record["issue_id"] != issue_id:
            raise PreviewStoreError(
                f"Issue mismatch: preview has '{record['issue_id']}', got '{issue_id}'"
            )
        if record["base_snapshot_id"] != base_snapshot_id:
            raise PreviewStoreError(
                f"Snapshot mismatch: preview has '{record['base_snapshot_id']}', got '{base_snapshot_id}'"
            )

        return True

    def _get_record(self, preview_id: str) -> Dict[str, Any]:
        if preview_id not in self._store:
            raise PreviewStoreError(f"Preview '{preview_id}' not found.")

        record = self._store[preview_id]
        if record["ttl"] is not None:
            elapsed = time.time() - record["created_at"]
            if elapsed > record["ttl"]:
                record["expired"] = True
                raise PreviewStoreError(f"Preview '{preview_id}' has expired (TTL exceeded).")

        if record["expired"]:
            raise PreviewStoreError(f"Preview '{preview_id}' has been expired.")

        return record
