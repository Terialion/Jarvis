# Phase 1 Interactive AgentLoop Migration Plan

## 1) Phase 1 Goal

- Interactive CLI: input starting with `/` continues through local command dispatcher.
- Interactive CLI: non-slash natural input defaults to `AgentLoop.run_turn()`.
- Ordinary natural language should no longer default to old `clarification.py` / dispatcher path.
- Do not delete `clarification.py` in Phase 1.
- Do not do large routing rewrites in Phase 1.
- Do not optimize loop/cycle rate in Phase 1.

## 2) Files To Change

- `jarvis/cli.py`
- `jarvis/cli_agent_output.py`
- `tests/cli/test_interactive_shell_agent_path.py`
- `tests/cli/test_no_bad_clarification_output.py`

## 3) Files To Read But Minimize Changes

- `src/jarvis/agent/loop.py`
- `src/jarvis/agent/types.py`
- `src/jarvis/agent/summary.py`
- `src/jarvis/core/routing/clarification.py`
- `src/jarvis/core/cli_response/dispatcher.py`

## 4) Target Runtime Path

- Slash command: `input -> LocalCommandDispatcher -> local output`
- Non-slash natural input: `input -> AgentLoop.run_turn() -> cli_agent_output renderer -> output`

## 5) Legacy Cleanup Plan

- After Phase 1: old natural dispatcher exits default interactive path.
- After Phase 2: `clarification.py` no longer in main interactive path.
- After Phase 3: delete `clarification.py` or keep deprecated stub only.
- Old AgentToolLoop adapter converges into AgentLoop ToolCallExecutor contract.
- Every legacy fallback removal requires:
  1. targeted regression test
  2. explicit migration note in `agent_migration_status.md`
  3. no behavior regression on safety/slash paths

## 6) Expected Test Matrix

- `/help` local
- `/hlep` did-you-mean
- `下午好` no bad clarify
- `晚上好` no bad clarify
- `你是什么模型` no bad clarify
- `你能帮我写代码吗` no bad clarify
- `给我讲个笑话` no bad clarify
- `读取 README.md` goes through AgentLoop
- `列一下当前目录` goes through AgentLoop
- `打印我的 .env` no secret leak / safety refusal
- `帮我弄一下` clarification allowed, but old default clarify sentence should not be emitted as generic fallback

## 7) Boundaries

- Keep slash local and deterministic.
- Keep safety precedence unchanged.
- Keep benchmark core unchanged in Phase 1.
