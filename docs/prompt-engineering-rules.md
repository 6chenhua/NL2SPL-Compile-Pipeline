# Prompt Engineering Rules

## 1. 只描述任务本身

LLM 不需要知道它在 pipeline 的第几步、上下游是什么、谁来消费它的输出。这些是架构文档的内容，不是 prompt 的内容。

- 对：`You are a semantic routing expert. Classify text spans.`
- 错：`You are Stage 2 of a 12-stage compiler pipeline. Your output feeds into…`

## 2. 不提禁止对象的名字

每一条"不要生成 X"都在 LLM 的注意力窗口里种下 X。用正向约束替代禁止清单。

- 对：`executable: true only when the text explicitly describes an action`
- 错：`Do NOT generate SPL, COMMAND, INVOKE_WORKER, CALL_API, or exception flows`

如果下游有 validator 做安全收口，prompt 更应该只给正向约束。Validator 的存在允许 prompt 变瘦。

## 3. 输入只给决策必需的数据

LLM 不需要看到所有可用数据。只给它做当前决策必需的最小字段集合。多余的字段是噪声——稀释注意力、浪费 token、引入无关信号。

- 对：spans（文本） + priors（当前标签） + allowed_schema（输出约束）
- 错：spans + sections + packets + hard_facts + compile_hints + priors + allowed_schema（全部塞进去）

如果你不确定某个字段是否必需，先不加。测试证明缺了再加。

## 4. 示例必须用与生产/测试不同域的数据

如果 prompt 示例和测试用例是同一领域，LLM 在测试时有"见过答案"的优势。示例应选择完全无关的领域。

- 对：测试是 Internal-Comms → 示例用 Inventory Management
- 错：测试是 Internal-Comms → 示例也是 Internal-Comms

## 5. 用示例替代通用输出格式声明

一段具体的 JSON 示例比一段 JSON schema 描述更有效。LLM 从示例学输出形状比从字段表学得快。优先放 2-3 个覆盖不同场景的示例，不必单独声明每个字段的类型。

## 6. Token 预算 = 注意力预算

每多 100 tokens，LLM 对核心任务的注意力就稀释一点。写完后问自己：删掉这一段，输出会变差吗？如果答案是不会——删掉。

常见可删内容：
- 输入字段描述（LLM 在 user prompt 里已经看到了）
- 上下游上下文（pipeline、compiler、consumer）
- 禁止清单（注意力污染）
- 冗余的 schema 表格（示例已经展示了）

## 7. 角色定义优先于规则列举

LLM 理解"你是一个 X 专家"比理解"你必须遵守以下 8 条规则"更快。把约束内化到角色定义和示例中，而不是用规则编号堆砌。

- 对：`Only mark executable when there is an action.`
- 错：`Rule 7.1: failure_mode MUST have executable=false. Rule 7.2: exception_handler_action MUST have executable=true.…`

## 8. 示例要覆盖边界情况

三个示例的最佳组合：
1. 一个展示核心能力（multi-label 拆分混合语义）
2. 一个展示约束（condition-only 不虚构 handler）
3. 一个展示细粒度区分（API/worker/boundary/prohibition）

每个示例不超过 15 行 JSON。不需要展示所有字段——只展示与当前场景相关的字段。
