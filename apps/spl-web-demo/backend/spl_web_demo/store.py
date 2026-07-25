"""In-memory run store for the SPL Web Demo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spl_web_demo.card_projector import SplConstructCard
from spl_web_demo.document_projector import SplDocumentNode
from spl_web_demo.provenance_projector import ProvenanceReadModel


@dataclass
class DemoRunRecord:
    api_run_id: str
    editing_run_id: str | None
    snapshot_path: Path | None
    snapshot_id: str | None
    overlay_version: int
    revision_token: str | None
    snapshot_status: str
    editing_available: bool
    rendered_spl: str | None = None
    spl_cards: tuple[SplConstructCard, ...] = ()
    provenance_read_model: ProvenanceReadModel | None = None
    pipeline_result: Any | None = None
    last_verification: Any | None = None
    projection_status: str = "available"
    spl_document_nodes: tuple[SplDocumentNode, ...] = ()
    spl_document_fidelity: str = "structured"

    def require_editing_run_id(self) -> str:
        if not self.editing_run_id:
            raise RuntimeError("editing_run_id is unavailable")
        return self.editing_run_id


class DemoRunStore:
    def __init__(self) -> None:
        self._records: dict[str, DemoRunRecord] = {}
        self._directive_owners: dict[str, tuple[str, str]] = {}
        self._preview_directive_ids: dict[str, str] = {}

    def put(self, record: DemoRunRecord) -> None:
        self._records[record.api_run_id] = record

    def get(self, api_run_id: str) -> DemoRunRecord | None:
        return self._records.get(api_run_id)

    def require(self, api_run_id: str) -> DemoRunRecord:
        record = self.get(api_run_id)
        if record is None:
            raise KeyError(api_run_id)
        return record

    def bind_directive(
        self,
        directive_id: str,
        api_run_id: str,
        editing_run_id: str,
    ) -> None:
        self._directive_owners[directive_id] = (api_run_id, editing_run_id)

    def directive_belongs_to_run(
        self,
        directive_id: str,
        api_run_id: str,
        editing_run_id: str,
    ) -> bool:
        return self._directive_owners.get(directive_id) == (
            api_run_id,
            editing_run_id,
        )

    def bind_preview(self, preview_id: str, directive_id: str) -> None:
        self._preview_directive_ids[preview_id] = directive_id

    def preview_belongs_to_directive(self, preview_id: str, directive_id: str) -> bool:
        return self._preview_directive_ids.get(preview_id) == directive_id
