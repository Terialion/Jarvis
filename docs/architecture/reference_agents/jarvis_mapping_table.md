# Jarvis Reference Mapping Table

| Reference Agent | Piece | Jarvis Layer | Jarvis Target Files | Phase | Legacy Cleanup Plan |
|---|---|---|---|---|---|
| Codex | Turn loop + tool call + approval + history rendering | Agent runtime + renderer | `src/jarvis/agent/loop.py`, `types.py`, `tools.py`, `events.py`, `jarvis/cli_agent_output.py` | 1-3 | Remove old interactive natural dispatcher default path; collapse to AgentLoop output contract |
| Claude Code | Slash/local command control + hook/permission UX | Local command + policy/hooks | `jarvis/cli.py`, `jarvis/cli_commands.py`, `src/jarvis/core/policy/*`, `src/jarvis/core/hooks/*` | 1-2 | Keep slash local handling; remove duplicated command branches after extraction |
| OpenClaw | Control surface + skills + replay/evidence + tool event view | Control surface + skills + event trail | `src/jarvis/core/skills/*`, `src/jarvis/core/replay/*`, `src/jarvis/core/evidence/*`, `src/jarvis/agent/events.py`, `jarvis/cli_agent_output.py` | 2-4 | Retire legacy route-time work response formatting once shared renderer/API contract lands |
| Hermes | Tool trail + trace/detail rendering | Renderer + summary/event mapping | `jarvis/cli_agent_output.py`, `src/jarvis/agent/events.py`, `src/jarvis/agent/summary.py` | 1-3 | Remove old mixed human/debug print branches after mode parity tests pass |

## Summary

1. Commands remain local dispatcher concerns.
2. Non-slash user turns move to AgentLoop.
3. Renderer consumes `AgentRunResult`; router only emits hints.
4. Clarification migrates from router fallback to explicit `output_type` in run result.
