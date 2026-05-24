# 01 Baseline Gap Tests：暴露 deterministic FieldRoute 的语义缺口

## 目标

在改生产代码前，先用测试明确当前 structural NL FieldRoute 的不足。

本任务不实现新逻辑，只建立 baseline / expected-failure 风格的测试证据，证明：

```text
packet_type / section_title deterministic mapping
```

无法可靠处理混合语义 section。

## 背景

当前 structural NL 路径中：

```text
StructuralNLAdapter
-> SpanSlicer
-> FieldRouter._execute_canonical()
-> deterministic RouteAnnotation
```

`FieldRouter` 不调用 LLM，且测试中有 `mock_client.call_json.assert_not_called()`。

这会导致以下风险：

- `Failure handling` 中的 handler action 被误归为 condition；
- `Delegation policy` 中的 API / worker / policy 被折叠为一个 delegation intent；
- `Reusable process` 中的 constraint 被误归为 executable process step；
- `Inputs for each run` / `Required outputs` 中混入行为文本时没有 conflict diagnostic。

## 实现思路

新增测试应先覆盖“当前行为不够”的场景。可以选择：

1. 先写成当前失败的测试，并用清晰注释说明目标行为；
2. 或者用 `xfail` 标记，等后续任务逐步转绿；
3. 不建议为了让测试绿而弱化断言。

这些测试的价值是定义 R3 的真实验收边界。

## 必须覆盖的场景

### 1. Failure handling condition + handler

输入：

```text
Failure handling:
Missing timeframe: ask one clarifying question.
```

目标行为：

```text
Missing timeframe
-> semantic_role=failure_mode
-> construct_target=EXCEPTION_FLOW
-> slot_target=condition
-> executable=false

ask one clarifying question
-> semantic_role=exception_handler_action 或 split recommendation
-> construct_target=EXCEPTION_FLOW
-> slot_target=handler
-> executable=true
```

当前 deterministic 行为很可能无法拆分。

### 2. Failure handling condition-only

输入：

```text
Failure handling:
Missing timeframe.
```

目标行为：

- 生成 condition annotation；
- 不生成 handler action；
- 不虚构 handler。

该测试确保 R3 后不会过度解释。

### 3. Delegation policy 混合语义

输入：

```text
Delegation policy:
Use SearchAPI for source lookup.
Delegate source gathering to ResearchWorker when connectors are available.
Only delegate if returned evidence can be normalized.
Do not delegate final approval.
```

目标行为：

- `SearchAPI` -> API candidate / integration hint；
- `ResearchWorker` -> worker handoff candidate；
- `when connectors are available` -> handoff condition；
- `Only delegate...` -> delegation boundary constraint；
- `Do not delegate final approval` -> delegation prohibition / policy；
- 没有 valid handoff contract 时，不生成 executable `INVOKE_WORKER`。

### 4. Reusable process 混入 constraint

输入：

```text
Reusable process:
Produce a draft. Do not finalize if required slots are missing.
```

目标行为：

- `Produce a draft` -> executable process material；
- `Do not finalize...` -> constraint / precondition；
- 后者不应成为普通 command。

### 5. Input/output section 混入行为文本

输入示例：

```text
Required outputs:
A draft communication artifact. Ask the user to confirm before finalizing.
```

目标行为：

- `A draft communication artifact` -> output contract；
- `Ask the user...` -> conflict / possible behavior annotation；
- 不应把整个 section 当 output contract 后静默吞掉行为文本。

## 建议修改文件

可新增或修改：

- `tests/unit/test_input_adapter_pipeline.py`
- `tests/unit/test_field_router.py`
- 可选新增：`tests/unit/test_adapter_guided_fieldroute_refinement.py`

不建议修改：

- `src/nl2spl/pipeline/stages/stage2_field_router.py`
- downstream stages
- adapter 生产代码

本任务只写测试，不改生产逻辑。

## 注意事项

- 测试名称必须表达目标行为，不要只测试当前实现。
- 不要只断言“有 annotation”；必须断言 role、executable、construct/slot、provenance。
- 对 mixed span，允许目标行为是 split recommendation，不一定要求 Stage 2 立刻创建 child spans。
- 如果用 `xfail`，必须写明解除条件。
- 不要削弱现有 Internal-Comms happy path 测试。

## 验收标准

本任务通过需满足：

1. 新增测试覆盖 failure condition + handler 混合场景。
2. 新增测试覆盖 condition-only 不虚构 handler。
3. 新增测试覆盖 delegation API / worker / policy 混合场景。
4. 新增测试覆盖 reusable process 中 constraint 不应 executable。
5. 新增测试覆盖 input/output section 混入行为时应产生 conflict 或保留语义。
6. 每个测试都明确目标 route-level 输出。
7. 不修改生产代码。
8. 当前失败测试必须标注为 expected gap，或以 baseline 形式记录当前不满足目标。

## 提交审核时说明

提交时请包含：

- 新增测试文件列表；
- 哪些测试当前通过，哪些标记为 expected gap；
- 每个 expected gap 对应后续哪个任务解决；
- 未修改生产代码的确认；
- 测试命令和结果。
