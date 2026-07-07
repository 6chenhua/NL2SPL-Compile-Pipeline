"""Unit tests for Stage 11: SPLRenderer."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.agent_profile_ir import AgentProfileIR, Aspect, Concept, PersonaIR
from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import ChildWorkerIR, WorkerInput, WorkerIR, WorkerOutput
from nl2spl.pipeline.stages.stage11_spl_renderer import SPLRenderer


class TestSPLRenderer:
    """Tests for SPLRenderer."""

    def test_basic_rendering(self) -> None:
        """Test basic SPL rendering."""
        # Arrange
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test worker",
            inputs=[WorkerInput("input1", True)],
            outputs=[WorkerOutput("output1", True)],
        )
        profile = AgentProfileIR(
            persona=PersonaIR(role="Test Role", aspects=[Aspect("Tone", "Professional")]),
            audience_aspects=[Aspect("Level", "Senior")],
            concepts=[Concept("Test", "Definition")],
        )
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("input1", "text", True, "Input", "input"),
                VariableSpec("output1", "text", True, "Output", "output"),
            ]
        )
        symbols = SymbolTable()
        steps = []
        constraints = []

        # Act
        spl_text, errors, warnings = renderer.render(
            worker, profile, resources, symbols, steps, constraints
        )

        # Assert
        assert "[DEFINE_AGENT: TestWorker \"Test worker\"]" in spl_text
        assert "[DEFINE_PERSONA:]" in spl_text
        assert "ROLE: Test Role" in spl_text
        assert "[DEFINE_AUDIENCE:]" in spl_text
        assert "[DEFINE_CONCEPTS:]" in spl_text
        assert "[DEFINE_VARIABLES:]" in spl_text
        assert "[DEFINE_WORKER: \"Test worker\" TestWorker]" in spl_text
        assert "[INPUTS]" in spl_text
        assert "[OUTPUTS]" in spl_text
        assert "[MAIN_FLOW]" in spl_text
        assert "[END_WORKER]" in spl_text
        assert "[END_AGENT]" in spl_text
        assert len(errors) == 0
        assert len(warnings) == 0

    def test_rendering_with_constraints(self) -> None:
        """Test rendering with constraints."""
        # Arrange
        renderer = SPLRenderer()
        worker = WorkerIR(worker_name="TestWorker", description="Test")
        profile = AgentProfileIR()
        resources = ResourceRegistryIR()
        symbols = SymbolTable()
        steps = []
        constraints = [
            ConstraintIR("c1", "Do not invent facts", "prohibition", ["global"], []),
            ConstraintIR("c2", "Require evidence", "evidence", ["global"], []),
        ]

        # Act
        spl_text, _, _ = renderer.render(worker, profile, resources, symbols, steps, constraints)

        # Assert
        assert "[DEFINE_CONSTRAINTS:]" in spl_text
        assert "Prohibition: Do not invent facts" in spl_text
        assert "Evidence: Require evidence" in spl_text
        assert "Do not invent facts" in spl_text
        assert "Require evidence" in spl_text

    def test_rendering_with_steps(self) -> None:
        """Test rendering with steps."""
        # Arrange
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=MagicMock(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
        )
        profile = AgentProfileIR()
        resources = ResourceRegistryIR()
        symbols = SymbolTable()
        steps = [StepIR("st1", "Test step", ["s1"], "GENERAL_COMMAND")]
        constraints = []

        # Act
        spl_text, _, _ = renderer.render(worker, profile, resources, symbols, steps, constraints)

        # Assert
        assert "[SEQUENTIAL_BLOCK]" in spl_text
        assert "COMMAND-1 [COMMAND Test step]" in spl_text

    def test_rendering_with_alternative_flows(self) -> None:
        """Test rendering with alternative flows."""
        # Arrange
        renderer = SPLRenderer()
        from nl2spl.ir.worker_ir import AlternativeFlowRef

        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            alternative_flows=[
                AlternativeFlowRef("alt_1", "condition", []),
                AlternativeFlowRef("alt_2", "condition2", []),
            ],
        )
        profile = AgentProfileIR()
        resources = ResourceRegistryIR()
        symbols = SymbolTable()
        steps = []
        constraints = []

        # Act
        spl_text, _, _ = renderer.render(worker, profile, resources, symbols, steps, constraints)

        # Assert
        assert "[ALTERNATIVE_FLOW: condition]" in spl_text
        assert "[ALTERNATIVE_FLOW: condition2]" in spl_text
        assert "[END_ALTERNATIVE_FLOW]" in spl_text

    def test_rendering_with_exception_flows(self) -> None:
        """Test rendering with exception flows."""
        # Arrange
        renderer = SPLRenderer()
        from nl2spl.ir.worker_ir import ExceptionFlowRef

        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            exception_flows=[
                ExceptionFlowRef("exc_1", "error", []),
            ],
        )
        profile = AgentProfileIR()
        resources = ResourceRegistryIR()
        symbols = SymbolTable()
        steps = []
        constraints = []

        # Act
        spl_text, _, _ = renderer.render(worker, profile, resources, symbols, steps, constraints)

        # Assert
        assert "[EXCEPTION_FLOW: error]" in spl_text
        assert "[END_EXCEPTION_FLOW]" in spl_text

    def test_empty_blocks_are_not_rendered(self) -> None:
        """Known partial flows stay visible without empty block wrappers."""
        renderer = SPLRenderer()
        from nl2spl.ir.worker_ir import ExceptionFlowRef

        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=MagicMock(
                blocks=[BlockIR("b_main_empty", "SEQUENTIAL", None, ["s1"])]
            ),
            exception_flows=[
                ExceptionFlowRef(
                    "exc_1",
                    "missing timeframe",
                    [BlockIR("b_exc_empty", "SEQUENTIAL", None, ["s2"])],
                ),
            ],
        )
        profile = AgentProfileIR()

        spl_text, _, _ = renderer.render(
            worker,
            profile,
            ResourceRegistryIR(),
            SymbolTable(),
            [],
            [],
        )

        assert "[EXCEPTION_FLOW: missing timeframe]" in spl_text
        assert "[END_EXCEPTION_FLOW]" in spl_text
        assert "[SEQUENTIAL_BLOCK]" not in spl_text
        assert "[END_SEQUENTIAL_BLOCK]" not in spl_text

    def test_rendering_with_multiple_aspects(self) -> None:
        """Test rendering with multiple persona aspects."""
        # Arrange
        renderer = SPLRenderer()
        worker = WorkerIR(worker_name="TestWorker", description="Test")
        profile = AgentProfileIR(
            persona=PersonaIR(
                role="Test Role",
                aspects=[
                    Aspect("Tone", "Professional"),
                    Aspect("Style", "Concise"),
                    Aspect("Format", "Clear"),
                ],
            )
        )
        resources = ResourceRegistryIR()
        symbols = SymbolTable()
        steps = []
        constraints = []

        # Act
        spl_text, _, _ = renderer.render(worker, profile, resources, symbols, steps, constraints)

        # Assert
        assert "Tone: Professional" in spl_text
        assert "Style: Concise" in spl_text
        assert "Format: Clear" in spl_text

    def test_rendering_with_optional_inputs_outputs(self) -> None:
        """Test rendering with optional inputs and outputs."""
        # Arrange
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            inputs=[
                WorkerInput("req_input", True),
                WorkerInput("opt_input", False),
            ],
            outputs=[
                WorkerOutput("req_output", True),
                WorkerOutput("opt_output", False),
            ],
        )
        profile = AgentProfileIR()
        resources = ResourceRegistryIR()
        symbols = SymbolTable()
        steps = []
        constraints = []

        # Act
        spl_text, _, _ = renderer.render(worker, profile, resources, symbols, steps, constraints)

        # Assert
        assert "REQUIRED <REF>req_input</REF>" in spl_text
        assert "OPTIONAL <REF>opt_input</REF>" in spl_text
        assert "REQUIRED <REF>req_output</REF>" in spl_text
        assert "OPTIONAL <REF>opt_output</REF>" in spl_text

    def test_rendering_empty_configuration(self) -> None:
        """Test rendering with empty configuration."""
        # Arrange
        renderer = SPLRenderer()
        worker = WorkerIR(worker_name="TestWorker", description="Test")
        profile = AgentProfileIR()
        resources = ResourceRegistryIR()
        symbols = SymbolTable()
        steps = []
        constraints = []

        # Act
        spl_text, errors, warnings = renderer.render(
            worker, profile, resources, symbols, steps, constraints
        )

        # Assert
        assert "[DEFINE_AGENT: TestWorker \"Test\"]" in spl_text
        assert "[END_AGENT]" in spl_text
        assert len(errors) == 0
        assert len(warnings) == 0

    def test_rendering_with_call_api_step(self) -> None:
        """Test rendering with CALL_API step."""
        # Arrange
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=MagicMock(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
        )
        profile = AgentProfileIR()
        resources = ResourceRegistryIR()
        symbols = SymbolTable()
        steps = [StepIR("st1", "API call", ["s1"], "CALL_API", integration_ref="api1")]
        constraints = []

        # Act
        spl_text, _, _ = renderer.render(worker, profile, resources, symbols, steps, constraints)

        # Assert
        assert "COMMAND-1 [CALL api1]" in spl_text

    def test_rendering_with_invoke_worker_step(self) -> None:
        """Test rendering with INVOKE_WORKER step."""
        # Arrange
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=MagicMock(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
        )
        profile = AgentProfileIR()
        resources = ResourceRegistryIR()
        symbols = SymbolTable()
        steps = [StepIR("st1", "Worker call", ["s1"], "INVOKE_WORKER", integration_ref="worker1")]
        constraints = []

        # Act
        spl_text, _, _ = renderer.render(worker, profile, resources, symbols, steps, constraints)

        # Assert
        assert "COMMAND-1 [INVOKE worker1]" in spl_text

    def test_rendering_with_concrete_child_worker_definition(self) -> None:
        """Test rendering concrete child worker definitions for invocations."""
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=MagicMock(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            child_worker_refs=["child_dc_1"],
            child_workers=[
                ChildWorkerIR(
                    worker_name="child_dc_1",
                    description="Source gathering can be delegated.",
                    task_text="Retrieve sources using approved source recipes",
                    inputs=[WorkerInput("available_connectors", True)],
                    outputs=[WorkerOutput("retrieved_sources", True)],
                )
            ],
        )
        profile = AgentProfileIR()
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("available_connectors", "List[text]", True, "Connectors", "input"),
                VariableSpec("retrieved_sources", "List[text]", True, "Sources", "step"),
            ]
        )
        symbols = SymbolTable()
        steps = [
            StepIR(
                "st1",
                "Retrieve sources using approved source recipes",
                ["s1"],
                "INVOKE_WORKER",
                inputs=["available_connectors"],
                outputs=["retrieved_sources"],
                integration_ref="child_dc_1",
            )
        ]

        spl_text, errors, _ = renderer.render(worker, profile, resources, symbols, steps, [])

        assert errors == []
        assert '[DEFINE_WORKER: "Source gathering can be delegated." child_dc_1]' in spl_text
        # Child worker has no blocks and no steps → empty MAIN_FLOW (no synthesis)
        assert "COMMAND-1 [INVOKE child_dc_1 WITH <REF>available_connectors</REF>" in spl_text
        # The child worker's task_text must NOT be rendered as a synthetic command
        assert "COMMAND-1 [COMMAND Retrieve sources" not in spl_text

    def test_unresolved_invoke_worker_reports_error(self) -> None:
        """Test unresolved worker invocation is not rendered as placeholder Worker."""
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=MagicMock(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
        )
        steps = [StepIR("st1", "Worker call", ["s1"], "INVOKE_WORKER")]

        spl_text, errors, _ = renderer.render(
            worker,
            AgentProfileIR(),
            ResourceRegistryIR(),
            SymbolTable(),
            steps,
            [],
        )

        assert any("no concrete worker target" in error for error in errors)
        assert "INVOKE Worker" not in spl_text
        assert "INVOKE <UNRESOLVED_WORKER>" in spl_text

    def test_rendering_with_step_inputs_outputs(self) -> None:
        """Test rendering with step inputs and outputs."""
        # Arrange
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=MagicMock(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
        )
        profile = AgentProfileIR()
        resources = ResourceRegistryIR()
        symbols = SymbolTable()
        steps = [
            StepIR(
                "st1",
                "Test step",
                ["s1"],
                "GENERAL_COMMAND",
                inputs=["input1"],
                outputs=["output1"],
            )
        ]
        constraints = []

        # Act
        spl_text, _, _ = renderer.render(worker, profile, resources, symbols, steps, constraints)

        # Assert
        assert (
            "COMMAND-1 [COMMAND Test step based on <REF>input1</REF> "
            "RESULT output1: text SET]"
        ) in spl_text

    def test_general_command_rejects_multiple_results(self) -> None:
        """GENERAL_COMMAND must be lowered before rendering multiple outputs."""
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=MagicMock(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
        )
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("summary", "text", True, "Summary", "step"),
                VariableSpec("score", "number", True, "Score", "step"),
            ]
        )
        steps = [
            StepIR(
                "st1",
                "Produce results",
                ["s1"],
                "GENERAL_COMMAND",
                outputs=["summary", "score"],
            )
        ]

        with pytest.raises(ValueError, match="Composite lowering must have run"):
            renderer.render(worker, AgentProfileIR(), resources, SymbolTable(), steps, [])

    def test_call_api_rejects_multiple_responses(self) -> None:
        """CALL_API must bind one structured response before rendering."""
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=MagicMock(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
        )
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("payload", "text", True, "Payload", "step"),
                VariableSpec("count", "number", True, "Count", "step"),
            ]
        )
        steps = [
            StepIR(
                "st1",
                "Call service",
                ["s1"],
                "CALL_API",
                outputs=["payload", "count"],
                integration_ref="SearchAPI",
            )
        ]

        with pytest.raises(ValueError, match="Composite lowering must have run"):
            renderer.render(worker, AgentProfileIR(), resources, SymbolTable(), steps, [])

    def test_invoke_worker_rejects_multiple_responses(self) -> None:
        """INVOKE_WORKER must bind one structured response before rendering."""
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            child_worker_refs=["ChildWorker"],
            main_flow=MagicMock(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
        )
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("draft", "text", True, "Draft", "step"),
                VariableSpec("status", "text", True, "Status", "step"),
            ]
        )
        steps = [
            StepIR(
                "st1",
                "Invoke child",
                ["s1"],
                "INVOKE_WORKER",
                outputs=["draft", "status"],
                integration_ref="ChildWorker",
            )
        ]

        with pytest.raises(ValueError, match="Composite lowering must have run"):
            renderer.render(worker, AgentProfileIR(), resources, SymbolTable(), steps, [])

    def test_request_input_rejects_multiple_values(self) -> None:
        """REQUEST_INPUT must bind one value target before rendering."""
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=MagicMock(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
        )
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("answer", "text", True, "Answer", "input"),
                VariableSpec("reason", "text", True, "Reason", "input"),
            ]
        )
        steps = [
            StepIR(
                "st1",
                "Ask for clarification",
                ["s1"],
                "REQUEST_INPUT",
                outputs=["answer", "reason"],
            )
        ]

        with pytest.raises(ValueError, match="Composite lowering must have run"):
            renderer.render(worker, AgentProfileIR(), resources, SymbolTable(), steps, [])

    def test_multiple_outputs_with_existing_refs_are_rejected(self) -> None:
        """Renderer must not mix refs and declarations in one result list."""
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            inputs=[WorkerInput("request", True)],
            main_flow=MagicMock(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1", "s2"])]),
        )
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("request", "text", True, "Request", "input"),
                VariableSpec("draft", "text", True, "Draft", "step"),
                VariableSpec("summary", "text", True, "Summary", "step"),
            ]
        )
        steps = [
            StepIR(
                "st1",
                "Create draft",
                ["s1"],
                "GENERAL_COMMAND",
                inputs=["request"],
                outputs=["draft"],
            ),
            StepIR(
                "st2",
                "Revise draft and summarize",
                ["s2"],
                "GENERAL_COMMAND",
                inputs=["draft"],
                outputs=["draft", "summary"],
            ),
        ]

        with pytest.raises(ValueError, match="Composite lowering must have run"):
            renderer.render(worker, AgentProfileIR(), resources, SymbolTable(), steps, [])

    def test_conditional_command_text_is_rewritten(self) -> None:
        """Test command text does not repeat an IF block condition."""
        # Arrange
        renderer = SPLRenderer()
        worker = WorkerIR(
            worker_name="TestWorker",
            description="Test",
            main_flow=MagicMock(
                blocks=[
                    BlockIR(
                        "b1",
                        "IF",
                        "When enough required information is available",
                        ["s1"],
                    )
                ]
            ),
        )
        profile = AgentProfileIR()
        resources = ResourceRegistryIR()
        symbols = SymbolTable()
        steps = [
            StepIR(
                "st1",
                "When enough required information is available, produce a draft.",
                ["s1"],
                "GENERAL_COMMAND",
                inputs=["user_request"],
                outputs=["draft"],
            )
        ]
        constraints = []

        # Act
        spl_text, _, _ = renderer.render(worker, profile, resources, symbols, steps, constraints)

        # Assert
        assert "DECISION-1 [IF enough required information is available]" in spl_text
        assert (
            "COMMAND-1 [COMMAND Produce a draft based on <REF>user_request</REF> "
            "RESULT draft: text SET]"
        ) in spl_text


# ===========================================================================
# D7: Renderer partial exception skeleton
# ===========================================================================


def test_d7_renderer_condition_only_exception_partial_skeleton() -> None:
    """D7: empty blocks render [EXCEPTION_FLOW] with condition, no synthetic command."""
    from nl2spl.ir.worker_ir import ExceptionFlowRef, FlowRef

    worker = WorkerIR(
        worker_name="MainWorker",
        description="Test.",
        steps=[StepIR("st1", "Main work", ["s_main"], "GENERAL_COMMAND")],
        inputs=[WorkerInput("in", required=True)],
        outputs=[WorkerOutput("out", required=True)],
        main_flow=FlowRef(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s_main"])]),
        exception_flows=[
            ExceptionFlowRef(
                flow_id="exc_adapter_00",
                condition_text="Missing timeframe.",
                blocks=[],
            ),
        ],
    )
    profile = AgentProfileIR(persona=PersonaIR(role="Assistant"))
    resources = ResourceRegistryIR()
    symbols = SymbolTable()
    steps = [StepIR("st1", "Main work", ["s_main"], "GENERAL_COMMAND")]
    constraints: list[ConstraintIR] = []

    renderer = SPLRenderer()
    spl_text, _, _ = renderer.render(worker, profile, resources, symbols, steps, constraints)

    assert "[EXCEPTION_FLOW: Missing timeframe]" in spl_text
    assert "[END_EXCEPTION_FLOW]" in spl_text
    # No synthetic handler command between EXCEPTION_FLOW and END_EXCEPTION_FLOW
    exc_section = spl_text.split("[EXCEPTION_FLOW:")[1].split("[END_EXCEPTION_FLOW]")[0]
    assert "COMMAND" not in exc_section, (
        f"No synthetic handler command between EXCEPTION_FLOW brackets: {exc_section}"
    )


def test_d7_renderer_child_worker_partial_exception() -> None:
    """D7: child worker partial exception skeleton renders under child worker."""
    from nl2spl.ir.worker_ir import ChildWorkerIR, ExceptionFlowRef, FlowRef

    child = ChildWorkerIR(
        worker_name="ChildWorker",
        description="Child.",
        task_text="Delegate task.",
        steps=[StepIR("st_child", "Child work", ["s_child"], "GENERAL_COMMAND")],
        main_flow=FlowRef(blocks=[BlockIR("b_c", "SEQUENTIAL", None, ["s_child"])]),
        exception_flows=[
            ExceptionFlowRef(
                flow_id="exc_adapter_01",
                condition_text="Evidence shortage.",
                blocks=[],
                spans=["s_fail2"],
            ),
        ],
    )
    worker = WorkerIR(
        worker_name="MainWorker",
        description="Test.",
        steps=[StepIR("st1", "Main work", ["s_main"], "GENERAL_COMMAND")],
        main_flow=FlowRef(blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s_main"])]),
        child_workers=[child],
    )

    renderer = SPLRenderer()
    spl_text, _, _ = renderer.render(
        worker,
        AgentProfileIR(persona=PersonaIR(role="Assistant")),
        ResourceRegistryIR(), SymbolTable(),
        [StepIR("st1", "Main", ["s_main"], "GENERAL_COMMAND")],
        [],
    )

    assert "[EXCEPTION_FLOW: Evidence shortage]" in spl_text
    assert "[END_EXCEPTION_FLOW]" in spl_text
    assert "ChildWorker" in spl_text
    # No synthetic COMMAND in child exception either
    exc_section = spl_text.split("[EXCEPTION_FLOW: Evidence shortage]")[1]
    exc_section = exc_section.split("[END_EXCEPTION_FLOW]")[0]
    assert "COMMAND" not in exc_section
