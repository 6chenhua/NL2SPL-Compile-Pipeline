from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "apps" / "spl-web-demo" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from spl_web_demo.app import create_app  # noqa: E402
from spl_web_demo.bootstrap import build_local_demo_api  # noqa: E402
from spl_web_demo.compiler import CompileOutcome  # noqa: E402

from nl2spl.errors import LLMError  # noqa: E402

SNAPSHOT = REPO_ROOT / "examples" / "output" / "demo" / "spl_editing_snapshot.json"


class FakeCompiler:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def compile(
        self,
        raw_text: str,
        *,
        language: str,
        precompute_issue_explanations: bool,
    ) -> CompileOutcome:
        self.calls.append(
            {
                "raw_text": raw_text,
                "language": language,
                "precompute_issue_explanations": precompute_issue_explanations,
            }
        )
        return CompileOutcome(
            run_name="web_demo_test",
            pipeline_result=self.result,
            elapsed_seconds=12.5,
        )


class FailingCompiler:
    def compile(self, *_args, **_kwargs) -> CompileOutcome:
        raise LLMError("provider unavailable")


def _pipeline_result(
    *,
    snapshot_status: str = "available",
    snapshot_path: Path | None = SNAPSHOT,
    spl_text: str = "[DEFINE_AGENT: Demo]",
) -> SimpleNamespace:
    return SimpleNamespace(
        spl_editing_snapshot_status=snapshot_status,
        spl_editing_snapshot_path=snapshot_path,
        spl_editing_snapshot_error=(
            None if snapshot_status == "available" else "snapshot persistence failed"
        ),
        spl_text=spl_text,
        completeness="partial",
    )


def test_live_compile_registers_snapshot_and_public_read_models() -> None:
    compiler = FakeCompiler(_pipeline_result())
    api = build_local_demo_api(repo_root=REPO_ROOT, compiler=compiler)

    status, created = api.create_run(
        {
            "raw_text": "  Create a source-backed workflow.  ",
            "language": "en-US",
            "precompute_issue_explanations": False,
        }
    )

    assert status == 200
    assert compiler.calls == [
        {
            "raw_text": "Create a source-backed workflow.",
            "language": "en-US",
            "precompute_issue_explanations": False,
        }
    ]
    assert created["run_id"] == "demo"
    assert created["snapshot_status"] == "available"
    assert created["editing_available"] is True
    assert created["projection_status"] == "available"
    assert created["compile_elapsed_seconds"] == 12.5
    assert created["spl_cards"]

    assert api.get_spl(created["run_id"])[1]["rendered_spl"]
    assert api.list_constructs(created["run_id"])[1]["constructs"]
    assert api.list_issues(created["run_id"])[0] == 200


def test_live_compile_snapshot_half_success_disables_editing() -> None:
    compiler = FakeCompiler(
        _pipeline_result(
            snapshot_status="failed_best_effort",
            snapshot_path=None,
        )
    )
    api = build_local_demo_api(repo_root=REPO_ROOT, compiler=compiler)

    status, created = api.create_run({"raw_text": "Create a workflow."})

    assert status == 200
    assert created["run_id"] == "web_demo_test"
    assert created["snapshot_status"] == "failed_best_effort"
    assert created["editing_available"] is False
    assert created["projection_status"] == "projection_unavailable"
    assert created["snapshot_error"] == "snapshot persistence failed"

    spl_status, spl = api.get_spl(created["run_id"])
    assert spl_status == 200
    assert spl["rendered_spl"] == "[DEFINE_AGENT: Demo]"
    assert spl["spl_cards"] == []
    issue_status, issue_error = api.list_issues(created["run_id"])
    assert issue_status == 422
    assert issue_error["error"]["code"] == "editing_unavailable"


def test_live_compile_without_usable_result_returns_compile_failed() -> None:
    compiler = FakeCompiler(
        _pipeline_result(
            snapshot_status="failed_required",
            snapshot_path=None,
            spl_text="",
        )
    )
    api = build_local_demo_api(repo_root=REPO_ROOT, compiler=compiler)

    status, body = api.create_run({"raw_text": "Create a workflow."})

    assert status == 422
    assert body["error"]["code"] == "compile_failed"


def test_live_compile_rejects_available_snapshot_without_path() -> None:
    compiler = FakeCompiler(
        _pipeline_result(
            snapshot_status="available",
            snapshot_path=None,
        )
    )
    api = build_local_demo_api(repo_root=REPO_ROOT, compiler=compiler)

    status, body = api.create_run({"raw_text": "Create a workflow."})

    assert status == 422
    assert body["error"]["code"] == "compile_failed"


def test_live_compile_maps_llm_failure_and_validates_payload() -> None:
    api = build_local_demo_api(repo_root=REPO_ROOT, compiler=FailingCompiler())

    status, body = api.create_run({"raw_text": "Create a workflow."})
    assert status == 502
    assert body["error"]["code"] == "llm_backend_error"

    status, body = api.create_run(
        {
            "raw_text": "Create a workflow.",
            "precompute_issue_explanations": "false",
        }
    )
    assert status == 400
    assert body["error"]["code"] == "invalid_request"


def test_live_compile_http_route_uses_injected_compiler() -> None:
    compiler = FakeCompiler(_pipeline_result())
    api = build_local_demo_api(repo_root=REPO_ROOT, compiler=compiler)
    client = TestClient(create_app(api))

    response = client.post(
        "/api/demo/v1/runs",
        json={
            "raw_text": "Create a source-backed workflow.",
            "language": "en-US",
            "precompute_issue_explanations": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["run_id"] == "demo"
    assert response.json()["spl_cards"]
