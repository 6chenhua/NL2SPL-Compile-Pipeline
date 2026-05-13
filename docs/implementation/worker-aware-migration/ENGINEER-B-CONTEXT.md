# 工程师 B 上下文文档

**角色**: Renderer 专家  
**负责任务**: 等待 → T1.6 → T3  
**预计工作时间**: 第 10-20 天

---

## 1. 项目背景

### 1.1 项目概述

nl2spl 是一个将自然语言（NL）转换为 SPL（Search Processing Language）的 pipeline 系统。用户输入自然语言查询，系统通过多个 Stage 处理，最终生成可执行的 SPL 代码。

### 1.2 当前问题

当前系统支持"worker"概念（类似于微服务或子任务），但实现不完整：
- Stage 10 的 `ChildWorkerIR` 无法存储 child worker 的 flow 和 steps
- Stage 11 的 `_render_child_worker()` 使用 synthetic `st_child`，无法渲染 child flow
- child worker 的流程被丢弃，无法正确渲染

### 1.3 迁移目标

实现全链路 worker-aware，让 Stage 10/11 能正确处理多个 worker。

---

## 2. 架构概览

### 2.1 Pipeline 流程（你的关注点）

```
Stage 9.5: IR Normalizer（IR 校验）
    ↓
Stage 10: Worker Assembler（worker 组装）← 你的重点任务
    ↓
Stage 11: SPL Renderer（SPL 渲染）← 你的重点任务
    ↓
输出：SPL 代码
```

### 2.2 关键 IR（中间表示）

#### WorkerIR（worker 组装结果）

```python
@dataclass
class WorkerIR:
    """Worker 组装结果。
    
    用途：存储完整的 worker 定义，用于 SPL 渲染。
    
    字段说明：
    - worker_name: worker 名称
    - description: worker 描述
    - inputs: 输入规格
    - outputs: 输出规格
    - main_flow: 主流程引用
    - alternative_flows: 备选流程引用
    - exception_flows: 异常流程引用
    - api_refs: 引用的 API 名称
    - child_workers: 子 worker 定义
    """
    worker_name: str
    description: str
    inputs: list[WorkerInput]
    outputs: list[WorkerOutput]
    main_flow: FlowRef
    alternative_flows: list[AlternativeFlowRef]
    exception_flows: list[ExceptionFlowRef]
    api_refs: list[str]
    child_workers: list[ChildWorkerIR]
```

**文件位置**: `src/nl2spl/ir/worker_ir.py`

#### ChildWorkerIR（子 worker 定义）- 当前缺陷

```python
@dataclass
class ChildWorkerIR:
    """子 worker 定义。
    
    当前问题：只能存储基本信息，无法存储 flow 和 steps。
    解决方案：新增 main_flow 和 steps 字段（D3 决策）。
    """
    worker_name: str
    description: str
    task_text: str
    inputs: list[WorkerInput]
    outputs: list[WorkerOutput]
    # 新增字段（D3 决策）
    main_flow: FlowRef = field(default_factory=FlowRef)
    alternative_flows: list[AlternativeFlowRef] = field(default_factory=list)
    exception_flows: list[ExceptionFlowRef] = field(default_factory=list)
    api_refs: list[str] = field(default_factory=list)
    steps: list[StepIR] = field(default_factory=list)
```

**关键点**: `steps` 字段用于存储 child worker 的步骤，Stage 11 渲染时需要。

#### FlowRef（流程引用）

```python
@dataclass
class FlowRef:
    """流程引用。
    
    用途：存储流程中的块列表。
    """
    blocks: list[BlockIR] = field(default_factory=list)
```

#### BlockIR（块定义）

```python
@dataclass
class BlockIR:
    """块定义。
    
    用途：存储控制结构和步骤引用。
    
    字段说明：
    - block_id: 块 ID（如 "b1", "b2"）
    - block_type: 块类型（SEQUENTIAL, IF, FOR, WHILE）
    - condition_text: 条件文本（IF/FOR/WHILE 时使用）
    - spans: 包含的步骤 ID 列表
    """
    block_id: str
    block_type: Literal["SEQUENTIAL", "IF", "FOR", "WHILE"]
    condition_text: str | None = None
    spans: list[str] = field(default_factory=list)
```

**关键点**: `spans` 存储的是步骤 ID（如 "st1", "st2"），不是文本 span ID。

#### StepIR（步骤定义）

```python
@dataclass
class StepIR:
    """步骤定义。
    
    用途：存储原子操作。
    
    字段说明：
    - step_id: 步骤 ID（如 "st1", "st2"）
    - text: 步骤描述
    - source_span_ids: 来源文本 span ID 列表
    - command_type: 命令类型
    - inputs: 输入变量名列表
    - outputs: 输出变量名列表
    - integration_ref: API 引用（CALL_API 时使用）
    - handoff_id: handoff ID（INVOKE_WORKER 时使用）
    """
    step_id: str
    text: str
    source_span_ids: list[str]
    command_type: Literal["GENERAL_COMMAND", "CALL_API", "INVOKE_WORKER", "REQUEST_INPUT", "DISPLAY_MESSAGE"]
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    integration_ref: str | None = None
    handoff_id: str | None = None
```

**关键点**: 
- `step_id` 格式为 "st{N}"（如 "st1", "st2"）
- `command_type` 决定了步骤的渲染方式

---

## 3. 你的任务详解

### 3.1 T1.6: WorkerIR/Renderer child-flow support（第 10-13 天）

**目标**: 升级 ChildWorkerIR 支持 child flow + steps，修改 Stage 10 和 Stage 11 渲染 child flow。

#### 3.1.1 升级 ChildWorkerIR

**文件**: `src/nl2spl/ir/worker_ir.py`

需要升级 `ChildWorkerIR` 类（D3 决策）：

```python
@dataclass
class ChildWorkerIR:
    """子 worker 定义。
    
    升级内容：
    - 新增 main_flow: 存储流程结构
    - 新增 alternative_flows: 存储备选流程
    - 新增 exception_flows: 存储异常流程
    - 新增 api_refs: 存储引用的 API
    - 新增 steps: 存储步骤列表
    """
    worker_name: str
    description: str
    task_text: str
    inputs: list[WorkerInput] = field(default_factory=list)
    outputs: list[WorkerOutput] = field(default_factory=list)
    # 新增字段
    main_flow: FlowRef = field(default_factory=FlowRef)
    alternative_flows: list[AlternativeFlowRef] = field(default_factory=list)
    exception_flows: list[ExceptionFlowRef] = field(default_factory=list)
    api_refs: list[str] = field(default_factory=list)
    steps: list[StepIR] = field(default_factory=list)
```

**设计决策**:
- 所有新字段都有默认值，保持向后兼容
- `steps` 字段用于 Stage 11 渲染

#### 3.1.2 实现 assemble_from_worker_scoped()

**文件**: `src/nl2spl/pipeline/stages/stage10_worker_assembler.py`

新增方法，从 worker-scoped 数据组装 WorkerIR：

```python
def assemble_from_worker_scoped(
    self,
    worker_step_plan: WorkerStepPlanIR,
    worker_scoped_resources: WorkerScopedResourceIR | None,
    symbol_table: SymbolTable,
    worker_plan: WorkerPlanIR,
    worker_flow_plan: WorkerFlowPlanIR | None = None,
    worker_block_plan: WorkerBlockPlanIR | None = None,
) -> WorkerIR:
    """从 worker-scoped 数据组装 WorkerIR。
    
    工作流程：
    1. 获取 main worker 的 steps
    2. 遍历 child workers：
       - 获取 child 的 steps、flow、blocks
       - 调用 _build_child_worker() 构建 ChildWorkerIR
    3. 构建 main worker 的 flow
    4. 返回 WorkerIR
    """
```

#### 3.1.3 实现 _build_child_worker()

构建 ChildWorkerIR：

```python
def _build_child_worker(
    self,
    worker: WorkerSpecIR,
    steps: list[StepIR],
    flow: FlowStructureIR | None,
    blocks: BlockStructureIR | None,
    symbol_table: SymbolTable,
) -> ChildWorkerIR:
    """构建 ChildWorkerIR。
    
    工作流程：
    1. 构建 main_flow（从 blocks）
    2. 构建 alternative_flows（从 flow 和 blocks）
    3. 构建 exception_flows（从 flow 和 blocks）
    4. 收集 api_refs（从 steps）
    5. 返回 ChildWorkerIR（包含 steps）
    """
```

**关键点**: 将 `steps` 传递给 `ChildWorkerIR`，供 Stage 11 渲染使用。

#### 3.1.4 修改 _render_child_worker()

**文件**: `src/nl2spl/pipeline/stages/stage11_spl_renderer.py`

修改渲染逻辑，使用 child 的 flow 和 steps：

```python
def _render_child_worker(self, child: ChildWorkerIR, indent: int) -> list[str]:
    """渲染子 worker。
    
    当前问题：使用 synthetic st_child，无法渲染 child flow。
    解决方案：使用 child.main_flow.blocks 和 child.steps 渲染。
    
    工作流程：
    1. 渲染 worker 头（worker name, description）
    2. 渲染 inputs/outputs
    3. 渲染 main flow blocks（使用 child.steps）
    4. 渲染 alternative flows
    5. 渲染 exception flows
    """
```

**关键点**:
- 使用 `child.steps` 而不是全局 `steps`
- 渲染 `child.main_flow.blocks` 中的所有块

#### 3.1.5 实现 _render_block()

渲染块：

```python
def _render_block(
    self,
    block: BlockIR,
    steps: list[StepIR],
    indent: int,
) -> list[str]:
    """渲染块。
    
    工作流程：
    1. 根据 block_type 选择渲染方式
    2. SEQUENTIAL: 顺序渲染步骤
    3. IF: 渲染条件和步骤
    4. FOR: 渲染循环和步骤
    5. WHILE: 渲染条件循环和步骤
    """
```

#### 3.1.6 实现 _render_step()

渲染步骤：

```python
def _render_step(self, step: StepIR, indent: int) -> list[str]:
    """渲染步骤。
    
    根据 command_type 选择渲染方式：
    - INVOKE_WORKER: 渲染 invoke_worker
    - CALL_API: 渲染 call_api
    - 其他: 渲染 command
    """
```

#### 3.1.7 修改 Orchestrator

**文件**: `src/nl2spl/pipeline/orchestrator.py`

新增 worker-aware 调用路径：

```python
# Stage 10 调用逻辑
if (self.config.enable_worker_boundary_planner
    and worker_step_plan is not None
    and worker_plan is not None):
    # Worker-aware path
    worker = self._run_stage10_worker_scoped(...)
else:
    # Legacy path
    worker = self._run_stage10(...)
```

**验收标准**:
- [ ] `ChildWorkerIR` 包含新字段
- [ ] `assemble_from_worker_scoped()` 实现正确
- [ ] `_build_child_worker()` 实现正确
- [ ] `_render_child_worker()` 渲染 child flow（不是 synthetic st_child）
- [ ] `_render_block()` 渲染各种块类型
- [ ] `_render_step()` 渲染各种步骤类型
- [ ] Orchestrator 正确处理两种 path
- [ ] 所有测试通过

---

### 3.2 T3: worker-aware path 去 adapter（第 14-20 天）

**目标**: 让 worker-aware path 不再读取 `delegation_candidates`。

#### 3.2.1 修改 Stage 4 调用

**文件**: `src/nl2spl/pipeline/orchestrator.py`

```python
# Stage 4 调用逻辑
if self.config.enable_worker_boundary_planner:
    # Worker-aware path
    worker_flow_plan = self._run_stage4(resolved_spans, resolved_routes, worker_plan)
    if not isinstance(worker_flow_plan, WorkerFlowPlanIR):
        raise TypeError("Worker-aware Stage 4 must return WorkerFlowPlanIR")
    worker_stage_warnings.extend(worker_flow_plan.warnings)
    intermediate["stage4_worker_flows"] = worker_flow_plan
    
    # 不再调用 worker_flow_plan_to_legacy_main_flow()
    # 不再设置 flow_structure = ...
else:
    # Legacy path
    flow_structure = self._run_stage4(resolved_spans, resolved_routes)
    intermediate["stage4_flow"] = flow_structure
```

#### 3.2.2 修改 Stage 5 调用

```python
# Stage 5 调用逻辑
if self.config.enable_worker_boundary_planner:
    # Worker-aware path
    worker_block_plan = self._run_stage5(resolved_spans, resolved_routes, worker_flow_plan)
    if not isinstance(worker_block_plan, WorkerBlockPlanIR):
        raise TypeError("Worker-aware Stage 5 must return WorkerBlockPlanIR")
    worker_stage_warnings.extend(worker_block_plan.warnings)
    intermediate["stage5_worker_blocks"] = worker_block_plan
    
    # 不再调用 worker_block_plan_to_legacy_main_blocks()
    # 不再设置 block_structure = ...
else:
    # Legacy path
    block_structure = self._run_stage5(resolved_spans, resolved_routes, flow_structure)
    intermediate["stage5_blocks"] = block_structure
```

#### 3.2.3 确认 Stage 6/7/9.5/10 使用正确 path

确保所有 Stage 都使用 worker-aware path（如果启用）或 legacy path（如果未启用）。

#### 3.2.4 条件性删除 legacy adapter

**条件**: 如果 legacy delegation 已迁完，可以删除：
- `src/nl2spl/pipeline/worker_plan_adapter.py`

**注意**: 这是可选步骤，只有在确认 legacy delegation 已完全迁移后才执行。

**验收标准**:
- [ ] worker-aware path 不读取 `delegation_candidates`
- [ ] legacy path 仍能正常使用 `delegation_candidates`
- [ ] Orchestrator 正确处理两种 path
- [ ] 所有测试通过

---

## 4. 关键概念

### 4.1 WorkerIR 结构

```
WorkerIR
├── worker_name: str
├── description: str
├── inputs: list[WorkerInput]
├── outputs: list[WorkerOutput]
├── main_flow: FlowRef
│   └── blocks: list[BlockIR]
│       ├── block_id: str
│       ├── block_type: Literal["SEQUENTIAL", "IF", "FOR", "WHILE"]
│       ├── condition_text: str | None
│       └── spans: list[str]  # 步骤 ID 列表
├── alternative_flows: list[AlternativeFlowRef]
├── exception_flows: list[ExceptionFlowRef]
├── api_refs: list[str]
└── child_workers: list[ChildWorkerIR]
    ├── worker_name: str
    ├── description: str
    ├── task_text: str
    ├── inputs: list[WorkerInput]
    ├── outputs: list[WorkerOutput]
    ├── main_flow: FlowRef  # 新增
    ├── steps: list[StepIR]  # 新增
    └── ...
```

### 4.2 SPL 渲染示例

**输入 WorkerIR**:
```python
WorkerIR(
    worker_name="main",
    description="主 worker",
    inputs=[WorkerInput(name="query", required=True)],
    outputs=[WorkerOutput(name="result", required=True)],
    main_flow=FlowRef(blocks=[
        BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["st1", "st2"]),
    ]),
    child_workers=[
        ChildWorkerIR(
            worker_name="child_1",
            description="子 worker 1",
            inputs=[WorkerInput(name="input", required=True)],
            outputs=[WorkerOutput(name="output", required=True)],
            main_flow=FlowRef(blocks=[
                BlockIR(block_id="b_child_1", block_type="SEQUENTIAL", spans=["st_child_1"]),
            ]),
            steps=[
                StepIR(step_id="st_child_1", text="处理输入", command_type="GENERAL_COMMAND"),
            ],
        ),
    ],
)
```

**输出 SPL**:
```spl
worker main
  description "主 worker"
  inputs
    query (required)
  outputs
    result (required)
  flow main
    command st1
      description "步骤 1"
    command st2
      description "步骤 2"
  worker child_1
    description "子 worker 1"
    inputs
      input (required)
    outputs
      output (required)
    flow main
      command st_child_1
        description "处理输入"
```

### 4.3 Block 渲染规则

| block_type | 渲染结果 |
|------------|----------|
| SEQUENTIAL | 顺序渲染步骤 |
| IF | `if {condition}` ... `endif` |
| FOR | `for {condition}` ... `endfor` |
| WHILE | `while {condition}` ... `endwhile` |

### 4.4 Step 渲染规则

| command_type | 渲染结果 |
|--------------|----------|
| GENERAL_COMMAND | `command {step_id}` |
| CALL_API | `command {step_id}` + `call_api {api_ref}` |
| INVOKE_WORKER | `command {step_id}` + `invoke_worker` |
| REQUEST_INPUT | `command {step_id}` + `request_input` |
| DISPLAY_MESSAGE | `command {step_id}` + `display_message` |

---

## 5. 开发环境

### 5.1 代码结构

```
src/nl2spl/
├── ir/                              # 中间表示定义
│   ├── worker_ir.py                 # WorkerIR, ChildWorkerIR
│   ├── flow_structure_ir.py         # FlowStructureIR
│   ├── block_structure_ir.py        # BlockStructureIR
│   └── step_ir.py                   # StepIR
├── pipeline/                        # Pipeline 实现
│   ├── orchestrator.py              # Pipeline 编排器
│   ├── worker_plan_adapter.py       # Legacy adapter（待删除）
│   └── stages/                      # 各个 Stage
│       ├── stage10_worker_assembler.py # Stage 10 实现
│       ├── stage11_spl_renderer.py    # Stage 11 实现
│       └── ...
└── tests/                           # 测试
    ├── ir/                          # IR 测试
    └── pipeline/                    # Pipeline 测试
```

### 5.2 关键文件

你需要修改的文件：
1. `src/nl2spl/ir/worker_ir.py` - T1.6: 升级 ChildWorkerIR
2. `src/nl2spl/pipeline/stages/stage10_worker_assembler.py` - T1.6: 新增 worker-aware 方法
3. `src/nl2spl/pipeline/stages/stage11_spl_renderer.py` - T1.6: 修改渲染逻辑
4. `src/nl2spl/pipeline/orchestrator.py` - T1.6/T3: 新增调用路径

### 5.3 测试文件

你需要创建的测试文件：
1. `tests/ir/test_child_worker_ir.py` - T1.6 测试
2. `tests/pipeline/stages/test_stage10_worker_scoped.py` - T1.6 测试
3. `tests/pipeline/stages/test_stage11_child_worker_render.py` - T1.6 测试

---

## 6. 测试策略

### 6.1 单元测试

每个新增方法都需要单元测试：

```python
class TestChildWorkerIR:
    def test_init_with_defaults(self):
        """测试默认值初始化。"""
        
    def test_init_with_flow(self):
        """测试带 flow 初始化。"""
        
    def test_init_with_steps(self):
        """测试带 steps 初始化。"""
        
    def test_init_with_all_fields(self):
        """测试所有字段初始化。"""
```

```python
class TestWorkerAssemblerWorkerScoped:
    def test_assemble_from_worker_scoped_single_worker(self):
        """测试单个 worker 组装。"""
        
    def test_assemble_from_worker_scoped_multiple_workers(self):
        """测试多个 worker 组装。"""
        
    def test_build_child_worker_with_flow(self):
        """测试带 flow 构建 child worker。"""
        
    def test_build_child_worker_with_steps(self):
        """测试带 steps 构建 child worker。"""
```

```python
class TestSPLRendererChildWorker:
    def test_render_child_worker_with_flow(self):
        """测试渲染带 flow 的 child worker。"""
        
    def test_render_child_worker_with_steps(self):
        """测试渲染带 steps 的 child worker。"""
        
    def test_render_block_sequential(self):
        """测试渲染 SEQUENTIAL 块。"""
        
    def test_render_block_if(self):
        """测试渲染 IF 块。"""
        
    def test_render_step_invoke_worker(self):
        """测试渲染 INVOKE_WORKER 步骤。"""
        
    def test_render_step_call_api(self):
        """测试渲染 CALL_API 步骤。"""
```

### 6.2 集成测试

端到端测试：

```python
class TestWorkerAwarePipeline:
    def test_end_to_end_child_worker_render(self):
        """测试 child worker 渲染的端到端流程。"""
        
    def test_legacy_path_unchanged(self):
        """测试 legacy path 不受影响。"""
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

### 7.1 如何构建 ChildWorkerIR？

```python
child_worker = ChildWorkerIR(
    worker_name=worker.worker_name,
    description=worker.description,
    task_text=f"Worker: {worker.worker_name}",
    inputs=[WorkerInput(name=f.name, required=f.required) for f in worker.input_contract],
    outputs=[WorkerOutput(name=f.name, required=f.required) for f in worker.output_contract],
    main_flow=FlowRef(blocks=blocks.main_flow_blocks),
    steps=steps,  # 关键：传递 steps
)
```

### 7.2 如何渲染 child worker？

```python
def _render_child_worker(self, child: ChildWorkerIR, indent: int) -> list[str]:
    lines = []
    prefix = " " * indent
    
    # 渲染 worker 头
    lines.append(f"{prefix}worker {child.worker_name}")
    lines.append(f"{prefix}  description \"{child.description}\"")
    
    # 渲染 inputs/outputs
    if child.inputs:
        lines.append(f"{prefix}  inputs")
        for inp in child.inputs:
            required = "required" if inp.required else "optional"
            lines.append(f"{prefix}    {inp.name} ({required})")
    
    if child.outputs:
        lines.append(f"{prefix}  outputs")
        for out in child.outputs:
            required = "required" if out.required else "optional"
            lines.append(f"{prefix}    {out.name} ({required})")
    
    # 渲染 main flow blocks（使用 child.steps）
    if child.main_flow.blocks:
        lines.append(f"{prefix}  flow main")
        for block in child.main_flow.blocks:
            lines.extend(self._render_block(block, child.steps, indent + 4))
    
    return lines
```

### 7.3 如何渲染块？

```python
def _render_block(self, block: BlockIR, steps: list[StepIR], indent: int) -> list[str]:
    lines = []
    prefix = " " * indent
    
    # 获取该块内的步骤
    block_steps = [s for s in steps if s.step_id in block.spans]
    
    if block.block_type == "SEQUENTIAL":
        for step in block_steps:
            lines.extend(self._render_step(step, indent))
    elif block.block_type == "IF":
        lines.append(f"{prefix}if {block.condition_text}")
        for step in block_steps:
            lines.extend(self._render_step(step, indent + 2))
        lines.append(f"{prefix}endif")
    # ... 其他块类型
    
    return lines
```

### 7.4 如何渲染步骤？

```python
def _render_step(self, step: StepIR, indent: int) -> list[str]:
    lines = []
    prefix = " " * indent
    
    if step.command_type == "INVOKE_WORKER":
        lines.append(f"{prefix}command {step.step_id}")
        lines.append(f"{prefix}  description \"{step.text}\"")
        lines.append(f"{prefix}  invoke_worker")
    elif step.command_type == "CALL_API":
        lines.append(f"{prefix}command {step.step_id}")
        lines.append(f"{prefix}  description \"{step.text}\"")
        lines.append(f"{prefix}  call_api {step.integration_ref}")
    else:
        lines.append(f"{prefix}command {step.step_id}")
        lines.append(f"{prefix}  description \"{step.text}\"")
    
    # 渲染 inputs/outputs
    if step.inputs:
        lines.append(f"{prefix}  inputs {', '.join(step.inputs)}")
    if step.outputs:
        lines.append(f"{prefix}  outputs {', '.join(step.outputs)}")
    
    return lines
```

### 7.5 如何处理 legacy path？

```python
if (self.config.enable_worker_boundary_planner
    and worker_step_plan is not None
    and worker_plan is not None):
    # Worker-aware path
    worker = self._run_stage10_worker_scoped(...)
else:
    # Legacy path
    worker = self._run_stage10(...)
```

---

## 8. 参考资料

### 8.1 文档

- [迁移方案 v3.0](../../migration-worker-aware-pipeline.md)
- [任务总览](README.md)
- [T1.6 任务文档](T1.6-child-worker-flow.md)
- [T3 任务文档](T3-remove-legacy-adapter.md)

### 8.2 代码

- [WorkerIR 定义](../../../src/nl2spl/ir/worker_ir.py)
- [ChildWorkerIR 定义](../../../src/nl2spl/ir/worker_ir.py)
- [FlowRef 定义](../../../src/nl2spl/ir/worker_ir.py)
- [BlockIR 定义](../../../src/nl2spl/ir/block_structure_ir.py)
- [StepIR 定义](../../../src/nl2spl/ir/step_ir.py)
- [Stage 10 实现](../../../src/nl2spl/pipeline/stages/stage10_worker_assembler.py)
- [Stage 11 实现](../../../src/nl2spl/pipeline/stages/stage11_spl_renderer.py)
- [Orchestrator 实现](../../../src/nl2spl/pipeline/orchestrator.py)

### 8.3 设计决策

- **D3**: ChildWorkerIR 升级，增加 main_flow + steps 字段
- **D6**: Phase 3 策略，保留 legacy adapter
- **D7**: Phase 3 时机，T1.6 后可提前部分 T3
