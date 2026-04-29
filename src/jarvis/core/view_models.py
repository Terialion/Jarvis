"""UI-friendly view models for Jarvis Core Phase 1 outputs."""

from __future__ import annotations

from typing import Any

REVIEW_PANE_UI_CONTRACT_VERSION = "1.0.0"
REVIEW_PANE_UI_PRIORITY_FIELDS = [
    "task_summary.task_id",
    "task_summary.status",
    "task_summary.title",
    "finalize_summary",
    "test_result_summary.latest.passed",
    "test_result_summary.latest.failure_summary",
    "fallback_explanation.fallback_on_assertion",
    "fallback_explanation.fallback_on_env_error",
    "checkpoint_compare_summary.top_changed_steps",
    "gate_status.passed",
    "rules_warnings",
]


def build_task_summary_view(task: dict) -> dict:
    return {
        "task_id": task.get("task_id"),
        "title": task.get("title"),
        "status": task.get("status"),
        "summary": task.get("summary"),
        "counts": {
            "steps": len(task.get("steps", [])),
            "changed_files": len(task.get("changed_files", [])),
            "command_runs": len(task.get("command_runs", [])),
            "test_runs": len(task.get("test_runs", [])),
            "checkpoints": len(task.get("checkpoints", [])),
            "react_runs": len(task.get("react_runs", [])),
        },
        "timestamps": {
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at"),
        },
    }


def build_task_timeline_view(task: dict, limit: int = 50) -> dict:
    steps = list(task.get("steps", []))
    selected = steps[-max(1, limit) :]
    items = []
    for step in selected:
        items.append(
            {
                "timeline_index": step.get("timeline_index"),
                "step_id": step.get("step_id"),
                "step_type": step.get("step_type"),
                "status": step.get("status"),
                "started_at": step.get("started_at"),
                "finished_at": step.get("finished_at"),
                "input_payload": step.get("input_payload", {}),
            }
        )
    return {"task_id": task.get("task_id"), "items": items, "total_steps": len(steps)}


def build_latest_test_result_view(task: dict) -> dict:
    test_runs = list(task.get("test_runs", []))
    latest = test_runs[-1] if test_runs else {}
    return {
        "task_id": task.get("task_id"),
        "has_test_run": bool(test_runs),
        "latest": {
            "passed": latest.get("passed"),
            "selected_command": latest.get("selected_command") or latest.get("command"),
            "attempted_count": latest.get("attempted_count"),
            "failure_summary": latest.get("failure_summary"),
            "fallback_used": latest.get("fallback_used"),
            "fallback_policy": latest.get("fallback_policy"),
        },
    }


def build_checkpoint_review_view(checkpoint_compare: dict) -> dict:
    return {
        "task_id": checkpoint_compare.get("task_id"),
        "checkpoint_id": checkpoint_compare.get("checkpoint_id"),
        "checkpoint_label": checkpoint_compare.get("checkpoint_label"),
        "sort_mode_used": checkpoint_compare.get("sort_mode_used"),
        "top_n_used": checkpoint_compare.get("top_n_used"),
        "checkpoint_key_steps": checkpoint_compare.get("checkpoint_key_steps", []),
        "current_key_steps": checkpoint_compare.get("current_key_steps", []),
        "top_changed_steps": checkpoint_compare.get("top_changed_steps", []),
        "delta": checkpoint_compare.get("delta", {}),
    }


def build_review_pane_view(
    *,
    task: dict,
    rules_warnings: list[dict],
    fallback_policy: dict,
    checkpoint_compare_summary: dict,
    test_result_summary: dict,
    finalize_summary: str | None = None,
    gate_status: dict | None = None,
) -> dict:
    task_summary = build_task_summary_view(task)
    normalized_warnings = list(rules_warnings or [])
    normalized_fallback = _normalized_fallback_policy(fallback_policy or {})
    normalized_checkpoint = checkpoint_compare_summary or {
        "task_id": task_summary.get("task_id"),
        "checkpoint_id": None,
        "checkpoint_label": None,
        "top_changed_steps": [],
        "delta": {},
    }
    normalized_test = test_result_summary or {
        "task_id": task_summary.get("task_id"),
        "has_test_run": False,
        "latest": {},
    }
    normalized_gate = gate_status or build_release_gate_summary_view(None)
    normalized_finalize = finalize_summary if finalize_summary is not None else task.get("summary")
    configured_priority = task.get("ui_priority_fields")
    if isinstance(configured_priority, list) and all(isinstance(item, str) for item in configured_priority):
        priority_fields = list(configured_priority)
        priority_source = "task_config"
    else:
        priority_fields = list(REVIEW_PANE_UI_PRIORITY_FIELDS)
        priority_source = "default"
    priority_items, unknown_priority_fields = _build_priority_items(
        priority_fields=priority_fields,
        payload_context={
            "task_summary": task_summary,
            "rules_warnings": normalized_warnings,
            "fallback_explanation": normalized_fallback,
            "checkpoint_compare_summary": normalized_checkpoint,
            "test_result_summary": normalized_test,
            "finalize_summary": normalized_finalize,
            "gate_status": normalized_gate,
        },
    )
    return {
        "task_summary": task_summary,
        "rules_warnings": normalized_warnings,
        "fallback_explanation": normalized_fallback,
        "checkpoint_compare_summary": normalized_checkpoint,
        "test_result_summary": normalized_test,
        "finalize_summary": normalized_finalize,
        "gate_status": normalized_gate,
        "ui_contract_version": REVIEW_PANE_UI_CONTRACT_VERSION,
        "ui_priority_fields": priority_fields,
        "ui_priority_source": priority_source,
        "ui_priority_values": priority_items,
        "ui_unknown_priority_fields": unknown_priority_fields,
        "groups": {
            "rules": {"warnings": normalized_warnings, "warning_count": len(normalized_warnings)},
            "fallback": {"policy": normalized_fallback},
            "checkpoint": {"compare": normalized_checkpoint},
            "tests": {"latest": normalized_test},
            "finalize": {"summary": normalized_finalize, "status": task_summary.get("status")},
            "gate": {"status": normalized_gate},
        },
}


def view_model_bundle(task: dict, checkpoint_compare: dict | None = None) -> dict[str, Any]:
    """Convenience bundle for CLI/App/UI consumers."""
    return {
        "task_summary": build_task_summary_view(task),
        "task_timeline": build_task_timeline_view(task),
        "latest_test_result": build_latest_test_result_view(task),
        "checkpoint_review": build_checkpoint_review_view(checkpoint_compare or {}),
    }


def build_release_gate_summary_view(release_gate_summary: dict | None) -> dict:
    summary = release_gate_summary or {}
    acceptance = summary.get("acceptance", {}) if isinstance(summary.get("acceptance", {}), dict) else {}
    regression = summary.get("regression", {}) if isinstance(summary.get("regression", {}), dict) else {}
    return {
        "available": bool(summary),
        "gate_name": summary.get("gate_name", "phase1_release_gate"),
        "passed": summary.get("passed"),
        "headline": summary.get("headline"),
        "first_failure": summary.get("first_failure"),
        "acceptance": {
            "passed": acceptance.get("passed"),
            "summary_line": acceptance.get("summary_line"),
            "first_failure": acceptance.get("first_failure"),
            "duration_ms": acceptance.get("duration_ms"),
        },
        "regression": {
            "passed": regression.get("passed"),
            "summary_line": regression.get("summary_line"),
            "first_failure": regression.get("first_failure"),
            "duration_ms": regression.get("duration_ms"),
        },
        "run_at": summary.get("run_at"),
        "duration_ms": summary.get("duration_ms"),
    }


def build_run_list_view(runs: list[dict], limit: int = 20) -> dict:
    selected = list(runs or [])[-max(1, limit) :]
    items = [build_run_summary_item(run) for run in reversed(selected)]
    return {"items": items, "count": len(items), "total_runs": len(runs or [])}


def build_run_summary_item(run: dict) -> dict:
    traces = list(run.get("traces", []))
    status = str(run.get("state") or "unknown")
    stop_reason = _extract_stop_reason(run)
    return {
        "run_id": run.get("run_id"),
        "task_id": run.get("task_id"),
        "runtime_status": status,
        "start_time": _run_start_time(run),
        "end_time": _run_end_time(run),
        "duration_ms": run.get("duration_ms"),
        "total_steps": len(traces),
        "success": status == "completed" and stop_reason == "success",
        "failure": status in {"failed"} or stop_reason in {"repeated_failure_stop", "timeout_stop"},
        "stopped": status in {"stopped", "waiting_for_approval"},
        "stop_reason": stop_reason,
        "retry_count": int(run.get("retries") or 0),
        "active_skills_count": _active_skills_count(run),
        "tool_calls_count": len(traces),
        "route_summary": _route_summary(run),
    }


def build_run_detail_view(run: dict) -> dict:
    traces = list(run.get("traces", []))
    step_trace = build_run_step_trace_view(run)
    stop_summary = build_run_stop_summary_view(run)
    skill_hits = build_run_skill_hits_view(run)
    tool_calls = build_run_tool_calls_view(run)
    return {
        "run": build_run_summary_item(run),
        "current_state": run.get("state"),
        "route_summary": _route_summary(run),
        "route_quality_summary": dict(run.get("route_quality_summary") or {}),
        "recovery_effectiveness_summary": dict(run.get("recovery_effectiveness_summary") or {}),
        "approval_policy_summary": dict(run.get("approval_policy_summary") or {}),
        "attached_default_skills": list((run.get("route_result") or {}).get("attached_default_skills") or []),
        "planner_hints": dict((run.get("route_result") or {}).get("planner_hints") or {}),
        "approval_risk_hints": dict((run.get("route_result") or {}).get("approval_risk_hints") or {}),
        "step_trace_summary": {
            "total_steps": len(traces),
            "last_step_number": traces[-1].get("step_number") if traces else None,
            "last_outcome": _trace_outcome(traces[-1]) if traces else None,
        },
        "final_summary": {
            "stop_reason": stop_summary.get("stop_reason"),
            "fallback_type": stop_summary.get("fallback_type"),
            "retry_count": stop_summary.get("retry_count"),
            "total_steps": len(traces),
        },
        "fallback_summary": run.get("fallback") or {"mode": "none", "detail": None},
        "approval_summary": {
            "approval_required": stop_summary.get("approval_required", False),
            "approval_state": stop_summary.get("approval_state", "not_required"),
        },
        "replay_stats": {
            "trace_events": len(traces),
            "skill_events": int(run.get("skill_eval", {}).get("total_steps") or 0),
        },
        "step_trace": step_trace,
        "skill_hits": skill_hits,
        "tool_calls": tool_calls,
        "stop": stop_summary,
    }


def build_run_step_trace_view(run: dict, limit: int = 200) -> dict:
    traces = list(run.get("traces", []))
    selected = traces[: max(1, limit)]
    items = []
    for trace in selected:
        action = trace.get("action_result", {}) or {}
        check = trace.get("check_result", {}) or {}
        items.append(
            {
                "step_number": trace.get("step_number"),
                "observation_summary": _observation_summary(trace),
                "chosen_skill": trace.get("chosen_skill"),
                "chosen_tool": trace.get("chosen_tool"),
                "action_summary": _action_summary(trace),
                "action_ok": bool(action.get("ok")),
                "check_result": check,
                "step_outcome": _trace_outcome(trace),
                "retry": bool(check.get("retry_same_plan")),
                "replan": bool(check.get("retry_with_replan")),
                "fallback": bool(check.get("stop_reason") == "fallback_to_summary"),
                "route_summary": trace.get("route_summary") or _route_summary(run),
                "strategy": trace.get("strategy") or check.get("strategy") or {},
            }
        )
    return {"run_id": run.get("run_id"), "task_id": run.get("task_id"), "items": items, "count": len(items)}


def build_run_stop_summary_view(run: dict) -> dict:
    stop_reason = _extract_stop_reason(run)
    fallback = run.get("fallback") or {}
    approval_required = stop_reason == "approval_required_stop" or run.get("state") == "waiting_for_approval"
    return {
        "run_id": run.get("run_id"),
        "task_id": run.get("task_id"),
        "runtime_status": run.get("state"),
        "stop_reason": stop_reason,
        "retry_count": int(run.get("retries") or 0),
        "fallback_type": fallback.get("mode") or "none",
        "fallback_detail": fallback.get("detail"),
        "approval_required": approval_required,
        "approval_state": "pending" if approval_required else "not_required",
        "approval_risk_hints": dict((run.get("route_result") or {}).get("approval_risk_hints") or {}),
    }


def build_run_skill_hits_view(run: dict) -> dict:
    traces = list(run.get("traces", []))
    items = []
    active_skills: set[str] = set()
    chosen_skills: set[str] = set()
    route = run.get("route_result") or {}
    seeded = set(route.get("attached_default_skills") or [])
    for trace in traces:
        chosen = trace.get("chosen_skill")
        if isinstance(chosen, str) and chosen:
            active_skills.add(chosen)
            chosen_skills.add(chosen)
        items.append(
            {
                "step_number": trace.get("step_number"),
                "active_skills": [chosen] if chosen else [],
                "matched_skills": [chosen] if chosen else [],
                "chosen_skill": chosen,
                "rejected_skills": [],
                "skill_usefulness": _skill_usefulness(trace),
                "seeded_by_policy": bool(chosen and chosen in seeded),
                "seed_sources": ["policy_seed"] if chosen and chosen in seeded else [],
            }
        )
    return {
        "run_id": run.get("run_id"),
        "task_id": run.get("task_id"),
        "items": items,
        "active_skills": sorted(active_skills),
        "matched_skills": sorted(active_skills),
        "chosen_skills": sorted(chosen_skills),
        "seeded_skill_ids": sorted([skill_id for skill_id in chosen_skills if skill_id in seeded]),
        "evaluation": run.get("skill_eval") or {},
    }


def build_run_tool_calls_view(run: dict) -> dict:
    traces = list(run.get("traces", []))
    items = []
    for trace in traces:
        action = trace.get("action_result", {}) or {}
        items.append(
            {
                "step_number": trace.get("step_number"),
                "tool_name": trace.get("chosen_tool"),
                "action_input_summary": _trim_dict(trace.get("action_input") or {}, max_items=5),
                "action_result_summary": _action_result_summary(action),
                "success": bool(action.get("ok")),
                "duration_ms": (action.get("meta") or {}).get("duration_ms"),
            }
        )
    return {"run_id": run.get("run_id"), "task_id": run.get("task_id"), "items": items, "count": len(items)}


def build_gateway_summary_view(runtime_status: dict | None) -> dict:
    status = runtime_status or {}
    return {
        "status": status.get("status", "unknown"),
        "gateway_id": status.get("gateway_id"),
        "gateway_version": status.get("gateway_version"),
        "uptime_ms": status.get("uptime_ms"),
        "is_bound": status.get("is_bound"),
        "is_fully_bound": status.get("is_fully_bound"),
        "task_count": status.get("task_count", 0),
        "session_count": status.get("session_count", 0),
    }


def build_channels_summary_view(channels_summary: dict | None) -> dict:
    summary = channels_summary or {}
    return {
        "available": bool(summary),
        "total": summary.get("total", 0),
        "active": summary.get("active", 0),
        "degraded": summary.get("degraded", 0),
        "offline": summary.get("offline", 0),
        "healthy_ratio": summary.get("healthy_ratio"),
    }


def build_nodes_summary_view(nodes_summary: dict | None) -> dict:
    summary = nodes_summary or {}
    return {
        "available": bool(summary),
        "total": summary.get("total", 0),
        "active": summary.get("active", 0),
        "degraded": summary.get("degraded", 0),
        "offline": summary.get("offline", 0),
        "healthy_ratio": summary.get("healthy_ratio"),
    }


def build_review_summary_view(review_summary: dict | None) -> dict:
    summary = review_summary or {}
    return {
        "total_tasks": summary.get("total_tasks", 0),
        "finalized_tasks": summary.get("finalized_tasks", 0),
        "open_tasks": summary.get("open_tasks", 0),
        "warning_tasks": summary.get("warning_tasks", 0),
        "needs_approval_tasks": summary.get("needs_approval_tasks", 0),
    }


def build_gate_summary_view(gate_summary: dict | None) -> dict:
    return build_release_gate_summary_view(gate_summary)


def build_operator_dashboard_view(
    *,
    gateway_summary: dict,
    active_runs_summary: dict,
    recent_runs: dict,
    channels_summary: dict,
    nodes_summary: dict,
    gate_summary: dict,
    review_summary: dict,
    runtime_observability_summary: dict,
) -> dict:
    return {
        "gateway_summary": gateway_summary,
        "active_runs_summary": active_runs_summary,
        "recent_runs": recent_runs,
        "channels_summary": channels_summary,
        "nodes_summary": nodes_summary,
        "gate_summary": gate_summary,
        "review_summary": review_summary,
        "runtime_observability_summary": runtime_observability_summary,
    }


def _normalized_fallback_policy(policy: dict) -> dict:
    defaults = {
        "fallback_on_assertion": False,
        "fallback_on_env_error": True,
        "fallback_attempt_limit": None,
        "warnings": [],
    }
    merged = {**defaults, **(policy or {})}
    if not isinstance(merged.get("warnings"), list):
        merged["warnings"] = []
    return merged


def _build_priority_items(priority_fields: list[str], payload_context: dict) -> tuple[list[dict], list[str]]:
    known_roots = {
        "task_summary",
        "rules_warnings",
        "fallback_explanation",
        "checkpoint_compare_summary",
        "test_result_summary",
        "finalize_summary",
        "gate_status",
    }
    items: list[dict] = []
    unknown: list[str] = []
    for path in priority_fields:
        if not isinstance(path, str) or not path.strip():
            continue
        root = path.split(".", 1)[0]
        if root not in known_roots:
            unknown.append(path)
            continue
        value, exists = _extract_path(payload_context, path)
        items.append({"path": path, "value": value, "exists": exists})
    return items, unknown


def _extract_path(payload: dict, path: str) -> tuple[object | None, bool]:
    current: object = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return None, False
    return current, True


def _run_start_time(run: dict) -> str | None:
    traces = run.get("traces") or []
    if traces:
        observation = traces[0].get("observation", {}) if isinstance(traces[0], dict) else {}
        payload = observation.get("payload", {}) if isinstance(observation, dict) else {}
        return payload.get("timestamp")
    return None


def _run_end_time(run: dict) -> str | None:
    traces = run.get("traces") or []
    if traces:
        observation = traces[-1].get("observation", {}) if isinstance(traces[-1], dict) else {}
        payload = observation.get("payload", {}) if isinstance(observation, dict) else {}
        return payload.get("timestamp")
    return None


def _active_skills_count(run: dict) -> int:
    traces = run.get("traces") or []
    return len({trace.get("chosen_skill") for trace in traces if trace.get("chosen_skill")})


def _extract_stop_reason(run: dict) -> str | None:
    stop_record = run.get("stop_record")
    if isinstance(stop_record, dict):
        return stop_record.get("reason")
    return None


def _observation_summary(trace: dict) -> dict:
    observation = trace.get("observation", {}) or {}
    payload = observation.get("payload", {}) if isinstance(observation, dict) else {}
    return {
        "step_number": payload.get("step_number"),
        "pending_plan_steps": payload.get("pending_plan_steps"),
        "task_status": payload.get("task_status"),
    }


def _action_summary(trace: dict) -> str:
    tool = trace.get("chosen_tool") or "unknown_tool"
    action_input = trace.get("action_input", {}) or {}
    keys = sorted([k for k in action_input.keys() if k not in {"step_number"}])[:3]
    return f"{tool} ({', '.join(keys)})" if keys else str(tool)


def _trace_outcome(trace: dict) -> str:
    check = trace.get("check_result", {}) or {}
    if isinstance(check, dict) and check.get("outcome"):
        return str(check["outcome"])
    action = trace.get("action_result", {}) or {}
    return "success" if action.get("ok") else "failure"


def _action_result_summary(action_result: dict) -> dict:
    if not isinstance(action_result, dict):
        return {"ok": False, "error_code": "COMMON_INTERNAL_ERROR"}
    if action_result.get("ok"):
        data = action_result.get("data")
        if isinstance(data, dict):
            return {"ok": True, "keys": sorted(list(data.keys()))[:6]}
        return {"ok": True, "keys": []}
    error = action_result.get("error") or {}
    return {"ok": False, "error_code": error.get("code"), "error_message": error.get("message")}


def _trim_dict(payload: dict, max_items: int = 5) -> dict:
    if not isinstance(payload, dict):
        return {}
    items = list(payload.items())[:max_items]
    return {str(k): v for k, v in items}


def _skill_usefulness(trace: dict) -> str:
    check = trace.get("check_result", {}) or {}
    if check.get("passed"):
        return "high"
    if check.get("retry_same_plan") or check.get("retry_with_replan"):
        return "medium"
    return "low"


def _route_summary(run: dict) -> dict:
    route = run.get("route_result") or {}
    return {
        "domain": route.get("domain"),
        "intent": route.get("intent"),
        "confidence": route.get("confidence"),
        "fallback_used": bool(route.get("fallback_used")),
    }
