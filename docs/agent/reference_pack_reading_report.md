# Jarvis Agent Reference Pack Reading Report

## 1. Reference Pack Status

- `found`: yes
- `zip_path`: `D:/Jarvis/jarvis_agent_reference_pack.zip`
- `extracted`: yes
- `extract_root`: `D:/Jarvis/reference/jarvis_agent_reference_pack/jarvis_agent_reference_pack`

## 2. Files Read

- `JARVIS_AGENT_AND_BENCHMARK_CODEX_SPEC_v2.md`
- `README.md`
- `00_gap_to_reference_matrix.md`
- `reference_index.json`
- `01_codex_reference.md`
- `02_hermes_reference.md`
- `03_openclaw_reference.md`
- `04_claude_code_reference.md`
- `05_jarvis_target_architecture.md`
- `06_codex_construction_prompt.md`
- `snippets/codex_key_snippets.md`
- `snippets/hermes_key_snippets.md`
- `snippets/openclaw_key_snippets.md`
- `snippets/claude_code_key_snippets.md`
- `blueprints/src/jarvis/agent/__init__.py`
- `blueprints/src/jarvis/agent/types.py`
- `blueprints/src/jarvis/agent/events.py`
- `blueprints/src/jarvis/agent/context.py`
- `blueprints/src/jarvis/agent/model.py`
- `blueprints/src/jarvis/agent/tools.py`
- `blueprints/src/jarvis/agent/summary.py`
- `blueprints/src/jarvis/agent/loop.py`

## 3. Codex References To Reuse

- `run_turn` style turn orchestration: context build -> model -> tool call -> tool result feedback -> final answer.
- Turn-scoped state discipline similar to `TurnContext`.
- Tool call as first-class event lifecycle with begin/end/fail semantics.
- Controlled execution path for command-like tools instead of direct handler bypass.

## 4. Hermes References To Reuse

- Error classification with recovery hints (`retryable`, `should_compress`, `should_fallback`).
- Context compression trigger model and summary-as-handoff framing.
- Text fallback tool-call parsing compatibility pattern when model output is mixed text/json.
- Tool event projection shape for timeline and benchmark scoring.

## 5. OpenClaw References To Reuse

- Agent loop lifecycle definition and message-to-reply pipeline framing.
- Session serialization / per-session run consistency principle.
- Transcript JSONL persistence discipline and compaction-aware housekeeping.
- Approval policy layering concept for exec-like actions.

## 6. Claude Code References To Reuse

- Strict permission and deny/ask split.
- PreToolUse/PostToolUse hook interception semantics.
- Skill metadata/frontmatter governance and `allowed-tools` style constraints.
- Hook failures as policy signals (deny for pre hooks, audit-only for post hooks).

## 7. Blueprint Files To Adopt

The following blueprint modules will be adopted as structure templates and then adapted to existing Jarvis implementations:

- `blueprints/src/jarvis/agent/types.py`
- `blueprints/src/jarvis/agent/events.py`
- `blueprints/src/jarvis/agent/context.py`
- `blueprints/src/jarvis/agent/model.py`
- `blueprints/src/jarvis/agent/tools.py`
- `blueprints/src/jarvis/agent/summary.py`
- `blueprints/src/jarvis/agent/loop.py`
- `blueprints/src/jarvis/agent/__init__.py`

## 8. Existing Jarvis Modules To Reuse

- `src/jarvis/core/task_runtime.py`: task artifacts and lifecycle attachment.
- `src/jarvis/core/react_readiness/heavy_runtime.py`: retry/rethink/fallback patterns and trace semantics.
- `src/jarvis/core/react_readiness/react_loop.py` and `step_runner.py`: bounded loop semantics.
- `src/jarvis/core/react_readiness/context_manager.py` and `context_compactor.py`: context layering and compaction behavior.
- `src/jarvis/core/react_readiness/replay_store.py`: event persistence adapter target.
- `src/jarvis/core/tools/*`: registry/runtime/schema safety chain and built-in tool contracts.
- `src/jarvis/core/llm/runtime_provider.py`: provider config and OpenAI-compatible runtime client.
- `src/jarvis/core/skill_harness/*`: skill discovery/matching/registry/execution.
- `src/jarvis/core/memory/store.py` and `retriever.py`: recall integration in context building.
- `src/jarvis/core/policy/*`: safety/permission/approval baseline.
- `src/jarvis/core/hooks/registry.py`: pre/post tool hook orchestration.

## 9. Modules Not Reused Directly (and Why)

- Direct Rust/TypeScript internals from Codex/OpenClaw are not reused directly due to language/runtime mismatch; only protocol and lifecycle patterns are ported.
- Full MCP native call stack from Codex is not copied; first version uses existing Jarvis tool/runtime path to keep safety and approval chain intact.
- Full Hermes ACP transport layer is not copied; first version uses existing Jarvis provider + tool runtime and only borrows event/parsing strategy.
- Existing `core/tools/loop.py` is not replaced in-place for this sprint; `src/jarvis/agent/loop.py` will be introduced as the benchmark-bound canonical entry for v0.1 while keeping existing CLI chain stable.

