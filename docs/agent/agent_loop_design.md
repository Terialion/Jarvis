# Jarvis AgentLoop Design

## Goal

Provide a chat-first, persisted, benchmarkable main loop:

`ChatInput -> Context -> Model -> ToolCall -> ToolResult -> ReAct Continue -> Final Answer -> Summary -> Persist`

## Main Modules

- `src/jarvis/agent/types.py`: runtime contracts (`ChatInput`, `ToolCall`, `ToolResult`, `AgentEvent`, `AgentRunResult`)
- `src/jarvis/agent/store.py`: JSONL session/turn/message/summary persistence
- `src/jarvis/agent/context.py`: history + memory recall + compaction adapter
- `src/jarvis/agent/model.py`: runtime provider adapter + fake model fallback
- `src/jarvis/agent/tools.py`: tool spec adapter and runtime executor bridge
- `src/jarvis/agent/retry.py`: error classifier + retry/replan decisions
- `src/jarvis/agent/summary.py`: human + machine summary composer
- `src/jarvis/agent/loop.py`: `AgentLoop.run_turn()`

## Reused Existing Jarvis Modules

- `core/tools/runtime.py` safety/permission/approval/hook chain
- `core/tools/schema.py` and `core/tools/registry.py`
- `core/repo_reader.py`, `core/file_editor.py`, `core/command_runner.py`, `core/test_runner.py`, `core/failure_analyzer.py`
- `core/memory/store.py`, `core/memory/retriever.py`
- `core/react_readiness/context_compactor.py`, `context_manager.py`, `replay_store.py`
- `core/skill_harness/registry.py`, `loader.py`, `matcher.py`, `executor.py`
- `core/policy/risk_matrix.py`, `core/hooks/registry.py`
- `core/llm/runtime_provider.py`

## Turn Flow

1. Create or resume session.
2. Create turn record.
3. Persist user message.
4. Build context messages (history + memory + tool info).
5. Call model.
6. If final answer: persist answer + summary and finish.
7. If tool calls: execute through `ToolCallExecutor` (safety/approval/policy active), persist results, append observation, continue.
8. On failure: classify and either retry or add replan hint.
9. Stop on completion, approval gate, timeout, no progress, or max steps.
10. Return `AgentRunResult` with event timeline and summary.

## Boundaries

- `AgentLoop` does not bypass `ToolRuntime`.
- Sensitive/dangerous actions are blocked by existing safety + approval chain.
- `AgentRunResult` always contains `summary` and `stop_reason`.

