# Multi-Agent Parallel Execution & TUI Polish — Design Spec

**Date:** 2026-05-19
**Status:** draft

## 1. Scope

Two workstreams, executed in order:

1. **Multi-agent parallel execution** — async spawn/wait/list/close, tool restriction by agent_type, depth control
2. **TUI polish** — fix rendering bugs, add multi-agent status panel, subagent output collapsing

Sandbox (Docker/Linux) and sub-agent security tightening is deferred to a follow-up.

## 2. Reference Systems

| Capability | Hermes-Agent | Codex | OpenClaw |
|---|---|---|---|
| Parallel model | ThreadPoolExecutor | tokio async | Promise.all |
| Spawn tool | delegate_task | spawn_agent | sessions_spawn |
| Wait tool | N/A (blocking submit) | wait_agent | sessions_yield |
| List tool | N/A | list_agents | sessions_list |
| Close tool | N/A | close_agent | N/A (session end) |
| Depth limit | max_spawn_depth=3 | agent_max_depth | N/A |
| Tool restriction | DELEGATE_BLOCKED_TOOLS frozenset | agent_type role taxonomy | tool-policy allow/deny |
| Result plumbing | heartbeat + progress callback | mailbox + trigger_turn | A2A turn-based conversation |
| Max workers | configurable | agent_max_threads | concurrency per gateway |

**Design rule:** follow Hermes-Agent's thread pool model + Codex's tool naming (spawn/wait/list/close).

## 3. Architecture

### 3.1 Multi-Agent Parallel

```
src/jarvis/core/subagents/
├── runner.py          # SubagentRunner — wraps AgentLoop, runs in thread
├── pool.py            # NEW: SubagentPool — ThreadPoolExecutor, max_workers=4
├── handle.py          # NEW: SubagentHandle — Future wrapper with status tracking
├── models.py          # UPDATE: add SubagentStatus enum, SubagentConfig
├── policy.py          # UPDATE: tool whitelist by agent_type, depth check
└── tools.py           # NEW: spawn_agent / wait_agent / list_agents / close_agent handlers
```

#### Data flow

```
AgentLoop.run_turn()
  ├── LLM call decides to spawn subagents
  ├── ToolCallExecutor handles spawn_agent
  │     └── SubagentPool.submit(config) → returns agent_id, status="running"
  │           └── ThreadPoolExecutor worker:
  │                 └── SubagentRunner.run() → blocks in thread
  │                       └── AgentLoop.run_turn() with restricted tools
  │                             └── on complete → SubagentPool.notify(agent_id, result)
  ├── AgentLoop continues processing other tool calls (non-blocking!)
  ├── Before next LLM call:
  │     └── drain_subagent_notifications()
  │           └── injects "<subagent-result agent_id=... status=...>" into messages
  └── LLM sees subagent results and continues reasoning
```

#### Key design decisions

- **ThreadPoolExecutor**, not asyncio — matches Hermes-Agent, minimal change to existing sync loop
- **max_workers=4 default** — same as Codex `agent_max_threads`, same as existing BackgroundTaskManager
- **Depth cap=2** — parent can spawn children, children can spawn grandchildren, no deeper
- **Result injection via drain pattern** — same as `bg.task` notifications, already implemented in AgentLoop
- **Agent registry in pool** — `{agent_id: SubagentHandle}`, supports list/close/wait operations

#### Tool restriction by agent_type

| agent_type | Tools allowed |
|---|---|
| `Explore` | bash, read_file, glob, grep, list_tree (read-only) |
| `Plan` | read-only + task_create/task_update (no exec/write) |
| `general-purpose` | all tools (must pass approval) |

#### Metrics to track (align with Codex)

- `spawn_count` — total subagents spawned
- `active_count` — currently running
- `completed_count` — finished successfully
- `failed_count` — errored or timed out
- `total_steps` — sum of steps across all subagents
- `total_tokens` — sum of tokens across all subagents
- `max_depth_reached` — deepest nesting level used

### 3.2 TUI Polish

#### Bug fixes

1. **hasStreaming non-boolean** — ensure all code paths return `true`/`false`, not truthy values
2. **Blank gap between messages and prompt** — Flexbox layout correction, remove magic margin
3. **Ctrl key leakage** — verify custom TextInput properly consumes all Ctrl+key combos
4. **Thinking/tools toggle state** — ensure expanded/collapsed state persists across re-renders

#### New: Multi-agent status panel

A collapsible sidebar (toggle with `Ctrl+A`) showing:

```
┌─ Agents (2 active) ──────────────────┐
│ ● sub_abc123  Explore  [████░░] 3/10 │
│ ● sub_def456  Fix bug  [██░░░] 1/8   │
│ ○ sub_ghi789  Plan     done   ✓      │
└──────────────────────────────────────┘
```

Each row shows: status indicator, agent_id, agent_type, progress bar (steps/total), step count. Completed agents show checkmark.

Toggle behavior: `Ctrl+A` toggles the panel. When agents are running, show a subtle indicator in the status bar ("2 agents running | Ctrl+A to view").

#### Subagent output collapsing

When a `spawn_agent` tool result returns with subagent output > 500 chars, default to collapsed showing first 200 chars + "Show full output (N chars)". Click or Enter to expand.

## 4. Success Criteria

- [ ] `spawn_agent` returns immediately, parent loop does not block
- [ ] Can spawn 3 subagents simultaneously, all make progress concurrently
- [ ] `wait_agent` blocks until specified agent completes
- [ ] `list_agents` shows all active/completed agents with status
- [ ] `close_agent` terminates a running agent and cleans up
- [ ] Explore-type agent cannot call write_file or command_runner.run
- [ ] Depth 2: parent → child → grandchild OK; parent → child → grandchild → great-grandchild blocked
- [ ] TUI: no infinite re-render loops
- [ ] TUI: no blank gap between messages and input
- [ ] TUI: Ctrl+A toggles multi-agent status panel
- [ ] TUI: subagent output collapsed by default, expandable
- [ ] All existing tests pass (no regression)

## 5. Out of Scope

- Docker/OS sandbox for subagent execution (separate follow-up)
- Per-subagent approval gating (separate follow-up)
- Worktree binding for subagents (separate follow-up)
- CSV batch spawning (Codex agent_jobs pattern — future)
- ACP/IDE integration (future)
