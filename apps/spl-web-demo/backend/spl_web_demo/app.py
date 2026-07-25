"""FastAPI application factory for the SPL Web Demo."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from spl_web_demo.bootstrap import build_local_demo_api
from spl_web_demo.card_api import SplWebDemoCardApi
from spl_web_demo.routes import build_demo_router


def create_app(api: SplWebDemoCardApi | None = None) -> FastAPI:
    """Create the local/demo HTTP application around an injected handler graph."""

    resolved_api = api if api is not None else build_local_demo_api()
    application = FastAPI(
        title="SPL Web Demo API",
        version="0.1.0",
        docs_url="/api/demo/docs",
        redoc_url=None,
        openapi_url="/api/demo/openapi.json",
    )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        _request: Request,
        _exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "request validation failed",
                    "details": {},
                }
            },
        )

    application.state.demo_api = resolved_api
    application.include_router(build_demo_router(resolved_api))
    return application


app = create_app()
