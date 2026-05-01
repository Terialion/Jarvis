# Jarvis Architecture

## Package Layout

`jarvis/`

CLI compatibility layer and real entrypoint. Product CLI starts from `python -m jarvis.cli`.

`src/jarvis/`

Core implementation. New core modules live under `src/jarvis/core`.

`src/jarvis/core/coding_loop/`

Main coding task execution loop: orchestration, judge, rethink, replan, scoped tests, final review, and evidence.

`src/jarvis/core/rethink/`

Reusable rethink models and compatibility helpers. These remain useful for generic trigger classification and strategy proposals.

`src/jarvis/core/react_readiness/`

Readiness and experimental loop primitives. These provide broader ReAct concepts but are not the current CLI coding-loop main path.

`src/jarvis/core/routing/`

Intent + Agent Loop Gateway implementation: input normalization, deterministic routing, LLM fallback classification, clarification policy, safety gate, and routing trace.

## Import Policy

- Product CLI starts from `python -m jarvis.cli`.
- Core tests import `src.jarvis.core.*`.
- Real CLI smoke tests use subprocess with `python -m jarvis.cli`.
- Do not mix `jarvis.core` and `src.jarvis.core` in the same test.
- `jarvis/cli.py` should stay a compatibility shell that delegates to core modules.

## Intent + Agent Loop Gateway

The real CLI natural-language path should converge on:

`InputGateway`
-> `SlashCommandRouter`
-> `SafetyPrecheck`
-> `IntentGateway`
-> `DeterministicIntentRouter`
-> `LLMIntentClassifier`
-> `ClarificationPolicy`
-> `RouteSafetyGate`
-> `ResponseModeDispatcher`
-> `NaturalResponse | RepoInspection | CodingLoopOrchestrator | Executor | Refusal`

Design rules:

- Deterministic routing handles slash commands, safety refusals, and high-confidence natural-language intents.
- LLM fallback handles semantic uncertainty, not safety or permission.
- Clarification is only used when deterministic routing is uncertain and the LLM fallback is unavailable or low-confidence.
- Safety and approval remain code-enforced and cannot be overridden by JARVIS.md or LLM output.

## Input Handling v1

- `InputEnvelope` records structural facts only: empty input, slash shape, URL hints, path hints, sensitive hints, workspace root, and session id.
- `CommandRegistry` provides centralized command metadata: description, argument hint, allowed tools, dispatch mode, and risk level.
- `CommandRouter` handles explicit slash commands locally and never enters LLM.
- `SkillCommandRouter` supports OpenClaw-style tool-dispatch vs model-dispatch skill commands.
- `NaturalLanguagePreparer` assembles workspace/session/path/url/sensitive hints plus available command and skill metadata before natural-language routing.
- `IntentGateway` handles only non-command natural language with deterministic-first routing and LLM fallback only for uncertainty.
- `HookStageRegistry` exists as a no-op scaffold for `user_prompt_submit`, `pre_tool_use`, `post_tool_use`, and `stop`.
- `SafetyGate` remains the final code-enforced boundary for approval, shell, write, network, and secret access.
