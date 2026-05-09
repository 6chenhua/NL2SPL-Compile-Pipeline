# Developer C (Flow Engineer) - 详细开发计划

## 角色定位

**代号**: C  
**角色**: Flow Engineer  
**职责**: Stage 4-5 实现（FlowAssembler, BlockAssembler）

---

## Week 2: Stage 4-5 实现

### Day 1-2: 理解架构 + Stage 4

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T2.1.1 理解 IR 模型 | `src/nl2spl/ir/flow_structure_ir.py` | 理解 FlowStructureIR | 能正确使用 |
| T2.1.2 理解 Stage 基类 | `src/nl2spl/pipeline/stages/base.py` | 理解 PipelineStage | 能正确继承 |
| T2.1.3 实现 Stage 4 | `src/nl2spl/pipeline/stages/stage4_flow_assembler.py` | FlowAssembler | Flow 判断正确 |

**Stage 4 实现要点**:
```python
class FlowAssembler(PipelineStage[
    tuple[list[SpanIR], FieldRouteIR],
    FlowStructureIR
]):
    @property
    def name(self) -> str:
        return "stage4_flow_assembler"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR]
    ) -> FlowStructureIR:
        spans, routes = input_data

        # 1. 筛选 behavior spans
        behavior_spans = [s for s in spans if s.span_id in routes.behavior]

        # 2. 构建 prompt
        behavior_json = json.dumps([asdict(s) for s in behavior_spans], ensure_ascii=False)
        all_json = json.dumps([asdict(s) for s in spans], ensure_ascii=False)

        system_prompt = STAGE4_SYSTEM
        user_prompt = f"""请分析以下 span 的流程结构：

behavior spans（只有 behavior 字段的 span 需要判断 Flow）：
---
{behavior_json}
---

所有 spans（用于上下文理解）：
---
{all_json}
---

输出 JSON："""

        # 3. 调用 LLM
        result = self.client.call_json(
            stage_name=self.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 4. 解析结果
        main_flow_spans = result.get("main_flow_spans", [])

        alternative_flows = []
        for flow_data in result.get("alternative_flows", []):
            flow = AlternativeFlow(
                flow_id=flow_data["flow_id"],
                condition_text=flow_data["condition_text"],
                spans=flow_data["spans"],
            )
            alternative_flows.append(flow)

        exception_flows = []
        for flow_data in result.get("exception_flows", []):
            flow = ExceptionFlow(
                flow_id=flow_data["flow_id"],
                condition_text=flow_data["condition_text"],
                spans=flow_data["spans"],
            )
            exception_flows.append(flow)

        delegation_candidates = []
        for cand_data in result.get("delegation_candidates", []):
            candidate = DelegationCandidate(
                candidate_id=cand_data["candidate_id"],
                spans=cand_data["spans"],
                reason=cand_data["reason"],
                suggested_type=cand_data["suggested_type"],
                input_variables=cand_data.get("input_variables", []),
                output_variables=cand_data.get("output_variables", []),
            )
            delegation_candidates.append(candidate)

        flow_structure = FlowStructureIR(
            main_flow_spans=main_flow_spans,
            alternative_flows=alternative_flows,
            exception_flows=exception_flows,
            delegation_candidates=delegation_candidates,
        )

        # 5. 保存 checkpoint
        self.save_checkpoint(asdict(flow_structure))

        return flow_structure
```

**关键决策规则**:
```
第一层：判断影响范围
- 影响单个动作 → 留给 Stage 5 (IF_BLOCK)
- 影响整条路径 → 进入第二层

第二层：判断路径类型
- 用户主动触发 → ALTERNATIVE_FLOW
- 负面事件 → EXCEPTION_FLOW
- 正常条件 → 留给 Stage 5 (IF_BLOCK)
```

**测试用例**:
```python
# tests/unit/test_flow_assembler.py
def test_main_flow():
    """测试主流程判断"""
    spans = [
        SpanIR("s1", "Determine type"),
        SpanIR("s2", "Identify fields"),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    result = assembler.execute((spans, routes))
    assert result.main_flow_spans == ["s1", "s2"]
    assert len(result.alternative_flows) == 0
    assert len(result.exception_flows) == 0

def test_exception_flow():
    """测试异常流程判断"""
    spans = [
        SpanIR("s1", "Determine type"),
        SpanIR("s2", "If evidence shortage, return error"),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    result = assembler.execute((spans, routes))
    assert "s1" in result.main_flow_spans
    assert len(result.exception_flows) == 1
    assert result.exception_flows[0].condition_text == "evidence shortage"

def test_alternative_flow():
    """测试替代流程判断"""
    spans = [
        SpanIR("s1", "Determine type"),
        SpanIR("s2", "If user asks for revision, revise"),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    result = assembler.execute((spans, routes))
    assert "s1" in result.main_flow_spans
    assert len(result.alternative_flows) == 1

def test_delegation_candidates():
    """测试 delegation 候选识别"""
    spans = [
        SpanIR("s1", "Determine type"),
        SpanIR("s2", "Gather sources from external APIs"),
        SpanIR("s3", "Normalize evidence"),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2", "s3"])
    result = assembler.execute((spans, routes))
    # delegation_candidates 可能为空，取决于 LLM 判断
```

### Day 2-3: Stage 5 实现

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T2.2.1 实现 Stage 5 | `src/nl2spl/pipeline/stages/stage5_block_assembler.py` | BlockAssembler | Block 判断正确 |
| T2.2.2 创建 Prompt | `prompts/stage5_system.txt` | System Prompt | 包含 Block 规则 |

**Stage 5 实现要点**:
```python
class BlockAssembler(PipelineStage[
    tuple[list[SpanIR], FieldRouteIR, FlowStructureIR],
    BlockStructureIR
]):
    @property
    def name(self) -> str:
        return "stage5_block_assembler"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR, FlowStructureIR]
    ) -> BlockStructureIR:
        spans, routes, flow_structure = input_data

        # 1. 构建 prompt
        behavior_spans = [s for s in spans if s.span_id in routes.behavior]
        behavior_json = json.dumps([asdict(s) for s in behavior_spans], ensure_ascii=False)
        flow_json = json.dumps(asdict(flow_structure), ensure_ascii=False)

        system_prompt = STAGE5_SYSTEM
        user_prompt = f"""请将以下 span 组织成 Block：

Flow 结构：
---
{flow_json}
---

behavior spans：
---
{behavior_json}
---

输出 JSON："""

        # 2. 调用 LLM
        result = self.client.call_json(
            stage_name=self.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 3. 解析结果
        main_flow_blocks = [
            BlockIR(**block) for block in result.get("main_flow_blocks", [])
        ]

        alternative_flow_blocks = {}
        for flow_id, blocks_data in result.get("alternative_flow_blocks", {}).items():
            alternative_flow_blocks[flow_id] = [
                BlockIR(**block) for block in blocks_data
            ]

        exception_flow_blocks = {}
        for flow_id, blocks_data in result.get("exception_flow_blocks", {}).items():
            exception_flow_blocks[flow_id] = [
                BlockIR(**block) for block in blocks_data
            ]

        block_structure = BlockStructureIR(
            main_flow_blocks=main_flow_blocks,
            alternative_flow_blocks=alternative_flow_blocks,
            exception_flow_blocks=exception_flow_blocks,
        )

        # 4. 保存 checkpoint
        self.save_checkpoint(asdict(block_structure))

        return block_structure
```

**Block 类型判断**:
```
SEQUENTIAL: 连续的、无条件的动作
IF: "if"、"when"、"unless"、"in case"
FOR: "for each"、"for every"、"遍历"
WHILE: "while"、"until"、"直到"
```

**测试用例**:
```python
# tests/unit/test_block_assembler.py
def test_sequential_block():
    """测试顺序块"""
    spans = [
        SpanIR("s1", "Determine type"),
        SpanIR("s2", "Identify fields"),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
    result = assembler.execute((spans, routes, flow))
    assert len(result.main_flow_blocks) == 1
    assert result.main_flow_blocks[0].block_type == "SEQUENTIAL"

def test_if_block():
    """测试条件块"""
    spans = [
        SpanIR("s1", "Determine type"),
        SpanIR("s2", "If sources needed, retrieve them"),
    ]
    routes = FieldRouteIR(behavior=["s1", "s2"])
    flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
    result = assembler.execute((spans, routes, flow))
    assert len(result.main_flow_blocks) == 2
    assert result.main_flow_blocks[1].block_type == "IF"

def test_for_block():
    """测试循环块"""
    spans = [
        SpanIR("s1", "For each topic, generate summary"),
    ]
    routes = FieldRouteIR(behavior=["s1"])
    flow = FlowStructureIR(main_flow_spans=["s1"])
    result = assembler.execute((spans, routes, flow))
    assert len(result.main_flow_blocks) == 1
    assert result.main_flow_blocks[0].block_type == "FOR"
```

### Day 3-4: Prompt + 测试

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T2.3.1 创建 Prompt | `prompts/stage{4,5}_system.txt` | Prompt 文件 | 包含决策规则 |
| T2.4.1 单元测试 | `tests/unit/test_flow_assembler.py` | 测试文件 | 覆盖正常/边界/错误 |
| T2.4.2 单元测试 | `tests/unit/test_block_assembler.py` | 测试文件 | 覆盖正常/边界/错误 |

### Day 4-5: 集成测试

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T2.5.1 集成测试更新 | `tests/integration/test_pipeline.py` | 测试更新 | Stage 1-5 集成 |

---

## 文件编辑权限

### 可编辑文件
```
src/nl2spl/pipeline/stages/stage4_flow_assembler.py
src/nl2spl/pipeline/stages/stage5_block_assembler.py
prompts/stage4_system.txt
prompts/stage5_system.txt
tests/unit/test_flow_assembler.py
tests/unit/test_block_assembler.py
```

### 不可编辑文件
```
src/nl2spl/ir/*.py
src/nl2spl/llm/client.py
src/nl2spl/pipeline/stages/base.py
src/nl2spl/pipeline/stages/stage{1,2,3}_*.py
src/nl2spl/pipeline/stages/stage{6,7,8,9,10,11}_*.py
```

---

## 交付物清单

| 交付物 | 文件 | 完成时间 |
|--------|------|----------|
| Stage 4 实现 | `stage4_flow_assembler.py` | Day 2 |
| Stage 5 实现 | `stage5_block_assembler.py` | Day 3 |
| Prompt 文件 | `prompts/stage{4,5}_system.txt` | Day 3 |
| 单元测试 | `tests/unit/test_{flow,block}_assembler.py` | Day 4 |
| 集成测试更新 | `tests/integration/test_pipeline.py` | Day 5 |

---

## 验收标准

### 功能验收
- [ ] MAIN_FLOW 正确识别（默认归属）
- [ ] ALTERNATIVE_FLOW 正确识别（用户触发）
- [ ] EXCEPTION_FLOW 正确识别（负面事件）
- [ ] delegation_candidates 正确识别
- [ ] SEQUENTIAL_BLOCK 正确组装
- [ ] IF_BLOCK 正确组装
- [ ] FOR_BLOCK / WHILE_BLOCK 正确组装
- [ ] Block 不嵌套

### 代码质量
- [ ] 通过 mypy 类型检查
- [ ] 通过 ruff 代码风格检查
- [ ] Flow/Block 边界清晰（使用分层决策树）
- [ ] 使用 logger 记录关键决策

### 测试覆盖
- [ ] 单元测试覆盖率 > 80%
- [ ] 覆盖 MAIN/ALTERNATIVE/EXCEPTION 流程
- [ ] 覆盖 SEQUENTIAL/IF/FOR/WHILE 块
