# 工程师 B - T1.6 准备文档

**日期**: 2026-05-12  
**状态**: 准备完成  
**前置条件**: T0 修复 ChildWorkerIR 缺失字段后可开始

---

## 1. 代码库分析摘要

### 1.1 Stage 10 (WorkerAssembler) - 当前状态

**文件**: `src/nl2spl/pipeline/stages/stage10_worker_assembler.py`

**当前实现**:
- `assemble()` 方法接收 legacy IRs (FlowStructureIR, BlockStructureIR, steps) + 可选 WorkerPlanIR
- `_child_workers_from_plan()` 从 WorkerPlanIR 构建 ChildWorkerIR
- `_child_workers_from_delegation()` 从 delegation_candidates 构建 ChildWorkerIR (legacy path)

**关键问题**:
```python
# line 174-182: _child_workers_from_plan() 创建 ChildWorkerIR 时
# 只设置了基本字段，没有传递 flow/blocks 信息
ChildWorkerIR(
    worker_name=spec.worker_name,
    description=spec.purpose or spec.reason,
    task_text=invoke_step.text if invoke_step else spec.purpose or spec.reason,
    inputs=self._inputs_from_contract(spec.input_contract),
    outputs=self._outputs_from_contract(spec.output_contract),
    # ❌ 缺少: main_flow, alternative_flows, exception_flows, api_refs, steps
)
```

**需要新增的方法**:
1. `assemble_from_worker_scoped()` - 从 worker-scoped 数据组装 WorkerIR
2. `_build_child_worker()` - 构建包含完整 flow/steps 的 ChildWorkerIR

---

### 1.2 Stage 11 (SPLRenderer) - 当前状态

**文件**: `src/nl2spl/pipeline/stages/stage11_spl_renderer.py`

**当前实现**:
- `render()` 方法渲染 WorkerIR 为 SPL 文本
- 主 worker 渲染正确使用 `worker.main_flow.blocks` (line 181)
- 主 worker 正确渲染 alternative_flows (line 185-196) 和 exception_flows (line 199-210)

**关键问题 - "synthetic st_child" 问题** (line 237-270):
```python
def _render_child_worker(self, worker: ChildWorkerIR) -> list[str]:
    """Render a concrete child worker generated from delegation."""
    lines = [f'[DEFINE_WORKER: "{self._quote_text(worker.description)}" {worker.worker_name}]']
    # ...
    lines.append("    [MAIN_FLOW]")
    lines.append("        [SEQUENTIAL_BLOCK]")
    
    # ❌ 问题所在：创建 synthetic step，忽略 child 的实际 flow/steps
    child_step = StepIR(
        step_id="st_child",           # synthetic ID
        text=worker.task_text,         # 使用 task_text 而非实际 steps
        source_span_ids=[],
        command_type="GENERAL_COMMAND",
        inputs=[inp.name for inp in worker.inputs],
        outputs=[out.name for ref worker.outputs],
    )
    lines.append(f"            {self._render_step(child_step)}")
    lines.append("        [END_SEQUENTIAL_BLOCK]")
    lines.append("    [END_MAIN_FLOW]")
    lines.append("[END_WORKER]")
    # ❌ 没有渲染 alternative_flows 和 exception_flows
```

**需要修改的方法**:
1. `_render_child_worker()` - 使用 child 的实际 flow/blocks/steps 渲染

**可复用的现有方法**:
- `_render_blocks(blocks, steps, indent)` - 渲染块列表 (line 293)
- `_render_step(step, condition_text)` - 渲染单个步骤 (line 396)
- `_steps_for_block(block, steps)` - 获取块对应的步骤 (line 365)

---

### 1.3 ChildWorkerIR - 当前状态

**文件**: `src/nl2spl/ir/worker_ir.py`

**当前字段** (line 78-101):
```python
@dataclass
class ChildWorkerIR:
    worker_name: str
    description: str
    task_text: str
    inputs: list[WorkerInput] = field(default_factory=list)
    outputs: list[WorkerOutput] = field(default_factory=list)
    main_flow: FlowRef = field(default_factory=FlowRef)      # ✅ 已添加
    steps: list[StepIR] = field(default_factory=list)          # ✅ 已添加
    # ❌ 缺少: alternative_flows, exception_flows, api_refs
```

**需要补充的字段** (T0 修复):
```python
    alternative_flows: list[AlternativeFlowRef] = field(default_factory=list)  # ← 新增
    exception_flows: list[ExceptionFlowRef] = field(default_factory=list)      # ← 新增
    api_refs: list[str] = field(default_factory=list)                          # ← 新增
```

---

### 1.4 Orchestrator - 当前状态

**文件**: `src/nl2spl/pipeline/orchestrator.py`

**当前实现**:
- `_run_stage10()` (line 450) 调用 `assembler.assemble()` 使用 legacy IRs
- `_run_stage11()` (line 463) 调用 `renderer.render()`

**需要新增**:
- `_run_stage10_worker_scoped()` 方法，使用 worker-scoped IRs 调用新方法

---

### 1.5 Worker-scoped IR 数据结构

**文件**: `src/nl2spl/ir/worker_plan_ir.py`

```python
@dataclass
class WorkerFlowPlanIR:
    """Flow structure scoped to workers."""
    worker_flows: dict[str, FlowStructureIR] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

@dataclass
class WorkerBlockPlanIR:
    """Block structure scoped to workers."""
    worker_blocks: dict[str, BlockStructureIR] = field(default_factory=dict)
    control_complexity_regions: list[ControlComplexityRegionIR] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

@dataclass
class WorkerStepPlanIR:
    """Steps scoped to workers."""
    main_worker_id: str
    worker_steps: dict[str, list[StepIR]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    
    @property
    def main_worker_steps(self) -> list[StepIR]:
        return self.worker_steps.get(self.main_worker_id, [])
    
    def get_all_steps(self) -> list[StepIR]:
        all_steps: list[StepIR] = []
        for steps in self.worker_steps.values():
            all_steps.extend(steps)
        return all_steps
```

---

## 2. T1.6 实现计划

### 2.1 Phase 1: 修复 ChildWorkerIR (依赖 T0)

**前提**: 等待工程师 A 修复 T0 的 ChildWorkerIR 缺失字段

**修改文件**: `src/nl2spl/ir/worker_ir.py`

```python
@dataclass
class ChildWorkerIR:
    """Concrete child worker with full flow and steps support."""
    worker_name: str
    description: str
    task_text: str
    inputs: list[WorkerInput] = field(default_factory=list)
    outputs: list[WorkerOutput] = field(default_factory=list)
    # Flow support
    main_flow: FlowRef = field(default_factory=FlowRef)
    alternative_flows: list[AlternativeFlowRef] = field(default_factory=list)  # ← 新增
    exception_flows: list[ExceptionFlowRef] = field(default_factory=list)      # ← 新增
    api_refs: list[str] = field(default_factory=list)                          # ← 新增
    steps: list[StepIR] = field(default_factory=list)
```

### 2.2 Phase 2: 修改 Stage 10 WorkerAssembler

**修改文件**: `src/nl2spl/pipeline/stages/stage10_worker_assembler.py`

**新增方法**:

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
    
    工作流程:
    1. 获取 main worker 的 steps
    2. 遍历 child workers:
       - 获取 child 的 steps、flow、blocks
       - 调用 _build_child_worker() 构建 ChildWorkerIR
    3. 构建 main worker 的 flow
    4. 返回 WorkerIR
    """

def _build_child_worker(
    self,
    worker: WorkerSpecIR,
    steps: list[StepIR],
    flow: FlowStructureIR | None,
    blocks: BlockStructureIR | None,
    symbol_table: SymbolTable,
) -> ChildWorkerIR:
    """构建包含完整 flow/steps 的 ChildWorkerIR。
    
    工作流程:
    1. 构建 main_flow（从 blocks.main_flow_blocks）
    2. 构建 alternative_flows（从 flow.alternative_flows + blocks）
    3. 构建 exception_flows（从 flow.exception_flows + blocks）
    4. 收集 api_refs（从 steps 中的 CALL_API）
    5. 返回 ChildWorkerIR（包含 steps）
    """
```

### 2.3 Phase 3: 修改 Stage 11 SPLRenderer

**修改文件**: `src/nl2spl/pipeline/stages/stage11_spl_renderer.py`

**修改方法**: `_render_child_worker()`

```python
def _render_child_worker(self, child: ChildWorkerIR) -> list[str]:
    """Render child worker with full flow support.
    
    使用 child.main_flow.blocks 和 child.steps 渲染，
    而不是 synthetic st_child。
    """
    lines = [f'[DEFINE_WORKER: "{self._quote_text(child.description)}" {child.worker_name}]']
    previous_produced = self._produced_variables
    self._produced_variables = {inp.name for inp in child.inputs}
    
    # INPUTS
    lines.append("    [INPUTS]")
    for inp in child.inputs:
        req = "REQUIRED" if inp.required else "OPTIONAL"
        lines.append(f"        {req} <REF>{inp.name}</REF>")
    lines.append("    [END_INPUTS]")
    
    # OUTPUTS
    lines.append("    [OUTPUTS]")
    for out in child.outputs:
        req = "REQUIRED" if out.required else "OPTIONAL"
        lines.append(f"        {req} <REF>{out.name}</REF>")
    lines.append("    [END_OUTPUTS]")
    
    # MAIN_FLOW - 使用 child 的实际 blocks 和 steps
    lines.append("    [MAIN_FLOW]")
    lines.extend(self._render_blocks(child.main_flow.blocks, child.steps, indent=8))
    lines.append("    [END_MAIN_FLOW]")
    
    # ALTERNATIVE_FLOWs
    for alt_flow in child.alternative_flows:
        condition = self._render_condition(alt_flow.condition_text)
        lines.append(f"    [ALTERNATIVE_FLOW: {condition}]")
        lines.extend(self._render_blocks(alt_flow.blocks, child.steps, indent=8))
        lines.append("    [END_ALTERNATIVE_FLOW]")
    
    # EXCEPTION_FLOWs
    for exc_flow in child.exception_flows:
        condition = self._render_condition(exc_flow.condition_text)
        lines.append(f"    [EXCEPTION_FLOW: {condition}]")
        lines.extend(self._render_blocks(exc_flow.blocks, child.steps, indent=8))
        lines.append("    [END_EXCEPTION_FLOW]")
    
    lines.append("[END_WORKER]")
    self._produced_variables = previous_produced
    return lines
```

### 2.4 Phase 4: 修改 Orchestrator

**修改文件**: `src/nl2spl/pipeline/orchestrator.py`

**新增方法**:

```python
def _run_stage10_worker_scoped(
    self,
    worker_step_plan: WorkerStepPlanIR,
    resources: ResourceRegistryIR,
    symbol_table: SymbolTable,
    worker_plan: WorkerPlanIR,
    worker_flow_plan: WorkerFlowPlanIR | None = None,
    worker_block_plan: WorkerBlockPlanIR | None = None,
) -> WorkerIR:
    """Run Stage 10 with worker-scoped input."""
    assembler = WorkerAssembler()
    return assembler.assemble_from_worker_scoped(
        worker_step_plan, resources, symbol_table, 
        worker_plan, worker_flow_plan, worker_block_plan
    )
```

**修改 Stage 10 调用** (line 268-277):

```python
# Stage 10: Worker Assembly
if (self.config.enable_worker_boundary_planner
    and worker_step_plan is not None
    and worker_plan is not None):
    # Worker-aware path
    worker = self._run_stage10_worker_scoped(
        worker_step_plan, resources, symbol_table, 
        worker_plan, worker_flow_plan, worker_block_plan
    )
else:
    # Legacy path
    worker = self._run_stage10(flow_structure, block_structure, steps, resources, symbol_table, worker_plan)
```

---

## 3. 测试计划

### 3.1 新增测试文件

1. `tests/ir/test_child_worker_ir.py` - ChildWorkerIR 单元测试
2. `tests/pipeline/stages/test_stage10_worker_scoped.py` - Stage 10 worker-scoped 测试
3. `tests/pipeline/stages/test_stage11_child_worker_render.py` - Stage 11 child worker 渲染测试

### 3.2 关键测试场景

**ChildWorkerIR**:
- 初始化只有默认值
- 初始化包含 flow
- 初始化包含 steps
- 初始化包含所有字段

**Stage 10 worker-scoped**:
- 单个 main worker 组装
- main + child workers 组装
- child worker 包含 flow
- child worker 包含 steps

**Stage 11 child worker 渲染**:
- child worker 包含 flow 渲染
- child worker 包含 steps 渲染
- child worker 包含 alternative_flows 渲染
- child worker 包含 exception_flows 渲染
- 各种 block 类型渲染 (SEQUENTIAL, IF, FOR, WHILE)

---

## 4. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| T0 修复延迟 | 高 | 可先实现 Stage 10/11，待 T0 修复后集成 |
| _render_blocks 复用问题 | 中 | 已验证现有方法支持 child steps |
| Orchestrator 集成复杂 | 中 | 保持 legacy path 兼容 |

---

## 5. 依赖关系

**前置依赖**:
- T0: ChildWorkerIR 缺失字段修复 (alternative_flows, exception_flows, api_refs)

**后续任务**:
- T2: WorkerScopedResourceIR + SymbolTable
- T3: worker-aware path 去 adapter

---

## 6. 准备完成清单

- [x] 理解 Stage 10 当前实现
- [x] 理解 Stage 11 当前实现
- [x] 识别 "synthetic st_child" 问题
- [x] 理解 Worker-scoped IR 数据结构
- [x] 识别 ChildWorkerIR 缺失字段
- [x] 制定实现计划
- [x] 制定测试计划
- [ ] 等待 T0 修复 (阻塞项)

---

**结论**: T1.6 准备工作已完成。主要阻塞项是 T0 的 ChildWorkerIR 缺失字段修复。一旦工程师 A 完成修复，即可开始实现。
