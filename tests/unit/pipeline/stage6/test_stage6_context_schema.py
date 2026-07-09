"""S6V2: Stage 6 context schema contract tests.

Verify the context builder output has:
- DECLARATION_EVIDENCE with run_inputs, required_deliverables,
  resource_contract_demands, explicit_action_output_intents,
  confirmed_response_targets.
- READ_ONLY_CONTEXT with control_clauses, branch_descriptions,
  rules_constraints, profile_persona, display_text.
- Hard instruction: "Only DECLARATION_EVIDENCE may introduce variables."
"""

from __future__ import annotations

from nl2spl.canonical import CanonicalCompileInput, HardFacts, VariableFact
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import (
    AlternativeFlow,
    ExceptionFlow,
    FlowStructureIR,
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import ContractFieldIR, WorkerSpecIR
from nl2spl.pipeline.stages.stage6_resource_extractor.context_builder import (
    build_resource_context,
)


# ---------------------------------------------------------------------------
# S6V2: DECLARATION_EVIDENCE / READ_ONLY_CONTEXT partition
# ---------------------------------------------------------------------------


class TestS6V2ContextHasDeclarationEvidencePartition:
    """Verify context output has DECLARATION_EVIDENCE section."""

    def test_declaration_evidence_header_present(self) -> None:
        ctx = build_resource_context(
            spans=[SpanIR("s1", "Step.")],
            routes=FieldRouteIR(behavior=["s1"]),
        )
        assert "## DECLARATION_EVIDENCE" in ctx, (
            "S6V2: context must have DECLARATION_EVIDENCE section header."
        )

    def test_read_only_context_header_present(self) -> None:
        ctx = build_resource_context(
            spans=[SpanIR("s1", "Step.")],
            routes=FieldRouteIR(behavior=["s1"]),
        )
        assert "## READ_ONLY_CONTEXT" in ctx, (
            "S6V2: context must have READ_ONLY_CONTEXT section header."
        )

    def test_declaration_evidence_contains_instruction(self) -> None:
        ctx = build_resource_context(
            spans=[SpanIR("s1", "Step.")],
            routes=FieldRouteIR(behavior=["s1"]),
        )
        assert "Only the sections below may introduce new variables" in ctx, (
            "S6V2: DECLARATION_EVIDENCE must include the instruction that "
            "only it may introduce variables."
        )

    def test_read_only_context_contains_instruction(self) -> None:
        ctx = build_resource_context(
            spans=[SpanIR("s1", "Step.")],
            routes=FieldRouteIR(behavior=["s1"]),
        )
        assert "NOT sources for declaring new variables" in ctx, (
            "S6V2: READ_ONLY_CONTEXT must warn that it is NOT a source "
            "for declaring new variables."
        )

    def test_extraction_policy_has_only_declaration_evidence_rule(self) -> None:
        ctx = build_resource_context(
            spans=[SpanIR("s1", "Step.")],
            routes=FieldRouteIR(behavior=["s1"]),
        )
        policy_section = ctx.split("Extraction policy")[1]
        assert "Only DECLARATION_EVIDENCE sections may introduce new variables" in policy_section, (
            "S6V2: extraction policy must reiterate DECLARATION_EVIDENCE rule."
        )


class TestS6V2ContractInDeclarationEvidence:
    """Authoritative contract and demand sections belong to DECLARATION_EVIDENCE."""

    def test_authoritative_contract_before_read_only(self) -> None:
        worker = WorkerSpecIR(
            worker_id="w1", worker_name="W1", kind="child",
            purpose="Test.",
            owned_span_ids=["s1"],
            input_contract=[ContractFieldIR("query", "text", True, "Q", "input")],
            output_contract=[],
        )
        ctx = build_resource_context(
            spans=[SpanIR("s1", "Step.")],
            routes=FieldRouteIR(behavior=["s1"]),
            worker_spec=worker, scope_kind="worker", scope_id="w1",
        )
        de_pos = ctx.find("## DECLARATION_EVIDENCE")
        ro_pos = ctx.find("## READ_ONLY_CONTEXT")
        contract_pos = ctx.find("Authoritative contract")
        assert de_pos < contract_pos < ro_pos, (
            "S6V2: Authoritative contract must be between "
            "DECLARATION_EVIDENCE and READ_ONLY_CONTEXT headers."
        )

    def test_hard_fact_inputs_in_declaration_evidence(self) -> None:
        canonical = CanonicalCompileInput(
            source_schema="structural_nl", schema_version="1.0", raw_text="",
            hard_facts=HardFacts(
                inputs=[VariableFact("user_request", "Request", "text", True,
                                       source_section_id="sec_inputs")],
                outputs=[],
            ),
        )
        ctx = build_resource_context(
            spans=[SpanIR("s1", "Step.")],
            routes=FieldRouteIR(behavior=["s1"]),
            canonical_input=canonical, scope_kind="global",
        )
        de_section = ctx.split("## DECLARATION_EVIDENCE")[1].split("## READ_ONLY_CONTEXT")[0]
        assert "user_request" in de_section, (
            "S6V2: hard fact inputs must appear in DECLARATION_EVIDENCE."
        )


class TestS6V2FlowBlockConditionsInReadOnly:
    """Flow and block condition summaries belong to READ_ONLY_CONTEXT."""

    def test_flow_conditions_in_read_only(self) -> None:
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            alternative_flows=[
                AlternativeFlow("alt_01", "threshold exceeded", spans=["s_alt"]),
            ],
            exception_flows=[
                ExceptionFlow("exc_01", "timeout", spans=["s_err"]),
            ],
        )
        ctx = build_resource_context(
            spans=[
                SpanIR("s1", "A"), SpanIR("s_alt", "Alt"), SpanIR("s_err", "Err"),
            ],
            routes=FieldRouteIR(behavior=["s1", "s_alt", "s_err"]),
            flow=flow,
        )
        ro_section = ctx.split("## READ_ONLY_CONTEXT")[1]
        assert "threshold exceeded" in ro_section, (
            "S6V2: alternative flow condition must be in READ_ONLY_CONTEXT."
        )
        assert "timeout" in ro_section, (
            "S6V2: exception flow condition must be in READ_ONLY_CONTEXT."
        )

    def test_block_conditions_in_read_only(self) -> None:
        blocks = BlockStructureIR(
            main_flow_blocks=[
                BlockIR("b1", "IF", condition_text="over budget", spans=["s1"]),
            ],
        )
        ctx = build_resource_context(
            spans=[SpanIR("s1", "Step.")],
            routes=FieldRouteIR(behavior=["s1"]),
            blocks=blocks,
        )
        ro_section = ctx.split("## READ_ONLY_CONTEXT")[1]
        assert "over budget" in ro_section, (
            "S6V2: block condition text must be in READ_ONLY_CONTEXT."
        )

    def test_flow_summary_not_in_declaration_evidence(self) -> None:
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow("exc_01", "timeout", spans=["s_err"]),
            ],
        )
        ctx = build_resource_context(
            spans=[SpanIR("s1", "A"), SpanIR("s_err", "Err")],
            routes=FieldRouteIR(behavior=["s1", "s_err"]),
            flow=flow,
        )
        de_section = ctx.split("## DECLARATION_EVIDENCE")[1].split("## READ_ONLY_CONTEXT")[0]
        assert "Flow summary" not in de_section, (
            "S6V2: Flow summary must not be in DECLARATION_EVIDENCE."
        )
        assert "Block summary" not in de_section, (
            "S6V2: Block summary must not be in DECLARATION_EVIDENCE."
        )


class TestS6V2SourceSpansInReadOnlyContext:
    """Source spans (behavior text) belong to READ_ONLY_CONTEXT.

    Raw source spans contain behavior and control descriptions that
    are NOT structured declaration evidence.  They must not be presented
    to the LLM as variable-declaration sources.
    """

    def test_source_spans_in_read_only_context(self) -> None:
        ctx = build_resource_context(
            spans=[SpanIR("s1", "Identify topics.")],
            routes=FieldRouteIR(behavior=["s1"]),
        )
        de_section = ctx.split("## DECLARATION_EVIDENCE")[1].split("## READ_ONLY_CONTEXT")[0]
        assert "Source spans" not in de_section, (
            "Fix 1: Source spans must NOT be in DECLARATION_EVIDENCE. "
            "They contain raw behavior/control text that LLM may extract "
            "variables from."
        )
        ro_section = ctx.split("## READ_ONLY_CONTEXT")[1]
        assert "Source spans" in ro_section, (
            "Fix 1: Source spans must be in READ_ONLY_CONTEXT."
        )


class TestS6V2KnownVariablesAndSymbolTable:
    """Known variables and symbol table still present and after partition."""

    def test_known_variables_after_read_only(self) -> None:
        sym = SymbolTable()
        sym.declare("existing", "text", "input", "Known input.")
        ctx = build_resource_context(
            spans=[SpanIR("s1", "Step.")],
            routes=FieldRouteIR(behavior=["s1"]),
            symbol_table=sym, scope_kind="worker", scope_id="w1",
        )
        ro_pos = ctx.find("## READ_ONLY_CONTEXT")
        kv_pos = ctx.find("Known variables")
        assert kv_pos > ro_pos, (
            "S6V2: Known variables must appear after READ_ONLY_CONTEXT."
        )
