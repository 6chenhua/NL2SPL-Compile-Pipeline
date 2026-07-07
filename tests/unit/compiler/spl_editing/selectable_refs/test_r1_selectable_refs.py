"""R1 SelectableRef Foundation tests."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairContext, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.selectable_refs import (
    SelectableRef,
    SelectableRefSet,
    SelectableRefSetBuilder,
    resolve_ref_id,
    resolve_ref_ids,
    resolve_ref_ids_to_result,
)
from nl2spl.compiler.spl_editing.selectable_refs.errors import (
    SelectableRefCollisionError,
    SelectableRefNotFoundError,
    SelectableRefPolicyViolationError,
    SelectableRefRoleMismatchError,
)
from nl2spl.ir import (
    AmbiguityInfo,
    ContractFieldIR,
    SpanIR,
    StepIR,
    SymbolTable,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.resource_registry_ir import (
    APISpec,
    FileSpec,
    ResourceRegistryIR,
    VariableSpec,
    WorkerScopedResourceIR,
)


def _snap(**kw: object) -> ArtifactSnapshot:
    d: dict[str, object] = dict(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=0,
        worker_plan=WorkerPlanIR("w_main", []),
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
        symbol_table=SymbolTable(),
        spans=(),
    )
    d.update(kw)
    return ArtifactSnapshot(**d)  # type: ignore[arg-type]


def _issue(**kw: object) -> EditableIssue:
    d: dict[str, object] = dict(
        issue_id="i1",
        primary_diagnostic_id="d1",
        related_diagnostic_ids=("d1",),
        issue_group_id=None,
        kind="missing_output_producer",
        target_ref="worker:w_main.output:draft",
        irs_ref=DiagnosticIRSRef(
            construct_type="REQUIRED_OUTPUT",
            construct_id="x",
            slot_name="producer",
        ),
        missing_slot="producer",
        source_span_ids=(),
        message="Producer unavailable.",
    )
    d.update(kw)
    return EditableIssue(**d)  # type: ignore[arg-type]


def _context(issue: EditableIssue, **kw: object) -> RepairContext:
    target = RepairTarget(
        target_ref=issue.target_ref,
        target_kind="REQUIRED_OUTPUT",
        irs_ref=issue.irs_ref,
        affordance_id="required_output.insert_or_bind_producer",
        construct_path=(),
        worker_id="w_main",
    )
    d: dict[str, object] = dict(
        issue=issue,
        target=target,
        worker_scope="w_main",
        related_steps=(),
        related_outputs=(issue.missing_slot,) if issue.missing_slot else (),
    )
    d.update(kw)
    return RepairContext(**d)  # type: ignore[arg-type]


def test_ref_id_is_stable() -> None:
    """Verify generated ref IDs are stable and consistent across identical builds."""
    issue = _issue()
    context = _context(issue)
    snap = _snap()

    refset1 = SelectableRefSetBuilder.build(snap, context)
    refset2 = SelectableRefSetBuilder.build(snap, context)

    assert refset1.set_id == refset2.set_id
    assert [r.ref_id for r in refset1.refs] == [r.ref_id for r in refset2.refs]


def test_same_canonical_name_in_different_scopes_does_not_collide() -> None:
    """Verify variables with the same canonical name in different scopes produce distinct ref IDs."""  # noqa: E501
    sym = SymbolTable()
    # 1. Global my_var (declared via public declare)
    sym.declare("my_var", "text", "input", "description")
    # 2. Worker-scoped my_var (declared via public declare_scoped)
    sym.declare_scoped(
        name="my_var",
        data_type="text",
        source="derived",
        description="scoped",
        scope_kind="worker",
        scope_id="w_main",
    )

    snap = _snap(symbol_table=sym)
    issue = _issue()
    context = _context(issue)

    refset = SelectableRefSetBuilder.build(snap, context)

    global_ref = refset.get_ref("variable:global:symbol_table:global:my_var")
    scoped_ref = refset.get_ref("variable:w_main:symbol_table:worker:my_var")

    assert global_ref is not None
    assert scoped_ref is not None
    assert global_ref.ref_id != scoped_ref.ref_id


def test_required_output_and_worker_input_same_name_do_not_collide() -> None:
    """Verify same variable name under required output vs worker input vs resource variable do not collide."""  # noqa: E501
    # Worker input contract
    worker_spec = WorkerSpecIR(
        worker_id="w_main",
        worker_name="w_main",
        kind="main",
        purpose="test",
        input_contract=[
            ContractFieldIR(
                name="payload_data",
                data_type="text",
                required=True,
                description="desc",
                source="input",
            )
        ],
    )
    # Worker scoped resource variable
    wsr = WorkerScopedResourceIR(
        global_resources=ResourceRegistryIR(
            variables=[
                VariableSpec(
                    name="payload_data",
                    data_type="text",
                    required=True,
                    description="global variable",
                    source="variable",
                )
            ]
        )
    )

    snap = _snap(
        worker_plan=WorkerPlanIR(main_worker_id="w_main", workers=[worker_spec]),
        worker_scoped_resources=wsr,
    )
    issue = _issue(missing_slot="payload_data")
    context = _context(issue, related_outputs=("payload_data",))

    refset = SelectableRefSetBuilder.build(snap, context)

    required_out_ref = refset.get_ref(
        "required_output:w_main:required_output_context::payload_data"
    )
    worker_in_ref = refset.get_ref("worker_input:w_main:w_main::payload_data")
    resource_var_ref = refset.get_ref(
        "resource:global:global_resources.variables:global_resources.variables:payload_data"
    )

    assert required_out_ref is not None
    assert worker_in_ref is not None
    assert resource_var_ref is not None

    ref_ids = {required_out_ref.ref_id, worker_in_ref.ref_id, resource_var_ref.ref_id}
    assert len(ref_ids) == 3


def test_resource_variable_file_and_api_same_name_do_not_collide() -> None:
    """Verify resource subtype namespace prevents legal same-name resource collisions."""
    resources = ResourceRegistryIR(
        variables=[
            VariableSpec(
                name="shared_name",
                data_type="text",
                required=True,
                description="resource variable",
                source="variable",
            )
        ],
        files=[
            FileSpec(
                name="shared_name",
                path="/tmp/shared_name.txt",
                data_type="text",
                description="resource file",
            )
        ],
        apis=[
            APISpec(
                api_name="shared_name",
                auth="none",
                description="resource api",
            )
        ],
    )
    snap = _snap(resources=resources)
    issue = _issue()
    context = _context(issue)

    refset = SelectableRefSetBuilder.build(snap, context)

    variable_ref = refset.get_ref(
        "resource:global:resources.variables:resources.variables:shared_name"
    )
    file_ref = refset.get_ref("resource:global:resources.files:resources.files:shared_name")
    api_ref = refset.get_ref("resource:global:resources.apis:resources.apis:shared_name")

    assert variable_ref is not None
    assert file_ref is not None
    assert api_ref is not None
    assert len({variable_ref.ref_id, file_ref.ref_id, api_ref.ref_id}) == 3
    assert variable_ref.ref_role == "selectable_input"
    assert file_ref.ref_role == "selectable_input"
    assert api_ref.ref_role == "api_resource"


def test_same_ref_in_same_snapshot_is_stable() -> None:
    """Verify consecutive builder calls on the same snapshot yield identical references."""
    sym = SymbolTable()
    sym.declare("a", "text", "input", "desc")
    snap = _snap(symbol_table=sym)
    issue = _issue()
    context = _context(issue)

    refset = SelectableRefSetBuilder.build(snap, context)
    assert len(refset.refs) > 0
    ref1 = refset.refs[0]
    ref2 = SelectableRefSetBuilder.build(snap, context).refs[0]
    assert ref1 == ref2


def test_overlay_added_ref_receives_stable_derived_id() -> None:
    """Verify step outputs added by previous overlays get stable IDs not dependent on version."""
    step = StepIR(
        step_id="st_repair_1_w_main",
        text="Produce outputs",
        source_span_ids=[],
        command_type="GENERAL_COMMAND",
        inputs=[],
        outputs=["derived_var"],
        metadata={"origin": "user_confirmed_repair"},
    )
    snap = _snap(worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": [step]}))
    issue = _issue()
    context = _context(issue)

    refset = SelectableRefSetBuilder.build(snap, context)
    ref = refset.get_ref("step_output:w_main:st_repair_1_w_main::derived_var")
    assert ref is not None
    assert ref.canonical_name == "derived_var"


def test_required_output_ref_has_target_output_role() -> None:
    """Verify target outputs have target_output role."""
    snap = _snap()
    issue = _issue(missing_slot="my_output")
    context = _context(issue, related_outputs=("my_output",))

    refset = SelectableRefSetBuilder.build(snap, context)
    ref = refset.get_ref("required_output:w_main:required_output_context::my_output")
    assert ref is not None
    assert ref.ref_role == "target_output"
    assert ref.ref_kind == "required_output"


def test_target_output_cannot_resolve_as_selectable_input() -> None:
    """Verify that a target output cannot be resolved as a selectable input."""
    snap = _snap()
    issue = _issue(missing_slot="my_output")
    context = _context(issue, related_outputs=("my_output",))

    refset = SelectableRefSetBuilder.build(snap, context)
    ref_id = "required_output:w_main:required_output_context::my_output"

    with pytest.raises(SelectableRefRoleMismatchError):
        resolve_ref_ids(refset, (ref_id,), "selectable_input")


def test_unknown_ref_id_fails() -> None:
    """Verify resolving unknown ref IDs raises SelectableRefNotFoundError."""
    refset = SelectableRefSetBuilder.build(_snap(), _context(_issue()))
    with pytest.raises(SelectableRefNotFoundError):
        resolve_ref_id(refset, "unknown_ref")


def test_cross_worker_ref_rejected_by_default_policy() -> None:
    """Verify cross-worker inputs are rejected under the default policy validation."""
    refset = SelectableRefSet(
        set_id="set_1",
        issue_id="i1",
        snapshot_id="snap_1",
        worker_scope="w_main",
        refs=(
            SelectableRef(
                ref_id="step_output:w_other:st_1::res",
                ref_kind="step_output",
                ref_role="selectable_input",
                canonical_name="res",
                display_label="res",
                worker_id="w_other",
            ),
        ),
        policy_id="required_output.producer.selectable_refs.v1",
    )

    with pytest.raises(SelectableRefPolicyViolationError, match="worker scope"):
        resolve_ref_ids(refset, ("step_output:w_other:st_1::res",), "selectable_input")


def test_refset_contains_worker_inputs_and_step_outputs() -> None:
    """Verify builder extracts worker inputs, step outputs, and symbol variables correctly."""
    worker_spec = WorkerSpecIR(
        worker_id="w_main",
        worker_name="w_main",
        kind="main",
        purpose="test",
        input_contract=[
            ContractFieldIR(
                name="main_input",
                data_type="text",
                required=True,
                description="desc",
                source="input",
            )
        ],
    )
    step = StepIR(
        step_id="st_1",
        text="test",
        source_span_ids=[],
        command_type="GENERAL_COMMAND",
        inputs=[],
        outputs=["my_step_output"],
    )

    snap = _snap(
        worker_plan=WorkerPlanIR(main_worker_id="w_main", workers=[worker_spec]),
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": [step]}),
    )
    issue = _issue()
    context = _context(issue)

    refset = SelectableRefSetBuilder.build(snap, context)

    input_ref = refset.get_ref("worker_input:w_main:w_main::main_input")
    assert input_ref is not None
    assert input_ref.ref_kind == "worker_input"
    assert input_ref.ref_role == "selectable_input"

    output_ref = refset.get_ref("step_output:w_main:st_1::my_step_output")
    assert output_ref is not None
    assert output_ref.ref_kind == "step_output"
    assert output_ref.ref_role == "selectable_input"


def test_builder_does_not_read_diagnostic_message() -> None:
    """Verify builder does not extract variables from diagnostic messages."""
    snap = _snap()
    issue = _issue(message="Hallucination attempt with project_data variables")
    context = _context(issue)

    refset = SelectableRefSetBuilder.build(snap, context)
    for ref in refset.refs:
        assert "project_data" not in ref.canonical_name


def test_refset_missing_required_artifact_marks_unavailable() -> None:
    """Verify missing required artifacts in snapshot flag the refset as unavailable."""
    snap = _snap(worker_step_plan=None)
    issue = _issue()
    context = _context(issue)

    refset = SelectableRefSetBuilder.build(snap, context)
    assert not refset.is_available
    assert "step_output" in refset.missing_required_ref_kinds
    assert "resource" in refset.missing_required_ref_kinds


def test_source_span_evidence() -> None:
    """Verify source spans are harvested as source_evidence role and source_span kind."""
    span = SpanIR(
        span_id="span_1", text="Example workflow span content.", ambiguity=AmbiguityInfo()
    )
    snap = _snap(spans=(span,))
    issue = _issue()
    context = _context(issue)

    refset = SelectableRefSetBuilder.build(snap, context)
    ref = refset.get_ref("source_span:global:spans::span_1")
    assert ref is not None
    assert ref.ref_kind == "source_span"
    assert ref.ref_role == "source_evidence"
    assert ref.display_label == "Example workflow span content."


def test_builder_fails_loudly_on_id_collision() -> None:
    """Verify that generating duplicate ref_ids raises SelectableRefCollisionError."""
    span1 = SpanIR(span_id="span_1", text="Span one text", ambiguity=AmbiguityInfo())
    span2 = SpanIR(span_id="span_1", text="Span two text", ambiguity=AmbiguityInfo())

    snap = _snap(spans=(span1, span2))
    issue = _issue()
    context = _context(issue)

    with pytest.raises(SelectableRefCollisionError, match="Collision detected for ref_id"):
        SelectableRefSetBuilder.build(snap, context)


def test_structured_resolution_result() -> None:
    """Verify that resolve_ref_ids_to_result yields structured success/error result records."""
    worker_spec = WorkerSpecIR(
        worker_id="w_main",
        worker_name="w_main",
        kind="main",
        purpose="test",
        input_contract=[
            ContractFieldIR(
                name="main_input",
                data_type="text",
                required=True,
                description="desc",
                source="input",
            )
        ],
    )
    snap = _snap(
        worker_plan=WorkerPlanIR(main_worker_id="w_main", workers=[worker_spec]),
    )
    issue = _issue(missing_slot="my_output")
    context = _context(issue, related_outputs=("my_output",))

    refset = SelectableRefSetBuilder.build(snap, context)

    # 1. Success case
    res1 = resolve_ref_ids_to_result(
        refset, ("worker_input:w_main:w_main::main_input",), "selectable_input"
    )
    assert res1.is_success
    assert len(res1.resolved_refs) == 1
    assert res1.resolved_refs[0].ref.canonical_name == "main_input"
    assert res1.resolved_refs[0].scope_matched
    assert len(res1.errors) == 0

    # 2. Unknown ID case
    res2 = resolve_ref_ids_to_result(refset, ("unknown_ref_id",), "selectable_input")
    assert not res2.is_success
    assert len(res2.resolved_refs) == 0
    assert len(res2.errors) == 1
    assert "not found" in res2.errors[0]

    # 3. Role mismatch case
    res3 = resolve_ref_ids_to_result(
        refset, ("required_output:w_main:required_output_context::my_output",), "selectable_input"
    )
    assert not res3.is_success
    assert len(res3.resolved_refs) == 0
    assert len(res3.errors) == 1
    assert "expected 'selectable_input'" in res3.errors[0]
