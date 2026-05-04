# 06. 给 Codex 的施工 Prompt

你现在在 Jarvis 仓库中施工。请读取本参考包所有 Markdown，重点阅读：

1. `00_gap_to_reference_matrix.md`
2. `05_jarvis_target_architecture.md`
3. `blueprints/src/jarvis/agent/*.py`
4. Jarvis 现有代码：
   - `jarvis/cli.py`
   - `src/jarvis/core/task_runtime.py`
   - `src/jarvis/core/react_readiness/heavy_runtime.py`
   - `src/jarvis/core/react_readiness/react_loop.py`
   - `src/jarvis/core/react_readiness/replay_store.py`
   - `src/jarvis/core/react_readiness/context_manager.py`
   - `src/jarvis/core/react_readiness/working_memory.py`
   - `src/jarvis/core/memory/store.py`
   - `src/jarvis/core/skill_harness/`
   - `src/jarvis/core/hooks/`
   - `src/jarvis/core/policy/`

## 硬要求

如果 Jarvis 之前已经有相似实现，必须优先收编、适配、重构和增强，不要从零重写。若不复用，必须在代码注释或 PR summary 说明原因。

## 目标

新增 `src/jarvis/agent/`，实现 chat-first agent 主循环：

```text
ChatInput -> ContextBuilder -> ModelClient -> ToolCall -> ToolExecutor -> ToolResult -> ModelClient -> FinalAnswer -> Summary -> Persist
```

## 施工步骤

### Step 1: 数据协议

新增 `src/jarvis/agent/types.py`：

- `ChatInput`
- `ChatMessage`
- `TurnState`
- `ToolSpec`
- `ToolCall`
- `ToolResult`
- `AgentEvent`
- `AgentRunResult`

### Step 2: 事件系统

新增 `events.py`：

- `EventSink`
- `InMemoryEventSink`
- `ReplayEventSink`，尽量复用 `ReplayStore`

事件至少包括：

- `turn.started`
- `model.delta`
- `model.completed`
- `tool.started`
- `tool.completed`
- `tool.failed`
- `turn.completed`
- `turn.failed`

### Step 3: Context / Thread

新增 `context.py`：

- `JsonlThreadStore`
- `ContextBuilder`
- 支持按 thread_id 读取历史消息
- 支持压缩入口，先实现简单 tail-window，后续接 `ContextCompactor`

### Step 4: ModelClient

新增 `model.py`：

- 定义 `ModelClient` 抽象接口
- 实现 `MockModelClient` 供测试
- 实现 `RuntimeModelClient` 桥接 Jarvis 现有 runtime provider
- 输出统一 `ModelEvent` 或直接返回 `ModelResponse`

### Step 5: ToolExecutor

新增 `tools.py`：

- `ToolRegistryAdapter`：把 Jarvis tools/skills 转成 `ToolSpec`
- `ToolExecutor`：统一执行工具
- 执行前接入 `ApprovalRiskMatrix` 和 HookExecutor
- 执行后归一化成 `ToolResult`

### Step 6: AgentLoop

新增 `loop.py`：

- 实现 `AgentLoop.run_turn(chat_input)`
- 支持 max_model_steps / max_tool_calls / timeout
- 每次模型输出 tool_call 后执行工具，并把结果追加成 observation
- 直到模型输出 final answer 或触发 stop condition

### Step 7: SummaryComposer

新增 `summary.py`：

输出结构：

```json
{
  "answer": "...",
  "tools_used": [],
  "evidence": [],
  "changed_files": [],
  "tests": [],
  "risks": [],
  "stop_reason": "..."
}
```

### Step 8: CLI/API 接入

不要破坏现有 CLI。新增最小入口：

```bash
python -m jarvis.cli chat "分析这个 repo 的结构"
```

或在现有 task run 中增加 `--agent-loop` 开关。

### Step 9: 测试

新增测试：

- `tests/agent/test_types.py`
- `tests/agent/test_agent_loop_no_tool.py`
- `tests/agent/test_agent_loop_tool_call.py`
- `tests/agent/test_agent_loop_tool_failure_replan.py`
- `tests/agent/test_thread_store_jsonl.py`
- `tests/agent/test_summary_composer.py`

## 验收命令

```bash
python -m pytest tests/agent -q
python -m pytest tests/react_readiness tests/memory tests/core_v0 -q
python -m jarvis.cli chat "hello" --agent-loop --dry-run
```

## 输出要求

施工完成后输出：

1. 新增/修改文件列表
2. 复用旧实现列表
3. 未复用原因列表
4. 测试结果
5. 已知风险
6. 下一步建议