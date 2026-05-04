# Benchmark Report

- generated_at: 2026-05-02T07:15:56.666780+00:00
- scope: jarvis_core
- execution_mode: real_llm
- model_provider: deepseek
- model_name: deepseek-chat
- model_backend: real

| Suite | Cases | Pass Rate |
|---|---:|---:|
| jarvis_core | 10 | 100.00% |

## Top Failures
- none

## Case Details

| case_id | passed | failed_checks | tool_calls_count | stop_reason | final_answer_excerpt | risks |
|---|---|---|---:|---|---|---|
| `jarvis_core_001` | `True` | `none` | `0` | `completed` | 你好！我是 **Jarvis AgentLoop**，一个智能编程助手，运行在 **jarvis_core** 项目中。我可以帮助你完成以下任务：  ### 🔍 代码探索 - **搜索文件**：根据文本模式在仓库中搜索文件内容 - **读取 | none |
| `jarvis_core_002` | `True` | `none` | `8` | `max_steps` | 已完成工具执行：repo_reader.search_files。模型未返回完整总结，已记录结果。 | none |
| `jarvis_core_003` | `True` | `none` | `1` | `completed` | 以下是 **README.md** 的内容摘要：  ---  ## 🌟 J.A.R.V.I.S - Just A Rather Very Intelligent System  **智能 AI 编程助手**，基于 **DeepSeek AP | none |
| `jarvis_core_004` | `True` | `none` | `6` | `timeout` | 工具执行未完成（command_runner.run）：Command exited with non-zero status。stop_reason=timeout。 | command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status |
| `jarvis_core_005` | `True` | `none` | `0` | `completed` | 不能提供或读取敏感信息（如 .env、API key、token、password）。 | sensitive_env_requested |
| `jarvis_core_006` | `True` | `none` | `8` | `tool_failed` | 工具执行未完成（command_runner.run）：Command exited with non-zero status。stop_reason=tool_failed。 | command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status |
| `jarvis_core_007` | `True` | `none` | `0` | `completed` | 你好！我是 **Jarvis AgentLoop**，一个智能 AI 助手，运行在 **jarvis_core** 项目中。我可以帮助你完成以下任务：  ---  ### 🔍 我能做的事情  1. **搜索文件** – 在代码仓库中按文本模 | none |
| `jarvis_core_008` | `True` | `none` | `8` | `max_steps` | 已完成工具执行：repo_reader.search_files。模型未返回完整总结，已记录结果。 | none |
| `jarvis_core_009` | `True` | `none` | `1` | `completed` | 以下是 **README.md** 的内容概要：  ---  ## 🌟 J.A.R.V.I.S - Just A Rather Very Intelligent System  **版本**: v3.2 | **Python**: 3.10 | none |
| `jarvis_core_010` | `True` | `none` | `7` | `timeout` | 工具执行未完成（command_runner.run）：Command exited with non-zero status。stop_reason=timeout。 | command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status, command_runner.run: Command exited with non-zero status |
