# 02. Hermes 参考重点

Hermes 最值得借鉴的是：**多 provider 适配、上下文压缩、错误分类与恢复、ACP/tool event 表达**。

## 关键参考点

1. `context_engine.py` 和 `context_compressor.py` 提供了“何时压缩、如何压缩、压缩后如何恢复”的工程规则。
2. `error_classifier.py` 把 API/上下文/网络/权限错误分类成不同恢复动作，而不是统一失败。
3. `copilot_acp_client.py` 中通过 `<tool_call>{...}</tool_call>` 从文本中抽取工具调用，这是一个兼容 fallback 的思路。
4. `acp_adapter/tools.py` 把工具调用映射成 UI/协议可展示的 ToolCallStart/Progress。
5. `shell_hooks.py` 类似 Claude Code hook，可以作为 Jarvis HookExecutor 的参考。

## Jarvis 可借鉴的结构

```text
Model error / tool error
  -> ErrorClassifier
  -> retry | compress | fallback provider | user-visible failure
```

对应到 Jarvis：

```text
ToolExecutor.execute()
  -> ToolResult(ok=False, error_type=...)
  -> AgentLoop adds observation
  -> model sees failure and replans
  -> SummaryComposer records failure and recovery path
```