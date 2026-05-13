"""Unit tests for WorkerStepPlanIR."""

from __future__ import annotations

from nl2spl.ir import StepIR, WorkerStepPlanIR


def step(step_id: str, text: str = "do something", span_ids: list[str] | None = None) -> StepIR:
    """Helper to create a StepIR."""
    return StepIR(
        step_id=step_id,
        text=text,
        source_span_ids=span_ids or [],
        command_type="GENERAL_COMMAND",
    )


def test_construct_empty_worker_step_plan() -> None:
    """Test constructing an empty WorkerStepPlanIR."""
    plan = WorkerStepPlanIR(main_worker_id="worker_main")

    assert plan.main_worker_id == "worker_main"
    assert plan.worker_steps == {}
    assert plan.warnings == []
    assert plan.main_worker_steps == []
    assert plan.get_all_steps() == []


def test_construct_with_worker_steps() -> None:
    """Test constructing WorkerStepPlanIR with worker steps."""
    main_steps = [step("st1", "step 1"), step("st2", "step 2")]
    child_steps = [step("st3", "step 3")]

    plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": main_steps,
            "worker_child": child_steps,
        },
    )

    assert plan.main_worker_id == "worker_main"
    assert len(plan.worker_steps) == 2
    assert len(plan.worker_steps["worker_main"]) == 2
    assert len(plan.worker_steps["worker_child"]) == 1


def test_main_worker_steps_property() -> None:
    """Test main_worker_steps property returns correct steps."""
    main_steps = [step("st1", "step 1"), step("st2", "step 2")]
    child_steps = [step("st3", "step 3")]

    plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": main_steps,
            "worker_child": child_steps,
        },
    )

    assert plan.main_worker_steps == main_steps


def test_main_worker_steps_property_empty_when_no_main() -> None:
    """Test main_worker_steps property returns empty list when main worker has no steps."""
    child_steps = [step("st3", "step 3")]

    plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_child": child_steps,
        },
    )

    assert plan.main_worker_steps == []


def test_get_all_steps() -> None:
    """Test get_all_steps returns all steps across all workers."""
    main_steps = [step("st1", "step 1"), step("st2", "step 2")]
    child_steps = [step("st3", "step 3")]

    plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": main_steps,
            "worker_child": child_steps,
        },
    )

    all_steps = plan.get_all_steps()
    assert len(all_steps) == 3
    assert all_steps == main_steps + child_steps


def test_get_all_steps_empty() -> None:
    """Test get_all_steps returns empty list when no workers have steps."""
    plan = WorkerStepPlanIR(main_worker_id="worker_main")

    assert plan.get_all_steps() == []


def test_warnings_field() -> None:
    """Test warnings field."""
    warnings = ["Warning 1", "Warning 2"]

    plan = WorkerStepPlanIR(
        main_worker_id="worker_main",
        warnings=warnings,
    )

    assert plan.warnings == warnings


def test_worker_steps_default_factory() -> None:
    """Test worker_steps uses default factory."""
    plan1 = WorkerStepPlanIR(main_worker_id="worker_main")
    plan2 = WorkerStepPlanIR(main_worker_id="worker_main")

    # Ensure each instance has its own dict
    plan1.worker_steps["worker_main"] = [step("st1")]

    assert "worker_main" not in plan2.worker_steps


def test_warnings_default_factory() -> None:
    """Test warnings uses default factory."""
    plan1 = WorkerStepPlanIR(main_worker_id="worker_main")
    plan2 = WorkerStepPlanIR(main_worker_id="worker_main")

    # Ensure each instance has its own list
    plan1.warnings.append("warning")

    assert len(plan2.warnings) == 0
