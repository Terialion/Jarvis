# 03. OpenClaw 参考重点

OpenClaw 最值得借鉴的是：**会话路由、队列、gateway、多端消息、agent loop 生命周期文档化**。

## 关键参考点

1. `docs/concepts/agent-loop.md` 明确把 agent loop 定义为 intake → context assembly → model inference → tool execution → streaming replies → persistence。
2. `docs/concepts/queue.md` 强调同一 session 串行运行，避免多个 agent run 撞同一个 transcript。
3. `docs/concepts/messages.md` 把 inbound message 到 outbound reply 的链路讲清楚。
4. `docs/reference/session-management-compaction.md` 说明 session store、transcript JSONL、compaction、silent housekeeping。
5. `docs/tools/exec-approvals.md` 和 `docs/tools/skills.md` 是 Jarvis 安全/skill 体系的好模板。

## Jarvis 可借鉴的结构

```text
Inbound message
  -> resolve session key
  -> session queue
  -> agent run
  -> streaming events
  -> transcript persistence
  -> outbound reply
```

对应到 Jarvis：

```text
ChatInput
  -> ThreadStore.resolve_or_create()
  -> AgentQueue.acquire(thread_id)
  -> AgentLoop.run_turn()
  -> EventSink.emit()
  -> ResponseComposer.final_answer
```