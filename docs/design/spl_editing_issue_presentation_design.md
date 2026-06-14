# SPL Editing Issue Presentation DTO 设计

## 1. 背景

SPL Editing 后端已经具备从 canonical `ArtifactSnapshot` 读取结构化 compiler state、提取 `EditableIssue`、生成 repair suggestion、用户确认 apply、并通过 Lane A / Lane B compiler replay 验证的能力。

当前 demo 输出仍然偏向开发者调试视角：它直接展示 `CompileDiagnostic` 与 IRS metadata，例如 `diagnostic_id`、`target_ref`、`irs.construct_type`、`irs.construct_id`、`slot_name`、`repairability`。这些字段对后端 repair routing 很重要，但对普通用户并不友好。

用户真正需要看到的是：

- 当前 SPL 还缺什么。
- 缺失内容会造成什么影响。
- 哪些问题可以通过 AI-assisted repair 修复。
- 每个问题有哪些可确认的修复选项。
- 用户确认 apply 后，compiler verification 是否接受修复。
- 更新后的 SPL 是什么。

因此需要新增一个后端-owned presentation DTO 层，将后端已有结构转换成用户可理解、可操作的问题视图。CLI / UI 只负责渲染 presentation DTO，不直接解释 raw diagnostic。

## 2. 设计目标

本设计目标是定义 SPL Editing 用户展示层的后端 contract。

核心目标：

- 默认展示业务问题，而不是 compiler diagnostic dump。
- 将 grouped `EditableIssue` 作为用户问题的基本单位。
- 将 developer-only 字段放入 Advanced Details。
- 所有业务事实只来自后端已有结构化状态。
- 所有展示文案来自 deterministic presentation template。
- LLM 不生成 issue presentation。
- CLI / UI 不做语义推断。
- 修复链路仍然通过 typed `RepairPatch`、用户确认、compiler replay verification 完成。

非目标：

- 不重新设计 `ArtifactSnapshot` persistence。
- 不改变 patch applier / verifier 的 authority model。
- 不允许 UI 从 `feedback_report.md`、`compile_report.txt` 或 `stage*.json` 读取信息。
- 不将 presentation text 作为 repair authority。
- 不要求 presentation DTO 持久化为 snapshot 的一部分。

## 3. 设计原则

### 3.1 用户默认看到业务问题

默认视图应回答：

- 这是哪类问题？
- 缺失的业务信息是什么？
- 影响是什么？
- 是否可以修？
- 可以怎么修？

默认视图不展示：

- `diagnostic_id`
- `target_ref`
- `irs_ref`
- `construct_id`
- `slot_name`
- `authority`
- grouping metadata

这些字段进入 Advanced Details。

### 3.2 后端提供 presentation，前端只渲染

正确数据流：

```text
ArtifactSnapshot
+ CompileDiagnostic metadata
+ EditableIssue
+ RepairCatalog
+ TargetResolver
+ RepairContextBuilder
+ source spans / traces
  -> IssuePresentationView
  -> CLI / UI render
```

禁止数据流：

```text
CompileDiagnostic
  -> CLI / UI 直接解释并拼接展示文案
```

Issue list 必须由后端按 section 组织，不能把一个 flat issue list 交给 CLI / UI 再由前端决定分区。默认至少区分：

- Editable issues
- Review needed
- Developer diagnostics

CLI / UI 可以选择是否显示某个 section，但不能自行决定 issue 属于哪个 section。

### 3.3 Presentation template 只翻译，不创造事实

展示文案可以是 deterministic template，例如：

- “The SPL has an exception flow for this condition, but no action to take.”
- “This output is declared, but no renderable step produces it.”
- “The compiler detected a possible delegated worker, but the handoff contract is incomplete.”

这些 template 只解释已有后端事实，不引入新的业务事实。

LLM 不生成 issue presentation。AI-assisted repair handler 可以生成 repair suggestion 的内容，但这些内容只能进入 suggestion presentation，不能反向写入 issue title、issue facts、missing items、category、repairability 或 source context。

### 3.4 `can_fix` 必须代表后端闭环可执行

如果一个问题显示为可修，必须同时满足：

- 有稳定 `EditableIssue`。
- 有 matching user-facing repair catalog entry。
- 有 handler / target resolver / context builder。
- 有 supported patch type。
- 生成的 suggestion 能进入 user confirmation。
- apply 后能走 verifier / compiler replay。

如果 diagnostic 标记为 `repairability=editable`，但无法映射为 `EditableIssue`，它不能进入默认用户问题列表。

### 3.5 区分 informational guidance 与 actionable repair

Presentation DTO 可以展示“建议如何处理”的说明，但必须区分两类信息：

- `suggested_resolution`：解释性或指导性文本，用于帮助用户理解可能的处理方向。
- `available_repairs`：可点击、可生成 suggestion、可进入 apply confirmation 的实际修复路径。

`suggested_resolution` 可以来自结构化 diagnostic、`EditableIssue`、RepairCatalog display metadata 或 deterministic template，但不能从 `feedback_report.md` 解析。它也不能自动变成可点击修复选项。

只有被 RepairCatalog 与 runtime registry 支持的 repair path 才能进入 `available_repairs`。

例如，若 suggested resolution 提到 “mark this exception as acknowledged without handling”，但当前没有对应 patch type，则它只能作为 informational guidance 展示，不能作为 `Fix with AI` 选项展示。

### 3.6 Repair availability 只能来自 RepairCatalog

Presentation template 不能成为第二套 repair truth source。

职责边界：

- RepairCatalog / runtime registry 决定有哪些 repair option 可用。
- Presentation template 只为已允许的 option 提供 label、impact、explanation、safety copy。
- Template 不声明支持哪些 patch type。
- Template 不选择 repair strategy。

因此：

```text
RepairCatalog = capability truth source
PresentationTemplateCatalog = display copy source
```

两者不能混合。

### 3.7 区分 repairability、can_fix 与 snapshot capability

Presentation 必须区分三层状态：

| 状态 | 含义 |
| --- | --- |
| `repairability` | issue 本身的语义可修复性，例如 editable / review-only / non-repairable |
| `can_fix` | 当前后端 flow 是否能为该 issue 提供 `Fix with AI` |
| snapshot editability | 当前 snapshot capability 是否允许对应修复和 verification |

示例：

```text
Issue semantically repairable
+ requires Lane B replay
+ snapshot lacks Lane B replay capability
=> repairability = editable
=> can_fix = false for Lane B-dependent option
=> detail view explains unavailable reason
```

这能避免 UI 把“理论可修”误展示成“当前可 apply”。

必须满足以下不变式：

```text
IssueCardView.can_fix is true
iff at least one RepairOptionView has availability = available.
```

如果所有 repair options 都不可用，则 issue card 不能显示 `Fix with AI`，只能显示 `View details`、`Review needed` 或对应的不可用说明。

同时：

```text
suggested_resolution is never used to determine RepairOptionView availability.
```

`suggested_resolution` 只能解释或提示，不参与判断某条 repair path 是否可执行。

### 3.8 Degraded presentation state

当用户可读字段缺失时，presentation 不应回退展示 compiler id。

例如：

- exception condition 不可得时，不应在标题里展示 `exc_adapter_00`。
- required output name 不可得时，不应在标题里展示 `rcd_output_s11`。

应使用 generic title，并标记为 degraded presentation。

示例：

```text
Exception has no handler
  Condition unavailable
```

或：

```text
Required output has no producer
  Output name unavailable
```

Raw target id 仍可放入 Advanced Details。

### 3.9 Advanced Details 默认属于 developer mode

Advanced Details 应默认隐藏，只在 developer mode、debug mode 或用户显式展开时展示。

默认用户流程不应要求用户理解 IRS、diagnostic id、construct id、slot name 或 repair metadata。

## 4. 输入来源

Issue Presentation DTO 只能从以下后端结构派生。

| 信息类别 | 允许来源 |
| --- | --- |
| run / snapshot identity | Snapshot identity |
| effective editability | Snapshot validation result / effective capabilities |
| issue grouping | EditableIssueExtractor output |
| raw diagnostic facts | CompileDiagnostic metadata |
| IRS boundary | `metadata["irs_ref"]` |
| repair affordance | RepairCatalog entry |
| target context | TargetResolver output |
| issue context | RepairContextBuilder output |
| source excerpt | source spans / traces |
| suggestion details | RepairSuggestion / patch previewer |
| apply effects | RepairPatch metadata |
| verification result | VerificationResult / verification artifacts |
| updated SPL | compiler replay rendered SPL |

Forbidden sources:

- `feedback_report.md`
- `compile_report.txt`
- `final_spl.txt` as repair authority
- `stage*.json` debug artifacts
- regex extraction from human-readable reports
- LLM-generated presentation text
- UI-side interpretation of `diagnostic.kind` alone

`CompileDiagnostic.message` may be displayed as fallback or Advanced Details, but should not be the primary source for user-facing issue facts when structured fields are available.

## 5. User-Facing Flow

The presentation layer supports this user flow:

```text
Run selection
-> Run summary
-> Grouped editable issue list
-> Issue detail
-> Repair suggestions
-> Apply confirmation
-> Verification result
-> Updated SPL
```

### 5.1 Run Selection

用户首先看到可编辑的 compile run，而不是 snapshot 文件路径。

Expected view:

```text
Available compile runs

[1] demo
    Snapshot: available
    Editable issues: 10
    Last version: base snapshot

[2] demo_capability_probe
    Snapshot: available
    Editable issues: 2
    Last version: base snapshot

Select run number:
```

路径信息属于 secondary / debug display。

### 5.2 Run Summary

选择 run 后，用户看到当前 snapshot 状态和 issue category summary。

Expected view:

```text
Run: demo
Snapshot: snap_5fcf0ce6a0fb
Version: base compile result

This SPL is partially complete.

Editable issues
  Exception handling: 6
  Required outputs without producers: 3
  Worker delegation contract gaps: 1

Select an issue to inspect or fix:
```

### 5.3 Grouped Editable Issue List

Issue list 以 `EditableIssue` 为单位，而不是 raw diagnostic 为单位。

Expected view:

```text
Editable issues

Exception handling

[1] Exception has no handler: Template unavailable
    The SPL has an exception flow for this condition, but no action to take.
    Fix with AI: Add handler step

[2] Exception has no handler: Communications lead unresponsive for over two days
    The SPL has an exception flow for this condition, but no action to take.
    Fix with AI: Add handler step

Required outputs

[7] Required output has no producer: draft_communication_artifact
    This output is declared, but no renderable step produces it.
    Fix with AI: Insert producer step / bind existing step

Worker delegation

[10] Worker delegation is underspecified
     The compiler detected a possible delegated worker, but the handoff contract is incomplete.
     Missing: input contract, output contract, invocation point, result handoff
     Fix with AI: create handoff / convert to main-flow step / ask user
```

### 5.4 Issue Detail

选择 issue 后，展示该 issue 的业务详情、缺失项、影响、可用修复选项，以及 Advanced Details。

Expected view:

```text
Issue [10]: Worker delegation is underspecified

What was detected:
  The compiler found a possible delegated worker, but it does not have enough
  contract information to safely render an INVOKE_WORKER step.

Missing information:
  - Input contract
  - Output contract
  - Invocation point
  - Result handoff

Why this matters:
  Without a complete handoff contract, the compiler cannot safely decide what
  the parent worker should pass to the child worker, when to invoke it, or how
  to bind the child result back.

Available fixes:
  [1] Create a worker handoff contract
      Use this if the task should become a separate worker.

  [2] Convert to main-flow step
      Use this if the action should stay inside the main worker.

  [3] Ask the user for missing information
      Use this if the missing contract details should be requested at runtime.

Advanced details:
  primary diagnostic: irs_235c6aad5e5b
  related diagnostics:
    irs_4d7dc95d4357
    irs_3eee831e90f3
    irs_40a561bc5259
  target: worker_promotion:del_s30
  construct: WORKER_PROMOTION
```

### 5.5 Repair Suggestions

Fix with AI 后展示 suggestion，而不是直接 apply。

Expected view:

```text
Repair suggestions

[1] Ask the user for an approved template
    Adds a REQUEST_INPUT handler inside this exception flow.

    Expected effect:
      - The exception flow will no longer be empty.
      - The handler step will be marked as user-confirmed repair evidence.

    Preview:
      [EXCEPTION_FLOW: Template unavailable]
        [SEQUENTIAL_BLOCK]
          COMMAND-X [INPUT DISPLAY Ask the user to provide an approved template VALUE approved_template:text SET]
        [END_SEQUENTIAL_BLOCK]
      [END_EXCEPTION_FLOW]

[2] Display a fallback message
    Adds a DISPLAY_MESSAGE handler.

[3] Record a manual fallback action
    Adds a GENERAL_COMMAND handler.
```

Preview 是 display-only。Apply authority 仍然是 typed patch。

### 5.6 Apply Confirmation

用户确认前，展示 apply 将做什么、不会做什么、将走哪条 verification lane。

Expected view:

```text
Apply suggestion [1]?

This will:
  - Add a REQUEST_INPUT step to exception flow “Template unavailable”.
  - Mark the new step as user-confirmed repair evidence.
  - Re-run compiler verification through Lane A.

This will not:
  - Modify final SPL text directly.
  - Bypass IRS, Gate, ProducerIndex, or Renderer.
  - Apply unconfirmed AI content.

Confirm apply? y/N
```

### 5.7 Verification Result

Apply 后展示 verification 结果与 updated SPL。

Expected view:

```text
Verification result: accepted

Resolved:
  - missing_handler: Template unavailable

No new blocking diagnostics.

Compiler authorities:
  IRS: passed
  Gate: new handler step is renderable
  Renderer: updated SPL produced

New snapshot:
  snapshot_id: snap_8a21c00d91ef
  overlay_version: 1

Updated SPL:
  [EXCEPTION_FLOW: Template unavailable]
    [SEQUENTIAL_BLOCK]
      COMMAND-X [INPUT DISPLAY Ask the user to provide an approved template VALUE approved_template:text SET]
    [END_SEQUENTIAL_BLOCK]
  [END_EXCEPTION_FLOW]
```

## 6. Presentation DTO Contract

This section defines logical DTO shape and field meaning. It does not prescribe implementation details.

### 6.1 RunPresentationView

Represents one compile run as a user-selectable editing target.

| Field | Meaning |
| --- | --- |
| run_id | Stable compile run identifier |
| run_label | Human-readable run label, usually run directory name |
| snapshot_id | Current snapshot identifier |
| overlay_version | Current overlay version |
| snapshot_status | Available / unavailable / invalid |
| editable | Whether SPL Editing can operate on this run |
| issue_count | Count of user-facing editable issues |
| issue_summary | Category-level issue counts |
| advanced | Debug-only run details |

### 6.2 IssueCategorySummary

Represents counts by user-facing category.

| Field | Meaning |
| --- | --- |
| category | Stable category key |
| label | Human-readable category label |
| count | Number of issues in that category |

Expected categories:

- Exception handling
- Required outputs
- Worker delegation
- Other editable issues

### 6.3 IssueListPresentationView

Represents all user-facing issues for one run.

| Field | Meaning |
| --- | --- |
| run_id | Compile run identifier |
| snapshot_id | Snapshot identifier |
| sections | Ordered issue sections |
| summary | Category summaries |

`IssueListPresentationView` must carry sectioned issue groups, not only a flat issue tuple. This prevents CLI / UI from becoming responsible for issue section semantics.

### 6.3.1 IssueSectionView

Represents one section in the issue list.

| Field | Meaning |
| --- | --- |
| section_key | Stable section key |
| label | User-facing section label |
| section_kind | Editable / review-needed / developer-diagnostics |
| items | Ordered issue cards in this section |
| visible_by_default | Whether the section appears in normal user mode |

Default semantics:

- Editable issues: visible by default, may expose `Fix with AI`.
- Review needed: visible separately, does not expose `Fix with AI`.
- Developer diagnostics: hidden by default, visible only in developer/debug mode.

### 6.4 IssueCardView

Represents one issue in the default list view.

| Field | Meaning |
| --- | --- |
| display_id | Sequential number displayed to the user |
| issue_id | Stable backend issue id |
| category | User-facing category |
| title | Short user-facing issue title |
| impact | One or two sentence impact text |
| fix_label | Short description of available repair |
| suggested_resolution | Optional informational guidance derived from structured backend state |
| source_excerpt | Optional source text excerpt |
| missing_items | User-readable missing items |
| repairability | User-facing repairability state |
| can_fix | Whether Fix with AI is available |
| presentation_quality | Complete or degraded presentation state |

### 6.5 IssueDetailPresentationView

Represents the selected issue.

| Field | Meaning |
| --- | --- |
| issue_id | Stable backend issue id |
| title | User-facing issue title |
| what_was_detected | Explanation of compiler finding |
| missing_items | User-readable missing items |
| why_it_matters | Impact of leaving issue unresolved |
| suggested_resolution | Optional informational guidance, not necessarily actionable |
| available_repairs | Repair options derived from catalog and supported patch types |
| source_context | Optional source excerpt or trace context |
| presentation_quality | Complete or degraded detail state |
| advanced | Developer details |

### 6.6 RepairOptionView

Represents one repair path exposed before suggestion generation.

| Field | Meaning |
| --- | --- |
| label | User-readable repair option label |
| description | When to choose this option |
| patch_types | Supported patch types behind this option |
| verification_lane | Expected verification lane |
| availability | Available / unavailable / review-only status |
| unavailable_reason | User-readable reason when the option cannot currently be used |

### 6.7 SuggestionPresentationView

Represents one generated repair suggestion.

| Field | Meaning |
| --- | --- |
| suggestion_id | Stable suggestion id within session |
| title | User-facing suggestion title |
| explanation | Human-readable explanation |
| expected_effect | Deterministic expected effects |
| risks | Known risks or caveats |
| preview | Display-only SPL-like preview |
| patch_type | Underlying typed patch type |

### 6.8 ApplyConfirmationView

Represents the final pre-apply confirmation.

| Field | Meaning |
| --- | --- |
| suggestion_id | Selected suggestion |
| title | Confirmation title |
| will_do | Effects of applying the patch |
| will_not_do | Safety boundaries |
| verification_lane | Lane A or Lane B |
| requires_user_confirmation | Always true for applying suggestions |

### 6.9 VerificationPresentationView

Represents the post-apply verification result.

| Field | Meaning |
| --- | --- |
| status | Accepted or rejected |
| resolved | User-readable resolved issues |
| new_blocking_diagnostics | User-readable new blocking diagnostics |
| authority_summary | IRS / Gate / ProducerIndex / Renderer result summary |
| new_snapshot_id | Overlay snapshot id, if available |
| overlay_version | Overlay version, if available |
| updated_spl | Updated rendered SPL, if available |

### 6.10 IssueAdvancedDetails

Developer-only details.

| Field | Meaning |
| --- | --- |
| primary_diagnostic_id | Primary diagnostic id |
| related_diagnostic_ids | Related diagnostic ids |
| diagnostic_kind | Diagnostic kind |
| target_ref | Raw target reference |
| irs_construct_type | IRS construct type |
| irs_construct_id | IRS construct id |
| irs_slot_name | IRS slot name |
| authority | Diagnostic source authority |
| repairability_metadata | Raw repairability metadata |

Advanced details must not be required for normal user decision-making.

## 7. Issue Category Rules

### 7.1 Exception Handling

Applies when an `EditableIssue` maps to missing handler repair for an exception flow.

User-facing title pattern:

```text
Exception has no handler: {condition_text}
```

Required user-facing facts:

- Exception condition or readable fallback label.
- Impact text explaining that the exception flow has no action.
- Fix label: Add handler step.

Preferred data sources:

1. Exception flow artifact condition.
2. Repair context condition / failure mode.
3. Source span excerpt.
4. Advanced fallback only: compiler target id.

The default view should not expose compiler-generated exception flow ids such as `exc_adapter_00`.

If the condition text is unavailable, the default title should degrade to a generic title such as `Exception has no handler`, with condition unavailable indicated separately. The compiler-generated target id remains Advanced-only.

If structured suggested resolution exists, it may be shown as informational guidance. It must not become an actionable repair option unless backed by a supported patch type.

### 7.2 Required Outputs

Applies when an `EditableIssue` maps to required output producer repair.

User-facing title pattern:

```text
Required output has no producer: {output_name}
```

Required user-facing facts:

- Output or resource name.
- Impact text explaining that the output is declared but not produced by a renderable step.
- Fix label: Insert producer step / bind existing step.

If a `missing_output_producer` diagnostic cannot be mapped to an `EditableIssue`, it must not appear in the default user-facing issue list.

If the output name is unavailable, the default title should degrade to a generic title such as `Required output has no producer`, with output name unavailable indicated separately. Compiler-generated resource contract ids remain Advanced-only.

### 7.3 Worker Delegation

Applies when grouped `type_or_contract_ambiguity` diagnostics map to worker promotion or handoff contract gaps.

User-facing title pattern:

```text
Worker delegation is underspecified
```

Required user-facing facts:

- Missing items derived from related diagnostic slot names.
- Impact text explaining incomplete handoff contract.
- Fix options derived from catalog:
  - Create handoff.
  - Convert to main-flow step.
  - Ask user / request input, when supported.

Related diagnostics for slots such as `promotion_input_contract`, `promotion_output_contract`, `promotion_invocation_point`, and `promotion_result_handoff` must be presented as one grouped issue.

If some repair options are unavailable because the snapshot lacks required capability, the detail view should show the option as unavailable with a reason, rather than silently implying it can be applied.

## 8. Deterministic Template Rules

Presentation templates are keyed by structured backend facts, not raw free text.

Recommended template key dimensions:

- construct type
- slot name
- diagnostic kind
- affordance id
- patch type, for suggestion / confirmation presentation

Templates may provide:

- category label
- title pattern
- impact text
- what-was-detected text
- why-it-matters text
- fix label
- repair option labels
- safety statements
- authority summary labels

Templates must not:

- invent source facts
- infer missing fields not present in backend state
- summarize source text with an LLM
- select repair strategy outside catalog affordances

Repair option availability is not a template concern. Templates may provide labels and explanatory copy only for options already authorized by RepairCatalog and the runtime registry.

## 9. Handling Unmapped or Incomplete Diagnostics

Presentation must distinguish user-facing repairable issues from developer diagnostics.

### 9.1 Fixable

An issue is fixable when it has:

- `EditableIssue`
- catalog affordance
- supported patch type
- target resolver
- context builder
- handler
- verification lane

These issues appear in the default issue list.

### 9.2 Review-only

A diagnostic may be shown as review-only when it carries useful user context but does not support automated repair.

Review-only items should appear in a separate `Review needed` section. They must not be mixed into the default `Editable issues` list, because that list carries the `Fix with AI` affordance.

Review-only items must not offer `Fix with AI`.

### 9.3 Developer-only

Diagnostics that are internally inconsistent, unmapped, or missing required repair contract metadata should be hidden from default user view and exposed only in Advanced / developer mode.

Example:

```text
repairability: editable
editable issue: not mapped
```

This is a backend contract problem, not a user-actionable issue.

### 9.4 Degraded

An issue may be user-facing but degraded when it is fixable or reviewable while missing ideal display context, such as condition text, source excerpt, or output name.

Degraded items may appear in user-facing sections, but must:

- use generic title text
- avoid compiler ids in default title
- expose missing display context explicitly
- preserve raw ids only in Advanced Details

### 9.5 Repair option availability states

Each repair option should have one of these semantic states:

- available
- unavailable because required snapshot capability is missing
- unavailable because handler / target resolver / context builder is missing
- unavailable because patch type is unsupported in this run
- review-only

This state explains why an issue may be semantically repairable but not currently actionable.

## 10. Suggestion and Apply Presentation

Suggestion presentation is downstream of issue presentation.

Rules:

- Suggestion preview is display-only.
- Apply authority remains the typed patch.
- User confirmation is mandatory before apply.
- Apply confirmation must state verification lane.
- Apply confirmation must state safety boundaries:
  - no direct final SPL text mutation
  - no bypassing compiler authorities
  - no unconfirmed AI content applied

Suggestion presentation may use:

- handler explanation
- patch type
- patch previewer output
- deterministic expected-effect templates
- deterministic risk labels

Suggestion presentation must not:

- claim verification success before verification runs
- hide patch type in developer/debug output
- replace user confirmation with implicit apply

## 11. Verification Presentation

Verification presentation converts `VerificationResult` into user-readable outcome.

Accepted result should show:

- accepted status
- resolved issues
- absence or presence of new blocking diagnostics
- compiler authority summary
- new snapshot identity / overlay version
- updated SPL

Rejected result should show:

- rejected status
- failure reasons
- unresolved issue
- new blocking diagnostics, if any
- no claim that SPL was fixed

Verification result must remain grounded in compiler replay artifacts and verifier output.

Baseline SPL display may use snapshot `final_spl` when present. Updated SPL display must use compiler replay rendered SPL from verification artifacts. Neither baseline nor updated SPL text may be parsed to infer repair state or issue semantics.

## 12. Security and Boundary Constraints

The presentation layer must preserve SPL Editing architecture boundaries:

- No report parsing.
- No stage debug JSON fallback.
- No final SPL text patching.
- No LLM-generated issue presentation.
- No frontend semantic inference.
- No dispatch based only on `diagnostic.kind`.
- No unconfirmed suggestion rendering as applied SPL.
- No bypass of IRS / Gate / ProducerIndex / Renderer verification.

## 13. Expected User Experience

The final CLI / UI experience should be:

```text
1. User selects a compile run.
2. User sees run summary and issue category counts.
3. User sees grouped, business-readable editable issues.
4. User selects one issue.
5. User sees issue details, missing information, impact, and repair options.
6. User requests suggestions.
7. User reviews suggestions and preview.
8. User confirms apply.
9. Backend applies typed patch.
10. Backend verifies through compiler authority.
11. User sees verification result and updated SPL.
```

The user should not need to understand IRS, diagnostic ids, construct ids, or repair metadata to operate SPL Editing.

## 14. Acceptance Criteria

This design is satisfied when:

- Default issue list renders `IssuePresentationView`, not raw `CompileDiagnostic`.
- Worker promotion related diagnostics appear as one grouped issue.
- Missing handler issues show human-readable exception condition when available.
- Output producer issues show output names when backend mapping is complete.
- Unmapped diagnostics do not appear as fixable user issues.
- Review-only diagnostics appear separately from editable issues.
- Degraded presentation never puts compiler-generated ids into default titles.
- Suggested resolution is presented as informational unless backed by a RepairCatalog option.
- Repair option availability is derived from catalog, runtime registry, and snapshot capabilities.
- Advanced Details preserve raw diagnostic / IRS fields.
- Advanced Details are hidden by default and shown only in developer/debug mode or explicit expansion.
- Suggestion list renders user-readable explanation, expected effect, and preview.
- Apply confirmation explains effects, safety boundaries, and verification lane.
- Verification result shows accepted/rejected status, resolved diagnostics, new blockers, snapshot overlay, and updated SPL.
- CLI / UI performs no report parsing, no stage debug JSON reads, and no semantic repair inference.

## 15. Open Design Questions

The following questions remain design-level decisions:

- Whether run selection should show only latest snapshot per run or allow explicit overlay version selection.
- Whether issue category labels should be localized in the presentation DTO or in a UI language layer.
- How much source excerpt should be included by default before it becomes noisy.
- Whether degraded presentation should block `Fix with AI` for specific issue categories, or allow repair with a visible warning.

These decisions do not affect the core requirement: user-facing issue presentation must be backend-derived and distinct from raw diagnostic rendering.
