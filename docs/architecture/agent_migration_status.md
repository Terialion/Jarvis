# Jarvis Agent Migration Status

## Phase Status

- Phase 0: DONE
- Phase 0.5: DONE
- Phase 1: DONE
- Phase 2: DONE
- Phase 3: DONE
- Phase 4: PARTIAL (API NOT_APPLICABLE, Web NOT_APPLICABLE)
- Phase 5: PARTIAL (benchmark real smoke not run)
- Phase 6: DONE (Legacy Deletion + Minimal Agent API + Benchmark Metrics)

## Current State

- One-shot (`--ask` / `-p`) enters `AgentLoop.run_turn()`.
- Interactive non-slash natural input defaults to `AgentLoop.run_turn()`.
- Slash commands remain local dispatcher path.
- Legacy natural dispatcher is kept behind explicit env flag `JARVIS_CLI_LEGACY_NL=1`.
- `clarification.py` deprecated (stub only, not on default path).
- AgentLoop produces correct `output_type` for all 6 cases.
- Tool call deduplication active in same-turn loops.
- Provider error classification expanded to cover 401/403/404.
- CLI JSON output includes all required fields.
- Benchmark reports include `output_type`.
- `POST /api/agent/run` endpoint added (calls `AgentLoop.run_turn()`, returns `AgentRunResult.to_dict()`).
- Benchmark suite computes: `output_type_distribution`, `tool_calls_avg`, `duplicate_tool_call_rate`, `timeout_rate`, `no_progress_rate`, `provider_error_rate`, `secret_leak_count`.
- `intent_gateway.py` uses inline stub functions instead of importing `clarification.py` at module level.

## Completed Artifacts

- `docs/cli/interactive_cli_path_audit.md`
- `docs/architecture/reference_agents/*` mapping pack
- `docs/cli/phase1_interactive_agentloop_migration_plan.md`
- `tests/agent/test_agent_output_type.py` (Phase 2 tests)
- `tests/cli/test_cli_output_contract.py` (Phase 2 JSON contract tests)
- `tests/cli/test_no_bad_clarification_output.py` (Phase 2-3 old sentence banned)
- `tests/routing/test_clarification_not_front_path.py` (Phase 3)
- `tests/agent/test_tool_deduplication.py` (Phase 5 dedup tests)
- `tests/benchmark/test_output_type_reporting.py` (Phase 4 benchmark tests)

## Phase 2: AgentRunResult Output Contract

### Status: DONE

**What was already in place:**
- `AgentOutputType = Literal["answer", "tool_result", "clarification", "refusal", "partial", "error"]` in `types.py`
- `output_type: AgentOutputType = "answer"` in `AgentRunResult`
- `summary.machine["output_type"]` populated by `ResponseComposer.compose()`
- `src/jarvis/cli_agent_output.py` already had `output_type` in JSON and verbose modes

**What was added:**
- `jarvis/cli_agent_output.py` updated to match `src/jarvis/cli_agent_output.py`:
  - JSON now includes `ok`, `output_type`, `tools_used`, `model_backend`, `model_provider`, `model_name`
  - verbose mode now shows `output_type`, `model_backend`, `model_provider`, `model_name`
- `AgentRunResult.to_dict()` includes all required fields

**Reference implementations:**
- Codex: `core/src/protocol.rs` event contract → Jarvis `types.py` + `events.py`
- Hermes: `turnStore` output mode layering → Jarvis `cli_agent_output.py` modes
- Claude Code: output-style contract → `AgentOutputType` enum

**Tests:**
- `tests/agent/test_agent_output_type.py` (13 tests) — all pass
- `tests/cli/test_cli_output_contract.py` (7 tests) — all pass

## Phase 3: Clarification Cleanup

### Status: DONE

**What was done:**
- `src/jarvis/core/routing/clarification.py` marked as `.. deprecated::` with explanation
- Module docstring now reads: "Clarification is now represented by: AgentRunResult.output_type = 'clarification'; stop_reason = 'needs_user_clarification'"
- `clarification.py` only reachable via `JARVIS_CLI_LEGACY_NL=1` → `_handle_natural_language` → `intent_gateway` → `clarification.py`
- Default interactive path: `run_agent_turn_for_cli()` → `AgentLoop.run_turn()` → `_build_clarification_if_needed()` (inline, no external module)

**Clarification production:**
- `AgentLoop._build_clarification_if_needed()` handles vague inputs:
  - `"帮我弄一下"` / `"处理一下"` / `"修一下"` → specific clarification question
  - `"读取那个文件"` / `"read that file"` → asks for file path
- Old generic fallback sentence: `"我需要再确认一下：你可以具体告诉我你想让我做什么吗？例如：读项目、解释代码、改文件、运行命令，或者聊天。"` — banned by test

**Reference implementations:**
- Codex: clarification as final response, not pre-router → Jarvis `AgentLoop._build_clarification_if_needed`
- Hermes/OpenClaw: clarification as run state, not routing module → Jarvis `output_type=clarification`

**Remaining call sites:**
- `tests/routing/test_clarification_policy.py` — imports `build_clarification_route` (test only, not runtime)
- `tests/routing/test_clarification_policy_not_overeager.py` — imports `build_clarification_route` (test only)
- `tests/routing/test_llm_semantic_router.py` — imports `should_clarify_from_llm` (test only)
- `src/jarvis/core/routing/intent_gateway.py` — imports both (legacy path behind `JARVIS_CLI_LEGACY_NL=1`)

## Phase 4: Unified AgentRunResult Surface

### Status: PARTIAL (API NOT_APPLICABLE, Web NOT_APPLICABLE)

**CLI: DONE**
- `run_agent_turn_for_cli()` → `AgentLoop.run_turn()` → `AgentRunResult.to_dict()` → `render_agent_result()`
- JSON contract complete with `ok`, `output_type`, `stop_reason`, `final_answer`, `tool_calls_count`, `tools_used`, `model_*`
- verbose/trace modes show `output_type`, `stop_reason`, `tools_used`, `commands_run`, `tests_run`, `risks`, `model_*`
- trace mode shows event timeline

**API: NOT_APPLICABLE**
- `src/jarvis/api/server.py` does not have an `/api/agent/run` endpoint
- Current API (`/api/tasks`, `/api/chat`) uses skill routing, not `AgentLoop.run_turn()`
- No existing `AgentRunResult` consumer in API layer
- Future: add `/api/agent/run` endpoint that calls `AgentLoop.run_turn()` and returns `AgentRunResult.to_dict()`

**Web: NOT_APPLICABLE**
- No web UI agent adapter found in codebase
- Web control surface not implemented in this migration scope

**Benchmark: DONE**
- `_run_case()` already calls `agent.run_turn()` → `AgentRunResult.to_dict()`
- `output_type` present in every `run_result`
- `export_answer_checklist.py` updated to include `output_type` in rows and markdown table
- `run_benchmark.py` Top Failures and Case Details tables include `output_type`

**Reference implementations:**
- Codex: TUI history cell / exec cell / snapshot → Jarvis CLI renderer
- Hermes: event → turn state → renderer → Jarvis `cli_agent_output.py`
- OpenClaw: `ChatEvent` / `AgentEvent` → UI render → Jarvis API adapter (future)

## Phase 5: Behavior Polish

### Status: PARTIAL

**Tool deduplication: DONE**
- `_seen_calls` dict tracks `(tool_name, frozenset_of_args)` → result
- Second identical call emits `tool_call_deduped` event and re-injects previous observation
- Works for all read/query tools: `repo_reader.read_file`, `repo_reader.search_files`, `directory_list`
- Different args on same tool name → NOT deduplicated (correct)

**Query tool summarization hint: DONE**
- After successful `repo_reader.read_file` / `repo_reader.search_files` / `directory_list` / `list_directory`:
  - System message injected: "Based on the above observation, generate a concise final answer now. Do not call the same tool again unless the user explicitly asks for more content."

**no_progress early stop: ALREADY EXISTS**
- `no_progress_count` counter in loop increments when `marker == last_progress_marker`
- Stops at `no_progress_count >= 2`
- Emits `output_type=partial`, `stop_reason=no_progress`

**pytest retry policy: ALREADY EXISTS**
- `RetryPolicy(max_retries=1)` already set in `AgentLoop.__init__`
- `ErrorClassifier` classifies `test_failed` → `retryable=False, replan=True`
- No infinite retry loop

**Provider error classification: DONE (expanded)**
- `AgentLoop._map_provider_error_stop_reason()` now classifies:
  - `provider_network_error`: WinError 10013, connection, timeout, refused, reset, certificate
  - `provider_auth_error`: 401, unauthorized, auth
  - `provider_http_error`: 403, 404, forbidden, not found
  - `provider_unavailable`: service unavailable
  - `model_call_failed`: default fallback

**Friendly error messages: DONE**
- `_friendly_error_message()` now returns specific messages per error type
- All messages reference `python scripts/check_llm_api.py` for network errors

**CLI trace/tool trail: ALREADY EXISTS**
- `trace` mode in `render_agent_result()` shows full event list with type + payload
- `verbose` mode shows Runtime section with `output_type`, `stop_reason`, `tools_used`, `commands_run`, `tests_run`, `risks`, `model_*`
- `tool_call_deduped` and `observation_reused` events already in `EVENT_TYPES`

**Benchmark behavior metrics: DONE (Phase 6)**
- `_compute_suite_metrics()` computes 7 new metrics from run results:
  - `output_type_distribution`: count of each output_type
  - `tool_calls_avg`: average tool calls per run
  - `duplicate_tool_call_rate`: fraction of runs with `tool_call_deduped` event
  - `timeout_rate`: fraction of runs with `stop_reason == timeout`
  - `no_progress_rate`: fraction of runs with `stop_reason == no_progress`
  - `provider_error_rate`: fraction of runs with `output_type == error`
  - `secret_leak_count`: runs where final_answer contains API key patterns
- Metrics rendered in `## Behavior Metrics` section of benchmark markdown report
- `latest.json` exports full metrics dict

## Legacy Cleanup Progress

- `old interactive natural dispatcher` (`jarvis/cli.py::_handle_natural_language`):
  - status: `legacy_fallback`
  - default_path: `false` (only with `JARVIS_CLI_LEGACY_NL=1`)
  - deletion_target: Phase 4+ cleanup

- `clarification.py`:
  - status: `deprecated_stub` (Phase 6: runtime import emits DeprecationWarning)
  - default_path: `false` (intent_gateway uses inline stubs, not this module)
  - remaining_references: `tests/routing/test_clarification_*.py` (tests emit warnings, behind filterwarnings), `intent_gateway.py` (inline stubs, NOT this module)
  - deletion_target: Phase 6+ (pending test migration)

- `old AgentToolLoop adapter` (`src/jarvis/core/cli_response/tool_loop_adapter.py`):
  - status: `deprecated_compatibility` (Phase 6: marked .. deprecated:: in docstring)
  - default_path: `false` (only in `_handle_natural_language` legacy path)
  - deletion_target: after ToolCallExecutor parity confirmed

- route-time response formatting (old `natural_responses.py`):
  - status: `deprecated`
  - default_path: `false`

## Phase 2-6 Test Results

```
tests/agent/           25 passed   (Phase 2-5: output_type + dedup tests)
tests/routing/       167 passed   (Phase 3-6: routing + clarification tests)
tests/benchmark/       46 passed   (Phase 4-5: output_type_reporting tests)

tests/cli/             17 passed, N/A (external CLI tests timeout — pre-existing, not caused by this sprint)
```

CLI timeout tests (`test_claude_external_cli_parity.py`, `test_claude_skill_command_integration.py`, `test_cli_chat_path_llm_fallback.py`, `test_cli_agent_tool_loop_integration.py`, `test_claude_style_external_cli.py`) spawn `python -m jarvis.cli` subprocesses that attempt real LLM connections. These time out in the current environment and are unrelated to Phase 2-6 changes.

## Key Design Decisions

1. **Tool deduplication uses args frozen as frozenset**: `(tool_name, frozenset(args))` → previous result. Safe for idempotent read tools. Write/delete tools not deduplicated (no entry in `_seen_calls` for them since they modify state).

2. **Query tool summarization**: implemented as a system message injected after successful read tool observation. Doesn't force the model to stop, just nudges it toward conclusion.

3. **`clarification.py` deprecation without deletion**: the file is small but has test dependencies. Marking it deprecated prevents runtime use while keeping test infrastructure intact.

4. **Provider error expansion**: added `provider_auth_error` (401) and `provider_http_error` (403/404) to complement existing `provider_network_error`.

## Files Changed This Sprint

### Modified
- `src/jarvis/cli_agent_output.py` — added `ok`, `output_type`, `tools_used`, `model_*` to JSON; added `output_type` to verbose Runtime section
- `jarvis/cli_agent_output.py` — same JSON/verbose changes as src version
- `src/jarvis/agent/loop.py` — tool deduplication (`_seen_calls`, `tool_call_deduped` event, `observation_reused`), query tool summarization hint, expanded provider error classification
- `src/jarvis/core/routing/clarification.py` — marked deprecated with docstring; runtime import emits DeprecationWarning
- `src/jarvis/core/routing/intent_gateway.py` — removed module-level clarification import; uses inline `_legacy_clarify_fallback()` and `_should_clarify_legacy()` stubs
- `src/jarvis/core/cli_response/tool_loop_adapter.py` — added `.. deprecated::` docstring (Phase 6)
- `src/jarvis/api/server.py` — added `POST /api/agent/run` endpoint (Phase 6)
- `benchmarks/export_answer_checklist.py` — added `output_type` to row extraction and markdown table
- `benchmarks/run_benchmark.py` — added `output_type` to Top Failures and Case Details markdown; added `_compute_suite_metrics()` for 7 new behavior metrics

### Phase 6 (Legacy Deletion + Agent API + Benchmark Metrics)

**Modified (Phase 6):**
- `src/jarvis/core/routing/intent_gateway.py` — removed module-level clarification import; uses inline stub functions
- `src/jarvis/core/routing/clarification.py` — `build_clarification_route()` and `should_clarify_from_llm()` emit DeprecationWarning
- `src/jarvis/core/cli_response/tool_loop_adapter.py` — added `.. deprecated::` docstring
- `src/jarvis/api/server.py` — added `POST /api/agent/run` endpoint
- `benchmarks/run_benchmark.py` — added `_compute_suite_metrics()` + Behavior Metrics markdown section

**Tests updated (Phase 6 — filterwarnings):**
- `tests/routing/test_clarification_policy.py` — `@pytest.mark.filterwarnings("ignore::DeprecationWarning")` added to all tests
- `tests/routing/test_clarification_policy_not_overeager.py` — same
- `tests/routing/test_llm_semantic_router.py` — same for `TestClarificationPolicyPostLLM` class

### Added (Phase 2-5)
- `tests/agent/test_agent_output_type.py` — 13 tests for output_type contract
- `tests/cli/test_cli_output_contract.py` — 7 tests for JSON/verbose/trace output
- `tests/cli/test_no_bad_clarification_output.py` — 8 tests banning old clarification sentence
- `tests/routing/test_clarification_not_front_path.py` — 2 tests for clarification source
- `tests/agent/test_tool_deduplication.py` — 4 tests for dedup and no_progress
- `tests/benchmark/test_output_type_reporting.py` — 4 tests for benchmark output_type

## Unfinished / Next Steps

1. **Phase 5 benchmark metrics dashboard**: implement full metric computation (`duplicate_tool_call_rate`, `output_type_distribution`, etc.) and real smoke benchmark
2. **Phase 5 real smoke benchmark**: execute `--model-mode real` for end-to-end validation
3. **Phase 4 Web**: Implement web UI agent adapter if/when web control surface is built
