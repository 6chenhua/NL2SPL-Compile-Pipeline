"""Framework-agnostic API handlers for the SPL Web Demo MVP."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from nl2spl.compiler.spl_editing.core.service import SPLEditingService
from nl2spl.compiler.spl_editing.interaction.model import (
    SubmitRepairDirectiveDraftRequest,
)
from nl2spl.compiler.spl_editing.presentation.explanation_cache import (
    read_cached_issue_explanation,
    read_explanation_cache,
)
from nl2spl.compiler.spl_editing.presentation.service import SPLEditingPresentationService
from nl2spl.errors import LLMError, NL2SPLError
from spl_web_demo.card_projector import CardProjector
from spl_web_demo.compiler import CompilerFacade
from spl_web_demo.document_projector import SplDocumentProjector
from spl_web_demo.explanation_scheduler import ExplanationScheduler
from spl_web_demo.provenance_projector import ProvenanceProjector
from spl_web_demo.serializers import (
    construct_card_to_api,
    construct_provenance_to_api,
    interaction_to_api,
    issue_detail_to_api,
    issue_list_to_api,
    preview_handle_to_api,
    run_view_to_api,
    span_to_api,
    spl_document_response_to_api,
    verification_to_api,
)
from spl_web_demo.store import DemoRunRecord, DemoRunStore

LOGGER = logging.getLogger(__name__)


class SplWebDemoApi:
    def __init__(
        self,
        *,
        editing_service: SPLEditingService | None = None,
        presentation_service: SPLEditingPresentationService | None = None,
        store: DemoRunStore | None = None,
        card_projector: CardProjector | None = None,
        document_projector: SplDocumentProjector | None = None,
        provenance_projector: ProvenanceProjector | None = None,
        explanation_scheduler: ExplanationScheduler | None = None,
        compiler: CompilerFacade | None = None,
        repo_root: Path | None = None,
    ) -> None:
        if editing_service is None:
            raise ValueError(
                "editing_service is required; use build_local_demo_api() for local bootstrap"
            )
        self.repo_root = repo_root or Path(__file__).resolve().parents[4]
        self.store = store if store is not None else DemoRunStore()
        self.card_projector = card_projector or CardProjector()
        self.provenance_projector = provenance_projector or ProvenanceProjector()
        self.document_projector = document_projector or SplDocumentProjector()
        self.explanation_scheduler = explanation_scheduler
        self.compiler = compiler
        self.editing = editing_service
        self.presentation = presentation_service or SPLEditingPresentationService(editing_service)

    def from_snapshot(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        raw_path = payload.get("snapshot_path")
        if not isinstance(raw_path, str) or not raw_path:
            return _error(400, "invalid_request", "snapshot_path is required")
        snapshot_path = Path(raw_path)
        if not snapshot_path.is_absolute():
            snapshot_path = self.repo_root / snapshot_path
        if not snapshot_path.exists():
            return _error(404, "snapshot_not_found", f"Snapshot not found: {raw_path}")

        return self._register_snapshot(snapshot_path)

    def create_run(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        validation_error = _validate_compile_payload(payload)
        if validation_error is not None:
            return _error(400, "invalid_request", validation_error)
        if self.compiler is None:
            return _error(503, "compile_unavailable", "live compile is unavailable")

        try:
            outcome = self.compiler.compile(
                payload["raw_text"].strip(),
                language=payload.get("language", "zh-CN"),
                precompute_issue_explanations=payload.get(
                    "precompute_issue_explanations",
                    False,
                ),
            )
        except TimeoutError:
            return _error(504, "compile_timeout", "compile timed out")
        except LLMError:
            return _error(502, "llm_backend_error", "LLM backend failed")
        except NL2SPLError:
            return _error(422, "compile_failed", "compile failed")
        except Exception:
            LOGGER.exception("Unexpected live compile failure")
            return _error(500, "internal_error", "internal server error")

        result = outcome.pipeline_result
        snapshot_status = getattr(result, "spl_editing_snapshot_status", None)
        snapshot_path = getattr(result, "spl_editing_snapshot_path", None)
        if snapshot_status == "available":
            if not snapshot_path:
                return _error(422, "compile_failed", "compile snapshot path is missing")
            path = Path(snapshot_path)
            if not path.exists():
                return _error(422, "compile_failed", "compile snapshot is missing")
            try:
                status, body = self._register_snapshot(path, pipeline_result=result)
            except (OSError, TypeError, ValueError):
                LOGGER.exception("Live compile snapshot registration failed")
                return _error(422, "compile_failed", "compile snapshot registration failed")
            body.update(
                {
                    "snapshot_path": str(path),
                    "completeness": getattr(result, "completeness", None),
                    "compile_elapsed_seconds": outcome.elapsed_seconds,
                    "spl_cards": [
                        construct_card_to_api(card)
                        for card in self.store.require(body["run_id"]).spl_cards
                    ],
                }
            )
            return status, body

        rendered_spl = getattr(result, "spl_text", None) or None
        if not rendered_spl:
            return _error(422, "compile_failed", "compile produced no usable result")
        record = DemoRunRecord(
            api_run_id=outcome.run_name,
            editing_run_id=None,
            snapshot_path=Path(snapshot_path) if snapshot_path else None,
            snapshot_id=None,
            overlay_version=0,
            revision_token=None,
            snapshot_status=snapshot_status or "unavailable",
            editing_available=False,
            rendered_spl=rendered_spl,
            pipeline_result=result,
            projection_status="projection_unavailable",
        )
        self.store.put(record)
        _, body = _run_record_to_api(record)
        body.update(
            {
                "snapshot_error": getattr(result, "spl_editing_snapshot_error", None),
                "completeness": getattr(result, "completeness", None),
                "compile_elapsed_seconds": outcome.elapsed_seconds,
                "spl_cards": [],
            }
        )
        return 200, body

    def _register_snapshot(
        self,
        snapshot_path: Path,
        *,
        pipeline_result: Any | None = None,
    ) -> tuple[int, dict[str, Any]]:
        snapshot = self.card_projector.load_snapshot_file(snapshot_path)
        base_cards = self.card_projector.project_snapshot(snapshot)
        document_read_model = self.document_projector.project_document(snapshot, base_cards)

        # Merge base cards and extra document cards, enforcing strict deduplication by construct_ref
        unique_extra = []
        base_refs = {c.construct_ref for c in base_cards}
        seen_refs = set()
        for card in document_read_model.extra_cards:
            if card.construct_ref in base_refs:
                raise ValueError(f"duplicate construct_ref: {card.construct_ref}")
            if card.construct_ref in seen_refs:
                raise ValueError(f"duplicate construct_ref: {card.construct_ref}")
            seen_refs.add(card.construct_ref)
            unique_extra.append(card)

        all_cards = tuple(base_cards) + tuple(unique_extra)
        provenance_read_model = self.provenance_projector.project_snapshot(snapshot, all_cards)
        editing_run_id = self.editing.register_snapshot_file(snapshot_path)
        run_view = self.presentation.get_run_presentation(
            editing_run_id,
            snapshot_path=snapshot_path,
        )
        revision = _revision_token_from_run_view(run_view)
        api_run_id = editing_run_id
        record = DemoRunRecord(
            api_run_id=api_run_id,
            editing_run_id=editing_run_id,
            snapshot_path=snapshot_path,
            snapshot_id=run_view.snapshot_id,
            overlay_version=run_view.overlay_version,
            revision_token=revision,
            snapshot_status="available",
            editing_available=True,
            rendered_spl=_read_initial_spl_from_snapshot_replay_artifact(snapshot_path),
            spl_cards=all_cards,
            provenance_read_model=provenance_read_model,
            pipeline_result=pipeline_result,
            projection_status="available",
            spl_document_nodes=document_read_model.nodes,
            spl_document_fidelity=document_read_model.fidelity,
        )
        self.store.put(record)
        body = run_view_to_api(
            run_view,
            api_run_id=api_run_id,
            editing_available=record.editing_available,
        )
        body["revision_token"] = revision
        body["projection_status"] = record.projection_status
        body["construct_count"] = len(record.spl_cards)
        return 200, body

    def get_spl_document(self, api_run_id: str) -> tuple[int, dict[str, Any]]:
        try:
            record = self.store.require(api_run_id)
        except KeyError:
            return _error(404, "run_not_found", "run not found")
        if record.overlay_version > 0 and record.projection_status != "available":
            return 200, {
                "run_id": record.api_run_id,
                "snapshot_id": record.snapshot_id,
                "overlay_version": record.overlay_version,
                "revision_token": record.revision_token,
                "projection_status": record.projection_status,
                "projection_fidelity": "partial",
                "nodes": [],
            }
        return 200, spl_document_response_to_api(
            run_id=record.api_run_id,
            snapshot_id=record.snapshot_id,
            overlay_version=record.overlay_version,
            revision_token=record.revision_token,
            projection_status=record.projection_status,
            projection_fidelity=record.spl_document_fidelity,
            nodes=record.spl_document_nodes,
        )

    def get_run(self, api_run_id: str) -> tuple[int, dict[str, Any]]:
        try:
            record = self.store.require(api_run_id)
        except KeyError:
            return _error(404, "run_not_found", "run not found")
        if not record.editing_run_id:
            return _run_record_to_api(record)
        run_view = self.presentation.get_run_presentation(
            record.editing_run_id,
            snapshot_path=record.snapshot_path,
        )
        body = run_view_to_api(
            run_view,
            api_run_id=record.api_run_id,
            editing_available=record.editing_available,
        )
        body["revision_token"] = record.revision_token
        body["projection_status"] = record.projection_status
        body["construct_count"] = (
            len(record.spl_cards) if record.projection_status == "available" else 0
        )
        return 200, body

    def get_spl(self, api_run_id: str) -> tuple[int, dict[str, Any]]:
        try:
            record = self.store.require(api_run_id)
        except KeyError:
            return _error(404, "run_not_found", "run not found")
        if record.overlay_version > 0 and record.projection_status != "available":
            return 200, _projection_unavailable_body(record)
        return 200, {
            "run_id": record.api_run_id,
            "snapshot_id": record.snapshot_id,
            "overlay_version": record.overlay_version,
            "revision_token": record.revision_token,
            "projection_status": record.projection_status,
            "rendered_spl": record.rendered_spl,
            "spl_cards": [construct_card_to_api(card) for card in record.spl_cards],
        }

    def list_constructs(self, api_run_id: str) -> tuple[int, dict[str, Any]]:
        try:
            record = self.store.require(api_run_id)
        except KeyError:
            return _error(404, "run_not_found", "run not found")
        if record.overlay_version > 0 and record.projection_status != "available":
            return 200, _construct_projection_unavailable_body(record)
        return 200, {
            "run_id": record.api_run_id,
            "snapshot_id": record.snapshot_id,
            "overlay_version": record.overlay_version,
            "revision_token": record.revision_token,
            "projection_status": record.projection_status,
            "constructs": [construct_card_to_api(card) for card in record.spl_cards],
        }

    def get_construct_provenance(
        self,
        api_run_id: str,
        construct_ref: str,
    ) -> tuple[int, dict[str, Any]]:
        try:
            record = self.store.require(api_run_id)
        except KeyError:
            return _error(404, "run_not_found", "run not found")
        if not any(card.construct_ref == construct_ref for card in record.spl_cards):
            return _error(404, "construct_not_found", "construct not found")
        if record.overlay_version > 0 and record.projection_status != "available":
            return 200, _provenance_projection_unavailable_body(record, construct_ref)
        read_model = record.provenance_read_model
        if read_model is None:
            return _error(422, "provenance_unavailable", "provenance is unavailable")
        provenance = read_model.get_construct(construct_ref)
        if provenance is None:
            return _error(404, "construct_not_found", "construct not found")
        return 200, {
            "run_id": record.api_run_id,
            "snapshot_id": record.snapshot_id,
            "overlay_version": record.overlay_version,
            "revision_token": record.revision_token,
            "projection_status": record.projection_status,
            "provenance": construct_provenance_to_api(provenance),
        }

    def get_span(self, api_run_id: str, span_id: str) -> tuple[int, dict[str, Any]]:
        try:
            record = self.store.require(api_run_id)
        except KeyError:
            return _error(404, "run_not_found", "run not found")
        read_model = record.provenance_read_model
        if read_model is None:
            return _error(422, "source_unavailable", "source spans are unavailable")
        span = read_model.get_span(span_id)
        if span is None:
            return _error(404, "span_not_found", "span not found")
        return 200, {
            "run_id": record.api_run_id,
            "snapshot_id": record.snapshot_id,
            "overlay_version": record.overlay_version,
            "revision_token": record.revision_token,
            "source_status": "available",
            "span": span_to_api(span),
        }

    def list_issues(self, api_run_id: str) -> tuple[int, dict[str, Any]]:
        record_or_response = self._require_editing_record(api_run_id)
        if isinstance(record_or_response, tuple):
            return record_or_response
        view = self.presentation.list_issue_presentations(
            record_or_response.require_editing_run_id()
        )
        return 200, issue_list_to_api(view)

    def get_issue(self, api_run_id: str, issue_id: str) -> tuple[int, dict[str, Any]]:
        record_or_response = self._require_editing_record(api_run_id)
        if isinstance(record_or_response, tuple):
            return record_or_response
        record = record_or_response
        try:
            detail = self.presentation.get_issue_detail_presentation(
                record.require_editing_run_id(),
                issue_id,
            )
        except StopIteration:
            return _error(404, "issue_not_found", "issue not found")
        except KeyError:
            return _error(404, "issue_not_found", "issue not found")
        explanation = self._explanation_envelope(record, issue_id)
        return 200, issue_detail_to_api(detail, explanation=explanation)

    def trigger_issue_explanation(
        self,
        api_run_id: str,
        issue_id: str,
    ) -> tuple[int, dict[str, Any]]:
        record_or_response = self._require_editing_record(api_run_id)
        if isinstance(record_or_response, tuple):
            return record_or_response
        record = record_or_response
        try:
            self.presentation.get_issue_detail_presentation(
                record.require_editing_run_id(),
                issue_id,
            )
        except (KeyError, StopIteration):
            return _error(404, "issue_not_found", "issue not found")

        current = self._explanation_envelope(record, issue_id)
        if current["status"] == "ready":
            return 200, _explanation_trigger_body(
                record,
                issue_id,
                current,
                scheduling_requested=False,
                scheduling_accepted=False,
            )
        if current["status"] == "pending":
            return 202, _explanation_trigger_body(
                record,
                issue_id,
                current,
                scheduling_requested=True,
                scheduling_accepted=False,
            )
        if record.snapshot_path is None:
            return _error(422, "explanation_unavailable", "snapshot is unavailable")
        if self.explanation_scheduler is None:
            return _error(
                503,
                "explanation_scheduler_unavailable",
                "explanation scheduling is unavailable",
            )
        try:
            self.explanation_scheduler.schedule(record.snapshot_path)
        except Exception:
            return _error(503, "explanation_schedule_failed", "explanation scheduling failed")

        refreshed = self._explanation_envelope(record, issue_id)
        status = 202 if refreshed["status"] in {"missing", "pending"} else 200
        return status, _explanation_trigger_body(
            record,
            issue_id,
            refreshed,
            scheduling_requested=True,
            scheduling_accepted=True,
        )

    def get_repair_interaction(
        self,
        api_run_id: str,
        issue_id: str,
        option_id: str,
        revision_token: str,
    ) -> tuple[int, dict[str, Any]]:
        record_or_response = self._require_editing_record(api_run_id)
        if isinstance(record_or_response, tuple):
            return record_or_response
        record = record_or_response
        try:
            view = self.presentation.get_repair_interaction(
                record.require_editing_run_id(),
                issue_id,
                option_id,
                revision_token,
            )
        except ValueError as exc:
            if str(exc) == "stale_revision":
                return _error(409, "stale_revision", "revision token is stale")
            return _error(422, "option_unavailable", str(exc))
        except KeyError:
            return _error(404, "issue_not_found", "issue or option not found")
        return 200, interaction_to_api(view)

    def submit_repair_directive(
        self,
        api_run_id: str,
        payload: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        record_or_response = self._require_editing_record(api_run_id)
        if isinstance(record_or_response, tuple):
            return record_or_response
        record = record_or_response
        validation_error = _validate_directive_payload(payload)
        if validation_error is not None:
            return _error(400, "invalid_request", validation_error)
        request = SubmitRepairDirectiveDraftRequest(
            run_id=record.require_editing_run_id(),
            issue_id=payload["issue_id"],
            strategy_id=payload["strategy_id"],
            option_id=payload["option_id"],
            contract_id=payload["contract_id"],
            contract_version=payload["contract_version"],
            revision_token=payload["revision_token"],
            field_values=dict(payload.get("field_values", {})),
            selected_ref_ids=dict(payload.get("selected_ref_ids", {})),
            new_fact_declarations=tuple(payload.get("new_fact_declarations", [])),
            additional_instruction=payload.get("additional_instruction"),
        )
        result = self.presentation.submit_repair_directive_draft(request)
        body = {
            "input_readiness": result.input_readiness,
            "directive_id": result.normalized_directive_id,
            "errors": [
                {
                    "code": error.code,
                    "field_id": error.field_id,
                    "message": error.message,
                }
                for error in result.errors
            ],
        }
        status = 200 if result.normalized_directive_id else 422
        if result.normalized_directive_id:
            self.store.bind_directive(
                result.normalized_directive_id,
                api_run_id,
                record.require_editing_run_id(),
            )
        return status, body

    def preview_repair_directive(
        self,
        api_run_id: str,
        directive_id: str,
    ) -> tuple[int, dict[str, Any]]:
        record_or_response = self._require_editing_record(api_run_id)
        if isinstance(record_or_response, tuple):
            return record_or_response
        record = record_or_response
        if not self.store.directive_belongs_to_run(
            directive_id,
            api_run_id,
            record.require_editing_run_id(),
        ):
            return _error(404, "directive_not_found", "directive not found")
        try:
            handle = self.presentation.preview_repair_directive(directive_id)
        except KeyError:
            return _error(404, "directive_not_found", "directive not found")
        preview_id = getattr(handle.preview, "preview_id", None)
        if isinstance(preview_id, str) and preview_id:
            self.store.bind_preview(preview_id, directive_id)
        return 200, preview_handle_to_api(handle)

    def apply_repair_preview(
        self,
        api_run_id: str,
        directive_id: str,
        preview_id: str,
        payload: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        record_or_response = self._require_editing_record(api_run_id)
        if isinstance(record_or_response, tuple):
            return record_or_response
        record = record_or_response
        if not self.store.directive_belongs_to_run(
            directive_id,
            api_run_id,
            record.require_editing_run_id(),
        ):
            return _error(404, "directive_not_found", "directive not found")
        if not self.store.preview_belongs_to_directive(preview_id, directive_id):
            return _error(404, "preview_not_found", "preview not found")
        if payload.get("user_confirmation") is not True:
            return _error(422, "input_required", "user_confirmation=true is required")
        try:
            session, verification = self.presentation.apply_repair_preview(directive_id, preview_id)
        except KeyError:
            return _error(404, "preview_not_found", "preview not found")
        record.overlay_version = session.overlay_version
        record.revision_token = (
            f"{record.require_editing_run_id()}:{record.snapshot_id}:{record.overlay_version}"
        )
        record.last_verification = verification
        record.projection_status = "projection_unavailable"
        body = {
            "status": "applied"
            if getattr(verification, "accepted", False)
            else "verification_failed",
            "run_id": record.api_run_id,
            "snapshot_id": record.snapshot_id,
            "overlay_version": record.overlay_version,
            "revision_token": record.revision_token,
            "verification": verification_to_api(verification),
            "projection_status": record.projection_status,
            "spl": _projection_unavailable_body(record),
            "issues": self.list_issues(api_run_id)[1],
        }
        return 200, body

    def _require_editing_record(
        self,
        api_run_id: str,
    ) -> DemoRunRecord | tuple[int, dict[str, Any]]:
        try:
            record = self.store.require(api_run_id)
        except KeyError:
            return _error(404, "run_not_found", "run not found")
        if not record.editing_run_id:
            return _error(422, "editing_unavailable", "editing is unavailable for this run")
        return record

    def _explanation_envelope(self, record: DemoRunRecord, issue_id: str) -> dict[str, Any]:
        if record.snapshot_path is None:
            return {"status": "missing", "value": None, "error": None}
        cache = read_explanation_cache(record.snapshot_path)
        value = read_cached_issue_explanation(record.snapshot_path, issue_id)
        if value is not None:
            return {"status": "ready", "value": value, "error": None}
        item = None
        if isinstance(cache, dict):
            items = cache.get("items")
            item = items.get(issue_id) if isinstance(items, dict) else None
        if isinstance(item, dict) and item.get("status") == "pending":
            return {"status": "pending", "value": None, "error": None}
        if isinstance(item, dict) and item.get("status") == "error":
            return {"status": "error", "value": None, "error": item.get("error")}
        return {"status": "missing", "value": None, "error": None}


def _explanation_trigger_body(
    record: DemoRunRecord,
    issue_id: str,
    explanation: dict[str, Any],
    *,
    scheduling_requested: bool,
    scheduling_accepted: bool,
) -> dict[str, Any]:
    return {
        "run_id": record.api_run_id,
        "snapshot_id": record.snapshot_id,
        "overlay_version": record.overlay_version,
        "revision_token": record.revision_token,
        "issue_id": issue_id,
        "explanation": explanation,
        "scheduling": {
            "requested": scheduling_requested,
            "accepted": scheduling_accepted,
        },
    }


def _run_record_to_api(record: DemoRunRecord) -> tuple[int, dict[str, Any]]:
    return 200, {
        "run_id": record.api_run_id,
        "editing_run_id": record.editing_run_id,
        "snapshot_id": record.snapshot_id,
        "snapshot_status": record.snapshot_status,
        "overlay_version": record.overlay_version,
        "revision_token": record.revision_token,
        "editing_available": record.editing_available,
        "projection_status": record.projection_status,
        "construct_count": (
            len(record.spl_cards) if record.projection_status == "available" else 0
        ),
    }


def _projection_unavailable_body(record: DemoRunRecord) -> dict[str, Any]:
    return {
        "run_id": record.api_run_id,
        "snapshot_id": record.snapshot_id,
        "overlay_version": record.overlay_version,
        "revision_token": record.revision_token,
        "projection_status": "projection_unavailable",
        "rendered_spl": None,
        "spl_cards": [],
        "message": (
            "Repair applied and verification accepted, but patched SPL projection is "
            "unavailable in this MVP build."
        ),
    }


def _validate_compile_payload(payload: dict[str, Any]) -> str | None:
    raw_text = payload.get("raw_text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        return "raw_text must be a non-empty string"
    language = payload.get("language", "zh-CN")
    if not isinstance(language, str) or not language.strip():
        return "language must be a non-empty string"
    precompute = payload.get("precompute_issue_explanations", False)
    if not isinstance(precompute, bool):
        return "precompute_issue_explanations must be a boolean"
    return None


def _construct_projection_unavailable_body(record: DemoRunRecord) -> dict[str, Any]:
    return {
        "run_id": record.api_run_id,
        "snapshot_id": record.snapshot_id,
        "overlay_version": record.overlay_version,
        "revision_token": record.revision_token,
        "projection_status": "projection_unavailable",
        "constructs": [],
        "message": (
            "Repair applied and verification accepted, but patched Construct projection "
            "is unavailable in this MVP build."
        ),
    }


def _provenance_projection_unavailable_body(
    record: DemoRunRecord,
    construct_ref: str,
) -> dict[str, Any]:
    return {
        "run_id": record.api_run_id,
        "snapshot_id": record.snapshot_id,
        "overlay_version": record.overlay_version,
        "revision_token": record.revision_token,
        "projection_status": "projection_unavailable",
        "construct_ref": construct_ref,
        "provenance": None,
        "message": (
            "Repair applied and verification accepted, but patched Construct provenance "
            "is unavailable in this MVP build."
        ),
    }


def _revision_token_from_run_view(run_view: Any) -> str:
    return f"{run_view.run_id}:{run_view.snapshot_id}:{run_view.overlay_version}"


def _read_initial_spl_from_snapshot_replay_artifact(snapshot_path: Path) -> str | None:
    """Read the canonical overlay-zero display artifact from a snapshot.

    This adapter is used only for the initial display, never after apply, and
    the returned text is not inspected to infer business state.
    """

    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload = data.get("payload")
    replay = payload.get("replay_artifacts") if isinstance(payload, dict) else None
    value = replay.get("final_spl") if isinstance(replay, dict) else None
    return value if isinstance(value, str) else None


def _validate_directive_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return "request body must be an object"
    required_strings = (
        "issue_id",
        "strategy_id",
        "option_id",
        "contract_id",
        "contract_version",
        "revision_token",
    )
    for field_name in required_strings:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            return f"{field_name} must be a non-empty string"
    if not isinstance(payload.get("field_values", {}), dict):
        return "field_values must be an object"
    if not isinstance(payload.get("selected_ref_ids", {}), dict):
        return "selected_ref_ids must be an object"
    if not isinstance(payload.get("new_fact_declarations", []), list):
        return "new_fact_declarations must be an array"
    additional_instruction = payload.get("additional_instruction")
    if additional_instruction is not None and not isinstance(additional_instruction, str):
        return "additional_instruction must be a string or null"
    return None


def _error(status: int, code: str, message: str) -> tuple[int, dict[str, Any]]:
    return status, {"error": {"code": code, "message": message, "details": {}}}
