# 05. Jarvis 目标架构与代码落点

## 新增目录

```text
src/jarvis/agent/
├── __init__.py
├── types.py      # 数据协议
├── events.py     # runtime event sink
├── context.py    # thread/history/context builder
├── model.py      # provider adapter + streaming
├── tools.py      # ToolSpec/ToolExecutor bridge
├── loop.py       # AgentLoop.run_turn
└── summary.py    # ResponseComposer/SummaryComposer
```

## 复用 Jarvis 已有模块

| 已有模块 | 用法 |
|---|---|
| `src/jarvis/core/task_runtime.py` | 继续记录 task/step/artifact，但不要作为唯一 session history |
| `src/jarvis/core/react_readiness/heavy_runtime.py` | 作为 coding task fallback/subroutine，不再作为 chat 主循环 |
| `src/jarvis/core/react_readiness/replay_store.py` | 记录 AgentEvent，同时保留 replay export |
| `src/jarvis/core/react_readiness/context_manager.py` | 可被 ContextBuilder 包装 |
| `src/jarvis/core/memory/store.py` | 作为长期/项目记忆底座 |
| `src/jarvis/core/skill_harness/*` | 转成模型可见 ToolSpec |
| `src/jarvis/core/policy/*` + hooks | 接入每次 ToolCall 前后 |

## 最小调用链

```python
agent = AgentLoop(
    model_client=RuntimeModelClient(...),
    tool_executor=ToolExecutor.from_jarvis_core(...),
    context_builder=ContextBuilder(...),
    summary_composer=SummaryComposer(...),
    event_sink=ReplayEventSink(...),
)
result = agent.run_turn(ChatInput(text="分析这个 repo", thread_id="..."))
```

## 最小验收

1. `AgentLoop.run_turn()` 支持无工具回答。
2. 支持模型输出一个 `ToolCall`，执行后把 `ToolResult` 回灌下一轮模型。
3. 支持工具失败，失败 observation 进入下一轮。
4. 支持 summary 输出：结论、工具、证据、改动、测试、风险。
5. 支持 ThreadStore 持久化至少 JSONL。