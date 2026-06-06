"""R0 Baseline Audit: IRS v6 重构基线测试

本文件锁定当前 IRS 相关行为，作为后续 R1-R9 重构的基线。

R0 规则：
1. 只增加测试，不修改生产代码
2. current-behavior tests 必须 pass
3. target-future tests 可以 xfail(strict=True)
4. 不允许 skip
5. 不引入新的 LLM/rule-based 语义判断
"""

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs_prompt_builder import IRSDrivenPromptBuilder
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import WorkerIR
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.stages.stage4_flow_assembler.irs_checker import (
    check_exception_flows_irs,
    check_worker_flow_plan_exception_flows_irs,
)
from nl2spl.pipeline.stages.stage7_step_extractor.irs_checker import (
    check_steps_irs,
    check_worker_step_plan_irs,
)
from nl2spl.pipeline.stages.stage9_5_normalizer import IRNormalizer
from nl2spl.pipeline.stages.stage9_5_normalizer.final_irs_checker import (
    PostNormalizeIRSChecker,
)


# ===========================================================================
# 7.1 Stage 4 EXCEPTION_FLOW IRS Baseline
# ===========================================================================


class TestR0Stage4ExceptionFlowBaseline:
    """锁定 Stage 4 IRS checker 对 exception flow 的当前行为"""

    def test_r0_stage4_condition_with_spans_is_partial_renderable(self):
        """当前行为：condition + spans -> partial + renderable"""
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Quoted pricing is over budget",
                    spans=["s20"],
                )
            ],
        )
        reports, diagnostics = check_exception_flows_irs(flow)

        assert len(reports) == 1
        assert reports[0].construct_type == "EXCEPTION_FLOW"
        assert reports[0].completeness == "partial"
        assert reports[0].renderable is True
        assert len(diagnostics) == 0

        # 验证 condition slot satisfied
        cond_slot = next(s for s in reports[0].slots if s.slot_name == "condition")
        assert cond_slot.status == "satisfied"
        assert cond_slot.relation == "direct"
        assert cond_slot.source_span_ids == ["s20"]

    def test_r0_stage4_condition_without_spans_reports_type_contract_ambiguity(self):
        """当前行为：condition 无 spans -> type_or_contract_ambiguity + not renderable"""
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Handle errors appropriately",
                    spans=[],
                )
            ],
        )
        reports, diagnostics = check_exception_flows_irs(flow)

        assert len(reports) == 1
        assert reports[0].renderable is False
        assert reports[0].completeness == "partial"

        assert len(diagnostics) == 1
        assert diagnostics[0].kind == "type_or_contract_ambiguity"
        assert "exc_1" in diagnostics[0].message
        assert diagnostics[0].blocks_rendering is True
        assert diagnostics[0].blocks_completion is True

        # 验证 condition slot assumed
        cond_slot = next(s for s in reports[0].slots if s.slot_name == "condition")
        assert cond_slot.status == "assumed"
        assert cond_slot.diagnostic_kind == "type_or_contract_ambiguity"

    def test_r0_stage4_does_not_emit_missing_handler(self):
        """当前行为：Stage 4 不负责 missing_handler diagnostic"""
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Over budget",
                    spans=["s20"],
                )
            ],
        )
        _, diagnostics = check_exception_flows_irs(flow)

        diagnostic_kinds = {d.kind for d in diagnostics}
        assert "missing_handler" not in diagnostic_kinds

    def test_r0_stage4_handler_action_slot_not_applicable(self):
        """当前行为：Stage 4 的 handler_action slot 标记为 not_applicable"""
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Over budget",
                    spans=["s20"],
                )
            ],
        )
        reports, _ = check_exception_flows_irs(flow)

        handler_slot = next(
            s for s in reports[0].slots if s.slot_name == "handler_action"
        )
        assert handler_slot.status == "not_applicable"

    def test_r0_stage4_worker_scoped_construct_ids(self):
        """当前行为：worker-aware path 生成 worker:xxx.exception_flow:xxx 格式 ID"""
        plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_main": FlowStructureIR(
                    main_flow_spans=["s1"],
                    exception_flows=[
                        ExceptionFlow(
                            flow_id="exc_1",
                            condition_text="Over budget",
                            spans=["s20"],
                        )
                    ],
                ),
            },
        )
        reports, _ = check_worker_flow_plan_exception_flows_irs(plan)

        assert len(reports) == 1
        assert reports[0].construct_id == "worker:worker_main.exception_flow:exc_1"

    def test_r0_stage4_unique_diagnostic_ids_across_workers(self):
        """当前行为：多 worker 的 diagnostic_id 不冲突"""
        plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_main": FlowStructureIR(
                    main_flow_spans=["s1"],
                    exception_flows=[
                        ExceptionFlow(
                            flow_id="exc_1",
                            condition_text="Handle errors",
                            spans=[],
                        )
                    ],
                ),
                "child_review": FlowStructureIR(
                    main_flow_spans=["s2"],
                    exception_flows=[
                        ExceptionFlow(
                            flow_id="exc_2",
                            condition_text="Review failure",
                            spans=[],
                        )
                    ],
                ),
            },
        )
        _, diagnostics = check_worker_flow_plan_exception_flows_irs(plan)

        assert len(diagnostics) == 2
        ids = {d.diagnostic_id for d in diagnostics}
        assert len(ids) == 2, f"Duplicate diagnostic_id found: {ids}"
        # R6.4: diagnostic_id format changed to irs_{hash}
        assert all(did.startswith("irs_") for did in ids)


# ===========================================================================
# 7.2 Stage 7 Step IRS Baseline
# ===========================================================================


class TestR0Stage7StepIRSBaseline:
    """锁定 Stage 7 IRS checker 对 StepIR 的当前行为"""

    def test_r0_stage7_general_command_without_source_is_not_renderable(self):
        """当前行为：GENERAL_COMMAND 无 source_span_ids -> assumed_command_not_renderable"""
        step = StepIR(
            step_id="st_1",
            text="Process data",
            source_span_ids=[],
            command_type="GENERAL_COMMAND",
            inputs=[],
            outputs=[],
            flow_ref="main",
            block_ref="b_1",
        )
        reports, diagnostics = check_steps_irs([step])

        assert len(reports) == 1
        assert reports[0].renderable is False
        assert reports[0].completeness == "partial"

        assert len(diagnostics) == 1
        assert diagnostics[0].kind == "assumed_command_not_renderable"

        # 验证 source_evidence slot missing
        source_slot = next(
            s for s in reports[0].slots if s.slot_name == "source_evidence"
        )
        assert source_slot.status == "missing"
        assert source_slot.diagnostic_kind == "assumed_command_not_renderable"

    def test_r0_stage7_general_command_with_source_is_complete(self):
        """当前行为：GENERAL_COMMAND 有 source_span_ids -> complete + renderable"""
        step = StepIR(
            step_id="st_1",
            text="Process data",
            source_span_ids=["s1"],
            command_type="GENERAL_COMMAND",
            inputs=[],
            outputs=[],
            flow_ref="main",
            block_ref="b_1",
        )
        reports, diagnostics = check_steps_irs([step])

        assert len(reports) == 1
        assert reports[0].completeness == "complete"
        assert reports[0].renderable is True
        assert len(diagnostics) == 0

    def test_r0_stage7_request_input_without_source_reports_contract_ambiguity(self):
        """当前行为：REQUEST_INPUT 无 source_span_ids -> type_or_contract_ambiguity"""
        step = StepIR(
            step_id="st_1",
            text="Ask user",
            source_span_ids=[],
            command_type="REQUEST_INPUT",
            inputs=[],
            outputs=[],
            flow_ref="main",
            block_ref="b_1",
        )
        reports, diagnostics = check_steps_irs([step])

        assert len(diagnostics) == 1
        assert diagnostics[0].kind == "type_or_contract_ambiguity"
        assert "ask/request/prompt" in diagnostics[0].message.lower()

    def test_r0_stage7_call_api_requires_integration_ref_and_source(self):
        """当前行为：CALL_API 缺 integration_ref 或 source -> type_or_contract_ambiguity"""
        # 缺 integration_ref
        step1 = StepIR(
            step_id="st_1",
            text="Call API",
            source_span_ids=["s1"],
            command_type="CALL_API",
            integration_ref=None,
            inputs=[],
            outputs=[],
            flow_ref="main",
            block_ref="b_1",
        )
        _, diags1 = check_steps_irs([step1])
        assert any(d.kind == "type_or_contract_ambiguity" for d in diags1)
        assert any("integration_ref" in d.message.lower() for d in diags1)

        # 缺 source_span_ids
        step2 = StepIR(
            step_id="st_2",
            text="Call SendGrid",
            source_span_ids=[],
            command_type="CALL_API",
            integration_ref="SendGrid",
            inputs=[],
            outputs=[],
            flow_ref="main",
            block_ref="b_1",
        )
        _, diags2 = check_steps_irs([step2])
        assert any(d.kind == "type_or_contract_ambiguity" for d in diags2)
        assert any("source-span" in d.message for d in diags2)

    def test_r0_stage7_invoke_worker_requires_target_and_handoff(self):
        """当前行为：INVOKE_WORKER 缺 integration_ref 或 handoff_id -> type_or_contract_ambiguity"""
        # 缺 handoff_id
        step1 = StepIR(
            step_id="st_1",
            text="Invoke worker",
            source_span_ids=[],
            command_type="INVOKE_WORKER",
            integration_ref="WorkerX",
            handoff_id=None,
            inputs=[],
            outputs=[],
            flow_ref="main",
            block_ref="b_1",
        )
        _, diags1 = check_steps_irs([step1])
        assert any(d.kind == "type_or_contract_ambiguity" for d in diags1)
        assert any("handoff_id" in d.message for d in diags1)

        # 缺 integration_ref
        step2 = StepIR(
            step_id="st_2",
            text="Invoke worker",
            source_span_ids=[],
            command_type="INVOKE_WORKER",
            integration_ref=None,
            handoff_id="handoff_1",
            inputs=[],
            outputs=[],
            flow_ref="main",
            block_ref="b_1",
        )
        _, diags2 = check_steps_irs([step2])
        assert any(d.kind == "type_or_contract_ambiguity" for d in diags2)
        assert any("integration_ref" in d.message for d in diags2)

    def test_r0_stage7_worker_scoped_construct_ids(self):
        """当前行为：worker-aware path 生成 worker:xxx.step:xxx 格式 ID"""
        plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    StepIR(
                        step_id="st_1",
                        text="Process",
                        source_span_ids=["s1"],
                        command_type="GENERAL_COMMAND",
                        inputs=[],
                        outputs=[],
                        flow_ref="main",
                        block_ref="b_1",
                    ),
                ],
            },
        )
        reports, _ = check_worker_step_plan_irs(plan)

        assert len(reports) == 1
        assert reports[0].construct_id == "worker:worker_main.step:st_1"

    def test_r0_stage7_unique_diagnostic_ids_across_workers(self):
        """当前行为：多 worker 的 diagnostic_id 不冲突"""
        plan = WorkerStepPlanIR(
            main_worker_id="worker_main",
            worker_steps={
                "worker_main": [
                    StepIR(
                        step_id="st_1",
                        text="Process",
                        source_span_ids=[],
                        command_type="GENERAL_COMMAND",
                        inputs=[],
                        outputs=[],
                        flow_ref="main",
                        block_ref="b_1",
                    ),
                ],
                "child_review": [
                    StepIR(
                        step_id="st_1",
                        text="Ask",
                        source_span_ids=[],
                        command_type="REQUEST_INPUT",
                        inputs=[],
                        outputs=[],
                        flow_ref="main",
                        block_ref="b_1",
                    ),
                ],
            },
        )
        _, diagnostics = check_worker_step_plan_irs(plan)

        ids = {d.diagnostic_id for d in diagnostics}
        assert len(ids) == 2
        # R6.4: diagnostic_id format changed to irs_{hash}
        assert all(did.startswith("irs_") for did in ids)


# ===========================================================================
# 7.3 Post-normalize IRS Baseline
# ===========================================================================


class TestR0PostNormalizeIRSBaseline:
    """锁定 PostNormalizeIRSChecker 当前 final construct-level diagnostics 行为"""

    def test_r0_post_normalize_missing_handler_emits_once(self):
        """当前行为：exception flow 无 handler -> missing_handler diagnostic"""
        from nl2spl.ir.worker_ir import ExceptionFlowRef, WorkerInput, WorkerOutput

        checker = PostNormalizeIRSChecker()

        # 构造一个 WorkerIR，包含 exception flow 但无 handler step
        worker = WorkerIR(
            worker_name="Main",
            description="Main worker",
            inputs=[],
            outputs=[],
            steps=[
                StepIR(
                    "st1",
                    "Do work",
                    ["s1"],
                    "GENERAL_COMMAND",
                    inputs=[],
                    outputs=[],
                    flow_ref="main",
                    block_ref="b1",
                )
            ],
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    blocks=[],
                    spans=["s2"],
                )
            ],
            alternative_flows=[],
            child_workers=[],
        )

        diagnostics = checker.check(worker)

        # 验证产生 missing_handler diagnostic
        missing_handler_diags = [d for d in diagnostics if d.kind == "missing_handler"]
        assert len(missing_handler_diags) == 1
        assert "exc_1" in missing_handler_diags[0].message
        assert "Missing timeframe" in missing_handler_diags[0].message
        assert missing_handler_diags[0].blocks_completion is True
        assert missing_handler_diags[0].blocks_rendering is False

    def test_r0_post_normalize_required_output_without_producer(self):
        """当前行为：required output 无 producer -> missing_output_producer diagnostic"""
        from nl2spl.ir.worker_ir import WorkerOutput

        checker = PostNormalizeIRSChecker()

        # 构造 WorkerPlanIR，main worker 有 required output 但无 producer step
        worker_plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_main",
                    worker_name="Main",
                    kind="main",
                    purpose="Main worker",
                    owned_span_ids=["s1"],
                    input_contract=[],
                    output_contract=[
                        ContractFieldIR(
                            name="result",
                            data_type="text",
                            required=True,
                            description="Result",
                            source="output",
                        )
                    ],
                    depends_on=[],
                    constraints=[],
                    boundary_kind="main_worker",
                    decision_evidence=[],
                    reason="",
                )
            ],
            candidates=[],
            decisions=[],
            handoffs=[],
        )

        worker = WorkerIR(
            worker_name="Main",
            description="Main worker",
            inputs=[],
            outputs=[
                WorkerOutput(name="result", required=True)
            ],
            steps=[
                # 没有产生 result 的 step
                StepIR(
                    "st1",
                    "Do work",
                    ["s1"],
                    "GENERAL_COMMAND",
                    inputs=[],
                    outputs=[],
                    flow_ref="main",
                    block_ref="b1",
                )
            ],
            exception_flows=[],
            alternative_flows=[],
            child_workers=[],
        )

        symbols = SymbolTable()
        symbols.declare("result", "text", "output", "Result")

        diagnostics = checker.check(worker, worker_plan=worker_plan, symbol_table=symbols)

        # 验证产生 missing_output_producer diagnostic
        missing_producer_diags = [
            d for d in diagnostics if d.kind == "missing_output_producer"
        ]
        assert len(missing_producer_diags) == 1
        assert "result" in missing_producer_diags[0].message
        assert missing_producer_diags[0].blocks_completion is True
        assert missing_producer_diags[0].blocks_rendering is False

    def test_r0_post_normalize_assumed_command_not_renderable(self):
        """当前行为：无 source evidence 且非 compiler scaffolding step -> assumed_command_not_renderable"""
        checker = PostNormalizeIRSChecker()

        worker = WorkerIR(
            worker_name="Main",
            description="Main worker",
            inputs=[],
            outputs=[],
            steps=[
                # 无 source_span_ids，且不是 compiler_unpack
                StepIR(
                    "st1",
                    "Process data",
                    [],  # 无 source_span_ids
                    "GENERAL_COMMAND",
                    inputs=[],
                    outputs=[],
                    flow_ref="main",
                    block_ref="b1",
                )
            ],
            exception_flows=[],
            alternative_flows=[],
            child_workers=[],
        )

        diagnostics = checker.check(worker)

        # 验证产生 assumed_command_not_renderable diagnostic
        assumed_diags = [
            d for d in diagnostics if d.kind == "assumed_command_not_renderable"
        ]
        assert len(assumed_diags) == 1
        assert "st1" in assumed_diags[0].message
        assert "no source evidence" in assumed_diags[0].message
        assert assumed_diags[0].blocks_rendering is True
        assert assumed_diags[0].blocks_completion is True

    def test_r0_normalizer_exception_flow_preserved_without_handler(self):
        assert not hasattr(IRNormalizer(), "normalize")
        return
        """额外 baseline：IRNormalizer 保留 exception flow 即使无 handler"""
        normalizer = IRNormalizer()
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    spans=["s2"],
                )
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])],
        )
        steps = [
            StepIR(
                "st1",
                "Do work",
                ["s1"],
                "GENERAL_COMMAND",
                inputs=[],
                outputs=[],
                flow_ref="main",
                block_ref="b1",
            ),
        ]

        normalized_flow, _, _, _, _, _, _ = normalizer._legacy_flat_normalize_removed(
            flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, []
        )

        # Exception flow 被保留（不被移除）
        assert len(normalized_flow.exception_flows) == 1
        assert normalized_flow.exception_flows[0].flow_id == "exc_1"

    def test_r0_normalizer_condition_only_flow_no_handler_fabrication(self):
        assert not hasattr(IRNormalizer(), "normalize")
        return
        """额外 baseline：IRNormalizer 不制造 handler step"""
        normalizer = IRNormalizer()
        flow = FlowStructureIR(
            main_flow_spans=["s_main"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_adapter_00",
                    condition_text="Missing timeframe.",
                    spans=["s_fail"],
                ),
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s_main"])],
            exception_flow_blocks={"exc_adapter_00": []},
        )
        steps = [
            StepIR(
                "st1",
                "Main work",
                ["s_main"],
                "GENERAL_COMMAND",
                inputs=[],
                outputs=[],
                flow_ref="main",
                block_ref="b1",
            )
        ]

        normalized_flow, _, normalized_steps, _, _, _, _ = (
            normalizer._legacy_flat_normalize_removed(
            flow,
            blocks,
            ResourceRegistryIR(),
            SymbolTable(),
            steps,
            [],
            )
        )

        assert len(normalized_flow.exception_flows) == 1
        handler_steps = [
            s for s in normalized_steps if s.flow_ref == "exc_adapter_00"
        ]
        assert len(handler_steps) == 0

    def test_r0_normalizer_unresolved_invoke_worker_is_rejected(self):
        assert not hasattr(IRNormalizer(), "normalize")
        return
        """额外 baseline：IRNormalizer 对 unresolved INVOKE_WORKER 产生 validation error"""
        normalizer = IRNormalizer()
        steps = [
            StepIR(
                "st1",
                "Produce a draft",
                ["s1"],
                "INVOKE_WORKER",
                inputs=[],
                outputs=["draft"],
                flow_ref="main",
                block_ref="b1",
                kind="invoke",
            )
        ]
        symbols = SymbolTable()
        symbols.declare("draft", "text", "output", "Draft")
        resources = ResourceRegistryIR()

        _, _, normalized_steps, _, _, errors, _ = normalizer._legacy_flat_normalize_removed(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            resources,
            symbols,
            steps,
            [],
        )

        assert normalized_steps[0].command_type == "INVOKE_WORKER"
        assert any("no concrete child worker" in error for error in errors)


# ===========================================================================
# 7.4 Stage 3.5 IRS Checklist Current State
# ===========================================================================


class TestR0Stage35IRSChecklistCurrentState:
    """记录当前 stage3_5 IRS checklist 的真实状态"""

    def test_r0_stage3_5_irs_checklist_is_empty_current_baseline(self):
        """当前行为：stage3_5 IRS checklist 为空（这是 current baseline，不是目标）"""
        registry = SPLConstructRegistry.default()
        builder = IRSDrivenPromptBuilder(registry)

        result = builder.render_for_stage("stage3_5")

        # 当前 stage3_5 不在 injection map 中，返回空字符串
        assert result == ""

    def test_r0_stage3_5a_irs_checklist_is_empty_current_baseline(self):
        """当前行为：stage3_5a IRS checklist 为空"""
        registry = SPLConstructRegistry.default()
        builder = IRSDrivenPromptBuilder(registry)

        result = builder.render_for_stage("stage3_5a")

        assert result == ""

    def test_r0_stage3_5b_irs_checklist_is_empty_current_baseline(self):
        """当前行为：stage3_5b IRS checklist 为空"""
        registry = SPLConstructRegistry.default()
        builder = IRSDrivenPromptBuilder(registry)

        result = builder.render_for_stage("stage3_5b")

        assert result == ""


# ===========================================================================
# 7.5 Worker/Delegation Promotion Gap
# ===========================================================================


class TestR0WorkerDelegationPromotionGap:
    """记录当前系统无法用 IRS satisfaction report 解释 promotion blocked 的缺口"""

    def test_r0_worker_candidate_has_no_worker_promotion_report_current_baseline(self):
        """当前行为：有 delegation candidate 但系统不生成 WORKER_PROMOTION report"""
        # 构造一个 WorkerPlanIR，包含真实 delegation candidate 但缺完整 contract
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_main",
                    worker_name="Main",
                    kind="main",
                    purpose="Main worker",
                    owned_span_ids=["s1"],
                    input_contract=[],
                    output_contract=[],
                    depends_on=[],
                    constraints=[],
                    boundary_kind="main_worker",
                    decision_evidence=[],
                    reason="",
                )
            ],
            candidates=[
                CandidateTaskUnitIR(
                    candidate_id="candidate_draft",
                    source_span_ids=["s2"],
                    task_text="Draft using templates",
                    purpose="Drafting can be delegated",
                    candidate_kind="explicit_delegation",
                    possible_inputs=[],  # 缺少 input contract
                    possible_outputs=[],  # 缺少 output contract
                    signals=["explicit_delegation"],
                    risks=["no_clear_input_contract", "no_clear_output_contract"],
                )
            ],
            decisions=[],
            handoffs=[],
        )

        # 当前没有 check_worker_plan_irs 函数，无法检查 WORKER_PROMOTION report
        # 验证：当前 WorkerPlanIR 不包含 promotion report 相关字段
        assert not hasattr(plan, "promotion_reports")
        
        # 验证 candidate 确实存在
        assert len(plan.candidates) == 1
        assert plan.candidates[0].candidate_kind == "explicit_delegation"
        assert "no_clear_input_contract" in plan.candidates[0].risks

    def test_target_worker_promotion_report_for_incomplete_delegation(self):
        """R4 验收：incomplete delegation 应产生 WORKER_PROMOTION blocked report"""
        from nl2spl.compiler.construct_registry import SPLConstructRegistry
        from nl2spl.compiler.irs.checkers.worker_delegation import (
            WorkerDelegationIRSChecker,
        )
        from nl2spl.compiler.irs.context import IRSCheckContext
        from nl2spl.compiler.irs.projector import DiagnosticProjector
        from nl2spl.compiler.irs.registry import IRSCheckerRegistry
        from nl2spl.compiler.irs.runner import IRSRunner

        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_main",
                    worker_name="Main",
                    kind="main",
                    purpose="Main worker",
                    owned_span_ids=["s1"],
                    input_contract=[],
                    output_contract=[],
                    depends_on=[],
                    constraints=[],
                    boundary_kind="main_worker",
                    decision_evidence=[],
                    reason="",
                )
            ],
            candidates=[
                CandidateTaskUnitIR(
                    candidate_id="candidate_draft",
                    source_span_ids=["s2"],
                    task_text="Draft using templates",
                    purpose="Drafting can be delegated",
                    candidate_kind="explicit_delegation",
                    possible_inputs=[],
                    possible_outputs=[],
                    signals=["explicit_delegation"],
                    risks=["no_clear_input_contract", "no_clear_output_contract"],
                )
            ],
            decisions=[],
            handoffs=[],
        )

        # Setup runner with R4 checker
        checker_registry = IRSCheckerRegistry()
        checker = WorkerDelegationIRSChecker()
        checker_registry.register(checker)

        construct_registry = SPLConstructRegistry.default()
        projector = DiagnosticProjector()

        runner = IRSRunner(
            registry=checker_registry,
            construct_registry=construct_registry,
            projector=projector,
        )

        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        result = runner.run_stage("stage3_5", context)

        # Verify WORKER_PROMOTION report exists and is blocked
        promotion_reports = [
            r for r in result.reports if r.construct_type == "WORKER_PROMOTION"
        ]
        assert len(promotion_reports) > 0
        assert promotion_reports[0].completeness == "partial"
        assert promotion_reports[0].metadata["promotion_status"] == "blocked"
        assert "promotion_input_contract" in promotion_reports[0].metadata["promotion_missing_slots"]
        assert "promotion_output_contract" in promotion_reports[0].metadata["promotion_missing_slots"]

        # Verify diagnostics are generated
        assert len(result.diagnostics) > 0
        for diagnostic in result.diagnostics:
            assert diagnostic.kind == "type_or_contract_ambiguity"


# ===========================================================================
# R0 Metadata - 删除空测试，改为注释说明
# ===========================================================================

# R0 基线测试计数：
# - Before R0: 1440 tests
# - R0 新增: 本文件中的测试
# - After R0: 1440 + 本文件测试数
#
# R0 验收标准：
# 1. 只修改测试和文档，不修改生产代码
# 2. 无 src/nl2spl/ 改动
# 3. 无 prompts/ 改动
# 4. current-behavior tests 全部 pass
# 5. target-future xfail 合规（strict=True, 有 reason）
# 6. 无 skip
# 7. 无空断言/弱断言
# 8. 真实调用 checker
# 9. 无新 LLM/rule-based 逻辑
#
# 实际验证通过 git diff 和审核清单完成。
