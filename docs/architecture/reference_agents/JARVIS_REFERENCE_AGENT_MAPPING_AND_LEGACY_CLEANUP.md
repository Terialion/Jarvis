# Jarvis Reference Agent Mapping：参考 Agent 拼图说明书与旧代码清理原则

> 目标：让 Codex 明确理解 Jarvis 每一块架构拼图是做什么的、在整体架构哪一层、应该参考哪个 agent 的哪些代码、最终落到 Jarvis 哪些文件，以及在哪个 Phase 改。
>
> 核心补充原则：
>
> **已经被新架构替换的旧代码，不能长期只“降级保留”。必须尽快进入删除计划。**
>
> 降级只能作为短期过渡，不能成为长期架构的一部分。否则旧路径会残留、测试会继续依赖旧逻辑，最后 Jarvis 会重新变成双轨系统。

---

## 0. 总体目标

Jarvis 的最终形态是：

```text
Jarvis ≈ Claude Code / Codex 的交互式 coding agent 主路径
      + OpenClaw 的 control surface / events / skills
      + Hermes 的 tool trail / trace / output renderer
```

也就是：

```text
命令归本地 dispatcher
对话归 AgentLoop
clarification 归 AgentRunResult.output_type
clarification.py 退出主路径并尽快删除
```

架构原则：

```text
1. Slash command 本地处理。
2. 普通自然语言默认进入 AgentLoop.run_turn()。
3. CLI / API / Web 共享 AgentRunResult。
4. Renderer 只负责显示，不做决策。
5. Router 最多提供 route_hint，不产生普通自然语言最终回答。
6. Clarification 是 Agent output_type，不是 router。
7. Safety refusal 是 Agent output_type，不是异常崩溃。
8. 被新路径替换的旧路径必须有删除计划。
9. Legacy fallback 只允许短期存在，并必须有测试证明不会被主路径调用。
10. 每个 Phase 结束时都要检查旧代码调用点是否减少。
```

---

## 1. 为什么要做参考 Agent 拼图说明书

Codex 不能只看到一句“参考 Codex / Claude Code / OpenClaw / Hermes”。它需要知道：

```text
这块拼图是做什么的？
它位于 Jarvis 总架构哪一层？
参考哪个 agent 的哪些代码路径？
借鉴点是什么？
不要照抄什么？
最终落到 Jarvis 哪些文件？
对应哪个 Phase？
旧代码什么时候删？
```

否则容易出现几类跑偏：

```text
1. 拿 OpenClaw 的 TUI 思路去改 AgentLoop。
2. 拿 Claude Code 的 slash command 去替代普通聊天。
3. 把 Hermes 的 renderer 状态管理塞进工具执行层。
4. 把旧 routing 降级后长期保留，形成双轨架构。
5. clarification.py 虽然不在主路径，但 tests 或 fallback 仍然依赖它。
```

---

## 2. Jarvis 总体拼图

```text
Jarvis
├── Entry Layer                         # CLI / API / Web 入口
├── Slash Command Control Surface        # 本地命令控制面
├── Natural Language Entry               # 普通自然语言入口
├── Agent Core Layer                     # AgentLoop 主链路
├── Tool / Skill Layer                   # 工具与技能
├── Policy / Approval / Safety Layer     # 安全与审批
├── Event / Trace Layer                  # 事件、轨迹、回放
├── Output Renderer Layer                # CLI / JSON / Web 输出
├── Clarification as Output              # 澄清作为 Agent 输出
├── Benchmark / Evaluation Layer         # 测试验收层
└── Legacy Cleanup Layer                 # 旧代码清理层
```

四个参考 agent 的主要价值：

| 参考对象 | 主要借鉴 |
|---|---|
| Codex | Agent turn loop、工具/命令执行展示、patch/diff、approval、history cell |
| Claude Code | slash command、权限边界、hooks、output style、coding assistant 交互习惯 |
| OpenClaw | control surface、skills、gateway/events、chat log、tool execution component |
| Hermes Agent | event stream、tool trail、thinking/details mode、CLI/TUI renderer |

---

## 3. Entry Layer：CLI / API / Web 入口层

### 3.1 这块是做什么的

负责接收用户输入，并决定入口类型：

```text
/ 开头        -> 本地 command
普通自然语言 -> AgentLoop.run_turn()
API/Web 输入  -> AgentLoop.run_turn()
```

它不应该负责复杂意图理解，也不应该生成 clarification。

### 3.2 Jarvis 目标文件

```text
jarvis/cli.py
jarvis/cli_commands.py              # 建议新增，可选
src/jarvis/api/server.py
web / control ui 相关入口
```

### 3.3 可参考 agent

#### Claude Code

参考内容：

```text
.claude/commands/
plugins/*/commands/
plugins/hookify/commands/
```

借鉴点：

```text
slash command 是控制命令
普通 prompt 是 agent conversation
/help /permissions /doctor /model 这类命令本地处理
```

不要照抄：

```text
不要把所有自然语言都包装成 slash command
不要让 command 系统接管普通对话
```

#### Codex

参考内容：

```text
codex-rs/cli/src/main.rs
codex-rs/cli/src/lib.rs
codex-rs/tui/src/main.rs
codex-rs/tui/src/cli.rs
```

借鉴点：

```text
CLI 参数解析
one-shot / interactive 入口
进入 TUI / agent turn 的入口组织
```

#### OpenClaw

参考内容：

```text
src/cli/
src/cli/argv.ts
src/cli/command-catalog.ts
src/cli/command-format.ts
src/tui/tui.ts
src/tui/tui-launch.ts
```

借鉴点：

```text
control surface
命令目录
daemon / gateway / web ui 控制入口
```

### 3.4 旧代码清理要求

如果 `jarvis/cli.py` 中有旧的普通自然语言分发路径：

```text
_handle_natural_language
_detect_intent_route
build_cli_route
dispatch_natural_language
execute_agent_tool_loop
```

它们在 Phase 1 后不能继续作为默认主路径。

清理策略：

```text
Phase 1:
- 保留旧函数作为 legacy fallback。
- 默认非 slash 输入不再调用它们。

Phase 2:
- 将可复用逻辑迁移到 AgentLoop / route_hint / safety。
- 测试不再依赖旧 natural dispatcher。

Phase 3:
- 删除未被调用的旧函数，或移动到 deprecated module。
- grep 确认主路径无调用。
```

---

## 4. Slash Command Control Surface：本地命令控制层

### 4.1 这块是做什么的

负责本地控制命令：

```text
/help
/config
/status
/tools
/skills
/permissions
/doctor
/exit
```

目标路径：

```text
Slash input
→ LocalCommandDispatcher
→ LocalCommandResult
→ CLI renderer
```

这条路径：

```text
不进 LLM
不进 AgentLoop
不进入普通自然语言 router
```

### 4.2 Jarvis 目标文件

```text
jarvis/cli.py
jarvis/cli_commands.py              # 建议拆出来
src/jarvis/core/commands/           # 可选
tests/cli/test_slash_commands.py
```

### 4.3 可参考 agent

#### Claude Code

参考内容：

```text
.claude/commands/
plugins/*/commands/
plugins/hookify/commands/
plugins/security-guidance/hooks/
```

借鉴点：

```text
/help
/doctor
/permissions
/config
/model
/memory
/agents
```

核心思想：

```text
slash command 是控制面
不是普通聊天
不是 AgentLoop 的替代品
```

#### OpenClaw

参考内容：

```text
src/cli/command-catalog.ts
src/cli/command-format.ts
src/cli/config-cli.ts
src/cli/exec-approvals-cli.ts
src/cli/gateway-cli/
src/cli/daemon-cli/
```

借鉴点：

```text
命令目录统一管理
命令输出格式统一
approval / config / gateway / daemon 控制命令本地处理
```

### 4.4 旧代码清理要求

如果 slash command 和普通自然语言共用同一个 dispatcher，要拆清楚：

```text
保留：
- slash command dispatcher
- unknown command did-you-mean
- local config/status/help handlers

删除或迁移：
- slash dispatcher 中对普通自然语言的 fallback
- command handler 中调用 clarification.py 的逻辑
```

---

## 5. Natural Language Entry：普通自然语言入口

### 5.1 这块是做什么的

这是 Jarvis 最关键的承重柱。

目标：

```text
非 slash 普通输入
→ ChatInput
→ AgentLoop.run_turn()
```

不再走：

```text
deterministic_router
→ llm_classifier
→ clarification.py
→ dispatcher
```

### 5.2 Jarvis 目标文件

```text
jarvis/cli.py
src/jarvis/agent/loop.py
src/jarvis/agent/types.py
```

### 5.3 可参考 agent

#### Codex

参考内容：

```text
codex-rs/core/src/codex.rs
codex-rs/core/src/conversation_manager.rs
codex-rs/core/src/protocol.rs
codex-rs/tui/src/chatwidget.rs
```

借鉴点：

```text
普通用户输入就是一个 turn
turn 内部由模型决定 answer / tool call / command / patch
UI 只是消费 turn events
```

#### Claude Code

参考内容：

```text
plugins/
.claude/commands/
examples/hooks/
```

借鉴点：

```text
非 slash prompt 是 agent conversation
权限和 hooks 是工具边界，不是普通对话路由器
```

#### Hermes

参考内容：

```text
ui-tui/src/app/createGatewayEventHandler.ts
ui-tui/src/app/turnStore.ts
ui-tui/src/app/turnController.ts
```

借鉴点：

```text
普通 message 进入 turn controller
event 更新 turn state
renderer 消费状态
```

### 5.4 旧代码清理要求

Phase 1 后，以下旧路径不能再是默认路径：

```text
interactive natural language
→ route_user_input
→ route_intent
→ clarification fallback
→ dispatch_natural_language
```

如果保留它们，只能作为：

```text
legacy compatibility
route_hint provider
special old tests support
```

并且必须在代码里明确命名为 legacy，避免误用。

---

## 6. Agent Core Layer：AgentLoop 主链路

### 6.1 这块是做什么的

Jarvis 的发动机房。

负责：

```text
上下文构建
模型调用
工具调用解析
工具执行
observation 回灌
retry / replan / stop
final answer
summary
AgentRunResult
```

### 6.2 Jarvis 目标文件

```text
src/jarvis/agent/loop.py
src/jarvis/agent/types.py
src/jarvis/agent/model.py
src/jarvis/agent/context.py
src/jarvis/agent/tools.py
src/jarvis/agent/retry.py
src/jarvis/agent/summary.py
src/jarvis/agent/events.py
```

### 6.3 可参考 agent

#### Codex

参考内容：

```text
codex-rs/core/src/codex.rs
codex-rs/core/src/conversation_manager.rs
codex-rs/core/src/protocol.rs
codex-rs/core/src/openai_tools.rs
codex-rs/core/src/exec.rs
codex-rs/core/src/safety.rs
```

借鉴点：

```text
run turn
model response item
tool call / exec request
approval request
observation append
final assistant message
```

Codex 对 Jarvis 的意义：

```text
AgentLoop 应该是主路径
不是 router/dispatcher 的附属品
```

#### Hermes

参考内容：

```text
hermes_agent/
ui-tui/src/app/turnController.ts
ui-tui/src/app/turnStore.ts
```

借鉴点：

```text
turn state
pending tools
active tools
stream segments
reasoning/tool events
```

### 6.4 旧代码清理要求

如果当前还有：

```text
core AgentToolLoop
tool_loop_adapter
旧 execute_agent_tool_loop
旧 dispatcher 直接跑工具
```

它们应逐步被：

```text
src/jarvis/agent/loop.py
src/jarvis/agent/tools.py
ToolCallExecutor
```

替换。

清理策略：

```text
Phase 1:
- interactive 默认走新 AgentLoop。
- old AgentToolLoop 只作为 fallback。

Phase 2:
- benchmark / CLI tests 不再依赖 old AgentToolLoop。

Phase 3:
- 删除或 deprecated old AgentToolLoop adapter。
```

---

## 7. Tool / Skill Layer：工具与技能层

### 7.1 这块是做什么的

负责工具注册、工具执行、技能执行、工具结果标准化。

工具包括：

```text
repo_reader
file_editor
command_runner
test_runner
web_search
skill_runner
mcp_adapter
```

### 7.2 Jarvis 目标文件

```text
src/jarvis/agent/tools.py
src/jarvis/core/tools/
src/jarvis/core/tools/runtime/
src/jarvis/core/tools/registry/
src/jarvis/core/skills/
skills/
```

### 7.3 可参考 agent

#### Codex

参考内容：

```text
codex-rs/core/src/openai_tools.rs
codex-rs/core/src/exec.rs
codex-rs/core/src/apply_patch.rs
codex-rs/core/src/safety.rs
```

借鉴点：

```text
工具 schema
exec command
apply patch
工具执行安全边界
```

#### Claude Code

参考内容：

```text
plugins/hookify/hooks/pretooluse.py
plugins/hookify/hooks/posttooluse.py
plugins/security-guidance/hooks/
examples/hooks/
```

借鉴点：

```text
PreToolUse / PostToolUse
allowed-tools
permission hooks
安全提示
```

#### OpenClaw

参考内容：

```text
skills/
src/tui/components/tool-execution.ts
src/tui/tui-event-handlers.ts
```

借鉴点：

```text
skills 作为模块化能力
tool execution component
tool start / update / result lifecycle
```

### 7.4 旧代码清理要求

不要出现多套工具执行器长期并存：

```text
AgentLoop ToolCallExecutor
core AgentToolLoop
dispatcher execute tool
skill runner direct call
```

最终统一：

```text
ToolRegistry 负责注册
ToolCallExecutor 负责执行
PolicyGate 负责是否允许
Renderer 负责展示
```

---

## 8. Policy / Approval / Safety Layer：安全与审批层

### 8.1 这块是做什么的

阻止危险动作：

```text
读 .env
打印 API key
删除项目
外传 secret
危险 shell
写文件
运行命令
```

### 8.2 Jarvis 目标文件

```text
src/jarvis/core/policy/
src/jarvis/core/safety/
src/jarvis/core/tools/runtime/safety*
src/jarvis/agent/loop.py
src/jarvis/agent/tools.py
```

### 8.3 可参考 agent

#### Claude Code

参考内容：

```text
plugins/hookify/hooks/pretooluse.py
plugins/hookify/hooks/posttooluse.py
plugins/security-guidance/hooks/security_reminder_hook.py
examples/hooks/bash_command_validator_example.py
```

借鉴点：

```text
工具调用前检查
工具调用后记录
危险命令拦截
安全提醒
```

#### Codex

参考内容：

```text
codex-rs/core/src/safety.rs
codex-rs/core/src/exec.rs
codex-rs/core/src/approvals.rs
```

借鉴点：

```text
approval mode
sandbox
命令执行权限
编辑权限
```

### 8.4 旧代码清理要求

安全相关旧逻辑不要分散在：

```text
cli.py
dispatcher.py
routing.py
tool_loop_adapter.py
AgentLoop
```

最终应收敛到：

```text
SafetyPrecheck
SafetyGate
ApprovalGate
SecretRedaction
```

敏感请求应变成：

```json
{
  "output_type": "refusal",
  "stop_reason": "safety_refusal",
  "final_answer": "不能直接打印 .env 内容..."
}
```

---

## 9. Event / Trace Layer：事件与轨迹层

### 9.1 这块是做什么的

记录每轮发生了什么：

```text
turn_started
model_call_started
model_call_completed
tool_call_started
tool_call_completed
observation_added
final_answer_created
summary_created
turn_completed
```

### 9.2 Jarvis 目标文件

```text
src/jarvis/agent/events.py
src/jarvis/agent/loop.py
src/jarvis/agent/summary.py
src/jarvis/core/replay/
src/jarvis/core/evidence/
```

### 9.3 可参考 agent

#### Hermes

参考内容：

```text
ui-tui/src/app/createGatewayEventHandler.ts
ui-tui/src/app/turnStore.ts
ui-tui/src/app/turnController.ts
ui-tui/src/components/thinking.tsx
ui-tui/src/components/streamingAssistant.tsx
```

借鉴点：

```text
event -> turn state -> renderer
active tools
pending tools
tool trail
details mode
```

#### OpenClaw

参考内容：

```text
src/tui/tui-event-handlers.ts
src/tui/tui-stream-assembler.ts
src/tui/components/chat-log.ts
```

借鉴点：

```text
ChatEvent / AgentEvent
tool stream
assistant stream
final event
```

#### Codex

参考内容：

```text
codex-rs/tui/src/chatwidget.rs
codex-rs/tui/src/app/event_dispatch.rs
codex-rs/tui/src/history_cell.rs
```

借鉴点：

```text
protocol event -> history cell
exec begin/end
mcp tool begin/end
reasoning summary
```

### 9.4 旧代码清理要求

如果旧 replay/evidence 和新 AgentEvent 并存，要建立映射：

```text
AgentEvent -> ReplayStore
AgentEvent -> EvidenceStore
AgentEvent -> CLI Trace
```

不要让旧 replay 自己再定义一套独立事件模型。

---

## 10. Output Layer：CLI / JSON / Web Renderer

### 10.1 这块是做什么的

把 `AgentRunResult` 渲染为用户可见输出。

支持：

```text
default
quiet
verbose
trace
json
web cards
```

### 10.2 Jarvis 目标文件

```text
jarvis/cli_agent_output.py
jarvis/cli.py
web renderer 相关文件
API response schema
```

### 10.3 可参考 agent

#### Hermes

参考内容：

```text
ui-tui/src/components/messageLine.tsx
ui-tui/src/components/streamingAssistant.tsx
ui-tui/src/components/thinking.tsx
ui-tui/src/components/markdown.tsx
ui-tui/src/components/streamingMarkdown.tsx
```

借鉴点：

```text
assistant message
tool trail
thinking/details
streaming markdown
```

#### Codex

参考内容：

```text
codex-rs/tui/src/history_cell.rs
codex-rs/tui/src/exec_cell/render.rs
codex-rs/tui/src/diff_render.rs
codex-rs/tui/src/markdown.rs
codex-rs/tui/src/snapshots/
```

借鉴点：

```text
assistant message cell
exec output cell
diff render
snapshot tests
```

#### OpenClaw

参考内容：

```text
src/tui/components/chat-log.ts
src/tui/components/assistant-message.ts
src/tui/components/tool-execution.ts
src/tui/tui-formatters.ts
```

借鉴点：

```text
assistant message component
tool execution component
sanitize text
final fallback
```

### 10.4 旧代码清理要求

旧输出函数如果直接消费 routing result / dispatcher result，要逐步改成消费：

```text
AgentRunResult
LocalCommandResult
```

不要让 renderer 同时支持太多旧结构。  
兼容适配器可以短期存在，但必须有删除计划。

---

## 11. Clarification as Output：澄清输出层

### 11.1 这块是做什么的

把 clarification 从旧路由模块迁移为 Agent 输出。

### 11.2 Jarvis 目标文件

```text
src/jarvis/agent/types.py
src/jarvis/agent/loop.py
src/jarvis/agent/summary.py
jarvis/cli_agent_output.py
tests/agent/test_agent_output_type.py
tests/cli/test_no_bad_clarification_output.py
```

### 11.3 可参考 agent

不要找独立 `clarification.py`。四个参考 agent 的共同模式是：

```text
clarification 是 assistant response / agent output
不是 front-path router
```

#### Codex / Claude Code

借鉴：

```text
模型需要更多信息时，直接在 assistant final answer 里问。
```

#### Hermes / OpenClaw

借鉴：

```text
作为 event / final response 的一种输出状态。
```

### 11.4 Jarvis 落地形式

```json
{
  "output_type": "clarification",
  "stop_reason": "needs_user_clarification",
  "final_answer": "我需要确认一下：你希望我读取哪个文件？"
}
```

### 11.5 旧代码清理要求

这是硬要求：

```text
clarification.py 不应长期 deprecated 后残留。
```

清理节奏：

```text
Phase 2:
- 主路径不再调用 clarification.py。
- tests 不再依赖旧默认澄清句。

Phase 3:
- 删除 clarification.py。
- 如果有极少数兼容需求，保留 deprecated stub，但必须无主路径 import。
- ripgrep 验收：主路径引用为 0。
```

---

## 12. Benchmark / Evaluation Layer：测试验收层

### 12.1 这块是做什么的

保证架构不跑偏。

### 12.2 Jarvis 目标文件

```text
benchmarks/run_benchmark.py
benchmarks/export_answer_checklist.py
benchmarks/suites/
tests/agent/
tests/cli/
tests/routing/
tests/benchmark/
```

### 12.3 可参考 agent

#### Codex

参考内容：

```text
codex-rs/tui/src/snapshots/
codex-rs/core tests
```

借鉴点：

```text
snapshot 固定 CLI 输出
tool / exec 输出样式不轻易退化
```

#### Hermes

借鉴点：

```text
event / details mode 测试
tool trail 测试
```

#### Claude Code

借鉴点：

```text
permissions / hooks 测试
slash command 行为测试
```

#### OpenClaw

借鉴点：

```text
event / skill / gateway 行为测试
```

### 12.4 必测输入

```text
/help
/hlep
你是什么模型
你能帮我写代码吗
读取 README.md
列一下当前目录
打印我的 .env
帮我弄一下
```

---

## 13. Legacy Cleanup Layer：旧代码清理层

### 13.1 这块是做什么的

专门防止旧代码降级后长期残留。

这是你特别补充的原则，必须写成独立层：

```text
旧的、已经被替换的代码，要尽快删掉。
不能只是降级。
不能让 legacy fallback 成为永久旁路。
```

### 13.2 为什么不能长期保留旧代码

长期保留会导致：

```text
1. interactive 和 one-shot 继续双轨。
2. tests 继续依赖旧 dispatcher。
3. 新 AgentLoop 行为被旧 fallback 掩盖。
4. clarification.py 虽然不在主路径，但仍可能被间接调用。
5. Codex 后续施工不知道该改哪条路。
6. bug 修到旧路径，新路径不受益。
```

### 13.3 旧代码处理规则

每个被替换模块必须有状态：

```text
active
legacy_fallback
deprecated
deleted
```

每个 Phase 结束必须输出：

```text
Legacy cleanup report
- 哪些旧路径已不再主路径调用
- 哪些旧函数仍被测试依赖
- 哪些旧文件下一 Phase 删除
- 哪些调用点必须迁移
```

### 13.4 删除优先级

| 优先级 | 旧代码 | 处理 |
|---|---|---|
| P0 | 错误 clarification 默认句 | 立即禁止输出 |
| P0 | clarification.py 主路径调用 | Phase 2 前移除 |
| P1 | interactive natural dispatcher | Phase 1 后退出默认路径 |
| P1 | core AgentToolLoop adapter | 新 AgentLoop 稳定后删除 |
| P2 | legacy route final answer | route_hint 化 |
| P2 | duplicate renderers | 收敛到 cli_agent_output |
| P3 | old tests relying on legacy | 改成 AgentRunResult tests |

---

## 14. Jarvis Mapping Table

| Jarvis 拼图 | 做什么 | 架构层 | 参考 agent | 参考代码 | 落地文件 | Phase | 旧代码清理 |
|---|---|---|---|---|---|---|---|
| Interactive non-slash input | 普通输入进 AgentLoop | Entry / Agent Input | Codex, Claude Code | `codex-rs/core/src/codex.rs`, `.claude/commands` | `jarvis/cli.py` | Phase 1 | 旧 natural dispatcher 退出默认路径 |
| Slash command | 本地控制命令 | Control Layer | Claude Code, OpenClaw | `.claude/commands`, `src/cli/command-catalog.ts` | `jarvis/cli_commands.py` | Phase 1 | command 中禁止普通 fallback |
| AgentLoop | turn 主循环 | Agent Core | Codex | `codex-rs/core/src/codex.rs` | `src/jarvis/agent/loop.py` | Phase 1/2 | old AgentToolLoop adapter 后续删除 |
| Tool executor | 工具执行 | Tool Layer | Codex, Claude Code | `openai_tools.rs`, hooks | `src/jarvis/agent/tools.py` | Phase 2+ | 多套 executor 收敛 |
| Safety refusal | 安全拒绝 | Policy Layer | Claude Code, Codex | hooks, `safety.rs` | `loop.py`, `safety.py` | Phase 2 | 分散安全逻辑收敛 |
| Tool trail | 工具轨迹展示 | Output/Event | Hermes, OpenClaw | `thinking.tsx`, `tool-execution.ts` | `cli_agent_output.py`, `events.py` | Phase 4 | 旧 renderer 删除 |
| Clarification output | 澄清作为输出 | Output Layer | Codex/Claude style | assistant final response | `types.py`, `loop.py` | Phase 2 | `clarification.py` Phase 3 删除 |
| Benchmark checklist | 验收 | Evaluation | Codex snapshots | snapshots | `benchmarks/`, `tests/` | All | 旧路径 tests 迁移 |

---

## 15. 给 Codex 的下一步施工 Prompt

```text
请根据 docs/architecture/jarvis_target_agent_architecture.md 和 docs/cli/interactive_cli_path_audit.md，
新增 docs/architecture/reference_agents/ 参考映射包。

本轮目标：
不是改主逻辑，而是把 Codex / Claude Code / OpenClaw / Hermes 的可借鉴部分，明确映射到 Jarvis 的每个架构拼图上。
同时新增 Phase 1 施工清单，准备下一轮把 interactive 非 slash 输入接到 AgentLoop。

请新增目录：
docs/architecture/reference_agents/

请新增文件：
1. docs/architecture/reference_agents/README.md
2. docs/architecture/reference_agents/codex_cli_turn_loop_notes.md
3. docs/architecture/reference_agents/claude_code_cli_control_notes.md
4. docs/architecture/reference_agents/openclaw_control_surface_notes.md
5. docs/architecture/reference_agents/hermes_tool_trail_renderer_notes.md
6. docs/architecture/reference_agents/jarvis_mapping_table.md

每个文件必须说明：
1. 这块是做什么的
2. 位于 Jarvis 架构哪一层
3. 参考哪个 agent 的哪些代码路径
4. 借鉴点是什么
5. 不要照抄什么
6. 最终落到 Jarvis 哪些文件
7. 对应哪个 Phase
8. 被替换旧代码的删除计划

特别要求：
旧的、已经被替换的代码不能只是降级保留。
所有 legacy fallback 必须有删除 Phase。
所有被替换代码必须在 jarvis_mapping_table.md 中写明：
- 当前状态
- 替代模块
- 删除时间点
- 验收方式

新增：
docs/cli/phase1_interactive_agentloop_migration_plan.md

该文件必须包含：
1. 要改的文件：
   - jarvis/cli.py
   - jarvis/cli_agent_output.py
   - tests/cli/test_interactive_shell_agent_path.py
   - tests/cli/test_no_bad_clarification_output.py

2. 要读但尽量不改的文件：
   - src/jarvis/agent/loop.py
   - src/jarvis/agent/types.py
   - src/jarvis/core/routing/clarification.py
   - src/jarvis/core/cli_response/dispatcher.py

3. 目标路径：
   - slash command -> LocalCommandDispatcher
   - non-slash natural input -> AgentLoop.run_turn()

4. 不做的事情：
   - 不删除 clarification.py
   - 不重写 routing
   - 不重写 benchmark
   - 不做降循环率优化

5. 旧代码清理预案：
   - Phase 1 后旧 natural dispatcher 退出默认路径
   - Phase 2 后 clarification.py 不再主路径调用
   - Phase 3 删除 clarification.py 或仅保留 deprecated stub
   - old AgentToolLoop adapter 后续收敛到 AgentLoop ToolCallExecutor

6. 预期测试：
   - /help 本地
   - /hlep did you mean
   - 你是什么模型 不澄清
   - 你能帮我写代码吗 不澄清
   - 读取 README.md 走 AgentLoop
   - 列一下当前目录 走 AgentLoop
   - 打印我的 .env 不泄露
   - 帮我弄一下 可以 clarification，但不能出现旧默认句

本轮不要改主逻辑，不删除 clarification.py。

验收：
1. 参考 agent 映射资料生成。
2. Phase 1 施工清单生成。
3. 每块拼图说明了“做什么 / 在哪层 / 参考谁 / 参考代码 / 落到哪 / Phase / 旧代码删除计划”。
4. 不破坏现有测试。
```

---

## 16. 总结

这份文档要告诉 Codex 的不是“去参考四个 agent”，而是：

```text
Codex 的 turn loop 放到 AgentCore
Claude Code 的 slash command 放到 Control Surface
OpenClaw 的 skills/events 放到 Control/Event layer
Hermes 的 tool trail 放到 Output/Event layer
旧 routing/clarification 被替换后必须删除，不允许长期残留
```

最终目标非常明确：

```text
Jarvis 不要双轨。
Jarvis 不要 clarification.py 抢跑。
Jarvis 不要旧代码阴魂不散。
Jarvis 要成为 AgentLoop 主导的 coding assistant。
