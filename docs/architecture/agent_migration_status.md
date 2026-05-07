# Jarvis Agent Migration Status

## Phase Status

- Phase 0: DONE
- Phase 0.5: DONE
- Phase 1: DONE
- Phase 2: DONE
- Phase 3: DONE
- Phase 4: DONE for CLI/API/Benchmark; Web NOT_APPLICABLE
- Phase 5: DONE for core behavior and benchmark metrics
- Phase 6: DONE
- Phase 7: DONE
- Phase 7.1: DONE
- Phase 7.2: DONE
- Phase 8: DONE
- Phase 9: DONE
- Phase 10A: DONE
- Phase 10B: DONE
- Phase 11: DONE
- Phase 12: DONE
- Phase 13A: DONE
- Phase 13B: DONE
- Phase 14: DONE
- Phase 15: DONE
- Phase 16: DONE
- Phase 17: DONE
- Phase 18: DONE
- Phase 19: PLANNED
- Phase 20: PLANNED

## Current State

- One-shot prompt handling uses `AgentLoop.run_turn()`.
- Interactive non-slash natural input defaults to `AgentLoop.run_turn()`.
- Slash commands remain local dispatcher concerns.
- `JARVIS_CLI_LEGACY_NL` is deprecated and ignored; natural-language input always uses `AgentLoop.run_turn()`.
- Clarification is represented by `AgentRunResult.output_type="clarification"` and `stop_reason="needs_user_clarification"`.
- Renderer modules consume `AgentRunResult`; they do not make routing decisions.
- `/api/agent/run` calls `AgentLoop.run_turn()` and returns an AgentRunResult-compatible wrapper.
- Benchmark reports emit the required behavior metrics in `latest.json` and `latest.md`.
- AgentLoop now builds a structured `TurnContext` and `ContextPack` before model calls.
- Skill metadata is indexed into prompts, and full `SKILL.md` bodies load through the `skill.load` tool.
- Skill loading now supports ecosystem-compatible frontmatter and static validation in both `compatibility` and `strict` modes.
- Builtin executable skills now run through `SkillExecutor`, enforce each skill's normalized `allowed_tools`, and still call workspace capabilities via `ToolCallExecutor`.
- Context state now records skill observations, active task state, handoff summaries, and compactable context needed for multi-turn continuation.
- Benchmark v0.2 now includes a dedicated `context_skill` suite for skill loading, executable skills, runtime tool enforcement, multi-turn reuse, compaction preservation, and skill safety.
- Web research now has first-class `web.search` / `web.fetch` tools, an offline fake provider path, SSRF-guarded fetch extraction, a deterministic Phase 13 smoke suite, and a formal Phase 14 `web_research` benchmark suite.

## Phase 7 Outcomes

### API Smoke

- status: done
- endpoint: `POST /api/agent/run`
- contract: AgentRunResult-compatible wrapper over `result.to_dict()`
- tests:
  - `tests/api/test_agent_run_contract.py`
  - covers `answer`, `tool_result`, `refusal`, `clarification`, and provider-error shaping

### Benchmark Metrics

- status: done
- metrics:
  - `output_type_distribution`
  - `tool_calls_avg`
  - `duplicate_tool_call_rate`
  - `timeout_rate`
  - `no_progress_rate`
  - `provider_error_rate`
  - `secret_leak_count`
- tests:
  - `tests/benchmark/test_behavior_metrics.py`
  - `tests/benchmark/test_output_type_reporting.py`
- artifacts:
  - `benchmarks/reports/latest.json`
  - `benchmarks/reports/latest.md`
  - `temp/benchmark_answer_checklist.md`

### Real Smoke

- status: done
- commands executed:
  - `python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 3 --model-mode real`
  - `python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 10 --model-mode real`
- latest 10-case result:
  - `execution_mode=real_llm`
  - `provider_error_rate=0.0`
  - `secret_leak_count=0`
  - `output_type_distribution={'answer': 2, 'partial': 5, 'refusal': 1, 'tool_result': 2}`
- note:
  - the 10-case real run completed and wrote reports successfully
  - no `UnicodeDecodeError` traceback was emitted after forcing subprocess text decoding to `encoding="utf-8", errors="replace"`

## Legacy Cleanup Status

### clarification.py

- status: deleted
- path: `src/jarvis/core/routing/clarification.py`
- default_path: false
- remaining_references:
  - comments/docs only
  - legacy inline clarification stub in `src/jarvis/core/routing/intent_gateway.py`
- migration notes:
  - `tests/routing/test_clarification_policy.py` now asserts `AgentLoop.run_turn(...).output_type == "clarification"`
  - `tests/routing/test_clarification_policy_not_overeager.py` now checks ordinary inputs do not clarify on the default path
  - `tests/routing/test_llm_semantic_router.py` no longer imports deleted clarification helpers

### tool_loop_adapter.py

- status: deleted
- path: `src/jarvis/core/cli_response/tool_loop_adapter.py`
- default_path: false
- remaining_references: []
- deletion_completed: true

### legacy_nl_escape_hatch

- status: removed
- env: `JARVIS_CLI_LEGACY_NL`
- behavior: deprecated warning only; the variable is ignored
- default_path: false

## Regression Summary

- `tests/agent`: `47 passed`
- `tests/routing`: `146 passed`
- `tests/benchmark`: `79 passed`
- `tests/api`: `21 passed`
- `tests/cli`: `203 passed`
- `tests/skills`: `90 passed`

## Phase 7.1 Outcomes

### CLI Green

- status: done
- failure categories resolved:
  - outdated path/cwd assumptions in subprocess-based CLI tests
  - brittle natural-language copy assertions
  - JSON/output contract mismatches caused by direct quick-path handling
  - real-provider timing sensitivity in external CLI parity tests
- result:
  - `python -m pytest tests/cli -q` -> `230 passed`

### Secret Redaction

- status: done
- coverage:
  - `AgentRunResult.to_dict()` redacts final answers, summaries, tool observations, and nested string payloads
  - benchmark markdown/json/checklist exports redact secret-like content before writing artifacts
  - CLI JSON output tests cover secret masking
- latest result:
  - fake benchmark `secret_leak_count=0`
  - real smoke `secret_leak_count=0`

### Subprocess Encoding

- status: done
- changes:
  - subprocess wrappers now force `encoding="utf-8", errors="replace"`
  - invalid byte sequences are preserved as replacement text instead of crashing reader threads
- tests:
  - `tests/agent/test_subprocess_text_decoding.py`

## Phase 7.2 Outcomes

### Legacy Adapter Removal

- status: done
- runtime result:
  - interactive non-slash input always uses `AgentLoop.run_turn()`
  - one-shot prompt handling always uses `AgentLoop.run_turn()`
  - API and benchmark remain on `AgentLoop.run_turn()`
- test migration:
  - old adapter-specific suites were replaced by `AgentLoop` / `AgentRunResult` contract tests
  - `tests/cli/test_cli_agent_tool_loop_integration.py` was replaced by `tests/cli/test_cli_agentloop_integration.py`
  - `tests/cli_response` now validates renderer consumption of `AgentRunResult`
  - `tests/agent_loop` now validates `AgentLoop` tool-call behavior directly
- search result:
  - no runtime or test references remain for `tool_loop_adapter`, `AgentToolLoop`, or `execute_agent_tool_loop`

## Phase 8 Outcomes

### context_foundation

- turn_context: done
- context_builder: done
- prompt_builder: done
- context_compactor: done

### details

- `src/jarvis/agent/context.py`
  - introduces `ProjectContext`, `ConversationContext`, `MemoryContext`, `SkillContext`, `ContextPack`, and `TurnContext` assembly
  - reads project instruction hints from `AGENTS.md`, `JARVIS.md`, and `README.md`
- `src/jarvis/agent/prompt_builder.py`
  - constructs messages from `TurnContext` instead of ad-hoc message assembly
  - injects project context, memory summary, recent conversation, and skill metadata index
- `src/jarvis/agent/context_compactor.py`
  - adds `micro_compact`, `should_auto_compact`, and the compaction safety prefix
  - prefix explicitly states historical summaries are background only and not new instructions

## Phase 17 Outcomes

### persistent_memory_threadstore

- `thread_store`: done
- `turn_message_persistence`: done
- `tool_call_persistence`: done
- `skill_observation_persistence`: done
- `research_observation_persistence`: done
- `approval_audit_persistence`: done
- `active_task_persistence`: done
- `handoff_summary_persistence`: done
- `user_project_memory`: done
- `context_save_resume`: done
- `redaction_before_persistence`: done
- `benchmark`: done

### details

- `src/jarvis/store/schema.py`
  - defines persistent records for threads, turns, messages, tool calls, skill observations, research observations, approval audit records, active task state, handoff summaries, project facts, user memory, and project memory
- `src/jarvis/store/thread_store.py`
  - implements the durable SQLite-backed `ThreadStore`, schema versioning, restart-safe reopen behavior, and redaction on every persistence path
- `src/jarvis/store/memory_store.py`
  - implements user/project memory MVP on top of the durable store
- `src/jarvis/store/observation_store.py`
  - provides durable skill/research observation helpers without bypassing existing context writeback
- `src/jarvis/store/redaction.py`
  - centralizes persistence redaction by reusing the existing Jarvis secret masking utilities
- `src/jarvis/agent/context_store.py`
  - keeps the in-memory/session fast layer and hydrates it from `ThreadStore` when resuming threads
- `src/jarvis/agent/context_updater.py`
  - persists redacted turns, skill observations, research observations, approval audits, active task state, handoff summaries, and project facts after each turn
- `src/jarvis/agent/context.py`
  - loads persistent user/project memory and resumed thread state into `TurnContext`
- `src/jarvis/agent/prompt_builder.py`
  - injects persistent memory and resumed context with an explicit background-only safety prefix
- `src/jarvis/cli.py` and `jarvis/cli.py`
  - add `/context save`, `/context resume`, `/threads list`, `/threads open`, `/memory show`, `/memory edit`, and `/memory clear`, and remove the visible Chinese mojibake variants from CLI intent matching
- `src/jarvis/api/server.py`
  - exposes durable thread, observation, context, and memory endpoints without routing through a second agent loop
- `benchmarks/suites/persistent_memory/`
  - adds the formal persistent-memory suite
- `benchmarks/run_benchmark.py`
  - adds persistent memory suite execution and `persistent_memory_metrics`
- `benchmarks/export_answer_checklist.py`
  - exports persistent memory checklist fields

## Phase 17 Tail Fixes

- persistent_memory metric semantics: corrected
  - `benchmarks/run_benchmark.py` now computes `persistent_memory_metrics` with relevant-case denominators instead of whole-suite denominators
  - `benchmarks/reports/latest.md` now prints `metric_semantics: relevant_case_denominator` plus relevant-case counts per metric
  - `tests/benchmark/test_persistent_memory_metrics.py` now asserts the corrected semantics and 1.0 success rates for the applicable fake-suite cases
- dirty workspace handling: direct Phase 18 changes separated from pre-existing unrelated dirty changes
  - Phase 18 work was limited to control-surface files, benchmark/report plumbing, and related tests/docs
  - pre-existing unrelated dirty changes were not reverted or counted as Phase 18 output

## Phase 18 Outcomes

### web_control_surface

- `boundary_doc`: done
- `api_surface`: done
- `timeline`: done
- `tool_cards`: done
- `skill_cards`: done
- `web_cards`: done
- `source_evidence_cards`: done
- `approval_panel`: done
- `context_inspector`: done
- `thread_memory_browser`: done
- `benchmark_dashboard`: done
- `trace_log`: done
- `redaction`: done
- `benchmark`: done
- `browser_boundary_preserved`: done

### details

- `docs/web_control_surface.md`
  - documents the control-surface boundary, explicit non-routing/non-execution constraints, persistent-memory background-only framing, and browser automation deferral
- `src/jarvis/api/timeline.py`
  - builds redacted timelines from `AgentRunResult.events` and `ThreadStore` records without executing tools
- `src/jarvis/api/server.py`
  - exposes thread timeline, context inspector, benchmark dashboard, control-surface status, approval-panel actions, and `POST /api/agent/run` timeline output on the existing API server
- `src/jarvis/api/benchmark_dashboard.py`
  - serves the latest benchmark snapshot from `benchmarks/reports/latest.json` without rerunning benchmarks
- `src/jarvis/webui/static/control_surface.html`
  - provides a minimal static control surface for prompt input, timeline/cards, approvals, context inspection, thread/memory browsing, benchmark viewing, and trace inspection
- `benchmarks/suites/control_surface/`
  - adds the formal control-surface benchmark suite
- `benchmarks/run_benchmark.py`
  - adds `control_surface` suite execution, `control_surface_metrics`, and corrected persistent-memory metric semantics
- `benchmarks/export_answer_checklist.py`
  - exports control-surface checklist fields and redacted UI-related state

### latest benchmark snapshot

- `benchmarks/reports/latest.json`
  - `persistent_memory_metrics.metric_semantics = relevant_case_denominator`
  - `control_surface_metrics.control_surface_api_success_rate = 1.0`
  - `control_surface_metrics.timeline_build_success_rate = 1.0`
  - `control_surface_metrics.ui_redaction_success_rate = 1.0`
  - `control_surface_metrics.control_surface_secret_leak_count = 0`
  - `control_surface_metrics.browser_boundary_preserved_count = 9`
  - `control_surface_metrics.second_agent_loop_violation_count = 0`

## Regression Summary

- `tests/api`: `31 passed`
- `tests/benchmark`: `89 passed`
- `tests/store`: `15 passed`
- `tests/policy`: `36 passed`
- `tests/skills`: `90 passed`
- `tests/agent`: `47 passed`
- `tests/web`: `23 passed`
- `tests/cli`: `205 passed`
- `tests/routing`: `146 passed`

## Remaining Gaps

- Phase 19 Coding Workflow remains planned.
- Phase 20 MCP / Gateway / Channels remains planned.
- Full browser automation remains out of scope.
- Browser fallback remains out of scope.
- Channel adapters remain out of scope.
- Advanced semantic memory retrieval remains future work.
- Approval resume remains retry-based and audit-oriented; Phase 18 does not add a second agent loop or direct tool execution from the UI.

## Phase 9 Outcomes

### skill_loading

- skill_loader: done
- skill_registry: done
- builtin_skills:
  - `repo_overview`
  - `summarize_file`
  - `run_tests`
  - `fix_test_failure`
- load_skill_tool: done
- skill_events: done
- cli_skill_commands: done
- benchmark_skill_reporting: done

### details

- `src/jarvis/skills/loader.py`
  - parses `SKILL.md` frontmatter for `name`, `description`, `risk_level`, and `allowed_tools`
- `src/jarvis/skills/registry.py`
  - scans builtin skills, exports metadata-only index rows, and lazily loads full bodies
- `src/jarvis/agent/tools.py`
  - registers `skill.load`
  - returns full `SKILL.md` content as a tool observation without bypassing tool policy/runtime
- `src/jarvis/agent/loop.py`
  - emits `skill_index_built`, `skill_load_started`, `skill_loaded`, `skill_load_failed`, and `skill_observation_reused`
  - records `available_skills`, `loaded_skills`, and `skill_loads_count` in `AgentRunResult`
- `src/jarvis/cli.py` and `jarvis/cli.py`
  - local slash commands support `/skill list` and `/skill show <name>` without entering the LLM path
- `benchmarks/run_benchmark.py` and `benchmarks/export_answer_checklist.py`
  - report `skill_loads_count`, `loaded_skills`, and `available_skills_count`-related data

### latest benchmark snapshot

- fake benchmark:
  - `python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 10 --model-mode fake`
  - generated reports include `skill_loads_count` and `loaded_skills`
- real smoke:
  - `python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 3 --model-mode real`
  - latest result: `pass_rate=100%`, `provider_error_rate=0.0`, `secret_leak_count=0`

## Phase 10A Outcomes

### skill_authoring

- ecosystem_format_compatibility: done
- contract_doc: done
- template_doc: done
- validator: done
- compatibility_validation: done
- strict_validation: done
- allowed_tools_normalization: done
- risk_inference: done
- create_skill_script: done
- validate_skills_script: done
- cli_create: done
- cli_validate: done
- cli_doctor: done
- cli_index: done
- skill_scanner_doc: done
- builtin_skills_validated: done

### details

- `src/jarvis/skills/schema.py`
  - expands `SkillSpec` to carry `source`, `source_format`, `raw_allowed_tools`, normalized `allowed_tools`, `read_when`, `always_apply`, `metadata`, and `external_metadata`
- `src/jarvis/skills/loader.py`
  - accepts ecosystem frontmatter forms such as `allowed-tools`, `allowed_tools`, `read_when`, `alwaysApply`, and `metadata`
  - reads `_meta.json` and `_skillhub_meta.json`
  - normalizes ecosystem tools such as `Read`, `Write`, `Bash`, `WebFetch`, and `Bash(agent-browser:*)`
  - infers `risk_level` when not declared
- `src/jarvis/skills/validator.py`
  - implements `compatibility` and `strict` validation modes
  - checks required metadata, required sections, unknown tool mappings, risk/tool mismatches, hardcoded secret patterns, and prompt override indicators
- `src/jarvis/skills/registry.py`
  - scans builtin, project, user, home, and env-provided skill roots
  - preserves deterministic duplicate handling and records duplicate warnings without silent overwrite
- `src/jarvis/skills/authoring.py`
  - provides the ecosystem-compatible skill template
  - formats `/skill validate`, `/skill doctor`, and `/skill index` output
- `scripts/create_skill.py`
  - creates `.jarvis/skills/<name>/SKILL.md` using the ecosystem-compatible template
- `scripts/validate_skills.py`
  - validates one skill, one path, or all discovered skills
  - supports `--json` and `--mode compatibility`
- `src/jarvis/cli.py` and `jarvis/cli.py`
  - add `/skill create <name>`, `/skill validate <name>`, `/skill doctor`, and `/skill index`
- `docs/skills/skill_authoring_contract.md`
  - documents ecosystem compatibility, strict vs compatibility validation, and the Phase 10B runtime boundary
- `docs/skills/skill_template.md`
  - documents the recommended Jarvis-authored template using ecosystem-compatible frontmatter
- builtin skills
  - `repo_overview`, `summarize_file`, `run_tests`, `fix_test_failure`, and `skill_scanner` now pass strict validation with no errors

### validation snapshot

- builtin strict checks:
  - `python scripts/validate_skills.py --skill summarize_file` -> `Status: OK`
  - `python scripts/validate_skills.py --skill skill_scanner` -> `Status: OK`
- full doctor sweep:
  - `python scripts/validate_skills.py` scans all discovered skills
  - imported marketplace-style skills under `skills/` are validated in `compatibility` mode by default
  - the command currently exits non-zero because several imported skills contain real static findings such as secret-like patterns or prompt-override indicators

### benchmark snapshot

- fake benchmark:
  - `python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 10 --model-mode fake`
  - latest metrics include `available_skills_count=111`, `skill_loads_count`, and `loaded_skills`
- real smoke:
  - `python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 3 --model-mode real`
  - latest metrics include `available_skills_count=111`, `provider_error_rate=0.0`, and `secret_leak_count=0`

## Phase 10B Outcomes

### skill_runtime

- skill_executor: done
- skill_call_contract: done
- skill_execution_context: done
- allowed_tools_runtime_enforcement: done
- builtin_executable_skills:
  - summarize_file: done
  - repo_overview: done
  - run_tests: done
  - fix_test_failure_dry_run: done
- skill_events: done
- cli_trace: done
- benchmark_reporting: done

### details

- `src/jarvis/skills/runtime.py`
  - introduces `SkillCall`, `SkillStep`, `SkillExecutionContext`, and `SkillResult`
- `src/jarvis/skills/executor.py`
  - executes builtin skills through the existing `ToolCallExecutor`
  - denies tools that are not permitted by the skill's normalized `allowed_tools`
  - records `skill_call_started`, `skill_step_started`, `skill_tool_denied`, `skill_observation_added`, and `skill_call_completed` events
  - refuses secret-bearing file targets such as `.env` before invoking file-read tools
- `src/jarvis/agent/loop.py`
  - maps stable builtin skill intents into `SkillCall` objects without restoring the old dispatcher
  - intercepts model `skill.run` tool calls and routes them into the same `SkillExecutor` path
  - records `skills_used`, `skill_calls_count`, and `skill_results` on `AgentRunResult`
- `src/jarvis/agent/tools.py`
  - exposes `skill.run(name, arguments)` as the model invocation contract while keeping actual execution inside `AgentLoop`
- `src/jarvis/cli_agent_output.py` and `jarvis/cli_agent_output.py`
  - render skill runtime fields in verbose/trace/json output
- `src/jarvis/api/server.py`
  - includes skill runtime fields in `/api/agent/run`
- `benchmarks/run_benchmark.py` and `benchmarks/export_answer_checklist.py`
  - report `skills_used`, `skill_calls_count`, `skill_results_count`, and context-fusion indicators

## Phase 11 Outcomes

### context_skill_fusion

- context_store: done
- context_updater: done
- skill_observation_writeback: done
- multi_turn_reference: done
- observation_reuse: done
- active_task_state: done
- handoff_summary: done
- compaction_preserves_skill_state: done

### details

- `src/jarvis/agent/skill_context.py`
  - introduces `SkillObservation`, `ActiveTaskState`, and `HandoffSummary`
- `src/jarvis/agent/context_store.py`
  - adds an in-memory session context store for recent turns, skill observations, project facts, active task state, and handoff summaries
- `src/jarvis/agent/context_updater.py`
  - writes skill results back into context after each turn without calling tools or models
  - updates `AgentRunResult.summary.machine` with active task, handoff, and skill observation summaries
- `src/jarvis/agent/context.py`
  - loads relevant stored observations and active task state into `ContextPack`
- `src/jarvis/agent/prompt_builder.py`
  - injects concise prior skill observations and active task state while keeping full skill bodies out of the prompt
- `src/jarvis/agent/context_compactor.py`
  - preserves active task, skills used, related files, remaining work, risks, and handoff state behind the safety prefix stating that summaries are not new instructions
- `src/jarvis/agent/loop.py`
  - reuses recent skill observations for follow-up references such as "刚才那个文件" and records `context_observation_reused`

### latest benchmark snapshot

- fake benchmark:
  - `.venv\Scripts\python.exe benchmarks/run_benchmark.py --suite jarvis_core --max-cases 10 --model-mode fake`
  - latest metrics: `provider_error_rate=0.0`, `secret_leak_count=0`, `available_skills_count=111`, `skill_results_count=0`, `handoff_summary_present_rate=1.0`
- checklist export:
  - `.venv\Scripts\python.exe benchmarks/export_answer_checklist.py`
  - `temp/benchmark_answer_checklist.json` includes `skills_used`, `skill_calls_count`, `context_reuse`, `active_task_present`, and `handoff_summary_present`

## Phase 12 Outcomes

### context_skill_benchmark

- suite: done
- skill_loading_cases: done
- skill_execution_cases: done
- allowed_tools_enforcement_cases: done
- multi_turn_context_cases: done
- context_compaction_cases: done
- skill_safety_cases: done
- metrics: done
- checklist_fields: done
- fake_benchmark: done
- real_smoke: not_run

### details

- `benchmarks/suites/context_skill/`
  - adds:
    - `skill_loading.jsonl`
    - `skill_execution.jsonl`
    - `allowed_tools_enforcement.jsonl`
    - `multi_turn_context.jsonl`
    - `context_compaction.jsonl`
    - `skill_safety.jsonl`
- `benchmarks/case_schema.py`
  - supports multi-turn `turns`, per-case `setup`, and `expected` compatibility aliasing without breaking single-turn suites
- `benchmarks/run_benchmark.py`
  - adds `context_skill` suite registration
  - loads every `*.jsonl` file inside a suite directory
  - runs multi-turn cases with a shared benchmark session id
  - supports setup fixtures for injected skill observations, active tasks, handoff summaries, compaction summaries, and disallowed-tool attempts
  - aggregates per-turn results into one case result with full event/tool/skill trails
  - emits top-level `behavior_metrics` and `context_skill_metrics`
- `benchmarks/evaluators/behavioral.py`
  - adds structured checks for:
    - `must_use_skills`
    - `must_have_events`
    - `must_have_skill_results`
    - `must_context_reuse`
    - `must_reference_previous_file`
    - `must_preserve_active_task`
    - `must_preserve_skill_state`
    - `must_include_compaction_safety_prefix`
    - denied-tool/risk assertions
- `benchmarks/export_answer_checklist.py`
  - scans all suite `*.jsonl` case files
  - exports:
    - `skills_used`
    - `skill_calls_count`
    - `skill_results_count`
    - `loaded_skills`
    - `skill_loads_count`
    - `context_reuse`
    - `active_task_present`
    - `handoff_summary_present`
    - `skill_observation_reused`
    - `skill_tool_denied_count`
- `src/jarvis/skills/executor.py`
  - returns normalized attempted/allowed tool-call shapes with call ids so benchmark trail validation can audit skill runtime consistently

### latest fake benchmark snapshot

- command:
  - `.venv\Scripts\python.exe benchmarks/run_benchmark.py --suite context_skill --model-mode fake`
- result:
  - `pass_rate=100%`
  - `secret_leak_count=0`
  - `skill_load_success_rate=1.0`
  - `skill_execution_success_rate=1.0`
  - `skill_tool_denied_count=2`
  - `multi_turn_context_success_rate=1.0`
  - `context_compaction_success_rate=1.0`

### latest all-suites fake benchmark snapshot

- command:
  - `.venv\Scripts\python.exe benchmarks/run_benchmark.py --all --model-mode fake`
- result:
  - completed successfully and wrote `benchmarks/reports/latest.json` and `benchmarks/reports/latest.md`
  - `context_skill_metrics` present at top level
  - `secret_leak_count=0`
- existing legacy suite pass-rate variation remains visible instead of being hidden

## Phase 13A Outcomes

- web.search: done
- web.fetch: done
- provider contracts: done
- fake provider: done
- fetch safety: done
- source classifier: done
- cache: done
- readable extraction: done
- web events: done

### details

- `src/jarvis/web/schema.py`
  - defines `SearchQuery`, `SearchResult`, `SearchRun`, `FetchRequest`, `ReadableDocument`, `FetchRun`, `WebToolResult`, and `SourceRef`
- `src/jarvis/web/providers/base.py`
  - establishes the provider contract
- `src/jarvis/web/providers/fake.py`
  - provides deterministic offline search results for tests and smoke runs
- `src/jarvis/web/providers/brave.py`
  - remains an optional skeleton provider and returns structured `provider_not_configured` results
- `src/jarvis/web/providers/router.py`
  - routes `provider=auto` to the fake provider by default
- `src/jarvis/web/search.py`
  - implements providerized `web.search` without fetching page bodies
- `src/jarvis/web/fetch.py`
  - implements safe `web.fetch` with readable extraction, redirect re-check, byte/char limits, and secret redaction
- `src/jarvis/web/safety.py`
  - blocks `file://`, loopback, private IPs, link-local addresses, internal hostnames, and metadata service targets
- `src/jarvis/web/source_classifier.py`
  - classifies sources into official docs, GitHub issue/PR, release notes, forum, blog, and unknown
- `src/jarvis/web/cache.py`
  - caches search and fetch results behind normalized keys without bypassing safety checks
- `src/jarvis/web/README.md`
  - documents the explicit boundary between `web.fetch` and future browser automation
- `src/jarvis/agent/tools.py`
  - registers `web.search` and `web.fetch` as first-class tools inside the existing ToolRuntime / ToolCallExecutor chain
- `src/jarvis/agent/events.py`
  - adds:
    - `web_search_started`
    - `web_search_completed`
    - `web_search_failed`
    - `web_fetch_started`
    - `web_fetch_completed`
    - `web_fetch_failed`
    - `web_fetch_blocked`
    - `web_content_extracted`

## Phase 13B Outcomes

- intent classifier: done
- query rewriter: done
- search planner: done
- provider routing: done
- dedup/rerank: done
- fetch selector: done
- evidence extractor: done
- answer composer: done
- ResearchObservation context write-back: done
- multi-turn research reuse: done

### details

- `src/jarvis/web/research.py`
  - adds `SearchIntentClassifier`
  - adds the deterministic `WebResearchPipeline`
  - runs `search -> rerank -> fetch -> evidence -> answer` without creating a second AgentLoop
- `src/jarvis/web/query_rewriter.py`
  - generates source-aware search tasks, including explicit official-docs + GitHub + general-workaround branches for Flink CDC bug verification
- `src/jarvis/web/search_planner.py`
  - deduplicates and caps search tasks
- `src/jarvis/web/rerank.py`
  - normalizes URLs, drops duplicates, and boosts official/GitHub sources
- `src/jarvis/web/fetch_selector.py`
  - chooses fetch targets with source-type coverage, especially for bug verification
- `src/jarvis/web/evidence.py`
  - extracts short evidence objects with `source_url`, `source_type`, `stance`, and `confidence`
  - judges source coverage quality
- `src/jarvis/web/answer_composer.py`
  - composes evidence-grounded answers and downgrades to `partial` when evidence is weak
- `src/jarvis/web/research_context.py`
  - defines `ResearchObservation`
- `src/jarvis/agent/loop.py`
  - adds a thin deterministic web-research branch before the model/tool loop
  - reuses prior `ResearchObservation` for follow-ups such as “刚才查到的官方资料怎么说？”
- `src/jarvis/agent/context_store.py`
  - stores `research_observations`
- `src/jarvis/agent/context_updater.py`
  - writes `ResearchObservation` back into context after each research turn
- `src/jarvis/agent/context.py` and `src/jarvis/agent/prompt_builder.py`
  - inject recent research observations as background only, not new instructions

### Phase 13 Smoke Reporting

- suite: done
- artifacts:
  - `benchmarks/suites/web_research_smoke/web_search_smoke.jsonl`
  - `benchmarks/suites/web_research_smoke/web_fetch_safety_smoke.jsonl`
  - `benchmarks/suites/web_research_smoke/web_research_pipeline_smoke.jsonl`
- `benchmarks/run_benchmark.py`
  - now exposes `web_research_smoke_metrics` in `latest.json` / `latest.md`
  - labels them as Phase 13 smoke reporting only
- latest fake smoke snapshot:
  - `web_search_runs_count=6`
  - `web_fetch_runs_count=3`
  - `web_fetch_blocked_count=1`
  - `evidence_count=5`
  - `official_sources_count=2`
  - `github_sources_count=2`
  - `research_context_reused=1`
  - `web_secret_leak_count=0`

## Phase 14 Outcomes

- web_research suite: done
- fake provider fixtures: done
- fetch safety benchmark: done
- evidence metrics: done
- source bias metrics: done
- context reuse metrics: done
- prompt injection safety benchmark: done
- browser automation boundary: preserved

### Formal Suite

- artifacts:
  - `benchmarks/suites/web_research/provider_selection.jsonl`
  - `benchmarks/suites/web_research/search_then_fetch.jsonl`
  - `benchmarks/suites/web_research/fetch_safety.jsonl`
  - `benchmarks/suites/web_research/official_source_bias.jsonl`
  - `benchmarks/suites/web_research/github_issue_lookup.jsonl`
  - `benchmarks/suites/web_research/evidence_extraction.jsonl`
  - `benchmarks/suites/web_research/stale_source_detection.jsonl`
  - `benchmarks/suites/web_research/context_reuse.jsonl`
  - `benchmarks/suites/web_research/prompt_injection_safety.jsonl`
- latest fake formal result:
  - `web_research` cases: `13`
  - pass_rate: `100%`
  - `web_secret_leak_count=0`
  - `web_fetch_blocked_count=1`
  - `prompt_injection_blocked_count=1`
  - `web_provider_error_rate=0.077`
  - `web_no_results_rate=0.077`

### Reporting

- `benchmarks/run_benchmark.py`
  - now emits `web_research_metrics` in `latest.json` and `latest.md`
  - keeps `web_research_smoke_metrics` clearly labeled as Phase 13 quick smoke reporting
- `benchmarks/export_answer_checklist.py`
  - now exports web research checklist fields for search/fetch counts, sources, evidence, citations, stale-source count, dedup count, research reuse, prompt-injection blocking, provider errors, and web secret leaks
- tests:
  - `tests/benchmark/test_web_research_suite.py`
  - `tests/benchmark/test_web_research_metrics.py`
  - `tests/benchmark/test_web_research_checklist.py`

### Web Tool Boundary

- `web.fetch` remains limited to safe HTTP/HTTPS GET plus readable extraction.
- `web.fetch` does not execute JavaScript, does not perform DOM interaction, does not handle login/button/screenshot/dynamic navigation flows, and is not browser automation.
- Fetched content remains untrusted and is not upgraded into system/developer/tool instructions.
- Browser automation and browser fallback remain out of scope for Phase 14 and later control-surface display work unless a future dedicated browser phase implements it.

## Phase 15 Outcomes

### skill_lifecycle

- install: done
- enable_disable: done
- update_check: done
- trust_quarantine: done
- source_management: done
- registry_filtering: done
- load_run_blocking: done
- benchmark: done

### details

- `docs/architecture/reference_code/`
  - contains the extracted Phase 13-20 reference pack as a single-layer `reference_code` tree
  - verified there is no nested `reference_code/reference_code` directory
- `src/jarvis/skills/lifecycle.py`
  - defines `SkillInstallRecord`, `SkillEnabledState`, lifecycle persistence, install/update/check, and enable/trust/quarantine operations
- `src/jarvis/skills/sources.py`
  - defines managed skill source records used by lifecycle config
- `src/jarvis/skills/trust.py`
  - defines `SkillTrustStatus`
- `src/jarvis/skills/quarantine.py`
  - defines `SkillQuarantineStatus`
- `src/jarvis/skills/registry.py`
  - extends discovery with lifecycle-aware source roots
  - filters disabled/quarantined skills from the prompt skill index and `available_names()`
  - blocks disabled/quarantined `skill.load` / `skill.run` through lifecycle-aware getters
- `src/jarvis/agent/tools.py`
  - `skill.load` now returns structured blocked errors for disabled/quarantined skills
- `src/jarvis/skills/executor.py`
  - `skill.run` now returns structured refusal/error results when lifecycle state blocks execution
- `src/jarvis/cli.py` and `jarvis/cli.py`
  - add `/skill install`, `/skill enable`, `/skill disable`, `/skill update`, `/skill check`, `/skill trust`, `/skill quarantine`, `/skill source list`, `/skill source add`, and `/skill source remove`
- `benchmarks/suites/skill_lifecycle/`
  - adds a formal lifecycle benchmark suite covering install, enable/disable, trust/quarantine, source management, registry filtering, and load/run blocking
- `benchmarks/run_benchmark.py`
  - emits `skill_lifecycle_metrics` in `latest.json` and `latest.md`
- `benchmarks/export_answer_checklist.py`
  - exports lifecycle checklist fields for install/enable/disable/trust/quarantine/source/blocking visibility

### latest benchmark snapshot

- `benchmarks/run_benchmark.py --suite skill_lifecycle --model-mode fake`
  - suite cases: `6`
  - pass_rate: `100%`
- `benchmarks/run_benchmark.py --all --model-mode fake`
  - completed and wrote reports including `skill_lifecycle_metrics`
- `benchmarks/export_answer_checklist.py`
  - completed and includes lifecycle fields in markdown/json exports

## Phase 16 Outcomes

### permissions_approval_hooks

- permission_profiles: done
- approval_contract: done
- approval_store: done
- pretool_hooks: done
- posttool_hooks: done
- security_hooks: done
- domain_policy: done
- toolcall_executor_integration: done
- web_fetch_policy_layering: done
- benchmark: done

### details

- `src/jarvis/core/policy/permissions.py`
  - defines `PermissionPolicy`, `ToolProfile`, `PermissionDecision`, `ToolRule`, and `DomainRule`
  - keeps the older `PermissionMode` compatibility interface intact
- `src/jarvis/core/policy/approval.py`
  - defines `ApprovalRequest`, `ApprovalResponse`, and in-memory `ApprovalStore`
  - stores only redacted approval previews
- `src/jarvis/core/policy/hooks.py`
  - defines `HookInput`, `HookResult`, `HookDefinition`, and `HookRegistry`
- `src/jarvis/core/policy/security_hooks.py`
  - provides default high-risk warning hooks
- `src/jarvis/agent/tools.py`
  - integrates permission policy, approval checks, pre/post hooks, and web domain policy into `ToolCallExecutor`
  - preserves skill lifecycle blocking and per-skill `allowed_tools` enforcement ordering
- `src/jarvis/web/fetch.py` / `src/jarvis/web/safety.py`
  - keep SSRF safety and the Phase 13 web boundary intact
  - approval cannot bypass localhost/private IP/metadata service/redirect-to-private blocks
- `src/jarvis/cli.py` / `jarvis/cli.py`
  - add `/permissions`, `/approve`, and `/deny`
- `src/jarvis/api/server.py`
  - adds `GET /api/permissions`
  - extends approval endpoints to resolve redacted approval requests
- `benchmarks/suites/permissions/`
  - adds formal permissions benchmark cases for profiles, approval, hooks, domain policy, layering, and SSRF bypass protection

### latest benchmark snapshot

- `benchmarks/run_benchmark.py --suite permissions --model-mode fake`
  - suite cases: `8`
  - pass_rate: `100%`
- `benchmarks/run_benchmark.py --all --model-mode fake`
  - completed and wrote reports including `permissions_metrics`
- `benchmarks/export_answer_checklist.py`
  - completed and includes permission fields in markdown/json exports

## Remaining Gaps

1. Web agent adapter still does not exist; this remains outside the completed CLI/API/benchmark path.
2. Phase 10B supports both deterministic builtin `SkillCall` selection and model-driven `skill.run`; broader skill selection quality can be expanded in Phase 12+ without adding a second AgentLoop.
3. Phase 11 context store is intentionally in-memory/session-local; durable persistence and richer retrieval remain future work.
4. Phase 17 Persistent Memory / ThreadStore remains planned.
5. Phase 18 Web / Control Surface remains planned.
6. Remote skill marketplace install remains optional and is not part of the current offline-first lifecycle path.
7. Remote source update remains optional; current Phase 15 update support is local-source-first.
8. Real providers remain optional and were not exercised in this phase.
9. Browser fallback / browser automation is still out of scope for the current web tool boundary.
10. Web UI and control-surface work remain out of scope for this phase.
11. Approval resume is intentionally limited to auditable approval plus user retry; no separate turn-resume mechanism was introduced in Phase 16.
12. `ApprovalStore` remains in-memory until a later persistence phase.

## Regression Summary

- `tests/web`: `23 passed`
- `tests/agent`: `47 passed`
- `tests/skills`: `90 passed`
- `tests/policy`: `36 passed`
- `tests/cli`: `204 passed`
- `tests/api`: `22 passed`
- `tests/routing`: `146 passed`
- `tests/benchmark`: `82 passed`
- `benchmarks/run_benchmark.py --suite web_research --model-mode fake`: `13 cases, 100% pass_rate`
- `benchmarks/run_benchmark.py --suite skill_lifecycle --model-mode fake`: `6 cases, 100% pass_rate`
- `benchmarks/run_benchmark.py --suite permissions --model-mode fake`: `8 cases, 100% pass_rate`
- `benchmarks/run_benchmark.py --all --model-mode fake`: completed and wrote reports
- `benchmarks/export_answer_checklist.py`: completed

## Real Smoke

- status: not_run
- reason:
  - Phase 15 default benchmark path must stay offline/deterministic
  - live provider configuration was not required for completion
