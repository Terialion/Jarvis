# Jarvis Interactive CLI Path Audit

Date: 2026-05-02  
Scope: structure audit only (no logic change)

## Read Scope

Reviewed:
- [D:\Jarvis\jarvis\cli.py](D:/Jarvis/jarvis/cli.py)
- [D:\Jarvis\src\jarvis\agent\loop.py](D:/Jarvis/src/jarvis/agent/loop.py)
- [D:\Jarvis\src\jarvis\core\routing\intent_gateway.py](D:/Jarvis/src/jarvis/core/routing/intent_gateway.py)
- [D:\Jarvis\src\jarvis\core\routing\clarification.py](D:/Jarvis/src/jarvis/core/routing/clarification.py)
- [D:\Jarvis\src\jarvis\core\routing\llm_classifier.py](D:/Jarvis/src/jarvis/core/routing/llm_classifier.py)
- [D:\Jarvis\src\jarvis\core\routing\deterministic_router.py](D:/Jarvis/src/jarvis/core/routing/deterministic_router.py)
- [D:\Jarvis\src\jarvis\core\cli_response\dispatcher.py](D:/Jarvis/src/jarvis/core/cli_response/dispatcher.py)
- [D:\Jarvis\src\jarvis\core\cli_response\natural_responses.py](D:/Jarvis/src/jarvis/core/cli_response/natural_responses.py)
- [D:\Jarvis\src\jarvis\core\cli_response\tool_loop_adapter.py](D:/Jarvis/src/jarvis/core/cli_response/tool_loop_adapter.py)
- tests in `tests/cli`, `tests/routing` (routing/clarify/CLI path related)

Requested but not present:
- `jarvis/cli_agent_output.py` (not found in repo)

---

## A. 当前路径图

### 1) Slash command (interactive)

`python -m jarvis.cli` interactive:

`input`  
-> `run_shell()`  
-> `build_input_envelope()`  
-> `if envelope.slash.is_slash_command`  
-> `_handle_slash_command()`  
-> `route_command()`  
-> (known) local handler map (`/help`, `/skills`, `/trace`, etc.) **or** skill router  
-> output text

Unknown slash example `/hlep`:

`/hlep`  
-> `route_command()` unknown branch  
-> `"Unknown command ... Did you mean ..."`  
-> output (no LLM, no AgentLoop)

### 2) Natural language old path (interactive)

`input`  
-> `run_shell()`  
-> `_handle_natural_language(state, text)`  
-> `_detect_intent_route(text)`  
-> `build_cli_route()`  
-> `route_user_input()`  
-> `route_user_text()` / `route_intent()`  
-> deterministic / safety / clarify routing  
-> `_apply_route_safety(...)` (again in `cli.py`)  
-> `dispatch_natural_language(...)`  
-> one of:
- chat renderer / clarify renderer / safety renderer
- **or** `execute_agent_tool_loop(...)` (core AgentToolLoop, not new `src/jarvis/agent/loop.py`)
-> output text

### 3) One-shot AgentLoop path (`--ask`, `-p`)

`input`  
-> `main()` parse args  
-> `_run_non_interactive_with_mode(prompt, output_mode)`  
-> instantiate `src.jarvis.agent.loop.AgentLoop`  
-> `AgentLoop.run_turn(ChatInput(...))`  
-> `_render_agent_result_text(...)`  
-> output

### 4) clarification.py 触发链

Chain:

`_handle_natural_language`  
-> `_detect_intent_route`  
-> `build_cli_route`  
-> `route_user_input`  
-> `intent_gateway.route_intent`  
-> Step 5 fallback `build_clarification_route(...)` when:
- deterministic not high-confidence, and
- LLM unavailable or LLM confidence < 0.55

Then dispatcher:

`dispatch_natural_language(mode="clarify_question")`  
-> optional `run_llm_chat` recovery only for limited marker set  
-> otherwise `render_clarify_question(...)`

---

## B. 输入路径对照表

| 输入 | 当前处理函数链 | 是否 AgentLoop | 是否 LLM | 当前输出类型 | 目标路径 |
|---|---|---:|---:|---|---|
| `/help` | `run_shell -> _handle_slash_command -> route_command -> handlers['/help']` | 否 | 否 | 本地帮助文本 | 保持本地 |
| `/hlep` | `run_shell -> _handle_slash_command -> route_command(unknown)` | 否 | 否 | unknown + did-you-mean | 保持本地 |
| `下午好` | `run_shell -> _handle_natural_language -> deterministic greeting -> dispatch(chat_like)` | 否 | 可选（chat-like可走 run_llm_chat） | chat answer | 可保持 chat path（可LLM优先） |
| `晚上好` | 同上（greeting rule） | 否 | 可选 | chat answer | 可保持 chat path（可LLM优先） |
| `你是什么模型` | `run_shell -> _handle_natural_language -> route_intent(LLM未接入此链) -> 常落 clarify -> dispatch clarify` | 否 | **路由阶段否**（关键） | 澄清问题（易误判） | 应走 chat/identity/explain（LLM直答或本地模板） |
| `你能帮我写代码吗？` | 同上，常因非高置信规则 + 无LLM路由而落 clarify | 否 | 路由阶段否 | 澄清问题（易误判） | 应走 capability/help answer（非立即执行） |
| `读取 README.md` | `... -> route_after_safety(work mode) -> dispatch -> execute_agent_tool_loop` | 否（不是新 AgentLoop） | 可能（取决core AgentToolLoop provider） | 工具链路输出 | 应统一到 `AgentLoop.run_turn` |
| `列一下当前目录` | 同上，work mode -> `execute_agent_tool_loop` | 否（不是新 AgentLoop） | 可能 | 工具链路输出 | 应统一到 `AgentLoop.run_turn` |
| `打印我的 .env` | `intent_gateway safety precheck -> refusal mode -> dispatch render_refusal_safety` | 否 | 否 | 安全拒绝 | 保持安全拒绝 |
| `给我讲个笑话` | 非deterministic高置信；若路由LLM不可用易落clarify；dispatcher有clarify恢复分支（marker命中时可LLM回复） | 否 | 部分（仅dispatch恢复） | chat或clarify（不稳定） | 应稳定 chat-like 直答 |

说明（关键差异）：
- Interactive routing path **没有把 `state.llm_provider` 传给 `build_cli_route`**，导致 `intent_gateway` 的 LLM 分类在交互路径默认不可用。
- One-shot `--ask/-p` 直接进 `AgentLoop.run_turn()`，不经过上述旧路由+clarify主链。

---

## C. 问题总结

### 1) 哪些输入被错误 clarification

高概率误澄清：
- `你是什么模型`
- `你能帮我写代码吗？`
- 其他不在 deterministic 高置信规则中的普通问答

根因：
1. `intent_gateway` 设计是 deterministic -> LLM classifier -> clarify。  
2. 但 interactive `_detect_intent_route()` 调用 `build_cli_route()` 时未注入 `llm_provider`，使第2步失效。  
3. 第5步 clarify 成为默认兜底。  
4. dispatcher 虽有 clarify->LLM recovery，但触发词有限，覆盖不全。

### 2) 哪些输入应本地回答

- slash command 本地处理（`/help`, `/commands`, `/trace`, `/exit` 等）
- unknown slash 本地 did-you-mean（如 `/hlep`）

### 3) 哪些输入应进 AgentLoop

工作型请求：
- 读文件/列目录/仓库检查
- 写代码/改文件/运行测试/命令执行

当前 interactive 多数工作请求是进 `execute_agent_tool_loop`（core AgentToolLoop），不是新 `src/jarvis/agent/loop.py`。

### 4) 哪些输入应安全拒绝

- `.env`、token、id_rsa、危险 shell pipeline、破坏性删除
- 当前有 safety precheck + safety gate，主路径可拒绝

### 5) 哪些 slash command 应保留本地处理

- `/help`, `/exit`, `/trace`, `/commands`, `/skills`, `/state`, `/approvals` 等控制面命令
- unknown slash 仍本地处理，避免误入 LLM / task

---

## D. 修改建议（不改代码，仅建议）

### Phase 1（最小修复）

1. 在 interactive `_detect_intent_route` / `build_cli_route` 链路注入 `state.llm_provider`。  
2. 保持 slash command 本地优先。  
3. 扩展 clarify recovery 触发词，覆盖模型/能力问句（短期止血）。

### Phase 2（切换非 slash 输入到统一 AgentLoop）

1. 非 slash 自然语言统一进入 `src/jarvis/agent/loop.py::AgentLoop.run_turn()`。  
2. 把 CLI renderer 作为唯一输出层（default/quiet/verbose/trace/json）。  
3. 将旧 `dispatch_natural_language + execute_agent_tool_loop` 作为兼容 fallback。

### Phase 3（clarification.py 主路径退场）

1. Clarification 从“主路由兜底”改为“LLM/agent 明确判定极度模糊时才触发”。  
2. 保留 safety refusal 优先级不变。  
3. 清理重复路由层，减少 `route_intent` 与 agent router 的双轨分叉。

---

## 结论（针对本次验收点）

1. 已生成审计文档：`docs/cli/interactive_cli_path_audit.md`。  
2. 已明确 `clarification.py` 触发链：`route_intent` Step 5 fallback -> dispatcher clarify。  
3. 已明确 one-shot 与 interactive 差异：  
   - one-shot: `--ask/-p -> AgentLoop.run_turn()`  
   - interactive natural language: 旧 routing + dispatcher + core AgentToolLoop adapter  
4. 本轮未修改主逻辑，未触碰现有测试行为。  
