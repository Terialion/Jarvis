# Claude Code CLI Control Notes

## What This Piece Does

Defines local command/control behavior: slash command dispatch, permissions UX, hook boundaries, and safety-first local control surface.

## Jarvis Layer

CLI command layer + policy/hooks boundary layer.

## Reference Code Paths

- `.claude/commands/`
- `plugins/*/commands/`
- `plugins/hookify/hooks/pretooluse.py`
- `plugins/hookify/hooks/posttooluse.py`
- `plugins/security-guidance/hooks/`
- `examples/hooks/`

## Borrowed Ideas

- Slash command local-first handling
- Permission/approval messages as explicit control flow states
- Hook lifecycle around tool use, not mixed with chat rendering
- Command metadata style for discoverability/help UX

## Do Not Copy

- Plugin packaging semantics directly
- Claude command folder structure as a strict template
- Hook internals tightly coupled to Claude runtime

## Jarvis Landing Files

- `jarvis/cli.py`
- `jarvis/cli_commands.py` (planned)
- `src/jarvis/core/policy/*`
- `src/jarvis/core/hooks/*`
- `src/jarvis/core/tools/runtime/*`

## Phase

- Phase 1: preserve local slash dispatcher while migrating non-slash to AgentLoop
- Phase 2: unify permission/hook render and event messages

## Legacy Deletion Plan

- Keep local slash path long-term
- Remove duplicate legacy command branches in `jarvis/cli.py` after `cli_commands.py` extraction
- Validate parity via slash command regression tests before each cleanup step
