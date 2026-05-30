# InputAdapter 与 FieldRoute 语义路由重构 TODO

日期：2026-05-18

## 目的

本文档定义了当前 `InputAdapter` 与 `FieldRoute` 集成的渐进式修正计划。

目标架构为：

```text
InputAdapter = 模式感知的预理解层
FieldRoute = 模式无关的语义路由层
后续阶段 = SPL 构造 / IR 生成层
```

当前实现已经具备正确的高层管线形态：

```text
原始文本
-> InputAdapterRegistry
-> CanonicalCompileInput
-> SpanSlicer
-> FieldRouter
-> worker / flow / block / resource / step / constraint 阶段
-> SPL 渲染器和诊断
```

然而，各层职责还不够清晰。`InputAdapter` 大体符合预期设计，而 `FieldRoute` 仍然过薄，尚无法充当统一的语义路由层。

本文档是一份修正计划，而非推倒重来的重新设计。重构必须在正确的地方保留现有管线行为，保持与现有测试的兼容性，并逐步将语义职责移入正确的层级。

## 背景

自然语言输入有多种组织方式：

- 任务背景；
- 流程；
- 输入与输出；
- 策略；
- 失败处理；
- 委托规则；
- 同时包含动作、约束、失败条件和资源引用的混合语句。

将此类输入直接转换为 SPL 是不稳定的。编译器在物化 SPL 构造之前需要一个稳定的中间语义表示。

`FieldRoute` 应当就是这个表示：

```text
原始/适配后的跨度
-> 归一化的语义字段和路由标注
-> 用于 SPL 构造生成的稳定输入
```

`InputAdapter` 不应替代 `FieldRoute`。它只应在输入已具有已知结构时降低路由不确定性。

对于结构化 NL，这意味着：

```text
原始文本
-> InputAdapter 解析 sections、packets、hard facts 和 hints
-> SpanSlicer 创建 section 感知/packet 感知的跨度
-> FieldRoute 消费跨度及适配器证据
-> 后续阶段生成部分或完整的 SPL IR
```

## 当前实现概要

当前实现已经包含若干有价值的组件：

- `CanonicalCompileInput`，包含 `raw_sections`、`semantic_packets`、`hard_facts`、`compile_hints`、`warnings` 和 `detection`。
- `StructuralNLAdapter`，能够识别：
  - `task_family`
  - `inputs_for_each_run`
  - `required_outputs`
  - `reusable_process`
  - `policies`
  - `failure_handling`
  - `delegation_policy`
- `SpanSlicer` 规范路径，创建携带 `source_section_id` 和 `source_packet_id` 的跨度。
- `FieldRouter` 规范路径，对适配器感知的跨度进行确定性路由。
- `bridge_failure_modes()`，将 `FailureModeFact` 转换为部分 `ExceptionFlow` 骨架，不虚构 handler 命令。
- `bridge_delegation_intents()`，为缺少有效交接合约的委托意图发出诊断。

这些组件是有价值的，应当保留。

## 当前问题

### 问题 1：FieldRouteIR 过于浅薄

`FieldRouteIR` 目前仅存储六个 span id 列表：

```text
identity
audience
rules
domain
integrations
behavior
```

这对于第一轮分类是够用的，但对于编译器级别的语义路由来说远远不够。它无法表达：

- 语义角色；
- 路由理由；
- 适配器提示使用情况；
- 构造目标；
- 槽位目标；
- 包来源；
- 路由诊断；
- 主路由与次路由；
- 多标签跨度。

当前的 `validate_no_overlap()` 还将重叠视为可疑，而预期设计明确允许一个跨度携带多个语义含义。

### 问题 2：适配器提示不是一等路由证据

对于结构化输入，`FieldRouter._execute_canonical()` 主要通过 `packet_type` 进行路由。

它没有正确消费：

- `semantic_packets.compile_targets`；
- `compile_hints.flow_hints`；
- `compile_hints.process_hints`；
- `compile_hints.constraint_hints`；
- `compile_hints.delegation_hints`；
- `hard_facts` 作为权威的非命令证据。

结果便是，`InputAdapter` 产生了有用的提示，但 `FieldRoute` 尚不是解释、修正或诊断这些提示的中心场所。

### 问题 3：失败处理通过桥接而非路由到达 ExceptionFlow

当前的失败路径大致为：

```text
failure_handling section
-> StructuralNLAdapter.hard_facts.failure_modes
-> failure_mode semantic packet
-> Stage 2 将 failure_mode 路由到 rules
-> Stage 4 运行 flow assembly
-> bridge_failure_modes() 追加部分 ExceptionFlow 骨架
```

这防止了意外的命令虚构，这是好的。

但从语义上讲，这条路由是错误的，或者至少是欠指定的。失败模式不是普通的规则，也不是普通的动作步骤。它应该被表示为：

```text
semantic_role = failure_mode
route_family = flow_relevant
construct_target = EXCEPTION_FLOW
slot_target = condition
executable = false
```

桥接目前弥补了缺失的路由语义。

### 问题 4：Stage 7 依赖 `routes.behavior` 作为可执行候选输入

`StepExtractor` 从 behavior 跨度中提取命令。因此，天真地将失败模式移入 `behavior` 会有产生虚假命令的风险，例如：

```text
COMMAND: Handle missing timeframe
```

任何使失败模式变得与流相关的重构，也必须教会 Stage 7 跳过不可执行的 behavior 类路由标注。

### 问题 5：Worker 感知路径可能不会收到适配器派生的异常流

当前的失败桥接更新的是遗留的 `FlowStructureIR`。当启用 worker 边界规划时，管线使用 worker 作用域的流计划。适配器派生的异常流骨架可能不会被物化到 worker 作用域的流路径中。

重构必须使失败模式物化在以下两条路径中一致工作：

- 遗留流路径；
- worker 感知流路径。

### 问题 6：来源追踪存在但不完整

`SpanIR` 携带 section 和 packet id，但硬事实证据通常只引用 section。后续的桥接逻辑通过 section 来解析 span id。这对 MVP 是可接受的，但目标架构需要更强的证据链：

```text
source_section_id
source_packet_id
source_span_ids
quoted_text
```

## 全系统影响清单

本次重构影响的不仅仅是 `InputAdapter` 和 `FieldRoute`。任何当前将 `routes.behavior`、`routes.rules` 或 `canonical_input.hard_facts` 视为直接语义契约的阶段都需要审查。

### 核心数据契约

涉及文件：

- `src/nl2spl/canonical/compile_input.py`
- `src/nl2spl/ir/span_ir.py`
- `src/nl2spl/ir/field_route_ir.py`
- `src/nl2spl/ir/flow_structure_ir.py`
- `src/nl2spl/ir/diagnostics.py`

需要的变更：

- 添加路由标注 IR；
- 强化提示元数据和证据引用；
- 保持 `source_section_id` 和 `source_packet_id` 从适配器到诊断/报告全程可用；
- 避免仅用六个 span-id 列表来编码路由语义。

### 适配器层

涉及文件：

- `src/nl2spl/adapters/structural_nl.py`
- `src/nl2spl/adapters/generic_nl.py`
- `src/nl2spl/adapters/llm_engine.py`
- `src/nl2spl/adapters/fact_verifier.py`

需要的变更：

- 结构化适配器应为以下内容发出更强的编译提示：
  - 失败模式；
  - 委托意图；
  - 输入/输出契约；
  - 策略；
  - 流程步骤；
- 失败模式提示必须标识 `EXCEPTION_FLOW.condition`；
- 委托提示在存在有效契约之前必须保持不可执行；
- 事实验证器应在可用时保留包级别的证据。

### Stage 1：SpanSlicer

涉及文件：

- `src/nl2spl/pipeline/stages/stage1_span_slicer.py`

需要的变更：

- 保持包感知的跨度生成；
- 当跨度后续被拆分时保留包和 section 来源；
- 可选地暴露路由标注所需的包元数据。

预期变更级别：小。

### Stage 2：FieldRouter

涉及文件：

- `src/nl2spl/pipeline/stages/stage2_field_router.py`

需要的变更：

- 添加产生标注的规范路由；
- 一起消费语义包、硬事实和编译提示；
- 生成路由诊断；
- 保留遗留的六字段列表以确保兼容性；
- 不再将 `failure_mode` 作为普通 `rules` 进行路由；
- 将失败模式标记为与流相关的、不可执行的异常条件候选。

预期变更级别：高。

### Stage 3：AmbiguityResolver

涉及文件：

- `src/nl2spl/pipeline/stages/stage3_ambiguity_resolver.py`

当前风险：

- 模糊跨度拆分目前从六个列表重建 `FieldRouteIR`，丢弃适配器来源和任何未来的路由标注。

需要的变更：

- 当跨度被拆分时，传播：
  - `source_section_id`；
  - `source_packet_id`；
  - 父路由标注；
  - 在仍然适用的情况下的语义角色；
- 如果拆分输出改变了路由语义，更新标注而不仅仅是更新旧的字段列表。

预期变更级别：中。

### Stage 3.5：WorkerBoundaryPlanner

涉及文件：

- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/executor.py`
- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/prompt_builder.py`
- `src/nl2spl/pipeline/stages/stage3_5_worker_boundary_planner/materializer.py`

当前风险：

- worker 规划由 `routes.behavior` 驱动；
- 如果失败模式变成与流相关的 behavior 类标注，它们可能被错误地分配为 worker 拥有的可执行工作；
- materializer 从硬事实中恢复契约，这很有用，但不应成为第二个路由系统。

需要的变更：

- 候选提取必须使用可执行的 behavior 候选，而非所有 behavior 类标注；
- 失败条件标注应作为上下文可用，而非 worker 任务候选；
- 委托意图标注应为边界决策提供信息，但不得在没有契约的情况下直接创建可执行 worker；
- worker 所有权必须包含流条件跨度，以便在需要时放置异常流，而不将其视为步骤候选。

预期变更级别：高。

### Stage 4：FlowAssembler

涉及文件：

- `src/nl2spl/pipeline/stages/stage4_flow_assembler/executor.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/flow_parser.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/span_filter.py`
- `src/nl2spl/pipeline/stages/stage4_flow_assembler/irs_checker.py`

当前风险：

- 流组装当前读取 `routes.behavior`；
- 适配器失败模式在 Stage 4 之后由 `bridge_failure_modes()` 追加；
- worker 感知的跨度过滤可能会丢弃异常条件跨度（如果它们不是被拥有的 behavior 跨度）。

需要的变更：

- 从可执行 behavior 候选组装主流；
- 从目标为 `EXCEPTION_FLOW.condition` 的路由标注物化异常流；
- 去重 LLM 生成的和路由派生的异常流；
- 在 worker 感知的 `WorkerFlowPlanIR` 中支持路由派生的异常流；
- 保留 `ExceptionFlow.spans` 用于来源追踪和缺失 handler 诊断。

预期变更级别：高。

### Stage 5：BlockAssembler

涉及文件：

- `src/nl2spl/pipeline/stages/stage5_block_assembler/executor.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler/prompt_enricher.py`
- `src/nl2spl/pipeline/stages/stage5_block_assembler/block_postprocess.py`

当前风险：

- 块组装接收异常流但没有路由语义；
- 仅有条件的部分异常流可能需要确定性回退块（如果 LLM 不创建异常流块）。

需要的变更：

- 确保每个路由派生的异常流都能渲染为部分骨架；
- 避免对部分异常流要求 handler 块；
- 在 worker 感知模式下，保留 worker 作用域的异常流块。

预期变更级别：中。

### Stage 6：ResourceExtractor

涉及文件：

- `src/nl2spl/pipeline/stages/stage6_resource_extractor/legacy.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/context_builder.py`
- `src/nl2spl/pipeline/stages/stage6_resource_extractor/resource_name_filter.py`

当前风险：

- 资源提取读取 `routes.behavior` 和 `routes.integrations`；
- 硬事实输入/输出与路由分开合并；
- 异常条件通过流摘要可见，但不通过路由标注可见。

需要的变更：

- 将输入/输出硬事实视为权威的契约资源；
- 将不可执行的失败条件跨度排除在变量提取之外，除非它们提到具体资源；
- 在资源上下文中包含路由标注摘要；
- 保持资源名称过滤器阻止编译器模式术语，如 `source_section_id`、`source_packet_id` 和 `exception_flows`。

预期变更级别：中。

### Stage 7：StepExtractor

涉及文件：

- `src/nl2spl/pipeline/stages/stage7_step_extractor/extractor.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/irs_checker.py`
- `src/nl2spl/pipeline/stages/stage7_step_extractor/legacy.py`

当前风险：

- Stage 7 使用 `routes.behavior` 作为可执行步骤输入；
- 有源头的不可执行失败条件如果进入 behavior 而没有可执行标志，可能变成 `GENERAL_COMMAND`；
- worker 作用域的 Stage 7 也将 `routes.behavior` 与流跨度相交。

需要的变更：

- 通过路由辅助方法选择可执行步骤候选；
- 跳过 `executable = false` 的标注；
- 避免对跳过的不可执行语义材料产生未映射 behavior 诊断；
- 保持交接生成的 `INVOKE_WORKER` / `CALL_API` 逻辑由契约驱动；
- 确保 `REQUEST_INPUT` 仅从显式的 ask/request 证据生成，而非从缺失失败 handler 的假设中产生。

预期变更级别：高。

### Stage 8：ProfileExtractor

涉及文件：

- `src/nl2spl/pipeline/stages/stage8_profile_extractor.py`

当前风险：

- profile 提取读取 `routes.identity`、`routes.audience` 和 `routes.domain`；
- 结构化的 `task_family` 目前映射到 domain，而适配器 profile 提示可能携带更丰富的 persona/domain 意图。

需要的变更：

- 可选地优先使用具有 profile/domain 语义角色的路由标注；
- 保留旧字段列表作为回退；
- 避免将失败或策略标注用作 profile 概念，除非明确被路由为 domain 上下文。

预期变更级别：低到中。

### Stage 9：ConstraintExtractor

涉及文件：

- `src/nl2spl/pipeline/stages/stage9_constraint_extractor.py`

当前风险：

- 约束提取只读取 `routes.rules`；
- `failure_mode` 当前被路由到 rules，因此更改失败路由可能会将失败文本从约束提示中移除；
- 委托边界目前部分表示为约束提示。

需要的变更：

- 使用路由标注作为约束候选；
- 保持策略跨度作为 rules；
- 仅在委托边界表达边界（而非可执行委托）时将其视为约束；
- 不将失败模式条件视为普通策略约束，除非文本明确陈述了策略。

预期变更级别：中。

### Stage 9.5：Normalizer

涉及文件：

- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalizer.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/normalization.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_scoped.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/flow_classification.py`
- `src/nl2spl/pipeline/stages/stage9_5_normalizer/worker_handoffs.py`

当前风险：

- 缺失 handler 逻辑大体正确，但它只看到最终的异常流和步骤；
- 伪 handler 检测必须保持作为防止 LLM 将条件重述为 handler 的守卫；
- worker 作用域的规范化也必须诊断路由派生的异常流。

需要的变更：

- 为路由派生的异常流保留缺失 handler 诊断；
- 确保当条件跨度和 handler 跨度重叠时应用伪 handler 过滤；
- 确保 worker 作用域的异常流获得作用域诊断；
- 避免 normalizer 虚构输出生产者或 handler 步骤。

预期变更级别：中。

### Stage 10：WorkerAssembler

涉及文件：

- `src/nl2spl/pipeline/stages/stage10_worker_assembler/assembler.py`
- `src/nl2spl/pipeline/stages/stage10_worker_assembler/child_worker_builder.py`

当前风险：

- assembler 已经将异常流携带到 `WorkerIR` 中，但依赖于 Stage 4/5 保留流和块；
- worker 感知的组装从 worker 作用域的流/块计划构建主异常流和子异常流。

需要的变更：

- 无重大语义重写，但添加测试证明路由派生的异常流在主 worker 和子 worker 中都能渲染；
- 确保仅有条件的异常流保持可渲染的部分结构。

预期变更级别：低到中。

### 可执行门控

涉及文件：

- `src/nl2spl/pipeline/executable_gate.py`

当前风险：

- 门控过滤的是步骤，而非路由标注；
- 它诊断门控后过滤掉的 handler，但不知道条件是否源自路由标注。

需要的变更：

- 保持过滤可执行步骤；
- 在假设的 handler 被阻止后保留路由派生的缺失 handler 诊断；
- 可选地在门控诊断中包含路由/来源元数据。

预期变更级别：低。

### Stage 11：SPLRenderer

涉及文件：

- `src/nl2spl/pipeline/stages/stage11_spl_renderer/renderer.py`
- `src/nl2spl/pipeline/stages/stage11_spl_renderer/block_renderer.py`

当前风险：

- 渲染器已经渲染异常流骨架；
- 它不知道路由标注，如果上游 IR 正确，也不应该需要知道。

需要的变更：

- 主要是测试覆盖；
- 确保空的异常流块仍然渲染合法的部分 `EXCEPTION_FLOW` 骨架；
- 确保子 worker 异常流渲染一致。

预期变更级别：低。

### 来源追踪与报告

涉及文件：

- `src/nl2spl/pipeline/provenance.py`
- `src/nl2spl/compiler/report_renderer.py`
- `src/nl2spl/compiler/feedback_report_renderer.py`
- `src/nl2spl/compiler/diagnostic_analyzer.py`
- `src/nl2spl/compiler/assumptions.py`

当前风险：

- 来源从 `source_span_ids` 和硬事实中解析；
- 路由标注尚不是可追踪的对象；
- 如果硬事实仅引用 section，诊断可能丢失包级别的证据。

需要的变更：

- 将路由派生的异常流追溯到 section、packet 和 span 证据；
- 追踪不可执行的委托意图而不渲染可执行的 SPL；
- 在报告中包含路由诊断；
- 避免来自 normalizer、诊断分析器和门控的重复缺失 handler 诊断。

预期变更级别：中。

### 编排器

涉及文件：

- `src/nl2spl/pipeline/orchestrator.py`

当前风险：

- 编排器在 Stage 4 之后直接调用 `bridge_failure_modes()`；
- 编排器在诊断期间直接调用 `bridge_delegation_intents()`；
- behavior 跨度所有权修复使用 `resolved_routes.behavior`；
- 规范的硬事实作为侧通道证据传递给多个阶段。

需要的变更：

- 路由派生的物化应在 Stage 4 输出最终确定之前或内部发生；
- 桥接调用应变为受保护的兼容性回退，然后被移除；
- 所有权修复应使用可执行 behavior 路由辅助方法；
- 最终诊断应包含路由诊断。

预期变更级别：高。

### 测试与 Fixtures

涉及区域：

- `tests/unit/test_field_router.py`
- `tests/unit/test_input_adapter_pipeline.py`
- `tests/unit/test_failure_mode_bridge.py`
- `tests/unit/test_flow_assembler.py`
- `tests/unit/test_step_extractor.py`
- `tests/unit/pipeline/stages/test_stage3_5_worker_boundary_planner.py`
- `tests/unit/pipeline/stages/test_stage7_worker_scoped.py`
- `tests/integration/test_partial_spl_mvp.py`
- `tests/integration/test_v5_irs_pipeline.py`
- `tests/integration/test_llm_adapter_engine_e2e.py`
- `examples/output` 下的示例中间 JSON

需要的变更：

- 添加路由标注测试，同时保留旧的字段列表测试；
- 将桥接测试迁移到路由驱动的 materializer 测试；
- 添加 worker 感知的失败模式回归测试；
- 更新假设失败模式位于 `routes.rules` 中的 fixtures；
- 为失败模式、委托意图和硬事实输入/输出契约添加反虚构测试。

## 目标设计

### 目标管线

```text
通用 NL：
    raw_text
    -> GenericNLAdapter
    -> CanonicalCompileInput
    -> SpanSlicer
    -> FieldRoute
    -> 构造生成

结构化 NL：
    raw_text
    -> StructuralNLAdapter
    -> CanonicalCompileInput
    -> 包感知的 SpanSlicer
    -> 提示感知的 FieldRoute
    -> 构造生成
```

所有输入都应通过相同的规范路由和编译管线。

### 目标 `InputAdapter` 职责

`InputAdapter` 应该：

- 检测已知的输入模式；
- 解析 sections；
- 创建语义包；
- 提取确定性的硬事实；
- 产生编译提示；
- 保留来源追踪；
- 发出适配器警告。

`InputAdapter` 不得：

- 生成 SPL；
- 生成最终的 Flow/Step/Worker/Constraint IR；
- 决定 worker 边界；
- 虚构缺失的 handler；
- 将委托意图直接转换为可执行调用。

### 目标 `FieldRoute` 职责

`FieldRoute` 应该：

- 将跨度和包分类到归一化的语义字段中；
- 将适配器证据作为路由先验消费；
- 允许一个跨度具有多个语义标注；
- 保留 section、packet 和 span 来源；
- 区分可执行动作候选和不可执行语义材料；
- 在适配器提示与内容冲突时记录诊断；
- 为后续构造生成提供稳定输入。

`FieldRoute` 不得：

- 生成 SPL；
- 创建最终的 `ExceptionFlow`、`StepIR` 或 `WorkerIR`；
- 默默地将硬事实转化为命令；
- 因不完整而丢弃有源头的材料。

### 目标失败处理语义

结构化 NL：

```text
Failure handling:
Missing timeframe, conflicting instructions, insufficient source access.
```

应变为：

```text
SemanticPacket:
    packet_type = failure_mode
    modality = hard_fact
    compile_targets = ["flow.exception.condition"]

HardFacts:
    failure_modes = [
        "Missing timeframe",
        "conflicting instructions",
        "insufficient source access"
    ]

CompileHint:
    route_family = flow_relevant
    construct_target = EXCEPTION_FLOW
    slot_target = condition
    executable = false
```

然后 `FieldRoute` 应产生如下路由标注：

```text
span_id = s7
primary_field = behavior
semantic_role = failure_mode
route_family = flow_relevant
construct_target = EXCEPTION_FLOW
slot_target = condition
executable = false
source_section_id = sec_failure_handling
source_packet_id = p_failure_mode_missing_timeframe
```

后续的流物化可以创建一个部分异常流：

```text
[EXCEPTION_FLOW: Missing timeframe]
    # 没有虚构的 handler
[END_EXCEPTION_FLOW]
```

并且诊断应报告：

```text
missing_handler: 存在失败条件，但未提供 handler 动作。
```

## 重构原则

1. 保持 `CanonicalCompileInput` 作为单一的适配器输出。
2. 保留当前适配器行为，除非需要更强的来源追踪或更清晰的提示而要求变更。
3. 兼容地扩展 `FieldRouteIR`；第一阶段不要移除现有的六个字段。
4. 首先以增量方式添加路由标注，然后迁移各阶段来消费它们。
5. 保持硬事实对资源契约和失败条件的权威性。
6. 永远不要将硬事实路由为可执行命令，除非源文本显式包含动作。
7. 支持部分 SPL 和诊断，而不是虚构缺失的槽位。
8. 保持遗留路径和 worker 感知路径行为一致。

## 提议的路由模型

在保留旧列表的同时引入新的路由标注模型：

```python
@dataclass
class RouteAnnotation:
    span_id: str
    field: str
    semantic_role: str | None = None
    route_family: str | None = None
    source_section_id: str | None = None
    source_packet_id: str | None = None
    source_hint_ids: list[str] = field(default_factory=list)
    construct_target: str | None = None
    slot_target: str | None = None
    executable: bool = True
    primary: bool = True
    diagnostics: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

扩展 `FieldRouteIR`：

```python
@dataclass
class FieldRouteIR:
    identity: list[str] = field(default_factory=list)
    audience: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    domain: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    behavior: list[str] = field(default_factory=list)
    annotations: list[RouteAnnotation] = field(default_factory=list)
```

兼容性规则：

- 现有阶段可以继续读取 `routes.behavior`、`routes.rules` 等；
- 新阶段应优先使用 `routes.annotations`；
- 辅助 API 应暴露：
  - `get_annotations(span_id)`；
  - `get_executable_behavior_span_ids()`；
  - `get_flow_condition_span_ids()`；
  - `get_annotations_by_construct("EXCEPTION_FLOW")`。

## 分阶段计划

## 阶段 0：基线与安全网

### 目标

在更改路由语义之前捕获当前行为。

### 任务

1. 为结构化 NL 添加有针对性的基线测试：
   - 输入和输出是硬事实；
   - 失败模式变为 `FailureModeFact`；
   - 失败模式跨度目前不变成命令；
   - 当不存在 handler 时生成部分 `EXCEPTION_FLOW`；
   - 委托意图在没有契约的情况下不渲染 `INVOKE_WORKER`。
2. 添加一个 worker 感知回归测试，展示 `enable_worker_boundary_planner=True` 时失败模式的当前行为。
3. 记录以下内容的当前预期中间输出：
   - `canonical_input`；
   - Stage 1 跨度；
   - Stage 2 路由；
   - Stage 4 流；
   - 诊断。

### 验收标准

- 基线测试在本地运行并记录当前行为。
- 此阶段不改变任何生产代码行为。
- 已知差距被显式标记为预期失败或 TODO 测试。

## 阶段 1：强化适配器提示和证据

### 目标

使适配器输出足够清晰地表达预期语义，以便 FieldRoute 后续消费。

### 任务

1. 为失败模式扩展 `CompileHint` 的使用：
   - `target = "EXCEPTION_FLOW"`；
   - `suggested_condition = 失败文本`；
   - `metadata["route_family"] = "flow_relevant"`；
   - `metadata["slot_target"] = "condition"`；
   - `metadata["executable"] = False`。
2. 更新 `failure_mode` 语义包：
   - `compile_targets = ["flow.exception.condition"]`。
3. 在可能的情况下为硬事实添加包级别的证据引用：
   - `source_section_id`；
   - `source_packet_id`；
   - `quoted_text`。
4. 为委托添加类似的提示元数据：
   - `route_family = "delegation_boundary"`；
   - `executable = False`，除非存在具体的交接契约。
5. 如需要，更新规范验证器以验证提示证据的一致性。

### 验收标准

- `StructuralNLAdapter` 对 `Failure handling` 的输出包含条件级别的提示。
- 每个失败模式硬事实具有可追踪的 section 证据，以及在可用情况下的 packet 证据。
- 现有适配器测试仍然通过。
- 尚不要求 SPL 渲染行为变更。

## 阶段 2：添加 RouteAnnotation 而不改变阶段行为

### 目标

在保留现有字段列表的同时引入更丰富的路由语义。

### 任务

1. 将 `RouteAnnotation` 添加到 IR 包中。
2. 用 `annotations` 扩展 `FieldRouteIR`。
3. 添加辅助方法：
   - `get_annotations(span_id)`；
   - `get_primary_field(span_id)`；
   - `get_executable_behavior_span_ids()`；
   - `get_non_executable_flow_condition_span_ids()`；
   - `get_construct_slot_candidates(construct, slot)`。
4. 保持 `identity`、`rules`、`behavior` 等不变以确保兼容性。
5. 更新序列化/检查点以包含标注。
6. 为以下内容添加测试：
   - 旧列表字段仍然工作；
   - 标注可以表示多个语义角色；
   - `validate_no_overlap()` 不再阻止标注级别的多标签语义。

### 验收标准

- `FieldRouteIR` 的所有现有调用者继续工作。
- 新的标注测试通过。
- 检查点包含标注数据。
- 尚不需要任何阶段消费标注。

## 阶段 3：使 FieldRouter 消费适配器证据

### 目标

将 `FieldRouter` 规范路径转变为提示感知的语义路由器。

### 任务

1. 在 `FieldRouter._execute_canonical()` 中构建索引：
   - 按 id 索引 packet；
   - 按 id 索引 section；
   - 按 section 索引提示；
   - 在有证据的情况下按 packet 索引提示；
   - 按 section / packet 索引硬事实。
2. 按语义优先级路由：
   - 硬事实资源契约优先；
   - 失败模式作为流条件候选；
   - 流程步骤作为可执行 behavior 候选；
   - 策略作为 rules；
   - 委托意图作为不可执行委托边界候选；
   - 任务族作为 domain/profile 上下文。
3. 为每个已路由的跨度生成 `RouteAnnotation`。
4. 从标注的主字段中保留旧的字段列表。
5. 为冲突添加路由诊断：
   - 适配器说是策略但文本看起来像可执行动作；
   - 适配器说是失败模式但文本包含显式的 handler 动作；
   - section 说是委托但没有 worker 契约存在。
6. 保持通用 NL 路径与遗留 LLM 路由兼容，但可选地添加从 LLM 路由字段派生的简单标注。

### 验收标准

- 结构化失败模式产生标注：
  - `semantic_role = "failure_mode"`；
  - `construct_target = "EXCEPTION_FLOW"`；
  - `slot_target = "condition"`；
  - `executable = False`。
- 运行时输入和所需输出不被路由为可执行 behavior。
- 策略路由到 rules 并带约束标注。
- 委托策略路由到不可执行委托标注。
- 现有 Stage 2 测试在更新预期路由元数据后通过。

## 阶段 4：保护 Stage 7 免受不可执行语义材料影响

### 目标

确保更丰富的路由不会产生虚构命令。

### 任务

1. 更新 `StepExtractor`，当标注可用时使用 `routes.get_executable_behavior_span_ids()` 选择可执行 behavior 跨度。
2. 为没有标注的遗留 `FieldRouteIR` 保留回退行为。
3. 仅在调试有用时为不可执行路由标注添加显式跳过诊断，而非作为面向用户的编译警告。
4. 添加测试：
   - `failure_mode` 路由在 behavior/flow-relevant 族中不产生 `GENERAL_COMMAND`；
   - 没有交接契约的 `delegation_policy` 不产生 `INVOKE_WORKER`；
   - 普通流程步骤仍然产生命令候选。

### 验收标准

- `Missing timeframe` 永远不会被发出为 `COMMAND: Handle missing timeframe`，除非源文本显式提供了 handler 动作。
- Stage 7 未映射 behavior 诊断不对不可执行失败条件跨度触发。
- 现有的正常 behavior 提取仍然工作。

## 阶段 5：将失败物化移入流构造

### 目标

使 `EXCEPTION_FLOW` 的创建消费路由标注，而不是通过单独的硬事实桥接绕过 FieldRoute。

此阶段是第一个下游迁移阶段。目的不仅是添加更好的路径，而是开始将语义所有权从 `pipeline.fact_bridges` 移入正常的路由 -> 流构造路径。

### 任务

1. 创建一个流物化辅助函数，消费：
   - `RouteAnnotation(construct_target="EXCEPTION_FLOW", slot_target="condition")`；
   - `FailureModeFact` 作为回退证据。
2. 在 Stage 4 内部或紧邻 Stage 4 使用该辅助函数。
3. 在迁移期间将 `bridge_failure_modes()` 保留为兼容性包装器。
4. 生成没有 handler 的部分 `ExceptionFlow` 骨架。
5. 保留现有的 LLM 生成的异常流，并按归一化条件文本去重。
6. 确保路由标注来源流入 `ExceptionFlow.spans`。

### 验收标准

- 失败模式从 FieldRoute 标注物化。
- 如果标注缺失但硬事实存在，回退仍然工作。
- 同一条件没有重复的异常流。
- 缺失 handler 诊断仍然通过 IRS/normalizer 路径触发。
- 现有失败桥接测试通过或被迁移到新的辅助函数。

### 下游迁移备注

当前编排器在 Stage 4 之后应用失败桥接：

```text
Stage 4 FlowAssembler
-> bridge_failure_modes()
-> Stage 4 IRS check
-> Stage 5 BlockAssembler
```

此阶段之后，预期的流程应变为：

```text
Stage 2 FieldRoute 标注
-> Stage 4 FlowAssembler / 流物化器
-> Stage 4 IRS check
-> Stage 5 BlockAssembler
```

`bridge_failure_modes()` 应暂时保留，但仅作为尚未提供路由标注的输入或测试的兼容性回退。

一旦路由标注可用，编排器应停止将 `canonical_input.hard_facts.failure_modes` 作为主要物化源。

## 阶段 6：支持 Worker 感知的异常流物化

### 目标

使适配器派生的失败模式在遗留路径和 worker 感知路径中都工作。

### 任务

1. 确定失败条件跨度的所有权：
   - 如果失败条件跨度由某个 worker 拥有，将异常流附加到该 worker；
   - 如果它是全局的且没有 worker 拥有它，附加到主 worker 或根据 worker 计划语义发出诊断。
2. 扩展 worker 作用域流计划物化以包含适配器派生的异常流。
3. 确保 worker 作用域的 Stage 5/10/11 能够渲染部分异常流。
4. 当失败条件所有权模糊时添加诊断。

### 验收标准

- 在 `enable_worker_boundary_planner=True` 时，结构化失败模式仍然产生部分异常流。
- 异常流来源指回 `sec_failure_handling` 和 packet/span id。
- 没有失败条件在 worker 作用域期间被静默丢弃。
- Worker 感知输出和遗留输出在语义上一致。

### 下游迁移备注

此阶段必须更新下游的 worker 感知代码，而不仅仅是前端路由。

涉及区域包括：

- `WorkerBoundaryPlanner`，因为 behavior 所有权目前驱动 worker 作用域流构造。
- `FlowAssembler._execute_worker_aware()`，因为它目前按 `routes.behavior` 过滤。
- worker 作用域的 Stage 5 和 Stage 10，因为异常流必须保持附加到正确的 worker 直到渲染。
- 渲染器和来源聚合，因为部分异常流需要像遗留流一样的追踪记录。

在此阶段完成之前不要删除桥接兼容性。否则遗留路径可能通过而 worker 感知路径静默丢弃失败模式。

## 阶段 7：路由诊断与冲突处理

### 目标

使 FieldRoute 修正行为可见且可审计。

### 任务

1. 添加结构化路由诊断，或将路由诊断映射到现有的 `CompileDiagnostic`。
2. 至少检测以下情况：
   - section 提示与文本内容冲突；
   - 硬事实被解释为可执行动作；
   - 失败模式包含条件但没有 handler；
   - 委托意图缺少有效契约；
   - 输入/输出契约在需要时缺少生产者或消费者。
3. 确保诊断包含：
   - `source_span_ids`；
   - 在可用时的 `source_section_id`；
   - 在可用时的 `source_packet_id`；
   - 建议的解决方案。
4. 如果下游尚未覆盖，为路由级别诊断添加可读的报告渲染。

### 验收标准

- 路由冲突在 `PipelineResult.diagnostics` 或等效的中间诊断中可见。
- 诊断不阻止渲染，除非缺失的槽位使渲染不可能。
- 不因有源头的部分结构仅仅是部分的就发出诊断。

## 阶段 8：废弃以桥接为中心的语义

### 目标

一旦路由驱动的物化稳定，移除或降级桥接逻辑。

### 任务

1. 审计所有对以下内容的使用：
   - `bridge_failure_modes()`；
   - `bridge_delegation_intents()`；
   - 仅硬事实的物化路径。
2. 用路由驱动的流物化替换编排器级别的失败桥接：
   - 移除直接的后 Stage 4 调用，这些调用以 `canonical_input.hard_facts.failure_modes` 为主要来源；
   - 仅在路由标注缺失时保留受保护的回退。
3. 将桥接测试迁移到新的路由驱动 materializer 测试：
   - 仅有条件的失败模式创建部分 `ExceptionFlow`；
   - 重复条件去重仍然工作；
   - 缺失 handler 诊断仍然出现；
   - section / packet / span 来源被保留。
4. 在一个发布窗口期内仅将桥接保留为兼容性适配器、诊断辅助或测试 fixtures。
5. 为桥接包装器添加废弃注释：
   - 说明替代 API；
   - 说明移除条件；
   - 说明哪些测试证明了替代覆盖。
6. 仅在遗留和 worker 感知的路由驱动测试覆盖所有桥接行为后才删除桥接包装器。
7. 更新文档，说明 FieldRoute 标注是后续阶段的主要语义契约。
8. 在安全的地方移除重复的失败/委托逻辑。

### 验收标准

- 失败和委托语义不分散在不相关的管线位置。
- 后续阶段可以从路由标注和来源中解释其决策。
- `bridge_failure_modes()` 要么被移除，要么除受保护的兼容性回退外没有生产调用点。
- `bridge_delegation_intents()` 要么被移除，要么降级为诊断兼容性，以路由标注作为主要证据源。
- 桥接包装器在移除前有清晰的 TODO 或废弃注释。

## 桥接删除策略

桥接删除必须有计划地进行，而非立即执行。

### 暂时保留

在以下情况下保留 `bridge_failure_modes()`：

- Stage 4 尚不能从路由标注物化异常流；
- worker 感知流物化不完整；
- 现有测试仍然直接断言桥接行为。

在以下情况下保留 `bridge_delegation_intents()`：

- 委托标注尚未直接供给诊断；
- worker 交接契约验证仍然依赖于事后硬事实扫描。

### 转换为兼容性包装器

一旦路由标注可用，桥接应变为薄包装器：

```text
硬事实
-> 如果缺失则合成路由标注
-> 调用路由驱动的 materializer / 诊断分析器
```

这保持了旧调用者工作，同时确保只存在一个语义实现。

### 删除或限制

仅在以下情况下删除或限制桥接代码：

- 路由驱动的遗留测试通过；
- 路由驱动的 worker 感知测试通过；
- 诊断和来源与桥接时代的行为匹配或更优；
- 没有生产编排器路径依赖于桥接优先的语义；
- 文档和示例使用路由标注作为规范路径。

如果删除风险过大，将包装器移入兼容性模块并标记为废弃。它们不应是主要的语义路径。

## 阶段 9：文档与迁移清理

### 目标

使新架构可理解且可执行。

### 任务

1. 更新 InputAdapter 文档以澄清：
   - 适配器发出证据和提示；
   - 适配器不决定最终构造。
2. 更新管线架构文档以澄清：
   - FieldRoute 是统一的语义路由层；
   - 路由标注是前端理解与构造生成之间的契约。
3. 添加示例：
   - 带失败处理的结构化输入；
   - 带委托策略的结构化输入；
   - 包含动作和策略的混合自由形式语句；
   - 没有生产者的输入/输出契约。
4. 为下游阶段作者添加迁移说明。

### 验收标准

- 文档描述的行为与测试强制执行的一致。
- 新开发者能够识别在哪里添加新的语义角色。
- 现有示例已更新或标注了预期的部分诊断。

## 最终验收标准

当以下所有条件为真时，完整重构完成：

1. 所有输入格式通过 `CanonicalCompileInput`、`SpanSlicer` 和 `FieldRoute`。
2. `InputAdapter` 从不直接生成最终 SPL IR。
3. `FieldRoute` 将适配器提示和硬事实作为证据消费，而非作为不容置疑的最终决定。
4. `FieldRouteIR` 能够表示语义角色、构造目标、槽位目标、可执行/不可执行状态以及来源。
5. 诸如 `Missing timeframe` 的失败模式变为 `EXCEPTION_FLOW.condition` 候选，而非命令。
6. 缺失的失败 handler 产生部分 SPL 加诊断，而非虚构的 handler。
7. 输入和输出仍然是资源契约，而非普通 behavior。
8. 委托策略仍然是委托意图或边界，除非存在有效的交接契约。
9. 遗留路径和 worker 感知路径都保留适配器派生的失败语义。
10. 来源能够将生成的 SPL 元素和诊断追溯到 section、packet 和 span 证据。

## 建议的工作顺序

推荐的实现顺序：

```text
阶段 0 -> 阶段 1 -> 阶段 2 -> 阶段 3 -> 阶段 4
```

此时，最重要的语义修正已经到位。然后继续：

```text
阶段 5 -> 阶段 6 -> 阶段 7
```

最后清理：

```text
阶段 8 -> 阶段 9
```

在阶段 5 和阶段 6 对遗留路径和 worker 感知路径都有回归覆盖之前，不要开始阶段 8。

## 风险评估

### 低风险

- 强化适配器提示。
- 兼容地添加路由标注。
- 添加测试和诊断。

### 中等风险

- 更改 Stage 7 可执行跨度选择。
- 将失败物化移近 Stage 4。
- 更新检查点模式。

### 高风险

- Worker 感知的异常流所有权。
- 过早移除桥接逻辑。
- 允许多标签路由语义而不更新下游消费者。

## 非目标

本次重构不试图：

- 重新设计 SPL 语法；
- 替换 IRS；
- 替换 worker 边界规划；
- 引入置信度分数；
- 要求所有路由都基于 LLM；
- 使不完整的输入编译为完整的 SPL。

## 立即的后续行动

1. 实现阶段 0 基线测试。
2. 实现阶段 1 适配器提示/证据强化。
3. 在阶段 2 添加 `RouteAnnotation` 而不改变阶段行为。
4. 在更改 Stage 7 或 Stage 4 之前审查生成的中间 JSON。
