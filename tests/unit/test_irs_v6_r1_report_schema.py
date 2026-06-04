"""R1 Report Schema Foundation: IRS v6 schema 扩展测试

本文件测试 IRS v6 新增的 schema/type foundation，确保：
1. ConstructEdge / ConstructGraph 基础类型正确
2. FrontierStatus / CutlineReason 类型正确
3. ConstructSatisfactionReport 兼容扩展
4. 旧 checker 无需修改即可生成带 v6 defaults 的 report

R1 规则：
1. 只测试 schema/type，不测试 checker 迁移
2. 不测试 IRSRunner / DiagnosticProjector
3. 不引入 LLM/rule-based 语义判断
4. 保证 R0 baseline 仍通过
"""

import typing

import pytest

from nl2spl.compiler.construct_registry import (
    ConstructCompleteness,
    ConstructSatisfactionReport,
    SlotSatisfaction,
    SPLConstructRegistry,
)
from nl2spl.compiler.irs import (
    ConstructEdge,
    ConstructEdgeType,
    ConstructGraph,
    CutlineReason,
    FrontierStatus,
)
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.pipeline.stages.stage4_flow_assembler.irs_checker import (
    check_exception_flows_irs,
)
from nl2spl.pipeline.stages.stage7_step_extractor.irs_checker import check_steps_irs


# ===========================================================================
# 7.1 ConstructEdge tests
# ===========================================================================


class TestR1ConstructEdge:
    """测试 ConstructEdge 基础类型"""

    def test_r1_construct_edge_defaults_are_isolated(self):
        """验证 ConstructEdge 默认值是独立的，不共享可变对象"""
        edge1 = ConstructEdge(from_id="a", to_id="b", edge_type="contains")
        edge2 = ConstructEdge(from_id="c", to_id="d", edge_type="produces")

        # 修改 edge1 不应影响 edge2
        edge1.source_span_ids.append("s1")
        edge1.metadata["key"] = "value"

        assert edge2.source_span_ids == []
        assert edge2.metadata == {}

    def test_r1_construct_edge_preserves_source_spans_and_metadata(self):
        """验证 ConstructEdge 可以保存 source spans 和 metadata"""
        edge = ConstructEdge(
            from_id="worker_main",
            to_id="step_1",
            edge_type="contains",
            source_span_ids=["s1", "s2"],
            metadata={"confidence": 0.9},
        )

        assert edge.from_id == "worker_main"
        assert edge.to_id == "step_1"
        assert edge.edge_type == "contains"
        assert edge.source_span_ids == ["s1", "s2"]
        assert edge.metadata == {"confidence": 0.9}

    def test_r1_construct_edge_type_supports_target_values(self):
        """验证 ConstructEdgeType 支持目标枚举值"""
        # 这些值应该都能通过类型检查
        edge_types: list[ConstructEdgeType] = [
            "contains",
            "produces",
            "consumes",
            "invokes",
            "handoff_to",
            "handles",
            "applies_to",
            "derived_from",
            "promotes_to",
            "blocked_by",
        ]

        for edge_type in edge_types:
            edge = ConstructEdge(from_id="a", to_id="b", edge_type=edge_type)
            assert edge.edge_type == edge_type


class TestR1ConstructGraph:
    """测试 ConstructGraph 基础类型"""

    def test_r1_construct_graph_defaults_are_isolated(self):
        """验证 ConstructGraph 默认值是独立的"""
        graph1 = ConstructGraph()
        graph2 = ConstructGraph()

        graph1.nodes.append("node1")
        graph1.edges.append(
            ConstructEdge(from_id="a", to_id="b", edge_type="contains")
        )

        assert graph2.nodes == []
        assert graph2.edges == []

    def test_r1_construct_graph_can_store_nodes_and_edges(self):
        """验证 ConstructGraph 可以存储 nodes 和 edges"""
        graph = ConstructGraph(
            nodes=["worker_main", "step_1", "step_2"],
            edges=[
                ConstructEdge(from_id="worker_main", to_id="step_1", edge_type="contains"),
                ConstructEdge(from_id="worker_main", to_id="step_2", edge_type="contains"),
                ConstructEdge(from_id="step_1", to_id="output_var", edge_type="produces"),
            ],
        )

        assert len(graph.nodes) == 3
        assert len(graph.edges) == 3
        assert graph.edges[0].edge_type == "contains"
        assert graph.edges[2].edge_type == "produces"


# ===========================================================================
# 7.2 Frontier tests
# ===========================================================================


class TestR1Frontier:
    """测试 FrontierStatus 和 CutlineReason 类型"""

    def test_r1_frontier_status_literals_include_cutline_values(self):
        """验证 FrontierStatus 包含所需的 literal 值"""
        # 通过构造 ConstructSatisfactionReport 验证类型
        statuses: list[FrontierStatus] = [
            "continue",
            "leaf",
            "cutline_partial",
            "cutline_blocked",
        ]

        for status in statuses:
            report = ConstructSatisfactionReport(
                construct_id="test",
                construct_type="TEST",
                slots=[],
                completeness="complete",
                renderable=True,
                frontier_status=status,
            )
            assert report.frontier_status == status

    def test_r1_cutline_reason_literals_include_promotion_blocked(self):
        """验证 CutlineReason 包含所需的 literal 值"""
        reasons: list[CutlineReason] = [
            "missing_required_for_complete",
            "no_source_demand",
            "promotion_blocked",
            "non_renderable_candidate",
            "blocked_by_gate",
        ]

        for reason in reasons:
            report = ConstructSatisfactionReport(
                construct_id="test",
                construct_type="TEST",
                slots=[],
                completeness="partial",
                renderable=False,
                cutline_reason=reason,
                frontier_status="cutline_blocked",
            )
            assert report.cutline_reason == reason


# ===========================================================================
# 7.3 ConstructSatisfactionReport compatibility tests
# ===========================================================================


class TestR1ConstructSatisfactionReportCompatibility:
    """测试 ConstructSatisfactionReport 兼容性扩展"""

    def test_r1_report_v6_type_contract_is_enforced(self):
        """验证 v6 字段绑定到真实类型，而不是裸 list/str"""
        type_hints = typing.get_type_hints(ConstructSatisfactionReport)

        # 验证 related_edges 绑定到 list[ConstructEdge]
        related_edges_type = type_hints["related_edges"]
        assert hasattr(related_edges_type, "__origin__")
        assert related_edges_type.__origin__ is list
        assert related_edges_type.__args__[0] is ConstructEdge

        # 验证 cutline_reason 绑定到 CutlineReason | None
        cutline_reason_type = type_hints["cutline_reason"]
        # Python 3.10+ uses types.UnionType, earlier uses typing.Union
        if hasattr(cutline_reason_type, "__args__"):
            # Union type
            args = cutline_reason_type.__args__
            # Should be (Literal[...], None) or similar
            assert type(None) in args
            # The other arg should be the Literal type (CutlineReason)
            non_none_args = [a for a in args if a is not type(None)]
            assert len(non_none_args) == 1
            # CutlineReason is a Literal, check it has __origin__
            cutline_literal = non_none_args[0]
            assert hasattr(cutline_literal, "__origin__")
        else:
            # Might be just the type itself in some edge cases
            pass

        # 验证 frontier_status 绑定到 FrontierStatus (Literal)
        frontier_status_type = type_hints["frontier_status"]
        assert hasattr(frontier_status_type, "__origin__")
        # FrontierStatus is a Literal type

    def test_r1_report_legacy_constructor_still_works(self):
        """验证只传旧字段仍可构造 report"""
        # 这是 R0 baseline 中使用的构造方式
        report = ConstructSatisfactionReport(
            construct_id="exc_1",
            construct_type="EXCEPTION_FLOW",
            slots=[
                SlotSatisfaction(
                    slot_name="condition",
                    status="satisfied",
                    source_span_ids=["s1"],
                )
            ],
            completeness="partial",
            renderable=True,
            diagnostics=[],
        )

        assert report.construct_id == "exc_1"
        assert report.construct_type == "EXCEPTION_FLOW"
        assert report.completeness == "partial"
        assert report.renderable is True

    def test_r1_report_new_fields_have_defaults(self):
        """验证新字段有正确的默认值"""
        report = ConstructSatisfactionReport(
            construct_id="test",
            construct_type="TEST",
            slots=[],
            completeness="complete",
            renderable=True,
        )

        # 验证所有新字段的默认值
        assert report.primary_parent_id is None
        assert report.child_construct_ids == []
        assert report.related_edges == []
        assert report.construct_path == ()
        assert report.source_span_ids == []
        assert report.source_section_id is None
        assert report.source_packet_id is None
        assert report.cutline_reason is None
        assert report.frontier_status == "leaf"
        assert report.metadata == {}

    def test_r1_report_new_mutable_fields_are_isolated(self):
        """验证新增可变字段不共享默认值"""
        report1 = ConstructSatisfactionReport(
            construct_id="test1",
            construct_type="TEST",
            slots=[],
            completeness="complete",
            renderable=True,
        )
        report2 = ConstructSatisfactionReport(
            construct_id="test2",
            construct_type="TEST",
            slots=[],
            completeness="complete",
            renderable=True,
        )

        # 修改 report1 不应影响 report2
        report1.child_construct_ids.append("child1")
        report1.related_edges.append(
            ConstructEdge(from_id="a", to_id="b", edge_type="contains")
        )
        report1.source_span_ids.append("s1")
        report1.metadata["key"] = "value"

        assert report2.child_construct_ids == []
        assert report2.related_edges == []
        assert report2.source_span_ids == []
        assert report2.metadata == {}

    def test_r1_report_accepts_parent_path_edge_frontier_metadata(self):
        """验证可以传递所有新字段"""
        edge = ConstructEdge(
            from_id="worker_main",
            to_id="step_1",
            edge_type="contains",
        )

        report = ConstructSatisfactionReport(
            construct_id="step_1",
            construct_type="GENERAL_COMMAND",
            slots=[],
            completeness="complete",
            renderable=True,
            primary_parent_id="worker_main",
            child_construct_ids=["substep_1"],
            related_edges=[edge],
            construct_path=("worker_main", "step_1"),
            source_span_ids=["s1", "s2"],
            source_section_id="section_1",
            source_packet_id="packet_1",
            cutline_reason="promotion_blocked",
            frontier_status="cutline_blocked",
            metadata={"confidence": 0.9},
        )

        assert report.primary_parent_id == "worker_main"
        assert report.child_construct_ids == ["substep_1"]
        assert len(report.related_edges) == 1
        assert report.related_edges[0].edge_type == "contains"
        assert report.construct_path == ("worker_main", "step_1")
        assert report.source_span_ids == ["s1", "s2"]
        assert report.source_section_id == "section_1"
        assert report.source_packet_id == "packet_1"
        assert report.cutline_reason == "promotion_blocked"
        assert report.frontier_status == "cutline_blocked"
        assert report.metadata == {"confidence": 0.9}


# ===========================================================================
# 7.4 Existing checker compatibility tests
# ===========================================================================


class TestR1ExistingCheckerCompatibility:
    """测试现有 checker 无需修改即可生成带 v6 defaults 的 report"""

    def test_r1_stage4_checker_reports_have_v6_defaults(self):
        """验证 Stage 4 checker 生成的 report 具有 v6 默认值"""
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

        reports, diagnostics = check_exception_flows_irs(flow)

        assert len(reports) == 1
        report = reports[0]

        # 验证旧字段仍正确
        assert report.construct_id == "exception_flow:exc_1"
        assert report.construct_type == "EXCEPTION_FLOW"
        assert report.completeness == "partial"
        assert report.renderable is True

        # R6.4: frontier_status now set by v6 checker (cutline_partial for source-backed)
        assert report.frontier_status == "cutline_partial"
        # R8.3: exception flow now has handles condition edge
        assert len(report.related_edges) >= 1
        handles = [e for e in report.related_edges if e.edge_type == "handles"]
        assert len(handles) == 1
        # R6.4: metadata now contains exception_flow_ir and worker_id
        assert "exception_flow_ir" in report.metadata
        assert report.child_construct_ids == []
        # R6.4: source_span_ids now populated from ExceptionFlow.spans
        assert report.source_span_ids == ["s20"]

    def test_r1_stage7_checker_reports_have_v6_defaults(self):
        """验证 Stage 7 checker 生成的 report 具有 v6 默认值"""
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
        report = reports[0]

        # 验证旧字段仍正确
        assert report.construct_id == "step:st_1"
        assert report.construct_type == "GENERAL_COMMAND"
        assert report.completeness == "complete"
        assert report.renderable is True

        # R6.4: v6 checker sets frontier_status, construct_path, metadata
        assert report.frontier_status == "leaf"
        assert report.related_edges == []
        assert "step_ir" in report.metadata
        assert report.primary_parent_id is None
        # R6.4: construct_path now populated by v6 checker
        assert report.construct_path == ("steps", "st_1")

    def test_r1_stage4_checker_core_assertions_still_hold(self):
        """验证 Stage 4 checker 的核心断言仍成立（来自 R0 baseline）"""
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Handle errors",
                    spans=[],
                )
            ],
        )

        reports, diagnostics = check_exception_flows_irs(flow)

        # R0 baseline 断言
        assert len(reports) == 1
        assert reports[0].renderable is False
        assert len(diagnostics) == 1
        assert diagnostics[0].kind == "type_or_contract_ambiguity"

    def test_r1_stage7_checker_core_assertions_still_hold(self):
        """验证 Stage 7 checker 的核心断言仍成立（来自 R0 baseline）"""
        step = StepIR(
            step_id="st_1",
            text="Process data",
            source_span_ids=[],  # 无 source
            command_type="GENERAL_COMMAND",
            inputs=[],
            outputs=[],
            flow_ref="main",
            block_ref="b_1",
        )

        reports, diagnostics = check_steps_irs([step])

        # R0 baseline 断言
        assert len(reports) == 1
        assert reports[0].renderable is False
        assert len(diagnostics) == 1
        assert diagnostics[0].kind == "assumed_command_not_renderable"


# ===========================================================================
# R1 Metadata - 不创建空测试，只用注释说明
# ===========================================================================

# R1 schema foundation 完成标准：
# 1. ConstructEdge / ConstructGraph 已定义在 compiler/irs/graph.py
# 2. FrontierStatus / CutlineReason 已定义在 compiler/irs/frontier.py
# 3. ConstructSatisfactionReport 已兼容扩展 v6 字段
# 4. 所有新增字段有默认值
# 5. 所有可变字段使用 default_factory
# 6. Stage 4 / Stage 7 旧 checker 无需改动且测试通过
# 7. R0 baseline 测试仍通过
# 8. 全量单元测试通过
# 9. 没有 prompt/example/output 改动
# 10. 没有 LLM/rule-based 语义逻辑
