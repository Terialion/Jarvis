from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))

from src.jarvis.agent.types import contains_secret_text, redact_secret_text


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sanitize_md_cell(value: Any, limit: int | None = None) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = _collapse_ws(text)
    text = text.replace("|", r"\|")
    if limit is not None and len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def _failed_checks(checks: dict[str, Any]) -> list[str]:
    return [k for k, v in checks.items() if not bool(v)]


def _load_case_map() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    root = Path("benchmarks/suites")
    if not root.exists():
        return out
    for cases in root.glob("*/*.jsonl"):
        for line in cases.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("id"):
                out[str(obj["id"])] = obj
    return out


def _model_calls_count(run_result: dict[str, Any]) -> int:
    return sum(
        1
        for evt in list(run_result.get("events") or [])
        if str((evt or {}).get("type") or "") == "model_call_started"
    )


def _extract_rows(payload: dict[str, Any], case_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for suite in payload.get("suites", []):
        suite_name = str(suite.get("suite") or "")
        suite_model_backend = str(suite.get("model_backend") or payload.get("model_backend") or "unknown")
        suite_model_provider = str(suite.get("model_provider") or payload.get("model_provider") or "unknown")
        suite_model_name = str(suite.get("model_name") or payload.get("model_name") or "unknown")

        for row in suite.get("results", []):
            checks = dict(row.get("checks") or {})
            failed = _failed_checks(checks)
            run_result = dict(row.get("run_result") or {})
            case_id = str(row.get("case_id") or "")
            case_def = case_map.get(case_id, {})
            expected_behavior = dict(case_def.get("expected_behavior") or {})
            event_list = list(run_result.get("events") or [])
            input_text = str(
                case_def.get("input")
                or (event_list[0].get("payload", {}).get("text", "") if event_list else "")
                or ""
            )
            final_answer = redact_secret_text(str(run_result.get("final_answer") or ""))
            stop_reason = str(run_result.get("stop_reason") or "")
            output_type = str(run_result.get("output_type") or "answer")
            machine = dict((run_result.get("summary") or {}).get("machine") or {})
            risks = list(machine.get("risks") or [])
            tools_used = list(machine.get("tools_used") or [])
            skills_used = list(run_result.get("skills_used") or machine.get("skills_used") or [])
            skill_results = list(run_result.get("skill_results") or machine.get("skill_results") or [])
            context_reuse = bool(machine.get("context_reuse"))
            active_task_present = bool(machine.get("active_task"))
            handoff_summary_present = bool(machine.get("handoff_summary"))
            event_types = [str((evt or {}).get("type") or "") for evt in list(run_result.get("events") or [])]
            skill_observation_reused = any(
                event_type in {"skill_observation_reused", "context_observation_reused"} for event_type in event_types
            )
            skill_tool_denied_count = sum(1 for event_type in event_types if event_type == "skill_tool_denied")
            web_search_runs_count = int(machine.get("web_search_runs_count") or 0)
            web_fetch_runs_count = int(machine.get("web_fetch_runs_count") or 0)
            web_fetch_blocked_count = int(machine.get("web_fetch_blocked_count") or 0)
            official_sources_count = int(machine.get("official_sources_count") or 0)
            github_sources_count = int(machine.get("github_sources_count") or 0)
            release_note_sources_count = int(machine.get("release_note_sources_count") or 0)
            evidence_count = int(machine.get("evidence_count") or 0)
            citation_count = int(machine.get("citation_count") or 0)
            stale_sources_count = int(machine.get("stale_sources_count") or 0)
            search_result_dedup_count = int(machine.get("search_result_dedup_count") or 0)
            research_context_reused = bool(machine.get("research_context_reused"))
            prompt_injection_blocked = bool(machine.get("prompt_injection_blocked"))
            web_provider_errors = int(machine.get("web_provider_errors") or 0)
            web_secret_leak_count = 1 if contains_secret_text(final_answer) else 0
            skill_installed = bool(machine.get("skill_installed"))
            skill_install_validation_status = "ok" if skill_installed else ("error" if machine.get("invalid_skill_not_enabled") else "unknown")
            skill_enabled = bool(machine.get("skill_enabled"))
            skill_disabled = bool(machine.get("skill_disabled"))
            skill_trusted = bool(machine.get("trust_not_bypass_validator")) or str(machine.get("trust_status") or "") == "trusted"
            skill_quarantined = bool(machine.get("skill_quarantined"))
            skill_source_added = bool(machine.get("skill_source_added"))
            skill_source_removed = bool(machine.get("skill_source_removed"))
            disabled_hidden_from_prompt = bool(machine.get("disabled_hidden_from_prompt"))
            disabled_load_blocked = bool(machine.get("disabled_load_blocked"))
            disabled_run_blocked = bool(machine.get("disabled_run_blocked"))
            quarantined_load_blocked = bool(machine.get("quarantined_load_blocked"))
            quarantined_run_blocked = bool(machine.get("quarantined_run_blocked"))
            skill_lifecycle_secret_leak_count = 1 if contains_secret_text(json.dumps(machine, ensure_ascii=False)) and str(row.get("suite") or "") == "skill_lifecycle" else 0
            permission_policy_evaluated = bool(machine.get("permission_policy_evaluated"))
            tool_policy_denied = bool(machine.get("tool_policy_denied"))
            approval_required = bool(machine.get("approval_required"))
            approval_created = bool(machine.get("approval_created"))
            approval_approved = bool(machine.get("approval_approved"))
            approval_denied = bool(machine.get("approval_denied"))
            pretool_hook_run = bool(machine.get("pretool_hook_run"))
            pretool_hook_denied = bool(machine.get("pretool_hook_denied"))
            posttool_hook_run = bool(machine.get("posttool_hook_run"))
            posttool_hook_warning = bool(machine.get("posttool_hook_warning"))
            domain_policy_denied = bool(machine.get("domain_policy_denied"))
            domain_approval_required = bool(machine.get("domain_approval_required"))
            unsafe_fetch_approval_bypass = bool(machine.get("unsafe_fetch_approval_bypass"))
            security_warning_emitted = bool(machine.get("security_warning_emitted"))
            permissions_secret_leak_count = 1 if contains_secret_text(json.dumps(machine, ensure_ascii=False)) and str(row.get("suite") or "") == "permissions" else 0
            thread_persisted = bool(machine.get("thread_persisted"))
            turn_persisted = bool(machine.get("turn_persisted"))
            message_persisted = bool(machine.get("message_persisted"))
            tool_call_persisted = bool(machine.get("tool_call_persisted"))
            skill_observation_persisted = bool(machine.get("skill_observation_persisted"))
            research_observation_persisted = bool(machine.get("research_observation_persisted"))
            active_task_persisted = bool(machine.get("active_task_persisted"))
            handoff_summary_persisted = bool(machine.get("handoff_summary_persisted"))
            context_resumed = bool(machine.get("context_resumed"))
            memory_command_success = bool(machine.get("memory_command_success"))
            persistent_memory_background_only = bool(machine.get("persistent_memory_background_only"))
            persistent_secret_leak_count = int(machine.get("persistent_secret_leak_count") or 0)
            approval_audit_persisted = bool(machine.get("approval_audit_persisted"))
            schema_version_ok = bool(machine.get("schema_version_ok"))
            process_restart_resume_ok = bool(machine.get("process_restart_resume_ok"))
            control_surface_api_ok = bool(machine.get("control_surface_api_ok"))
            timeline_built = bool(machine.get("timeline_built"))
            tool_cards_present = bool(machine.get("tool_cards_present"))
            skill_cards_present = bool(machine.get("skill_cards_present"))
            web_cards_present = bool(machine.get("web_cards_present"))
            source_evidence_cards_present = bool(machine.get("source_evidence_cards_present"))
            approval_panel_present = bool(machine.get("approval_panel_present"))
            approval_action_ok = bool(machine.get("approval_action_ok"))
            context_inspector_present = bool(machine.get("context_inspector_present"))
            thread_browser_present = bool(machine.get("thread_browser_present"))
            memory_browser_present = bool(machine.get("memory_browser_present"))
            benchmark_dashboard_present = bool(machine.get("benchmark_dashboard_present"))
            ui_payloads_redacted = bool(machine.get("ui_payloads_redacted"))
            browser_boundary_preserved = bool(machine.get("browser_boundary_preserved"))
            second_agent_loop_violation_count = int(machine.get("second_agent_loop_violation_count") or 0)
            control_surface_secret_leak_count = int(machine.get("control_surface_secret_leak_count") or 0)

            rows.append(
                {
                    "case_id": case_id,
                    "suite": suite_name,
                    "passed": bool(row.get("passed")),
                    "failed_checks": failed,
                    "model_backend": suite_model_backend,
                    "model_provider": suite_model_provider,
                    "model_name": suite_model_name,
                    "model_calls": _model_calls_count(run_result),
                    "tool_calls_count": len(list(run_result.get("tool_calls") or [])),
                    "available_skills_count": len(list(run_result.get("available_skills") or [])),
                    "loaded_skills": list(run_result.get("loaded_skills") or []),
                    "skill_loads_count": int(run_result.get("skill_loads_count") or 0),
                    "skills_used": skills_used,
                    "skill_calls_count": int(run_result.get("skill_calls_count") or machine.get("skill_calls_count") or 0),
                    "skill_results_count": len(skill_results),
                    "context_reuse": context_reuse,
                    "active_task_present": active_task_present,
                    "handoff_summary_present": handoff_summary_present,
                    "skill_observation_reused": skill_observation_reused,
                    "skill_tool_denied_count": skill_tool_denied_count,
                    "web_search_runs_count": web_search_runs_count,
                    "web_fetch_runs_count": web_fetch_runs_count,
                    "web_fetch_blocked_count": web_fetch_blocked_count,
                    "web_sources_count": official_sources_count + github_sources_count + release_note_sources_count,
                    "official_sources_count": official_sources_count,
                    "github_sources_count": github_sources_count,
                    "release_note_sources_count": release_note_sources_count,
                    "evidence_count": evidence_count,
                    "citation_count": citation_count,
                    "stale_sources_count": stale_sources_count,
                    "search_result_dedup_count": search_result_dedup_count,
                    "research_context_reused": research_context_reused,
                    "prompt_injection_blocked": prompt_injection_blocked,
                    "web_provider_errors": web_provider_errors,
                    "web_secret_leak_count": web_secret_leak_count,
                    "skill_installed": skill_installed,
                    "skill_install_validation_status": skill_install_validation_status,
                    "skill_enabled": skill_enabled,
                    "skill_disabled": skill_disabled,
                    "skill_trusted": skill_trusted,
                    "skill_quarantined": skill_quarantined,
                    "skill_source_added": skill_source_added,
                    "skill_source_removed": skill_source_removed,
                    "disabled_hidden_from_prompt": disabled_hidden_from_prompt,
                    "disabled_load_blocked": disabled_load_blocked,
                    "disabled_run_blocked": disabled_run_blocked,
                    "quarantined_load_blocked": quarantined_load_blocked,
                    "quarantined_run_blocked": quarantined_run_blocked,
                    "skill_lifecycle_secret_leak_count": skill_lifecycle_secret_leak_count,
                    "permission_policy_evaluated": permission_policy_evaluated,
                    "tool_policy_denied": tool_policy_denied,
                    "approval_required": approval_required,
                    "approval_created": approval_created,
                    "approval_approved": approval_approved,
                    "approval_denied": approval_denied,
                    "pretool_hook_run": pretool_hook_run,
                    "pretool_hook_denied": pretool_hook_denied,
                    "posttool_hook_run": posttool_hook_run,
                    "posttool_hook_warning": posttool_hook_warning,
                    "domain_policy_denied": domain_policy_denied,
                    "domain_approval_required": domain_approval_required,
                    "unsafe_fetch_approval_bypass": unsafe_fetch_approval_bypass,
                    "security_warning_emitted": security_warning_emitted,
                    "permissions_secret_leak_count": permissions_secret_leak_count,
                    "thread_persisted": thread_persisted,
                    "turn_persisted": turn_persisted,
                    "message_persisted": message_persisted,
                    "tool_call_persisted": tool_call_persisted,
                    "skill_observation_persisted": skill_observation_persisted,
                    "research_observation_persisted": research_observation_persisted,
                    "active_task_persisted": active_task_persisted,
                    "handoff_summary_persisted": handoff_summary_persisted,
                    "context_resumed": context_resumed,
                    "memory_command_success": memory_command_success,
                    "persistent_memory_background_only": persistent_memory_background_only,
                    "persistent_secret_leak_count": persistent_secret_leak_count,
                    "approval_audit_persisted": approval_audit_persisted,
                    "schema_version_ok": schema_version_ok,
                    "process_restart_resume_ok": process_restart_resume_ok,
                    "control_surface_api_ok": control_surface_api_ok,
                    "timeline_built": timeline_built,
                    "tool_cards_present": tool_cards_present,
                    "skill_cards_present": skill_cards_present,
                    "web_cards_present": web_cards_present,
                    "source_evidence_cards_present": source_evidence_cards_present,
                    "approval_panel_present": approval_panel_present,
                    "approval_action_ok": approval_action_ok,
                    "context_inspector_present": context_inspector_present,
                    "thread_browser_present": thread_browser_present,
                    "memory_browser_present": memory_browser_present,
                    "benchmark_dashboard_present": benchmark_dashboard_present,
                    "ui_payloads_redacted": ui_payloads_redacted,
                    "browser_boundary_preserved": browser_boundary_preserved,
                    "second_agent_loop_violation_count": second_agent_loop_violation_count,
                    "control_surface_secret_leak_count": control_surface_secret_leak_count,
                    "output_type": output_type,
                    "stop_reason": stop_reason,
                    "input": input_text,
                    "expected_behavior": expected_behavior,
                    "final_answer_excerpt": final_answer[:200],
                    "risks": risks,
                    "tools_used": tools_used,
                }
            )
    return rows


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _redact_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_payload(v) for v in value]
    if isinstance(value, str):
        return redact_secret_text(value)
    return value


def _render_markdown(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# Benchmark Answer Checklist")
    lines.append("")
    lines.append(f"- generated_at: {payload.get('generated_at')}")
    lines.append(f"- scope: {payload.get('scope')}")
    lines.append(f"- execution_mode: {payload.get('execution_mode')}")
    lines.append(f"- model_provider: {payload.get('model_provider')}")
    lines.append(f"- model_backend: {payload.get('model_backend')}")
    lines.append("")

    by_suite: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_suite.setdefault(str(row["suite"]), []).append(row)

    for suite_name, suite_rows in by_suite.items():
        lines.append(f"## Suite: {suite_name}")
        lines.append("")
        lines.append(
            "| case_id | passed | failed_checks | output_type | model_calls | tool_calls_count | skill_loads_count | loaded_skills | skill_calls_count | skills_used | context_reuse | active_task | handoff | skill_obs_reused | skill_tool_denied_count | web_search_runs | web_fetch_runs | web_fetch_blocked | web_sources | evidence | citations | stale | dedup | research_reused | prompt_injection_blocked | web_provider_errors | web_secret_leak_count | skill_installed | skill_enabled | skill_disabled | skill_trusted | skill_quarantined | source_added | source_removed | disabled_hidden | disabled_load_blocked | disabled_run_blocked | quarantined_load_blocked | quarantined_run_blocked | skill_lifecycle_secret_leak_count | permission_policy_evaluated | tool_policy_denied | approval_required | approval_created | approval_approved | approval_denied | pretool_hook_run | pretool_hook_denied | posttool_hook_run | posttool_hook_warning | domain_policy_denied | domain_approval_required | unsafe_fetch_approval_bypass | security_warning_emitted | permissions_secret_leak_count | thread_persisted | turn_persisted | message_persisted | tool_call_persisted | skill_observation_persisted | research_observation_persisted | active_task_persisted | handoff_summary_persisted | context_resumed | memory_command_success | persistent_memory_background_only | persistent_secret_leak_count | approval_audit_persisted | schema_version_ok | process_restart_resume_ok | control_surface_api_ok | timeline_built | tool_cards_present | skill_cards_present | web_cards_present | source_evidence_cards_present | approval_panel_present | approval_action_ok | context_inspector_present | thread_browser_present | memory_browser_present | benchmark_dashboard_present | ui_payloads_redacted | browser_boundary_preserved | second_agent_loop_violation_count | control_surface_secret_leak_count | stop_reason | final_answer_excerpt | risks |"
        )
        lines.append("|---|---|---|---|---:|---:|---:|---|---:|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---:|---:|---|---|")
        for row in suite_rows:
            excerpt = str(row.get("final_answer_excerpt") or "").replace("\n", " ").replace("\t", " ").strip()
            lines.append(
                f"| `{_sanitize_md_cell(row['case_id'])}` | "
                f"`{_sanitize_md_cell(row['passed'])}` | "
                f"`{_sanitize_md_cell(', '.join(row['failed_checks']) if row['failed_checks'] else 'none')}` | "
                f"`{_sanitize_md_cell(row['output_type'])}` | "
                f"`{_sanitize_md_cell(row['model_calls'])}` | "
                f"`{_sanitize_md_cell(row['tool_calls_count'])}` | "
                f"`{_sanitize_md_cell(row['skill_loads_count'])}` | "
                f"`{_sanitize_md_cell(', '.join(row['loaded_skills']) if row['loaded_skills'] else 'none', 80)}` | "
                f"`{_sanitize_md_cell(row['skill_calls_count'])}` | "
                f"`{_sanitize_md_cell(', '.join(row['skills_used']) if row['skills_used'] else 'none', 80)}` | "
                f"`{_sanitize_md_cell(row['context_reuse'])}` | "
                f"`{_sanitize_md_cell(row['active_task_present'])}` | "
                f"`{_sanitize_md_cell(row['handoff_summary_present'])}` | "
                f"`{_sanitize_md_cell(row['skill_observation_reused'])}` | "
                f"`{_sanitize_md_cell(row['skill_tool_denied_count'])}` | "
                f"`{_sanitize_md_cell(row['web_search_runs_count'])}` | "
                f"`{_sanitize_md_cell(row['web_fetch_runs_count'])}` | "
                f"`{_sanitize_md_cell(row['web_fetch_blocked_count'])}` | "
                f"`{_sanitize_md_cell(row['web_sources_count'])}` | "
                f"`{_sanitize_md_cell(row['evidence_count'])}` | "
                f"`{_sanitize_md_cell(row['citation_count'])}` | "
                f"`{_sanitize_md_cell(row['stale_sources_count'])}` | "
                f"`{_sanitize_md_cell(row['search_result_dedup_count'])}` | "
                f"`{_sanitize_md_cell(row['research_context_reused'])}` | "
                f"`{_sanitize_md_cell(row['prompt_injection_blocked'])}` | "
                f"`{_sanitize_md_cell(row['web_provider_errors'])}` | "
                f"`{_sanitize_md_cell(row['web_secret_leak_count'])}` | "
                f"`{_sanitize_md_cell(row['skill_installed'])}` | "
                f"`{_sanitize_md_cell(row['skill_enabled'])}` | "
                f"`{_sanitize_md_cell(row['skill_disabled'])}` | "
                f"`{_sanitize_md_cell(row['skill_trusted'])}` | "
                f"`{_sanitize_md_cell(row['skill_quarantined'])}` | "
                f"`{_sanitize_md_cell(row['skill_source_added'])}` | "
                f"`{_sanitize_md_cell(row['skill_source_removed'])}` | "
                f"`{_sanitize_md_cell(row['disabled_hidden_from_prompt'])}` | "
                f"`{_sanitize_md_cell(row['disabled_load_blocked'])}` | "
                f"`{_sanitize_md_cell(row['disabled_run_blocked'])}` | "
                f"`{_sanitize_md_cell(row['quarantined_load_blocked'])}` | "
                f"`{_sanitize_md_cell(row['quarantined_run_blocked'])}` | "
                f"`{_sanitize_md_cell(row['skill_lifecycle_secret_leak_count'])}` | "
                f"`{_sanitize_md_cell(row['permission_policy_evaluated'])}` | "
                f"`{_sanitize_md_cell(row['tool_policy_denied'])}` | "
                f"`{_sanitize_md_cell(row['approval_required'])}` | "
                f"`{_sanitize_md_cell(row['approval_created'])}` | "
                f"`{_sanitize_md_cell(row['approval_approved'])}` | "
                f"`{_sanitize_md_cell(row['approval_denied'])}` | "
                f"`{_sanitize_md_cell(row['pretool_hook_run'])}` | "
                f"`{_sanitize_md_cell(row['pretool_hook_denied'])}` | "
                f"`{_sanitize_md_cell(row['posttool_hook_run'])}` | "
                f"`{_sanitize_md_cell(row['posttool_hook_warning'])}` | "
                f"`{_sanitize_md_cell(row['domain_policy_denied'])}` | "
                f"`{_sanitize_md_cell(row['domain_approval_required'])}` | "
                f"`{_sanitize_md_cell(row['unsafe_fetch_approval_bypass'])}` | "
                f"`{_sanitize_md_cell(row['security_warning_emitted'])}` | "
                f"`{_sanitize_md_cell(row['permissions_secret_leak_count'])}` | "
                f"`{_sanitize_md_cell(row['thread_persisted'])}` | "
                f"`{_sanitize_md_cell(row['turn_persisted'])}` | "
                f"`{_sanitize_md_cell(row['message_persisted'])}` | "
                f"`{_sanitize_md_cell(row['tool_call_persisted'])}` | "
                f"`{_sanitize_md_cell(row['skill_observation_persisted'])}` | "
                f"`{_sanitize_md_cell(row['research_observation_persisted'])}` | "
                f"`{_sanitize_md_cell(row['active_task_persisted'])}` | "
                f"`{_sanitize_md_cell(row['handoff_summary_persisted'])}` | "
                f"`{_sanitize_md_cell(row['context_resumed'])}` | "
                f"`{_sanitize_md_cell(row['memory_command_success'])}` | "
                f"`{_sanitize_md_cell(row['persistent_memory_background_only'])}` | "
                f"`{_sanitize_md_cell(row['persistent_secret_leak_count'])}` | "
                f"`{_sanitize_md_cell(row['approval_audit_persisted'])}` | "
                f"`{_sanitize_md_cell(row['schema_version_ok'])}` | "
                f"`{_sanitize_md_cell(row['process_restart_resume_ok'])}` | "
                f"`{_sanitize_md_cell(row['control_surface_api_ok'])}` | "
                f"`{_sanitize_md_cell(row['timeline_built'])}` | "
                f"`{_sanitize_md_cell(row['tool_cards_present'])}` | "
                f"`{_sanitize_md_cell(row['skill_cards_present'])}` | "
                f"`{_sanitize_md_cell(row['web_cards_present'])}` | "
                f"`{_sanitize_md_cell(row['source_evidence_cards_present'])}` | "
                f"`{_sanitize_md_cell(row['approval_panel_present'])}` | "
                f"`{_sanitize_md_cell(row['approval_action_ok'])}` | "
                f"`{_sanitize_md_cell(row['context_inspector_present'])}` | "
                f"`{_sanitize_md_cell(row['thread_browser_present'])}` | "
                f"`{_sanitize_md_cell(row['memory_browser_present'])}` | "
                f"`{_sanitize_md_cell(row['benchmark_dashboard_present'])}` | "
                f"`{_sanitize_md_cell(row['ui_payloads_redacted'])}` | "
                f"`{_sanitize_md_cell(row['browser_boundary_preserved'])}` | "
                f"`{_sanitize_md_cell(row['second_agent_loop_violation_count'])}` | "
                f"`{_sanitize_md_cell(row['control_surface_secret_leak_count'])}` | "
                f"`{_sanitize_md_cell(row['stop_reason'], 80)}` | "
                f"{_sanitize_md_cell(excerpt, 120)} | "
                f"{_sanitize_md_cell(', '.join(row['risks']) if row['risks'] else 'none', 120)} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    latest = Path("benchmarks/reports/latest.json")
    if not latest.exists():
        print("missing benchmarks/reports/latest.json")
        return 1

    payload = _redact_payload(json.loads(latest.read_text(encoding="utf-8")))
    case_map = _load_case_map()
    rows = _extract_rows(payload, case_map)

    out_md = Path("temp/benchmark_answer_checklist.md")
    out_json = Path("temp/benchmark_answer_checklist.json")
    out_md.parent.mkdir(parents=True, exist_ok=True)

    out_md.write_text(_render_markdown(payload, rows), encoding="utf-8")
    out_json.write_text(json.dumps({"meta": payload, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_md))
    print(str(out_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
