# SPL Editing Issue Presentation 实施计划

状态：实施计划草案  
来源设计：[spl_editing_issue_presentation_design.md](../design/spl_editing_issue_presentation_design.md)  
目标产物：后端-owned Issue Presentation DTO 层，供 CLI / UI 直接渲染用户可理解的 SPL Editing 问题视图。

## 0. 目标

本计划描述如何在 SPL Editing 后端新增 Issue Presentation 层，将现有结构化状态：

```text
ArtifactSnapshot
+ CompileDiagnostic metadata
+ EditableIssue
+ RepairCatalog
+ TargetResolver
+ RepairContextBuilder
+ source spans / traces
+ RepairSuggestion / RepairPatch
+ VerificationResult
```

转换为：

```text
RunPresentationView
IssueListPresentationView
IssueCardView
IssueDetailPresentationView
SuggestionPresentationView
ApplyConfirmationView
VerificationPresentationView
```

从而让 CLI / UI 展示：

```text
Run summary
-> grouped editable issue list
-> issue detail
-> repair suggestions
-> apply confirmation
-> verification result
-> updated SPL
```

而不是直接展示 raw `CompileDiagnostic` / IRS metadata dump。

## 1. 非目标

本阶段不做：

- 重新设计 `ArtifactSnapshot` persistence；
- 修改 patch applier / verifier authority model；
- 将 presentation DTO 持久化进 canonical snapshot；
- 从 `feedback_report.md`、`compile_report.txt`、`final_spl.txt` 或 `stage*.json` 解析 presentation 信息；
- 让 LLM 生成 issue presentation；
- 让 CLI / UI 根据 `diagnostic.kind`、`target_ref` 或 `irs_ref` 自行推断业务含义；
- 新增新的 repair capability；
- 修复所有 existing diagnostics mapping 问题。

其中 `missing_output_producer` 的 `RESOURCE_CONTRACT_DEMAND.producer` 映射问题可以在本计划中被识别和隔离，但是否扩展其 repair support 是独立任务。

## 2. 核心约束

实施时必须保持以下约束：

- 默认用户视图只渲染 presentation DTO，不渲染 raw diagnostics。
- `EditableIssue` 是用户可行动 issue 的基本单位。
- `RepairCatalog` / runtime registry 是 repair availability 的唯一 truth source。
- Presentation template 只提供 display copy，不声明或选择 repair capability。
- `suggested_resolution` 是 informational guidance，不是 repair authority。
- `IssueCardView.can_fix` 必须等价于“至少一个 repair option available”。
- Review-only 项进入独立 `Review needed` section，不混入 `Editable issues`。
- Developer-only / unmapped diagnostic 只进入 developer diagnostics。
- Degraded presentation 不得把 compiler-generated id 放入默认标题。
- Advanced Details 默认隐藏，只在 developer/debug mode 或显式展开时显示。

## 3. 总体阶段划分

推荐按以下阶段实施：

```text
P-1 Presentation Contract Freeze
P0 Presentation Model
P1 Template Catalog
P2 Issue Presentation Builder
P3 Run Presentation Builder
P4 Suggestion / Apply / Verification Presentation
P5 Service API Integration
P6 CLI Demo Replacement
P7 State Matrix Hardening
P8 End-to-End Regression
P9 Documentation / Final Audit
```

不要从改 CLI 输出开始。CLI 应作为 presentation DTO 的消费者，而不是规则承载者。

## 3.1 目标模块结构

Presentation DTO 层属于 SPL Editing service 的展示投影层，应放在 `spl_editing` 后端内部，而不是 compiler artifact snapshot 模块中。

推荐结构：

```text
src/nl2spl/compiler/spl_editing/presentation/
  __init__.py

  contract/
    __init__.py
    categories.py
    sections.py
    availability.py
    quality.py
    modes.py
    invariants.py

  model/
    __init__.py
    run.py
    issue.py
    suggestion.py
    confirmation.py
    verification.py
    advanced.py
    sections.py

  templates/
    __init__.py
    catalog.py
    keys.py
    issue_copy.py
    repair_option_copy.py
    suggestion_copy.py
    confirmation_copy.py
    verification_copy.py
    unavailable_reasons.py

  resolvers/
    __init__.py
    display_context.py
    suggested_resolution.py
    repair_options.py
    source_excerpt.py
    advanced_details.py

  issue_presenters/
    __init__.py
    base.py
    exception_handling.py
    required_outputs.py
    worker_delegation.py
    generic.py
    review_only.py
    developer_only.py

  builders/
    __init__.py
    run_builder.py
    issue_builder.py
    section_builder.py
    suggestion_builder.py
    confirmation_builder.py
    verification_builder.py

  service.py
  errors.py
```

该结构的目的不是增加层数，而是防止以下劣化：

- `presentation.py` 成为巨型文件；
- `IssuePresentationBuilder` 同时取事实、判断能力、拼文案、组织流程；
- template catalog 变成第二套 RepairCatalog；
- CLI 继续根据 raw diagnostic / IRS metadata 做语义判断。

## 3.2 六层职责边界

### contract

只放稳定枚举、section key、category key、availability、quality、mode 和 invariant。

禁止：

- import `EditableIssue` / `RepairCatalog` / `ArtifactSnapshot`；
- 编写业务判断；
- 读取 diagnostics 或 snapshot。

### model

只定义 frozen presentation DTO。

禁止：

- 持有 runtime service object；
- 直接持有 raw `CompileDiagnostic`；
- 做 section 分类或 repair availability 判断。

### templates

只提供 display copy。

允许：

- category label；
- issue title / impact / why-it-matters copy；
- repair option label / description；
- suggestion / confirmation / verification copy；
- unavailable reason copy。

禁止：

- 声明 supported patch type；
- 决定 repair option availability；
- 选择 repair strategy；
- 根据 diagnostic kind 单字段决定 repair capability。

### resolvers

只从已允许的后端结构中解析 display facts 和 option availability。

典型职责：

- display context；
- source excerpt；
- suggested resolution；
- repair option availability；
- advanced details projection。

约束：

- `repair_options` 可以查询 RepairCatalog / runtime registry / snapshot capabilities；
- `repair_options` 不能凭 `suggested_resolution` 或 raw message 决定 availability；
- `suggested_resolution` resolver 只产出 informational guidance。
- Presentation resolvers must not parse `CompileDiagnostic.message` to extract primary display facts such as condition text, output name, source target, missing slot, or repair strategy. `CompileDiagnostic.message` may only be copied into fallback display or Advanced Details.

### issue_presenters

按 issue family 生成 card/detail，不做全局编排。

MVP presenters：

- Exception handling；
- Required outputs；
- Worker delegation；
- Generic degraded fallback；
- Review-only；
- Developer-only。

### builders / service / CLI renderer

Builders 负责编排 presentation DTO，不承载具体 family 规则。

Presentation service 是 CLI / UI 的窄 facade。

CLI 是 renderer，只消费 presentation DTO，不访问 raw diagnostics、IRS metadata、context builder 或 RepairCatalog。

## 4. P-1 Presentation Contract Freeze

### 目标

冻结 presentation 层的 contract 常量、枚举和不变式，避免后续实现阶段散落硬编码字符串。

### 内容

需要冻结的概念：

- issue category keys；
- presentation quality；
- repair option availability；
- presentation sections；
- developer mode / advanced details 策略；
- `can_fix` invariant；
- `suggested_resolution` invariant；
- review-only section 策略。

### 验收

- 所有后续测试引用 contract 常量 / 枚举，不重复硬编码同名字符串。
- `can_fix` 和 repair option availability 的关系有明确 contract 测试。
- `suggested_resolution` 不参与 repair option availability 的关系有 contract 测试。
- `contract/` 不 import SPL Editing runtime model、snapshot model 或 RepairCatalog。

## 5. P0 Presentation Model

### 目标

建立 backend-owned neutral DTO，作为 CLI / UI 的唯一展示输入。

### DTO 范围

应覆盖：

- `RunPresentationView`
- `IssueCategorySummary`
- `IssueListPresentationView`
- `IssueSectionView`
- `IssueCardView`
- `IssueDetailPresentationView`
- `RepairOptionView`
- `SuggestionPresentationView`
- `ApplyConfirmationView`
- `VerificationPresentationView`
- `IssueAdvancedDetails`
- `RunAdvancedDetails`

### 设计要求

- DTO 不持有 runtime service object。
- DTO 不直接持有 raw `CompileDiagnostic` 对象。
- Advanced details 可以持有 raw ids 和 metadata 的稳定 projection。
- DTO 字段应表达 presentation 语义，而不是 compiler internal object graph。
- `IssueListPresentationView` 必须携带 sectioned issue groups，而不是 flat issue tuple。
- `Developer diagnostics` section 默认隐藏，只通过 developer/debug mode 或显式展开显示。

### 验收

- DTO frozen / immutable。
- `IssueCardView.can_fix` 与 repair option availability 可以被校验。
- Advanced details 与 default display 字段分离。
- Editable / review-needed / developer-diagnostics section 语义由 DTO 表达，不由 CLI 推断。
- DTO 模块不 import CLI / UI。
- DTO 模块不 import LLM adapter。
- DTO 模块不 import `CompileDiagnostic`。

## 6. P1 Template Catalog

### 目标

建立 deterministic display copy 来源，用于将 backend facts 转换为用户可理解的文案。

### 职责

Template catalog 可提供：

- category label；
- title pattern；
- impact text；
- what-was-detected text；
- why-it-matters text；
- fix label；
- repair option label；
- safety statement；
- authority summary label；
- unavailable reason label。

### 边界

Template catalog 不得：

- 决定 repair option 是否可用；
- 声明支持哪些 patch type；
- 根据 diagnostic kind 单字段选择 repair strategy；
- 从 diagnostic message 中抽取业务事实；
- 调用 LLM。

### 验收

- 对每个 MVP issue family 均有 deterministic template。
- Template 对 unknown category 有 degraded / generic 文案。
- Template 不包含可用 patch type 的 truth source。
- Template 与 RepairCatalog 的职责边界有测试保护。
- Template 模块不包含 `supported_patch_types`、`verification_lane` 或 handler id truth source。
- Template catalog 不集中成一个承载全部文案和规则的巨型 dict。

## 7. P2 Issue Presentation Builder

### 目标

将 `EditableIssue` 转换为 `IssueCardView` 和 `IssueDetailPresentationView`。

### 输入

允许输入：

- `EditableIssue`
- current `ArtifactSnapshot`
- related `CompileDiagnostic` projection
- `RepairCatalog`
- target resolver output
- repair context output
- source spans / traces
- effective snapshot capabilities

### 输出

- default issue card；
- selected issue detail；
- advanced details；
- repair options with availability；
- suggested resolution as informational guidance；
- degraded state if human-readable display facts are missing。

### 分类策略

MVP issue families：

1. Exception handling
2. Required outputs
3. Worker delegation

Fallback：

- Review-only
- Developer-only
- Degraded generic issue

### Presenter 拆分原则

`IssuePresentationBuilder` 只负责编排，不应承载所有 issue family 的具体展示规则。

设计上应保持以下职责分离：

- Exception handling presenter：处理 missing handler。
- Required output presenter：处理 missing output producer。
- Worker delegation presenter：处理 worker promotion / handoff contract gaps。
- Generic presenter：处理 degraded / review-only / fallback display。

这可以防止 P2 演化成单一巨大 builder，也能让每类 issue 的 data-source 和 degraded 策略单独被测试。

### 验收

- Builder 不接收或读取 report files。
- Builder 不读取 stage debug JSON。
- Builder 不调用 LLM。
- Builder 不成为单一巨大 if/else 规则容器。
- 每个 MVP issue family 有独立 presenter 级测试。
- Resolvers 集中处理 display context、source excerpt、suggested resolution、repair option availability、advanced details。
- Resolvers 不解析 `CompileDiagnostic.message` 来提取 primary display facts。
- Family presenter 不直接决定 repair availability；它只消费 repair option resolver 的结果。
- Builder 不让 CLI / UI 参与语义推断。
- Worker promotion 多条 related diagnostics 合并成一个 issue view。
- Missing handler 默认标题不显示 `exc_*` id。
- Missing output producer unmapped diagnostic 不进入 editable issue list。
- Degraded title 不显示 compiler-generated id。

## 8. P3 Run Presentation Builder

### 目标

为 run selection 和 run summary 提供 presentation DTO。

### 输入

允许输入：

- run id / run label；
- loaded snapshot identity；
- snapshot validation result / effective capabilities；
- issue presentation summary；
- current snapshot / overlay identity；
- optional path for debug display。

### 输出

- `RunPresentationView`
- issue category summary
- snapshot availability / editability
- base / overlay version label
- advanced run details

### MVP 语义

MVP 默认显示每个 run 的 latest snapshot。  
Developer mode 可以在后续支持 base / overlay 显式选择。

### 验收

- Run selection 默认不暴露完整 path。
- Path 只进入 secondary / advanced display。
- Editable issue count 来自 `EditableIssueExtractor` / issue presentation summary，不来自 raw diagnostic count。
- Run editability 来自 snapshot validation / effective capabilities。

## 9. P4 Suggestion / Apply / Verification Presentation

### 目标

将 suggestion、confirmation、verification 三个后续步骤也纳入 presentation DTO，而不是让 CLI 自己拼接输出。

### Suggestion Presentation

输入：

- `RepairSuggestion`
- patch previewer output
- deterministic expected-effect template
- deterministic risk labels

输出：

- suggestion title
- explanation
- expected effect
- risks
- display-only preview
- patch type for advanced/debug display

约束：

- preview 不作为 apply authority。
- 不声称 verification 成功。
- 不隐藏 patch type。
- AI-generated suggestion explanation 可以显示在 suggestion presentation 中。
- AI-generated suggestion explanation 不得反向写入 issue facts、issue category、missing items、source context、repairability 或 `available_repairs`。

### Apply Confirmation Presentation

输入：

- selected suggestion
- typed patch
- verification lane
- patch-specific deterministic safety copy

输出：

- will-do list
- will-not-do list
- verification lane
- user confirmation prompt semantics

约束：

- 必须说明不会直接修改 final SPL text。
- 必须说明不会绕过 compiler authorities。
- 必须说明未确认 suggestion 不会 apply。

### Verification Presentation

输入：

- `VerificationResult`
- verification artifacts
- latest overlay snapshot identity
- rendered SPL from replay

输出：

- accepted / rejected
- resolved issues
- new blocking diagnostics
- authority summary
- new snapshot id / overlay version
- updated SPL

约束：

- baseline SPL 可来自 snapshot final_spl 展示。
- updated SPL 必须来自 replay rendered SPL。
- SPL text 不用于推断 repair state。

### 验收

- Suggestion / confirmation / verification 输出不由 CLI 自行解释 runtime object。
- Rejected verification 不显示修复成功。
- Accepted verification 显示 resolved issue 和 updated SPL。

## 10. P5 Service API Integration

### 目标

让 SPL Editing service 暴露 presentation 级 API，使 CLI / UI 不再直接调用 raw issue / diagnostic rendering。

### API 语义

需要覆盖：

- list runs as presentation；
- load / register run and get run presentation；
- list issue presentations；
- get issue detail presentation；
- generate suggestions and get suggestion presentations；
- get apply confirmation presentation；
- apply suggestion；
- verify session and get verification presentation。

### 边界

- service API 可返回 presentation DTO。
- service API 仍可保留低层 API 给 tests / internal use。
- CLI / UI 默认只使用 presentation API。
- Developer diagnostics 通过显式 developer presentation API 或 developer mode 暴露，不进入默认 issue list API。

### 验收

- CLI 不需要访问 `CompileDiagnostic`。
- CLI 不需要访问 `irs_ref`。
- CLI 不需要调用 context builder。
- CLI 不需要解析 diagnostic message。
- CLI 不需要访问 RepairCatalog。

## 11. P6 CLI Demo Replacement

### 目标

将当前 direct-run demo 从 raw diagnostics console 改为 presentation-driven flow。

### 目标流程

```text
Available compile runs
-> select run
-> Run summary
-> Editable issues / Review needed
-> select issue
-> Issue detail
-> Generate suggestions
-> select suggestion
-> Apply confirmation
-> confirm apply
-> Verification result
-> Updated SPL
```

### 输出要求

- 默认不展示 diagnostic id。
- 默认不展示 target ref。
- 默认不展示 IRS construct id。
- Advanced details 仅 developer/debug mode 或显式展开。
- `Editable issues`、`Review needed`、`Developer diagnostics` 由 presentation DTO section 渲染。
- CLI 不自行根据 issue fields 决定 section。
- Unmapped developer diagnostics 不进入默认 view。

### 验收

- 运行 demo 不再显示 `IRS diagnostics` 作为主标题。
- Worker promotion 4 条 raw diagnostic 显示为 1 个 delegation issue。
- Missing handler 显示 human-readable condition 或 degraded generic title。
- Unmapped `missing_output_producer` 不显示为 fixable。
- 选择 issue 后展示 detail / repair options。
- suggestion / confirmation / verification 均来自 presentation DTO。
- CLI 源码边界测试禁止 import `CompileDiagnostic` / `DiagnosticIRSRef` / `RepairCatalog`。

## 12. P7 State Matrix Hardening

### 目标

系统性覆盖 presentation 状态矩阵，防止 UX contract 漂移。

### 必测状态

Issue-level：

- fixable
- review-only
- developer-only
- degraded but fixable
- degraded and not fixable
- semantically editable but capability unavailable
- suggested_resolution informational only
- suggested_resolution backed by actionable repair option

Repair option：

- available
- unavailable due to snapshot capability
- unavailable due to missing handler / target resolver / context builder
- unavailable due to unsupported patch type
- review-only

Run-level：

- snapshot available
- snapshot invalid
- no editable issues
- only review-needed items
- latest overlay selected
- base snapshot selected in developer mode

### 验收

- `can_fix = exists(available repair option)` is enforced.
- `suggested_resolution` never determines availability.
- Review-only never offers Fix with AI.
- Developer-only diagnostics never appear in default issue list.
- Degraded default titles never use compiler-generated ids.
- Degraded state does not automatically block Fix with AI, but issue-family presenters may downgrade specific repair options.
- If all repair options are unavailable, `can_fix` is false and the card does not show Fix with AI.

## 13. P8 End-to-End Regression

### 目标

验证 presentation layer 不破坏现有 SPL Editing authority chain。

### E2E 覆盖

至少覆盖：

- missing_handler：issue list -> detail -> suggestion -> confirmation -> apply -> Lane A verify accepted。
- missing_output_producer：mapped issue path 或 review/developer isolation path。
- worker delegation：grouped issue -> detail -> suggestion -> apply -> Lane B verify accepted。
- rejected verification path。
- snapshot capability unavailable path。
- degraded presentation path。
- developer diagnostics section hidden by default path。

### 验收

- Presentation E2E 不读取 report / stage debug JSON。
- Apply 仍然通过 typed patch。
- Verification 仍然通过 Lane A / Lane B replay。
- Updated SPL 仍然来自 replay rendered SPL。
- CLI E2E proves issue sections come from presentation DTO.

## 13.1 推荐测试结构

推荐测试分层：

```text
tests/unit/compiler/spl_editing/presentation/
  test_contract_invariants.py
  test_model_dto_boundaries.py
  test_template_catalog_boundaries.py

  test_exception_handling_presenter.py
  test_required_output_presenter.py
  test_worker_delegation_presenter.py
  test_review_developer_degraded_presenters.py

  test_repair_option_resolver.py
  test_suggested_resolution_resolver.py
  test_section_builder.py
  test_run_presentation_builder.py
  test_suggestion_confirmation_verification_presentation.py

tests/unit/compiler/spl_editing/
  test_presentation_service_api.py
  test_cli_uses_presentation_api.py

tests/integration/compiler/spl_editing/
  test_presentation_e2e_missing_handler.py
  test_presentation_e2e_missing_output_producer.py
  test_presentation_e2e_worker_delegation.py
```

测试重点不是锁死文案逐字内容，而是锁住边界与不变式：

- `can_fix = exists(available repair option)`；
- `suggested_resolution` 不影响 availability；
- Review-only 不出现 `Fix with AI`；
- Developer-only 不进默认 issue list；
- Degraded title 不出现 compiler id；
- Template 不声明 supported patch type；
- CLI 不 import raw diagnostic 类型；
- Verification output 来自 replay artifact。

## 14. P9 Documentation / Final Audit

### 目标

更新用户和开发者文档，明确 presentation DTO 层的职责与边界。

### 文档更新

需要记录：

- presentation DTO flow；
- CLI demo usage；
- Advanced Details / developer mode；
- review-only vs editable；
- degraded presentation；
- suggested_resolution vs available_repairs；
- `can_fix` invariant；
- no report parsing boundary。

### Final Audit

审计清单：

- CLI 是否仍直接打印 raw diagnostic。
- UI / CLI 是否解释 `irs_ref`。
- Template 是否声明 repair capability。
- `suggested_resolution` 是否影响 availability。
- Review-only 是否混入 editable issue list。
- Advanced Details 是否默认显示。
- Degraded title 是否暴露 compiler id。
- Verification output 是否来自 replay artifacts。

## 15. 风险与防线

### 风险 1：Presentation 变成第二套 RepairCatalog

防线：

- Repair availability only from RepairCatalog / runtime registry。
- Template 只提供 copy。
- 测试禁止 template 声明 supported patch type。
- Template 不包含 verification lane / handler id / patch support truth source。

### 风险 2：CLI 继续做语义推断

防线：

- CLI 只消费 presentation DTO。
- CLI 不访问 `CompileDiagnostic` / `irs_ref`。
- CLI 测试检查源码边界。
- CLI 不访问 RepairCatalog / TargetResolver / context builder。

### 风险 3：Degraded 状态掩盖后端上下文缺失

防线：

- 明确 `presentation_quality`。
- default title 不放 compiler id。
- detail view 明示 missing display context。

### 风险 4：Suggested resolution 被误当 repair authority

防线：

- `suggested_resolution` 不参与 `available_repairs`。
- unsupported suggested action 只能 informational。
- confirmation 只针对 typed patch。

### 风险 5：Unmapped editable diagnostic 进入用户默认列表

防线：

- 默认 issue list 只来自 `EditableIssue`。
- unmatched diagnostics 进入 developer diagnostics。
- `repairability=editable but not mapped` 作为 contract warning。

### 风险 6：巨型 IssuePresentationBuilder

防线：

- Top-level builder 只编排。
- Issue family 逻辑拆入 dedicated presenters。
- Display facts 和 availability 由 resolvers 提供。
- 测试按 presenter family 拆分。

### 风险 7：巨型 template dict

防线：

- Template 按 issue copy、repair option copy、suggestion copy、confirmation copy、verification copy、unavailable reason 拆分。
- Template 只保存 copy，不保存 capability。
- Template 边界测试检查 forbidden fields。

## 16. 阶段完成定义

本计划完成时应满足：

- Direct-run demo 不再展示 raw `IRS diagnostics` 主视图。
- 用户看到 grouped editable issue list。
- Worker delegation 相关 diagnostics 被合并为一个 issue。
- Missing handler 展示 condition 或 degraded generic title。
- Missing output producer 不再出现 `editable_issue = not mapped` 的用户可修复项。
- Review-only 和 developer-only 有独立展示策略。
- Suggestion、apply confirmation、verification 都有 presentation DTO。
- CLI / UI 无需读取 raw diagnostic / IRS metadata 即可完成用户流程。
- 现有 typed patch apply 与 Lane A / Lane B verification 权威链路不变。

## 17. Delivery Status / Final Audit

状态：Presentation DTO backend projection layer implemented.

已交付：

- `src/nl2spl/compiler/spl_editing/presentation/contract/`
  - category、section、availability、quality、mode、invariant contract。
- `src/nl2spl/compiler/spl_editing/presentation/model/`
  - Run、issue list、section、card、detail、suggestion、confirmation、verification、advanced DTO。
- `src/nl2spl/compiler/spl_editing/presentation/templates/`
  - issue copy、repair option copy、suggestion copy、confirmation copy、verification copy、unavailable reason copy。
- `src/nl2spl/compiler/spl_editing/presentation/resolvers/`
  - display context、source excerpt、suggested resolution、repair option availability、advanced details。
- `src/nl2spl/compiler/spl_editing/presentation/issue_presenters/`
  - exception handling、required outputs、worker delegation、generic、review-only、developer-only presenters。
- `src/nl2spl/compiler/spl_editing/presentation/builders/`
  - issue list/detail、section、run、suggestion、confirmation、verification builders。
- `src/nl2spl/compiler/spl_editing/presentation/service.py`
  - CLI / UI facing presentation facade。
- `examples/output/spl_editing_demo/run_demo.py`
  - direct-run demo 改为 presentation DTO renderer。

审计结果：

- CLI 不再显示 `IRS diagnostics` 作为主视图。
- CLI 默认不打印 diagnostic id、target ref、IRS construct id / slot。
- CLI 不 import `CompileDiagnostic`、`DiagnosticIRSRef`、`RepairCatalog`。
- Issue list 由 `IssueListPresentationView.sections` 驱动，不由 CLI 自行分区。
- Worker promotion related diagnostics 以 grouped issue presentation 展示。
- Missing handler title 优先来自 structured exception flow artifact condition；缺失时降级为 generic title，不展示 compiler id。
- `suggested_resolution` 只作为 informational guidance，不参与 repair option availability。
- `IssueCardView.can_fix` 由 available repair option 推导。
- Template modules 不 import RepairCatalog，不声明 `supported_patch_types` / handler id truth source。
- Presentation resolvers 不解析 `CompileDiagnostic.message` 来提取 primary display facts。
- Suggestion、apply confirmation、verification 输出均通过 presentation DTO。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m ruff check src\nl2spl\compiler\spl_editing\presentation examples\output\spl_editing_demo\run_demo.py tests\unit\compiler\spl_editing\presentation
.\.venv\Scripts\python.exe -m pytest tests\unit\compiler\spl_editing\presentation -q --basetemp .\.tmp_pytest
.\.venv\Scripts\python.exe -m pytest tests\unit\compiler\spl_editing tests\integration\compiler\spl_editing -q --basetemp .\.tmp_pytest
```

当前验证结果：

- Presentation focused tests: 12 passed。
- SPL Editing unit + integration: 477 passed。
- Ruff: clean。

备注：

- 全量仓库 `pytest` 当前仍有与本次 presentation 层无直接关系的既有失败，集中在 annotation role contract 与 resource contract baseline/demo output expectations。
