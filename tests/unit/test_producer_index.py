"""Unit tests for ProducerIndex (Phase 2)."""

from __future__ import annotations

from nl2spl.compiler.producer_index import ProducerIndex, ProducerRef, _step_is_renderable
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR
from nl2spl.pipeline.resource_declaration_gate import ResourceDeclarationGate
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import (
    InputBindingIR,
    OutputBindingIR,
    WorkerHandoffIR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _invoke_handoff(
    handoff_id: str,
    to_worker: str | None = "w_child",
    output_var: str = "result",
    input_var: str = "req",
    *,
    no_inputs: bool = False,
    no_outputs: bool = False,
) -> WorkerHandoffIR:
    return WorkerHandoffIR(
        handoff_id=handoff_id,
        from_worker="w_main",
        to_worker=to_worker,
        api_ref=None,
        mode="invoke",
        condition_text=None,
        ordering="after",
        input_bindings=[] if no_inputs else [
            InputBindingIR(input_var, "child_in", True),
        ],
        output_bindings=[] if no_outputs else [
            OutputBindingIR("child_out", output_var, True, "set"),
        ],
    )


def _api_call_handoff(
    handoff_id: str,
    api_ref: str | None = "SearchAPI",
    output_var: str = "results",
) -> WorkerHandoffIR:
    return WorkerHandoffIR(
        handoff_id=handoff_id,
        from_worker="w_main",
        to_worker=None,
        api_ref=api_ref,
        mode="api_call",
        condition_text=None,
        ordering="after",
        output_bindings=[OutputBindingIR("api_out", output_var, True, "set")],
    )


# ---------------------------------------------------------------------------
# ProducerRef
# ---------------------------------------------------------------------------

class TestProducerRef:
    def test_default_renderable_false(self) -> None:
        ref = ProducerRef("v", "step", "st1")
        assert ref.renderable is False

    def test_source_backed(self) -> None:
        ref = ProducerRef("v", "step", "st1", source_span_ids=["s1"], renderable=True)
        assert ref.renderable is True

    def test_producer_kind_handoff(self) -> None:
        ref = ProducerRef("r", "handoff", "h1", renderable=True)
        assert ref.producer_kind == "handoff"


# ---------------------------------------------------------------------------
# _step_is_renderable
# ---------------------------------------------------------------------------

class TestStepRenderable:
    def test_source_spans_always_renderable(self) -> None:
        assert _step_is_renderable(StepIR("st1", "W", ["s1"], "GENERAL_COMMAND"))

    def test_handoff_exists_mode_matches_is_renderable(self) -> None:
        step = StepIR("st1", "Inv", [], "INVOKE_WORKER", handoff_id="h1")
        assert _step_is_renderable(step, {"h1": _invoke_handoff("h1")})

    def test_handoff_not_in_index_not_renderable(self) -> None:
        step = StepIR("st1", "Inv", [], "INVOKE_WORKER", handoff_id="fake")
        assert not _step_is_renderable(step, {"h": _invoke_handoff("h")})

    def test_handoff_id_without_index_not_renderable(self) -> None:
        assert not _step_is_renderable(
            StepIR("st1", "X", [], "INVOKE_WORKER", handoff_id="h1"), None
        )

    def test_invoke_with_api_call_handoff_mode_blocked(self) -> None:
        step = StepIR("st1", "Inv", [], "INVOKE_WORKER", handoff_id="h1")
        assert not _step_is_renderable(step, {"h1": _api_call_handoff("h1")})

    def test_call_api_with_invoke_handoff_mode_blocked(self) -> None:
        step = StepIR("st1", "Call", [], "CALL_API", handoff_id="h1")
        assert not _step_is_renderable(step, {"h1": _invoke_handoff("h1")})

    def test_compiler_unpack_renderable(self) -> None:
        assert _step_is_renderable(
            StepIR("st_u", "E", [], "GENERAL_COMMAND",
                   metadata={"origin": "compiler_unpack"})
        )

    def test_empty_no_handoff_not_renderable(self) -> None:
        assert not _step_is_renderable(
            StepIR("st_synth", "S", [], "GENERAL_COMMAND")
        )

    def test_user_confirmed_repair_renderable(self) -> None:
        """User-confirmed repair step is renderable."""
        assert _step_is_renderable(
            StepIR("st_ucr", "User confirmed", [], "GENERAL_COMMAND",
                   metadata={"origin": "user_confirmed_repair"})
        )

    def test_user_confirmed_repair_with_outputs_renderable(self) -> None:
        """UCR step with outputs is renderable for producer indexing."""
        assert _step_is_renderable(
            StepIR("st_ucr", "Ask user", [], "REQUEST_INPUT",
                   outputs=["answer"],
                   metadata={"origin": "user_confirmed_repair"})
        )

    def test_unconfirmed_no_source_not_renderable(self) -> None:
        """Unconfirmed no-source step is NOT renderable."""
        assert not _step_is_renderable(
            StepIR("st_assumed", "Maybe do", [], "GENERAL_COMMAND")
        )


# ---------------------------------------------------------------------------
# Step producers (handoff-backed steps are excluded)
# ---------------------------------------------------------------------------

class TestStepProducers:
    def test_source_backed_step_produces(self) -> None:
        steps = [StepIR("st1", "W", ["s1"], "GENERAL_COMMAND", outputs=["draft"])]
        index = ProducerIndex(steps=steps)
        assert index.is_produced("draft")

    def test_synthetic_step_not_renderable(self) -> None:
        steps = [StepIR("st_s", "W", [], "GENERAL_COMMAND", outputs=["draft"])]
        index = ProducerIndex(steps=steps)
        assert not index.is_produced("draft")

    def test_compiler_unpack_is_renderable(self) -> None:
        steps = [StepIR("st_u", "E", [], "GENERAL_COMMAND",
                        outputs=["f"], metadata={"origin": "compiler_unpack"})]
        index = ProducerIndex(steps=steps)
        assert index.is_produced("f")

    def test_handoff_backed_step_excluded_from_section_1(self) -> None:
        """P1: step with handoff_id must NOT produce via step.outputs.
        Only handoff.output_bindings (section 2) are trusted."""
        h = _invoke_handoff("h1", output_var="real_result")
        steps = [
            StepIR("st_invoke", "Invoke child", [], "INVOKE_WORKER",
                   handoff_id="h1", outputs=["wrong_output"])
        ]
        index = ProducerIndex(steps=steps, handoffs=[h])
        # "wrong_output" is NOT produced because:
        # - Section 1 skips handoff-backed steps
        # - Section 2 handoff binds "real_result", not "wrong_output"
        assert not index.is_produced("wrong_output")
        # "real_result" IS produced by handoff binding
        assert index.is_produced("real_result")


# ---------------------------------------------------------------------------
# P1 #1: handoff step outputs mismatch handoff bindings
# ---------------------------------------------------------------------------

class TestP1HandoffStepOutputMismatch:
    """Gate requires step.outputs == handoff output_bindings exactly.
    ProducerIndex must not trust step.outputs when handoff is involved."""

    def test_step_output_different_from_binding_not_produced(self) -> None:
        h = _invoke_handoff("h1", output_var="correct_output")
        steps = [
            StepIR("st1", "Invoke", [], "INVOKE_WORKER",
                   handoff_id="h1", outputs=["wrong_output"])
        ]
        index = ProducerIndex(steps=steps, handoffs=[h])
        # Gate would block this step → wrong_output must not be considered produced
        assert not index.is_produced("wrong_output")

    def test_step_output_matching_binding_is_produced_by_handoff_section(self) -> None:
        h = _invoke_handoff("h1", output_var="final_report")
        steps = [
            StepIR("st1", "Invoke", [], "INVOKE_WORKER",
                   handoff_id="h1", outputs=["final_report"])
        ]
        index = ProducerIndex(steps=steps, handoffs=[h])
        # Step output is skipped (section 1), but handoff binding (section 2)
        # produces "final_report" → still produced via the binding
        assert index.is_produced("final_report")

    def test_structured_handoff_result_is_produced_when_metadata_matches(self) -> None:
        h = WorkerHandoffIR(
            "h1",
            "w_main",
            "w_child",
            None,
            "invoke",
            None,
            "after",
            input_bindings=[InputBindingIR("req", "child_in", True)],
            output_bindings=[
                OutputBindingIR("child_one", "out_one", True, "set"),
                OutputBindingIR("child_two", "out_two", True, "set"),
            ],
        )
        steps = [
            StepIR(
                "st1",
                "Invoke",
                [],
                "INVOKE_WORKER",
                handoff_id="h1",
                outputs=["h1_response_structured"],
                metadata={
                    "structured_aggregation": {
                        "result_name": "h1_response_structured",
                        "original_outputs": ["out_one", "out_two"],
                        "type_name": "h1_response_structured_type",
                    }
                },
            )
        ]
        index = ProducerIndex(
            steps=steps,
            handoffs=[h],
            known_child_worker_ids={"w_child"},
        )

        assert index.is_produced("h1_response_structured")


# ---------------------------------------------------------------------------
# P1 #2: handoff renderability — main worker excluded, IO required
# ---------------------------------------------------------------------------

class TestP1HandoffRenderability:
    """Handoff renderability mirrors gate: child worker, IO bindings present."""

    def test_main_worker_target_excluded(self) -> None:
        """invoke handoff to main worker → not renderable."""
        h = _invoke_handoff("h1", to_worker="w_main", output_var="r")
        index = ProducerIndex(
            steps=[], handoffs=[h],
            known_child_worker_ids={"w_child"},
        )
        assert not index.is_produced("r")

    def test_child_worker_target_allowed(self) -> None:
        h = _invoke_handoff("h1", to_worker="w_child", output_var="r")
        index = ProducerIndex(
            steps=[], handoffs=[h],
            known_child_worker_ids={"w_child"},
        )
        assert index.is_produced("r")

    def test_no_input_bindings_not_renderable(self) -> None:
        h = _invoke_handoff("h1", no_inputs=True, output_var="r")
        index = ProducerIndex(
            steps=[], handoffs=[h],
            known_child_worker_ids={"w_child"},
        )
        assert not index.is_produced("r")

    def test_no_output_bindings_not_renderable(self) -> None:
        h = _invoke_handoff("h1", no_outputs=True, output_var="r")
        index = ProducerIndex(
            steps=[], handoffs=[h],
            known_child_worker_ids={"w_child"},
        )
        assert not index.is_produced("r")

    def test_both_io_bindings_present_is_renderable(self) -> None:
        h = _invoke_handoff("h1", output_var="r")  # has both input and output
        index = ProducerIndex(
            steps=[], handoffs=[h],
            known_child_worker_ids={"w_child"},
        )
        assert index.is_produced("r")

    def test_no_child_ids_falls_back_to_to_worker_check_only(self) -> None:
        h = _invoke_handoff("h1", to_worker="any_target", output_var="r")
        index = ProducerIndex(steps=[], handoffs=[h])
        # No known_child_worker_ids → only to_worker non-None + IO exist check
        assert index.is_produced("r")

    def test_child_to_main_handoff_blocked(self) -> None:
        """P2: child worker invokes main worker → handoff is NOT renderable.

        When the caller is a child worker and the handoff targets the main
        worker, the main worker must be excluded from known_child_worker_ids.
        Otherwise a child→main handoff output binding would mask
        missing_output_producer on the child's required output.
        """
        # Simulate child_ids as computed by worker_scoped: main excluded
        child_ids = {"w_child_2"}  # main worker "w_main" NOT in this set
        h = _invoke_handoff("h1", to_worker="w_main", output_var="r")
        index = ProducerIndex(
            steps=[], handoffs=[h],
            known_child_worker_ids=child_ids,
        )
        assert not index.is_produced("r")


# ---------------------------------------------------------------------------
# P1 #3: CALL_API handoff-backed — no global fallback
# ---------------------------------------------------------------------------

class TestP1CallApiHandoffFallback:
    """When a CALL_API step has handoff_id, api_ref MUST come from the handoff."""

    def test_handoff_with_matching_api_ref_is_declared(self) -> None:
        h = _api_call_handoff("h1", api_ref="SearchAPI")
        steps = [
            StepIR("st_api", "Call", [], "CALL_API",
                   integration_ref="SearchAPI", outputs=["results"],
                   handoff_id="h1")
        ]
        index = ProducerIndex(
            steps=steps, handoffs=[h],
            api_handoff_refs={"h1": "SearchAPI"},
        )
        assert index.is_produced("results")

    def test_handoff_without_api_ref_no_global_fallback(self) -> None:
        """CALL_API step has handoff_id but handoff has no api_ref.
        Must NOT fall back to global declared_apis."""
        h = _api_call_handoff("h1", api_ref=None)
        steps = [
            StepIR("st_api", "Call", [], "CALL_API",
                   integration_ref="SearchAPI", outputs=["results"],
                   handoff_id="h1")
        ]
        index = ProducerIndex(
            steps=steps, handoffs=[h],
            declared_apis={"SearchAPI"},
            api_handoff_refs={},  # no api_ref from handoff
        )
        assert not index.is_produced("results")

    def test_handoff_with_wrong_api_ref_blocked(self) -> None:
        h = _api_call_handoff("h1", api_ref="CorrectAPI")
        steps = [
            StepIR("st_api", "Call", [], "CALL_API",
                   integration_ref="WrongAPI", outputs=["results"],
                   handoff_id="h1")
        ]
        index = ProducerIndex(steps=steps, handoffs=[h])
        assert not index.is_produced("results")

    def test_handoff_missing_from_index_blocked(self) -> None:
        """CALL_API step has handoff_id but handoff doesn't exist."""
        steps = [
            StepIR("st_api", "Call", [], "CALL_API",
                   integration_ref="SearchAPI", outputs=["results"],
                   handoff_id="ghost")
        ]
        index = ProducerIndex(steps=steps, handoffs=[], declared_apis={"SearchAPI"})
        assert not index.is_produced("results")

    def test_call_api_no_handoff_uses_global_declared(self) -> None:
        """Without handoff_id, global declared_apis is fine."""
        steps = [
            StepIR("st_api", "Call", ["s1"], "CALL_API",
                   integration_ref="SearchAPI", outputs=["results"])
        ]
        index = ProducerIndex(steps=steps, declared_apis={"SearchAPI"})
        assert index.is_produced("results")


# ---------------------------------------------------------------------------
# Handoff output bindings
# ---------------------------------------------------------------------------

class TestHandoffProducers:
    def test_valid_invoke_handoff_output(self) -> None:
        h = _invoke_handoff("h1", output_var="result")
        index = ProducerIndex(steps=[], handoffs=[h])
        assert index.is_produced("result")

    def test_invoke_handoff_no_to_worker_not_renderable(self) -> None:
        h = _invoke_handoff("h1", to_worker=None, output_var="r")
        index = ProducerIndex(steps=[], handoffs=[h])
        assert not index.is_produced("r")

    def test_api_call_handoff_valid_api_ref(self) -> None:
        h = _api_call_handoff("h1", "SearchAPI")
        index = ProducerIndex(steps=[], handoffs=[h], declared_apis={"SearchAPI"})
        assert index.is_produced("results")

    def test_api_call_handoff_no_api_ref_not_renderable(self) -> None:
        h = _api_call_handoff("h1", None)
        index = ProducerIndex(steps=[], handoffs=[h])
        assert not index.is_produced("results")


# ---------------------------------------------------------------------------
# CALL_API steps (no handoff)
# ---------------------------------------------------------------------------

class TestCallApiProducers:
    def test_declared_ref_is_producer(self) -> None:
        steps = [
            StepIR("st_api", "Call", ["s_api"], "CALL_API",
                   integration_ref="SearchAPI", outputs=["results"])
        ]
        index = ProducerIndex(steps=steps, declared_apis={"SearchAPI"})
        assert index.is_produced("results")

    def test_no_integration_ref_not_producer(self) -> None:
        steps = [StepIR("st_api", "Call", [], "CALL_API", outputs=["r"])]
        index = ProducerIndex(steps=steps)
        assert not index.is_produced("r")

    def test_undeclared_ref_not_producer(self) -> None:
        steps = [
            StepIR("st_api", "Call", [], "CALL_API",
                   integration_ref="GhostAPI", outputs=["r"])
        ]
        index = ProducerIndex(steps=steps, declared_apis={"SearchAPI"})
        assert not index.is_produced("r")

    def test_extra_api_names_do_not_authorize_direct_call_api(self) -> None:
        steps = [
            StepIR("st_api", "Call", ["s1"], "CALL_API",
                   integration_ref="ExtraAPI", outputs=["d"])
        ]
        index = ProducerIndex(steps=steps, extra_api_names={"ExtraAPI"})
        assert not index.is_produced("d")

    def test_handoff_api_ref_authorizes_matching_handoff_call_api(self) -> None:
        handoff = _api_call_handoff("h_extra", api_ref="ExtraAPI")
        steps = [
            StepIR(
                "st_api",
                "Call",
                [],
                "CALL_API",
                integration_ref="ExtraAPI",
                outputs=["d"],
                handoff_id="h_extra",
            )
        ]
        index = ProducerIndex(steps=steps, handoffs=[handoff])
        assert index.is_produced("d")

    def test_call_api_no_double_record(self) -> None:
        """P2: CALL_API only produces api-kind entries, never step-kind."""
        steps = [
            StepIR("st_api", "Call", ["s_api"], "CALL_API",
                   integration_ref="SearchAPI", outputs=["r"])
        ]
        index = ProducerIndex(steps=steps, declared_apis={"SearchAPI"})
        refs = index.get_producers("r")
        assert len(refs) == 1
        assert refs[0].producer_kind == "api"

    def test_raw_resource_registry_api_without_gate_view_not_producer(self) -> None:
        raw_resources = ResourceRegistryIR(
            apis=[APISpec("SearchAPI", "none", "Search API")]
        )
        gate_view = ResourceDeclarationGate().apply(raw_resources, [])
        steps = [
            StepIR(
                "st_api",
                "Call",
                ["s_api"],
                "CALL_API",
                integration_ref="SearchAPI",
                outputs=["results"],
            )
        ]

        index = ProducerIndex(steps=steps, declared_apis=gate_view.api_names)

        assert raw_resources.get_api_names() == {"SearchAPI"}
        assert gate_view.api_names == set()
        assert not index.is_produced("results")


# ---------------------------------------------------------------------------
# find_unproduced / all_produced_variables
# ---------------------------------------------------------------------------

class TestFindUnproduced:
    def test_all_produced(self) -> None:
        steps = [StepIR("st1", "W", ["s1"], "GENERAL_COMMAND", outputs=["o1"])]
        index = ProducerIndex(steps=steps)
        assert index.find_unproduced(["o1"]) == []

    def test_none_produced(self) -> None:
        index = ProducerIndex()
        assert index.find_unproduced(["m1", "m2"]) == ["m1", "m2"]

    def test_partial(self) -> None:
        steps = [StepIR("st1", "W", ["s1"], "GENERAL_COMMAND", outputs=["o1"])]
        index = ProducerIndex(steps=steps)
        assert index.find_unproduced(["o1", "missing"]) == ["missing"]


class TestAllProducedVariables:
    def test_returns_set(self) -> None:
        steps = [
            StepIR("st1", "A", ["s1"], "GENERAL_COMMAND", outputs=["a"]),
            StepIR("st_s", "B", [], "GENERAL_COMMAND", outputs=["b"]),
            StepIR("st2", "C", ["s2"], "GENERAL_COMMAND", outputs=["c"]),
        ]
        index = ProducerIndex(steps=steps)
        assert index.all_produced_variables() == {"a", "c"}


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------

class TestAcceptanceCriteria:
    def test_ac1_required_output_without_producer_unproduced(self) -> None:
        index = ProducerIndex()
        assert not index.is_produced("final_report")
        assert "final_report" in index.find_unproduced(["final_report"])

    def test_ac2_blocked_assumed_step_not_producer(self) -> None:
        steps = [
            StepIR("st_synth", "X", [], "GENERAL_COMMAND", outputs=["final_report"])
        ]
        index = ProducerIndex(steps=steps)
        assert not index.is_produced("final_report")

    def test_ac3_valid_child_worker_handoff_output_is_producer(self) -> None:
        h = _invoke_handoff("h_invoke", output_var="final_report")
        index = ProducerIndex(steps=[], handoffs=[h])
        assert index.is_produced("final_report")

    def test_ac4_worker_outputs_declaration_does_not_suppress(self) -> None:
        index = ProducerIndex()
        assert not index.is_produced("declared_output")
        assert "declared_output" in index.find_unproduced(["declared_output"])

    def test_ac5_source_backed_step_is_valid(self) -> None:
        steps = [
            StepIR("st1", "Generate", ["s5"], "GENERAL_COMMAND",
                   outputs=["final_report"])
        ]
        index = ProducerIndex(steps=steps)
        assert index.is_produced("final_report")

    def test_ac6_handoff_step_output_produced_via_binding(self) -> None:
        """Handoff-backed step output produced by binding (section 2), not step outputs."""
        h = _invoke_handoff("h1", output_var="result")
        steps = [
            StepIR("st_invoke", "Invoke", [], "INVOKE_WORKER",
                   handoff_id="h1", outputs=["result"])
        ]
        index = ProducerIndex(steps=steps, handoffs=[h])
        assert index.is_produced("result")

    def test_ac7_compiler_unpack_is_valid(self) -> None:
        steps = [
            StepIR("st_u", "Extract", [], "GENERAL_COMMAND",
                   outputs=["f"], metadata={"origin": "compiler_unpack"})
        ]
        index = ProducerIndex(steps=steps)
        assert index.is_produced("f")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_index(self) -> None:
        index = ProducerIndex()
        assert index.all_produced_variables() == set()

    def test_multiple_outputs_per_step(self) -> None:
        steps = [StepIR("st1", "M", ["s1"], "GENERAL_COMMAND", outputs=["a", "b", "c"])]
        index = ProducerIndex(steps=steps)
        assert index.all_produced_variables() == {"a", "b", "c"}

    def test_handoff_without_output_bindings(self) -> None:
        h = _invoke_handoff("h_e", no_outputs=True, output_var="r")
        index = ProducerIndex(steps=[], handoffs=[h])
        assert index.all_produced_variables() == set()

    def test_handoff_with_multiple_outputs(self) -> None:
        h = WorkerHandoffIR(
            handoff_id="h_m", from_worker="w_main",
            to_worker="w_child", api_ref=None, mode="invoke",
            condition_text=None, ordering="after",
            input_bindings=[InputBindingIR("x", "y", True)],
            output_bindings=[
                OutputBindingIR("c1", "p1", True, "set"),
                OutputBindingIR("c2", "p2", True, "append"),
            ],
        )
        index = ProducerIndex(steps=[], handoffs=[h])
        assert index.all_produced_variables() == {"p1", "p2"}

    def test_handoff_step_with_multiple_outputs_uses_bindings(self) -> None:
        h = WorkerHandoffIR(
            handoff_id="h_m",
            from_worker="w_main",
            to_worker="w_child",
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=[InputBindingIR("x", "y", True)],
            output_bindings=[
                OutputBindingIR("c1", "p1", True, "set"),
                OutputBindingIR("c2", "p2", True, "set"),
            ],
        )
        steps = [
            StepIR(
                "st_invoke",
                "Invoke",
                [],
                "INVOKE_WORKER",
                handoff_id="h_m",
                outputs=["p1", "p2"],
            )
        ]
        index = ProducerIndex(steps=steps, handoffs=[h])
        assert index.all_produced_variables() == {"p1", "p2"}

    def test_default_factory_lists_not_shared(self) -> None:
        r1 = ProducerRef("a", "step", "st1")
        r2 = ProducerRef("b", "step", "st2")
        r1.source_span_ids.append("s1")
        assert r2.source_span_ids == []

    def test_producer_ref_file_resource_kind(self) -> None:
        """ProducerRef can carry resource_kind=file."""
        ref = ProducerRef(
            "finished_draft", "step", "st_draft",
            source_span_ids=["s14"],
            renderable=True,
            resource_kind="file",
        )
        assert ref.resource_kind == "file"
        assert ref.variable_name == "finished_draft"

    def test_is_produced_with_resource_kind_filter(self) -> None:
        """is_produced with resource_kind filter only counts matching kinds."""
        step = StepIR(
            step_id="st1",
            text="Draft document",
            source_span_ids=["s14"],
            command_type="GENERAL_COMMAND",
            inputs=[],
            outputs=["finished_draft"],
            kind="normal",
        )
        index = ProducerIndex(steps=[step])
        # Without filter: variable kind default → no match for file filtering
        assert index.is_produced("finished_draft")
        assert not index.is_produced("finished_draft", resource_kind="file")

    def test_step_output_bound_to_file_counts_as_file_producer(self) -> None:
        """A source-backed step output can produce a file resource via binding."""
        from nl2spl.ir.resource_contract_ir import ResourceContractBindingIR

        step = StepIR(
            step_id="st1",
            text="Draft document",
            source_span_ids=["s14"],
            command_type="GENERAL_COMMAND",
            outputs=["finished_draft"],
            kind="normal",
        )
        binding = ResourceContractBindingIR(
            contract_demand_id="rcd_output_s11",
            resource_name="finished_draft",
            resource_kind="file",
            direction="output",
            scope_kind="global",
            scope_id=None,
        )
        index = ProducerIndex(
            steps=[step],
            resource_contract_bindings=[binding],
        )

        assert index.is_produced("finished_draft")
        assert index.is_produced("finished_draft", resource_kind="file")
        assert not index.is_produced("finished_draft", resource_kind="variable")
