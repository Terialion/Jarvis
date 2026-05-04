# Jarvis CLI Output Contract (AgentLoop)

本文件定义 `python -m jarvis.cli --ask "<prompt>"` 的输出合同，便于人工验收和自动测试。

## 推荐入口

推荐使用 one-shot：

```bash
python -m jarvis.cli --ask "<prompt>" --output default
```

位置参数 `python -m jarvis.cli "<prompt>"` 当前默认仍走 legacy 路径。  
如果需要切到新 one-shot 渲染，可设置：

```bash
JARVIS_CLI_AGENT_ONESHOT=1
```

## 1) default

必须包含：
- `Jarvis`
- 最终回答文本
- 若有工具调用，显示“工具摘要”

行为：
- 默认不显示 `LLM provider` / `Status` / `Summary` / `Trace`。
- 仅当 `stop_reason` 非 `completed|success` 时显示 `stop_reason`。
- 不打印 API key 明文。

## 2) quiet

必须包含：
- 仅最终回答文本。

必须不包含：
- `LLM provider:`
- `Tool calls`
- `Summary`
- `Trace`

## 3) verbose

在 `default` 基础上增加：
- `Runtime`
- `LLM provider: ...`
- `status=...`
- `stop_reason=...`
- `Summary`
- `outcome=...`
- `tools_used=...`
- 可选：`commands_run=...`、`tests_run=...`、`risks=...`

## 4) trace

在 `verbose` 基础上增加：
- `Trace`
- 事件列表（例如 `model_call_started` / `tool_call_started` / `tool_call_completed`）。

## 5) json

输出必须是合法 JSON，对象顶层字段：
- `result`

`result` 至少包含：
- `status`
- `stop_reason`
- `final_answer`
- `tool_calls_count`
- `tool_calls`
- `summary`
- `events`

网络错误场景下：
- `result.stop_reason=provider_network_error`
- `result.error.type` 存在
- `result.error.message` 为友好诊断文案

## 安全脱敏规则

输出中：
- 不得出现真实 API key。
- 类似 `sk-xxxxx` 必须脱敏为 `sk-****`。
- `token=...` / `api_key=...` / `password=...` 必须脱敏为 `...=****`。

## 验收最小命令

```bash
python -m pytest tests/cli/test_cli_output_modes.py -q
```
