# 00. Jarvis 与四个 Agent 的差距-参考矩阵

| 链路 | Jarvis 当前缺口 | 参考 agent | 参考代码/文档 | Jarvis 修改点 |
|---|---|---|---|---|
| Input / Turn | CLI/API/Web 入口未统一成 ChatInput/TurnInput | Codex | `codex-rs/app-server-protocol/src/lib.rs`, `app-server/src/thread_state.rs`, `core/src/session/turn.rs` | 新增 `src/jarvis/agent/types.py`，定义 `ChatInput`, `Turn`, `AgentEvent` |
| Thread / History | TaskRuntime 是内存态任务记录，不是完整线程历史 | Codex / OpenClaw | `core/src/message_history.rs`, `docs/reference/session-management-compaction.md` | 新增 `ThreadStore`，优先 JSONL，后续 SQLite |
| Chat Loop | 缺 chat-first `run_turn()` | Codex | `core/src/session/turn.rs` | 新增 `AgentLoop.run_turn()`，把模型输出和工具结果循环起来 |
| Model Streaming | provider 有，但未统一 streaming/reasoning/tool events | Codex / Hermes | `core/src/session/turn.rs`, `agent/transports/*`, `agent/copilot_acp_client.py` | 新增 `ModelClient.stream()` 统一接口 |
| Tool Schema | Skill 多，但缺统一 ToolSpec/ToolCall/ToolResult | Codex / Hermes | `core/src/function_tool.rs`, `core/src/mcp_tool_call.rs`, `acp_adapter/tools.py` | 新增 `tools.py` 中 `ToolRegistryAdapter`, `ToolExecutor` |
| Native ToolCall | HeavyRuntime 以 if-else + 固定 plan 为主 | Codex / Hermes | `mcp_tool_call.rs`, `copilot_acp_client.py` | 让 LLM 产出 `ToolCall`，executor 再分发到 Jarvis 已有工具 |
| ReAct | 有 skeleton/HeavyRuntime，但动态计划不足 | Hermes / Codex | `context_engine.py`, `error_classifier.py`, `session/turn.rs` | `AgentLoop` 中处理 tool_result 后继续 model step |
| Retry/Rethink | 有 rethink 种子，但未模型化 replan | Hermes | `error_classifier.py`, `context_compressor.py` | 工具失败时生成诊断 observation，交给模型 replan |
| Context/Summary | 有 ContextManager/compactor，但未接入 turn loop | Codex / Hermes / OpenClaw | `compact.rs`, `context_compressor.py`, `session-management-compaction.md` | 新增 `ContextBuilder`, `SummaryComposer` |
| UI/Event | Web UI 控制台雏形，缺 turn timeline/tool cards | Codex / OpenClaw / Hermes ACP | `event_mapping.rs`, `acp_adapter/events.py`, `docs/concepts/agent-loop.md` | 新增 `events.py`，统一事件流 |
| Approval | 有风险矩阵和 hooks，但未贴到每次 ToolCall | Claude Code / Codex / OpenClaw | `settings-strict.json`, `bash_command_validator_example.py`, `mcp_tool_call.rs`, `exec-approvals.md` | `ToolExecutor.before_execute()` 接 ApprovalRiskMatrix/HookExecutor |
| Skills | Jarvis skill harness 已有，但需模型可见 catalog | Claude Code / OpenClaw | `skill-development/SKILL.md`, `docs/tools/skills.md` | Skill 转 ToolSpec：描述、参数、权限、dry-run |