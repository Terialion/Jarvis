# Reference Agents Mapping Pack

## Purpose

This folder captures how Jarvis migration phases borrow from Codex / Claude Code / OpenClaw / Hermes, without cloning their full architecture.

## Jarvis Layer

Architecture / migration planning layer (not runtime code).

## Reference Inputs

- Codex core + TUI turn loop/render split
- Claude Code command/control + hook/permission boundaries
- OpenClaw control surface/events/skills organization
- Hermes tool trail + event-to-renderer UX

## What We Borrow

- Clear separation: command dispatcher vs agent turn loop vs renderer
- Event-first output contracts
- Permission/safety boundaries independent from rendering
- Tool trail and trace as first-class run artifacts

## What We Do Not Copy

- Rust/TS implementation details
- Full TUI frameworks
- Provider-specific coupling to external runtime conventions

## Jarvis Landing Files

- `jarvis/cli.py`
- `jarvis/cli_agent_output.py` (planned)
- `src/jarvis/agent/*`
- `src/jarvis/core/policy/*`
- `src/jarvis/core/hooks/*`
- `src/jarvis/core/skills/*`

## Phase Mapping

- Phase 0.5: mapping + migration plan docs (this pack)
- Phase 1+: progressive runtime migration

## Legacy Cleanup Plan

- Documented per mapping file and in `docs/architecture/agent_migration_status.md`.
