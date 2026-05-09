# Developer A (Tech Lead) - 详细开发计划

## 角色定位

**代号**: A  
**角色**: Tech Lead  
**职责**: 架构搭建、代码审查、集成调试、发布管理

---

## Week 1: 基础架构搭建

### Day 1-2: 项目初始化

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T1.1.1 创建 pyproject.toml | `pyproject.toml` | 项目配置 | `pip install -e .` 成功 |
| T1.1.2 创建 .env.example | `.env.example` | 环境变量模板 | 包含所有必要配置项 |
| T1.1.3 创建 config.py | `src/nl2spl/config.py` | 配置管理 | 支持 LLMConfig + PipelineConfig |
| T1.1.4 创建 main.py | `src/nl2spl/main.py` | 入口点 | 支持 stdin/file 输入 |

**config.py 接口定义**:
```python
@dataclass
class LLMConfig:
    model: str = "gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.0
    api_key: Optional[str] = None
    base_url: Optional[str] = None

@dataclass
class PipelineConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    output_dir: Path = Path("output")
    save_intermediate: bool = True
    log_level: str = "INFO"
    log_file: Optional[Path] = None
    max_retries: int = 3
```

### Day 2-3: 错误处理模块

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T1.2.1 定义异常层次 | `src/nl2spl/errors/exceptions.py` | 异常类 | 5 个异常类 |
| T1.2.2 创建 __init__.py | `src/nl2spl/errors/__init__.py` | 导出 | 正确导出所有异常 |

**异常层次**:
```
NL2SPLError (基类)
├── PipelineError (管道错误)
├── StageError (Stage 错误)
├── LLMError (LLM API 错误)
├── IRValidationError (IR 校验错误)
└── SpanError (Span 处理错误)
```

### Day 3-4: 工具模块

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T1.3.1 日志模块 | `src/nl2spl/utils/logger.py` | 日志工具 | 支持 console + file |
| T1.3.2 持久化模块 | `src/nl2spl/utils/persistence.py` | 中间结果保存 | JSON 格式保存 |
| T1.3.3 创建 __init__.py | `src/nl2spl/utils/__init__.py` | 导出 | 正确导出 |

**logger.py 接口**:
```python
def setup_logger(name: str, level: str, log_file: Optional[Path]) -> logging.Logger
def get_stage_logger(stage_name: str) -> logging.Logger
```

**persistence.py 接口**:
```python
def save_intermediate_result(stage_name: str, result: dict, output_dir: Path) -> Path
def load_intermediate_result(filepath: Path) -> dict
def save_ir_snapshot(stage_name: str, ir_data: Any, output_dir: Path) -> Path
```

### Day 4-5: IR 数据模型

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T1.4.1 SpanIR | `src/nl2spl/ir/span_ir.py` | Span 数据类 | 含 AmbiguityInfo |
| T1.4.2 FieldRouteIR | `src/nl2spl/ir/field_route_ir.py` | 路由结果 | 含 validate_no_overlap() |
| T1.4.3 FlowStructureIR | `src/nl2spl/ir/flow_structure_ir.py` | Flow 结构 | 含 delegation_candidates |
| T1.4.4 BlockStructureIR | `src/nl2spl/ir/block_structure_ir.py` | Block 结构 | 含 BlockType 枚举 |
| T1.4.5 AgentProfileIR | `src/nl2spl/ir/agent_profile_ir.py` | Profile | 含 PersonaIR, Aspect, Concept |
| T1.4.6 ConstraintIR | `src/nl2spl/ir/constraint_ir.py` | 约束 | 含 ConstraintKind 枚举 |
| T1.4.7 ResourceRegistryIR | `src/nl2spl/ir/resource_registry_ir.py` | 资源注册 | 含 Variable/File/API/Type |
| T1.4.8 SymbolTable | `src/nl2spl/ir/symbol_table.py` | 符号表 | 含 declare/reference 方法 |
| T1.4.9 StepIR | `src/nl2spl/ir/step_ir.py` | Step | 含 CommandType/StepKind |
| T1.4.10 WorkerIR | `src/nl2spl/ir/worker_ir.py` | Worker | 含 FlowRef/AlternativeFlowRef |
| T1.4.11 创建 __init__.py | `src/nl2spl/ir/__init__.py` | 导出 | 正确导出所有 IR |

**关键接口 - SymbolTable**:
```python
class SymbolTable:
    def declare(self, name, data_type, source, description, flow_ref, block_ref) -> None
    def reference(self, name) -> str  # 返回 <REF>name</REF>
    def value_reference(self, name) -> str  # 返回 <REF>*name</REF>
    def get_variable_list_for_prompt(self) -> str
    def add_producer(self, name, step_id) -> None
    def add_consumer(self, name, step_id) -> None
    def validate_references(self, known_step_ids) -> list[str]
```

### Day 5: LLM 客户端 + Stage 基类

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T1.5.1 LLM 客户端 | `src/nl2spl/llm/client.py` | LLMClient | 支持 call_json/call_text |
| T1.5.2 Stage 基类 | `src/nl2spl/pipeline/stages/base.py` | PipelineStage | 含 checkpoint 保存 |
| T1.5.3 Pipeline Orchestrator | `src/nl2spl/pipeline/orchestrator.py` | PipelineOrchestrator | 含所有 Stage 调用占位 |

**LLMClient 接口**:
```python
class LLMClient:
    def __init__(self, config: LLMConfig) -> None
    def call_json(self, stage_name, system_prompt, user_prompt, model, max_tokens, temperature) -> dict
    def call_text(self, stage_name, system_prompt, user_prompt, model, max_tokens) -> str
```

**PipelineStage 接口**:
```python
class PipelineStage(abc.ABC, Generic[Input, Output]):
    def __init__(self, config: PipelineConfig, client: LLMClient) -> None
    @property
    @abc.abstractmethod
    def name(self) -> str: ...
    @abc.abstractmethod
    def execute(self, input_data: Input) -> Output: ...
    def save_checkpoint(self, data: Any) -> None
```

---

## Week 2-5: 代码审查 + 集成

### 每日任务

| 时间 | 任务 | 说明 |
|------|------|------|
| 10:00-10:15 | Standup | 同步进度 |
| 10:15-12:00 | 代码审查 | 审查 PR |
| 14:00-16:00 | 集成调试 | 集成各 Stage |
| 16:00-17:00 | 问题解答 | 回答团队问题 |

### Sprint 2 (Week 2)

| 任务 | 说明 | 验收标准 |
|------|------|----------|
| T2.6.1 审查 Stage 4 代码 | FlowAssembler | 接口一致、错误处理完整 |
| T2.6.2 审查 Stage 5 代码 | BlockAssembler | 接口一致、错误处理完整 |
| T2.6.3 集成测试审查 | test_pipeline.py | 覆盖 Stage 1-5 |

### Sprint 3 (Week 3)

| 任务 | 说明 | 验收标准 |
|------|------|----------|
| T3.7.1 审查 Stage 6 代码 | ResourceExtractor | SymbolTable 构建正确 |
| T3.7.2 审查 Stage 7 代码 | StepExtractor | 变量识别逻辑正确 |
| T3.7.3 集成测试更新 | test_pipeline.py | 覆盖 Stage 1-7 |

### Sprint 4 (Week 4)

| 任务 | 说明 | 验收标准 |
|------|------|----------|
| T4.10.1 审查 Stage 8-11 代码 | Profile/Constraint/Normalizer/Worker/SPL | 接口一致 |
| T4.10.2 集成测试更新 | test_pipeline.py | 覆盖所有 Stage |
| T4.10.3 SPL 输出验证 | - | 输出符合 SPL 语法 |

### Sprint 5 (Week 5)

| 任务 | 说明 | 验收标准 |
|------|------|----------|
| T5.5.1 文档完善 | README.md | 包含安装/使用/API |
| T5.7.1 最终代码审查 | 所有代码 | 通过 mypy/ruff |
| T5.8.1 发布准备 | pyproject.toml | 版本号、依赖正确 |

---

## 交付物清单

| 交付物 | 文件 | 完成时间 |
|--------|------|----------|
| 项目配置 | `pyproject.toml`, `.env.example` | Day 1 |
| 配置管理 | `src/nl2spl/config.py` | Day 1 |
| 入口点 | `src/nl2spl/main.py` | Day 1 |
| 错误处理 | `src/nl2spl/errors/*.py` | Day 2 |
| 工具模块 | `src/nl2spl/utils/*.py` | Day 3 |
| IR 数据模型 | `src/nl2spl/ir/*.py` (11个文件) | Day 4 |
| LLM 客户端 | `src/nl2spl/llm/client.py` | Day 5 |
| Stage 基类 | `src/nl2spl/pipeline/stages/base.py` | Day 5 |
| Orchestrator | `src/nl2spl/pipeline/orchestrator.py` | Day 5 |
| 代码审查记录 | PR comments | 持续 |
| 集成测试 | `tests/integration/test_pipeline.py` | Week 2-5 |
| 文档 | `README.md`, `docs/` | Week 5 |

---

## 验收标准

### 代码质量
- [ ] 通过 mypy 类型检查
- [ ] 通过 ruff 代码风格检查
- [ ] 所有公共 API 有 docstring
- [ ] 无 TODO/FIXME 注释

### 接口一致性
- [ ] 所有 IR 使用 dataclass
- [ ] 所有 Stage 继承 PipelineStage
- [ ] 所有异常继承 NL2SPLError
- [ ] SymbolTable 接口完整

### 集成测试
- [ ] Stage 1-5 集成测试通过
- [ ] Stage 1-7 集成测试通过
- [ ] 端到端测试通过
- [ ] SPL 输出符合语法
