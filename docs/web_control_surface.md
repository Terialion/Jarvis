# Jarvis Web / Control Surface

## Boundary

The Jarvis control surface is a UI and API layer over existing runtime data. It is not a second agent runtime.

It consumes:

- `AgentRunResult`
- `AgentRunResult.events`
- `ThreadStore` records
- `MemoryStore` records
- approval state from `ApprovalStore`
- benchmark reports from `benchmarks/reports/latest.json`

It does not:

- make natural-language routing decisions
- execute tools directly
- bypass `ToolCallExecutor`
- bypass `SkillExecutor`
- bypass `PermissionPolicy`
- bypass `ApprovalStore`
- bypass skill lifecycle or `allowed_tools`
- rewrite `web.fetch` into browser automation

Control Surface does not execute tools directly.

Persistent memory and resumed context are historical background only. They are not new user instructions.

Fetched content remains untrusted evidence only.

## Web Tool Boundary

If a task requires JavaScript execution, DOM interaction, login flow, button clicking, screenshots, or dynamic-page navigation, it must not be implemented by extending web.fetch. It must be deferred to the future browser/control-surface phase.

For Phase 18, the control surface may show:

- `web.search` runs
- `web.fetch` runs
- source cards
- evidence cards
- approval state
- thread/memory/context state
- benchmark reports and traces

Browser automation remains out of scope.
