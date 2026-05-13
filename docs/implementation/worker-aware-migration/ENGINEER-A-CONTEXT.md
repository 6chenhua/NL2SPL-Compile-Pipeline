# 工程师 A 上下文文档

**角色**: IR/Stage 专家  
**负责任务**: T0 → T1 → T1.5 → T2 辅助  
**预计工作时间**: 第 1-18 天

---

## 1. 项目背景

### 1.1 项目概述

nl2spl 是一个将自然语言（NL）转换为 SPL（Search Processing Language）的 pipeline 系统。用户输入自然语言查询，系统通过多个 Stage 处理，最终生成可执行的 SPL 代码。

### 1.2 当前问题

当前系统支持"worker"概念（类似于微服务或子任务），但实现不完整：
- Stage 4/5 已经支持 worker-aware（能识别多个 worker）
- Stage 6/7/9.5/10 仍然使用旧版适配器，只能看到 main worker
- child worker 的流程被丢弃，无法正确渲染

### 1.3 迁移目标

实现全链路 worker-aware，让所有 Stage 都能正确处理多个 worker。

---

## 2. 架构概览

### 2.1 Pipeline 流程

```
用户输入（自然语言）
    ↓
Stage 1: Span Slicer（分词）
    ↓
Stage 2: Field Router（字段路由）
    ↓
Stage 3: Ambiguity Resolver（歧义解决）
    ↓
Stage 3.5: Worker Boundary Planner（worker 边界规划）← 输出 WorkerPlanIR
    ↓
Stage 4: Flow Assembler（流程组装）← 输出 WorkerFlowPlanIR
    ↓
Stage 5: Block Assembler（块组装）← 输出 WorkerBlockPlanIR
    ↓
Stage 6: Resource Extractor（资源提取）
    ↓
Stage 7: Step Extractor（步骤提取）← 你的重点任务
    ↓
Stage 8: Profile Extractor（配置提取）
    ↓
Stage 9: Constraint Extractor（约束提取）
    ↓
Stage 9.5: IR Normalizer（IR 校验）← 你的重点任务
    ↓
Stage 10: Worker Assembler（worker 组装）
    ↓
Stage 11: SPL Renderer（SPL 渲染）
    ↓
输出：SPL 代码
```

### 2.2 关键 IR（中间表示）

#### WorkerPlanIR（worker 边界规划结果）

```python
@dataclass
class WorkerPlanIR:
    main_worker_id: str                    # 主 worker ID
    workers: list[WorkerSpecIR]            # 所有 worker 规格
    handoffs: list[WorkerHandoffIR]        # worker 间的调用关系
    candidates: list[CandidateTaskUnitIR]  # 候选任务单元
    decisions: list[WorkerBoundaryDecisionIR]  # 边界决策
    rejected_candidates: list[WorkerBoundaryDecisionIR]  # 拒绝的候选
```

**文件位置**: `src/nl2spl/ir/worker_plan_ir.py`

#### WorkerSpecIR（worker 规格）

```python
@dataclass
class WorkerSpecIR:
    worker_id: str                         # worker ID
    worker_name: str                       # worker 名称
    kind: Literal["main", "child", "api_adapter"]  # 类型
    purpose: str                           # 用途描述
    owned_span_ids: list[str]              # 拥有的 span ID 列表
    input_contract: list[ContractFieldIR]  # 输入契约
    output_contract: list[ContractFieldIR] # 输出契约
```

**关键点**: `owned_span_ids` 定义了该 worker 负责处理的文本片段。

#### WorkerHandoffIR（worker 间调用）

```python
@dataclass
class WorkerHandoffIR:
    handoff_id: str                        # 调用 ID
    from_worker: str                       # 调用方 worker ID
    to_worker: str | None                  # 被调用方 worker ID
    api_ref: str | None                    # API 引用
    mode: Literal["invoke", "api_call"]    # 调用模式
    input_bindings: list[InputBindingIR]   # 输入绑定
    output_bindings: list[OutputBindingIR] # 输出绑定
    invoke_location_hint: InvokeLocationHintIR  # 调用位置提示
```

**关键点**: 
- `mode="invoke"` 表示调用另一个 worker
- `mode="api_call"` 表示调用外部 API
- `invoke_location_hint` 指示在哪里插入调用步骤

#### InvokeLocationHintIR（调用位置提示）

```python
@dataclass
class InvokeLocationHintIR:
    flow_kind: Literal["main", "alternative", "exception"]
    flow_id: str | None
    after_span_id: str | None              # 在哪个 span 之后调用
    before_span_id: str | None             # 在哪个 span 之前调用
    block_hint: Literal["sequential", "if", "for", "while", "unknown"]
```

**关键点**: `after_span_id` 和 `before_span_id` 用于确定调用步骤的位置。

---

## 3. 你的任务详解

### 3.1 T0: IR Contract 修正（第 1 天）

**目标**: 修正关键设计缺口，冻结 IR contract。

**具体工作**:

#### 3.1.1 修正 WorkerStepPlanIR

**文件**: `src/nl2spl/ir/worker_plan_ir.py`

需要新增 `WorkerStepPlanIR` 类：

```python
@dataclass
class WorkerStepPlanIR:
    """Worker-scoped step extraction result.
    
    用途：存储按 worker 分组的步骤提取结果。
    
    字段说明：
    - main_worker_id: 主 worker 的 ID，从 WorkerPlanIR 获取
    - worker_steps: 按 worker_id 分组的步骤列表
    - warnings: 验证警告信息
    """
    main_worker_id: str
    worker_steps: dict[str, list[StepIR]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    
    @property
    def main_worker_steps(self) -> list[StepIR]:
        """获取主 worker 的步骤。"""
        return self.worker_steps.get(self.main_worker_id, [])
    
    def get_all_steps(self) -> list[StepIR]:
        """获取所有 worker 的步骤。"""
        all_steps = []
        for steps in self.worker_steps.values():
            all_steps.extend(steps)
        return all_steps
```

**设计决策**:
- 使用 `main_worker_id` 而不是硬编码 `"_main"`
- 支持按 worker_id 索引步骤

#### 3.1.2 升级 ChildWorkerIR（设计）

**文件**: `src/nl2spl/ir/worker_ir.py`

需要设计 `ChildWorkerIR` 的升级方案：

```python
@dataclass
class ChildWorkerIR:
    """Child worker 定义。
    
    当前问题：只能存储基本信息，无法存储 flow 和 steps。
    解决方案：新增 main_flow 和 steps 字段。
    """
    worker_name: str
    description: str
    task_text: str
    inputs: list[WorkerInput]
    outputs: list[WorkerOutput]
    # 新增字段（D3 决策）
    main_flow: FlowRef = field(default_factory=FlowRef)
    steps: list[StepIR] = field(default_factory=list)
```

**设计决策**:
- 新增 `main_flow` 存储流程结构
- 新增 `steps` 存储步骤列表
- 所有新字段都有默认值，保持向后兼容

#### 3.1.3 设计 SymbolTable scope 方案

**文件**: `src/nl2spl/ir/symbol_table.py`

需要设计 scope 方案（不实现，只设计）：

```python
# 设计方案（D4 决策）
# 使用复合 key: (scope_kind, scope_id, name)
# 
# scope_kind: "global" | "worker" | "handoff"
# scope_id: worker_id 或 handoff_id（global 时为 None）
# name: 变量名
#
# 示例：
# ("global", None, "query") -> 全局变量 query
# ("worker", "worker_1", "result") -> worker_1 的变量 result
# ("handoff", "handoff_1", "input") -> handoff_1 的变量 input
```

**设计决策**:
- 使用复合 key 支持同名不同 scope 的变量
- 保持 `self.variables` 兼容旧接口

#### 3.1.4 记录设计决策

需要在迁移方案文档中记录 D1-D7 决策。

**验收标准**:
- [ ] `WorkerStepPlanIR` 类定义正确
- [ ] `ChildWorkerIR` 设计方案完成
- [ ] SymbolTable scope 设计方案完成
- [ ] D1-D7 决策已记录

---

### 3.2 T1: WorkerScopedStepIR + Stage 7（第 2-6 天）

**目标**: 让 Stage 7 按 worker_id 输出 steps。

**文件**: `src/nl2spl/pipeline/stages/stage7_step_extractor.py`

#### 3.2.1 理解当前 Stage 7

当前 Stage 7 的工作流程：
1. 接收 spans、flow_structure、block_structure、symbol_table
2. 构建 prompt，让 LLM 提取步骤
3. 返回 `list[StepIR]`

**问题**: 只处理 main worker 的 flow，child worker 的 flow 被丢弃。

#### 3.2.2 实现 execute_worker_scoped()

新增方法，按 worker 分别提取步骤：

```python
def execute_worker_scoped(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    symbol_table: SymbolTable,
    worker_plan: WorkerPlanIR,
) -> tuple[WorkerStepPlanIR, SymbolTable]:
    """执行 worker-scoped 步骤提取。
    
    工作流程：
    1. 遍历 worker_plan.workers
    2. 对每个 worker：
       - 获取该 worker 的 flow 和 blocks
       - 获取该 worker 拥有的 spans
       - 构建 worker-scoped prompt
       - 调用 LLM 提取步骤
    3. 为 main worker 生成 INVOKE_WORKER 步骤（从 handoffs）
    4. 返回 WorkerStepPlanIR
    """
```

**关键点**:
- 每个 worker 独立提取步骤
- prompt 中只包含该 worker 的变量
- 验证步骤只引用该 worker 拥有的 spans

#### 3.2.3 实现 _generate_handoff_steps()

从 `WorkerHandoffIR` 生成 `INVOKE_WORKER` / `CALL_API` 步骤：

```python
def _generate_handoff_steps(
    self,
    worker_plan: WorkerPlanIR,
    symbol_table: SymbolTable,
) -> list[StepIR]:
    """从 handoffs 生成调用步骤。
    
    设计决策 D1：只从 WorkerHandoffIR 生成，不从 decisions 生成。
    
    工作流程：
    1. 遍历 worker_plan.handoffs
    2. 对于 mode="invoke"：生成 INVOKE_WORKER 步骤
    3. 对于 mode="api_call"：生成 CALL_API 步骤
    """
```

**关键点**:
- 只从 `handoffs` 生成，不从 `decisions` 生成（D1 决策）
- 使用 `invoke_location_hint` 确定步骤位置（D2 决策）

#### 3.2.4 实现 _get_invoke_source_spans()

确定调用步骤的 source_span_ids：

```python
def _get_invoke_source_spans(
    self,
    handoff: WorkerHandoffIR,
    worker_plan: WorkerPlanIR,
) -> list[str]:
    """获取调用步骤的 source spans。
    
    设计决策 D2：优先使用 invoke_location_hint。
    
    规则：
    1. 如果有 after_span_id，使用 [after_span_id]
    2. 如果有 before_span_id，使用 [before_span_id]
    3. 否则，fallback 到 from_worker 的 owned_span_ids（并 warning）
    """
```

**关键点**:
- 优先使用 `invoke_location_hint`
- fallback 时需要 warning

#### 3.2.5 实现 _validate_step_span_ownership()

验证步骤只引用 worker 拥有的 spans：

```python
def _validate_step_span_ownership(
    self,
    steps: list[StepIR],
    worker: WorkerSpecIR,
) -> list[str]:
    """验证步骤的 span 所有权。
    
    设计决策 D5：span ownership violation 是 error，不是 warning。
    
    规则：
    - INVOKE_WORKER/CALL_API 步骤可以引用 caller span
    - 其他步骤只能引用 owned spans
    - 违规则返回 error 列表
    """
```

**关键点**:
- 返回 error 列表，不是 warning
- 调用方需要处理这些 errors

#### 3.2.6 修改 Orchestrator

**文件**: `src/nl2spl/pipeline/orchestrator.py`

新增 worker-aware 调用路径：

```python
# Stage 7 调用逻辑
if (self.config.enable_worker_boundary_planner
    and worker_flow_plan is not None
    and worker_block_plan is not None
    and worker_plan is not None):
    # Worker-aware path
    worker_step_plan, symbol_table = self._run_stage7_worker_scoped(...)
    steps = worker_step_plan.get_all_steps()
else:
    # Legacy path
    steps, symbol_table = self._run_stage7(...)
```

**验收标准**:
- [ ] `execute_worker_scoped()` 实现正确
- [ ] `_generate_handoff_steps()` 从 handoffs 生成步骤（D1）
- [ ] `_get_invoke_source_spans()` 优先使用 invoke_location_hint（D2）
- [ ] `_validate_step_span_ownership()` 返回 error（D5）
- [ ] Orchestrator 正确处理两种 path
- [ ] 所有测试通过

---

### 3.3 T1.5: Worker-aware Stage 9.5（第 7-9 天）

**目标**: 在 Stage 10 之前校验 worker-scoped IR 的完整性。

**文件**: `src/nl2spl/pipeline/stages/stage9_5_normalizer.py`

#### 3.3.1 理解当前 Stage 9.5

当前 Stage 9.5 的工作流程：
1. 接收 flow、blocks、resources、symbol_table、steps、constraints
2. 校验一致性
3. 返回校验后的 IR 和 errors/warnings

**问题**: 只校验 main worker 的 flow，无法校验 worker 间的关系。

#### 3.3.2 实现 normalize_worker_scoped()

新增方法，校验 worker-scoped IR：

```python
def normalize_worker_scoped(
    self,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    worker_step_plan: WorkerStepPlanIR,
    worker_plan: WorkerPlanIR,
    resources: ResourceRegistryIR,
    symbol_table: SymbolTable,
) -> tuple[
    WorkerFlowPlanIR,
    WorkerBlockPlanIR,
    WorkerStepPlanIR,
    SymbolTable,
    list[str],  # errors
    list[str],  # warnings
]:
    """校验 worker-scoped IR。
    
    校验内容：
    1. span ownership（D5: error）
    2. handoff completeness
    3. output binding
    4. producer/consumer reachability
    5. handoff types
    """
```

#### 3.3.3 实现 _validate_span_ownership()

验证 span 所有权：

```python
def _validate_span_ownership(
    self,
    worker_step_plan: WorkerStepPlanIR,
    worker_plan: WorkerPlanIR,
) -> list[str]:
    """验证 span 所有权。
    
    设计决策 D5：span ownership violation 是 error。
    
    规则：
    - Main worker 步骤不能引用 child-owned spans
    - Child worker 步骤只能引用自己 owned spans
    - Handoff 步骤可以引用 caller span
    """
```

#### 3.3.4 实现其他校验方法

- `_validate_handoffs()`: 验证 handoff 完整性
- `_validate_output_binding()`: 验证 child output 绑定
- `_validate_reachability()`: 验证 producer/consumer 可达性
- `_validate_handoff_types()`: 验证 handoff 类型

**验收标准**:
- [ ] `normalize_worker_scoped()` 实现正确
- [ ] `_validate_span_ownership()` 返回 error（D5）
- [ ] 其他校验方法实现正确
- [ ] Orchestrator 正确处理 error
- [ ] 所有测试通过

---

### 3.4 T2 辅助: SymbolTable scope 设计（第 10-18 天）

**目标**: 协助工程师 C 实现 SymbolTable scope。

**具体工作**:
- 设计 `VariableSymbol` 的 scope 字段
- 设计 `SymbolTable` 的 scoped 方法
- 评审工程师 C 的实现
- 编写测试

---

## 4. 关键概念

### 4.1 Span（文本片段）

Span 是文本的基本单位，每个 span 有唯一的 ID（如 `sp1`, `sp2`）。

**示例**:
- 输入: "查询最近 7 天的销售数据"
- Span 1: "查询" (sp1)
- Span 2: "最近 7 天" (sp2)
- Span 3: "销售数据" (sp3)

### 4.2 Worker（工作者）

Worker 是处理任务的单位，可以是：
- **Main worker**: 主流程
- **Child worker**: 子任务
- **API adapter**: 外部 API 调用

**示例**:
- Main worker: 处理主流程
- Child worker 1: 处理数据查询
- Child worker 2: 处理数据格式化

### 4.3 Handoff（调用）

Handoff 表示 worker 间的调用关系：
- **invoke**: 调用另一个 worker
- **api_call**: 调用外部 API

**示例**:
- Main worker 调用 Child worker 1（invoke）
- Child worker 1 调用外部 API（api_call）

### 4.4 Step（步骤）

Step 是原子操作，类型包括：
- **GENERAL_COMMAND**: 一般命令
- **CALL_API**: 调用 API
- **INVOKE_WORKER**: 调用 worker
- **REQUEST_INPUT**: 请求输入
- **DISPLAY_MESSAGE**: 显示消息

**示例**:
```python
StepIR(
    step_id="st1",
    text="查询销售数据",
    command_type="INVOKE_WORKER",
    inputs=["query"],
    outputs=["result"],
    handoff_id="handoff_1"
)
```

### 4.5 Flow（流程）

Flow 定义了步骤的执行顺序：
- **Main flow**: 主流程
- **Alternative flow**: 备选流程
- **Exception flow**: 异常流程

### 4.6 Block（块）

Block 是流程中的控制结构：
- **SEQUENTIAL**: 顺序执行
- **IF**: 条件判断
- **FOR**: 循环
- **WHILE**: 条件循环

---

## 5. 开发环境

### 5.1 代码结构

```
src/nl2spl/
├── ir/                              # 中间表示定义
│   ├── worker_plan_ir.py            # WorkerPlanIR, WorkerStepPlanIR
│   ├── worker_ir.py                 # WorkerIR, ChildWorkerIR
│   ├── flow_structure_ir.py         # FlowStructureIR
│   ├── block_structure_ir.py        # BlockStructureIR
│   ├── step_ir.py                   # StepIR
│   ├── symbol_table.py              # SymbolTable
│   └── resource_registry_ir.py      # ResourceRegistryIR
├── pipeline/                        # Pipeline 实现
│   ├── orchestrator.py              # Pipeline 编排器
│   └── stages/                      # 各个 Stage
│       ├── stage7_step_extractor.py # Stage 7 实现
│       ├── stage9_5_normalizer.py   # Stage 9.5 实现
│       └── ...
└── tests/                           # 测试
    ├── ir/                          # IR 测试
    └── pipeline/                    # Pipeline 测试
```

### 5.2 关键文件

你需要修改的文件：
1. `src/nl2spl/ir/worker_plan_ir.py` - T0: 新增 WorkerStepPlanIR
2. `src/nl2spl/ir/worker_ir.py` - T0: 升级 ChildWorkerIR
3. `src/nl2spl/ir/symbol_table.py` - T0: 设计 scope 方案
4. `src/nl2spl/pipeline/stages/stage7_step_extractor.py` - T1: 新增 worker-aware 方法
5. `src/nl2spl/pipeline/stages/stage9_5_normalizer.py` - T1.5: 新增 worker-aware 方法
6. `src/nl2spl/pipeline/orchestrator.py` - T1/T1.5: 新增调用路径

### 5.3 测试文件

你需要创建的测试文件：
1. `tests/ir/test_worker_step_plan_ir.py` - T0 测试
2. `tests/pipeline/stages/test_stage7_worker_scoped.py` - T1 测试
3. `tests/pipeline/stages/test_stage9_5_worker_scoped.py` - T1.5 测试

---

## 6. 测试策略

### 6.1 单元测试

每个新增方法都需要单元测试：

```python
class TestStepExtractorWorkerScoped:
    def test_execute_worker_scoped_single_worker(self):
        """测试单个 worker 的步骤提取。"""
        
    def test_execute_worker_scoped_multiple_workers(self):
        """测试多个 worker 的步骤提取。"""
        
    def test_generate_handoff_steps_invoke(self):
        """测试从 invoke handoff 生成步骤。"""
        
    def test_generate_handoff_steps_api_call(self):
        """测试从 api_call handoff 生成步骤。"""
        
    def test_get_invoke_source_spans_with_hint(self):
        """测试有 invoke_location_hint 时获取 source spans。"""
        
    def test_get_invoke_source_spans_without_hint(self):
        """测试没有 invoke_location_hint 时获取 source spans。"""
        
    def test_validate_step_span_ownership_valid(self):
        """测试有效的 span 所有权验证。"""
        
    def test_validate_step_span_ownership_invalid(self):
        """测试无效的 span 所有权验证（D5: error）。"""
```

### 6.2 集成测试

端到端测试：

```python
class TestWorkerAwarePipeline:
    def test_end_to_end_single_worker(self):
        """测试单个 worker 的端到端流程。"""
        
    def test_end_to_end_multiple_workers(self):
        """测试多个 worker 的端到端流程。"""
        
    def test_span_ownership_violation(self):
        """测试 span 所有权违规（D5: error）。"""
```

### 6.3 回归测试

确保现有测试通过：

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/ir/
pytest tests/pipeline/stages/
```

---

## 7. 常见问题

### 7.1 如何获取 worker 拥有的 spans？

```python
worker_span_ids = set(worker.owned_span_ids)
worker_spans = [s for s in spans if s.span_id in worker_span_ids]
```

### 7.2 如何从 handoff 生成 INVOKE_WORKER 步骤？

```python
step = StepIR(
    step_id=f"st_invoke_{handoff.handoff_id}",
    text=f"Invoke worker: {to_worker.worker_name}",
    source_span_ids=self._get_invoke_source_spans(handoff, worker_plan),
    command_type="INVOKE_WORKER",
    inputs=[b.parent_variable for b in handoff.input_bindings],
    outputs=[b.parent_variable for b in handoff.output_bindings],
    kind="invoke",
    handoff_id=handoff.handoff_id,
)
```

### 7.3 如何验证 span 所有权？

```python
errors = []
owned_spans = set(worker.owned_span_ids)

for step in steps:
    if step.command_type in ("INVOKE_WORKER", "CALL_API"):
        continue  # 调用步骤可以引用 caller span
    
    for span_id in step.source_span_ids:
        if span_id not in owned_spans:
            errors.append(f"Step {step.step_id} references span {span_id} not owned by worker {worker.worker_id}")

return errors
```

### 7.4 如何处理 legacy path？

```python
if (self.config.enable_worker_boundary_planner
    and worker_flow_plan is not None
    and worker_block_plan is not None
    and worker_plan is not None):
    # Worker-aware path
    ...
else:
    # Legacy path
    ...
```

---

## 8. 参考资料

### 8.1 文档

- [迁移方案 v3.0](../../migration-worker-aware-pipeline.md)
- [任务总览](README.md)
- [T0 任务文档](T0-ir-contract.md)
- [T1 任务文档](T1-worker-scoped-step.md)
- [T1.5 任务文档](T1.5-worker-aware-normalizer.md)

### 8.2 代码

- [WorkerPlanIR 定义](../../../src/nl2spl/ir/worker_plan_ir.py)
- [ChildWorkerIR 定义](../../../src/nl2spl/ir/worker_ir.py)
- [SymbolTable 定义](../../../src/nl2spl/ir/symbol_table.py)
- [Stage 7 实现](../../../src/nl2spl/pipeline/stages/stage7_step_extractor.py)
- [Stage 9.5 实现](../../../src/nl2spl/pipeline/stages/stage9_5_normalizer.py)
- [Orchestrator 实现](../../../src/nl2spl/pipeline/orchestrator.py)

### 8.3 设计决策

- **D1**: INVOKE_WORKER 从 handoffs 生成
- **D2**: source_span_ids 优先使用 invoke_location_hint
- **D5**: span ownership violation 是 error
