# Developer E (Compiler Engineer) - 详细开发计划

## 角色定位

**代号**: E  
**角色**: Compiler Engineer  
**职责**: Stage 8-11 实现（ProfileExtractor, ConstraintExtractor, IRNormalizer, WorkerAssembler, SPLRenderer）

---

## Week 4: Stage 8-11 实现

### Day 1: Stage 8 实现

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T4.1.1 实现 Stage 8 | `src/nl2spl/pipeline/stages/stage8_profile_extractor.py` | ProfileExtractor | Profile 提取正确 |
| T4.1.2 创建 Prompt | `prompts/stage8_system.txt` | System Prompt | 包含提取规则 |

**Stage 8 实现要点**:
```python
class ProfileExtractor(PipelineStage[
    tuple[list[SpanIR], FieldRouteIR, SymbolTable],
    AgentProfileIR
]):
    @property
    def name(self) -> str:
        return "stage8_profile_extractor"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR, SymbolTable]
    ) -> AgentProfileIR:
        spans, routes, symbol_table = input_data

        # 1. 筛选 identity/audience/domain spans
        identity_spans = [s for s in spans if s.span_id in routes.identity]
        audience_spans = [s for s in spans if s.span_id in routes.audience]
        domain_spans = [s for s in spans if s.span_id in routes.domain]

        # 2. 构建 prompt
        identity_json = json.dumps([asdict(s) for s in identity_spans], ensure_ascii=False)
        audience_json = json.dumps([asdict(s) for s in audience_spans], ensure_ascii=False)
        domain_json = json.dumps([asdict(s) for s in domain_spans], ensure_ascii=False)
        variable_list = symbol_table.get_variable_list_for_prompt()

        system_prompt = STAGE8_SYSTEM
        user_prompt = f"""请从以下文本中提取 persona、audience、concepts：

identity spans：
---
{identity_json}
---

audience spans：
---
{audience_json}
---

domain spans：
---
{domain_json}
---

已知变量：
---
{variable_list}
---

输出 JSON："""

        # 3. 调用 LLM
        result = self.client.call_json(
            stage_name=self.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 4. 解析 persona
        persona_data = result.get("persona", {})
        persona = PersonaIR(
            role=persona_data.get("role", "General Assistant"),
            aspects=[Aspect(**a) for a in persona_data.get("aspects", [])],
        )

        # 5. 解析 audience
        audience_aspects = [Aspect(**a) for a in result.get("audience", {}).get("aspects", [])]

        # 6. 解析 concepts
        concepts = [Concept(**c) for c in result.get("concepts", [])]

        # 7. 构建 AgentProfileIR
        profile = AgentProfileIR(
            persona=persona,
            audience_aspects=audience_aspects,
            concepts=concepts,
        )

        # 8. 保存 checkpoint
        self.save_checkpoint(asdict(profile))

        return profile
```

**测试用例**:
```python
# tests/unit/test_profile_extractor.py
def test_persona_extraction():
    """测试 persona 提取"""
    spans = [SpanIR("s1", "Internal communications specialist")]
    routes = FieldRouteIR(identity=["s1"])
    symbols = SymbolTable()
    profile = extractor.execute((spans, routes, symbols))
    assert profile.persona.role != "General Assistant"

def test_audience_extraction():
    """测试 audience 提取"""
    spans = [SpanIR("s1", "Senior leadership requiring briefings")]
    routes = FieldRouteIR(audience=["s1"])
    symbols = SymbolTable()
    profile = extractor.execute((spans, routes, symbols))
    assert len(profile.audience_aspects) > 0

def test_concepts_extraction():
    """测试 concepts 提取"""
    spans = [SpanIR("s1", "Provenance: The origin of sourced facts")]
    routes = FieldRouteIR(domain=["s1"])
    symbols = SymbolTable()
    profile = extractor.execute((spans, routes, symbols))
    assert len(profile.concepts) > 0

def test_empty_spans():
    """测试空 span"""
    spans = []
    routes = FieldRouteIR()
    symbols = SymbolTable()
    profile = extractor.execute((spans, routes, symbols))
    assert profile.persona.role == "General Assistant"
```

### Day 2: Stage 9 实现

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T4.2.1 实现 Stage 9 | `src/nl2spl/pipeline/stages/stage9_constraint_extractor.py` | ConstraintExtractor | Constraint 提取正确 |
| T4.2.2 创建 Prompt | `prompts/stage9_system.txt` | System Prompt | 包含约束类型 |

**Stage 9 实现要点**:
```python
class ConstraintExtractor(PipelineStage[
    tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable, list[StepIR]],
    list[ConstraintIR]
]):
    @property
    def name(self) -> str:
        return "stage9_constraint_extractor"

    def execute(
        self, input_data: tuple[list[SpanIR], FieldRouteIR, FlowStructureIR, BlockStructureIR, SymbolTable, list[StepIR]]
    ) -> list[ConstraintIR]:
        spans, routes, flow, blocks, symbol_table, steps = input_data

        # 1. 筛选 rules spans
        rules_spans = [s for s in spans if s.span_id in routes.rules]

        # 2. 构建 prompt
        rules_json = json.dumps([asdict(s) for s in rules_spans], ensure_ascii=False)
        variable_list = symbol_table.get_variable_list_for_prompt()
        step_list = "\n".join([f"- {s.step_id}: {s.text}" for s in steps])

        system_prompt = STAGE9_SYSTEM
        user_prompt = f"""请从以下文本中提取约束：

rules spans：
---
{rules_json}
---

已知变量：
---
{variable_list}
---

已知 steps：
---
{step_list}
---

输出 JSON："""

        # 3. 调用 LLM
        result = self.client.call_json(
            stage_name=self.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        # 4. 解析 constraints
        constraints = []
        for const_data in result.get("constraints", []):
            constraint = ConstraintIR(
                constraint_id=const_data["constraint_id"],
                text=const_data["text"],
                kind=const_data["kind"],
                targets=const_data.get("targets", []),
                source_span_ids=const_data.get("source_span_ids", []),
            )
            constraints.append(constraint)

        # 5. 保存 checkpoint
        self.save_checkpoint({"constraints": [asdict(c) for c in constraints]})

        return constraints
```

**约束类型**:
```
requirement: 必须满足的要求
prohibition: 禁止的行为
gate: 门控条件
evidence: 证据要求
approval: 审批要求
safety: 安全约束
audit: 审计要求
delegation_boundary: 委托边界
promotion_requirement: 晋升门槛
```

**测试用例**:
```python
# tests/unit/test_constraint_extractor.py
def test_prohibition_constraint():
    """测试禁止约束"""
    spans = [SpanIR("s1", "Do not invent facts")]
    routes = FieldRouteIR(rules=["s1"])
    constraints = extractor.execute((spans, routes, FlowStructureIR(), BlockStructureIR(), SymbolTable(), []))
    assert len(constraints) == 1
    assert constraints[0].kind == "prohibition"

def test_requirement_constraint():
    """测试要求约束"""
    spans = [SpanIR("s1", "Require evidence for claims")]
    routes = FieldRouteIR(rules=["s1"])
    constraints = extractor.execute((spans, routes, FlowStructureIR(), BlockStructureIR(), SymbolTable(), []))
    assert len(constraints) == 1
    assert constraints[0].kind == "evidence"

def test_variable_target():
    """测试变量目标"""
    spans = [SpanIR("s1", "Draft must include citations")]
    routes = FieldRouteIR(rules=["s1"])
    symbols = SymbolTable()
    symbols.declare("draft", "text", "output", "Draft")
    constraints = extractor.execute((spans, routes, FlowStructureIR(), BlockStructureIR(), symbols, []))
    assert any("variable:" in t for c in constraints for t in c.targets)
```

### Day 3: Stage 9.5 实现

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T4.3.1 实现 Stage 9.5 | `src/nl2spl/pipeline/stages/stage9_5_normalizer.py` | IRNormalizer | 归一化正确 |

**Stage 9.5 实现要点**:
```python
class IRNormalizer:
    """IR Normalization and validation."""

    def normalize(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
        steps: list[StepIR],
        constraints: list[ConstraintIR],
    ) -> tuple[FlowStructureIR, BlockStructureIR, list[StepIR], list[ConstraintIR], SymbolTable, list[str], list[str]]:
        """Normalize all IRs and validate consistency."""
        errors = []
        warnings = []

        # 1. Validate references
        errors.extend(self._validate_references(steps, constraints, symbol_table, resources))

        # 2. Validate coverage
        warnings.extend(self._validate_coverage(flow, steps))

        # 3. Reconcile step flow_ref/block_ref
        steps = self._reconcile_steps(steps, flow, blocks)

        # 4. Update SymbolTable with new_variables
        # (already done in Stage 7)

        # 5. Reconcile constraint targets
        constraints = self._reconcile_constraints(constraints, steps, blocks)

        return flow, blocks, steps, constraints, symbol_table, errors, warnings

    def _validate_references(
        self, steps: list[StepIR], constraints: list[ConstraintIR],
        symbol_table: SymbolTable, resources: ResourceRegistryIR
    ) -> list[str]:
        """Validate all references."""
        errors = []
        step_ids = {s.step_id for s in steps}
        api_names = {a.api_name for a in resources.apis}

        # Validate step variable references
        for step in steps:
            for var_name in step.inputs + step.outputs:
                if var_name not in symbol_table.variables:
                    errors.append(f"Step {step.step_id} references unknown variable: {var_name}")

            if step.integration_ref and step.integration_ref not in api_names:
                errors.append(f"Step {step.step_id} references unknown API: {step.integration_ref}")

        # Validate constraint targets
        for constraint in constraints:
            for target in constraint.targets:
                if ":" in target:
                    target_type, target_id = target.split(":", 1)
                    if target_type == "step" and target_id not in step_ids:
                        errors.append(f"Constraint {constraint.constraint_id} references unknown step: {target_id}")

        return errors

    def _validate_coverage(self, flow: FlowStructureIR, steps: list[StepIR]) -> list[str]:
        """Validate all spans are covered by steps."""
        warnings = []
        flow_spans = flow.get_all_flow_spans()
        covered_spans = set()
        for step in steps:
            covered_spans.update(step.source_span_ids)

        uncovered = flow_spans - covered_spans
        if uncovered:
            warnings.append(f"Spans not covered by any step: {uncovered}")

        return warnings

    def _reconcile_steps(
        self, steps: list[StepIR], flow: FlowStructureIR, blocks: BlockStructureIR
    ) -> list[StepIR]:
        """Reconcile step flow_ref and block_ref."""
        for step in steps:
            if not step.flow_ref:
                step.flow_ref = flow.get_flow_for_span(step.source_span_ids[0]) if step.source_span_ids else "main"
            if not step.block_ref:
                block = blocks.get_block_for_span(step.source_span_ids[0]) if step.source_span_ids else None
                step.block_ref = block.block_id if block else ""
        return steps

    def _reconcile_constraints(
        self, constraints: list[ConstraintIR], steps: list[StepIR], blocks: BlockStructureIR
    ) -> list[ConstraintIR]:
        """Reconcile constraint targets."""
        for constraint in constraints:
            if not constraint.targets:
                constraint.targets = ["global"]
        return constraints
```

**测试用例**:
```python
# tests/unit/test_normalizer.py
def test_reference_validation():
    """测试引用校验"""
    steps = [StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND", inputs=["unknown_var"])]
    constraints = []
    symbols = SymbolTable()
    resources = ResourceRegistryIR()

    normalizer = IRNormalizer()
    _, _, _, _, _, errors, _ = normalizer.normalize(
        FlowStructureIR(), BlockStructureIR(), resources, symbols, steps, constraints
    )
    assert any("unknown_var" in e for e in errors)

def test_coverage_validation():
    """测试覆盖校验"""
    flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
    steps = [StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND")]

    normalizer = IRNormalizer()
    _, _, _, _, _, _, warnings = normalizer.normalize(
        flow, BlockStructureIR(), ResourceRegistryIR(), SymbolTable(), steps, []
    )
    assert any("s2" in w for w in warnings)
```

### Day 4: Stage 10 实现

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T4.4.1 实现 Stage 10 | `src/nl2spl/pipeline/stages/stage10_worker_assembler.py` | WorkerAssembler | Worker 组装正确 |

**Stage 10 实现要点**:
```python
class WorkerAssembler:
    """Worker assembly (code logic)."""

    def assemble(
        self,
        flow: FlowStructureIR,
        blocks: BlockStructureIR,
        steps: list[StepIR],
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
    ) -> WorkerIR:
        """Assemble WorkerIR from IRs."""
        # 1. Build inputs
        inputs = []
        for var in resources.variables:
            if var.source == "input":
                inputs.append(WorkerInput(name=var.name, required=var.required))

        # 2. Build outputs
        outputs = []
        for var in resources.variables:
            if var.source == "output":
                outputs.append(WorkerOutput(name=var.name, required=var.required))

        # 3. Build main flow
        main_flow = FlowRef(blocks=blocks.main_flow_blocks)

        # 4. Build alternative flows
        alternative_flows = []
        for alt_flow in flow.alternative_flows:
            alt_blocks = blocks.alternative_flow_blocks.get(alt_flow.flow_id, [])
            alternative_flows.append(AlternativeFlowRef(
                flow_id=alt_flow.flow_id,
                condition_text=alt_flow.condition_text,
                blocks=alt_blocks,
            ))

        # 5. Build exception flows
        exception_flows = []
        for exc_flow in flow.exception_flows:
            exc_blocks = blocks.exception_flow_blocks.get(exc_flow.flow_id, [])
            exception_flows.append(ExceptionFlowRef(
                flow_id=exc_flow.flow_id,
                condition_text=exc_flow.condition_text,
                blocks=exc_blocks,
            ))

        # 6. Build API refs
        api_refs = [a.api_name for a in resources.apis]

        # 7. Build child worker refs (from delegation_candidates)
        child_worker_refs = []
        for candidate in flow.delegation_candidates:
            if candidate.suggested_type == "child_worker":
                child_worker_refs.append(f"child_{candidate.candidate_id}")

        # 8. Build WorkerIR
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Main worker",
            inputs=inputs,
            outputs=outputs,
            main_flow=main_flow,
            alternative_flows=alternative_flows,
            exception_flows=exception_flows,
            api_refs=api_refs,
            child_worker_refs=child_worker_refs,
        )

        return worker
```

**测试用例**:
```python
# tests/unit/test_worker_assembler.py
def test_basic_assembly():
    """测试基本组装"""
    flow = FlowStructureIR(main_flow_spans=["s1"])
    blocks = BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])])
    steps = [StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND")]
    resources = ResourceRegistryIR(variables=[
        VariableSpec("user_request", "text", True, "User request", "input"),
        VariableSpec("draft", "text", True, "Draft", "output"),
    ])
    symbols = SymbolTable()

    assembler = WorkerAssembler()
    worker = assembler.assemble(flow, blocks, steps, resources, symbols)

    assert len(worker.inputs) == 1
    assert len(worker.outputs) == 1
    assert worker.inputs[0].name == "user_request"
    assert worker.outputs[0].name == "draft"
```

### Day 5: Stage 11 实现

| 任务 | 文件 | 输出 | 验收标准 |
|------|------|------|----------|
| T4.5.1 实现 Stage 11 | `src/nl2spl/pipeline/stages/stage11_spl_renderer.py` | SPLRenderer | SPL 渲染正确 |
| T4.6.1 实现 SPL 格式化器 | `src/nl2spl/compiler/spl_formatter.py` | SPLFormatter | 格式化正确 |
| T4.7.1 实现静态校验器 | `src/nl2spl/validator/static_validator.py` | StaticValidator | 校验正确 |

**SPL 渲染逻辑**:
```python
class SPLRenderer:
    """SPL rendering (code logic)."""

    def render(
        self,
        worker: WorkerIR,
        profile: AgentProfileIR,
        resources: ResourceRegistryIR,
        symbol_table: SymbolTable,
    ) -> tuple[str, list[str], list[str]]:
        """Render SPL text."""
        errors = []
        warnings = []
        parts = []

        # 1. DEFINE_AGENT header
        parts.append(f'[DEFINE_AGENT: {worker.worker_name} "{worker.description}"]')

        # 2. DEFINE_PERSONA
        parts.append("[DEFINE_PERSONA:]")
        parts.append(f"    ROLE: {worker.persona.role}")
        for aspect in profile.persona.aspects:
            parts.append(f"    {aspect.name}: {aspect.text}")
        parts.append("[END_PERSONA]")

        # 3. DEFINE_AUDIENCE
        if profile.audience_aspects:
            parts.append("[DEFINE_AUDIENCE:]")
            for aspect in profile.audience_aspects:
                parts.append(f"    {aspect.name}: {aspect.text}")
            parts.append("[END_AUDIENCE]")

        # 4. DEFINE_CONCEPTS
        if profile.concepts:
            parts.append("[DEFINE_CONCEPTS:]")
            for concept in profile.concepts:
                parts.append(f"    {concept.term}: {concept.definition}")
            parts.append("[END_CONCEPTS]")

        # 5. DEFINE_VARIABLES
        parts.append("[DEFINE_VARIABLES:]")
        for var in resources.variables:
            parts.append(f'    "{var.description}" {var.name}: {var.data_type}')
        parts.append("[END_VARIABLES]")

        # 6. DEFINE_CONSTRAINTS
        # (constraints are rendered inline in flows)

        # 7. DEFINE_WORKER
        parts.append(f'[DEFINE_WORKER: "{worker.description}" {worker.worker_name}]')

        # 8. INPUTS
        parts.append("    [INPUTS]")
        for inp in worker.inputs:
            req = "REQUIRED" if inp.required else "OPTIONAL"
            parts.append(f"        {req} <REF>{inp.name}</REF>")
        parts.append("    [END_INPUTS]")

        # 9. OUTPUTS
        parts.append("    [OUTPUTS]")
        for out in worker.outputs:
            req = "REQUIRED" if out.required else "OPTIONAL"
            parts.append(f"        {req} <REF>{out.name}</REF>")
        parts.append("    [END_OUTPUTS]")

        # 10. MAIN_FLOW
        parts.append("    [MAIN_FLOW]")
        parts.extend(self._render_blocks(worker.main_flow.blocks, steps, indent=8))
        parts.append("    [END_MAIN_FLOW]")

        # 11. ALTERNATIVE_FLOWs
        for alt_flow in worker.alternative_flows:
            parts.append(f"    [ALTERNATIVE_FLOW: {alt_flow.condition_text}]")
            parts.extend(self._render_blocks(alt_flow.blocks, steps, indent=8))
            parts.append("    [END_ALTERNATIVE_FLOW]")

        # 12. EXCEPTION_FLOWs
        for exc_flow in worker.exception_flows:
            parts.append(f"    [EXCEPTION_FLOW: {exc_flow.condition_text}]")
            parts.extend(self._render_blocks(exc_flow.blocks, steps, indent=8))
            parts.append("    [END_EXCEPTION_FLOW]")

        # 13. END_WORKER
        parts.append("[END_WORKER]")

        # 14. END_AGENT
        parts.append("[END_AGENT]")

        spl_text = "\n".join(parts)

        return spl_text, errors, warnings
```

---

## 文件编辑权限

### 可编辑文件
```
src/nl2spl/pipeline/stages/stage8_profile_extractor.py
src/nl2spl/pipeline/stages/stage9_constraint_extractor.py
src/nl2spl/pipeline/stages/stage9_5_normalizer.py
src/nl2spl/pipeline/stages/stage10_worker_assembler.py
src/nl2spl/pipeline/stages/stage11_spl_renderer.py
src/nl2spl/compiler/spl_formatter.py
src/nl2spl/validator/static_validator.py
prompts/stage8_system.txt
prompts/stage9_system.txt
tests/unit/test_profile_extractor.py
tests/unit/test_constraint_extractor.py
tests/unit/test_normalizer.py
tests/unit/test_worker_assembler.py
tests/unit/test_spl_renderer.py
```

### 不可编辑文件
```
src/nl2spl/ir/*.py
src/nl2spl/llm/client.py
src/nl2spl/pipeline/stages/base.py
src/nl2spl/pipeline/stages/stage{1,2,3,4,5,6,7}_*.py
```

---

## 交付物清单

| 交付物 | 文件 | 完成时间 |
|--------|------|----------|
| Stage 8 实现 | `stage8_profile_extractor.py` | Day 1 |
| Stage 9 实现 | `stage9_constraint_extractor.py` | Day 2 |
| Stage 9.5 实现 | `stage9_5_normalizer.py` | Day 3 |
| Stage 10 实现 | `stage10_worker_assembler.py` | Day 4 |
| Stage 11 实现 | `stage11_spl_renderer.py` | Day 5 |
| SPL 格式化器 | `compiler/spl_formatter.py` | Day 5 |
| 静态校验器 | `validator/static_validator.py` | Day 5 |
| Prompt 文件 | `prompts/stage{8,9}_system.txt` | Day 2 |
| 单元测试 | `tests/unit/test_*.py` | Day 5 |

---

## 验收标准

### 功能验收
- [ ] Persona 正确提取（role + aspects）
- [ ] Audience 正确提取（aspects）
- [ ] Concepts 正确提取（term + definition）
- [ ] Constraints 正确提取（kind + targets）
- [ ] IR 归一化正确（引用完整性、覆盖完整性）
- [ ] Worker 组装正确（inputs/outputs/flows）
- [ ] SPL 渲染正确（符合语法）

### 代码质量
- [ ] 通过 mypy 类型检查
- [ ] 通过 ruff 代码风格检查
- [ ] SPL 输出符合 4 空格缩进
- [ ] 使用 logger 记录关键信息

### 测试覆盖
- [ ] 单元测试覆盖率 > 80%
- [ ] 覆盖 Profile/Constraint 提取
- [ ] 覆盖 IR 归一化逻辑
- [ ] 覆盖 Worker 组装逻辑
- [ ] 覆盖 SPL 渲染逻辑
