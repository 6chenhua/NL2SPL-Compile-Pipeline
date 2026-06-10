# AI-assisted SPL Editing 详细设计文档（修订版）

## 0. 文档信息

**模块名称**：AI-assisted SPL Editing
**建议目录**：`src/nl2spl/compiler/spl_editing/`
**设计阶段**：MVP 架构设计（基于 Construct IR）
**目标定位**：基于 diagnostics，对具体 SPL Construct IR 进行 issue-driven、用户确认驱动的 AI 辅助修复。
**核心原则**：

* 不做全文 SPL 重写
* 不直接编辑 SPL Text
* 编辑对象是 SPL Construct IR
* 所有修改必须经过用户确认
* 修复结果最终落到 Construct IR，并重新验证

---

# 1. 设计修正与核心认知

经过进一步分析，原设计中的部分概念需要调整。

最重要的变化是：

> AI-assisted SPL Editing 的真实编辑对象不是 SPL Text，而是 L2SPL Compile Pipeline 生成的 SPL Construct IR。

因此：

```text
用户
  ↓
选择某个有问题的 Construct
  ↓
发送编辑请求
  ↓
后端获取 Construct IR
  ↓
结合 diagnostics 构造上下文
  ↓
LLM 生成修复建议
  ↓
用户确认
  ↓
修改 Construct IR
  ↓
重新验证
```

而不是：

```text
SPL Text
  ↓
定位文本片段
  ↓
替换文本
```

因此 MVP 的核心实际上是：

> Construct-level AI Repair，而不是 Text Patch System。

---

# 2. 功能背景

当前 NL2SPL Compiler 已经能够生成：

```text
CompileResult
PipelineResult

Construct IR

Diagnostics

Feedback Report

Provenance

IRS Satisfaction Result
```

例如：

```text
EXCEPTION_FLOW
 ├─ condition = "Template unavailable"
 └─ handler = None
```

IRS 会产生：

```text
missing_handler
```

此时用户在 UI 中看到该 Exception Flow 被标记为存在问题。

用户点击该 Construct：

```text
Exception Flow:
Template unavailable
```

然后请求 AI 修复。

因此 Editing 的入口实际上是：

```text
Construct + Issue
```

而不是：

```text
SPL Document + Cursor Position
```

---

# 3. 核心设计原则

## 3.1 Construct-driven，而不是 Document-driven

编辑对象：

```text
SPL Construct IR
```

例如：

```text
ExceptionFlowIR
CommandIR
WorkerHandoffIR
OutputIR
```

而不是：

```text
SPL Text Fragment
```

---

## 3.2 Issue-driven

编辑请求必须绑定 Issue。

例如：

```text
missing_handler

missing_output_producer

contract_ambiguity
```

不存在：

```text
请帮我优化整个 SPL
```

这种请求。

---

## 3.3 用户确认驱动

AI 永远只负责：

```text
生成建议
```

真正修改 IR 的动作必须来自：

```text
用户确认
```

因此：

```text
AI Suggestion
    ≠
Applied Repair
```

---

## 3.4 Construct IR 是唯一真实状态

系统中的真实状态：

```text
Construct IR
```

不是：

```text
SPL Text
```

SPL Text 只是 Render Result。

因此：

```text
Construct IR
    ↓
Renderer
    ↓
SPL Text
```

Editing 修改的是：

```text
Construct IR
```

而不是：

```text
Rendered SPL
```

---

# 4. 用户交互模型

## 4.1 实际交互流程

用户在 UI 中：

```text
看到 Issue
    ↓
点击 Construct
    ↓
请求 AI 修复
```

前端发送：

```json
{
  "construct_id": "flow_001",
  "issue_id": "diag_001",
  "user_suggestion": null
}
```

或者：

```json
{
  "construct_id": "flow_001",
  "issue_id": "diag_001",
  "user_suggestion": "Ask requestor to provide approved template."
}
```

---

## 4.2 Suggestions 是可选输入

用户可以：

```text
不给建议
```

让 AI 自己生成候选方案。

或者：

```text
给出自己的修复意图
```

例如：

```text
Ask requestor to provide approved template.
```

然后 AI 基于该意图生成 Construct Repair。

因此：

```python
user_suggestion: str | None
```

应该成为标准输入。

---

## 4.3 Suggestions 可以重新生成

用户可能：

```text
Generate Suggestions
```

得到：

```text
Suggestion A
Suggestion B
Suggestion C
```

不满意。

再次点击：

```text
Regenerate
```

得到新的建议。

这是前端行为。

后端只负责：

```text
Generate Suggestions
```

接口。

---

## 4.4 所有建议必须确认

AI 输出：

```text
Suggestion A
Suggestion B
Suggestion C
```

都不能直接应用。

必须：

```text
用户选择
    ↓
Confirm
```

然后前端发送：

```json
{
  "suggestion_id": "suggestion_b",
  "confirmed": true
}
```

后端才真正修改 Construct IR。

因此：

```text
Generate Suggestion
```

与：

```text
Apply Repair
```

必须是两个独立接口。

---

# 5. 总体架构（修订版）

## 5.1 核心流程

```text
Construct ID
Issue ID
User Suggestion(Optional)
        ↓
Construct Resolver
        ↓
Construct IR
Diagnostics
        ↓
Repair Context Builder
        ↓
Issue-specific Context
        ↓
LLM
        ↓
Repair Suggestions
        ↓
User Confirmation
        ↓
IR Mutation
        ↓
Verification
        ↓
Persist
```

---

## 5.2 为什么仍然需要 Locator

最初认为：

```text
用户已经选中了 Construct
```

似乎不需要 Locator。

但进一步分析后发现：

并非所有 Issue 都天然对应一个明确 Construct。

例如：

```text
missing_handler
```

对应：

```text
ExceptionFlowIR
```

非常明确。

但是：

```text
missing_output_producer
```

对应的是：

```text
Output Variable
```

而不是某个 Command。

例如：

```text
OUTPUT:
approved_template
```

IRS 报告：

```text
missing_output_producer
```

问题是：

```text
哪个 Construct 应该被编辑？
```

可能是：

```text
CommandIR
```

也可能是：

```text
WorkerCallIR
```

甚至：

```text
新增一个 Construct
```

因此系统仍然需要：

```text
Issue Target Resolver
```

只是它不再是：

```text
PatchLocator
```

而应该是：

```text
ConstructLocator
```

职责：

```text
Issue
    ↓
定位需要编辑的 Construct IR
```

---

# 6. Context Builder 设计

这是整个系统最核心的部分。

不同 Issue 需要完全不同的上下文。

因此不能简单：

```text
Construct IR
+
Diagnostics
```

直接塞给 LLM。

必须：

```text
Issue-specific Context Builder
```

---

## 6.1 Missing Handler

需要：

```text
ExceptionFlowIR

Condition

Parent Flow

Diagnostics

User Suggestion
```

---

## 6.2 Missing Output Producer

需要：

```text
Output Definition

ProducerIndex

Flow Graph

Related Commands

Diagnostics
```

因为 AI 必须理解：

```text
为什么这个 Output 没有 Producer
```

---

## 6.3 Contract Ambiguity

需要：

```text
Worker Contract

Call Site

Inputs

Outputs

Diagnostics
```

否则 AI 无法判断：

```text
到底缺什么 Contract 信息
```

---

# 7. 核心数据模型

## 7.1 EditingRequest

```python
@dataclass
class EditingRequest:
    construct_id: str
    issue_id: str

    user_suggestion: str | None = None
```

---

## 7.2 RepairContext

```python
@dataclass
class RepairContext:
    issue: EditableIssue

    construct_ir: Any

    diagnostics: list[CompileDiagnostic]

    related_constructs: list[Any]

    user_suggestion: str | None
```

---

## 7.3 RepairSuggestion

AI 输出：

```python
@dataclass
class RepairSuggestion:
    suggestion_id: str

    explanation: str

    proposed_ir: Any

    rationale: str
```

注意：

```text
proposed_ir
```

才是真正重要的内容。

不是文本。

---

## 7.4 ConfirmedRepair

```python
@dataclass
class ConfirmedRepair:
    suggestion_id: str

    construct_id: str

    replacement_ir: Any
```

---

# 8. Handler 设计（修订）

原设计中的：

```text
RepairRegistry
IssueRepairHandler
```

仍然成立。

但：

```text
handler
```

不是用户扩展点。

因此不需要插件化概念。

这里只是内部组织代码。

例如：

```text
handlers/
    missing_handler.py

    missing_output_producer.py

    contract_ambiguity.py
```

即可。

---

## 8.1 Handler 职责

每个 Handler：

```text
构造 Context

构造 Prompt

调用 LLM

解析结果

生成 RepairSuggestion
```

---

## 8.2 Handler 输入

```python
generate_suggestions(
    context: RepairContext
)
```

---

## 8.3 Handler 输出

```python
list[RepairSuggestion]
```

建议固定：

```text
3 个 Suggestions
```

方便 UI 展示。

---

# 9. Missing Handler 设计

输入：

```text
ExceptionFlowIR

Condition:
Template unavailable

User Suggestion(Optional)
```

输出：

```text
Suggestion A

Ask requestor to provide approved template.
```

对应：

```python
SequentialBlockIR(
    commands=[
        CommandIR(...)
    ]
)
```

---

```text
Suggestion B

Escalate to supervisor.
```

对应：

```python
SequentialBlockIR(...)
```

---

```text
Suggestion C

Terminate workflow.
```

对应：

```python
SequentialBlockIR(...)
```

用户确认后：

```text
ExceptionFlowIR.handler
    ↓
replacement_ir
```

---

# 10. Missing Output Producer 设计

这是 MVP 后最复杂的问题之一。

---

## 10.1 Issue 呈现

用户看到：

```text
OUTPUT:
approved_template
```

被标红。

原因：

```text
missing_output_producer
```

---

## 10.2 编辑目标不明确

问题：

```text
Output 本身不是 Producer
```

因此：

```text
编辑 OutputIR
```

通常没有意义。

真正需要修改的可能是：

```text
CommandIR

WorkerCallIR

APIInvokeIR
```

甚至：

```text
新增 Construct
```

---

## 10.3 ConstructLocator 的职责

因此：

```text
missing_output_producer
```

必须先执行：

```text
Issue
    ↓
ConstructLocator
    ↓
Candidate Constructs
```

例如：

```text
Command-4

WorkerCall-2

APIInvoke-1
```

然后构造上下文。

---

## 10.4 AI Suggestions

AI 可能建议：

### Suggestion A

```text
Bind existing command output.
```

对应：

```python
Modify CommandIR
```

---

### Suggestion B

```text
Add producer command.
```

对应：

```python
Insert CommandIR
```

---

### Suggestion C

```text
Mark output optional.
```

对应：

```python
Modify OutputIR
```

---

# 11. Verification

确认后：

```text
Construct IR
    ↓
Mutation
    ↓
Verification
```

验证包括：

```text
IRS

ProducerIndex

Executable Gate
```

---

验证通过：

```text
Persist
```

否则：

```text
Reject Repair
```

---

# 12. Demo CLI 设计

由于 MVP 没有 UI。

因此 Demo CLI 必须模拟完整交互。

---

## 12.1 Generate Suggestions

```bash
edit-demo suggest \
    --construct flow_001 \
    --issue diag_001
```

输出：

```text
Suggestion A
Suggestion B
Suggestion C
```

---

## 12.2 Generate Suggestions With User Input

```bash
edit-demo suggest \
    --construct flow_001 \
    --issue diag_001 \
    --suggestion "Ask requestor to provide approved template."
```

---

## 12.3 Confirm Suggestion

```bash
edit-demo apply \
    --suggestion suggestion_b
```

执行：

```text
IR Mutation

Verification

Persist
```

---

# 13. 关于 PatchLayer 的修正

原设计：

```python
PatchLayer = Literal[
    "spl_text",
    "ir",
    "requirement_amendment",
]
```

经过分析后：

MVP 实际只需要：

```python
PatchLayer = Literal[
    "ir"
]
```

原因：

### spl_text

不应该存在。

系统真实状态不是 SPL Text。

---

### requirement_amendment

这是未来 Requirement Editing 系统的能力。

不属于当前 SPL Editing MVP。

---

因此：

```python
PatchLayer = Literal["ir"]
```

即可。

---

# 14. 关于 EvidenceStatus 的修正

原设计：

```python
source_backed
user_confirmed
ai_suggested_unconfirmed
assumption_only
```

对于 Editing MVP：

真正进入系统状态的修改：

```text
只能是用户确认后的修改
```

因此最终持久化状态：

```python
EvidenceStatus = Literal[
    "user_confirmed"
]
```

即可。

AI Suggestion 不属于系统状态。

只是临时生成结果。

---

# 15. MVP 范围重新定义

MVP：

```text
missing_handler
```

完整支持。

---

支持：

```text
Generate Suggestions

Confirm Suggestion

IR Mutation

Verification
```

---

暂不支持：

```text
missing_output_producer

contract_ambiguity
```

真正修复。

但架构必须预留：

```text
ConstructLocator

Issue-specific Context Builder
```

因为这两个能力未来一定需要。

---

# 16. 最终结论

经过重新分析后，AI-assisted SPL Editing 的核心模型应调整为：

```text
Issue
    ↓
ConstructLocator
    ↓
Construct IR
    ↓
Context Builder
    ↓
LLM
    ↓
Repair Suggestions
    ↓
User Confirmation
    ↓
IR Mutation
    ↓
Verification
    ↓
Persist
```

其中最关键的几个结论是：

```text
1. 编辑对象是 Construct IR，不是 SPL Text。

2. 用户请求天然绑定 Construct，因此传统 Text Patch 思路不是主路径。

3. PatchLocator 应演进为 ConstructLocator，
   用于解决 missing_output_producer 等无法直接定位编辑目标的问题。

4. Suggestions 必须支持用户输入（可选）。

5. Suggestions 必须支持重新生成。

6. 所有 Suggestions 都必须经过用户确认。

7. Demo CLI 需要模拟 Generate → Confirm 的完整流程。

8. PatchLayer MVP 只保留 IR。

9. EvidenceStatus MVP 只保留 user_confirmed。

10. Context Builder 将成为未来最核心的复杂度来源，
    因为不同 Issue 所需上下文完全不同。
```

因此，本系统本质上不是：

```text
AI Patch Generator
```

而是：

```text
Issue-driven Construct IR Repair System
```

这是与原设计相比最重要的架构修正。
