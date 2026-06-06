"""Unit tests for PostNormalizeIRSChecker — final authority for construct-level diagnostics."""

from __future__ import annotations

from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import (
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerInput,
    WorkerOutput,
    WorkerIR,
)
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    InputBindingIR,
    OutputBindingIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.stages.stage9_5_normalizer.final_irs_checker import (
    PostNormalizeIRSChecker,
)


def _make_worker(**kwargs) -> WorkerIR:
    defaults = dict(
        worker_name="main",
        description="Main worker",
        main_flow=FlowRef(),
        steps=[],
    )
    defaults.update(kwargs)
    return WorkerIR(**defaults)


class TestMissingHandler:
    """Exception flows without handlers -> missing_handler diagnostic."""

    def test_exception_flow_without_handler_emits_missing_handler(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                )
            ],
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND", flow_ref="main"),
            ],
        )

        diags = checker.check(worker)
        mh = [d for d in diags if d.kind == "missing_handler"]
        assert len(mh) == 1
        assert "exc_1" in mh[0].message
        assert mh[0].blocks_rendering is False
        assert mh[0].blocks_completion is True

    def test_exception_flow_with_handler_step_does_not_emit(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            exception_flows=[
                ExceptionFlowRef(flow_id="exc_1", condition_text="Error."),
            ],
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND", flow_ref="main"),
                StepIR("st2", "Handle error", ["s2"], "GENERAL_COMMAND", flow_ref="exc_1"),
            ],
        )

        diags = checker.check(worker)
        mh = [d for d in diags if d.kind == "missing_handler"]
        assert len(mh) == 0

    def test_handler_metadata_does_not_override_flow_ref(self) -> None:
        """Handler presence is structural; metadata is ignored."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            exception_flows=[
                ExceptionFlowRef(flow_id="exc_1", condition_text="API error."),
            ],
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND", flow_ref="main"),
                StepIR(
                    "st2", "Show error", [],
                    "DISPLAY_MESSAGE", flow_ref="exc_1",
                    metadata={"pseudo_exception_handler": "true"},
                ),
            ],
        )

        diags = checker.check(worker)
        mh = [d for d in diags if d.kind == "missing_handler"]
        assert len(mh) == 0

    def test_child_worker_exception_flow_without_handler(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[StepIR("st1", "Main work", ["s1"], "GENERAL_COMMAND")],
            child_workers=[
                ChildWorkerIR(
                    worker_name="child_1",
                    description="Child",
                    task_text="Do child work",
                    exception_flows=[
                        ExceptionFlowRef(flow_id="exc_c1", condition_text="Child error."),
                    ],
                    steps=[
                        StepIR("stc1", "Child work", ["cs1"], "GENERAL_COMMAND"),
                    ],
                )
            ],
        )

        diags = checker.check(worker)
        mh = [d for d in diags if d.kind == "missing_handler"]
        assert len(mh) == 1
        assert "exc_c1" in mh[0].message

    def test_no_exception_flows_no_missing_handler(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[StepIR("st1", "Work", ["s1"], "GENERAL_COMMAND")],
        )

        diags = checker.check(worker)
        mh = [d for d in diags if d.kind == "missing_handler"]
        assert len(mh) == 0


class TestMissingOutputProducer:
    """Required outputs without producers -> missing_output_producer diagnostic."""

    def test_required_output_without_producer(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[StepIR("st1", "Work", ["s1"], "GENERAL_COMMAND")],
        )
        worker_plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[
                WorkerSpecIR(
                    worker_id="main",
                    worker_name="main",
                    kind="main",
                    purpose="Main worker",
                    owned_span_ids=["s1"],
                    output_contract=[
                        ContractFieldIR("draft", "text", True, "Draft document", "output"),
                        ContractFieldIR("assumptions_log", "text", True, "Assumptions", "output"),
                    ],
                    input_contract=[],
                    boundary_kind="main_worker",
                )
            ],
            handoffs=[],
        )
        symbol_table = SymbolTable()
        symbol_table.declare("draft", "text", "output", "The draft document")
        symbol_table.declare("assumptions_log", "text", "output", "Assumptions log")

        diags = checker.check(
            worker, worker_plan=worker_plan,
            symbol_table=symbol_table,
            resources=ResourceRegistryIR(),
        )
        mop = [d for d in diags if d.kind == "missing_output_producer"]
        assert len(mop) == 2
        assert any("draft" in d.message for d in mop)
        assert any("assumptions_log" in d.message for d in mop)

    def test_output_with_producer_no_diagnostic(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR(
                    "st1", "Produce draft", ["s1"],
                    "GENERAL_COMMAND", outputs=["draft"],
                ),
            ],
        )
        worker_plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[
                WorkerSpecIR(
                    worker_id="main",
                    worker_name="main",
                    kind="main",
                    purpose="Main",
                    owned_span_ids=["s1"],
                    output_contract=[
                        ContractFieldIR("draft", "text", True, "Draft", "output"),
                    ],
                    input_contract=[],
                    boundary_kind="main_worker",
                )
            ],
            handoffs=[],
        )
        symbol_table = SymbolTable()
        symbol_table.declare("draft", "text", "step", "Draft")
        symbol_table.add_producer("draft", "st1")

        diags = checker.check(
            worker, worker_plan=worker_plan,
            symbol_table=symbol_table,
            resources=ResourceRegistryIR(),
        )
        mop = [d for d in diags if d.kind == "missing_output_producer"]
        assert len(mop) == 0

    def test_api_produced_output_no_missing_producer(self) -> None:
        """An output produced by CALL_API via handoff is not missing."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR(
                    "st1", "Call external API", ["s1"],
                    "CALL_API", integration_ref="my_api",
                    outputs=["api_result"], handoff_id="h1",
                ),
            ],
        )
        worker_plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[
                WorkerSpecIR(
                    worker_id="main",
                    worker_name="main",
                    kind="main",
                    purpose="Main",
                    owned_span_ids=["s1"],
                    output_contract=[
                        ContractFieldIR("api_result", "text", True, "API result", "output"),
                    ],
                    input_contract=[],
                    boundary_kind="main_worker",
                )
            ],
            handoffs=[
                WorkerHandoffIR(
                    handoff_id="h1",
                    from_worker="main",
                    to_worker=None,
                    api_ref="my_api",
                    mode="api_call",
                    condition_text=None,
                    ordering="after",
                    input_bindings=[],
                    output_bindings=[
                        OutputBindingIR(
                            child_output="raw", parent_variable="api_result",
                            required=True, merge_strategy="set",
                        ),
                    ],
                )
            ],
        )
        resources = ResourceRegistryIR(apis=[APISpec("my_api", "none", "Test API")])
        symbol_table = SymbolTable()
        symbol_table.declare("api_result", "text", "output", "API result")
        symbol_table.add_producer("api_result", "st1")

        diags = checker.check(
            worker, worker_plan=worker_plan,
            symbol_table=symbol_table,
            resources=resources,
        )
        mop = [d for d in diags if d.kind == "missing_output_producer"]
        assert len(mop) == 0

    def test_worker_scoped_missing_output_producer(self) -> None:
        """Child worker required output without producer."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[StepIR("st1", "Main work", ["s1"], "GENERAL_COMMAND")],
        )
        worker_plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[
                WorkerSpecIR(
                    worker_id="main",
                    worker_name="main",
                    kind="main",
                    purpose="Main",
                    owned_span_ids=["s1"],
                    output_contract=[],
                    input_contract=[],
                    boundary_kind="main_worker",
                ),
                WorkerSpecIR(
                    worker_id="child_1",
                    worker_name="child_1",
                    kind="child",
                    purpose="Child worker",
                    owned_span_ids=["cs1"],
                    output_contract=[
                        ContractFieldIR("child_draft", "text", True, "Child draft", "output"),
                    ],
                    input_contract=[],
                    boundary_kind="child_worker",
                ),
            ],
            handoffs=[],
        )
        symbol_table = SymbolTable()
        symbol_table.declare("child_draft", "text", "output", "Child draft")

        diags = checker.check(
            worker, worker_plan=worker_plan,
            symbol_table=symbol_table,
            resources=ResourceRegistryIR(),
        )
        mop = [d for d in diags if d.kind == "missing_output_producer"]
        assert len(mop) == 1
        assert "child_draft" in mop[0].message


class TestTypeContractAmbiguity:
    """Ambiguous command contracts -> type_or_contract_ambiguity diagnostic."""

    def test_call_api_without_integration_ref(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR("st1", "Call API", ["s1"], "CALL_API"),
            ],
        )

        diags = checker.check(worker)
        toca = [d for d in diags if d.kind == "type_or_contract_ambiguity"]
        assert len(toca) == 1
        assert "no integration_ref" in toca[0].message
        assert toca[0].blocks_rendering is True

    def test_call_api_undeclared_api(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR(
                    "st1", "Call undeclared", ["s1"],
                    "CALL_API", integration_ref="undeclared_api",
                ),
            ],
        )
        resources = ResourceRegistryIR(apis=[APISpec("declared_api", "none", "Test")])

        diags = checker.check(worker, resources=resources)
        toca = [d for d in diags if d.kind == "type_or_contract_ambiguity"]
        assert len(toca) == 1
        assert "undeclared_api" in toca[0].message

    def test_call_api_declared_no_ambiguity(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR(
                    "st1", "Call API", ["s1"],
                    "CALL_API", integration_ref="my_api",
                ),
            ],
        )
        resources = ResourceRegistryIR(apis=[APISpec("my_api", "none", "Test API")])

        diags = checker.check(worker, resources=resources)
        toca = [d for d in diags if d.kind == "type_or_contract_ambiguity"]
        assert len(toca) == 0

    def test_invoke_worker_without_target(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR("st1", "Invoke worker", ["s1"], "INVOKE_WORKER"),
            ],
        )

        diags = checker.check(worker)
        toca = [d for d in diags if d.kind == "type_or_contract_ambiguity"]
        assert len(toca) == 1
        assert "INVOKE_WORKER" in toca[0].message
        assert "no concrete worker target" in toca[0].message

    def test_request_input_without_source_span(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR("st1", "Ask user", [], "REQUEST_INPUT"),
            ],
        )

        diags = checker.check(worker)
        toca = [d for d in diags if d.kind == "type_or_contract_ambiguity"]
        assert len(toca) == 1
        assert "REQUEST_INPUT" in toca[0].message

    def test_request_input_with_source_span_no_ambiguity(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR("st1", "Ask user for input", ["s1"], "REQUEST_INPUT"),
            ],
        )

        diags = checker.check(worker)
        toca = [d for d in diags if d.kind == "type_or_contract_ambiguity"]
        assert len(toca) == 0

    def test_construct_findings_are_ignored_for_compatibility(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            exception_flows=[
                ExceptionFlowRef(flow_id="exc_1", condition_text="API error."),
            ],
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND", flow_ref="main"),
            ],
        )
        findings = {
            "pseudo_handlers": [
                {
                    "step_id": "st_disp",
                    "flow_id": "exc_1",
                    "worker_id": "main",
                    "text": "Display error message",
                    "source_span_ids": ["s2"],
                }
            ]
        }

        diags = checker.check(worker, construct_findings=findings)
        toca = [d for d in diags if d.kind == "type_or_contract_ambiguity"]
        assert not any("st_disp" in d.message for d in toca)
        assert not any("condition restatement" in d.message for d in toca)

    def test_call_api_with_handoff_bound_api_no_ambiguity(self) -> None:
        """CALL_API with handoff_id matching an api_call handoff is not ambiguous."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR(
                    "st1", "Call API", ["s1"],
                    "CALL_API", integration_ref="handoff_api",
                    handoff_id="h1",
                ),
            ],
        )
        worker_plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[
                WorkerSpecIR(
                    worker_id="main",
                    worker_name="main",
                    kind="main",
                    purpose="Main",
                    owned_span_ids=["s1"],
                    output_contract=[],
                    input_contract=[],
                    boundary_kind="main_worker",
                )
            ],
            handoffs=[
                WorkerHandoffIR(
                    handoff_id="h1",
                    from_worker="main",
                    to_worker=None,
                    api_ref="handoff_api",
                    mode="api_call",
                    condition_text=None,
                    ordering="after",
                    input_bindings=[],
                    output_bindings=[],
                )
            ],
        )

        diags = checker.check(worker, worker_plan=worker_plan)
        toca = [d for d in diags if d.kind == "type_or_contract_ambiguity"]
        assert len(toca) == 0


class TestAssumedCommand:
    """Steps without source evidence -> assumed_command_not_renderable."""

    def test_step_without_source_span_is_assumed(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR("st1", "Do work", [], "GENERAL_COMMAND"),
            ],
        )

        diags = checker.check(worker)
        ac = [d for d in diags if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 1
        assert "st1" in ac[0].message
        assert ac[0].blocks_rendering is True

    def test_source_backed_step_is_not_assumed(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
            ],
        )

        diags = checker.check(worker)
        ac = [d for d in diags if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 0

    def test_compiler_unpack_step_is_not_assumed(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR(
                    "st1", "Extract field from result", [],
                    "GENERAL_COMMAND",
                    metadata={"origin": "compiler_unpack"},
                ),
            ],
        )

        diags = checker.check(worker)
        ac = [d for d in diags if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 0

    def test_valid_handoff_step_is_not_assumed(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR(
                    "st1", "Invoke child", [],
                    "INVOKE_WORKER",
                    integration_ref="child_worker_1",
                    handoff_id="h1",
                ),
            ],
        )
        worker_plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[
                WorkerSpecIR(
                    worker_id="main",
                    worker_name="main",
                    kind="main",
                    purpose="Main",
                    owned_span_ids=["s1"],
                    output_contract=[],
                    input_contract=[],
                    boundary_kind="main_worker",
                )
            ],
            handoffs=[
                WorkerHandoffIR(
                    handoff_id="h1",
                    from_worker="main",
                    to_worker="child_1",
                    api_ref=None,
                    mode="invoke",
                    condition_text=None,
                    ordering="after",
                    input_bindings=[],
                    output_bindings=[],
                )
            ],
        )

        diags = checker.check(worker, worker_plan=worker_plan)
        ac = [d for d in diags if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 0

    def test_handoff_step_without_validity_set_not_assumed_legacy(self) -> None:
        """Legacy path: handoff_id without validity set is accepted."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR(
                    "st1", "Invoke worker", [],
                    "INVOKE_WORKER", handoff_id="h1",
                ),
            ],
        )

        diags = checker.check(worker)  # no worker_plan -> valid_handoff_ids is empty set
        ac = [d for d in diags if d.kind == "assumed_command_not_renderable"]
        # Legacy: without validity set, handoff_id is accepted.
        assert len(ac) == 0

    def test_invalid_handoff_id_is_assumed(self) -> None:
        """Handoff_id not in valid set -> assumed."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR(
                    "st1", "Invoke worker", [],
                    "INVOKE_WORKER", handoff_id="h_fake",
                ),
            ],
        )
        worker_plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[
                WorkerSpecIR(
                    worker_id="main",
                    worker_name="main",
                    kind="main",
                    purpose="Main",
                    owned_span_ids=["s1"],
                    output_contract=[],
                    input_contract=[],
                    boundary_kind="main_worker",
                )
            ],
            handoffs=[
                WorkerHandoffIR(
                    handoff_id="h_real",
                    from_worker="main",
                    to_worker="child_1",
                    api_ref=None,
                    mode="invoke",
                    condition_text=None,
                    ordering="after",
                    input_bindings=[],
                    output_bindings=[],
                )
            ],
        )

        diags = checker.check(worker, worker_plan=worker_plan)
        ac = [d for d in diags if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 1
        assert "st1" in ac[0].message

    def test_display_message_step_without_source_is_assumed(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR("st1", "Display message", [], "DISPLAY_MESSAGE"),
            ],
        )

        diags = checker.check(worker)
        ac = [d for d in diags if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 1


class TestMultipleDiagnosticKinds:
    """Scenarios producing multiple diagnostic kinds simultaneously."""

    def test_missing_handler_and_assumed_command_together(self) -> None:
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            exception_flows=[
                ExceptionFlowRef(flow_id="exc_1", condition_text="Missing timeframe."),
            ],
            steps=[
                StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND", flow_ref="main"),
                StepIR("st2", "Synthetic step without source", [], "GENERAL_COMMAND"),
            ],
        )

        diags = checker.check(worker)
        kinds = {d.kind for d in diags}
        assert "missing_handler" in kinds
        assert "assumed_command_not_renderable" in kinds
        assert len(diags) >= 2

    def test_all_diagnostics_from_worker_scoped_resources(self) -> None:
        """Worker-scoped resources merge correctly for CALL_API check."""
        from nl2spl.ir.resource_registry_ir import WorkerScopedResourceIR

        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR(
                    "st1", "Call worker-local API", ["s1"],
                    "CALL_API", integration_ref="worker_local_api",
                ),
            ],
        )
        resources = ResourceRegistryIR()  # global resources don't have it
        ws_resources = WorkerScopedResourceIR(
            global_resources=resources,
            worker_resources={
                "main": ResourceRegistryIR(
                    apis=[APISpec("worker_local_api", "none", "Worker-local API")],
                )
            },
        )

        diags = checker.check(
            worker,
            resources=resources,
            worker_scoped_resources=ws_resources,
        )
        toca = [d for d in diags if d.kind == "type_or_contract_ambiguity"]
        assert len(toca) == 0


# ------------------------------------------------------------------
# R7.3: missing_slot / target_ref / source_span_ids shape tests
# ------------------------------------------------------------------


class TestDiagnosticShapeHardening:
    """R7.3: Verify missing_slot is populated for all diagnostic kinds."""

    def test_missing_handler_has_missing_slot(self) -> None:
        """missing_handler diagnostic has populated missing_slot."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            exception_flows=[
                ExceptionFlowRef(flow_id="exc_1", condition_text="Fail."),
            ],
            steps=[StepIR("st1", "Work", ["s1"], "GENERAL_COMMAND")],
        )
        diags = checker.check(worker)
        mh = [d for d in diags if d.kind == "missing_handler"]
        assert len(mh) == 1
        assert mh[0].missing_slot is not None
        assert mh[0].missing_slot.slot_name == "handler_action"
        assert mh[0].missing_slot.required_for == "exc_1"
        assert mh[0].target_ref == "exception_flow:exc_1"

    def test_missing_handler_fallback_source_spans(self) -> None:
        """missing_handler falls back to ExceptionFlowRef.spans when no findings."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Fail.",
                    spans=["s_fail"],
                ),
            ],
            steps=[StepIR("st1", "Work", ["s1"], "GENERAL_COMMAND")],
        )
        diags = checker.check(worker)
        mh = [d for d in diags if d.kind == "missing_handler"]
        assert len(mh) == 1
        # source_span_ids should fall back to ExceptionFlowRef.spans
        assert mh[0].source_span_ids == ["s_fail"]
        assert mh[0].missing_slot.source_span_ids == ["s_fail"]

    def test_missing_output_producer_has_missing_slot(self) -> None:
        """missing_output_producer diagnostic has populated missing_slot."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[StepIR("st1", "Work", ["s1"], "GENERAL_COMMAND")],
        )
        worker_plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[
                WorkerSpecIR(
                    worker_id="main",
                    worker_name="main",
                    kind="main",
                    purpose="Main",
                    owned_span_ids=["s1"],
                    output_contract=[
                        ContractFieldIR("draft", "text", True, "Draft", "output"),
                    ],
                    input_contract=[],
                    boundary_kind="main_worker",
                ),
            ],
            handoffs=[],
        )
        symbol_table = SymbolTable()
        symbol_table.declare("draft", "text", "output", "Draft")

        diags = checker.check(
            worker, worker_plan=worker_plan, symbol_table=symbol_table,
            resources=ResourceRegistryIR(),
        )
        mop = [d for d in diags if d.kind == "missing_output_producer"]
        assert len(mop) == 1
        assert mop[0].missing_slot is not None
        assert mop[0].missing_slot.slot_name == "draft"
        assert mop[0].target_ref is not None

    def test_type_contract_ambiguity_has_missing_slot(self) -> None:
        """type_or_contract_ambiguity diagnostic has populated missing_slot."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[
                StepIR("st1", "Call API", ["s1"], "CALL_API"),
            ],
        )
        diags = checker.check(worker)
        toca = [d for d in diags if d.kind == "type_or_contract_ambiguity"]
        assert len(toca) == 1
        assert toca[0].missing_slot is not None
        assert toca[0].missing_slot.slot_name == "api_name"
        assert toca[0].target_ref == "step:st1"
        assert toca[0].source_span_ids == ["s1"]

    def test_assumed_command_has_missing_slot(self) -> None:
        """assumed_command_not_renderable diagnostic has populated missing_slot."""
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            steps=[StepIR("st1", "Do thing", [], "GENERAL_COMMAND")],
        )
        diags = checker.check(worker)
        ac = [d for d in diags if d.kind == "assumed_command_not_renderable"]
        assert len(ac) == 1
        assert ac[0].missing_slot is not None
        assert ac[0].missing_slot.slot_name == "source_evidence"
        assert ac[0].missing_slot.required_for == "st1"
        assert ac[0].target_ref == "step:st1"
        # source_span_ids is empty by design (the diagnostic fires because
        # the step has no source spans)
        assert ac[0].source_span_ids == []

    def test_missing_slot_slot_name_aligns_with_irs_registry(self) -> None:
        """All missing_slot.slot_name values must exist in the IRS construct spec."""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry

        registry = SPLConstructRegistry.default()
        checker = PostNormalizeIRSChecker()
        worker = _make_worker(
            exception_flows=[
                ExceptionFlowRef(flow_id="exc_1", condition_text="Fail."),
            ],
            steps=[
                StepIR("st1", "Do work", [], "GENERAL_COMMAND"),
                StepIR("st2", "Call API", ["s1"], "CALL_API"),
            ],
        )
        diags = checker.check(worker)
        for d in diags:
            if d.missing_slot is not None:
                # For step-level diagnostics, the slot_name might not be
                # an IRS slot (it's the step's own field). For construct-
                # level diagnostics, it should match.
                if d.kind == "missing_handler":
                    exc_irs = registry.get("EXCEPTION_FLOW")
                    slot = exc_irs.get_slot(d.missing_slot.slot_name)
                    assert slot is not None, (
                        f"slot_name '{d.missing_slot.slot_name}' not found "
                        f"in EXCEPTION_FLOW IRS"
                    )


# ------------------------------------------------------------------
# R7.6: Projector bridge spike
# ------------------------------------------------------------------


class TestProjectorBridgeSpike:
    """R7.6: Verify DiagnosticProjector can produce equivalent diagnostics
    from ConstructSatisfactionReport for PostNormalizeIRSChecker kinds.

    This is a proof-of-concept. PostNormalizeIRSChecker still directly
    creates CompileDiagnostic in production. The bridge shows that the
    projector COULD be used for future unification.
    """

    def test_projector_bridge_assumed_command(self) -> None:
        """Projector produces same diagnostic kind as PostNormalizeIRSChecker."""
        from nl2spl.compiler.construct_registry import (
            ConstructSatisfactionReport,
            SlotSatisfaction,
        )
        from nl2spl.compiler.irs.context import IRSCheckContext
        from nl2spl.compiler.irs.projector import DiagnosticProjector

        # Build a report that mirrors what PostNormalizeIRSChecker would produce
        report = ConstructSatisfactionReport(
            construct_id="step:st1",
            construct_type="GENERAL_COMMAND",
            slots=[
                SlotSatisfaction(
                    slot_name="action_text",
                    status="satisfied",
                    source_span_ids=[],
                ),
                SlotSatisfaction(
                    slot_name="source_evidence",
                    status="missing",
                    diagnostic_kind="assumed_command_not_renderable",
                    explanation="Step has no source-span evidence.",
                ),
                SlotSatisfaction(
                    slot_name="result_variable",
                    status="not_applicable",
                ),
            ],
            completeness="partial",
            renderable=False,
            frontier_status="leaf",
        )

        projector = DiagnosticProjector()
        context = IRSCheckContext(stage_name="post_normalize")
        result = projector.project([report], context)

        assert len(result.diagnostics) == 1
        d = result.diagnostics[0]
        assert d.kind == "assumed_command_not_renderable"
        assert d.target_ref == "step:st1"
        assert d.blocks_rendering is True
        assert d.missing_slot is not None
        assert d.missing_slot.slot_name == "source_evidence"
