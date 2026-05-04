# OpenClaw Control Surface Notes

## What This Piece Does

Shapes Jarvis control surface around consistent command catalog, evented chat log, tool execution components, and skills-facing UX.

## Jarvis Layer

Control surface + event/replay/evidence + skills orchestration layer.

## Reference Code Paths

- `src/cli/command-catalog.ts`
- `src/cli/command-format.ts`
- `src/tui/components/chat-log.ts`
- `src/tui/components/assistant-message.ts`
- `src/tui/components/tool-execution.ts`
- `src/tui/tui-event-handlers.ts`
- `src/tui/tui-stream-assembler.ts`
- `skills/`

## Borrowed Ideas

- Command catalog as explicit public surface
- Tool execution visibility in output stream
- Replay/evidence surfaced as first-class control features
- Skills represented as controllable, auditable capability units

## Do Not Copy

- OpenClaw TS UI architecture directly
- OpenClaw-specific transport assumptions
- One-to-one command naming if it conflicts with Jarvis compatibility

## Jarvis Landing Files

- `src/jarvis/core/skills/*`
- `src/jarvis/core/replay/*`
- `src/jarvis/core/evidence/*`
- `src/jarvis/agent/events.py`
- `jarvis/cli_agent_output.py` (planned)
- API/Web control surface adapters

## Phase

- Phase 1: define renderer/event contracts
- Phase 2-3: unify CLI/API/Web around AgentRunResult and event trail

## Legacy Deletion Plan

- Retire duplicate replay/evidence text assembly in legacy CLI paths once event renderer is shared
- Remove route-time response text composition for work paths after renderer contract cutover
