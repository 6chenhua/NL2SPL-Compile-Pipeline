from __future__ import annotations

from typing import Any

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import AlternativeFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, TypeSpec
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR
from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver import (
    resolve_condition_variable_references,
)


class FakeConditionRefClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, str]] = []

    def call_json(self, **kwargs: str) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        return self.payload


def test_resolver_collects_flow_and_block_condition_refs() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="ready_flag",
        data_type="Boolean",
        source="input",
        description="readiness",
        scope_kind="worker",
        scope_id="worker_main",
    )
    symbols.declare_scoped(
        name="missing_evidence",
        data_type="Boolean",
        source="input",
        description="missing evidence",
        scope_kind="worker",
        scope_id="worker_main",
    )
    flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(
                main_flow_spans=["s1"],
                alternative_flows=[
                    AlternativeFlow(
                        flow_id="alt_1",
                        condition_text="<REF>missing_evidence</REF> is detected",
                        spans=["s2"],
                    ),
                ],
            )
        }
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="IF",
                        condition_text="<REF>ready_flag</REF> is available",
                        spans=["s1"],
                    )
                ],
            )
        }
    )

    plan = resolve_condition_variable_references(
        worker_flow_plan=flow_plan,
        worker_block_plan=block_plan,
        symbol_table=symbols,
        resource_registry=ResourceRegistryIR(),
    )

    assert {ref.owner_kind for ref in plan.references} == {
        "alternative_flow_condition",
        "block_condition",
    }
    assert {ref.status for ref in plan.references} == {"resolved"}
    assert {ref.evidence_kind for ref in plan.references} == {"explicit_ref_token"}
    assert not plan.diagnostics


def test_resolver_reports_unresolved_and_invalid_qualified_ref() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="profile",
        data_type="Profile",
        source="input",
        description="profile",
        scope_kind="worker",
        scope_id="worker_main",
    )
    flow_plan = WorkerFlowPlanIR(worker_flows={"worker_main": FlowStructureIR()})
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="IF",
                        condition_text=(
                            "<REF>profile.unknown</REF> and "
                            "<REF>missing</REF> are ready"
                        ),
                        spans=["s1"],
                    )
                ],
            )
        }
    )

    plan = resolve_condition_variable_references(
        worker_flow_plan=flow_plan,
        worker_block_plan=block_plan,
        symbol_table=symbols,
        resource_registry=ResourceRegistryIR(
            types=[
                TypeSpec(
                    type_name="Profile",
                    type_kind="structured",
                    definition="{email: text}",
                )
            ]
        ),
    )

    assert [ref.status for ref in plan.references] == [
        "invalid_qualified_ref",
        "unresolved",
    ]
    assert {diag.kind for diag in plan.diagnostics} == {
        "condition_variable_invalid_qualified_ref",
        "condition_variable_ref_unresolved",
    }


def test_resolver_admits_llm_semantic_condition_reference() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="evidence",
        data_type="text",
        source="input",
        description="Collected evidence",
        scope_kind="worker",
        scope_id="worker_main",
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="IF",
                        condition_text="when enough evidence has been collected",
                        spans=["s1"],
                    )
                ]
            )
        }
    )
    owner_ref = "condition:block:worker_main:main:b1"
    client = FakeConditionRefClient(
        {
            "owner_ref": owner_ref,
            "references": [
                {
                    "relation": "condition_reads",
                    "selected_symbol": "evidence",
                    "qualified_ref": "evidence",
                    "evidence_text": "evidence",
                    "confidence": "medium",
                    "reason": "condition checks evidence readiness",
                }
            ],
            "unresolved_candidates": [],
        }
    )

    plan = resolve_condition_variable_references(
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=block_plan,
        symbol_table=symbols,
        resource_registry=ResourceRegistryIR(),
        llm_client=client,
    )

    assert len(plan.references) == 1
    assert plan.references[0].evidence_kind == "llm_condition_semantic_match"
    assert plan.references[0].canonical_ref == "evidence"
    assert plan.references[0].status == "resolved"
    assert not plan.diagnostics


def test_resolver_rejects_llm_symbol_outside_candidate_view() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="evidence",
        data_type="text",
        source="input",
        description="Collected evidence",
        scope_kind="worker",
        scope_id="worker_main",
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="IF",
                        condition_text="when enough evidence has been collected",
                        spans=["s1"],
                    )
                ]
            )
        }
    )
    owner_ref = "condition:block:worker_main:main:b1"
    client = FakeConditionRefClient(
        {
            "owner_ref": owner_ref,
            "references": [
                {
                    "relation": "condition_reads",
                    "selected_symbol": "invented_status",
                    "qualified_ref": "invented_status",
                    "evidence_text": "enough evidence has been collected",
                    "confidence": "medium",
                }
            ],
            "unresolved_candidates": [],
        }
    )

    plan = resolve_condition_variable_references(
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=block_plan,
        symbol_table=symbols,
        resource_registry=ResourceRegistryIR(),
        llm_client=client,
    )

    assert plan.references[0].status == "rejected"
    assert plan.references[0].reason == "selected_symbol_not_in_candidate_symbols"
    assert not plan.diagnostics


def test_llm_unresolved_concept_stays_audit_only() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="background_information",
        data_type="text",
        source="input",
        description="Background information",
        scope_kind="worker",
        scope_id="worker_main",
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="IF",
                        condition_text="facts and background information are available",
                        spans=["s1"],
                    )
                ]
            )
        }
    )
    client = FakeConditionRefClient(
        {
            "owner_ref": "condition:block:worker_main:main:b1",
            "references": [],
            "unresolved_candidates": [
                {
                    "proposed_symbol_text": "facts",
                    "evidence_text": "facts",
                    "reason": "No matching declared symbol.",
                }
            ],
        }
    )

    plan = resolve_condition_variable_references(
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=block_plan,
        symbol_table=symbols,
        resource_registry=ResourceRegistryIR(),
        llm_client=client,
    )

    assert len(plan.references) == 1
    assert plan.references[0].status == "unresolved"
    assert plan.references[0].evidence_kind == "llm_unresolved_condition_symbol"
    assert not plan.diagnostics


def test_admission_accepts_minimal_variable_substring() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="timeframe",
        data_type="text",
        source="input",
        description="timeframe context",
        scope_kind="worker",
        scope_id="worker_main",
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="IF",
                        condition_text="Missing timeframe",
                        spans=["s1"],
                    )
                ]
            )
        }
    )
    owner_ref = "condition:block:worker_main:main:b1"
    client = FakeConditionRefClient(
        {
            "owner_ref": owner_ref,
            "references": [
                {
                    "relation": "condition_reads",
                    "selected_symbol": "timeframe",
                    "qualified_ref": "timeframe",
                    "evidence_text": "timeframe",
                    "confidence": "high",
                    "reason": "Direct reference to timeframe variable",
                }
            ],
            "unresolved_candidates": [],
        }
    )

    plan = resolve_condition_variable_references(
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=block_plan,
        symbol_table=symbols,
        resource_registry=ResourceRegistryIR(),
        llm_client=client,
    )

    assert len(plan.references) == 1
    assert plan.references[0].status == "resolved"
    assert plan.references[0].evidence_text == "timeframe"
    assert not plan.diagnostics


def test_admission_rejects_full_phrase_evidence_text() -> None:
    # 1. Direct admission level check:
    # _admit_llm_reference returns status="rejected" and reason="full_condition_overmatch"
    from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.candidate_symbols import (
        CandidateSymbol,
    )
    from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.owner import (
        ConditionOwner,
    )
    from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.resolver import (
        ConditionReferenceResolver,
    )
    from nl2spl.pipeline.stages.stage6_5_condition_reference_resolver.response_parser import (
        LLMConditionReferenceCandidate,
    )

    owner = ConditionOwner(
        owner_kind="block_condition",
        owner_ref="condition:block:worker_main:main:b1",
        condition_text="Missing timeframe",
        source_span_ids=("s1",),
        worker_id="worker_main",
        flow_ref="main",
        block_ref="b1",
    )
    candidate = LLMConditionReferenceCandidate(
        relation="condition_reads",
        selected_symbol="timeframe",
        qualified_ref="timeframe",
        evidence_text="Missing timeframe",
        confidence="high",
        reason="Semantic match",
    )
    candidate_symbol = CandidateSymbol(
        name="timeframe",
        data_type="text",
        scope_kind="worker",
        scope_id="worker_main",
        description="timeframe context",
        source="input",
    )

    resolver = ConditionReferenceResolver()
    ref = resolver._admit_llm_reference(
        owner=owner,
        candidate=candidate,
        candidates=(candidate_symbol,),
        resource_registry=ResourceRegistryIR(),
        index=0,
    )
    assert ref.status == "rejected"
    assert ref.reason == "full_condition_overmatch"

    # 2. Pipeline-level check: rejected overmatch reference is NOT in final references or diagnostics
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="timeframe",
        data_type="text",
        source="input",
        description="timeframe context",
        scope_kind="worker",
        scope_id="worker_main",
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="IF",
                        condition_text="Missing timeframe",
                        spans=["s1"],
                    )
                ]
            )
        }
    )
    client = FakeConditionRefClient(
        {
            "owner_ref": "condition:block:worker_main:main:b1",
            "references": [
                {
                    "relation": "condition_reads",
                    "selected_symbol": "timeframe",
                    "qualified_ref": "timeframe",
                    "evidence_text": "Missing timeframe",
                    "confidence": "high",
                    "reason": "Matching entire phrase",
                }
            ],
            "unresolved_candidates": [],
        }
    )

    plan = resolve_condition_variable_references(
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=block_plan,
        symbol_table=symbols,
        resource_registry=ResourceRegistryIR(),
        llm_client=client,
    )

    assert len(plan.references) == 0
    assert len(plan.diagnostics) == 0


def test_user_refusal_does_not_map_to_user_request() -> None:
    symbols = SymbolTable()
    symbols.declare_scoped(
        name="user_request",
        data_type="text",
        source="input",
        description="user request context",
        scope_kind="worker",
        scope_id="worker_main",
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="IF",
                        condition_text="user refusal to answer",
                        spans=["s1"],
                    )
                ]
            )
        }
    )
    client = FakeConditionRefClient(
        {
            "owner_ref": "condition:block:worker_main:main:b1",
            "references": [
                {
                    "relation": "condition_reads",
                    "selected_symbol": "user_request",
                    "qualified_ref": "user_request",
                    "evidence_text": "user refusal to answer",
                    "confidence": "low",
                    "reason": "Closest symbol to refusal",
                }
            ],
            "unresolved_candidates": [],
        }
    )

    plan = resolve_condition_variable_references(
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=block_plan,
        symbol_table=symbols,
        resource_registry=ResourceRegistryIR(),
        llm_client=client,
    )

    # Verifies no resolved/rejected ref in the final plan, and no blocking warning
    assert len(plan.references) == 0
    assert len(plan.diagnostics) == 0


def test_abstract_static_condition_empty_llm_response_has_no_diagnostics() -> None:
    symbols = SymbolTable()
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="IF",
                        condition_text="conflicting instructions",
                        spans=["s1"],
                    )
                ]
            )
        }
    )
    client = FakeConditionRefClient(
        {
            "owner_ref": "condition:block:worker_main:main:b1",
            "references": [],
            "unresolved_candidates": [],
        }
    )

    plan = resolve_condition_variable_references(
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"worker_main": FlowStructureIR()}
        ),
        worker_block_plan=block_plan,
        symbol_table=symbols,
        resource_registry=ResourceRegistryIR(),
        llm_client=client,
    )

    assert len(plan.references) == 0
    assert len(plan.diagnostics) == 0
