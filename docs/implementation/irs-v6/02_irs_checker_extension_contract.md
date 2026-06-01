# IRS Checker 扩展契约

## 目标

本文档定义新增 IRS checker 时必须遵守的接口、输出、诊断和测试标准。目标是让 IRS 新增变成局部、可审核、可回归的工程动作。

## 新增 IRS 的标准步骤

### Step 1：定义或确认 ConstructIRS

在 construct registry 中确认 construct 类型存在。例如：

```text
WORKER_CANDIDATE
WORKER_PROMOTION
CHILD_WORKER
WORKER_HANDOFF
BLOCK
SEQUENTIAL_BLOCK
IF_BLOCK
LOOP_BLOCK
```

每个 construct 必须明确定义：

1. `existence_policy`
2. `source_signals`
3. required-for-partial slots
4. required-for-complete slots
5. `partial_rendering_allowed`
6. `missing_diagnostic`
7. `no_demand_behavior`

### Step 2：实现 ConstructInstance 提取

checker 必须先把 stage IR 转成标准 construct instance。

示例：

```text
WorkerPlanIR.candidates[]
-> ConstructInstance(type=WORKER_CANDIDATE, source_demanded=True, candidate_only=True)

WorkerPlanIR.candidates[]
-> ConstructInstance(type=WORKER_PROMOTION, source_demanded=True, candidate_only=True)

WorkerPlanIR.workers[kind=child]
-> ConstructInstance(type=CHILD_WORKER, materialized=True)

WorkerHandoffIR
-> ConstructInstance(type=WORKER_HANDOFF, materialized=True)
```

提取实例时必须保留：

```text
construct_id
construct_type
primary_parent_id
construct_path
source_span_ids
ir_ref
materialized
source_demanded
candidate_only
metadata
```

### Step 3：检查 slot satisfaction

checker 只能判断当前 construct 的 slot，不应在这里生成不存在的 child construct。

示例：

```text
WORKER_CANDIDATE.responsibility
WORKER_CANDIDATE.delegation_signal
WORKER_PROMOTION.promotion_input_contract
WORKER_PROMOTION.promotion_output_contract
WORKER_PROMOTION.promotion_invocation_point
WORKER_PROMOTION.promotion_result_handoff
```

### Step 4：生成 ConstructSatisfactionReport

report 必须能被后续 consolidation、feedback report 和未来递归 checker 使用。

正式 schema 应优先采用显式字段，并提供默认值以兼容 v5 测试：

```python
@dataclass
class ConstructSatisfactionReport:
    construct_id: str
    construct_type: str
    slots: list[SlotSatisfaction]
    completeness: ConstructCompleteness
    renderable: bool
    diagnostics: list = field(default_factory=list)

    primary_parent_id: str | None = None
    child_construct_ids: list[str] = field(default_factory=list)
    related_edges: list[ConstructEdge] = field(default_factory=list)
    construct_path: tuple[str, ...] = ()
    source_span_ids: list[str] = field(default_factory=list)
    cutline_reason: str | None = None
    frontier_status: Literal[
        "continue",
        "cutline_partial",
        "cutline_blocked",
        "leaf",
    ] = "leaf"
    metadata: dict[str, Any] = field(default_factory=dict)
```

如果短期不能修改 dataclass，可先放入 metadata，但正式实现应扩展 schema。

### Step 5：投影 CompileDiagnostic

推荐流程：

```text
IRSChecker
  -> ConstructSatisfactionReport / SlotSatisfaction
  -> DiagnosticProjector
  -> CompileDiagnostic
```

checker 不应各自拼装完整 diagnostic message。

如果 MVP 阶段 checker 暂时直接返回 diagnostics，也必须符合下面要求，并在后续迁移到 projector：

1. 使用已注册 diagnostic kind。
2. 设置稳定 `target_ref`。
3. 携带 `source_span_ids`。
4. 区分 `blocks_rendering` 和 `blocks_completion`。
5. 不把 report-only ambiguity 误标成 render-blocking。

## Checker 接口草案

```python
class IRSChecker(Protocol):
    checker_id: str
    stage_names: frozenset[str]
    construct_types: frozenset[str]

    def extract_instances(
        self,
        ir: object,
        context: IRSCheckContext,
    ) -> list[ConstructInstance]:
        ...

    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        ...

    def diagnostics_for_report(
        self,
        report: ConstructSatisfactionReport,
        context: IRSCheckContext,
    ) -> list[CompileDiagnostic]:
        ...
```

`diagnostics_for_report()` 是兼容方法。新 checker 应优先依赖 `DiagnosticProjector`。

## Runner 接口草案

```python
class IRSRunner:
    def __init__(
        self,
        construct_registry: SPLConstructRegistry,
        checker_registry: IRSCheckerRegistry,
        diagnostic_projector: DiagnosticProjector,
    ) -> None:
        ...

    def run_stage(
        self,
        stage_name: str,
        ir: object,
        context: IRSCheckContext,
    ) -> tuple[list[ConstructSatisfactionReport], list[CompileDiagnostic]]:
        ...
```

## Checker 不能做的事

IRS checker 不得：

1. 调用 LLM。
2. 生成新的 SPL construct。
3. 修改输入 IR。
4. 补全缺失 slot。
5. 为缺失 child evidence 制造 child construct report。
6. 把 candidate-only construct 当成可渲染 SPL construct。

checker 只负责裁决已经 materialized 或 source-demanded 的 construct。

## ConstructInstance 状态语义

| 状态 | 行为 |
| --- | --- |
| `materialized=True` | 检查 materialized construct 的 IRS |
| `source_demanded=True, candidate_only=True` | 生成 report-only satisfaction，不渲染 SPL construct |
| `materialized=False, source_demanded=False` | 不应创建 instance，也不应产生 diagnostic |
| `candidate_only=True` | 不得被 renderer 或 gate 当成可执行 construct |

## 和 Validator / Gate 的边界

### WorkerPlanValidator

`WorkerPlanValidator` 检查结构合法性，例如 ID、enum、handoff binding 是否引用合法字段。

IRS checker 检查信息需求满足度，例如 child worker 是否有足够 source-backed contract 可以被 materialized。

二者可以共享辅助函数，但职责不同。

### DiagnosticProjector

`DiagnosticProjector` 负责把 report 中的 missing slot、diagnostic kind、source evidence 统一转成 `CompileDiagnostic`。checker 不应该复制 message/severity/dedup 逻辑。

### Gate

Gate 是最终 renderability 裁决，尤其针对 executable element。

IRS checker 可以提前发出 `renderable=False` report，但最终是否渲染 executable step 仍由 Gate 保底。

### ProducerIndex

ProducerIndex 是 output producer 的最终权威。

`REQUIRED_OUTPUT` IRS 可以报告 producer slot missing，但不应自己推断 producer。

## 新增 IRS 的验收标准

新增一个 IRS checker 必须满足：

1. checker 不修改输入 IR。
2. checker 能独立单测。
3. checker 能通过 runner 接入 stage。
4. 输出 `ConstructSatisfactionReport`。
5. 输出 diagnostics 可进入 final compile diagnostics。
6. diagnostics 可进入 readable report / feedback report。
7. checker 没有 prompt-only 逻辑。
8. 对无 source demand 的 construct 不产生噪声诊断。
9. candidate-only construct 不得被误判为 renderable SPL construct。
10. diagnostics 由统一 projector 或兼容投影层产生。

## 推荐测试类型

### Registry 测试

检查 ConstructIRS slot 定义是否正确。

### Checker 单元测试

直接构造 IR，调用 checker。

### Runner 测试

通过 `IRSRunner.run_stage()` 验证 checker 注册与运行。

### Orchestrator 集成测试

验证 reports 和 diagnostics 进入：

```text
intermediate["construct_satisfaction"]
intermediate["stage_local_diagnostics"]
result.compile_diagnostics
result.readable_report
```

### Negative 测试

确认无 source demand 不产生 construct，不产生 diagnostic。
