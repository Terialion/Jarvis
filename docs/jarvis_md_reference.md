# JARVIS.md Reference

## What It Is

`JARVIS.md` is project guidance for Jarvis. It helps shape planning, responses, repo inspection summaries, success judging, rethink, replan, and final review.

It is not permission. Safety and approval gates are enforced by code and cannot be overridden by instructions.

## Relationship To AGENTS.md And CLAUDE.md

Jarvis can load `JARVIS.md`, `AGENTS.md`, and `CLAUDE.md` together. These files provide guidance from different agent ecosystems, but Jarvis still applies its own routing, safety, approval, and scoped-test policies.

## Discovery Order

1. Builtin default instructions.
2. `~/.jarvis/JARVIS.md`.
3. `<repo>/JARVIS.md`.
4. `<repo>/AGENTS.md`.
5. `<repo>/CLAUDE.md`.
6. `<repo>/.jarvis/JARVIS.override.md`.
7. Directory-scoped `JARVIS.md` inside the workspace when applicable.

Each loaded source records scope, path, byte count, and skip reason when skipped.

## Recommended Structure

- Project Overview
- CLI Behavior
- Language Policy
- Capability Answer Policy
- Usage Help Policy
- Repo Inspection Policy
- Coding Task Policy
- Loop Policy
- Success Judge Policy
- Rethink/Replan Policy
- Test Policy
- Safety Policy
- Response Style

## Coding Loop Use

The prompt builder includes instruction text when creating natural response, repo inspection summary, coding plan, success judge, rethink/replan, and final review prompts.

Deterministic checks still run first. The LLM may explain a decision, but it cannot convert failed tests into success, bypass pending approval, or ignore safety violations.

## Safety Boundary

`JARVIS.md` cannot authorize reading `.env`, private keys, tokens, credentials, or other secrets. It cannot authorize shell commands, file writes, network access, or approval bypass.

## Example

```markdown
# JARVIS.md

## Coding Task Policy

Use scoped tests by default. For docs-only changes, prefer no shell unless the user asks for validation.

## Safety Policy

Never read secrets or run shell without approval.
```

