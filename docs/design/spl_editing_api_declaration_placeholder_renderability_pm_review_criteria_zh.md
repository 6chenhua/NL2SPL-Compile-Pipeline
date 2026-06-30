# SPL Editing API Declaration Placeholder Renderability 严格 PM 审核准则

本文档用于逐阶段审核以下实施计划：

- docs/design/spl_editing_api_declaration_placeholder_renderability_implementation_plan_zh.md

本文档不是新的实现方案，不改变原计划的 authority、阶段顺序或范围。它把原计划转换成可执行的 PM 门禁，回答：

- 每个阶段开始前必须具备什么；
- 实施者必须提交什么证据；
- PM 必须亲自检查什么；
- 哪些情况直接拒绝；
- 哪些阶段完成后才允许进入后续阶段；
- 最终 E2E 如何证明真实行为闭环。

---

## 1. 审核目标

审核的核心不是确认 API declaration 或 CALL_API 能否输出，而是确认以下状态和 authority 已被正确分离：

    NL2SPL structural renderability
      != downstream API contract validity

    API_DECLARATION construct completeness
      != PipelineResult completeness

    diagnostic visibility
      != repair capability

    review_only / deferred_validation
      != editable

最终允许同时成立：

    API_DECLARATION completeness = partial
    IRS renderable = true
    PipelineResult completeness = complete
    API contract validation status = pending

前提是不存在其他 blocks_completion diagnostics。

---

## 2. 本准则冻结的设计决策

### 2.1 Deferred diagnostic contract

本准则固定：

| 字段 | 值 |
| --- | --- |
| diagnostic kind | deferred_api_contract_validation |
| severity | info |
| blocks_rendering | false |
| blocks_completion | false |
| repairability | review_only |
| presentation disposition | deferred_validation |
| validation authority | downstream_spl_compiler |
| allowed target | api |

实施者不得在阶段内将 severity 改为 warning。若认为必须调整，需先提交独立设计决策，不得在代码中临时改变。

### 2.2 Placeholder 状态语义

| 状态 | NL2SPL 含义 | 是否表示外部 API 已验证 |
| --- | --- | --- |
| unknown_placeholder | grammar-safe，占位内容仍需下游验证 | 否 |
| known_empty | 权威输入明确为空 | 否 |
| known_present | NL2SPL artifact 中存在内容 | 否 |
| malformed | 结构非法，必须在 NL2SPL fail closed | 否 |

仅凭 SPL 文本中的空对象或空 functions，不能精确区分 unknown_placeholder 与 known_empty。文本消费者必须继续执行下游验证。

### 2.3 Repair capability

API_DECLARATION.functions 和 API_DECLARATION.openapi_schema 在 AP0-AP7 中必须保持：

    repair_affordances = ()

它们不得显示 Fix with AI，不得进入 Editable issues，不得生成 handler、patch、prompt 或 materialization strategy。

### 2.4 Issue grouping

合法 placeholder 产生的 functions/schema deferred diagnostics 必须按稳定 API construct identity 聚合成一个 issue。

Malformed schema、missing API identity、missing source evidence 等 structural diagnostics不得混入 deferred group。

---

## 3. PM 判定等级

### 3.1 PASS

只有同时满足以下条件才可判定 PASS：

1. 本阶段全部准入条件满足。
2. 全部必交付物存在。
3. 全部正向、负向和边界测试通过。
4. PM 已亲自核对真实 artifact 或真实运行行为。
5. 没有 P0/P1 finding。
6. 没有新增 skip、xfail、弱断言或无条件 fallback。
7. 没有超出允许修改范围的无关改动。
8. 阶段退出条件全部满足。

PASS 才允许自动解锁依赖该阶段的后续阶段。

### 3.2 CONDITIONAL_PASS

仅允许用于：

- 不影响当前阶段核心语义的 P2；
- 已明确 owner、issue、到期时间的非核心清理项；
- 外部环境导致但已有独立证据覆盖的非功能问题。

CONDITIONAL_PASS 默认不能解锁下游阶段。PM 必须明确写出：

    allowed_to_start_next_phase = true | false

不得用 conditional pass 掩盖缺少负向测试、缺少真实 E2E、authority 不清或状态模型不闭合。

### 3.3 FAIL

出现任一 P0/P1、证据不完整、测试仅覆盖 mock 路径、阶段越界或真实行为与计划不符时，判定 FAIL。

### 3.4 BLOCKED

前置阶段未 PASS、关键设计决策未冻结或真实测试环境不可用时，判定 BLOCKED。BLOCKED 不是 PASS，不得合并依赖它的生产变更。

---

## 4. Finding 严重度

### P0：语义或 authority 破坏

包括但不限于：

- placeholder 被当成真实 API contract；
- malformed API 被放行；
- unknown_placeholder 自动升级为 known_empty/known_present；
- 仅按 diagnostic kind 标记 editable；
- functions/schema 增加 mandatory repair affordance；
- API deferred issue 进入 apply flow；
- Stage 7、Gate 或 Renderer 要求 semantic complete；
- CALL_API 被降级为 GENERAL_COMMAND；
- 通过 diagnostic.message、feedback report 或 final SPL 反向推断事实；
- NL2SPL 调用外部 API validator、网络 probe 或 credential validation；
- 只有 deferred API diagnostic 时 PipelineResult 仍被置为 partial；
- preview、report 或 CLI 自行构造不来自结构化后端的 API issue。

P0 必须修复后重新审核，不允许 waiver。

### P1：阶段闭环缺失

包括但不限于：

- 缺少计划规定的正向或负向测试；
- projector metadata 未完整 round-trip；
- group primary/alias 不稳定；
- IssueInventory 仍只覆盖 editable；
- deferred item 被过滤后静默消失；
- run summary count 语义改变；
- snapshot 未保留 handoff 状态；
- 仅有单元测试，没有阶段要求的真实集成证据；
- compatibility shim 无移除阶段；
- 允许修改范围外存在功能性变更；
- severity 未按本准则固定为 info。

P1 必须修复，原则上不允许进入下一阶段。

### P2：非阻断质量问题

例如局部命名、缺少非关键说明、可读性问题。P2 不得涉及行为、authority、状态或测试完整性。

---

## 5. 证据优先级

PM 按以下优先级接受证据：

1. 真实 Pipeline 执行产出的结构化 artifact。
2. 真实 snapshot round-trip。
3. 真实 Presentation Service DTO。
4. 真实 run_demo.py 交互输出。
5. 真实 final SPL。
6. 集成测试。
7. 单元测试。
8. 静态扫描。
9. 实施者说明。

低优先级证据不能替代高优先级证据。例如：

- final SPL 存在 CALL 不能证明 PipelineResult completeness 正确；
- CLI 截图不能证明 IssueInventory 正确；
- 测试总数不能证明测试走过真实 Stage 6/7；
- mock APISpec 不能证明 Stage 6 materialization 正确；
- presentation 文案正确不能证明 repairability 来源正确。

---

## 6. 每阶段必交审核包

实施者提交每个阶段时必须提供：

### 6.1 Change manifest

- phase_id；
- commit 或明确 diff 范围；
- 新增、修改、删除文件列表；
- 每个文件对应的计划条目；
- 是否修改 schema、serializer、snapshot 或 public API；
- 是否存在 compatibility shim；
- 是否存在生成文件变化。

### 6.2 Behavioral evidence

- 修改前行为；
- 修改后行为；
- 结构化输入 fixture；
- 结构化输出；
- 至少一个正向和一个负向示例；
- 阶段涉及状态轴时，提供完整状态矩阵。

### 6.3 Test evidence

必须给出完整命令、退出码和关键断言。不得只写“全部测试通过”。

至少包括：

    python -m pytest <phase-specific-tests> -q
    python -m ruff check <changed-scope>
    git diff --check

### 6.3.1 IRS contract gate

凡阶段修改 ConstructIRS、SlotSpec、DiagnosticRegistry、diagnostic disposition、
grouping metadata 或 RepairCatalog 关系，必须额外执行：

    python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py --construct API_DECLARATION --scope all --format json
    python .agents/skills/audit-irs-contract/scripts/audit_irs_contract.py --construct CALL_API --scope all --format json

审核要求：

1. 不得出现新的 unwaived P0/P1。
2. 既有 waiver 必须 finding ID、owner、issue 和期限均未改变。
3. 实施者必须提交修改前后 finding diff。
4. 不得新增 waiver 来让当前阶段通过。
5. API functions/schema 必须继续被判定为 non-editable deferred validation。

audit 通过只证明 registry/runtime closure coherence，不能替代本阶段的 Pipeline、
snapshot、presentation 或 E2E 验收。

### 6.4 Static audit evidence

必须提供与阶段对应的 rg 或 AST 扫描结果，并说明每个命中是否合理。

### 6.5 Residual risk

- 未完成项；
- 已知风险；
- 是否阻断下一阶段；
- owner；
- 计划移除阶段。

缺少任一部分，PM 不得判 PASS。

---

## 7. 全局代码审查门禁

每个阶段都必须检查：

1. 没有新增 LLM 调用或 prompt/schema。
2. 没有新增 report/final SPL parsing。
3. 没有新增 CALL_API 到 GENERAL_COMMAND fallback。
4. 没有把 diagnostic kind 当 repair capability。
5. 没有修改 API placeholder grammar。
6. 没有把 known_present 写成 validated。
7. 没有把 unknown_placeholder 写成 known_empty。
8. 没有新增 API functions/schema repair affordance。
9. 没有 demo 名称、API 名称或 source retrieval 关键字硬编码。
10. 没有无关全仓格式化、metadata churn 或生成文件覆盖。
11. 没有新增 skip、xfail、try/except 吞错或弱断言。
12. 新增 grouping 必须基于 structured identity。
13. 新增 presentation 必须消费 DTO/IssueInventory。
14. diagnostics 必须进入 final compile diagnostics 或明确的 developer partition。
15. None、空容器和 placeholder 状态不得通过 truthiness 混淆。

---

## 8. 阶段依赖门禁

| 阶段 | 必须先通过 | 解锁 |
| --- | --- | --- |
| AP-1 | 无 | AP0 |
| AP0 | AP-1 | AP1 |
| AP1.1 | AP0 | AP1.2 |
| AP1.2 | AP1.1 | AP1.3 |
| AP1.3 | AP1.2 | AP2、AP3 |
| AP2 | AP1 | AP4、AP5 |
| AP3.1-AP3.4 | AP1；可与 AP2 部分并行 | AP7 |
| AP4 | AP2 | AP7 |
| AP5.1 | AP2 | AP5.2 |
| AP5.2 | AP5.1 | AP5.3 |
| AP5.3 | AP5.2 | AP5.4 |
| AP5.4 | AP5.3 | AP7 |
| AP6 | AP1；必须在 AP7 前完成 | AP7 |
| AP7 | AP0-AP6 全部 PASS | 核心项目完成 |
| AO1 | AP7 PASS + 独立设计批准 | 可选增强 |

---

## 9. Phase AP-1 审核准则

### 9.1 准入

- 当前 Stage 6/7、Gate、Renderer baseline 可运行。
- 未开始任何生产代码语义修改。
- 基线 demo/snapshot 可定位。

### 9.2 必交付物

必须新增 characterization tests，覆盖：

- valid source-backed API + unknown placeholders；
- malformed schema；
- malformed functions container；
- missing API name；
- missing source evidence；
- valid partial declaration + valid CALL_API demand/binding/placement；
- 当前错误 editable metadata；
- 当前 presentation 丢失 deferred item；
- structured diagnostic counts。

### 9.3 PM 必查

1. 本阶段不得修改 src/nl2spl 生产代码。
2. 不得修改 final_spl.txt 或 snapshot 来迎合测试。
3. 计数必须从 diagnostics 结构计算。
4. expected-correct 与 expected-to-change 断言必须分开命名。
5. 测试必须真实经过 Stage 6、IRS、Gate、Stage 7。
6. malformed 负向路径必须存在。
7. 不允许 skip/xfail。

### 9.4 直接拒绝

- fixture 手工拼最终 SPL；
- 解析 feedback_report.md 得到计数；
- 修改生产代码；
- 只记录 happy path；
- 用 broad snapshot golden 替代字段级断言。

### 9.5 PASS 条件

- characterization 全部通过；
- baseline 数量有结构化来源；
- 后续应改变的错误行为被清晰锁定；
- 无生产 diff。

---

## 10. Phase AP0 审核准则

### 10.1 准入

AP-1 必须 PASS。

### 10.2 必交付物

- DiagnosticRegistry 注册 deferred_api_contract_validation；
- severity 固定为 info；
- blocks_completion=false；
- allowed target=api；
- serializer round-trip；
- completeness tests；
- API slots affordance 不变证明。

### 10.3 PM 必查

1. type_or_contract_ambiguity 的全局 blocking 语义未修改。
2. 新 diagnostic 只用于 grammar-safe unknown placeholders。
3. malformed、missing identity、missing evidence 仍用 structural diagnostic。
4. functions/schema repair_affordances 仍为空。
5. 只有 deferred diagnostics 时 compute_completeness 返回 complete。
6. 新 diagnostic 不被加入 editable kind 常量作为 shortcut。
7. 没有新增 feature flag 或 LLM。

### 10.4 直接拒绝

- 将 type_or_contract_ambiguity 全局改为 non-blocking；
- severity 使用 warning；
- deferred kind 被其他普通 contract gap 复用；
- 通过 message 判断是否 deferred；
- 新增 API repair affordance。

### 10.5 PASS 条件

- diagnostic contract 唯一且可 round-trip；
- completeness 语义正确；
- malformed 行为未弱化；
- 全量 diagnostic/completeness tests 通过。

---

## 11. Phase AP1 审核准则

### 11.1 AP1.1：Slot classification

#### 必交证据

状态矩阵至少覆盖：

| schema/functions 状态 | grammar shape | expected diagnostic | renderable |
| --- | --- | --- | --- |
| known_present | valid | none | true |
| known_empty | valid | none | true |
| unknown_placeholder | valid partial | deferred | true |
| invalid shape | invalid | structural blocking | false |
| status contradiction | invalid | structural blocking | false |

#### PM 必查

- condition 来自 APISpec structured status；
- unknown_placeholder 没被标成 satisfied/validated；
- report completeness 可 partial；
- report renderable=true；
- metadata 包含 nl2spl_renderable、api_contract_validation_status、validation_authority、issue_group_id、repairability、presentation_disposition；
- condition/source identity 缺失仍 fail closed。

#### PASS 条件

分类确定、无文本解析、无 truthiness 混淆、正负路径齐全。

### 11.2 AP1.2：Projector whitelist

#### 必交证据

只允许投影：

- issue_group_id；
- repairability；
- validation_authority；
- nl2spl_renderable；
- api_contract_validation_status；
- placeholder_fields；
- 既有 IRS ref/authority 字段。

#### PM 必查

1. 使用显式 whitelist，不复制任意 metadata。
2. severity/blocks_completion 仍来自 DiagnosticRegistry。
3. message 不参与 disposition。
4. snapshot diagnostic round-trip 不丢字段。
5. 未白名单字段有负向测试。

#### PASS 条件

合法 metadata 完整传播，任意 metadata 无法泄漏。

### 11.3 AP1.3：Completeness 回归

#### PM 必查的完整断言

    report.completeness == partial
    report.renderable == true
    diagnostic.kind == deferred_api_contract_validation
    diagnostic.blocks_completion == false
    PipelineResult.completeness == complete

同时必须有 malformed 对照：

    report.renderable == false
    structural diagnostic blocks completion
    PipelineResult.completeness != complete

#### PASS 条件

construct partial 与 pipeline complete 的组合被真实测试证明，不是手工构造 PipelineResult。

---

## 12. Phase AP2 审核准则

### 12.1 准入

AP1 全部 PASS。

### 12.2 必交付物

- capability-aware diagnostic annotator；
- compiler-owned generic grouping；
- stable API group ID；
- deterministic primary/alias；
- metadata/catalog conflict 处理；
- permutation tests。

### 12.3 PM 必查

1. 删除或停用 type_or_contract_ambiguity blanket editable。
2. 显式 review_only/non_repairable metadata 优先保留。
3. editable 仅在 IRS slot 有 user-facing RepairCatalog entry 时成立。
4. promoted worker policy 仍可产生 editable。
5. API deferred group repairability=review_only。
6. API group恰好一个 primary。
7. related_diagnostic_ids 包含完整 functions/schema diagnostics。
8. grouping 模块不 import SPL Editing service/runtime。
9. diagnostic 顺序变化不改变 group ID、primary 或 disposition。
10. malformed structural diagnostic 不进入 deferred group。

### 12.4 直接拒绝

- 按 kind 标 editable；
- 用 target_ref/message regex 分组；
- UI/CLI 自己聚合；
- API group 与 worker group 共用错误 target；
- metadata 声称 editable 但 catalog 无 entry 时静默过滤。

### 12.5 PASS 条件

API、worker、generic ambiguity 三类 disposition 均有正负测试，且顺序无关。

---

## 13. Phase AP3 审核准则

AP3 以 contract hardening 为主。大规模重写已工作的 Stage 6/7 默认判 P1，除非提供必要性证明。

### 13.1 AP3.1：Stage 6

必须证明：

- schema placeholder canonical_text 恰为 {}；
- functions placeholder 恰为空 functions；
- status 为 unknown_placeholder；
- declaration_status 为 grammar_minimal_partial；
- replay 不重复创建 API；
- identity/provenance 被复用；
- known_present/known_empty 不被覆盖；
- 无 source demand 不创建 API；
- 不调用 LLM。

### 13.2 AP3.2：ResourceDeclarationGate

必须证明 Gate 只依赖：

- report.renderable；
- grammar status；
- grammar_valid；
- api_name satisfied；
- source_evidence satisfied。

必须有负向测试证明 malformed、identity/evidence failure 被拒绝。

直接拒绝以下条件进入 Gate：

- schema/functions 必须非 placeholder；
- report.completeness 必须 complete；
- incomplete_api_names 直接阻止 CALL_API。

### 13.3 AP3.3：Stage 7

必须证明：

- partial but renderable API 可生成 CALL_API；
- demand、unique declaration binding、placement、identity、binding status、operation coverage 仍要求完整；
- not_required bindings 可接受空 inputs/outputs；
- missing declaration/binding/placement fail closed；
- 不降级 GENERAL_COMMAND；
- 不要求 semantic API contract complete。

### 13.4 AP3.4：ExecutableGate 与 Renderer

必须证明：

- integration_ref 必须解析到 approved declaration；
- binding identity 一致；
- placeholder status 不是 rejection reason；
- undeclared ref 被拒绝；
- Renderer 同时输出 DEFINE_APIS 和 CALL；
- exact placeholder syntax 稳定；
- Renderer 不执行 API semantic validation。

### 13.5 AP3 总 PASS 条件

四个子阶段分别通过，且生产 diff 没有无理由重写现有 pipeline。

---

## 14. Phase AP4 审核准则

### 14.1 准入

AP2 必须 PASS。

### 14.2 必交付物

- 通用 GroupedDiagnosticView 或等价 projection；
- DiagnosticSectionKind 或等价 section contract；
- Deferred downstream validation section；
- API 与 worker grouping 回归；
- permutation tests。

### 14.3 PM 必查

1. 分组读取 issue_group_id、primary、related IDs。
2. summary 每组只出现一次。
3. details 从 missing_slot/irs_ref 获取。
4. 无 structured group metadata 时保留 raw diagnostic，不猜测。
5. Deferred diagnostics 不进入 requirement gaps。
6. malformed structural diagnostics 进入 blocking section。
7. developer details 可追踪原始 diagnostic identity。
8. worker-specific order 只控制 detail order。
9. report 不影响 PipelineResult completeness。
10. 文案不得写成“API 缺失导致结果 partial”。

### 14.4 PASS 条件

API deferred group 在用户 summary 中恰好一次，两个 slot 可追踪，worker grouping 不回归。

---

## 15. Phase AP5 审核准则

### 15.1 AP5.1：Canonical model

必须具备 UserFacingIssue 或等价模型，至少表达：

- disposition；
- primary/related diagnostic IDs；
- group ID；
- target/IRS ref；
- missing slots；
- blocks_rendering/completion；
- validation authority；
- affordance IDs。

IssueInventory 必须独立分区：

- editable；
- review；
- deferred；
- developer。

直接拒绝把 repairability=review_only 的对象命名或存入 EditableIssue。

### 15.2 AP5.2：Extractor

PM 必查流程：

    validate authority/IRS refs
    -> group by structured issue_group_id
    -> exactly one primary
    -> derive disposition from metadata + catalog
    -> emit partitions

必须证明：

- API group进入 deferred；
- API group不进入 list_editable_issues；
- worker promotion进入 editable；
- editable metadata 无 affordance 时进入 developer/review，不静默消失；
- list_editable_issues 从 inventory.editable compatibility projection 返回；
- group identity 稳定。

### 15.3 AP5.3：Presentation

API deferred card 必须：

- can_fix=false；
- available_repairs=()；
- 不显示 Fix with AI；
- 使用 structured API name、missing slots、placeholder metadata、validation authority；
- 不读取 raw diagnostic.message；
- Advanced Details 可追踪 diagnostics/slots/authority。

Deferred section 必须来自 inventory.deferred，不得由 CLI 临时拼接。

### 15.4 AP5.4：Run summary 与 CLI

必须证明：

    Editable issues: 7
    Deferred validation: 1

并检查：

- issue_count 仍表示 editable count；
- review/deferred 不混入旧 issue_count；
- deferred item 可查看但不可进入 suggestion/apply；
- worker delegation 仍可修；
- CLI 不 import raw diagnostic 类型做语义判断；
- Presentation DTO 是唯一渲染输入。

若 demo fixture 因前置结构化输入合理变化导致计数改变，实施者必须提交经 PM 批准的 baseline change 说明，不能自行更新期望值。

### 15.5 AP5 总 PASS 条件

model、extractor、presentation、CLI 四个子阶段独立通过，且 deferred issue 不再静默消失。

---

## 16. Phase AP6 审核准则

### 16.1 准入

AP1 已 PASS；必须在 AP7 前 PASS。

### 16.2 必交付物

- downstream contract 文档；
- APISpec status round-trip tests；
- deferred diagnostic metadata round-trip tests；
- PipelineResult 可定位 pending API identity；
- rendered SPL placeholder stability test。

### 16.3 PM 必查

1. 不新增 SPL grammar。
2. 不调用外部 validator。
3. 不进行网络、endpoint、provider 或 credential probe。
4. Rendered SPL 是 text-only consumer 的 normative handoff。
5. Structured artifacts 是支持结构化消费者的额外 authority。
6. intermediate debug JSON 不是唯一持久化 authority。
7. source provenance 保留。
8. known_present 不被描述为 validated。
9. known_empty 不被描述为 provider callable。
10. malformed placeholder 不离开 NL2SPL。

### 16.4 PASS 条件

文本消费者和结构化消费者均可识别“需要下游验证”，且 NL2SPL 从未宣称已验证。

---

## 17. Phase AP7 最终审核准则

### 17.1 准入

AP0-AP6 全部 PASS。任何 conditional pass 必须有 PM 明确批准进入 AP7 的记录。

### 17.2 必须真实运行的场景

#### 场景 1：Only placeholders pending

必须真实证明：

- Stage 6 生成 grammar_minimal_partial；
- final SPL 包含 {}；
- final SPL 包含空 functions；
- final SPL 包含 CALL；
- PipelineResult complete；
- diagnostic 为 info/non-blocking deferred；
- 无 Fix with AI。

#### 场景 2：Demo mixed issues

必须运行真实 run_demo.py，并检查：

- 7 editable；
- 1 deferred；
- 6 exception；
- 1 worker delegation；
- API group只有一个；
- API item 不可 apply；
- worker item 可进入修复流程。

#### 场景 3：Malformed schema

必须证明：

- IRS structural diagnostic；
- ResourceDeclarationGate reject；
- CALL_API 不渲染；
- compile 不 complete；
- 无 GENERAL_COMMAND fallback。

#### 场景 4：Missing identity/evidence

必须证明 declaration 和 CALL 均不可用，且 diagnostic 是 structural，不是 deferred。

#### 场景 5：Known present/known empty

必须证明 declaration/CALL 渲染、无 placeholder deferred diagnostic，但仍不宣称 external validated。

#### 场景 6：API + worker

必须证明：

- API 在 Deferred validation；
- worker 在 Editable issues；
- target、title、category、group ID 均不混淆。

#### 场景 7：Permutation/metamorphic

至少改变：

- diagnostic 顺序；
- API declaration 顺序；
- API 名称；
- source domain 名称。

结果必须保持：

- grouping 稳定；
- disposition 稳定；
- placeholder policy 稳定；
- 无 demo-specific 分支。

### 17.3 静态审计

必须执行并提交结果：

    rg "repair_affordances" src/nl2spl/compiler/construct_registry.py
    rg "type_or_contract_ambiguity" src/nl2spl
    rg "feedback_report|diagnostic.message|final_spl" src/nl2spl
    rg "GENERAL_COMMAND" src/nl2spl/pipeline/stages/stage7_step_extractor
    rg "schema_status|functions_status|completeness" src/nl2spl/pipeline
    rg "LLM|generate_json|prompt" <changed-files>

PM 必须审阅命中项，不能只接受“无异常”的口头结论。

### 17.4 最终 PASS 条件

1. 七个 E2E 场景全部通过。
2. 全量 unit/integration tests 通过。
3. 项目既定 Ruff 范围通过。
4. 无 skip/xfail。
5. 无 demo-specific hardcode。
6. 无未清理 compatibility shim。
7. 设计、downstream contract 与代码一致。
8. PM 亲自查看真实 final SPL。
9. PM 亲自查看真实 run_demo 输出。
10. PM 确认 API deferred issue 无法进入 apply flow。
11. git diff 无无关格式化或 generated artifact churn。
12. 只有 deferred diagnostics 时整体 completeness 为 complete。

---

## 18. AO1 可选阶段审核

AO1 不属于 AP0-AP7 的完成条件。

AO1 只有在以下条件全部满足时才可启动：

1. AP7 已 PASS。
2. 产品明确要求 NL2SPL 阶段提供 API contract enrichment。
3. 已有独立设计文档和实施计划。
4. 明确用户输入、configured contract refs、typed normalization 和 evidence authority。
5. 关闭 AO1 时 baseline placeholder/CALL_API 链路仍完整工作。

禁止：

- 把 AO1 作为 rendering 依赖；
- 在 AP0-AP7 中提前加入 enrichment prompt；
- 让 LLM 自由生成 OpenAPI；
- 把 optional enrichment 变成 mandatory editable issue；
- 用 AO1 修补基础状态模型缺陷。

---

## 19. 最终 E2E 审核矩阵

| 场景 | Declaration | CALL_API | Pipeline | Inventory | Apply | Downstream |
| --- | --- | --- | --- | --- | --- | --- |
| valid unknown placeholders | rendered partial | rendered | complete | one deferred | forbidden | pending |
| malformed schema/functions | rejected | rejected | partial/blocked | structural | not applicable | not reached |
| missing identity/evidence | rejected | rejected | partial/blocked | structural | not applicable | not reached |
| known local contract | rendered | rendered | complete if no other gaps | no placeholder deferred | not applicable | still validates |
| API + worker | rendered | independent | based on real blockers | deferred + editable | worker only | API pending |
| AO1 disabled | rendered | rendered | unaffected | deferred if unknown | forbidden | pending |

任何一行未被真实测试覆盖，最终 AP7 不得 PASS。

---

## 20. PM 阶段审核报告模板

每阶段必须形成如下记录：

    Phase:
    Reviewer:
    Date:
    Commit/diff:
    Prerequisites:
    Verdict: PASS | CONDITIONAL_PASS | FAIL | BLOCKED
    allowed_to_start_next_phase: true | false

    Design requirements checked:
    - ...

    Files changed:
    - ...

    Positive tests:
    - command:
      exit code:
      key assertion:

    Negative tests:
    - command:
      exit code:
      key assertion:

    Real artifact evidence:
    - artifact:
      source:
      observed fields:

    Static audit:
    - command:
      findings:
      disposition:

    P0:
    - none | ...

    P1:
    - none | ...

    P2:
    - none | ...

    Residual risks:
    - owner:
      issue:
      target phase:

    PM conclusion:
    - ...

禁止仅提交：

    tests passed
    ruff passed
    implementation complete

以上内容不能证明阶段语义正确。

---

## 21. PM 最终签署条件

PM 只能在以下事实全部成立后签署项目完成：

1. API placeholder renderability 与 API validity 已形成两个独立状态轴。
2. deferred_api_contract_validation 为 info 且不阻断。
3. API construct partial 不再自动造成 PipelineResult partial。
4. malformed API 仍 fail closed。
5. API diagnostics 稳定聚合为一个 deferred issue。
6. API issue 不进入 Editable issues 或 apply flow。
7. worker delegation 仍独立且可修复。
8. IssueInventory 成为 presentation 的完整数据源。
9. feedback report 正确区分 blocking 与 deferred。
10. Stage 6/7/Gate/Renderer authority 未被重写或混淆。
11. text 和 structured downstream handoff 均有测试。
12. 全部真实 E2E 和负向场景通过。
13. 无 LLM、report parsing、fallback 或 demo hardcode。
14. 无未清理 shim、skip、xfail 或无关改动。
15. 实施计划、审核准则、代码和用户可见行为一致。

只有满足以上全部条件，最终 Verdict 才能为 PASS。
