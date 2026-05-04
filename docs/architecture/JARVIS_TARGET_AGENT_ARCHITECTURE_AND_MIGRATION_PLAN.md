# Jarvis Target Agent Architecture：交互式 Coding Agent 主架构设计与迁移施工书

> 目标：把 Jarvis 从“router-driven chatbot / control shell”逐步改造成“agent-turn-driven coding assistant”。
>
> 核心定位：
>
> ```text
> Jarvis ≈ Claude Code / Codex 的交互式 coding agent 主路径
>       + OpenClaw 的 control surface / events / skills
>       + Hermes 的 tool trail / trace / output renderer
> ```

---

## 0. 本文用途

本文是 Jarvis 后续改造的架构约束文档。Codex 后续施工必须先阅读本文，再按 Phase 逐步改造。

本文要解决的问题：

1. 明确 Jarvis 最终主路径是什么。
2. 明确 CLI / API / Web 如何共享 AgentLoop。
3. 明确 slash command 和普通自然语言如何分流。
4. 明确 clarification 不再是前置模块，而是 Agent 输出类型。
5. 明确旧 routing / dispatcher / natural_responses 的降级位置。
6. 明确每一阶段应该改什么、不应该改什么。
7. 防止后续施工中重新走回 `deterministic_router -> clarification.py -> dispatcher` 的旧路。

---

## 1. 当前问题

当前 Jarvis 已经具备很多能力：

- CLI interactive shell
- slash commands
- API / Web control surface
- AgentLoop.run_turn()
- ToolCallExecutor
- fake / real LLM mode
- benchmark / checklist
- CLI renderer
- safety / approval / skills / tools / replay / evidence

但是目前至少存在两套自然语言处理路径：

```text
A. one-shot 新路径：
python -m jarvis.cli --ask "..."
→ AgentLoop.run_turn()
→ AgentRunResult
→ CLI renderer

B. interactive 旧路径：
python -m jarvis.cli
> 普通自然语言
→ deterministic_router / llm_classifier / clarification.py / dispatcher
→ canned response 或错误澄清
```

这导致交互式 CLI 中出现错误行为：

```text
> 你是什么模型
我需要再确认一下：你可以具体告诉我你想让我做什么吗？例如：读项目、解释代码、改文件、运行命令，或者聊天。

> 你能帮我写代码吗？
我需要再确认一下：你可以具体告诉我你想让我做什么吗？例如：读项目、解释代码、改文件、运行命令，或者聊天。
```

这说明普通自然语言没有稳定进入 AgentLoop，而是被旧 clarification 兜底抢跑。

---

## 2. 目标架构总原则

请把下面十条视为 Jarvis Agent 架构的硬原则。

```text
1. 命令归命令，对话归 Agent。
2. Slash command 本地处理，不进入 LLM。
3. 普通自然语言默认进入 AgentLoop.run_turn()。
4. CLI / API / Web 共享 AgentRunResult。
5. Renderer 只负责显示，不做决策。
6. Tool call 必须经过 policy / approval / safety。
7. Router 最多提供 route_hint，不产生普通自然语言最终回答。
8. Clarification 是 Agent output_type，不是 router。
9. Safety refusal 是 Agent output_type，不是异常崩溃。
10. Benchmark 必须覆盖 fake 和 real 两种模式。
```

---

## 3. 最终目标结构

```text
Jarvis
├── Entry Layer
│   ├── CLI Interactive Shell
│   ├── CLI One-shot: --ask
│   ├── API Server
│   └── Web Control Surface
│
├── Command / Control Layer
│   ├── SlashCommandDispatcher
│   ├── Config / Status / Doctor
│   ├── Tools / Skills / Permissions
│   ├── Approvals / Replay / Evidence
│   └── LocalCommandResult
│
├── Agent Input Layer
│   ├── ChatInput
│   ├── Session / Thread Context
│   ├── Safety Precheck
│   └── Optional Route Hint
│
├── Agent Core Layer
│   ├── AgentLoop.run_turn()
│   ├── ContextBuilder
│   ├── ModelClient
│   ├── ToolCall Parser
│   ├── ToolCallExecutor
│   ├── Observation Feedback
│   ├── Retry / Replan / Stop Policy
│   └── ResponseComposer
│
├── Tool / Skill Layer
│   ├── ToolRegistry
│   ├── SkillRegistry
│   ├── RepoReader
│   ├── FileEditor
│   ├── CommandRunner
│   ├── TestRunner
│   ├── Web/Search Tools
│   └── MCP / External Tool Adapter
│
├── Policy / Safety Layer
│   ├── SafetyGate
│   ├── ApprovalGate
│   ├── PermissionMode
│   ├── Secret Redaction
│   ├── Dangerous Command Guard
│   └── Sensitive File Guard
│
├── Event / Trace Layer
│   ├── AgentEvent
│   ├── ToolTrail
│   ├── Trace Timeline
│   ├── ReplayStore
│   └── EvidenceStore
│
├── Output Layer
│   ├── AgentRunResult
│   ├── output_type
│   │   ├── answer
│   │   ├── tool_result
│   │   ├── clarification
│   │   ├── refusal
│   │   ├── partial
│   │   └── error
│   ├── CLI Renderer
│   ├── Web Renderer
│   └── JSON Renderer
│
└── Benchmark / Evaluation Layer
    ├── jarvis_core
    ├── coding
    ├── terminal
    ├── web_research
    ├── real_llm smoke
    └── checklist / report
```

---

## 4. CLI 输入分流设计

### 4.1 Slash command

输入以 `/` 开头：

```text
/help
/status
/config
/tools
/skills
/doctor
/permissions
/approvals
/replay
/evidence
/exit
```

目标路径：

```text
Slash input
→ SlashCommandDispatcher
→ LocalCommandResult
→ CLI renderer
```

特点：

- 不进 LLM。
- 不进 AgentLoop。
- 不调用普通自然语言 router。
- 用于控制 Jarvis 本地状态、工具、权限、配置、日志、replay、evidence。

### 4.2 普通自然语言

输入不以 `/` 开头：

```text
下午好
你是什么模型
你能帮我写代码吗？
读取 README.md
列一下当前目录
运行 pytest
修复这个 bug
帮我弄一下
```

目标路径：

```text
Natural language input
→ ChatInput
→ AgentLoop.run_turn()
→ AgentRunResult
→ CLI/Web/API renderer
```

特点：

- 默认进入 AgentLoop。
- AgentLoop 决定是否调用模型、工具、安全拒绝、澄清或直接回答。
- 旧 routing 只能作为 hint，不能直接生成普通自然语言最终回答。

---

## 5. Clarification 新设计

### 5.1 旧设计：必须废弃

旧路径：

```text
Natural language
→ deterministic_router
→ llm_classifier
→ clarification.py
→ dispatcher
```

问题：

- 容易把普通问题误判成澄清。
- “你是什么模型”被澄清。
- “你能帮我写代码吗”被澄清。
- “给我讲个笑话”可能被澄清。
- 破坏交互式 agent 体验。

### 5.2 新设计：Clarification 是 Agent 输出之一

Clarification 应该出现在：

```text
AgentLoop.run_turn()
→ AgentRunResult
   ├── output_type = "clarification"
   ├── stop_reason = "needs_user_clarification"
   ├── final_answer = "我需要确认一下：你希望我读取哪个文件？"
   └── summary.machine.needs_user_clarification = true
```

也就是说：

```text
clarification 是 final answer 的一种
clarification 不是独立 router
clarification 不是默认 fallback
clarification 不应抢跑普通自然语言
```

### 5.3 AgentOutputType

建议在 `src/jarvis/agent/types.py` 中定义：

```python
class AgentOutputType(str, Enum):
    ANSWER = "answer"
    TOOL_RESULT = "tool_result"
    CLARIFICATION = "clarification"
    REFUSAL = "refusal"
    PARTIAL = "partial"
    ERROR = "error"
```

并在 `AgentRunResult` 中增加：

```python
output_type: str = "answer"
```

或使用 Literal：

```python
output_type: Literal[
    "answer",
    "tool_result",
    "clarification",
    "refusal",
    "partial",
    "error",
]
```

### 5.4 Clarification 输出结构

```json
{
  "ok": true,
  "output_type": "clarification",
  "stop_reason": "needs_user_clarification",
  "final_answer": "我需要确认一下：你希望我读取哪个文件？",
  "summary": {
    "machine": {
      "outcome": "partial",
      "needs_user_clarification": true,
      "missing_fields": ["file_path"],
      "clarification_question": "你希望我读取哪个文件？"
    }
  }
}
```

---

## 6. Clarification 触发规则

### 6.1 允许触发 clarification

Clarification 只允许在**真正缺必要信息**时触发。

| 输入 | 原因 | 合理澄清 |
|---|---|---|
| 帮我弄一下 | 缺任务对象 | 你希望我处理哪个文件、命令或问题？ |
| 处理一下 | 缺动作和对象 | 你希望我分析、修改、运行测试，还是总结？ |
| 修一下 | 缺 bug / 文件 / 测试 | 你希望我修复哪个问题？可以提供文件、报错或测试命令吗？ |
| 读取那个文件 | 缺文件路径 | 你希望我读取哪个文件？ |
| 这个有问题 | 缺上下文 | 你说的“这个”指的是哪个文件、错误或功能？ |

### 6.2 禁止触发 clarification

| 输入 | 正确行为 |
|---|---|
| 下午好 | 问候回答 |
| 晚上好 | 问候回答 |
| 你是谁？ | 自我介绍 |
| 你是什么模型？ | 回答当前 provider/model |
| 你能帮我写代码吗？ | 回答能力和权限边界 |
| 给我讲个笑话 | 直接聊天或 LLM 回答 |
| 读取 README.md | 调工具读取 |
| 列一下当前目录 | 调工具列目录 |
| 运行 pytest | 调命令/测试工具 |
| 打印我的 .env | 安全拒绝 |
| 显示 API key | 安全拒绝 |
| /help | 本地命令 |

原则：

```text
clarification 只解决“缺必要参数”
不解决“路由不确定”
```

如果只是路由不确定，应交给 AgentLoop / ModelClient 处理，而不是 clarification 抢跑。

---

## 7. 各类输入目标路径表

| 输入 | 目标路径 | output_type | 是否工具 | 是否 LLM |
|---|---|---|---:|---:|
| /help | LocalCommandDispatcher | command | 否 | 否 |
| /hlep | LocalCommandDispatcher + suggestion | command_error | 否 | 否 |
| 下午好 | AgentLoop 或 local quick answer | answer | 否 | 可选 |
| 晚上好 | AgentLoop 或 local quick answer | answer | 否 | 可选 |
| 你是谁 | AgentLoop | answer | 否 | 是 |
| 你是什么模型 | local config answer 或 AgentLoop | answer | 否 | 可选 |
| 你能帮我写代码吗 | AgentLoop 或 local capability answer | answer | 否 | 可选 |
| 给我讲个笑话 | AgentLoop | answer | 否 | 是 |
| 读取 README.md | AgentLoop + repo_reader.read_file | answer/tool_result | 是 | 是 |
| 列一下当前目录 | AgentLoop + repo_reader.search_files | answer/tool_result | 是 | 是 |
| 运行 pytest | AgentLoop + command/test tool | partial/answer | 是 | 是 |
| 打印我的 .env | Safety refusal | refusal | 否 | 可选 |
| 显示 API key | Safety refusal | refusal | 否 | 可选 |
| 帮我弄一下 | AgentLoop clarification | clarification | 否 | 是 |
| 修一下 | AgentLoop clarification | clarification | 否 | 是 |
| 读取那个文件 | AgentLoop clarification | clarification | 否 | 是 |

---

## 8. 模块职责划分

### 8.1 `jarvis/cli.py`

职责：

- CLI 参数解析。
- 交互式 shell 循环。
- slash command 判断。
- 调用 AgentLoop。
- 调用 `cli_agent_output` renderer。

不应负责：

- 复杂自然语言路由。
- clarification 生成。
- 工具执行。
- summary 生成。
- 直接拼接 raw AgentRunResult。

目标伪代码：

```python
def handle_interactive_input(text: str):
    if is_slash_command(text):
        return run_local_command(text)

    return run_agent_turn(text)
```

---

### 8.2 `jarvis/cli_agent_output.py`

职责：

- 把 `AgentRunResult` 渲染为 CLI 输出。
- 支持 default / quiet / verbose / trace / json。
- 负责脱敏、截断、格式化。
- 不做决策。

不应负责：

- 是否调用工具。
- 是否澄清。
- 是否拒绝。
- 是否重试。

---

### 8.3 `src/jarvis/agent/loop.py`

职责：

- 普通自然语言主路径。
- 管理 model call、tool call、observation、retry、summary。
- 产生 AgentRunResult。
- 产生 clarification / refusal / partial / error 等 output_type。

核心流程：

```text
ChatInput
→ ContextBuilder
→ Safety Precheck
→ ModelClient
→ ToolCall parsing
→ Policy / Approval
→ ToolCallExecutor
→ Observation feedback
→ Retry / Replan
→ ResponseComposer
→ AgentRunResult
```

---

### 8.4 `src/jarvis/agent/types.py`

职责：

- 定义 Agent 基础数据结构。

建议包含：

```text
ChatInput
ToolCall
ToolResult
AgentEvent
AgentRunResult
AgentOutputType
```

---

### 8.5 `src/jarvis/core/routing/*`

最终职责应降级。

保留用途：

- route_hint
- legacy compatibility
- benchmark old tests compatibility
- optional classifier

不再负责：

- 普通自然语言最终回答。
- 默认 clarification。
- CLI 交互主路径。

### 8.6 `src/jarvis/core/routing/clarification.py`

最终目标：

- 删除。
- 或保留 deprecated stub。
- 不允许主路径 import / call。

---

## 9. 与四个参考 agent 的对应关系

| Jarvis 层 | 参考对象 | 借鉴点 |
|---|---|---|
| CLI 普通输入 -> AgentLoop | Claude Code / Codex | 普通 prompt 是 agent turn |
| Slash command | Claude Code | /help /config /permissions 本地控制 |
| Tool execution | Codex / Claude Code | read/edit/run/test + approval |
| Control surface / skills | OpenClaw | skills、gateway、web UI、events |
| Event/trace 输出 | Hermes / OpenClaw | event stream、tool trail、trace |
| CLI renderer | Hermes / Codex | default/verbose/trace/json 分层 |
| Clarification | Agent output | needs_user_clarification，不是模块 |

---

## 10. 最终数据流示例

### 10.1 普通聊天

```text
用户：你能帮我写代码吗？

CLI
→ AgentLoop.run_turn()
→ ModelClient / local capability answer
→ AgentRunResult(output_type=answer)
→ CLI renderer

输出：
可以。我可以读取和解释当前项目、搜索代码、生成修改方案、在安全审批后修改文件，并运行测试总结结果。
```

### 10.2 文件读取

```text
用户：读取 README.md

CLI
→ AgentLoop.run_turn()
→ ModelClient decides tool call
→ repo_reader.read_file
→ observation
→ ModelClient final answer
→ AgentRunResult(output_type=answer)
→ CLI renderer
```

### 10.3 敏感请求

```text
用户：打印我的 .env

CLI
→ AgentLoop.run_turn()
→ Safety precheck
→ AgentRunResult(output_type=refusal)
→ CLI renderer

输出：
不能直接打印 .env 内容，因为其中可能包含 API key、token 或密码。
```

### 10.4 真正需要澄清

```text
用户：读取那个文件

CLI
→ AgentLoop.run_turn()
→ 缺 file_path
→ AgentRunResult(output_type=clarification)
→ CLI renderer

输出：
我需要确认一下：你希望我读取哪个文件？
```

---

## 11. 迁移计划

### Phase 0：结构审计

目标：

- 不改代码。
- 生成当前路径审计文档。
- 明确 interactive natural language 当前路径。
- 明确 `--ask` one-shot 当前路径。
- 明确 `clarification.py` 调用点。
- 明确 slash command 路径。

产物：

```text
docs/cli/interactive_cli_path_audit.md
```

验收：

- 文档列出当前路径图。
- 文档列出目标路径图。
- 文档列出 clarification.py 调用点。
- 文档列出输入路径对照表。
- 不破坏测试。

---

### Phase 1：交互式 CLI 接 AgentLoop

目标：

```text
非 slash 输入默认走 AgentLoop.run_turn()
slash command 保持本地处理
```

改动范围：

```text
jarvis/cli.py
jarvis/cli_agent_output.py
tests/cli/
```

验收：

```text
你是什么模型 不澄清
你能帮我写代码吗 不澄清
读取 README.md 走工具
列目录走工具
/help 本地处理
/hlep 仍有 did you mean
```

---

### Phase 2：Clarification 迁移为 Agent 输出

目标：

```text
clarification.py 不再主路径调用
AgentRunResult 增加 output_type
needs_user_clarification 作为 stop_reason
```

改动范围：

```text
src/jarvis/agent/types.py
src/jarvis/agent/loop.py
src/jarvis/agent/summary.py
src/jarvis/core/routing/intent_gateway.py
src/jarvis/core/routing/clarification.py
tests/agent/
tests/cli/
tests/routing/
```

验收：

```text
帮我弄一下 -> output_type=clarification
读取那个文件 -> output_type=clarification
你是什么模型 -> output_type=answer
你能帮我写代码吗 -> output_type=answer
```

---

### Phase 3：删除或废弃 `clarification.py`

目标：

```text
src/jarvis/core/routing/clarification.py 删除
```

或者：

```text
保留 deprecated stub
不允许主路径 import / call
```

验收：

```text
grep clarification.py 调用点为 0 或全部为 deprecated test/compat
旧默认澄清句不再出现
tests/routing + tests/cli + tests/agent + tests/benchmark 通过
```

---

## 12. 风险与回归测试清单

### 12.1 风险

| 风险 | 说明 | 防护 |
|---|---|---|
| slash command 被误送进 AgentLoop | /help /exit 等被模型处理 | tests/cli 覆盖 slash command |
| 普通输入仍走旧 clarification | 用户继续看到默认澄清句 | 禁止旧句测试 |
| output_type 缺失导致 JSON 破坏 | 旧测试不兼容 | 默认 output_type=answer |
| 敏感请求被工具读取 | .env 泄露风险 | safety precheck + tests |
| benchmark 退化 | jarvis_core pass 下降 | fake/real benchmark 回归 |
| CLI 输出过吵 | default 像 debug report | output contract 测试 |

### 12.2 必测输入

```text
/help
/hlep
下午好
晚上好
你是谁
你是什么模型
你能帮我写代码吗
给我讲个笑话
读取 README.md
列一下当前目录
运行 pytest
打印我的 .env
显示 API key
帮我弄一下
修一下
读取那个文件
```

### 12.3 必跑命令

```bash
python -m pytest tests/cli -q
python -m pytest tests/routing -q
python -m pytest tests/agent -q
python -m pytest tests/benchmark -q
python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 10 --model-mode fake
python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 10 --model-mode real
```

---

## 13. Codex 执行顺序

Codex 后续每次施工必须遵守：

```text
1. 先阅读本文。
2. 每次只执行一个 Phase。
3. 不跨 Phase 大改。
4. 每个 Phase 完成后写报告。
5. 每个 Phase 必须跑对应 tests。
6. 任何偏离本文目标结构的修改必须说明原因。
```

---

## 14. Phase 0 Codex Prompt

```text
请阅读 docs/architecture/jarvis_target_agent_architecture.md，然后执行 Phase 0：结构审计。本轮只生成文档，不修改主逻辑。

目标：
审计 Jarvis 当前 CLI / routing / clarification 架构，为后续迁移做准备。

请阅读：
- jarvis/cli.py
- jarvis/cli_agent_output.py
- src/jarvis/agent/loop.py
- src/jarvis/agent/types.py
- src/jarvis/agent/summary.py
- src/jarvis/core/routing/intent_gateway.py
- src/jarvis/core/routing/clarification.py
- src/jarvis/core/routing/llm_classifier.py
- src/jarvis/core/routing/deterministic_router.py
- src/jarvis/core/cli_response/dispatcher.py
- src/jarvis/core/cli_response/natural_responses.py
- tests/cli/
- tests/routing/

请生成：
docs/cli/interactive_cli_path_audit.md

文档必须包含：

A. 当前结构图
- slash command 当前路径
- interactive natural language 当前路径
- --ask one-shot AgentLoop 当前路径
- clarification.py 当前触发路径

B. 目标结构图
- slash command -> LocalCommandDispatcher
- natural language -> AgentLoop.run_turn()
- clarification -> AgentRunResult.output_type="clarification"

C. clarification.py 调用点清单
列出所有 import / call site：
- 文件路径
- 函数名
- 调用条件
- 是否应删除/迁移

D. 输入路径对照表

| 输入 | 当前路径 | 是否 AgentLoop | 是否 LLM | 当前输出 | 目标路径 | 目标 output_type |
|---|---|---:|---:|---|---|---|

至少包含：
- /help
- /hlep
- 下午好
- 晚上好
- 你是谁
- 你是什么模型
- 你能帮我写代码吗
- 给我讲个笑话
- 读取 README.md
- 列一下当前目录
- 运行 pytest
- 打印我的 .env
- 帮我弄一下
- 修一下
- 读取那个文件

E. 迁移计划细化
基于当前代码，细化：
- Phase 1 要改哪些函数
- Phase 2 要改哪些函数
- Phase 3 要删除/废弃哪些调用点

F. 风险评估
说明可能影响：
- /help 等 slash command
- 旧 natural_responses
- routing tests
- CLI tests
- benchmark tests

本轮验收：
1. 只生成文档，不大改代码。
2. 明确指出 clarification.py 怎么被触发。
3. 明确指出如何把 clarification 迁移为 Agent 输出。
4. 不破坏现有测试。
```

---

## 15. Phase 1 Codex Prompt

```text
请阅读 docs/architecture/jarvis_target_agent_architecture.md 和 docs/cli/interactive_cli_path_audit.md，然后执行 Phase 1：交互式 CLI 接入 AgentLoop。

本轮目标：
1. slash command 保持本地处理。
2. interactive CLI 的非 slash 普通自然语言默认进入 AgentLoop.run_turn()。
3. 不再让普通自然语言走 clarification.py / dispatcher 旧默认路径。
4. 暂不删除 clarification.py。
5. 暂不大改 routing 模块。
6. 保持 /help、/hlep、/status、/config 等命令行为不退化。

请实现：
- python -m jarvis.cli 交互模式下：
  - 输入以 / 开头 -> LocalCommandDispatcher
  - 输入不以 / 开头 -> AgentLoop.run_turn()
- 使用已有 cli_agent_output renderer 输出。
- 保持 --ask one-shot 逻辑一致。

必须特别处理：
- 你是什么模型 -> 不澄清，回答 provider/model 或走 AgentLoop。
- 你能帮我写代码吗 -> 不澄清，回答能力。
- 下午好 / 晚上好 / 给我讲个笑话 -> 不澄清。
- 打印我的 .env -> refusal，不读取 .env。

新增或修改测试：
- tests/cli/test_interactive_shell_agent_path.py
- tests/cli/test_no_bad_clarification_output.py

测试必须覆盖：
- /help 本地命令
- /hlep did you mean
- 下午好 不澄清
- 你是什么模型 不澄清
- 你能帮我写代码吗 不澄清
- 读取 README.md 走 AgentLoop
- 列一下当前目录 走 AgentLoop
- 打印我的 .env 不泄露
- 帮我弄一下 可以 clarification
- 旧默认澄清句不再出现

运行：
python -m pytest tests/cli -q
python -m pytest tests/agent -q
python -m pytest tests/benchmark -q

人工 smoke：
python -m jarvis.cli
输入：
下午好
你是什么模型
你能帮我写代码吗？
读取 README.md
列一下当前目录
打印我的 .env
/hlep
/help
/exit

验收：
1. 普通自然语言进入 AgentLoop。
2. slash command 不退化。
3. 不再出现旧默认澄清句。
4. 敏感请求不泄露。
```

---

## 16. Phase 2 Codex Prompt

```text
请阅读 docs/architecture/jarvis_target_agent_architecture.md 和 docs/cli/interactive_cli_path_audit.md，然后执行 Phase 2：将 clarification 迁移为 Agent 输出类型。

本轮目标：
1. AgentRunResult 增加 output_type。
2. clarification 成为 output_type="clarification"。
3. stop_reason 使用 needs_user_clarification。
4. final_answer 是具体澄清问题。
5. clarification.py 不再被主路径调用。
6. 旧默认澄清句彻底禁用。

请实现：
- 在 src/jarvis/agent/types.py 增加 AgentOutputType 或 output_type 字段。
- 在 AgentLoop / ResponseComposer 中支持：
  - answer
  - tool_result
  - clarification
  - refusal
  - partial
  - error
- 对真正模糊输入返回：
  output_type=clarification
  stop_reason=needs_user_clarification
  final_answer=具体问题
- 对敏感请求返回：
  output_type=refusal
  stop_reason=completed 或 safety_refusal
- 对工具失败/timeout 返回：
  output_type=partial 或 error

Clarification 允许场景：
- 帮我弄一下
- 处理一下
- 修一下
- 读取那个文件
- 这个有问题

Clarification 禁止场景：
- 你是什么模型
- 你能帮我写代码吗
- 下午好
- 晚上好
- 给我讲个笑话
- 读取 README.md
- 列一下当前目录
- 打印我的 .env

新增或修改测试：
- tests/agent/test_agent_output_type.py
- tests/cli/test_no_bad_clarification_output.py
- tests/routing/test_clarification_not_front_path.py

运行：
python -m pytest tests/agent -q
python -m pytest tests/cli -q
python -m pytest tests/routing -q
python -m pytest tests/benchmark -q

验收：
1. output_type 出现在 AgentRunResult JSON 中。
2. 真正模糊输入 output_type=clarification。
3. 普通聊天 output_type=answer。
4. 敏感请求 output_type=refusal。
5. 旧默认澄清句不再出现。
6. clarification.py 不再主路径调用。
```

---

## 17. Phase 3 Codex Prompt

```text
请阅读 docs/architecture/jarvis_target_agent_architecture.md，然后执行 Phase 3：删除或废弃 clarification.py。

本轮目标：
1. 删除 src/jarvis/core/routing/clarification.py，或保留 deprecated stub。
2. 主路径不得 import / call clarification.py。
3. 所有 clarification 都由 AgentLoop / ResponseComposer 产生。
4. 清理旧 tests 中依赖 clarification.py 的逻辑。
5. 保持 routing 作为 route_hint / legacy compatibility，而不是最终回答路径。

请执行：
- grep / ripgrep 所有 clarification.py 引用。
- 删除主路径 import / call。
- 如果必须保留文件，文件顶部写明 deprecated，并确保不被主路径调用。
- 更新 docs。
- 更新 tests。

运行：
python -m pytest tests/routing -q
python -m pytest tests/cli -q
python -m pytest tests/agent -q
python -m pytest tests/benchmark -q

人工 smoke：
python -m jarvis.cli
输入：
你是什么模型
你能帮我写代码吗？
帮我弄一下
读取那个文件
/exit

验收：
1. 普通输入不再走 clarification.py。
2. 需要澄清的输入仍然返回 output_type=clarification。
3. 不再出现旧默认澄清句。
4. 所有测试通过。
```

---

## 18. 最终验收标准

最终完成后，以下行为必须成立：

```text
/help                         -> 本地命令
/hlep                         -> did you mean
下午好                         -> answer，不澄清
你是什么模型                   -> answer，显示 provider/model，不澄清
你能帮我写代码吗                -> answer，说明能力，不澄清
给我讲个笑话                    -> answer，不澄清
读取 README.md                 -> AgentLoop + tool
列一下当前目录                   -> AgentLoop + tool
运行 pytest                    -> AgentLoop + command/test tool
打印我的 .env                  -> refusal，不读 .env
显示 API key                   -> refusal，不泄露
帮我弄一下                      -> clarification
修一下                          -> clarification
读取那个文件                    -> clarification
```

最终架构：

```text
命令归本地 dispatcher
对话归 AgentLoop
clarification 归 AgentRunResult.output_type
clarification.py 退出主路径
```
