# Stage 9.5 基于规则的语义清理计划

> 原文：[stage9_5_rule_based_semantic_cleanup_plan.md](stage9_5_rule_based_semantic_cleanup_plan.md)

## 背景

Stage 9.5 目前命名为 `IRNormalizer`，但其混合了三种不同职责：

1. 确定性 IR 标准化与一致性检查。
2. 属于 post-normalize IRS 的构造级诊断。
3. 基于文本关键词的规则驱动语义修补。

第三类是核心问题。纯代码仅在消费稳定结构时才是稳定的，不应从自然语言片段推断用户意图、handler 语义、流程语义或交互语义。这些决策应归于 LLM 阶段和 IRS 满足度检查。静默回退或语义修补也会使 LLM 故障更难调试，因为下游 IR 经过代码改写后可能表面看起来合法。

本文档定义清理计划，本身不修改生产代码。

## 设计原则

### 纯代码允许做的事

纯代码可执行确定性编译器工作：

- 验证一个 IR 引用的 ID 是否存在于另一个 IR 中。
- 从权威结构化来源（如 `WorkerPlanIR` handoffs 和 worker 归属）协调字段。
- 在已有结构化 IR 上构建图/索引视图。
- 标准化 SPL 所需的语法形状，如每条命令仅一个 `RESULT` 变量。
- 从显式 step 输入/输出填充生产者/消费者链接。
- 当 LLM 阶段产出格式错误的 IR 时快速失败。

### 纯代码不允许做的事

纯代码不得：

- 通过关键词判断自然语言条件是真正的异常、普通条件、循环、拒绝还是重试策略。
- 通过关键词判断 `DISPLAY_MESSAGE` 步骤实际上是 `REQUEST_INPUT`。
- 通过关键词判断异常流步骤是"伪 handler"。
- 为使输出可渲染而发明、降级或重写语义命令类型。
- 将 `available_connectors` 等来源特定变量修补到通用数据流中。
- 用语义回退掩盖 LLM 故障。

### IRS 边界

IRS 回答的是：一个物化构造是否具有必需的槽位和来源证据。它可以报告不完整的构造，但不得修改输入 IR、生成缺失构造或用关键词规则解析原始自然语言。

post-normalize IRS 应作为 Stage 10 组装 `WorkerIR` 后构造级诊断的最终权威。

## 当前生产路径

当前编排器路径：

```text
Stage 7 worker-scoped step extraction
  -> Stage 9 constraint extraction
  -> Stage 9.5 IRNormalizer.normalize_worker_scoped()
  -> Stage 10 WorkerAssembler
  -> PostNormalizeIRSChecker.check()
  -> ExecutableElementGate
  -> Renderer
```

`PipelineOrchestrator` 调用 `_run_normalization_worker_scoped()`，该方法创建 `IRNormalizer()` 并调用 `normalize_worker_scoped()`。

旧版扁平 `IRNormalizer.normalize()` 路径不再被当前生产编排器代码调用，但仍被直接单元测试和集成测试引用。

## 问题清单

### 1. 旧版 `normalize()` 路径

**位置：**

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalizer.py`

**问题：**

- `normalize()` 已不在生产编排器路径上。
- 它保留了旧的语义修补行为：
  - 流程分类修补；
  - 来源检索输入重映射；
  - 旧版子委托候选物化；
  - 旧版必需输出发现；
  - 旧版约束协调。
- 测试仍直接调用它，使其看起来仍受支持，但生产已迁移到 worker-scoped IR。

**决策：**

- 移除 `normalize()` 作为受支持的公共入口点。
- 如果测试需要扁平 fixture，将其迁移到 worker-scoped fixture 或移至保留的确定性辅助函数的专项辅助测试。

**理由：**

- 保留两个公共标准化器路径会使语义清理存在歧义。
- 扁平路径保留了不应被复活的基于规则的行为。

### 2. 基于规则的流程分类修补

**位置：**

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/flow_classification.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/helpers.py`

**问题：**

- `_normalize_flow_classification()` 在主流、备选流和异常流结构之间移动流程。
- `_is_exception_condition()` 依赖 `fail`、`missing`、`invalid`、`cannot`、`blocked` 等关键词。
- `_is_loop_condition()` 依赖 `"do not finalize"` 和 `"missing"`。

这是从原始文本进行的语义分类，无法做到完备，且跨领域时很脆弱。

**决策：**

- 随旧版扁平路径一并删除此行为。
- 不移植到 `normalize_worker_scoped()`。
- 流程分类应由 Stage 4 LLM 拥有，必要时由 Stage 4 IRS 诊断负责。

**替代方案：**

- Stage 4 应发出其认为正确的流程分类。
- Stage 9.5 可验证结构一致性：
  - block 引用的 flow ID 是否存在；
  - flow span 是否归该 worker 所有；
  - 除非显式允许，否则同一稳定 span 集不得有重复 block。
- 如果 Stage 4 输出不一致，应报错或诊断，而非静默地在语义流类别之间移动 span。

### 3. `available_connectors` 来源检索输入修补

**位置：**

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`

**问题：**

- `_normalize_source_retrieval_inputs()` 当步骤文本包含 source/retriev/provenance 时，将步骤输入重写为 `available_connectors`。
- `available_connectors` 是来源/应用特定的，不是编译器级不变量。
- 重写可能掩盖 Stage 6/7 的合约失败。

**决策：**

- 随旧版扁平路径一并删除 `_normalize_source_retrieval_inputs()`。
- 在 worker-scoped 标准化中不调用等效方法。

**替代方案：**

- Stage 6 应声明运行时输入和资源变量。
- Stage 7 应使用 `SymbolTable` 选择步骤输入。
- Handoffs 应携带显式输入绑定。
- 如果检索步骤缺少必要输入，应报告缺失输入/合约诊断，而非重写它。

### 4. `DISPLAY_MESSAGE` -> `REQUEST_INPUT` 修补

**位置：**

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`
- 从 `normalize_worker_scoped()` 调用。

**问题：**

- `_normalize_interactive_display_steps()` 检查步骤文本，当文本包含 ask、clarify、prompt、confirm、collect user 或 iterate with user 等标记时，将 `DISPLAY_MESSAGE` 改为 `REQUEST_INPUT`。
- Stage 7 prompt 已告知 LLM 如何区分 `REQUEST_INPUT` 和 `DISPLAY_MESSAGE`。
- 重分类掩盖了 Stage 7 的错误，将语义意图变成了硬编码短语列表。

**决策：**

- 移除 Stage 9.5 中的命令类型变更。
- 仅保留结构验证：
  - `REQUEST_INPUT` 必须有来源 span 或已接受的 handoff/scaffold 证据；
  - `DISPLAY_MESSAGE` 可显示已产出的值；
  - 有输出的 `DISPLAY_MESSAGE` 在结构上可疑，应作为诊断/错误，而非自动重写。

**替代方案：**

1. 首选：在 Stage 9.5 对不可能的命令形状进行快速失败验证。
2. 可选：Stage 7 IRS 对模糊命令类型的诊断，不进行 IR 变更。
3. 后续可选：仅在显式启用且在编译诊断中可见的情况下才运行专用 LLM 修补通道，不得作为隐藏回退运行。

**建议的近期行为：**

```text
如果 command_type == DISPLAY_MESSAGE 且有 outputs：
    发出验证错误：DISPLAY_MESSAGE 不能产出 outputs

如果 command_type == REQUEST_INPUT 且无 source_span_ids 且无已接受的 handoff：
    post-normalize IRS 发出 type_or_contract_ambiguity

不重写 command_type
```

### 5. 必需输出生产者检查

**位置：**

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/final_irs_checker.py`

**问题：**

- `_ensure_required_main_outputs()` 和 `_ensure_required_worker_outputs()` 在 `construct_findings` 中记录 `missing_output_producer`。
- `PostNormalizeIRSChecker._check_missing_output_producers()` 在 Stage 10 组装 worker 作用域后独立检查必需输出。
- 标准化器侧的发现要么是旧版的，要么是重复的。

**决策：**

- 将最终必需输出生产者职责完全移至 `PostNormalizeIRSChecker`。
- Stage 9.5 可构建或刷新生产者/消费者链接，但不应创建最终的缺失输出发现。

**替代方案：**

- 保留 `ProducerIndex` 作为确定性结构机制。
- 在 post-normalize IRS（Stage 10 之后）中使用它，因为那里有完整的 `WorkerIR` 和子 worker 作用域。
- 从 `IRNormalizer` 中移除 `missing_output_producer` 收集。

**理由：**

- 必需输出生产者是 IRS 完整性问题："这个必需输出是否有来源支持的生产证据？"
- Stage 9.5 不需要预计算最终检查器已有权计算的诊断。

### 6. 伪异常 handler 检测

**位置：**

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`
- 发现结果由 `PostNormalizeIRSChecker` 消费。

**问题：**

- `_is_pseudo_handler()` 当 handler 的文本和 span 匹配硬编码短语模式（如 "do not finalize"、"check if"、"confirm with the user"、"display a message"）时，将其分类为伪 handler。
- `_diagnose_exception_flow_handlers()` 从步骤列表中移除这些步骤。
- 这是语义解释和 IR 变更。显示/报告步骤在某些工作流中可能是有效的 handler。

**决策：**

- 停止在 Stage 9.5 中删除步骤作为伪 handler。
- 停止使用文本标记伪 handler 分类。
- 缺失 handler 应先进行结构检查：
  - 异常流是否有至少一个 `flow_ref` 匹配的步骤；
  - 该步骤在 Gate 后是否可渲染；
  - 来源/IRS 是否说 handler 动作槽已满足？

**替代方案：**

- Stage 4/7 LLM 应判断来源文本是否包含 handler 动作。
- Stage 4 IRS 可从阶段本地视图报告异常流缺失 handler 证据。
- post-normalize IRS 应在组装的 IR 没有异常流的 handler 步骤时发出 `missing_handler`。
- 如果未来需要 handler 动作语义，应添加消费结构化字段（而非原始文本关键词）的 IRS 检查器。

**近期行为：**

```text
如果 exception_flow 存在且无 step.flow_ref == exception_flow.flow_id：
    PostNormalizeIRSChecker 发出 missing_handler

如果步骤存在：
    Stage 9.5 不判断其文本是否"足够真实"
```

### 7. Stage 7 命令降级回退

**位置：**

- `src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py`

**问题：**

- 子 worker 步骤中无效的 `INVOKE_WORKER` 或 `CALL_API` 被重写为 `GENERAL_COMMAND`。
- 这在 Stage 9.5 之外，但直接影响 Stage 9.5 的输入质量。
- 它掩盖了 LLM 命令类型错误。

**决策：**

- 用显式验证错误或诊断替代降级。
- 不转换语义命令类型以使 IR 通过后续阶段。

**替代方案：**

```text
如果子 worker 发出 INVOKE_WORKER/CALL_API 但无已接受的传出 handoff：
    使 Stage 7 worker-scoped 提取失败或发出阻塞诊断
    不变更为 GENERAL_COMMAND
```

这应在同一波清理中处理，否则 Stage 9.5 将继续接收已被修补的语义 IR。

## 目标 Stage 9.5 职责

清理后，Stage 9.5 应缩减为编译器一致性检查。

### 保留

1. **Worker-scoped 结构验证：**
   - span 归属；
   - 每个 handoff 是否有对应步骤；
   - handoff 模式匹配 `CALL_API` 或 `INVOKE_WORKER`；
   - handoff 输入/输出绑定匹配步骤形状；
   - 子输出合约在需要时绑定回父级。

2. **Symbol table 刷新：**
   - 从最终 step 输入/输出重新计算生产者和消费者链接；
   - 仅从编译器拥有的索引中移除过时的生产者链接，不从来源合约中移除。

3. **多输出结构聚合：**
   - 一条 SPL 命令只能发出一个结果变量；
   - 将多个输出聚合为结构化结果变量；
   - 记录元数据供下游渲染和诊断使用。

4. **引用验证：**
   - step 变量存在；
   - 声明的 API 引用已知或已绑定 handoff；
   - 约束目标存在。

5. **确定性形状检查：**
   - 不支持的命令/输出组合；
   - handoff 生成的步骤缺少 handoff ID；
   - 格式错误的 worker 归属引用。

### 移除

1. `normalize()` 旧版扁平入口点。
2. 流程语义重分类。
3. 来源检索输入重映射。
4. 命令类型语义重分类。
5. 伪 handler 关键词检测和步骤删除。
6. 标准化器侧必需输出生产者发现。
7. 为使 LLM 输出通过而引入的任何静默语义回退。

## 建议的模块结构

**当前包：**

```text
stage9_5_normalizer/
  normalizer.py
  normalization.py
  validation.py
  worker_scoped.py
  worker_handoffs.py
  flow_classification.py
  helpers.py
  final_irs_checker.py
```

**目标包：**

```text
stage9_5_normalizer/
  normalizer.py              # 精简门面：仅 normalize_worker_scoped
  structural_normalization.py # 多输出聚合、symbol 同步
  structural_validation.py   # 引用、归属、handoffs
  worker_scoped.py           # 结构化 pass 编排
  helpers.py                 # 仅 ID 排序/安全名称
  final_irs_checker.py       # post-normalize IRS 权威
```

**删除或清空：**

- `flow_classification.py`
- `normalization.py` 的旧版部分
- `normalizer.py` 中的扁平旧版入口点

**可选的中间状态：**

- 初始保持文件名稳定，但删除语义方法和调用。
- 仅在行为清理通过测试后才重命名模块，避免将语义和机械重构混在一起。

## 实施计划

### Phase 0：基线审计

**目标：**

- 确认所有仍依赖旧版或语义修补行为的生产入口点和测试。

**命令：**

```powershell
rg -n "\.normalize\(|normalize_worker_scoped\(|_normalize_interactive_display_steps|_normalize_flow_classification|_normalize_source_retrieval_inputs|_diagnose_exception_flow_handlers|_ensure_required.*outputs" src tests docs
```

**预期审计输出：**

- `src/nl2spl/pipeline/orchestrator.py` 仅调用 `normalize_worker_scoped()`。
- 旧版 `normalize()` 引用仅存在于测试/文档中。
- Worker-scoped 路径仍调用：
  - `_normalize_interactive_display_steps()`；
  - `_normalize_multi_output_steps()`；
  - `_ensure_required_worker_outputs()`；
  - `_diagnose_exception_flow_handlers()`。

**验收标准：**

- 创建需要删除、重写或保留的测试清单。

### Phase 1：移除旧版扁平标准化器支持

**操作：**

1. 删除 `IRNormalizer.normalize()`。
2. 删除 `_normalize_flow_classification()` 和 `flow_classification.py`。
3. 删除 `_normalize_source_retrieval_inputs()`。
4. 如果没有生产 worker-scoped 路径使用旧版 `_materialize_child_worker_invocations()`，则删除它。
5. 更新 `IRNormalizer` 继承列表。
6. 删除或重写直接断言旧版扁平标准化的测试。

**需审查的候选测试：**

- `tests/unit/test_normalizer.py`
- `tests/integration/test_partial_spl_mvp.py`
- `tests/integration/test_multi_worker_pipeline.py`
- `tests/integration/test_llm_adapter_engine_e2e.py`
- `tests/integration/test_e2e_failure_handling.py`
- `tests/unit/pipeline/stages/test_worker_plan_normalizer.py` 中的旧版直接调用

**迁移规则：**

- 如果测试验证有效的结构行为，将其重写为使用 `normalize_worker_scoped()`。
- 如果测试验证语义修补，删除它或重写为断言相反行为：不发生重写且产出诊断/错误。

**验收标准：**

- 没有生产或测试代码导入或调用 `IRNormalizer.normalize()`。
- `rg -n "\.normalize\(" tests src` 不存在 `IRNormalizer().normalize(...)` 调用。

### Phase 2：移除命令类型语义修补

**操作：**

1. 从 `normalize_worker_scoped()` 中移除 `_normalize_interactive_display_steps()` 调用。
2. 删除 `_normalize_interactive_display_steps()` 和 `_looks_like_user_input_step()`，除非 Phase 1 中已随删除的旧版模块一起移除。
3. 为不可能的命令形状添加验证：
   - 有输出的 `DISPLAY_MESSAGE` 应为错误或阻塞诊断。
   - 无来源证据的 `REQUEST_INPUT` 应作为 post-normalize IRS 诊断，而非标准化器重写。

**测试变更：**

- 更改期望 `DISPLAY_MESSAGE` 变为 `REQUEST_INPUT` 的测试。
- 新测试应断言：
  - 命令类型保持不变；
  - 无效形状被报告；
  - Stage 7 分类错误可见。

**验收标准：**

- Stage 9.5 从不基于 `step.text` 变更 `step.command_type`。

### Phase 3：将必需输出生产者权威移至 post-normalize IRS

**操作：**

1. 从 `normalize_worker_scoped()` 中移除 `_ensure_required_worker_outputs()` 调用。
2. 如果旧版路径已删除，删除 `_ensure_required_worker_outputs()` 和 `_ensure_required_main_outputs()`。
3. 在 `PostNormalizeIRSChecker` 中保留 `ProducerIndex` 用法。
4. 确保 `PostNormalizeIRSChecker` 覆盖：
   - 主 worker 必需输出；
   - 子 worker 必需输出；
   - handoff 输出绑定；
   - 结构化聚合输出。

**测试变更：**

- 测试应对 `missing_output_producer` 调用 `PostNormalizeIRSChecker.check()`，而非检查 `normalizer.construct_findings`。
- 移除标准化器记录 `missing_output_producer` 的期望。

**验收标准：**

- `normalizer.construct_findings` 不再包含 `missing_output_producer`。
- `PostNormalizeIRSChecker` 是最终 `missing_output_producer` 诊断的唯一生产者。

### Phase 4：移除伪 handler 文本规则

**操作：**

1. 删除 `_is_pseudo_handler()`。
2. 从 `_diagnose_exception_flow_handlers()` 中删除伪 handler 移除逻辑。
3. 用结构化辅助方法替换 `_diagnose_exception_flow_handlers()` 或完全移除。
4. 让 `PostNormalizeIRSChecker` 从组装的 `WorkerIR` 检测缺失 handler：
   - 异常流中无步骤 -> `missing_handler`；
   - 步骤存在 -> 标准化器不判断语义充分性。

**可选的后续工作：**

- 仅当消费 Stage 4/7 创建的结构化证据（而非原始文本关键词）时，才添加 `EXCEPTION_HANDLER_ACTION` 的真正 IRS 检查器。

**测试变更：**

- 删除期望 Stage 9.5 产出 `pseudo_handlers` 发现的测试。
- 添加测试：
  - 异常流无 handler 步骤 -> post-normalize `missing_handler`；
  - 有显示步骤的异常流保留存在，由可渲染性/IRS 稍后判断，不被标准化器删除。

**验收标准：**

- Stage 9.5 从不基于文本内容删除步骤。
- 没有代码引用 `pseudo_exception_handler` 元数据，除非由未来显式的来源支持机制产出。

### Phase 5：移除 Stage 7 语义降级回退

**操作：**

1. 在 `stage7_step_extractor/worker_scoped.py` 中，用快速失败验证替换子 worker `INVOKE_WORKER`/`CALL_API` 降级。
2. 如果当前 API 无法在该点失败，返回阻塞诊断并保持命令不变。
3. 确保无效 LLM 输出在日志和编译诊断中可见。

**测试变更：**

- 替换期望降级为 `GENERAL_COMMAND` 的测试。
- 添加测试验证无效子 worker handoff 命令失败或诊断。

**验收标准：**

- 没有语义命令类型被降级为 `GENERAL_COMMAND` 以保留编译。

### Phase 6：文档和 README 清理

**操作：**

1. 更新 README Stage 9.5 描述：
   - "标准化 IR、结构验证、SPL 形状标准化"。
   - 不广泛宣传"诊断"，除非特指结构错误/警告。
2. 更新 IRS 文档：
   - post-normalize IRS 拥有构造级诊断。
   - Stage 9.5 不解析原始自然语言或分类语义意图。
3. 移除将旧版扁平 `normalize()` 描述为当前行为的文档。

**验收标准：**

- 文档匹配当前生产路径和清理原则。

## 测试策略

### 保留的测试

保留验证确定性结构的测试：

- worker span 归属；
- handoff 形状和绑定；
- API handoff 目标匹配；
- 结构化多输出聚合；
- symbol table 生产者/消费者刷新；
- 引用验证；
- post-normalize IRS 诊断。

### 删除或重写的测试

删除或重写验证语义关键词行为的测试：

- 普通条件从异常流中移出；
- 来源检索输入重写为 `available_connectors`；
- 显示步骤重分类为请求输入；
- 伪 handler 文本检测；
- 标准化器侧缺失输出发现。

### 新增回归测试

添加负面测试：

1. 带有 ask 类文本的 `DISPLAY_MESSAGE` 不被重分类。
2. 有输出的 `DISPLAY_MESSAGE` 报告无效形状。
3. 异常流 handler 步骤不被标准化器移除。
4. 必需输出生产者诊断仅来自 `PostNormalizeIRSChecker`。
5. 无效的子 worker `INVOKE_WORKER` 不被降级为 `GENERAL_COMMAND`。
6. 旧版 `IRNormalizer.normalize()` 导入/调用已消失。

### 建议的测试命令

```powershell
python -m pytest tests/unit/pipeline/stages/test_worker_plan_normalizer.py -q
python -m pytest tests/unit/pipeline/stages/test_final_irs_checker.py -q
python -m pytest tests/unit/test_producer_index.py -q
python -m pytest tests/pipeline/test_worker_aware_integration.py -q
python -m pytest tests/integration/test_e2e_failure_handling.py -q
```

如果 pytest 临时写入与沙箱冲突，在仓库下使用本地 `--basetemp`。

## 迁移风险

### 风险：LLM 输出质量下降，因为代码不再修补它

这是预期行为。目标是暴露 LLM 错误。

**缓解措施：**

- 改进 Stage 4/7 prompt 和 schema 验证器。
- 为无效 IR 添加直接诊断。
- 保留无效 LLM 输出作为回归 fixture。

### 风险：更多部分 SPL 或诊断

如果来源证据不完整或 LLM 输出模糊，这是可接受的。渲染一个虚构的命令更糟。

**缓解措施：**

- 使诊断精确。
- 保留部分 SPL 行为。
- 不将诊断转换为合成命令。

### 风险：测试揭示对旧版扁平路径的隐藏依赖

**缓解措施：**

- 仅迁移有结构价值的测试。
- 锁定过时语义修补的测试予以删除。
- 如果需要可见的公共 API 破坏，保留一个显式测试验证旧版入口点不可用。

### 风险：必需输出诊断时机变化

**缓解措施：**

- 断言最终编译诊断，而非中间标准化器发现。
- 确保 `PostNormalizeIRSChecker` 始终在 Gate 之前运行。

## 实施顺序总结

建议顺序：

1. 从公共路径移除旧版 `normalize()` 和旧语义辅助方法。
2. 移除 worker-scoped `DISPLAY_MESSAGE` 语义重分类。
3. 将必需输出生产者诊断完全移至 post-normalize IRS。
4. 移除伪 handler 关键词检测和步骤删除。
5. 用快速失败行为替换 Stage 7 命令降级回退。
6. 更新测试和文档。

此顺序先移除死代码，再移除活跃语义变更，最后清理诊断权威重复。

## 完成定义

清理完成的标志：

- `IRNormalizer` 仅暴露生产使用的 worker-scoped 标准化。
- Stage 9.5 不基于文本变更命令类型。
- Stage 9.5 不在语义类别之间移动流程。
- Stage 9.5 不重写 `available_connectors` 等来源特定变量。
- Stage 9.5 不基于文本关键词删除 handler 步骤。
- 必需输出生产者最终诊断来自 `PostNormalizeIRSChecker`。
- Stage 7 不将无效命令类型降级为 `GENERAL_COMMAND`。
- 测试验证结构编译器行为和最终诊断，而非隐藏的语义回退。
