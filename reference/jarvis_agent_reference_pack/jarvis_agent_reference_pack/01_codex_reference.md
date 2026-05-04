# 01. Codex 参考重点

Codex 最值得 Jarvis 借鉴的是 **Turn 驱动的核心循环**，不是某个单独工具。

## 关键参考点

1. `run_turn()` 是主航道：把用户输入、上下文、技能注入、工具调用、自动压缩、模型响应、事件通知串成一个 turn。
2. `TurnContext` 把 turn 运行所需的环境、工具 gate、压缩提示、模型配置、审批等状态集中管理。
3. `message_history` 是跨 turn 的记忆基础，不把每轮任务孤立成临时对象。
4. `mcp_tool_call` 把工具调用做成有 begin/end/skip/approval 的一等事件。
5. `exec` 工具不是普通 subprocess，而是带 capture、sandbox、approval、event 的受控工具。

## Jarvis 可借鉴的结构

```text
Codex run_turn
  -> pre-sampling compact
  -> build initial input / skill injection
  -> model sampling
  -> parse ResponseItem
  -> dispatch tool call
  -> append FunctionCallOutput
  -> continue sampling
  -> turn completed / failed
```

对应到 Jarvis：

```text
AgentLoop.run_turn
  -> ContextBuilder.build()
  -> ModelClient.stream()
  -> ToolCall parser
  -> ToolExecutor.execute()
  -> ToolResult -> Observation
  -> continue until final answer / stop condition
  -> SummaryComposer
```

## 不要照搬

- 不要把 Rust session 模块直接翻译成 Python。
- 不要一开始实现完整 MCP 复杂逻辑。
- 先用 Jarvis SkillHarness/本地工具模拟 MCP ToolSpec。