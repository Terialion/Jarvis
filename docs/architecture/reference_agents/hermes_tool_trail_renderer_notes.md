# Hermes Tool Trail Renderer Notes

## What This Piece Does

Defines how Jarvis should present tool trail, reasoning/trace slices, and output modes (default/verbose/trace/json) from a single run result.

## Jarvis Layer

Renderer/output layer + event-to-view mapping layer.

## Reference Code Paths

- `ui-tui/src/components/messageLine.tsx`
- `ui-tui/src/components/streamingAssistant.tsx`
- `ui-tui/src/components/thinking.tsx`
- `ui-tui/src/app/createGatewayEventHandler.ts`
- `ui-tui/src/app/turnStore.ts`
- `ui-tui/src/app/turnController.ts`
- `ui-tui/src/lib/text.ts`

## Borrowed Ideas

- Event stream drives rendering detail levels
- Tool trail is visible and auditable
- Same run object can feed different display modes
- Text compaction/safe rendering for terminal readability

## Do Not Copy

- Hermes React/TUI implementation
- Hermes UI state store implementation details
- Any provider/runtime specifics unrelated to renderer contract

## Jarvis Landing Files

- `jarvis/cli_agent_output.py` (planned)
- `src/jarvis/agent/events.py`
- `src/jarvis/agent/summary.py`
- `src/jarvis/agent/types.py` (`AgentRunResult`)

## Phase

- Phase 1: interactive renderer switch to AgentRunResult-driven output
- Phase 2: richer trail in verbose/trace modes

## Legacy Deletion Plan

- Remove legacy mixed responder text assembly once `cli_agent_output.py` is primary renderer
- Keep compatibility shim temporarily; remove after tests verify mode parity
