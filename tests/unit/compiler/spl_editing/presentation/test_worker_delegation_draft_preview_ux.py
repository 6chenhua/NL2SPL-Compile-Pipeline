from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

from nl2spl.compiler.spl_editing.demo import _build_default_service
from nl2spl.compiler.spl_editing.drafting.model import (
    UserRepairFieldValue,
    UserRepairInput,
)
from nl2spl.compiler.spl_editing.drafting.values import (
    BusinessLogicValue,
    NewOutputDraftValue,
    ResponsibilityValue,
    SelectedInputRefsValue,
)
from nl2spl.compiler.spl_editing.presentation.service import SPLEditingPresentationService
from tests.spl_editing_stub_llm import StubSuggestionLLM

SNAPSHOT = Path("examples/output/demo/spl_editing_snapshot.json")
RUN_DEMO = Path("examples/output/spl_editing_demo/run_demo.py")


def _runtime():
    editing = _build_default_service(suggestion_llm=StubSuggestionLLM())
    run_id = editing.register_snapshot_file(SNAPSHOT)
    editing._snapshot_repository = None
    presentation = SPLEditingPresentationService(editing)
    snapshot = editing._get_snapshot(run_id)
    revision = f"{snapshot.compile_run_id}:{snapshot.snapshot_id}:{snapshot.overlay_version}"
    issue = next(
        item
        for item in editing.list_issue_inventory(run_id).editable
        if item.irs_ref.construct_type == "WORKER_PROMOTION"
    )
    return editing, presentation, run_id, issue, revision


def _create_draft():
    _editing, presentation, run_id, issue, revision = _runtime()
    creation = presentation.create_repair_draft(
        run_id=run_id,
        issue_id=issue.issue_id,
        option_id="define_child_worker",
        revision_token=revision,
        user_input=UserRepairInput(
            input_mode="free_text",
            free_text="Gather approved source evidence",
            selected_option_id="define_child_worker",
        ),
    )
    return presentation, run_id, issue, revision, creation


def _run_demo_module():
    spec = importlib.util.spec_from_file_location("spl_editing_demo_run_demo", RUN_DEMO)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    previous = os.environ.get("SPL_EDITING_DEMO_BOOTSTRAPPED")
    os.environ["SPL_EDITING_DEMO_BOOTSTRAPPED"] = "1"
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            os.environ.pop("SPL_EDITING_DEMO_BOOTSTRAPPED", None)
        else:
            os.environ["SPL_EDITING_DEMO_BOOTSTRAPPED"] = previous
    return module


def test_multiline_prompt_text_is_sanitized_and_wrapped() -> None:
    module = _run_demo_module()

    text = module._sanitize_prompt_text(
        "Task summary\nwith multiple lines\nand a very long tail " * 8,
        width=80,
    )

    assert "\n" not in text
    assert len(text) <= 80
    assert text.endswith("...")


def test_draft_preview_default_is_user_readable_without_internal_ids() -> None:
    _presentation, _run_id, _issue, _revision, creation = _create_draft()

    rendered = "\n".join(
        [
            creation.draft_preview.title,
            creation.draft_preview.summary,
            *creation.draft_preview.field_summaries,
        ]
    )

    assert "Create child worker" in rendered
    assert "Input variables:" in rendered
    assert "Returned result:" in rendered
    assert "Business logic:" in rendered
    assert "Insert:" in rendered
    assert "Result handling:" in rendered
    assert "parent-local temporary" not in rendered
    assert "del s31" not in rendered
    assert "ref:" not in rendered
    assert "worker_input:" not in rendered
    assert "handoff_" not in rendered
    assert "step_id" not in rendered
    assert "block_id" not in rendered


def test_enter_accept_path_does_not_require_technical_fields() -> None:
    presentation, run_id, issue, revision, creation = _create_draft()

    field_ids = {field.field_id for field in creation.draft.fields}
    accepted = presentation.accept_repair_draft(
        run_id=run_id,
        issue_id=issue.issue_id,
        option_id="define_child_worker",
        session_id=creation.session_id,
        draft_id=creation.draft_id,
        revision_token=revision,
        user_input=_accepted_defaults(creation.draft, creation.draft_id),
    )

    assert "placement_ref" not in field_ids
    assert "result_usage" not in field_ids
    assert "handoff_binding" not in field_ids
    assert "invoke_output" not in field_ids
    assert accepted.input_readiness == "input_complete"


def test_materialized_preview_contains_final_ids_after_draft_acceptance() -> None:
    presentation, run_id, issue, revision, creation = _create_draft()
    accepted = presentation.accept_repair_draft(
        run_id=run_id,
        issue_id=issue.issue_id,
        option_id="define_child_worker",
        session_id=creation.session_id,
        draft_id=creation.draft_id,
        revision_token=revision,
        user_input=_accepted_defaults(creation.draft, creation.draft_id),
    )

    handle = presentation.create_materialized_preview_from_draft(
        accepted.normalized_directive_id
    )

    assert handle.preview.typed_artifact is not None
    roles = {node.role for node in handle.preview.typed_artifact.construct_nodes}
    assert {"child_worker", "parent_invoke"}.issubset(roles)
    assert "Will ensure" not in handle.preview.rendered_preview
    assert "Will materialize" not in handle.preview.rendered_preview
    assert "[DEFINE_WORKER:" in handle.preview.rendered_preview
    assert "[INVOKE " in handle.preview.rendered_preview
    assert "ChildWorker_" not in handle.preview.rendered_preview


def test_interactive_define_child_worker_collects_typed_interaction_values(monkeypatch) -> None:
    module = _run_demo_module()
    calls = {}
    prompts: list[str] = []

    class _Service:
        def _get_snapshot(self, run_id):
            return SimpleNamespace(
                compile_run_id="demo",
                snapshot_id="snap_1",
                overlay_version=0,
                symbol_table=None,
                resources=None,
                agent_profile=None,
            )

        def get_patched_spl(self, run_id):
            return "patched"

    class _Presentation:
        def get_repair_interaction(self, run_id, issue_id, option_id, revision):
            return SimpleNamespace(
                strategy_id="worker_delegation.complete_closure.v2",
                option_id=option_id,
                contract_id="worker_delegation.define_child_worker.v1",
                contract_version="1",
                revision_token=revision,
                schemas=(
                    SimpleNamespace(
                        schema_id="worker_delegation.new_child_output.v1",
                        fields=(
                            SimpleNamespace(
                                field_id="display_name",
                                label="Returned result",
                                required=True,
                                input_type="short_text",
                                value=None,
                                options=(),
                                object_schema_id=None,
                                fact_schema_id=None,
                            ),
                            SimpleNamespace(
                                field_id="semantic_description",
                                label="Result description",
                                required=True,
                                input_type="long_text",
                                value=None,
                                options=(),
                                object_schema_id=None,
                                fact_schema_id=None,
                            ),
                        ),
                    ),
                ),
                fields=(
                    SimpleNamespace(
                        field_id="delegated_responsibility",
                        label="Child task",
                        required=True,
                        input_type="long_text",
                        value=None,
                        options=(),
                        object_schema_id=None,
                        fact_schema_id=None,
                    ),
                    SimpleNamespace(
                        field_id="input_refs",
                        label="Input variables",
                        required=True,
                        input_type="reference_select",
                        value=None,
                        options=(
                            SimpleNamespace(
                                label="user_request",
                                value="ref:input:user_request",
                            ),
                            SimpleNamespace(
                                label="No parent input",
                                value="explicit_none",
                            ),
                        ),
                        object_schema_id=None,
                        fact_schema_id=None,
                    ),
                    SimpleNamespace(
                        field_id="returned_results",
                        label="Returned results",
                        required=True,
                        input_type="new_fact_list",
                        value=None,
                        options=(),
                        object_schema_id=None,
                        fact_schema_id="worker_delegation.new_child_output.v1",
                    ),
                    SimpleNamespace(
                        field_id="child_business_logic",
                        label="Business logic",
                        required=True,
                        input_type="long_text",
                        value=None,
                        options=(),
                        object_schema_id=None,
                        fact_schema_id=None,
                    ),
                )
            )

        def submit_repair_directive_draft(self, request):
            calls["request"] = request
            return SimpleNamespace(
                input_readiness="input_complete",
                errors=(),
                normalized_directive_id="directive_1",
            )

        def preview_repair_directive(self, directive_id):
            return SimpleNamespace(
                session_id="session_1",
                suggestion_id="suggestion_1",
                evidence_user_text="{}",
                preview=SimpleNamespace(
                    preview_id="preview_1",
                    typed_artifact=object(),
                )
            )

        def apply_repair_preview(self, directive_id, preview_id):
            calls["apply"] = (directive_id, preview_id)
            return (
                SimpleNamespace(overlay_version=1),
                SimpleNamespace(accepted=True, failure_reasons=()),
            )

        def present_verification(self, run_id, verification, updated_spl=None):
            return SimpleNamespace()

    inputs = iter(
        (
            "Gather evidence",
            "",
            "source evidence",
            "Gather evidence using user_request",
            "y",
        )
    )

    def _input(prompt: str = "") -> str:
        prompts.append(prompt)
        return next(inputs)

    monkeypatch.setattr("builtins.input", _input)
    monkeypatch.setattr(module, "_print_verification", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "nl2spl.rendering.render_repair_preview_spl",
        lambda _artifact, _context: SimpleNamespace(text="[WORKER: ChildWorker_test]"),
    )

    module._run_typed_interaction_repair(
        service=_Service(),
        presentation=_Presentation(),
        run_id="demo",
        issue_id="issue_1",
        option=SimpleNamespace(option_id="define_child_worker"),
    )

    assert any("Child worker task" in prompt for prompt in prompts)
    assert not any("Local ID" in prompt for prompt in prompts)
    assert not any("Result description" in prompt for prompt in prompts)
    request = calls["request"]
    assert request.field_values == {
        "child_task": "Gather evidence",
        "delegated_responsibility": "Gather evidence",
        "child_business_logic": "Gather evidence using user_request",
        "invocation_timing": "append",
        "result_usage": (
            {
                "output_local_id": "source_evidence",
                "create_parent_local_temporary": "yes",
            },
        ),
    }
    assert request.selected_ref_ids == {"input_refs": ("ref:input:user_request",)}
    assert request.new_fact_declarations == (
        {
            "local_id": "source_evidence",
            "display_name": "source evidence",
            "semantic_description": "Result returned by child worker: source evidence",
        },
    )
    assert calls["apply"] == ("directive_1", "preview_1")


def _accepted_defaults(draft, draft_id: str) -> UserRepairInput:
    fields = {field.field_id: field.value for field in draft.fields}
    task = fields["child_task"]
    inputs = fields["child_inputs"]
    output = fields["child_output"]
    logic = fields["child_business_logic"]
    assert isinstance(task, ResponsibilityValue)
    assert isinstance(inputs, SelectedInputRefsValue)
    assert isinstance(output, NewOutputDraftValue)
    assert isinstance(logic, BusinessLogicValue)
    return UserRepairInput(
        input_mode="structured_form",
        field_values=(
            UserRepairFieldValue("child_task", task.text, "accepted_default"),
            UserRepairFieldValue("child_inputs", inputs.ref_ids, "accepted_default"),
            UserRepairFieldValue("child_output", output.display_name, "accepted_default"),
            UserRepairFieldValue("child_business_logic", logic.text, "accepted_default"),
        ),
        accepted_draft_id=draft_id,
        draft_accepted=True,
    )
