# R1 Report Schema Foundation 实施计划

## 1. 阶段定位

R1 是 IRS v6 的 schema foundation 阶段。

目标是让当前 IRS report 数据结构具备 v6 所需的 parent/path/edge/frontier/cutline 表达能力，同时保持现有 Stage 4 / Stage 7 / Post-normalize 行为不变。

```text
R1 = schema compatibility expansion
R1 != checker migration
R1 != runner integration
R1 != diagnostic projector implementation
R1 != worker/delegation checker implementation
```

## 2. 阶段目标

R1 需要完成：

```text
1. 新增 ConstructEdge / ConstructGraph 的基础类型定义。
2. 新增 FrontierStatus / CutlineReason 的基础类型定义。
3. 兼容扩展 ConstructSatisfactionReport。
4. 保证旧 ConstructSatisfactionReport 构造方式完全可用。
5. 保证 Stage 4 / Stage 7 现有 checker 不需要同步大改。
6. 保证现有 diagnostics、renderer、orchestrator 行为不变。
7. 为 R2 compiler/irs framework skeleton 留好类型落点。
```

## 3. 允许修改范围

R1 允许修改生产代码，但范围必须严格限制在 schema/type foundation。

允许修改：

```text
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/__init__.py
src/nl2spl/compiler/irs/__init__.py
src/nl2spl/compiler/irs/graph.py
src/nl2spl/compiler/irs/frontier.py
tests/unit/
docs/implementation/irs-v6/
```

如果 `src/nl2spl/compiler/irs/` 目录尚不存在，R1 可以创建最小目录与类型文件。

R1 不允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py
src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/irs_prompt_builder.py
prompts/
examples/
output/
```

如实施者认为必须修改上述文件，必须先暂停并说明原因，不能直接实施。

## 4. 禁止事项

```text
1. 不迁移 Stage 4 / Stage 7 checker。
2. 不接入 IRSRunner。
3. 不实现 IRSChecker Protocol。
4. 不实现 DiagnosticProjector。
5. 不实现 Worker/Delegation checker。
6. 不改变 PostNormalizeIRSChecker。
7. 不改变 CompileDiagnostic 投影路径。
8. 不改变 final_spl / compile_report 输出。
9. 不新增 LLM 调用。
10. 不新增 rule-based 语义判断。
```

## 5. LLM / Rule-based 决策约束

R1 是纯 schema/type 扩展，不需要语义理解。

因此：

```text
1. 不允许新增 LLM 调用。
2. 不允许新增自然语言语义分类规则。
3. 不允许通过 rule-based 逻辑推断 parent/path/edge。
4. 不允许根据文本内容自动生成 ConstructEdge。
```

R1 只定义类型，不负责从真实 IR 中抽取 edge/path/frontier。

如果实施者认为需要在 R1 中根据 IR 或 NL 内容生成 edge，必须先请求确认；默认应推迟到 R4/R8。

## 6. 目标文件设计

### 6.1 `src/nl2spl/compiler/irs/graph.py`

定义：

```python
ConstructEdgeType = Literal[
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

@dataclass
class ConstructEdge:
    from_id: str
    to_id: str
    edge_type: ConstructEdgeType
    source_span_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class ConstructGraph:
    nodes: list[str] = field(default_factory=list)
    edges: list[ConstructEdge] = field(default_factory=list)
```

R1 只要求基础容器，不要求 traversal、validation、topological sort。

### 6.2 `src/nl2spl/compiler/irs/frontier.py`

定义：

```python
FrontierStatus = Literal[
    "continue",
    "leaf",
    "cutline_partial",
    "cutline_blocked",
]

CutlineReason = Literal[
    "missing_required_for_complete",
    "no_source_demand",
    "promotion_blocked",
    "non_renderable_candidate",
    "blocked_by_gate",
]
```

R1 可只定义 Literal 类型，不要求行为函数。

### 6.3 `src/nl2spl/compiler/construct_registry.py`

扩展 `ConstructSatisfactionReport`，新增字段必须全部有默认值：

```python
primary_parent_id: str | None = None
child_construct_ids: list[str] = field(default_factory=list)
related_edges: list[ConstructEdge] = field(default_factory=list)
construct_path: tuple[str, ...] = ()
source_span_ids: list[str] = field(default_factory=list)
source_section_id: str | None = None
source_packet_id: str | None = None
cutline_reason: CutlineReason | None = None
frontier_status: FrontierStatus = "leaf"
metadata: dict[str, Any] = field(default_factory=dict)
```

兼容要求：

```text
1. 旧调用 ConstructSatisfactionReport(... diagnostics=...) 不需要改。
2. 旧 checker 不传新字段时 frontier_status 默认为 leaf。
3. related_edges 默认为空列表，不能共享可变默认值。
4. metadata 默认为空 dict，不能共享可变默认值。
```

### 6.4 `src/nl2spl/compiler/irs/__init__.py`

导出：

```python
ConstructEdge
ConstructGraph
ConstructEdgeType
FrontierStatus
CutlineReason
```

是否从 `src/nl2spl/compiler/__init__.py` 顶层导出由实施者判断，但如果导出，必须加测试锁定。

## 7. 测试计划

建议新增：

```text
tests/unit/test_irs_v6_r1_report_schema.py
```

也可补充到已有 construct registry 测试，但推荐独立文件，便于阶段审核。

### 7.1 ConstructEdge tests

建议测试：

```text
test_r1_construct_edge_defaults_are_isolated
test_r1_construct_edge_preserves_source_spans_and_metadata
test_r1_construct_graph_defaults_are_isolated
```

验收点：

```text
1. ConstructEdge 默认 source_span_ids 是独立 list。
2. metadata 是独立 dict。
3. ConstructGraph 默认 nodes/edges 是独立 list。
4. edge_type 支持目标枚举值。
```

### 7.2 Frontier tests

建议测试：

```text
test_r1_frontier_status_literals_include_cutline_values
test_r1_cutline_reason_literals_include_promotion_blocked
```

验收点：

```text
1. FrontierStatus 包含 continue / leaf / cutline_partial / cutline_blocked。
2. CutlineReason 包含 promotion_blocked / no_source_demand。
```

如果 Literal 测试实现过于脆弱，可以通过构造 `ConstructSatisfactionReport(frontier_status=...)` 验证。

### 7.3 ConstructSatisfactionReport compatibility tests

建议测试：

```text
test_r1_report_legacy_constructor_still_works
test_r1_report_new_fields_have_defaults
test_r1_report_new_mutable_fields_are_isolated
test_r1_report_accepts_parent_path_edge_frontier_metadata
```

验收点：

```text
1. 只传旧字段仍可构造。
2. 新字段默认值正确。
3. child_construct_ids / related_edges / source_span_ids / metadata 不共享。
4. 可传 primary_parent_id / construct_path / source_section_id / source_packet_id。
5. 可传 frontier_status=cutline_partial 与 cutline_reason=promotion_blocked。
```

### 7.4 Existing checker compatibility tests

建议测试：

```text
test_r1_stage4_checker_reports_have_v6_defaults
test_r1_stage7_checker_reports_have_v6_defaults
```

验收点：

```text
1. 调用现有 Stage 4 checker 不需要改参数。
2. 生成 report 具有 frontier_status == "leaf"。
3. related_edges == []。
4. metadata == {}。
5. Stage 4 / Stage 7 原有核心断言仍成立。
```

## 8. 测试命令

R1 提交审核时至少提供：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_irs_v6_r1_report_schema.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_irs_v6_r0_baseline.py tests/unit/test_irs_v6_r1_report_schema.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/ -q --basetemp=.pytest-tmp
```

如果修改了 `src/nl2spl/compiler/__init__.py`，还应运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/ -q --basetemp=.pytest-tmp
```

## 9. 审核清单

审核时我会逐条核验：

```text
1. 是否只修改允许范围内文件。
2. 是否没有修改 orchestrator / Stage 4 checker / Stage 7 checker / PostNormalizeIRSChecker。
3. 是否没有 prompt、example、output 改动。
4. ConstructSatisfactionReport 旧构造方式是否仍可用。
5. 新增字段是否全部有默认值。
6. 可变默认值是否使用 default_factory。
7. ConstructEdge / FrontierStatus 是否定义在约定文件。
8. Stage 4 / Stage 7 现有 checker 是否无需修改即可生成带 v6 defaults 的 report。
9. 是否没有新增 LLM / rule-based 语义逻辑。
10. R0 baseline 是否仍通过。
11. full unit test suite 是否通过。
```

## 10. 提交审核时需要填写的信息

实施者提交 R1 审核时，请提供：

```text
1. 修改文件列表。
2. 新增类型列表。
3. ConstructSatisfactionReport 新增字段列表。
4. 兼容性说明：旧 checker 是否改动。
5. 测试命令与结果。
6. 是否修改生产行为：必须为否。
7. 是否引入 LLM/rule-based 新逻辑：必须为否。
8. 已知风险。
9. 后续 R2 依赖事项。
```

## 11. R1 完成标准

R1 完成必须满足：

```text
1. ConstructEdge / ConstructGraph 已定义在 compiler/irs/graph.py。
2. FrontierStatus / CutlineReason 已定义在 compiler/irs/frontier.py。
3. ConstructSatisfactionReport 已兼容扩展 v6 字段。
4. 所有新增字段有默认值。
5. 所有可变字段使用 default_factory。
6. Stage 4 / Stage 7 旧 checker 无需改动且测试通过。
7. R0 baseline 测试仍通过。
8. 全量单元测试通过。
9. 没有 prompt/example/output 改动。
10. 没有 LLM/rule-based 语义逻辑。
11. 进度跟踪 HTML 的 R1 区块已填写。
```

