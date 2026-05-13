# 工程师 C 上下文文档

**角色**: Resources 专家  
**负责任务**: 等待 → T2 → T3 辅助  
**预计工作时间**: 第 10-20 天

---

## 1. 项目背景

### 1.1 项目概述

nl2spl 是一个将自然语言（NL）转换为 SPL（Search Processing Language）的 pipeline 系统。用户输入自然语言查询，系统通过多个 Stage 处理，最终生成可执行的 SPL 代码。

### 1.2 当前问题

当前系统支持"worker"概念（类似于微服务或子任务），但实现不完整：
- SymbolTable 没有 worker scope 概念，变量可见性不明确
- Stage 6 只能提取 main worker 的资源，child worker 的资源被丢弃
- 同名变量在不同 worker 中会冲突

### 1.3 迁移目标

实现全链路 worker-aware，让 SymbolTable 和 Stage 6 能正确处理多个 worker。

---

## 2. 架构概览

### 2.1 Pipeline 流程（你的关注点）

```
Stage 5: Block Assembler（块组装）
    ↓
Stage 6: Resource Extractor（资源提取）← 你的重点任务
    ↓
Stage 7: Step Extractor（步骤提取）
    ↓
Stage 9.5: IR Normalizer（IR 校验）
    ↓
Stage 10: Worker Assembler（worker 组装）
    ↓
Stage 11: SPL Renderer（SPL 渲染）
    ↓
输出：SPL 代码
```

### 2.2 关键 IR（中间表示）

#### SymbolTable（符号表）

```python
class SymbolTable:
    """符号表。
    
    用途：管理变量声明和引用。
    
    当前问题：
    - 没有 worker scope 概念
    - 同名变量会冲突
    - 无法区分 global/worker/handoff 变量
    
    解决方案：
    - 使用复合 key: (scope_kind, scope_id, name)
    - 支持同名不同 scope 的变量
    """
    
    def __init__(self) -> None:
        self.variables: dict[str, VariableSymbol] = {}  # 旧接口，只存 global
        self._variables: dict[tuple[str, str | None, str], VariableSymbol] = {}  # 新接口，支持 scope
```

**文件位置**: `src/nl2spl/ir/symbol_table.py`

#### VariableSymbol（变量符号）

```python
@dataclass
class VariableSymbol:
    """变量符号。
    
    用途：存储变量的元数据。
    
    字段说明：
    - name: 变量名
    - data_type: 数据类型
    - source: 变量来源（input/output/step/api/file）
    - description: 变量描述
    - scope_kind: scope 类型（global/worker/handoff）
    - scope_id: scope ID（worker_id 或 handoff_id）
    - flow_ref: 关联的流程
    - block_ref: 关联的块
    - producer_step: 生产该变量的步骤
    - consumer_steps: 消费该变量的步骤列表
    - declared: 是否在 DEFINE_VARIABLES 中声明
    """
    name: str
    data_type: str
    source: str
    description: str
    scope_kind: Literal["global", "worker", "handoff"] = "global"
    scope_id: str | None = None
    flow_ref: str = "main"
    block_ref: str | None = None
    producer_step: str | None = None
    consumer_steps: list[str] = field(default_factory=list)
    declared: bool = True
```

**关键点**:
- `scope_kind` 和 `scope_id` 用于区分变量的 scope
- `declared` 用于控制是否在 SPL 中声明

#### ResourceRegistryIR（资源注册表）

```python
@dataclass
class ResourceRegistryIR:
    """资源注册表。
    
    用途：存储提取的资源。
    
    字段说明：
    - variables: 变量规格列表
    - files: 文件规格列表
    - apis: API 规格列表
    - types: 类型规格列表
    """
    variables: list[VariableSpec] = field(default_factory=list)
    files: list[FileSpec] = field(default_factory=list)
    apis: list[APISpec] = field(default_factory=list)
    types: list[TypeSpec] = field(default_factory=list)
```

**文件位置**: `src/nl2spl/ir/resource_registry_ir.py`

#### VariableSpec（变量规格）

```python
@dataclass
class VariableSpec:
    """变量规格。
    
    用途：存储变量的详细信息。
    
    字段说明：
    - name: 变量名（snake_case）
    - data_type: 数据类型
    - required: 是否必需
    - description: 变量描述
    - source: 变量来源（input/output/step/api/file）
    """
    name: str
    data_type: str
    required: bool
    description: str
    source: str
```

#### WorkerScopedResourceIR（worker-scoped 资源）

```python
@dataclass
class WorkerScopedResourceIR:
    """Worker-scoped 资源提取结果。
    
    用途：存储按 worker 分组的资源。
    
    字段说明：
    - global_resources: 全局资源（所有 worker 可见）
    - worker_resources: 按 worker_id 分组的资源
    - handoff_contracts: handoff 契约
    """
    global_resources: ResourceRegistryIR = field(default_factory=ResourceRegistryIR)
    worker_resources: dict[str, ResourceRegistryIR] = field(default_factory=dict)
    handoff_contracts: dict[str, HandoffContractIR] = field(default_factory=dict)
```

#### HandoffContractIR（handoff 契约）

```python
@dataclass
class HandoffContractIR:
    """Handoff 契约。
    
    用途：存储 worker 间的调用契约。
    
    字段说明：
    - handoff_id: handoff ID
    - parent_worker_id: 父 worker ID
    - child_worker_id: 子 worker ID
    - input_variables: 输入变量列表
    - output_variables: 输出变量列表
    """
    handoff_id: str
    parent_worker_id: str
    child_worker_id: str
    input_variables: list[ContractFieldIR] = field(default_factory=list)
    output_variables: list[ContractFieldIR] = field(default_factory=list)
```

#### ContractFieldIR（契约字段）

```python
@dataclass
class ContractFieldIR:
    """契约字段。
    
    用途：存储 worker 的输入/输出契约。
    
    字段说明：
    - name: 字段名
    - data_type: 数据类型
    - required: 是否必需
    - description: 字段描述
    - source: 来源（input/output/state/derived）
    """
    name: str
    data_type: str
    required: bool
    description: str
    source: Literal["input", "output", "state", "derived"]
```

---

## 3. 你的任务详解

### 3.1 T2: WorkerScopedResourceIR + SymbolTable（第 10-18 天）

**目标**: 让 Stage 6 支持 worker scope，明确 global/main/child/handoff 变量可见性。

#### 3.1.1 实现 WorkerScopedResourceIR

**文件**: `src/nl2spl/ir/resource_registry_ir.py`

需要新增 `WorkerScopedResourceIR` 类：

```python
@dataclass
class WorkerScopedResourceIR:
    """Worker-scoped 资源提取结果。
    
    用途：存储按 worker 分组的资源。
    
    使用场景：
    - global_resources: 存储所有 worker 共享的资源
    - worker_resources: 存储每个 worker 独立的资源
    - handoff_contracts: 存储 worker 间的调用契约
    """
    global_resources: ResourceRegistryIR = field(default_factory=ResourceRegistryIR)
    worker_resources: dict[str, ResourceRegistryIR] = field(default_factory=dict)
    handoff_contracts: dict[str, HandoffContractIR] = field(default_factory=dict)
```

**设计决策**:
- `global_resources` 存储所有 worker 共享的资源
- `worker_resources` 按 worker_id 分组存储独立资源
- `handoff_contracts` 存储 worker 间的调用契约

#### 3.1.2 实现 HandoffContractIR

**文件**: `src/nl2spl/ir/worker_plan_ir.py`

需要新增 `HandoffContractIR` 类：

```python
@dataclass
class HandoffContractIR:
    """Handoff 契约。
    
    用途：存储 worker 间的调用契约。
    
    使用场景：
    - 存储父 worker 传递给子 worker 的输入变量
    - 存储子 worker 返回给父 worker 的输出变量
    """
    handoff_id: str
    parent_worker_id: str
    child_worker_id: str
    input_variables: list[ContractFieldIR] = field(default_factory=list)
    output_variables: list[ContractFieldIR] = field(default_factory=list)
```

#### 3.1.3 修改 SymbolTable 支持 scope

**文件**: `src/nl2spl/ir/symbol_table.py`

需要修改 `VariableSymbol` 和 `SymbolTable`：

**修改 VariableSymbol**:

```python
@dataclass
class VariableSymbol:
    """变量符号。
    
    升级内容：
    - 新增 scope_kind: scope 类型（global/worker/handoff）
    - 新增 scope_id: scope ID（worker_id 或 handoff_id）
    """
    name: str
    data_type: str
    source: str
    description: str
    # 新增字段（D4 决策）
    scope_kind: Literal["global", "worker", "handoff"] = "global"
    scope_id: str | None = None
    # 保留旧字段兼容性
    flow_ref: str = "main"
    block_ref: str | None = None
    producer_step: str | None = None
    consumer_steps: list[str] = field(default_factory=list)
    declared: bool = True
```

**修改 SymbolTable**:

```python
class SymbolTable:
    """符号表。
    
    升级内容：
    - 新增 _variables: 使用复合 key 存储变量
    - 保留 self.variables: 兼容旧接口，只存 global 变量
    - 新增 declare_scoped(): 声明带 scope 的变量
    - 新增 get_variables_for_worker(): 获取 worker 可见的变量
    - 新增 get_variables_for_handoff(): 获取 handoff 可见的变量
    - 新增 get_all_declared_variables(): 获取所有声明的变量
    """
    
    def __init__(self) -> None:
        """初始化空符号表。"""
        # 新接口：使用复合 key
        self._variables: dict[tuple[str, str | None, str], VariableSymbol] = {}
        # 旧接口：只存 global 变量
        self.variables: dict[str, VariableSymbol] = {}
    
    def declare_scoped(
        self,
        name: str,
        data_type: str,
        source: str,
        description: str,
        scope_kind: Literal["global", "worker", "handoff"] = "global",
        scope_id: str | None = None,
    ) -> None:
        """声明带 scope 的变量。
        
        Args:
            name: 变量名
            data_type: 数据类型
            source: 变量来源
            description: 变量描述
            scope_kind: scope 类型
            scope_id: scope ID（worker_id 或 handoff_id）
        
        设计决策 D4：使用复合 key (scope_kind, scope_id, name)
        """
        key = (scope_kind, scope_id, name)
        self._variables[key] = VariableSymbol(
            name=name,
            data_type=data_type,
            source=source,
            description=description,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )
        
        # 兼容旧接口：global 变量也加入 self.variables
        if scope_kind == "global":
            self.variables[name] = self._variables[key]
    
    def get_variables_for_worker(self, worker_id: str) -> dict[str, VariableSymbol]:
        """获取 worker 可见的变量。
        
        返回 global + worker-scoped 变量。
        
        Args:
            worker_id: worker ID
        
        Returns:
            变量名到 VariableSymbol 的映射
        """
        result = {}
        
        # Global 变量
        for key, var in self._variables.items():
            if key[0] == "global":
                result[var.name] = var
        
        # Worker-scoped 变量
        for key, var in self._variables.items():
            if key[0] == "worker" and key[1] == worker_id:
                result[var.name] = var
        
        return result
    
    def get_variables_for_handoff(self, handoff_id: str) -> dict[str, VariableSymbol]:
        """获取 handoff 可见的变量。
        
        返回 global + handoff-scoped 变量。
        
        Args:
            handoff_id: handoff ID
        
        Returns:
            变量名到 VariableSymbol 的映射
        """
        result = {}
        
        # Global 变量
        for key, var in self._variables.items():
            if key[0] == "global":
                result[var.name] = var
        
        # Handoff-scoped 变量
        for key, var in self._variables.items():
            if key[0] == "handoff" and key[1] == handoff_id:
                result[var.name] = var
        
        return result
    
    def get_variable_list_for_worker_prompt(self, worker_id: str) -> str:
        """生成 worker 的变量列表文本（用于 LLM prompt）。
        
        Args:
            worker_id: worker ID
        
        Returns:
            格式化的变量列表字符串
        """
        visible_vars = self.get_variables_for_worker(worker_id)
        if not visible_vars:
            return "No variables available."
        
        lines = []
        for var in visible_vars.values():
            scope_info = ""
            if var.scope_kind == "worker":
                scope_info = f" [worker: {var.scope_id}]"
            elif var.scope_kind == "handoff":
                scope_info = f" [handoff: {var.scope_id}]"
            lines.append(
                f"- {var.name}: {var.data_type} ({var.source}){scope_info} - {var.description}"
            )
        return "\n".join(lines)
    
    def get_all_declared_variables(self) -> dict[str, VariableSymbol]:
        """获取所有声明的变量（用于 SPL DEFINE_VARIABLES）。
        
        包含：
        - global 变量
        - 所有 contract 变量（input/output）
        - 所有渲染的步骤变量
        
        不包含：
        - worker 内部变量（除非被声明为 contract）
        """
        result = {}
        
        for key, var in self._variables.items():
            # global 变量总是包含
            if key[0] == "global":
                result[var.name] = var
            # contract 变量（input/output）总是包含
            elif var.source in ("input", "output"):
                result[var.name] = var
            # 渲染的步骤变量如果 declared 则包含
            elif var.declared:
                result[var.name] = var
        
        return result
```

**设计决策**:
- 使用复合 key `(scope_kind, scope_id, name)` 支持同名不同 scope 的变量
- 保持 `self.variables` 兼容旧接口
- `get_all_declared_variables()` 用于 SPL DEFINE_VARIABLES

#### 3.1.4 实现 execute_worker_scoped()

**文件**: `src/nl2spl/pipeline/stages/stage6_resource_extractor.py`

新增方法，按 worker 提取资源：

```python
def execute_worker_scoped(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
    worker_plan: WorkerPlanIR,
    canonical_input: CanonicalCompileInput,
) -> tuple[WorkerScopedResourceIR, SymbolTable]:
    """执行 worker-scoped 资源提取。
    
    工作流程：
    1. 提取 global 资源（从 main worker）
    2. 遍历 child workers：
       - 提取 child 的资源
       - 使用 symbol_table.declare_scoped() 声明变量
    3. 提取 handoff contracts
    4. 返回 WorkerScopedResourceIR
    """
```

#### 3.1.5 实现 _extract_resources_for_scope()

提取特定 scope 的资源：

```python
def _extract_resources_for_scope(
    self,
    spans: list[SpanIR],
    routes: FieldRouteIR,
    flow: FlowStructureIR,
    blocks: BlockStructureIR,
    symbol_table: SymbolTable,
    canonical_input: CanonicalCompileInput,
    scope_kind: Literal["global", "worker", "handoff"] = "global",
    scope_id: str | None = None,
) -> tuple[ResourceRegistryIR, SymbolTable]:
    """提取特定 scope 的资源。
    
    工作流程：
    1. 从 spans 提取变量、文件、API、类型
    2. 使用 symbol_table.declare_scoped() 声明变量
    3. 返回 ResourceRegistryIR
    """
```

#### 3.1.6 实现 _build_handoff_contract()

构建 handoff 契约：

```python
def _build_handoff_contract(
    self,
    handoff: WorkerHandoffIR,
    symbol_table: SymbolTable,
) -> HandoffContractIR:
    """构建 handoff 契约。
    
    工作流程：
    1. 从 handoff.input_bindings 提取输入变量
    2. 从 handoff.output_bindings 提取输出变量
    3. 返回 HandoffContractIR
    """
```

#### 3.1.7 修改 Orchestrator

**文件**: `src/nl2spl/pipeline/orchestrator.py`

新增 worker-aware 调用路径：

```python
# Stage 6 调用逻辑
if (self.config.enable_worker_boundary_planner
    and worker_flow_plan is not None
    and worker_block_plan is not None
    and worker_plan is not None):
    # Worker-aware path
    worker_scoped_resources, symbol_table = self._run_stage6_worker_scoped(...)
    resources = worker_scoped_resources.global_resources
else:
    # Legacy path
    resources, symbol_table = self._run_stage6(...)
```

**验收标准**:
- [ ] `WorkerScopedResourceIR` 类定义正确
- [ ] `HandoffContractIR` 类定义正确
- [ ] `SymbolTable` 支持 worker scope（D4: 复合 key）
- [ ] `VariableSymbol` 包含 `scope_kind` 和 `scope_id` 字段
- [ ] `declare_scoped()` 实现正确
- [ ] `get_variables_for_worker()` 实现正确
- [ ] `get_variables_for_handoff()` 实现正确
- [ ] `get_all_declared_variables()` 实现正确
- [ ] `execute_worker_scoped()` 实现正确
- [ ] `_extract_resources_for_scope()` 实现正确
- [ ] `_build_handoff_contract()` 实现正确
- [ ] Orchestrator 正确处理两种 path
- [ ] 所有测试通过

---

## 4. 关键概念

### 4.1 变量 Scope

变量可以有三种 scope：

| scope_kind | scope_id | 说明 | 示例 |
|------------|----------|------|------|
| global | None | 全局变量，所有 worker 可见 | query, result |
| worker | worker_id | worker 内部变量 | temp_data (worker_1) |
| handoff | handoff_id | handoff 变量 | input (handoff_1) |

**示例**:
```python
# 全局变量
symbol_table.declare_scoped("query", "str", "input", "查询文本", scope_kind="global")

# worker 变量
symbol_table.declare_scoped("temp_data", "dict", "step", "临时数据", scope_kind="worker", scope_id="worker_1")

# handoff 变量
symbol_table.declare_scoped("input", "str", "input", "输入数据", scope_kind="handoff", scope_id="handoff_1")
```

### 4.2 变量可见性

| 变量类型 | 可见范围 |
|----------|----------|
| global | 所有 worker |
| worker | 只有该 worker |
| handoff | 只有该 handoff |

**示例**:
```python
# worker_1 可以看到：
# - global 变量
# - worker_1 的变量
# 但不能看到 worker_2 的变量

visible_vars = symbol_table.get_variables_for_worker("worker_1")
```

### 4.3 同名变量处理

使用复合 key 支持同名不同 scope 的变量：

```python
# 两个 worker 都有 "result" 变量
symbol_table.declare_scoped("result", "dict", "step", "worker_1 结果", scope_kind="worker", scope_id="worker_1")
symbol_table.declare_scoped("result", "dict", "step", "worker_2 结果", scope_kind="worker", scope_id="worker_2")

# 获取 worker_1 的变量
vars_1 = symbol_table.get_variables_for_worker("worker_1")
# vars_1["result"] -> worker_1 的 result

# 获取 worker_2 的变量
vars_2 = symbol_table.get_variables_for_worker("worker_2")
# vars_2["result"] -> worker_2 的 result
```

### 4.4 DEFINE_VARIABLES 策略

SPL 的 DEFINE_VARIABLES 应该包含：

| 变量类型 | 是否包含 | 原因 |
|----------|----------|------|
| global | 是 | 所有 worker 共享 |
| contract (input/output) | 是 | worker 的接口 |
| worker 内部 | 否 | 封装在 worker 内部 |

**示例**:
```spl
worker main
  inputs
    query (required)
  outputs
    result (required)
  flow main
    command st1
      description "步骤 1"
  
  worker child_1
    inputs
      input (required)
    outputs
      output (required)
    flow main
      command st_child_1
        description "处理输入"
```

在这个示例中：
- `query`, `result` 是 main worker 的 contract，会被声明
- `input`, `output` 是 child_1 的 contract，会被声明
- child_1 内部的变量不会被声明

### 4.5 Handoff 契约

Handoff 契约定义了 worker 间的调用关系：

```python
HandoffContractIR(
    handoff_id="handoff_1",
    parent_worker_id="main",
    child_worker_id="child_1",
    input_variables=[
        ContractFieldIR(name="input", data_type="str", required=True, description="输入数据", source="input"),
    ],
    output_variables=[
        ContractFieldIR(name="output", data_type="str", required=True, description="输出数据", source="output"),
    ],
)
```

**含义**: main worker 调用 child_1，传递 `input` 变量，接收 `output` 变量。

---

## 5. 开发环境

### 5.1 代码结构

```
src/nl2spl/
├── ir/                              # 中间表示定义
│   ├── symbol_table.py              # SymbolTable, VariableSymbol
│   ├── resource_registry_ir.py      # ResourceRegistryIR, WorkerScopedResourceIR
│   ├── worker_plan_ir.py            # WorkerPlanIR, HandoffContractIR
│   ├── flow_structure_ir.py         # FlowStructureIR
│   ├── block_structure_ir.py        # BlockStructureIR
│   └── step_ir.py                   # StepIR
├── pipeline/                        # Pipeline 实现
│   ├── orchestrator.py              # Pipeline 编排器
│   └── stages/                      # 各个 Stage
│       ├── stage6_resource_extractor.py # Stage 6 实现
│       └── ...
└── tests/                           # 测试
    ├── ir/                          # IR 测试
    └── pipeline/                    # Pipeline 测试
```

### 5.2 关键文件

你需要修改的文件：
1. `src/nl2spl/ir/resource_registry_ir.py` - T2: 新增 WorkerScopedResourceIR
2. `src/nl2spl/ir/worker_plan_ir.py` - T2: 新增 HandoffContractIR
3. `src/nl2spl/ir/symbol_table.py` - T2: 修改 SymbolTable 支持 scope
4. `src/nl2spl/pipeline/stages/stage6_resource_extractor.py` - T2: 新增 worker-aware 方法
5. `src/nl2spl/pipeline/orchestrator.py` - T2: 新增调用路径

### 5.3 测试文件

你需要创建的测试文件：
1. `tests/ir/test_worker_scoped_resource_ir.py` - T2 测试
2. `tests/ir/test_symbol_table_scoped.py` - T2 测试
3. `tests/pipeline/stages/test_stage6_worker_scoped.py` - T2 测试

---

## 6. 测试策略

### 6.1 单元测试

每个新增方法都需要单元测试：

```python
class TestWorkerScopedResourceIR:
    def test_init_with_defaults(self):
        """测试默认值初始化。"""
        
    def test_init_with_global_resources(self):
        """测试带 global resources 初始化。"""
        
    def test_init_with_worker_resources(self):
        """测试带 worker resources 初始化。"""
        
    def test_init_with_handoff_contracts(self):
        """测试带 handoff contracts 初始化。"""
```

```python
class TestSymbolTableScoped:
    def test_declare_scoped_global(self):
        """测试声明 global 变量。"""
        
    def test_declare_scoped_worker(self):
        """测试声明 worker 变量。"""
        
    def test_declare_scoped_handoff(self):
        """测试声明 handoff 变量。"""
        
    def test_get_variables_for_worker(self):
        """测试获取 worker 可见的变量。"""
        
    def test_get_variables_for_handoff(self):
        """测试获取 handoff 可见的变量。"""
        
    def test_get_variable_list_for_worker_prompt(self):
        """测试生成 worker 的变量列表文本。"""
        
    def test_get_all_declared_variables(self):
        """测试获取所有声明的变量。"""
        
    def test_same_name_different_scope(self):
        """测试同名不同 scope 的变量。"""
        
    def test_backward_compatibility(self):
        """测试向后兼容性。"""
```

```python
class TestResourceExtractorWorkerScoped:
    def test_execute_worker_scoped_single_worker(self):
        """测试单个 worker 的资源提取。"""
        
    def test_execute_worker_scoped_multiple_workers(self):
        """测试多个 worker 的资源提取。"""
        
    def test_extract_resources_for_scope_global(self):
        """测试提取 global 资源。"""
        
    def test_extract_resources_for_scope_worker(self):
        """测试提取 worker 资源。"""
        
    def test_build_handoff_contract(self):
        """测试构建 handoff 契约。"""
```

### 6.2 集成测试

端到端测试：

```python
class TestWorkerAwarePipeline:
    def test_end_to_end_resource_extraction(self):
        """测试资源提取的端到端流程。"""
        
    def test_variable_visibility(self):
        """测试变量可见性。"""
        
    def test_same_name_different_scope(self):
        """测试同名不同 scope 的变量。"""
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

### 7.1 如何声明带 scope 的变量？

```python
# 全局变量
symbol_table.declare_scoped(
    name="query",
    data_type="str",
    source="input",
    description="查询文本",
    scope_kind="global",
)

# worker 变量
symbol_table.declare_scoped(
    name="temp_data",
    data_type="dict",
    source="step",
    description="临时数据",
    scope_kind="worker",
    scope_id="worker_1",
)

# handoff 变量
symbol_table.declare_scoped(
    name="input",
    data_type="str",
    source="input",
    description="输入数据",
    scope_kind="handoff",
    scope_id="handoff_1",
)
```

### 7.2 如何获取 worker 可见的变量？

```python
# 获取 worker_1 可见的变量
visible_vars = symbol_table.get_variables_for_worker("worker_1")

# 生成变量列表文本（用于 LLM prompt）
var_list = symbol_table.get_variable_list_for_worker_prompt("worker_1")
```

### 7.3 如何处理同名变量？

```python
# 两个 worker 都有 "result" 变量
symbol_table.declare_scoped("result", "dict", "step", "worker_1 结果", scope_kind="worker", scope_id="worker_1")
symbol_table.declare_scoped("result", "dict", "step", "worker_2 结果", scope_kind="worker", scope_id="worker_2")

# 获取 worker_1 的变量
vars_1 = symbol_table.get_variables_for_worker("worker_1")
# vars_1["result"] -> worker_1 的 result

# 获取 worker_2 的变量
vars_2 = symbol_table.get_variables_for_worker("worker_2")
# vars_2["result"] -> worker_2 的 result
```

### 7.4 如何构建 WorkerScopedResourceIR？

```python
worker_scoped_resources = WorkerScopedResourceIR(
    global_resources=global_resources,
    worker_resources={
        "worker_1": worker_1_resources,
        "worker_2": worker_2_resources,
    },
    handoff_contracts={
        "handoff_1": handoff_1_contract,
        "handoff_2": handoff_2_contract,
    },
)
```

### 7.5 如何构建 HandoffContractIR？

```python
handoff_contract = HandoffContractIR(
    handoff_id=handoff.handoff_id,
    parent_worker_id=handoff.from_worker,
    child_worker_id=handoff.to_worker,
    input_variables=[
        ContractFieldIR(
            name=binding.parent_variable,
            data_type="str",
            required=True,
            description=f"Input from {binding.parent_variable}",
            source="input",
        )
        for binding in handoff.input_bindings
    ],
    output_variables=[
        ContractFieldIR(
            name=binding.child_output,
            data_type="str",
            required=True,
            description=f"Output from {binding.child_output}",
            source="output",
        )
        for binding in handoff.output_bindings
    ],
)
```

### 7.6 如何处理 legacy path？

```python
if (self.config.enable_worker_boundary_planner
    and worker_flow_plan is not None
    and worker_block_plan is not None
    and worker_plan is not None):
    # Worker-aware path
    worker_scoped_resources, symbol_table = self._run_stage6_worker_scoped(...)
    resources = worker_scoped_resources.global_resources
else:
    # Legacy path
    resources, symbol_table = self._run_stage6(...)
```

---

## 8. 参考资料

### 8.1 文档

- [迁移方案 v3.0](../../migration-worker-aware-pipeline.md)
- [任务总览](README.md)
- [T2 任务文档](T2-scoped-resources-symboltable.md)

### 8.2 代码

- [SymbolTable 定义](../../../src/nl2spl/ir/symbol_table.py)
- [VariableSymbol 定义](../../../src/nl2spl/ir/symbol_table.py)
- [ResourceRegistryIR 定义](../../../src/nl2spl/ir/resource_registry_ir.py)
- [WorkerScopedResourceIR 定义](../../../src/nl2spl/ir/resource_registry_ir.py)
- [HandoffContractIR 定义](../../../src/nl2spl/ir/worker_plan_ir.py)
- [ContractFieldIR 定义](../../../src/nl2spl/ir/worker_plan_ir.py)
- [Stage 6 实现](../../../src/nl2spl/pipeline/stages/stage6_resource_extractor.py)
- [Orchestrator 实现](../../../src/nl2spl/pipeline/orchestrator.py)

### 8.3 设计决策

- **D4**: SymbolTable scope 使用复合 key `(scope_kind, scope_id, name)`
- **D5**: span ownership violation 是 error
