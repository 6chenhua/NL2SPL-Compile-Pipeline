"""FastAPI route adapters for the SPL Web Demo MVP."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from spl_web_demo.card_api import SplWebDemoCardApi

API_PREFIX = "/api/demo/v1"


def build_demo_router(api: SplWebDemoCardApi) -> APIRouter:
    """Bind the framework-agnostic handler contract to HTTP routes."""

    router = APIRouter(prefix=API_PREFIX)

    @router.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "spl-web-demo",
            "editing_service": "ready",
        }

    @router.post("/runs/from-snapshot")
    def create_run_from_snapshot(
        payload: Annotated[dict[str, Any], Body()],
    ) -> JSONResponse:
        return _to_json_response(api.from_snapshot(payload))

    @router.post("/runs")
    def create_run(
        payload: Annotated[dict[str, Any], Body()],
    ) -> JSONResponse:
        return _to_json_response(api.create_run(payload))

    @router.get("/runs/{run_id}")
    def get_run(run_id: str) -> JSONResponse:
        return _to_json_response(api.get_run(run_id))

    @router.get("/runs/{run_id}/spl")
    def get_spl(run_id: str) -> JSONResponse:
        return _to_json_response(api.get_spl(run_id))

    @router.get("/runs/{run_id}/spl-document")
    def get_spl_document(run_id: str) -> JSONResponse:
        return _to_json_response(api.get_spl_document(run_id))

    @router.get("/runs/{run_id}/constructs")
    def list_constructs(run_id: str) -> JSONResponse:
        return _to_json_response(api.list_constructs(run_id))

    @router.get("/runs/{run_id}/constructs/{construct_ref}/provenance")
    def get_construct_provenance(run_id: str, construct_ref: str) -> JSONResponse:
        return _to_json_response(api.get_construct_provenance(run_id, construct_ref))

    @router.get("/runs/{run_id}/spans/{span_id}")
    def get_span(run_id: str, span_id: str) -> JSONResponse:
        return _to_json_response(api.get_span(run_id, span_id))

    @router.get("/runs/{run_id}/issues")
    def list_issues(run_id: str) -> JSONResponse:
        return _to_json_response(api.list_issues(run_id))

    @router.get("/runs/{run_id}/issues/{issue_id}")
    def get_issue(run_id: str, issue_id: str) -> JSONResponse:
        return _to_json_response(api.get_issue(run_id, issue_id))

    @router.post("/runs/{run_id}/issues/{issue_id}/explanation")
    def trigger_issue_explanation(run_id: str, issue_id: str) -> JSONResponse:
        return _to_json_response(api.trigger_issue_explanation(run_id, issue_id))

    @router.get("/runs/{run_id}/issues/{issue_id}/repair-options/{option_id}/interaction")
    def get_repair_interaction(
        run_id: str,
        issue_id: str,
        option_id: str,
        revision_token: Annotated[str, Query(min_length=1)],
    ) -> JSONResponse:
        return _to_json_response(
            api.get_repair_interaction(
                run_id,
                issue_id,
                option_id,
                revision_token,
            )
        )

    @router.post("/runs/{run_id}/repair-directives")
    def submit_repair_directive(
        run_id: str,
        payload: Annotated[dict[str, Any], Body()],
    ) -> JSONResponse:
        return _to_json_response(api.submit_repair_directive(run_id, payload))

    @router.post("/runs/{run_id}/repair-directives/{directive_id}/preview")
    def preview_repair_directive(run_id: str, directive_id: str) -> JSONResponse:
        return _to_json_response(api.preview_repair_directive(run_id, directive_id))

    @router.post("/runs/{run_id}/repair-directives/{directive_id}/previews/{preview_id}/apply")
    def apply_repair_preview(
        run_id: str,
        directive_id: str,
        preview_id: str,
        payload: Annotated[dict[str, Any], Body()],
    ) -> JSONResponse:
        return _to_json_response(
            api.apply_repair_preview(
                run_id,
                directive_id,
                preview_id,
                payload,
            )
        )

    return router


def _to_json_response(result: tuple[int, dict[str, Any]]) -> JSONResponse:
    status_code, body = result
    return JSONResponse(status_code=status_code, content=body)
