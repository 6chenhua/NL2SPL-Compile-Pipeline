# Developer D (Resource Engineer) - 详细开发计划

## 角色定位

**代号**: D  
**角色**: Resource Engineer  
**职责**: Stage 6-7 实现（ResourceExtractor, StepExtractor）

---

## Week 3: Stage 6-7 实现

### Day 1-2: 理解架构 + Stage 6

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T3.1.1 理解 IR 模型 | `src/nl2spl/ir/resource_registry_ir.py` | 理解 ResourceRegistryIR | 能正确使用 |
| T3.1.2 理解 SymbolTable | `src/nl2spl/ir/symbol_table.py` | 理解 SymbolTable | 能正确使用 |
| T3.1.3 实现 Stage 6 | `src/nl2spl/pipeline/stages/stage6_resource_extractor.py` | ResourceExtractor | 资源提取正确 |

**Stage 6 实现要点**:
```python
class ResourceExtractor(PipelineStage[
    tuple[list[SpanIR], FieldRouteIR],
    tuple[ResourceRegistryIR, SymbolTable]
]):
    @property
    def name(self) -> str:
        return "stage6_resource_extractor"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR]
    ) -> tuple[ResourceRegistryIR, SymbolTable]:
        spans, routes = input_data

        # 1. 筛选 behavior 和 integrations spans
        behavior_spans = [s for s in spans if s.span_id in routes.behavior]
        integrations_spans = [s for s in spans if s.span_id in routes.integrations]

        # 2. 构建 prompt
        behavior_json = json.dumps([asdict(s) for s in behavior_spans], ensure_ascii=False)
        integrations_json = json.dumps([asdict(s) for s in integrations_spans], ensure_ascii=False)

        system_prompt = STAGE6_SYSTEM
        user_prompt = f"""请从以下文本中提取资源：

behavior spans：
---
{behavior_json}
---

integrations spans：
---
{integrations_json}
---

输出 JSON："""

        # 3. 调用 LLM
        result = self.client.call_json(
            stage_name=self.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 4. 解析 variables
        variables = []
        for var_data in result.get("variables", []):
            var = VariableSpec(
                name=var_data["name"],
                data_type=var_data["data_type"],
                required=var_data.get("required", False),
                description=var_data.get("description", ""),
                source=var_data.get("source", "step"),
            )
            variables.append(var)

        # 5. 解析 files
        files = []
        for file_data in result.get("files", []):
            file_spec = FileSpec(
                name=file_data["name"],
                path=file_data.get("path", "<runtime>"),
                data_type=file_data.get("data_type", "text"),
                description=file_data.get("description", ""),
            )
            files.append(file_spec)

        # 6. 解析 apis
        apis = []
        for api_data in result.get("apis", []):
            functions = []
            for func_data in api_data.get("functions", []):
                func = APIFunction(
                    name=func_data["name"],
                    description=func_data.get("description", ""),
                    parameters=func_data.get("parameters", []),
                    return_type=func_data.get("return_type", "text"),
                )
                functions.append(func)

            api = APISpec(
                api_name=api_data["api_name"],
                auth=api_data.get("auth", "none"),
                description=api_data.get("description", ""),
                functions=functions,
            )
            apis.append(api)

        # 7. 解析 types
        types = []
        for type_data in result.get("types", []):
            type_spec = TypeSpec(
                type_name=type_data["type_name"],
                type_kind=type_data.get("type_kind", "structured"),
                definition=type_data.get("definition", ""),
            )
            types.append(type_spec)

        # 8. 构建 ResourceRegistryIR
        resources = ResourceRegistryIR(
            variables=variables,
            files=files,
            apis=apis,
            types=types,
        )

        # 9. 构建 SymbolTable
        symbol_table = SymbolTable()
        for var in variables:
            symbol_table.declare(
                name=var.name,
                data_type=var.data_type,
                source=var.source,
                description=var.description,
            )

        # 10. 保存 checkpoint
        self.save_checkpoint({
            "resources": asdict(resources),
            "symbol_table": {name: asdict(var) for name, var in symbol_table.variables.items()},
        })

        return resources, symbol_table
```

**变量识别规则**:
```
输入变量: "user provides"、"input"、"given"、"request" → source: "input"
输出变量: "produce"、"generate"、"output"、"result" → source: "output"
中间变量: "then use"、"pass to"、"feed into" → source: "step"
API 变量: "call"、"retrieve"、"fetch" → source: "api"
```

**测试用例**:
```python
# tests/unit/test_resource_extractor.py
def test_input_variables():
    """测试输入变量识别"""
    spans = [SpanIR("s1", "A user request is provided")]
    routes = FieldRouteIR(behavior=["s1"])
    resources, symbols = extractor.execute((spans, routes))
    assert any(v.source == "input" for v in resources.variables)

def test_output_variables():
    """测试输出变量识别"""
    spans = [SpanIR("s1", "Produce a draft communication")]
    routes = FieldRouteIR(behavior=["s1"])
    resources, symbols = extractor.execute((spans, routes))
    assert any(v.source == "output" for v in resources.variables)

def test_api_extraction():
    """测试 API 提取"""
    spans = [SpanIR("s1", "Call source retrieval API")]
    routes = FieldRouteIR(integrations=["s1"])
    resources, symbols = extractor.execute((spans, routes))
    assert len(resources.apis) > 0

def test_symbol_table_construction():
    """测试 SymbolTable 构建"""
    spans = [SpanIR("s1", "A user request is provided")]
    routes = FieldRouteIR(behavior=["s1"])
    resources, symbols = extractor.execute((spans, routes))
    assert len(symbols.variables) > 0
```

### Day 2-3: Stage 7 实现

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T3.2.1 实现 Stage 7 | `src/nl2spl/pipeline/stages/stage7_step_extractor.py` | StepExtractor | Step 提取正确 |
| T3.2.2 创建 Prompt | `prompts/stage7_system.txt` | System Prompt | 包含变量列表 |

**Stage 7 实现要点**:
```python
class StepExtractor(PipelineStage[
    tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable],
    tuple[list[StepIR], SymbolTable]
]):
    @property
    def name(self) -> str:
        return "stage7_step_extractor"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable]
    ) -> tuple[list[StepIR], SymbolTable]:
        spans, routes, flow_structure, block_structure, symbol_table = input_data

        # 1. 构建 prompt（包含变量列表）
        behavior_spans = [s for s in spans if s.span_id in routes.behavior]
        behavior_json = json.dumps([asdict(s) for s in behavior_spans], ensure_ascii=False)
        flow_json = json.dumps(asdict(flow_structure), ensure_ascii=False)
        blocks_json = json.dumps(asdict(block_structure), ensure_ascii=False)
        variable_list = symbol_table.get_variable_list_for_prompt()

        system_prompt = STAGE7_SYSTEM.format(variable_list=variable_list)
        user_prompt = f"""请从以下文本中提取 step：

behavior spans：
---
{behavior_json}
---

Flow 结构：
---
{flow_json}
---

Block 结构：
---
{blocks_json}
---

已知变量：
---
{variable_list}
---

输出 JSON："""

        # 2. 调用 LLM
        result = self.client.call_json(
            stage_name=self.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 3. 解析 steps
        steps = []
        for step_data in result.get("steps", []):
            step = StepIR(
                step_id=step_data["step_id"],
                text=step_data["text"],
                source_span_ids=step_data["source_span_ids"],
                command_type=step_data["command_type"],
                inputs=step_data.get("inputs", []),
                outputs=step_data.get("outputs", []),
                integration_ref=step_data.get("integration_ref"),
                flow_ref=step_data.get("flow_ref", "main"),
                block_ref=step_data.get("block_ref", ""),
                kind=step_data.get("kind", "normal"),
            )
            steps.append(step)

            # 4. 更新 SymbolTable（producer/consumer）
            for var_name in step.inputs:
                symbol_table.add_consumer(var_name, step.step_id)
            for var_name in step.outputs:
                symbol_table.add_producer(var_name, step.step_id)

        # 5. 处理 new_variables
        for new_var_data in result.get("new_variables", []):
            new_var_name = new_var_data["name"]
            if new_var_name not in symbol_table.variables:
                symbol_table.declare(
                    name=new_var_name,
                    data_type=new_var_data.get("data_type", "text"),
                    source="step",
                    description=new_var_data.get("description", ""),
                )
                symbol_table.add_producer(new_var_name, new_var_data.get("producer_step", ""))

        # 6. 保存 checkpoint
        self.save_checkpoint({
            "steps": [asdict(s) for s in steps],
            "new_variables": result.get("new_variables", []),
        })

        return steps, symbol_table
```

**变量识别逻辑**:
```
从 SymbolTable 的变量列表中，识别每个 step 的 inputs 和 outputs：
- inputs: 该 step 消费的变量
- outputs: 该 step 产生的变量
- 语义匹配: 变量名和 step 描述可能不完全一致
```

**测试用例**:
```python
# tests/unit/test_step_extractor.py
def test_basic_step_extraction():
    """测试基本 step 提取"""
    spans = [SpanIR("s1", "Determine communication type")]
    routes = FieldRouteIR(behavior=["s1"])
    flow = FlowStructureIR(main_flow_spans=["s1"])
    blocks = BlockStructureIR(main_flow_blocks=[
        BlockIR("b1", "SEQUENTIAL", None, ["s1"])
    ])
    symbols = SymbolTable()
    symbols.declare("user_request", "text", "input", "User request")

    steps, updated_symbols = extractor.execute((spans, routes, flow, blocks, symbols))
    assert len(steps) == 1
    assert steps[0].step_id == "st1"

def test_variable_inputs_outputs():
    """测试变量输入输出识别"""
    spans = [SpanIR("s1", "Determine type from request")]
    routes = FieldRouteIR(behavior=["s1"])
    flow = FlowStructureIR(main_flow_spans=["s1"])
    blocks = BlockStructureIR(main_flow_blocks=[
        BlockIR("b1", "SEQUENTIAL", None, ["s1"])
    ])
    symbols = SymbolTable()
    symbols.declare("user_request", "text", "input", "User request")

    steps, updated_symbols = extractor.execute((spans, routes, flow, blocks, symbols))
    assert "user_request" in steps[0].inputs

def test_new_variable_creation():
    """测试新变量创建"""
    spans = [SpanIR("s1", "Produce communication type")]
    routes = FieldRouteIR(behavior=["s1"])
    flow = FlowStructureIR(main_flow_spans=["s1"])
    blocks = BlockStructureIR(main_flow_blocks=[
        BlockIR("b1", "SEQUENTIAL", None, ["s1"])
    ])
    symbols = SymbolTable()

    steps, updated_symbols = extractor.execute((spans, routes, flow, blocks, symbols))
    assert "communication_type" in updated_symbols.variables
```

### Day 3-4: Prompt + 测试

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T3.3.1 创建 Prompt | `prompts/stage{6,7}_system.txt` | Prompt 文件 | 包含变量列表模板 |
| T3.4.1 单元测试 | `tests/unit/test_resource_extractor.py` | 测试文件 | 覆盖正常/边界/错误 |
| T3.4.2 单元测试 | `tests/unit/test_step_extractor.py` | 测试文件 | 覆盖正常/边界/错误 |

### Day 4-5: 集成测试

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T3.6.1 集成测试更新 | `tests/integration/test_pipeline.py` | 测试更新 | Stage 1-7 集成 |

---

## 文件编辑权限

### 可编辑文件
```
src/nl2spl/pipeline/stages/stage6_resource_extractor.py
src/nl2spl/pipeline/stages/stage7_step_extractor.py
prompts/stage6_system.txt
prompts/stage7_system.txt
tests/unit/test_resource_extractor.py
tests/unit/test_step_extractor.py
```

### 不可编辑文件
```
src/nl2spl/ir/*.py
src/nl2spl/llm/client.py
src/nl2spl/pipeline/stages/base.py
src/nl2spl/pipeline/stages/stage{1,2,3,4,5}_*.py
src/nl2spl/pipeline/stages/stage{8,9,10,11}_*.py
```

---

## 交付物清单

| 交付物 | 文件 | 完成时间 |
|--------|------|----------|
| Stage 6 实现 | `stage6_resource_extractor.py` | Day 2 |
| Stage 7 实现 | `stage7_step_extractor.py` | Day 3 |
| Prompt 文件 | `prompts/stage{6,7}_system.txt` | Day 3 |
| 单元测试 | `tests/unit/test_{resource,step}_extractor.py` | Day 4 |
| 集成测试更新 | `tests/integration/test_pipeline.py` | Day 5 |

---

## 验收标准

### 功能验收
- [ ] 输入变量正确识别（source: "input"）
- [ ] 输出变量正确识别（source: "output"）
- [ ] 中间变量正确识别（source: "step"）
- [ ] API 正确提取
- [ ] 文件正确提取
- [ ] SymbolTable 正确构建
- [ ] Step 正确提取（原子性、完整性）
- [ ] Step 的 inputs/outputs 正确识别
- [ ] new_variables 正确更新到 SymbolTable

### 代码质量
- [ ] 通过 mypy 类型检查
- [ ] 通过 ruff 代码风格检查
- [ ] SymbolTable 使用正确（declare/reference/add_producer/add_consumer）
- [ ] 使用 logger 记录关键信息

### 测试覆盖
- [ ] 单元测试覆盖率 > 80%
- [ ] 覆盖变量识别（input/output/step/api）
- [ ] 覆盖 API/文件提取
- [ ] 覆盖 Step 提取和变量关联
