# Jarvis Input Handling v1

## Layering

Jarvis input handling is intentionally split into layers:

`InputEnvelope`
- Parse structural facts only.
- Detect empty input, slash-shaped input, URL hints, path hints, workspace root, session id, and sensitive hints.
- Never decide business intent.
- Never call LLM.

`CommandRouter`
- Handle explicit control-plane commands such as `/help`, `/context`, `/compact`, `/resume`, `/approve`, and `/reject`.
- Keep `command_name`, `raw_args`, and `args_tokens`.
- Unknown slash commands must not enter LLM.

`CommandRegistry`
- Central command metadata surface inspired by Claude Code command files and Hermes command registry.
- Exposes `description`, `argument_hint`, `allowed_tools`, `dispatch`, and `risk_level`.
- `allowed_tools` can only narrow command execution scope; it never grants permission.

`SkillCommandRouter`
- Resolve user-invocable skill commands.
- Support OpenClaw-style split:
  - `command-dispatch: tool` -> deterministic tool route + approval/safety
  - default model dispatch -> agent request with injected skill context

`NaturalLanguagePreparer`
- Prepare workspace/session/URL/path/sensitive hints plus available command and skill metadata.
- Do not classify business intent.
- Do not call LLM.

`IntentGateway`
- Handles only non-command natural language.
- Order:
  1. safety precheck
  2. deterministic router
  3. LLM fallback classifier
  4. clarification policy

`SafetyGate`
- Remains code-enforced.
- LLM, JARVIS.md, AGENTS.md, and SKILL.md cannot bypass approval, secret refusal, shell gating, or write gating.

`Hooks Scaffold`
- Defines `user_prompt_submit`, `pre_tool_use`, `post_tool_use`, and `stop` stages.
- Exists as a no-op registry scaffold in v1 and does not alter current behavior.

## Claude Code Alignment

- Built-in slash commands are handled locally by the CLI harness.
- Natural language enters agent routing instead of being forced through slash/command parsing.
- Unix-style absolute paths such as `/Users/...` or `/etc/hosts` must not be misclassified as slash commands.
- Tool outcomes feed the next loop step, but command parsing itself stays local and deterministic.
- Command-file style metadata maps to Jarvis `CommandRegistry`.
- Hook stages are mirrored as scaffolding only in this sprint.

## OpenClaw Alignment

- Gateway handles commands before semantic intent classification.
- Skill commands can be exposed as slash commands.
- `command-dispatch: tool` routes directly to tool dispatch, still behind safety and approval.
- Default skill commands become agent requests with preserved command arguments.
- Natural-language replies are prepared with workspace/session context before agent routing.

## Hermes Alignment

- Central command metadata is shared by CLI-friendly routing code.
- Skills and context are treated as preparation context, not as permissions.
- Hook scaffolding follows Hermes shell-hook separation, but without changing runtime behavior.

## Codex Alignment

- Project instructions and environment context remain part of prepared input, not execution permission.
- Approval, sandbox, and exec policy remain explicit code-owned boundaries.
- Future `compact` and `resume` belong to a later context lifecycle sprint, not to Input Handling v1.

## Golden Set

Input Handling v1 is guarded by a golden set covering:
- greetings
- capability/help
- repo inspection
- coding creation
- shell execution
- safety refusal
- vague writing clarification
- generic ambiguity clarification
- slash commands
- path-vs-command distinction
