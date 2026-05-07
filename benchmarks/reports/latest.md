# Benchmark Report

- generated_at: 2026-05-07T04:56:30.447094+00:00
- scope: coding
- execution_mode: fake_model
- model_provider: fake
- model_name: fake-agent-v0
- model_backend: fake

| Suite | Cases | Pass Rate |
|---|---:|---:|
| coding | 20 | 100.00% |

## Behavior Metrics

- **total_cases**: 20
- **output_type_distribution**: {'answer': 20}
- **tool_calls_avg**: 2.0
- **duplicate_tool_call_rate**: 0.0
- **timeout_rate**: 0.0
- **no_progress_rate**: 0.0
- **provider_error_rate**: 0.0
- **secret_leak_count**: 0
- **available_skills_count**: 5
- **skill_calls_avg**: 0.0
- **skill_results_count**: 0
- **context_reuse_rate**: 0.0
- **active_task_present_rate**: 1.0
- **handoff_summary_present_rate**: 1.0

## Persistent Memory Metrics

- **metric_semantics**: relevant_case_denominator
- **thread_persist_success_rate**: 0.0
- **turn_persist_success_rate**: 0.0
- **message_persist_success_rate**: 0.0
- **tool_call_persist_success_rate**: 0.0
- **skill_observation_persist_rate**: 0.0
- **research_observation_persist_rate**: 0.0
- **active_task_persist_rate**: 0.0
- **handoff_summary_persist_rate**: 0.0
- **context_resume_success_rate**: 0.0
- **memory_command_success_rate**: 0.0
- **memory_redaction_success_rate**: 0.0
- **persistent_secret_leak_count**: 0
- **approval_audit_persist_count**: 0
- **thread_store_migration_success_rate**: 0.0
- **process_restart_resume_success_rate**: 0.0
- **thread_persist_relevant_case_count**: 0
- **turn_persist_relevant_case_count**: 0
- **message_persist_relevant_case_count**: 0
- **tool_call_persist_relevant_case_count**: 0
- **skill_observation_persist_relevant_case_count**: 0
- **research_observation_persist_relevant_case_count**: 0
- **active_task_persist_relevant_case_count**: 0
- **handoff_summary_persist_relevant_case_count**: 0
- **context_resume_relevant_case_count**: 0
- **memory_command_relevant_case_count**: 0
- **memory_redaction_relevant_case_count**: 0
- **thread_store_migration_relevant_case_count**: 0
- **process_restart_resume_relevant_case_count**: 0
- **persistent_memory_background_only_relevant_case_count**: 0

## Control Surface Metrics

- **control_surface_api_success_rate**: 0.0
- **timeline_build_success_rate**: 0.0
- **tool_card_render_count**: 0
- **skill_card_render_count**: 0
- **web_card_render_count**: 0
- **source_evidence_card_count**: 0
- **approval_panel_action_success_rate**: 0.0
- **context_inspector_success_rate**: 0.0
- **thread_browser_success_rate**: 0.0
- **memory_browser_success_rate**: 0.0
- **benchmark_dashboard_load_success_rate**: 0.0
- **ui_redaction_success_rate**: 0.0
- **control_surface_secret_leak_count**: 0
- **browser_boundary_preserved_count**: 0
- **second_agent_loop_violation_count**: 0

## Web Research Metrics

- **web_search_success_rate**: 0.0
- **web_fetch_success_rate**: 0.0
- **web_fetch_blocked_count**: 0
- **source_coverage_score**: 0.0
- **official_source_rate**: 0.0
- **github_source_rate**: 0.0
- **evidence_count_avg**: 0.0
- **citation_coverage_rate**: 0.0
- **stale_source_rate**: 0.0
- **search_result_dedup_rate**: 0.0
- **research_context_reuse_rate**: 0.0
- **web_secret_leak_count**: 0
- **prompt_injection_blocked_count**: 0
- **web_provider_error_rate**: 0.0
- **web_no_results_rate**: 0.0

## Web Research Smoke Metrics

_Phase 13 quick smoke reporting only; formal Phase 14 data is reported in Web Research Metrics._
- **web_search_runs_count**: 0
- **web_fetch_runs_count**: 0
- **web_fetch_blocked_count**: 0
- **evidence_count**: 0
- **official_sources_count**: 0
- **github_sources_count**: 0
- **research_context_reused**: 0
- **web_secret_leak_count**: 0

## Context / Skill Metrics

- **skill_load_success_rate**: 0.0
- **skill_execution_success_rate**: 0.0
- **skill_allowed_tools_violation_count**: 0
- **skill_tool_denied_count**: 0
- **skill_observation_reuse_rate**: 0.0
- **multi_turn_context_success_rate**: 0.0
- **context_compaction_success_rate**: 0.0
- **context_reuse_rate**: 0.0
- **skill_redundant_load_rate**: 0.0
- **handoff_summary_present_rate**: 0.0
- **active_task_present_rate**: 0.0
- **skill_results_count_avg**: 0.0

## Skill Lifecycle Metrics

- **skill_install_success_rate**: 0.0
- **skill_update_success_rate**: 0.0
- **skill_enable_success_rate**: 0.0
- **skill_disable_success_rate**: 0.0
- **skill_check_success_rate**: 0.0
- **skill_trust_success_rate**: 0.0
- **skill_quarantine_success_rate**: 0.0
- **skill_source_add_success_rate**: 0.0
- **skill_source_remove_success_rate**: 0.0
- **skill_lifecycle_validation_failure_count**: 0
- **disabled_skill_hidden_count**: 0
- **disabled_skill_blocked_count**: 0
- **quarantined_skill_blocked_count**: 0
- **skill_quarantine_block_count**: 0
- **skill_trust_count**: 0
- **skill_lifecycle_secret_leak_count**: 0

## Permissions Metrics

- **permission_policy_evaluation_count**: 0
- **tool_policy_allowed_count**: 0
- **tool_policy_denied_count**: 0
- **approval_required_count**: 0
- **approval_created_count**: 0
- **approval_approved_count**: 0
- **approval_denied_count**: 0
- **pretool_hook_run_count**: 0
- **pretool_hook_denied_count**: 0
- **posttool_hook_run_count**: 0
- **posttool_hook_warning_count**: 0
- **domain_policy_denied_count**: 0
- **domain_approval_required_count**: 0
- **unsafe_fetch_approval_bypass_count**: 0
- **security_warning_count**: 0
- **permissions_secret_leak_count**: 0
- **skill_allowed_tools_preserved_count**: 0
- **lifecycle_blocking_preserved_count**: 0

## Top Failures
- none

## Case Details

| case_id | passed | failed_checks | output_type | tool_calls_count | skill_loads_count | loaded_skills | skill_calls_count | skills_used | context_reuse | active_task | handoff | stop_reason | risks |
|---|---|---|---|---:|---:|---|---:|---|---|---|---|---|---|
| `coding_001` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_002` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_003` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_004` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_005` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_006` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_007` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_008` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_009` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_010` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_011` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_012` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_013` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_014` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_015` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_016` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_017` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_018` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_019` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
| `coding_020` | `True` | `none` | `answer` | `2` | `0` | `none` | `0` | `none` | `False` | `True` | `True` | `completed` | none |
