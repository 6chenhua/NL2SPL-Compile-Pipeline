# -*- coding: utf-8 -*-
"""
Unit tests for renderer fail-closed validation of multi-output steps.
"""

from __future__ import annotations

import pytest
from nl2spl.ir import (
    StepIR,
    ResourceRegistryIR,
    SymbolTable,
    WorkerIR,
    TypeSpec,
    BlockIR,
    FlowRef,
    VariableSpec,
)
from nl2spl.ir.agent_profile_ir import AgentProfileIR, PersonaIR
from nl2spl.pipeline.stages.stage11_spl_renderer.renderer import SPLRenderer


def _setup_renderer_args(step: StepIR, types: list[TypeSpec] | None = None) -> tuple:
    step.block_ref = "b1"
    
    worker = WorkerIR(
        worker_name="MainWorker",
        description="Main worker",
        steps=[step],
        main_flow=FlowRef(blocks=[
            BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s20"])
        ]),
        child_worker_refs=["ChildWorker"],
    )
    profile = AgentProfileIR(
        persona=PersonaIR(role="Assistant", aspects=[]),
        audience_aspects=[],
        concepts=[],
    )
    resources = ResourceRegistryIR()
    # Add a variable to ensure [DEFINE_VARIABLES:] is rendered
    resources.variables.append(
        VariableSpec(
            name="record",
            data_type="text",
            required=True,
            description="Record variable",
            source="output",
        )
    )
    if types:
        resources.types.extend(types)
    symbol_table = SymbolTable()
    return worker, profile, resources, symbol_table, [step], []


def test_renderer_fails_on_multi_output_general_command() -> None:
    step = StepIR(
        step_id="st7",
        text="Record assumptions and completion status",
        command_type="GENERAL_COMMAND",
        source_span_ids=["s20"],
        outputs=["a", "b"],
    )
    worker, profile, resources, symbol_table, steps, constraints = _setup_renderer_args(step)
    renderer = SPLRenderer()
    with pytest.raises(ValueError, match="Renderer invariant violated"):
        renderer.render(worker, profile, resources, symbol_table, steps, constraints)


def test_renderer_fails_on_multi_output_call_api() -> None:
    step = StepIR(
        step_id="st7",
        text="CALL SearchAPI",
        command_type="CALL_API",
        integration_ref="SearchAPI",
        source_span_ids=["s20"],
        outputs=["a", "b"],
    )
    worker, profile, resources, symbol_table, steps, constraints = _setup_renderer_args(step)
    renderer = SPLRenderer()
    with pytest.raises(ValueError, match="Renderer invariant violated"):
        renderer.render(worker, profile, resources, symbol_table, steps, constraints)


def test_renderer_fails_on_multi_output_invoke_worker() -> None:
    step = StepIR(
        step_id="st7",
        text="INVOKE ChildWorker",
        command_type="INVOKE_WORKER",
        integration_ref="ChildWorker",
        handoff_id="h1",
        source_span_ids=["s20"],
        outputs=["a", "b"],
    )
    worker, profile, resources, symbol_table, steps, constraints = _setup_renderer_args(step)
    renderer = SPLRenderer()
    with pytest.raises(ValueError, match="Renderer invariant violated"):
        renderer.render(worker, profile, resources, symbol_table, steps, constraints)


def test_renderer_fails_on_multi_output_request_input() -> None:
    step = StepIR(
        step_id="st7",
        text="Ask user for confirmation",
        command_type="REQUEST_INPUT",
        source_span_ids=["s20"],
        outputs=["a", "b"],
    )
    worker, profile, resources, symbol_table, steps, constraints = _setup_renderer_args(step)
    renderer = SPLRenderer()
    with pytest.raises(ValueError, match="Renderer invariant violated"):
        renderer.render(worker, profile, resources, symbol_table, steps, constraints)


def test_renderer_renders_define_types_before_define_variables() -> None:
    step = StepIR(
        step_id="st7",
        text="Record assumptions",
        command_type="GENERAL_COMMAND",
        source_span_ids=["s20"],
        outputs=["record"],
    )
    types = [
        TypeSpec(
            type_name="RunRecord",
            type_kind="structured",
            definition={"field1": "text"},
        )
    ]
    worker, profile, resources, symbol_table, steps, constraints = _setup_renderer_args(step, types)
    renderer = SPLRenderer()
    spl_text, errors, warnings = renderer.render(worker, profile, resources, symbol_table, steps, constraints)
    
    assert not errors
    assert "[DEFINE_TYPES:]" in spl_text
    assert "[DEFINE_VARIABLES:]" in spl_text
    
    types_pos = spl_text.index("[DEFINE_TYPES:]")
    vars_pos = spl_text.index("[DEFINE_VARIABLES:]")
    assert types_pos < vars_pos


def test_renderer_single_output_success() -> None:
    step = StepIR(
        step_id="st7",
        text="Record assumptions",
        command_type="GENERAL_COMMAND",
        source_span_ids=["s20"],
        outputs=["record"],
    )
    worker, profile, resources, symbol_table, steps, constraints = _setup_renderer_args(step)
    renderer = SPLRenderer()
    spl_text, errors, warnings = renderer.render(worker, profile, resources, symbol_table, steps, constraints)
    assert not errors
    assert "RESULT record: text SET" in spl_text
