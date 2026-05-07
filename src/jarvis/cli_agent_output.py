"""CLI renderer for AgentRunResult.

Renderer-only module: consumes AgentRunResult-like objects and returns text/JSON.
No routing or execution decisions should be made here.
"""

from __future__ import annotations

import json
from typing import Any


def safe_text(mask_fn: Any, value: Any) -> str:
    return str(mask_fn(str(value or "")))


def compact_tool_args(mask_fn: Any, value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return ""
    parts: list[str] = []
    for key, val in list(value.items())[:3]:
        parts.append(f"{key}={safe_text(mask_fn, str(val))[:60]}")
    return ", ".join(parts)


def provider_error_info(events: list[dict[str, Any]]) -> tuple[bool, str, str]:
    for event in events:
        if not isinstance(event, dict):
            continue
        if str(event.get("type") or "") != "turn_failed":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        raw_error = str(payload.get("error") or "")
        raw_type = str(payload.get("error_type") or "")
        lowered = (raw_error + " " + raw_type).lower()
        if "winerror 10013" in lowered or "access socket" in lowered or "permission" in lowered:
            return (
                True,
                "真实 LLM 调用失败，网络连接被系统拒绝。无法连接 LLM。",
                "WinError10013" if "winerror 10013" in lowered else (raw_type or "PermissionError"),
            )
        if "llm network error" in lowered or "timed out" in lowered or "connection reset" in lowered:
            return (True, "真实 LLM 调用失败，网络连接异常。无法连接 LLM。", raw_type or "RuntimeError")
    return (False, "", "")


def render_agent_result(
    *,
    result: Any,
    provider_line: str,
    output_mode: str,
    mask_fn: Any,
) -> str:
    final_answer = safe_text(mask_fn, getattr(result, "final_answer", "") or "")
    stop_reason = safe_text(mask_fn, getattr(result, "stop_reason", "") or "")
    status = safe_text(mask_fn, getattr(result, "status", "") or "")
    output_type = safe_text(mask_fn, getattr(result, "output_type", "") or "answer")
    tool_calls = list(getattr(result, "tool_calls", []) or [])
    available_skills = list(getattr(result, "available_skills", []) or [])
    loaded_skills = list(getattr(result, "loaded_skills", []) or [])
    skill_loads_count = int(getattr(result, "skill_loads_count", 0) or 0)
    skills_used = list(getattr(result, "skills_used", []) or [])
    skill_calls_count = int(getattr(result, "skill_calls_count", 0) or 0)
    skill_results = list(getattr(result, "skill_results", []) or [])
    events = list(getattr(result, "events", []) or [])
    summary = dict(getattr(result, "summary", {}) or {})
    summary_machine = dict(summary.get("machine") or {})
    risks = list(summary_machine.get("risks") or [])

    has_provider_error, provider_error_message, provider_error_type = provider_error_info(events)

    if output_mode == "quiet":
        if has_provider_error and not final_answer:
            return provider_error_message
        return final_answer

    if output_mode == "json":
        normalized_stop_reason = stop_reason
        error_payload: dict[str, Any] | None = None
        if has_provider_error:
            normalized_stop_reason = "provider_network_error"
            error_payload = {
                "type": provider_error_type or "RuntimeError",
                "message": provider_error_message,
            }
        tools_used = list(summary_machine.get("tools_used") or [])
        model_backend = str(getattr(result, "model_backend", "") or summary_machine.get("model_backend") or provider_line.split("model=")[-1].split()[0] if "model=" in provider_line else "unknown")
        model_provider = str(summary_machine.get("model_provider") or "unknown")
        model_name = str(summary_machine.get("model_name") or "unknown")
        payload = {
            "ok": getattr(result, "ok", True),
            "result": {
                "status": status,
                "output_type": output_type,
                "stop_reason": normalized_stop_reason,
                "final_answer": final_answer,
                "tool_calls_count": len(tool_calls),
                "tools_used": tools_used,
                "tool_calls": tool_calls,
                "available_skills": available_skills,
                "loaded_skills": loaded_skills,
                "skill_loads_count": skill_loads_count,
                "skills_used": skills_used,
                "skill_calls_count": skill_calls_count,
                "skill_results": skill_results,
                "summary": summary,
                "events": events,
                "model_backend": model_backend,
                "model_provider": model_provider,
                "model_name": model_name,
            },
        }
        if error_payload is not None:
            payload["result"]["error"] = error_payload
        return json.dumps(payload, ensure_ascii=False, indent=2)

    lines: list[str] = []
    lines.append("Jarvis")
    lines.append(final_answer or (provider_error_message if has_provider_error else "(empty)"))

    if tool_calls:
        lines.append("")
        lines.append("工具摘要")
        for idx, call in enumerate(tool_calls, start=1):
            name = safe_text(mask_fn, call.get("name", "unknown"))
            args = compact_tool_args(mask_fn, call.get("arguments"))
            lines.append(f"{idx}. {name}" + (f" ({args})" if args else ""))

    if output_mode == "default":
        if (stop_reason or "").lower() not in {"completed", "success"}:
            lines.append("")
            lines.append(f"stop_reason={stop_reason or 'unknown'}")
        if has_provider_error:
            lines.extend(
                [
                    "",
                    "可能原因：",
                    "- Windows 防火墙或安全软件阻止 Python 访问网络",
                    "- 代理未配置",
                    "- 当前网络限制外部 API",
                    "- base_url 不可达",
                    "",
                    "你可以先运行：",
                    "python scripts/check_llm_api.py",
                ]
            )
        return "\n".join(lines).strip()

    lines.append("")
    lines.append("Runtime")
    lines.append(provider_line)
    lines.append(f"status={status or 'unknown'}")
    lines.append(f"output_type={output_type or 'answer'}")
    lines.append(f"stop_reason={stop_reason or 'unknown'}")

    if output_mode in {"verbose", "trace"}:
        lines.append("")
        lines.append("Summary")
        outcome = safe_text(mask_fn, summary_machine.get("outcome", ""))
        tools_used = ", ".join(safe_text(mask_fn, x) for x in list(summary_machine.get("tools_used") or [])[:8])
        commands_run = ", ".join(safe_text(mask_fn, x) for x in list(summary_machine.get("commands_run") or [])[:5])
        tests_run = ", ".join(safe_text(mask_fn, x) for x in list(summary_machine.get("tests_run") or [])[:5])
        lines.append(f"outcome={outcome or 'unknown'}")
        lines.append(f"tools_used={tools_used or '(none)'}")
        if commands_run:
            lines.append(f"commands_run={commands_run}")
        if tests_run:
            lines.append(f"tests_run={tests_run}")
        if risks:
            lines.append(f"risks={'; '.join(safe_text(mask_fn, x) for x in risks[:5])}")
        if available_skills:
            lines.append(f"available_skills={', '.join(safe_text(mask_fn, x) for x in available_skills[:8])}")
        if loaded_skills:
            lines.append(f"loaded_skills={', '.join(safe_text(mask_fn, x) for x in loaded_skills[:8])}")
        lines.append(f"skill_loads_count={skill_loads_count}")
        if skills_used:
            lines.append(f"skills_used={', '.join(safe_text(mask_fn, x) for x in skills_used[:8])}")
        lines.append(f"skill_calls_count={skill_calls_count}")
        active_task = summary_machine.get("active_task") if isinstance(summary_machine.get("active_task"), dict) else {}
        if active_task:
            lines.append(f"active_task_phase={safe_text(mask_fn, active_task.get('current_phase', ''))}")
        handoff = summary_machine.get("handoff_summary") if isinstance(summary_machine.get("handoff_summary"), dict) else {}
        if handoff:
            lines.append(f"handoff_state={safe_text(mask_fn, handoff.get('current_state', ''))}")

    if output_mode == "trace":
        lines.append("")
        lines.append("Trace")
        for idx, event in enumerate(events, start=1):
            evt_type = safe_text(mask_fn, event.get("type", "unknown"))
            payload = event.get("payload") if isinstance(event, dict) else {}
            payload_text = safe_text(mask_fn, json.dumps(payload, ensure_ascii=False))
            lines.append(f"{idx}. {evt_type} {payload_text[:180]}")

    return "\n".join(lines).strip()
