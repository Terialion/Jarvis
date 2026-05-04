# Jarvis Agent 参考代码摘要包

这个包不是把 Codex / Claude Code / Hermes / OpenClaw 代码硬拷进 Jarvis，而是把四个 agent 中最值得借鉴的关键链路摘出来，翻译成 Jarvis 的改造落点。

## 包结构

```text
jarvis_agent_reference_pack/
├── README.md
├── 00_gap_to_reference_matrix.md
├── 01_codex_reference.md
├── 02_hermes_reference.md
├── 03_openclaw_reference.md
├── 04_claude_code_reference.md
├── 05_jarvis_target_architecture.md
├── 06_codex_construction_prompt.md
├── reference_index.json
├── snippets/
│   ├── codex_key_snippets.md
│   ├── hermes_key_snippets.md
│   ├── openclaw_key_snippets.md
│   └── claude_code_key_snippets.md
└── blueprints/src/jarvis/agent/
    ├── types.py
    ├── loop.py
    ├── model.py
    ├── context.py
    ├── tools.py
    ├── events.py
    ├── summary.py
    └── __init__.py
```

## 施工目标一句话

把 Jarvis 从“TaskRuntime + HeavyReActRuntime + SkillHarness 零件仓”升级成：

```text
ChatInput
  -> Thread/Turn
  -> context build
  -> model stream
  -> native tool_call
  -> approval + ToolExecutor
  -> tool_result observation
  -> ReAct continue
  -> ResponseComposer
  -> persisted summary/history/events
```

## 使用方法

1. 把这个包解压到 Jarvis 仓库外部或 `docs/reference/agent_ref_pack/`。
2. 让 Codex 先读：
   - `06_codex_construction_prompt.md`
   - `05_jarvis_target_architecture.md`
   - `00_gap_to_reference_matrix.md`
3. 然后让 Codex 根据 `blueprints/src/jarvis/agent/` 新增或改写 Jarvis 模块。
4. 强制 Codex 先复用 Jarvis 已有模块：`TaskRuntime`、`HeavyReActRuntime`、`SkillHarness`、`PersistentMemoryStore`、`ReplayStore`、`HookExecutor`、`ApprovalRiskMatrix`。

## 重要原则

- 不要把 Rust/TS/Python 异构代码机械移植。
- 只借鉴架构协议、事件流、工具调用语义、上下文压缩策略、审批边界。
- Jarvis 的落地语言和模块边界保持 Python。
- 先完成最小 chat-agent loop，再扩展 UI、MCP、browser、subagent。