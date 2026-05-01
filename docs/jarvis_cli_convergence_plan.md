# Jarvis CLI Convergence Plan

## Current Status
Completed now:
- slash command fast path
- Hybrid Intent Router
- route safety gate
- route trace
- safe task flow
- skills basics
- approval basics
- replay/evidence basics
- true natural CLI UX for chat/help/usage in real entry path
- CLI response-mode dispatcher
- real CLI smoke test for natural UX
- read-only repo inspection execution module
- real small coding smoke (edit + scoped test + diff)
- deterministic rethink/replan loop baseline with stop_reason
- JARVIS.md instruction loading baseline
- CLI coding path routed through CodingLoopOrchestrator

Still missing:
- CLI test baseline fully reconciled
- context/resume/compact lifecycle
- sandbox adapter
- skill lifecycle governance
- learning proposal workflow

## CLI Response Mode Baseline
Modes that must not enter task flow:
- chat_answer
- help_answer
- clarify_question
- repo_inspection
- search_pipeline
- url_summary
- skill_admin
- context_admin
- model_admin
- refusal_or_safety_message

Modes allowed to enter task flow:
- coding_loop
- executor_action
- automation_action

## Claude Code Alignment
P0:
- natural chat/help/usage responses in real CLI

P1:
- read-only repo inspection module
- inspect -> plan -> approval -> edit -> diff -> scoped test -> review

P2:
- context/resume/compact loop
- hooks lifecycle
- skill on-demand loading

## Codex Alignment
P0:
- approval never bypassed for write/shell/network-sensitive requests

P1:
- AGENTS.md / JARVIS.md instruction hierarchy
- scoped test policy by change footprint

P2:
- sandbox adapter
- stronger enforcement for network/write/shell policies

## OpenClaw Alignment
P1:
- skill status/trust/source/review in CLI surfaces
- operator trace visibility improvements

P2:
- web control surface
- gateway/channel adapters

## Hermes Alignment
P1:
- usage telemetry stabilization

P2:
- lesson extraction
- skill improvement proposal workflow
- user approval before skill metadata updates

P3:
- memory recall loop

## Next Sprint Sequence
1. Real CLI Natural UX Fix completion hardening
2. Read-only Repo Inspection implementation
3. Real Small Coding Smoke (fixture-based)
4. Context / Resume / Compact
5. Sandbox Adapter
6. Skill Lifecycle
7. Learning Proposal

## Test Policy
- Core router tests do not replace real CLI entry smoke tests.
- Each critical response mode requires both core-level assertions and real-entry smoke coverage.
- Chat/help/usage/safety tests must assert no `Task task_`, no `Plan`, no `Result`, and no safe-fallback boilerplate.

## Read-only Repo Inspection Baseline
- `repo_inspection` does not enter task flow.
- Inspection is strictly read-only.
- No shell commands are executed in inspection mode.
- Sensitive files are skipped by denylist policy.
- File reads are constrained by file-size, total-byte, file-count, and tree-entry limits.
- Inspection writes structured trace records for operator visibility.
- Coverage requires both core-level tests and real CLI smoke.

## Real Small Coding Smoke + Rethink/Replan Baseline
- Only `coding_task` enters task flow.
- Before approval: no file writes and no shell test execution.
- After approval: patch apply and diff evidence are required.
- Scoped tests are preferred over full regression.
- Test failure must feed `judge` and produce `replan` or `blocked`.
- Loop decisions include `done`, `blocked`, `approval_denied`, `max_rounds`, `unsafe`, or `user_needed`.
- Rethink/replan records are written for operator visibility; no automatic skill mutation in this phase.

## JARVIS.md Instruction Baseline
- Load builtin guidance plus `JARVIS.md`, `AGENTS.md`, `CLAUDE.md`, and `.jarvis/JARVIS.override.md` when present.
- Record instruction provenance for every source.
- Treat instructions as guidance, never as safety permission.

## Coding Loop Hardening Baseline
- `coding_loop` response mode routes to `CodingLoopOrchestrator`.
- The legacy safe/task flow remains a fallback for non-coding executor paths.
- Deterministic judge runs before any LLM explanation.
- Failed tests trigger rethink/replan and cannot be marked as success by instructions.

## File Structure Boundary
- `jarvis/` remains the real CLI compatibility layer.
- `src/jarvis/core/` is the core implementation home.
- Core tests should import `src.jarvis.core.*`; real CLI smoke tests should call `python -m jarvis.cli`.

## Recommended Next Action Baseline
- Repo inspection recommends coding smoke or scoped validation.
- Coding `done` recommends Context / Resume / Compact.
- `max_rounds`, `test_failed`, and `approval_required` produce explicit next actions.

## Intent + Agent Loop Gateway
- `InputGateway` normalizes raw CLI text into an envelope with language, slash-command, URL, workspace, and session metadata.
- `DeterministicIntentRouter` owns high-confidence chat/help/usage/repo/coding/shell/search/url rules.
- `LLMIntentClassifier` is only a fallback for semantic uncertainty and must return strict JSON.
- `ClarificationPolicy` is the last resort for truly ambiguous input.
- `RouteSafetyGate` remains the code-enforced layer for approval, write, shell, network, and secret boundaries.
- `coding_loop` continues into `CodingLoopOrchestrator`; natural responses and repo inspection never regress into task fallback.

## Input Handling v1 Baseline
- `InputEnvelope` must not do business intent classification and must not call LLM.
- `CommandRegistry` centralizes command metadata such as `description`, `argument_hint`, `allowed_tools`, `dispatch`, and `risk_level`.
- `CommandRouter` handles `/help`, `/context`, `/compact`, `/resume`, `/approve`, `/reject`, `/exit`, and similar control-plane commands directly.
- Slash command parsing must preserve `raw_args`.
- Unix absolute paths such as `/Users/...` or `/etc/hosts` must not be treated as unknown slash commands.
- `SkillCommandRouter` follows OpenClaw-style split:
  - `command-dispatch: tool` -> deterministic tool route + approval/safety
  - default dispatch -> agent request with injected skill context
- `NaturalLanguagePreparer` prepares workspace/session/url/path/sensitive hints and available command/skill metadata without doing business intent classification.
- `IntentGateway` only handles non-command natural language:
  1. safety precheck
  2. deterministic route
  3. LLM fallback
  4. clarification
- `HookStageRegistry` provides non-invasive scaffolding for Claude/Hermes-style lifecycle hooks: `user_prompt_submit`, `pre_tool_use`, `post_tool_use`, and `stop`.
