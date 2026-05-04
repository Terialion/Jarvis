# Jarvis Agent 主链路 + Benchmark v0.1 联合施工说明书 v2

> 本版本修正重点：**必须显式读取 `jarvis_agent_reference_pack.zip` 参考代码摘要包**。  
> Codex 不能只按抽象说明施工，必须先解压参考包，阅读其中的 reference matrix、四个 agent 摘要、snippets 和 blueprints，再改 Jarvis。

---

## 0. 必须使用的输入材料

本次施工有两个强制输入：

```text
1. Jarvis 当前仓库代码
2. jarvis_agent_reference_pack.zip
```

其中 `jarvis_agent_reference_pack.zip` 是本次改造的参考代码摘要包，里面已经把 Codex / Hermes / OpenClaw / Claude Code 四个 agent 的关键参考逻辑整理成 Jarvis 可借鉴的工程材料。

Codex 必须先执行：

```bash
mkdir -p /tmp/jarvis_agent_reference_pack
unzip -o jarvis_agent_reference_pack.zip -d /tmp/jarvis_agent_reference_pack
find /tmp/jarvis_agent_reference_pack -maxdepth 4 -type f | sort
```

如果 zip 放在项目根目录，则：

```bash
mkdir -p reference/jarvis_agent_reference_pack
unzip -o jarvis_agent_reference_pack.zip -d reference/jarvis_agent_reference_pack
find reference/jarvis_agent_reference_pack -maxdepth 4 -type f | sort
```

如果 zip 不在项目根目录，Codex 需要根据实际路径定位。  
如果找不到该 zip，必须停止并报告：`missing_reference_pack`，不要凭空施工。

---

## 1. 参考代码包预期结构

参考包大致包含：

```text
├── jarvis_agent_reference_pack/
  ├── 00_gap_to_reference_matrix.md
  ├── 01_codex_reference.md
  ├── 02_hermes_reference.md
  ├── 03_openclaw_reference.md
  ├── 04_claude_code_reference.md
  ├── 05_jarvis_target_architecture.md
  ├── 06_codex_construction_prompt.md
  ├── README.md
  ├── blueprints/
    ├── src/
      ├── jarvis/
        ├── agent/
  ├── reference_index.json
  ├── snippets/
    ├── claude_code_key_snippets.md
    ├── codex_key_snippets.md
    ├── hermes_key_snippets.md
    ├── openclaw_key_snippets.md
```

如果实际结构略有差异，以解压后的真实文件为准。

---

## 2. 参考包里的文件必须怎么读

Codex 需要按以下顺序阅读：

### 2.1 总览文件

```text
README.md
00_gap_to_reference_matrix.md
reference_index.json
```

阅读目的：

- 理解 Jarvis 当前差距。
- 理解四个 agent 分别适合参考哪一段。
- 建立“差距 → 参考代码 → Jarvis 修改点”的索引。

### 2.2 四个 agent 参考摘要

```text
01_codex_reference.md
02_hermes_reference.md
03_openclaw_reference.md
04_claude_code_reference.md
```

阅读目的：

| 文件 | 必须提取的参考点 |
|---|---|
| `01_codex_reference.md` | `run_turn`、Thread/Turn、tool call loop、exec/patch policy、stream event |
| `02_hermes_reference.md` | OpenAI tool-calling loop、context compression、error classifier、retry/fallback |
| `03_openclaw_reference.md` | gateway/session/event lifecycle、skills/runtime、queue、UI timeline |
| `04_claude_code_reference.md` | hooks、permissions、allowed tools、CLI coding tool UX、final summary |

### 2.3 snippets

```text
snippets/codex_key_snippets.md
snippets/hermes_key_snippets.md
snippets/openclaw_key_snippets.md
snippets/claude_code_key_snippets.md
```

阅读目的：

- 找具体伪代码/关键逻辑。
- 不要整段照抄异构代码。
- 把关键结构翻译为 Jarvis Python 实现。

### 2.4 Jarvis 目标架构和蓝图

```text
05_jarvis_target_architecture.md
06_codex_construction_prompt.md
blueprints/src/jarvis/agent/
```

阅读目的：

- 直接作为新 `src/jarvis/agent/` 的蓝图。
- 先比较蓝图与 Jarvis 现有代码，能复用就复用。
- 不能机械覆盖现有模块。

---

## 3. 参考包和 Jarvis 修改点的强绑定关系

Codex 必须按下面映射施工：

| Jarvis 要补的能力 | 必读参考包文件 | Jarvis 落点 |
|---|---|---|
| Chat-first turn loop | `01_codex_reference.md`, `snippets/codex_key_snippets.md`, `blueprints/src/jarvis/agent/loop.py` | `src/jarvis/agent/loop.py` |
| Thread / Turn / MessageHistory | `01_codex_reference.md`, `05_jarvis_target_architecture.md` | `src/jarvis/agent/store.py`, `src/jarvis/agent/context.py` |
| Tool call 协议 | `01_codex_reference.md`, `02_hermes_reference.md`, `blueprints/src/jarvis/agent/types.py` | `src/jarvis/agent/types.py`, `src/jarvis/agent/tools.py` |
| Tool execution / policy | `04_claude_code_reference.md`, `snippets/claude_code_key_snippets.md` | `src/jarvis/agent/tools.py`, existing `src/jarvis/core/policy/` |
| ReAct retry / fallback | `02_hermes_reference.md`, `snippets/hermes_key_snippets.md` | `src/jarvis/agent/retry.py`, existing `heavy_runtime.py` |
| Event timeline | `03_openclaw_reference.md`, `snippets/openclaw_key_snippets.md` | `src/jarvis/agent/events.py` |
| Summary / final response | `04_claude_code_reference.md`, `05_jarvis_target_architecture.md` | `src/jarvis/agent/summary.py` |
| Benchmark harness | `06_codex_construction_prompt.md`, this spec | `benchmarks/`, `tests/benchmark/` |

---

## 4. 施工前必须输出的分析报告

在正式改代码前，Codex 必须先生成一个短报告：

```text
docs/agent/reference_pack_reading_report.md
```

报告必须包含：

1. 参考包是否找到。
2. 解压路径。
3. 实际读取了哪些文件。
4. 从 Codex 摘要中借鉴什么。
5. 从 Hermes 摘要中借鉴什么。
6. 从 OpenClaw 摘要中借鉴什么。
7. 从 Claude Code 摘要中借鉴什么。
8. 哪些 blueprint 文件会被采用。
9. Jarvis 现有哪些模块会被复用。
10. 哪些模块暂不复用以及原因。

如果没有这个报告，本次施工视为未完成。

---

## 5. 总目标

把 Jarvis 从：

```text
CLI / TaskRuntime / ReAct skeleton / SkillHarness / Memory / Replay 的零件集合
```

升级为：

```text
Input → Chat Turn → Model Call → Tool Call → Tool Result / Observation
→ ReAct Continue → Final Answer → Summary → Persist → Benchmark Evaluation
```

---

## 6. 总原则

不要从零重写 Jarvis。

如果 Jarvis 现有代码已经有相近能力，必须优先收编、适配、重构和增强，而不是重复造轮子。

必须阅读并尽量复用：

```text
jarvis/cli.py
src/jarvis/core/task_runtime.py
src/jarvis/core/react_readiness/
src/jarvis/core/react_readiness/heavy_runtime.py
src/jarvis/core/skill_harness/
src/jarvis/core/memory/
src/jarvis/core/routing/
src/jarvis/core/policy/
src/jarvis/core/hooks/
src/jarvis/core/control_surface.py
tests/
```

如果发现已有实现能复用：

1. 复用并统一到新的 agent 协议。
2. 补最小测试。
3. 在报告中说明复用了哪些旧实现。

如果不复用：

1. 说明原因。
2. 证明旧实现确实无法满足当前目标。
3. 不允许无说明地绕过现有模块。

---

## 7. 两个任务必须连接起来

本次施工不是两个独立任务。

```text
任务 A：补齐 Agent 主链路
任务 B：建立 Benchmark v0.1
```

强制要求：

```text
Benchmark 必须直接调用新 AgentLoop.run_turn()
Benchmark 必须覆盖 AgentLoop 的输入、工具调用、ReAct、summary、持久化结果
Benchmark 报告必须能反向暴露 AgentLoop 的缺陷
```

不要只写 benchmark harness 却不接真实 AgentLoop。  
也不要只补 AgentLoop 却只靠单元测试证明它可用。

---

# 任务 A：补齐 Jarvis Chat Agent 主链路

## A1. 新增目录

新增：

```text
src/jarvis/agent/
├── __init__.py
├── types.py
├── loop.py
├── model.py
├── context.py
├── tools.py
├── events.py
├── summary.py
├── retry.py
└── store.py
```

优先参考：

```text
blueprints/src/jarvis/agent/
```

但不要机械覆盖。  
需要结合 Jarvis 现有模块改成可运行实现。

---

## A2. `types.py`

定义：

```python
@dataclass
class ChatInput:
    text: str
    session_id: str | None = None
    project_id: str | None = None
    cwd: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    risk_level: str = "low"
    requires_approval: bool = False

@dataclass
class ToolResult:
    call_id: str
    name: str
    ok: bool
    content: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class AgentRunResult:
    ok: bool
    session_id: str
    turn_id: str
    final_answer: str
    events: list[dict[str, Any]]
    summary: dict[str, Any]
    stop_reason: str
```

要求：

- 所有对象能 `to_dict()`。
- 不能泄露 secret。
- 必须有测试。

---

## A3. `store.py`

实现 JSONL 持久化：

```text
data/agent_threads/
├── sessions.jsonl
├── <session_id>/
│   ├── turns.jsonl
│   ├── messages.jsonl
│   └── summaries.jsonl
```

最低功能：

- 创建 session
- 创建 turn
- append message
- append tool call/result
- 保存 final answer
- 保存 summary
- 根据 session_id 读取历史
- 支持“继续上次任务”

---

## A4. `context.py`

实现：

- `MessageHistory`
- `ContextBuilder`
- `ContextCompactorAdapter`

必须复用或适配：

```text
src/jarvis/core/react_readiness/context_manager.py
src/jarvis/core/react_readiness/context_compactor.py
src/jarvis/core/memory/store.py
src/jarvis/core/memory/retriever.py
```

功能：

1. 从 session 读取最近 N 轮。
2. 加入 cwd/project 信息。
3. 加入 memory recall。
4. 加入 tool schemas。
5. 超预算时压缩。
6. 生成 model messages。

---

## A5. `model.py`

实现统一模型适配：

```python
class ModelClient:
    def complete(self, messages, tools=None, stream=False, metadata=None) -> ModelResponse:
        ...
```

要求：

- 复用现有 runtime provider。
- 没 API key 时提供 fake model。
- fake model 必须能驱动 benchmark。
- 支持 tool schema 注入。
- 支持 assistant text、reasoning summary、tool_call、final answer。

---

## A6. `tools.py`

实现：

```python
class ToolRegistryAdapter:
    def list_tool_specs(self) -> list[dict]:
        ...

class ToolCallExecutor:
    def execute(self, call: ToolCall, context: dict) -> ToolResult:
        ...
```

第一版至少支持：

```text
repo_reader.search_files
repo_reader.read_file
file_editor.replace_text
command_runner.run
test_runner.run_test
```

必须收编：

```text
RepoReader
FileEditor
CommandRunner
TestRunner
FailureAnalyzer
SkillRegistry
SkillLoader
SkillMatcher
ApprovalRiskMatrix
```

不能继续在 AgentLoop 里做 `_act()` if-else 大分发。  
AgentLoop 只调 `ToolCallExecutor.execute()`。

---

## A7. `events.py`

实现事件：

```text
turn_started
model_call_started
model_call_completed
reasoning_delta
tool_call_started
tool_call_completed
approval_required
observation_added
retry_started
final_answer_created
summary_created
turn_completed
turn_failed
```

事件必须：

- 有 `event_id`
- 有 `turn_id`
- 有 `timestamp`
- 有 `type`
- 有 `payload`
- 写入 run result
- 能被 benchmark 评分

---

## A8. `retry.py`

实现：

- `ErrorClassifier`
- `RetryPolicy`
- `ReplanPolicy`

要求：

- 命令失败可重试。
- 测试失败可 replan。
- tool schema 错误可请求模型重新发 tool call。
- 连续失败超过阈值停止。
- stop reason 结构化。

参考：

```text
02_hermes_reference.md
snippets/hermes_key_snippets.md
src/jarvis/core/react_readiness/heavy_runtime.py
```

---

## A9. `summary.py`

实现 `ResponseComposer`。

输出用户可读内容：

```text
结论
做了什么
调用了哪些工具
改了哪些文件
测试结果
风险和未完成项
下一步建议
```

机器可读 summary：

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

参考：

```text
04_claude_code_reference.md
05_jarvis_target_architecture.md
```

---

## A10. `loop.py`

实现：

```python
class AgentLoop:
    def run_turn(self, chat_input: ChatInput) -> AgentRunResult:
        ...
```

流程：

```text
1. 创建或恢复 session
2. 创建 turn
3. 记录 user message
4. 构建上下文 messages
5. 注入 tool schemas
6. 调用模型
7. 如果模型返回 final answer：
   - 保存 answer
   - 生成 summary
   - 完成 turn
8. 如果模型返回 tool_call：
   - 标准化 ToolCall
   - policy/approval 检查
   - 执行工具
   - 记录 ToolResult
   - 将 observation 回灌上下文
   - 继续模型调用
9. 如果工具失败：
   - ErrorClassifier
   - RetryPolicy / ReplanPolicy
10. 到达 max_steps / timeout / no_progress：
   - 生成 partial summary
   - stop_reason
11. 返回 AgentRunResult
```

必须参考：

```text
01_codex_reference.md
snippets/codex_key_snippets.md
blueprints/src/jarvis/agent/loop.py
```

最低要求：

- 8 步以内 ReAct。
- fake model 可测。
- 至少 5 个核心工具。
- 事件记录。
- summary。
- session 持久化。

---

# 任务 B：建立 Jarvis Benchmark v0.1

Codex 在构造 Benchmark v0.1 样例时，必须参考以下公开 benchmark 的任务形态：

1. coding suite:
   - 参考 SWE-bench Lite / SWE-bench Verified 的 issue → patch → test 形态。
   - 参考 HumanEval / MBPP 的小函数 + 单元测试形态。
   - 默认不要全量下载 SWE-bench；先构造本地小 repo fixtures。

2. terminal suite:
   - 参考 Terminal-Bench 的 instruction + terminal sandbox + verification script 形态。
   - 每个 case 至少包含 instruction、workspace、verify script 或 expected output。

3. web_research suite:
   - 参考 GAIA 的多步工具使用问题形态。
   - 参考 BrowseComp 的 hard-to-find but easy-to-verify 短答案形态。
   - 不复制 BrowseComp/GAIA 受保护或不建议公开泄露的题目；第一版用 mocked local web pages。

4. jarvis_core suite:
   - 自建 30 个核心链路 case，用于验证 AgentLoop.run_turn() 的输入、tool call、observation、summary、event、session persistence。

## B1. 新增目录

```text
benchmarks/
├── README.md
├── case_schema.py
├── run_benchmark.py
├── suites/
│   ├── jarvis_core/
│   │   ├── cases.jsonl
│   │   └── fixtures/
│   ├── coding/
│   │   ├── cases.jsonl
│   │   └── fixtures/
│   ├── terminal/
│   │   └── cases.jsonl
│   └── web_research/
│       └── cases.jsonl
├── evaluators/
│   ├── base.py
│   ├── behavioral.py
│   ├── coding.py
│   ├── terminal.py
│   └── web_research.py
└── reports/
```

---

## B2. Case schema

```python
@dataclass
class BenchmarkCase:
    id: str
    suite: str
    category: str
    input: str
    workspace: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    expected_behavior: dict[str, Any] = field(default_factory=dict)
    grading: dict[str, Any] = field(default_factory=dict)
```

---

## B3. Runner

命令：

```bash
python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 30
python benchmarks/run_benchmark.py --suite coding --max-cases 20
python benchmarks/run_benchmark.py --suite terminal --max-cases 10
python benchmarks/run_benchmark.py --suite web_research --max-cases 10
python benchmarks/run_benchmark.py --all
```

Runner 必须：

1. 读取 cases.jsonl。
2. 准备 workspace。
3. 调用 `AgentLoop.run_turn()`。
4. 收集 events、tool calls、answer、summary、diff、command result。
5. 调用 evaluator。
6. 输出 JSON/Markdown 报告。

强制导入：

```python
from src.jarvis.agent.loop import AgentLoop
from src.jarvis.agent.types import ChatInput
```

禁止 benchmark 直接调用旧 `HeavyReActRuntime`。

---

## B4. Evaluator

最低检查：

```text
final_answer_exists
summary_exists
tool_call_schema_valid
must_call_tools
no_forbidden_tool
must_include
must_not_modify_files
test_passed
stop_reason_valid
event_timeline_valid
```

---

## B5. Codex 必须自己构建样例

至少创建：

```text
jarvis_core >= 30
coding >= 20
terminal >= 10
web_research >= 10
```

要求：

- 默认离线可跑。
- coding fixtures 必须带测试。
- terminal fixtures 必须可验证。
- web_research 第一版可用 mocked pages。
- 不要下载大型数据集作为默认依赖。

可以参考公开 benchmark 的任务形态，但默认不要强依赖：

```text
SWE-bench Lite / Verified
Terminal-Bench
GAIA Level 1
BrowseComp
HumanEval / MBPP
RepoQA
```

---

# 测试与验收

## 单元测试

```bash
python -m pytest tests/agent -q
python -m pytest tests/benchmark -q
```

## Benchmark

```bash
python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 30
python benchmarks/run_benchmark.py --suite coding --max-cases 20
python benchmarks/run_benchmark.py --suite terminal --max-cases 10
python benchmarks/run_benchmark.py --suite web_research --max-cases 10
python benchmarks/run_benchmark.py --all
```

## 最低通过标准

| Suite | 最低通过率 |
|---|---:|
| jarvis_core | >= 80% |
| coding | >= 40% |
| terminal | >= 50% |
| web_research | >= 40% |

AgentLoop 指标：

| 指标 | 最低要求 |
|---|---:|
| final answer 生成率 | 100% for successful cases |
| tool call schema 合法率 | >= 95% |
| forbidden tool 违规率 | 0 |
| summary 生成率 | 100% |
| event timeline 生成率 | 100% |
| session 持久化成功率 | 100% |
| stop reason 存在率 | 100% for failed/partial cases |

---

# 文档交付

必须生成：

```text
docs/agent/reference_pack_reading_report.md
docs/agent/agent_loop_design.md
docs/agent/benchmark_v0_1.md
benchmarks/reports/latest.md
```

最终报告必须说明：

1. 参考包是否读取。
2. 读取了哪些参考文件。
3. 从四个 agent 分别借鉴了什么。
4. 新增了哪些模块。
5. 复用了 Jarvis 哪些旧模块。
6. 哪些旧模块没有复用以及原因。
7. Benchmark v0.1 有多少 case。
8. 各 suite 通过率。
9. 失败 case Top 10。
10. 下一轮优先修复项。

---

# 给 Codex 的最终执行 Prompt

你现在在 Jarvis 仓库中工作。请完成一次“参考包驱动的 Agent 主链路 + Benchmark v0.1”联合施工。

## 第一步：读取参考包

先找到并解压：

```text
jarvis_agent_reference_pack.zip
```

必须阅读：

```text
README.md
00_gap_to_reference_matrix.md
reference_index.json
01_codex_reference.md
02_hermes_reference.md
03_openclaw_reference.md
04_claude_code_reference.md
snippets/codex_key_snippets.md
snippets/hermes_key_snippets.md
snippets/openclaw_key_snippets.md
snippets/claude_code_key_snippets.md
05_jarvis_target_architecture.md
06_codex_construction_prompt.md
blueprints/src/jarvis/agent/
```

生成：

```text
docs/agent/reference_pack_reading_report.md
```

如果找不到参考包，停止并报告 `missing_reference_pack`。

## 第二步：阅读 Jarvis 当前代码

阅读：

```text
jarvis/cli.py
src/jarvis/core/task_runtime.py
src/jarvis/core/react_readiness/
src/jarvis/core/react_readiness/heavy_runtime.py
src/jarvis/core/skill_harness/
src/jarvis/core/memory/
src/jarvis/core/routing/
src/jarvis/core/policy/
src/jarvis/core/hooks/
tests/
```

## 第三步：实现 Agent 主链路

新增或补齐：

```text
src/jarvis/agent/
```

实现：

```python
AgentLoop.run_turn(ChatInput) -> AgentRunResult
```

要求支持：

```text
session persistence
message history
model call
tool schema injection
tool call execution
tool result observation
ReAct loop
retry/replan
summary
event timeline
```

## 第四步：实现 Benchmark v0.1

新增：

```text
benchmarks/
tests/benchmark/
```

Benchmark 必须调用：

```python
AgentLoop.run_turn()
```

创建本地样例：

```text
jarvis_core >= 30
coding >= 20
terminal >= 10
web_research >= 10
```

## 第五步：测试

运行：

```bash
python -m pytest tests/agent -q
python -m pytest tests/benchmark -q
python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 30
python benchmarks/run_benchmark.py --suite coding --max-cases 20
python benchmarks/run_benchmark.py --suite terminal --max-cases 10
python benchmarks/run_benchmark.py --suite web_research --max-cases 10
python benchmarks/run_benchmark.py --all
```

## 完成标准

必须证明：

```text
参考包已读取
AgentLoop 能跑真实 turn
ToolCall 能触发
ToolResult 能回灌
ReAct 能继续
Summary 能生成
Session 能持久化
Benchmark 能调用 AgentLoop 并暴露真实失败
```

不要只交设计文档。必须有可运行代码、测试和 benchmark 报告。
