# Codex CLI Turn Loop Notes

## What This Piece Does

Defines the target behavior for Jarvis agent turn execution: user input -> model reasoning -> tool call -> observation -> final answer, with stable event output.

## Jarvis Layer

Agent runtime layer + CLI renderer integration layer.

## Reference Code Paths

- `codex-rs/core/src/codex.rs`
- `codex-rs/core/src/conversation_manager.rs`
- `codex-rs/core/src/protocol.rs`
- `codex-rs/core/src/openai_tools.rs`
- `codex-rs/core/src/exec.rs`
- `codex-rs/core/src/safety.rs`
- `codex-rs/tui/src/chatwidget.rs`
- `codex-rs/tui/src/history_cell.rs`
- `codex-rs/tui/src/exec_cell/render.rs`

## Borrowed Ideas

- Turn loop as primary path for non-command input
- Structured run result + events as shared contract
- Safety/approval checks in execution path, not renderer
- Renderer consumes run artifacts, does not decide intent

## Do Not Copy

- Codex Rust protocol types verbatim
- Codex TUI implementation and component hierarchy
- Codex-specific model/tool APIs as-is

## Jarvis Landing Files

- `src/jarvis/agent/loop.py`
- `src/jarvis/agent/types.py`
- `src/jarvis/agent/tools.py`
- `src/jarvis/agent/events.py`
- `jarvis/cli_agent_output.py` (planned)

## Phase

- Phase 1: interactive non-slash default -> AgentLoop
- Phase 2+: contract hardening and shared API/Web consumption

## Legacy Deletion Plan

- Phase 1: old interactive natural dispatcher exits default path
- Phase 2: `cli_response/tool_loop_adapter.py` usage reduced to compatibility
- Phase 3: old natural response fallback path removed from default interactive flow
