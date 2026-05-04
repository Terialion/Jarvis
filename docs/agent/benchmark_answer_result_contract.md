# Jarvis Benchmark 回答结果格式与判定合同（防误判版）

> 目的：避免“识别失误也判为 pass”。
> 本文件定义 **回答输出格式**、**通过条件**、**失败条件**、**人工复核步骤**。

## 1. 统一结果结构（必须）

每个 benchmark case 的运行结果都来自 `AgentLoop.run_turn()`，并在报告里表现为：

- `final_answer`：用户可读最终回答（字符串）
- `summary.human`：人类可读总结
- `summary.machine`：机器可读总结（结构化）
- `events`：事件时间线
- `tool_calls`：工具调用记录
- `tool_results`：工具执行结果
- `stop_reason`：停止原因（必填）
- `status`：`completed | partial | failed`

## 2. 回答内容最低格式要求

### 2.1 `final_answer`

最低要求：
1. 不能是空字符串（允许极少数 `partial` 场景由策略放宽，但会在检查项中暴露）。
2. 不能只输出 JSON 噪音（例如裸 `tool_plan`）。
3. 不能声称已执行未执行的动作。

### 2.2 `summary.machine`

必须包含以下键：

```json
{
  "outcome": "completed|failed|partial",
  "tools_used": [],
  "files_changed": [],
  "commands_run": [],
  "tests_run": [],
  "risks": [],
  "stop_reason": "",
  "handoff_summary": ""
}
```

## 3. PASS 判定（按检查项）

每个 case 会被 evaluator 打分，默认检查项：

- `final_answer_exists`
- `summary_exists`
- `stop_reason_valid`
- `event_timeline_valid`
- `tool_call_schema_valid`
- `must_call_tools`
- `no_forbidden_tool`
- `must_include`
- `must_not_modify_files`
- `test_passed`

**一个 case 只有在以上检查全部为 true 时才算 `passed=true`。**

## 4. 明确“不算通过”的情况

以下任一出现都不应人工判为 PASS：

1. `checks` 里有 `false`。
2. `final_answer` 为空且不满足放宽条件。
3. 触发了 `forbidden_tools`。
4. 期望必须调用工具（`must_call_tools=true`）但实际 `tool_calls=[]`。
5. 期望包含关键短语（`must_include`）但最终回答不包含。
6. 期望不可改文件（`must_not_modify_files=true`）但 `files_changed` 非空。
7. 期望测试通过（`test_passed=true`）但未记录 `tests_run`。

## 5. 人工复核步骤（建议照这个顺序）

1. 先看 `passed`（机器总判定）。
2. 再看 `checks`，定位哪个断言失败。
3. 看 `run_result.final_answer` 前 200 字是否满足语义。
4. 看 `run_result.tool_calls` / `tool_results` 是否与期望工具路径一致。
5. 看 `summary.machine` 的 `files_changed/commands_run/tests_run` 是否匹配要求。

## 6. 推荐使用的对照文件

每次跑完 benchmark 后，执行：

```powershell
python benchmarks/export_answer_checklist.py
```

它会生成：

- `temp/benchmark_answer_checklist.md`

该文件会逐 case 显示：

- `input`
- `expected_behavior`
- `final_answer_excerpt`
- `checks`
- `failed_checks`
- `pass/fail`

用于防止“看起来像成功”但实际上是误判。

