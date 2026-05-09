# SPL 缩进规范文档

## 1. 概述

SPL（Structured Prompt Language）采用**固定缩进规则**，每个元素的缩进级别由其在 SPL 结构中的位置决定，而非动态计算。

**核心原则**：
- 最顶层的内容无需缩进
- 每一层被包含的内容都需要多一个缩进级别
- 每个缩进级别 = 4 个空格

---

## 2. 缩进级别对照表

### 2.1 顶层结构（0级缩进，0空格）

| 元素 | 说明 |
|------|------|
| `[DEFINE_AGENT: ...]` | Agent 定义开始 |
| `[END_AGENT]` | Agent 定义结束 |

### 2.2 一级结构（1级缩进，4空格）

| 元素 | 说明 |
|------|------|
| `[DEFINE_PERSONA:]` / `[END_PERSONA]` | 角色定义 |
| `[DEFINE_AUDIENCE:]` / `[END_AUDIENCE]` | 受众定义 |
| `[DEFINE_CONCEPTS:]` / `[END_CONCEPTS]` | 概念定义 |
| `[DEFINE_CONSTRAINTS:]` / `[END_CONSTRAINTS]` | 约束定义 |
| `[DEFINE_VARIABLES:]` / `[END_VARIABLES]` | 变量定义 |
| `[DEFINE_FILES:]` / `[END_FILES]` | 文件定义 |
| `[DEFINE_APIS:]` / `[END_APIS]` | API 定义 |
| `[DEFINE_WORKER: ...]` / `[END_WORKER]` | Worker 定义 |

### 2.3 二级结构（2级缩进，8空格）

| 元素 | 说明 |
|------|------|
| `ROLE: ...` | 角色描述 |
| `Tone: ...` / `Style: ...` 等 | 可选方面 |
| `Key: "Value"` | 约束条目（key-value 形式） |
| `"描述" var_name: type` | 变量声明 |
| `"描述" api_name <auth> RETRY n` | API 声明 |
| `[INPUTS]` / `[END_INPUTS]` | 输入定义 |
| `[OUTPUTS]` / `[END_OUTPUTS]` | 输出定义 |
| `[MAIN_FLOW]` / `[END_MAIN_FLOW]` | 主流程 |
| `[ALTERNATIVE_FLOW: ...]` / `[END_ALTERNATIVE_FLOW]` | 替代流程 |
| `[EXCEPTION_FLOW: ...]` / `[END_EXCEPTION_FLOW]` | 异常流程 |
| `{...}` | OPENAPI_SCHEMA（JSON 块） |
| `{...}` | API_IN_SPL（JSON 块） |

### 2.4 三级结构（3级缩进，12空格）

| 元素 | 说明 |
|------|------|
| `REQUIRED <REF>...</REF>` | 输入/输出声明 |
| `OPTIONAL <REF>...</REF>` | 可选输入/输出 |
| `[SEQUENTIAL]` / `[END_SEQUENTIAL]` | 顺序块 |
| `[IF: ...]` / `[END_IF]` | 条件块 |
| `[FOR: ...]` / `[END_FOR]` | 循环块 |
| `[WHILE: ...]` / `[END_WHILE]` | While 循环 |

### 2.5 四级结构（4级缩进，16空格）

| 元素 | 说明 |
|------|------|
| `COMMAND-N [COMMAND ...]` | 通用命令 |
| `COMMAND-N [CALL API_NAME ...]` | API 调用 |
| `COMMAND-N [INVOKE WORKER_NAME ...]` | Worker 调用 |
| `COMMAND-N [INPUT ...]` | 请求输入 |
| `COMMAND-N [DISPLAY ...]` | 显示消息 |

---

## 3. 完整示例

### 3.1 基本 Agent 结构

```
[DEFINE_AGENT: MainWorker "Internal communications agent"]
    [DEFINE_PERSONA:]
        ROLE: Internal communications specialist
        Tone: Professional and concise
        Style: Clear and direct
    [END_PERSONA]

    [DEFINE_AUDIENCE:]
        Level: Senior leadership
        Format: Briefings
    [END_AUDIENCE]

    [DEFINE_CONCEPTS:]
        Provenance: The origin of sourced facts
        Evidence: Supporting documentation
    [END_CONCEPTS]

    [DEFINE_CONSTRAINTS:]
        Safety: Do not invent facts or fabricate sources
        Evidence: Require evidence for claims
        Evidence: Cite sources when referencing external information
    [END_CONSTRAINTS]

    [DEFINE_VARIABLES:]
        "User request" user_request: text
        "Draft output" draft: text
        "Completion status" status: boolean
    [END_VARIABLES]

    [DEFINE_WORKER: "Main worker" MainWorker]
        [INPUTS]
            REQUIRED <REF>user_request</REF>
        [END_INPUTS]

        [OUTPUTS]
            REQUIRED <REF>draft</REF>
            REQUIRED <REF>status</REF>
        [END_OUTPUTS]

        [MAIN_FLOW]
            [SEQUENTIAL]
                COMMAND-1 [COMMAND Determine the communication type based on <REF> user_request </REF> RESULT communication_type: text]
                COMMAND-2 [COMMAND Identify missing fields from <REF> user_request </REF> RESULT missing_fields: List[text]]
            [END_SEQUENTIAL]
        [END_MAIN_FLOW]

        [ALTERNATIVE_FLOW: Missing timeframe]
            [SEQUENTIAL]
                COMMAND-3 [COMMAND Request timeframe from user RESULT timeframe: text]
            [END_SEQUENTIAL]
        [END_ALTERNATIVE_FLOW]

        [EXCEPTION_FLOW: Evidence shortage]
            [SEQUENTIAL]
                COMMAND-4 [COMMAND Request additional evidence from user RESULT evidence: text]
            [END_SEQUENTIAL]
        [END_EXCEPTION_FLOW]
    [END_WORKER]
[END_AGENT]
```

### 3.2 API 定义示例

```
[DEFINE_APIS:]
    "Google Maps API" google_maps <apikey> RETRY 3
    {
        info: {
            title: "Google Maps API",
            version: "1.0"
        },
        paths: {
            /directions: {
                get: {
                    summary: "Get directions",
                    parameters: [
                        {
                            name: "origin",
                            in: "query",
                            required: true,
                            schema: {type: "string"}
                        }
                    ]
                }
            }
        }
    }
    {
        functions: [
            {
                name: "get_directions",
                url: "https://maps.googleapis.com/directions",
                description: "Get directions between two points",
                parameters: {
                    parameters: [
                        {
                            required: true,
                            name: "origin",
                            type: "text",
                            description: "Starting point"
                        },
                        {
                            required: true,
                            name: "destination",
                            type: "text",
                            description: "End point"
                        }
                    ],
                    controlled-input: false
                },
                return: {
                    type: "text",
                    controlled-output: false
                }
            }
        ]
    }
[END_APIS]
```

### 3.3 复杂流程示例

```
[MAIN_FLOW]
    [SEQUENTIAL]
        COMMAND-1 [COMMAND Parse user request and extract key information RESULT parsed_request: text]
        COMMAND-2 [CALL google_maps WITH origin=<REF>origin</REF>, destination=<REF>destination</REF> RESPONSE directions: text]
    [END_SEQUENTIAL]

    DECISION-1 [IF: directions found]
        [SEQUENTIAL]
            COMMAND-3 [COMMAND Format directions into readable format RESULT formatted_directions: text]
            COMMAND-4 [COMMAND Draft communication based on <REF>formatted_directions</REF> RESULT draft: text]
        [END_SEQUENTIAL]
    [ELSE]
        [SEQUENTIAL]
            COMMAND-5 [DISPLAY Unable to find directions for the specified route]
        [END_SEQUENTIAL]
    [END_IF]
[END_MAIN_FLOW]
```

---

## 4. 特殊情况处理

### 4.1 JSON 结构的缩进

OPENAPI_SCHEMA 和 API_IN_SPL 等 JSON 结构采用**标准 JSON 缩进**（每级2空格），但整个 JSON 块的起始位置遵循 SPL 缩进规则。

```
    "API Name" api_name <apikey>        # 2级缩进（8空格）
    {                                   # 2级缩进（8空格）
        key: {                          # JSON 内部缩进
            nested: "value"
        }
    }
```

### 4.2 约束的缩进

约束采用 key-value 形式，与 persona 类似（value 无需双引号）：

```
    [DEFINE_CONSTRAINTS:]               # 1级缩进（4空格）
        Safety: Do not invent facts     # 2级缩进（8空格）
        Evidence: Require evidence      # 2级缩进（8空格）
    [END_CONSTRAINTS]                   # 1级缩进（4空格）
```

### 4.3 多行描述的缩进

多行描述保持与首行相同的缩进级别。

```
        ROLE: Internal communications specialist
            who handles executive briefings
            and prepares reports
```

---

## 5. 验证规则

### 5.1 缩进验证

- 所有缩进必须是 4 的倍数
- 不允许使用 Tab 字符
- 每行的缩进必须符合其元素类型的固定级别

### 5.2 括号匹配验证

- 每个 `[TAG]` 必须有对应的 `[END_TAG]`
- 标签名称必须匹配（不区分大小写）
- 嵌套顺序必须正确

---

## 6. 格式化工具

使用 `SPLFormatter` 类自动格式化 SPL 文本：

```python
from nl2spl.compiler.spl_formatter import SPLFormatter

formatter = SPLFormatter()
formatted = formatter.format(raw_spl_text)
```

---

## 7. 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-05-06 | 初始版本，定义固定缩进规则 |

---

**文档维护者**: Developer E (Compiler Engineer)  
**最后更新**: 2026-05-06
