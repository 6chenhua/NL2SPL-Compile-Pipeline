# R2 IRS v6 Framework Skeleton 实施计划

## 1. 阶段定位

R2 是 IRS v6 的框架骨架阶段。

R1 已经完成 `ConstructSatisfactionReport` 的 v6 schema 扩展，并新增了 graph/frontier 基础类型。R2 的目标是在 `src/nl2spl/compiler/irs/` 下补齐后续 checker 可插拔接入所需的基础接口与调度骨架，但不把任何现有 Stage 4 / Stage 7 / Post-normalize checker 迁移到新框架，也不接入 orchestrator。

```text
R2 = framework skeleton / extension seam
R2 != checker migration
R2 != Worker/Delegation IRS implementation
R2 != DiagnosticProjector full semantics
R2 != orchestrator integration
R2 != recursive IRS evaluator
```

R2 完成后，项目应该具备以下能力：

```text
1. 可以定义一个 v6 checker。
2. 可以把 checker 注册到 registry。
3. 可以用 runner 在指定 stage 上调度 checker。
4. 可以从 context 中抽取 ConstructInstance。
5. 可以返回 ConstructSatisfactionReport。
6. 空 registry / 空 checker 场景不改变任何 pipeline 行为。
7. 未来 R3/R4 可以在此基础上实现 DiagnosticProjector 与 Worker/Delegation checker。
```

## 2. 阶段目标

R2 需要完成：

```text
1. 新增 IRSCheckContext。
2. 新增 ConstructInstance。
3. 新增 IRSChecker Protocol。
4. 新增 IRSCheckerRegistry。
5. 新增 IRSRunner skeleton。
6. 新增 DiagnosticProjector skeleton。
7. 扩展 compiler/irs/__init__.py 导出 R2 类型。
8. 增加 R2 单元测试，验证 import、registry、runner、context、instance、projector skeleton 行为。
9. 保证 R0/R1 baseline 继续通过。
10. 保证全量单元测试通过。
```

R2 不需要实现任何 NL 语义分类，也不需要根据文本内容推断 worker、flow、step、edge 或 slot。

## 3. 允许修改范围

R2 允许新增或修改：

```text
src/nl2spl/compiler/irs/__init__.py
src/nl2spl/compiler/irs/context.py
src/nl2spl/compiler/irs/instance.py
src/nl2spl/compiler/irs/checker.py
src/nl2spl/compiler/irs/registry.py
src/nl2spl/compiler/irs/runner.py
src/nl2spl/compiler/irs/projector.py
tests/unit/compiler/irs/
tests/unit/test_irs_v6_r2_framework_skeleton.py
docs/implementation/irs-v6/
```

如果测试目录 `tests/unit/compiler/irs/` 尚不存在，可以创建。推荐优先使用：

```text
tests/unit/compiler/irs/test_r2_framework_skeleton.py
```

R2 可以读取 R1 已新增的：

```text
src/nl2spl/compiler/irs/graph.py
src/nl2spl/compiler/irs/frontier.py
src/nl2spl/compiler/construct_registry.py
src/nl2spl/compiler/diagnostic_registry.py
src/nl2spl/ir/diagnostics.py
```

但 R2 不应修改 `construct_registry.py`，除非发现 R1 schema 存在阻塞 R2 的明确 bug。若确需修改，提交审核时必须单独说明原因。

## 4. 禁止修改范围

R2 不允许修改：

```text
src/nl2spl/pipeline/orchestrator.py
src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py
src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py
src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py
src/nl2spl/pipeline/executable_gate.py
src/nl2spl/compiler/irs_prompt_builder.py
src/nl2spl/config.py
prompts/
examples/
output/
```

R2 不增加 feature flag。Runner 还不接入 pipeline，因此不需要配置开关。

## 5. LLM / Rule-based 决策约束

R2 是接口与调度骨架，不需要语义理解。

禁止事项：

```text
1. 不新增 LLM 调用。
2. 不新增自然语言语义分类规则。
3. 不根据 span text 推断 construct_type。
4. 不根据 worker 名称、section 名称或 packet 名称推断 promotion readiness。
5. 不自动生成 Worker/Delegation report。
6. 不自动生成 ConstructEdge。
7. 不根据 missing slot 生成新的 IR construct。
```

如果实施时认为某个测试需要“判断文本语义”，必须暂停并向我确认：这个判断应由 LLM、rule-based 逻辑，还是推迟到 R4 的 checker 专项任务。未经确认，不允许把语义规则混入 R2。

## 6. 目标模块设计

### 6.1 `context.py`

新增 `IRSCheckContext`。

建议字段：

```python
@dataclass(frozen=True)
class IRSCheckContext:
    stage_name: str
    spans: list[Any] = field(default_factory=list)
    routes: Any | None = None
    flow: Any | None = None
    block_plan: Any | None = None
    resources: Any | None = None
    steps: list[Any] = field(default_factory=list)
    worker_plan: Any | None = None
    worker_flows: Any | None = None
    worker_blocks: Any | None = None
    worker_steps: Any | None = None
    profile: Any | None = None
    constraints: Any | None = None
    normalized_ir: Any | None = None
    symbol_table: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

设计要求：

```text
1. Context 是只读输入容器，推荐 frozen=True。
2. Context 允许多数 IR 字段为空，以支持不同 stage。
3. Context 不提供 mutating helper。
4. Context 不负责从真实 pipeline artifact 中推断 construct。
5. metadata 用于测试或未来 stage-local 附加信息，不承载语义推断。
```

如果 `frozen=True` 与可变 list/dict 默认值的使用方式产生测试复杂度，可以保留 dataclass 非 frozen，但必须在文档和 Protocol 中说明 checker 不得修改 context 内 IR。推荐仍使用 `frozen=True`，因为 R2 的目标是建立只读边界。

### 6.2 `instance.py`

新增 `ConstructInstance`。

建议字段：

```python
@dataclass
class ConstructInstance:
    construct_id: str
    construct_type: str
    ir_ref: Any | None = None
    materialized: bool = True
    source_demanded: bool = True
    candidate_only: bool = False
    primary_parent_id: str | None = None
    child_construct_ids: list[str] = field(default_factory=list)
    related_edges: list[ConstructEdge] = field(default_factory=list)
    construct_path: tuple[str, ...] = ()
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

状态语义：

```text
materialized=True:
    IR 中已经存在的 construct。

source_demanded=True:
    source evidence 要求系统考虑该 construct 或候选 construct。

candidate_only=True:
    只表示候选或 blocked promotion，不表示已经生成可渲染 construct。
```

典型未来用法：

```text
WORKER_CANDIDATE:
    materialized=False
    source_demanded=True
    candidate_only=True

WORKER_PROMOTION:
    materialized=False
    source_demanded=True
    candidate_only=True

CHILD_WORKER:
    materialized=True
    source_demanded=True
    candidate_only=False
```

R2 只定义状态字段和测试默认值，不实现 Worker/Delegation 语义。

### 6.3 `checker.py`

新增 `IRSChecker` Protocol。

建议接口：

```python
class IRSChecker(Protocol):
    checker_id: str
    supported_construct_types: tuple[str, ...]
    supported_stages: tuple[str, ...]

    def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
        ...

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        ...
```

Checker contract 必须写入 docstring：

```text
1. checker 不调用 LLM。
2. checker 不修改 IR。
3. checker 不生成新的 SPL construct。
4. checker 不补全缺失 slot。
5. checker 不直接拼装最终 CompileDiagnostic。
6. checker 不为没有 source demand 的 child construct 制造 report。
```

R2 不要求在运行时强制检测 “不修改 IR”，但测试中应至少用 fake checker 验证正常 checker 不需要 mutate context 才能运行。运行时 mutation guard 可留给后续 hardening。

### 6.4 `registry.py`

新增 `IRSCheckerRegistry`。

建议能力：

```python
class IRSCheckerRegistry:
    def register(self, checker: IRSChecker) -> None: ...
    def get_for_stage(self, stage_name: str) -> list[IRSChecker]: ...
    def get_for_construct_type(self, construct_type: str) -> list[IRSChecker]: ...
    def get_for_stage_and_construct_type(
        self,
        stage_name: str,
        construct_type: str,
    ) -> list[IRSChecker]: ...
```

验收行为：

```text
1. 空 registry 查询返回 []。
2. register 后可按 stage 查询。
3. register 后可按 construct_type 查询。
4. stage + construct_type 双条件查询正确过滤。
5. 重复 checker_id 应被拒绝，抛 ValueError。
6. 查询结果顺序稳定，按注册顺序返回。
```

R2 不需要自动 discover checker，也不需要 plugin loading。

### 6.5 `projector.py`

新增 `DiagnosticProjector` skeleton。

R2 的 projector 只做安全空投影，不实现完整 report -> CompileDiagnostic 语义。完整投影规则属于 R3。

建议接口：

```python
@dataclass
class DiagnosticProjectionResult:
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DiagnosticProjector:
    def project(
        self,
        reports: list[ConstructSatisfactionReport],
        context: IRSCheckContext,
    ) -> DiagnosticProjectionResult:
        return DiagnosticProjectionResult()
```

R2 projector skeleton 的预期效果：

```text
1. 可 import。
2. 可实例化。
3. 空 reports 返回空 diagnostics。
4. 非空 reports 在 R2 仍不生成 diagnostics，避免提前实现 R3。
5. 不修改 report。
```

如果实施者认为 R2 需要从 slot.diagnostic_kind 生成 CompileDiagnostic，必须停止；这是 R3 的职责。

### 6.6 `runner.py`

新增 `IRSRunner`。

建议结果类型：

```python
@dataclass
class IRSRunResult:
    reports: list[ConstructSatisfactionReport] = field(default_factory=list)
    diagnostics: list[CompileDiagnostic] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

建议接口：

```python
class IRSRunner:
    def __init__(
        self,
        registry: IRSCheckerRegistry | None = None,
        construct_registry: SPLConstructRegistry | None = None,
        projector: DiagnosticProjector | None = None,
    ) -> None: ...

    def run_stage(
        self,
        stage_name: str,
        context: IRSCheckContext,
    ) -> IRSRunResult: ...
```

Runner 行为：

```text
1. 空 registry -> reports=[], diagnostics=[], warnings=[]。
2. 找到 stage checker 后，调用 extract_instances(context)。
3. 对每个 instance，根据 instance.construct_type 从 SPLConstructRegistry 获取 ConstructIRS。
4. 如果 construct_type 未注册，跳过该 instance，并记录 warning。
5. 对已注册 construct，调用 checker.check_instance(instance, irs, context)。
6. 收集 reports。
7. 调用 DiagnosticProjector.project(reports, context)。
8. 返回 IRSRunResult。
```

R2 runner 不接 orchestrator，不写 intermediate，不写 checkpoint。

未注册 construct_type 的处理建议为 warning 而不是 exception，原因是 R2 是骨架阶段；R4/R5 可以根据需要收紧。

### 6.7 `__init__.py`

扩展 `src/nl2spl/compiler/irs/__init__.py` 导出：

```text
ConstructEdge
ConstructEdgeType
ConstructGraph
FrontierStatus
CutlineReason
IRSCheckContext
ConstructInstance
IRSChecker
IRSCheckerRegistry
IRSRunner
IRSRunResult
DiagnosticProjector
DiagnosticProjectionResult
```

导出测试必须覆盖至少一个从 `nl2spl.compiler.irs import ...` 的路径。

## 7. 测试计划

建议新增：

```text
tests/unit/compiler/irs/test_r2_framework_skeleton.py
```

如果该目录结构会造成现有测试发现问题，也可以使用：

```text
tests/unit/test_irs_v6_r2_framework_skeleton.py
```

但推荐新目录，因为 R2 开始进入 `compiler/irs` 子包测试。

### 7.1 Context tests

建议测试：

```text
test_context_allows_stage_only_construction
test_context_accepts_partial_stage_artifacts
test_context_metadata_default_is_isolated
```

验收点：

```text
1. 只传 stage_name 可构造。
2. spans/routes/flow/steps/worker_plan 等字段可选。
3. metadata 默认 dict 不共享。
4. context 不在构造时推断任何 construct。
```

### 7.2 ConstructInstance tests

建议测试：

```text
test_instance_defaults_represent_materialized_source_demanded_construct
test_instance_can_represent_candidate_only_source_demand
test_instance_mutable_defaults_are_isolated
test_instance_preserves_parent_path_source_and_edges
```

验收点：

```text
1. 默认 materialized=True, source_demanded=True, candidate_only=False。
2. 可显式构造 candidate_only=True 的候选 instance。
3. child_construct_ids / related_edges / source_span_ids / metadata 默认不共享。
4. parent/path/source 字段可保存。
```

### 7.3 Checker protocol tests

建议用 fake checker：

```python
class FakeChecker:
    checker_id = "fake"
    supported_construct_types = ("GENERAL_COMMAND",)
    supported_stages = ("stage_fake",)

    def extract_instances(...): ...
    def check_instance(...): ...
```

建议测试：

```text
test_fake_checker_satisfies_protocol_shape
test_checker_contract_docstring_mentions_no_llm_no_ir_mutation_no_construct_generation
```

验收点：

```text
1. fake checker 可以被 registry/runner 使用。
2. Protocol 不要求 checker 继承具体 base class。
3. checker contract 文档明确禁止越界职责。
```

### 7.4 Registry tests

建议测试：

```text
test_registry_empty_queries_return_empty_lists
test_registry_register_and_query_by_stage
test_registry_register_and_query_by_construct_type
test_registry_query_by_stage_and_construct_type
test_registry_rejects_duplicate_checker_id
test_registry_preserves_registration_order
```

验收点：

```text
1. 空查询稳定返回 []。
2. stage 过滤正确。
3. construct_type 过滤正确。
4. 双条件过滤正确。
5. duplicate checker_id 抛 ValueError。
6. 注册顺序稳定。
```

### 7.5 Projector skeleton tests

建议测试：

```text
test_projector_empty_reports_returns_empty_result
test_projector_non_empty_reports_still_does_not_emit_diagnostics_in_r2
test_projector_does_not_mutate_reports
```

验收点：

```text
1. R2 projector 不提前实现 R3。
2. 不修改输入 report。
3. 结果对象字段稳定。
```

### 7.6 Runner tests

建议测试：

```text
test_runner_empty_registry_returns_empty_result
test_runner_invokes_registered_checker_for_stage
test_runner_filters_checker_by_stage
test_runner_uses_construct_registry_to_fetch_irs
test_runner_warns_and_skips_unknown_construct_type
test_runner_calls_projector_after_collecting_reports
```

验收点：

```text
1. 空 registry 不报错。
2. stage 匹配时调用 checker。
3. stage 不匹配时不调用 checker。
4. construct_type 已注册时生成 report。
5. construct_type 未注册时不崩溃，返回 warning。
6. projector 被调用，R2 diagnostics 仍为空。
```

### 7.7 Compatibility tests

建议测试：

```text
test_r0_r1_public_imports_still_work
test_existing_stage4_stage7_checkers_not_required_to_use_runner
```

验收点：

```text
1. R1 graph/frontier imports 保持可用。
2. Stage 4 / Stage 7 旧 checker 不需要改为 v6 checker。
```

## 8. 测试命令

R2 提交审核时至少提供：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/compiler/irs/test_r2_framework_skeleton.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_irs_v6_r0_baseline.py tests/unit/test_irs_v6_r1_report_schema.py tests/unit/compiler/irs/test_r2_framework_skeleton.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/ -q --basetemp=.pytest-tmp-r2
```

如果选择测试文件路径 `tests/unit/test_irs_v6_r2_framework_skeleton.py`，命令中替换对应路径。

由于当前环境可能存在 `.pytest_cache` 或 `.pytest-tmp` 权限噪声，允许使用新的 workspace 内 basetemp，例如：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/ -q --basetemp=.pytest-tmp-r2-review
```

测试结束后可清理本阶段创建的临时目录，但不要删除不确定来源的目录。

## 9. 审核清单

审核时我会逐条核验：

```text
1. 是否只修改 R2 允许范围内文件。
2. 是否没有修改 orchestrator。
3. 是否没有修改 Stage 4 / Stage 7 / Post-normalize checker。
4. 是否没有修改 config、prompts、examples、output。
5. 是否没有新增 LLM 调用。
6. 是否没有新增 rule-based NL 语义判断。
7. IRSCheckContext 是否只是只读/输入容器。
8. ConstructInstance 是否包含 materialized/source_demanded/candidate_only。
9. IRSChecker Protocol 是否明确 checker 职责边界。
10. Registry 是否支持注册、查询、重复 checker_id 拒绝、顺序稳定。
11. Runner 空 registry 是否返回空结果。
12. Runner 是否按 stage 过滤 checker。
13. Runner 是否按 construct_type 获取 IRS。
14. 未注册 construct_type 是否 warning + skip，而不是崩溃或生成伪 report。
15. DiagnosticProjector 是否只是 skeleton，没有提前实现 R3 语义。
16. R0/R1/R2 测试是否通过。
17. 全量单元测试是否通过。
```

## 10. 提交审核时需要填写的信息

实施者提交 R2 审核时，请提供：

```text
1. 修改文件列表。
2. 新增类型列表。
3. IRSCheckContext 字段列表。
4. ConstructInstance 字段列表。
5. IRSChecker Protocol 方法列表。
6. Registry 行为说明。
7. Runner 行为说明。
8. Projector skeleton 行为说明。
9. 测试命令与结果。
10. 是否修改 orchestrator：必须为否。
11. 是否修改 Stage 4 / Stage 7 / Post-normalize checker：必须为否。
12. 是否修改 prompts/examples/output：必须为否。
13. 是否新增 LLM/rule-based 语义逻辑：必须为否。
14. 已知风险。
15. 后续 R3/R4 依赖事项。
```

## 11. R2 完成标准

R2 完成必须满足：

```text
1. IRSCheckContext 已定义并可 import。
2. ConstructInstance 已定义并可表达 materialized/source_demanded/candidate_only。
3. IRSChecker Protocol 已定义并包含 extract_instances / check_instance。
4. IRSCheckerRegistry 支持注册、查询、重复 checker_id 拒绝、顺序稳定。
5. IRSRunner 支持空 registry 安全返回。
6. IRSRunner 支持 fake checker 调度并返回 ConstructSatisfactionReport。
7. IRSRunner 对未知 construct_type 返回 warning 并跳过。
8. DiagnosticProjector skeleton 可 import、可调用、R2 不生成 diagnostics。
9. `nl2spl.compiler.irs` 顶层导出 R2 类型。
10. 没有 orchestrator 接入。
11. 没有旧 checker 迁移。
12. 没有 Worker/Delegation checker。
13. 没有新增 LLM 或 rule-based 语义判断。
14. R0 baseline 测试通过。
15. R1 schema 测试通过。
16. R2 framework skeleton 测试通过。
17. 全量单元测试通过。
18. 进度跟踪 HTML 的 R2 区块已填写。
```

## 12. 后续阶段衔接

R2 为 R3/R4 提供基础接口：

```text
R3 DiagnosticProjector:
    在 R2 projector skeleton 上实现 report/slot -> CompileDiagnostic。

R4 Worker/Delegation Checker:
    使用 R2 IRSChecker、ConstructInstance、IRSRunner、Registry。

R5 Runner Orchestrator Integration:
    将 R2 runner 接入 orchestrator，但只在 feature flag 开启时运行。
```

R2 不解决 internal-comms-3 Issue 3。Issue 3 的结构化解释应在 R4 Worker/Delegation checker 与 R5 runner integration 后形成。

