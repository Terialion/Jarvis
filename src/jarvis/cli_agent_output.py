"""CLI renderer for AgentRunResult — Rich-enhanced output."""

from __future__ import annotations

import json
from typing import Any

from .cli_ui.render import render_markdown, render_panel


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
            return (True, "LLM network error: connection refused by system", "NetworkError")
        if "llm network error" in lowered or "timed out" in lowered or "connection reset" in lowered:
            return (True, "LLM network error: connection failed", raw_type or "RuntimeError")
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
    events = list(getattr(result, "events", []) or [])
    summary = dict(getattr(result, "summary", {}) or {})
    summary_machine = dict(summary.get("machine") or {})
    skills_used = list(getattr(result, "skills_used", []) or [])
    available_skills = list(getattr(result, "available_skills", []) or [])
    loaded_skills = list(getattr(result, "loaded_skills", []) or [])

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
            error_payload = {"type": provider_error_type or "RuntimeError", "message": provider_error_message}
        tools_used = list(summary_machine.get("tools_used") or [])
        model_backend = str(
            getattr(result, "model_backend", "")
            or summary_machine.get("model_backend")
            or provider_line.split("model=")[-1].split()[0]
            if "model=" in provider_line
            else "unknown"
        )
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
                "skills_used": skills_used,
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

    # Rich rendering for default/verbose/trace modes
    from .cli_ui.console import THEME

    # Capture rich output as string
    from io import StringIO
    from rich.console import Console as RichConsole

    string_out = StringIO()
    rich_console = RichConsole(file=string_out, force_terminal=False, theme=THEME)

    # Answer — plain markdown, no panel (matching Claude Code)
    if final_answer:
        md = render_markdown(final_answer)
        rich_console.print(md)
    elif has_provider_error:
        rich_console.print(render_panel(provider_error_message, title="Error", border_style="error"))
    else:
        rich_console.print(render_panel("(empty response)", title="Agent", border_style="muted"))

    # Tool call summary — compact inline (matching Claude Code)
    if tool_calls:
        from rich.text import Text
        from .cli_ui.streaming import _TOOL_DISPLAY, _format_tool_args
        tool_text = Text()
        for idx, call in enumerate(tool_calls, start=1):
            raw_name = safe_text(mask_fn, call.get("name", "unknown"))
            display_name = _TOOL_DISPLAY.get(raw_name, raw_name)
            raw_args_str = json.dumps(call.get("arguments", {}), ensure_ascii=False) if isinstance(call.get("arguments"), dict) else str(call.get("arguments", ""))
            formatted_args = _format_tool_args(raw_name, raw_args_str)
            tool_text.append(f"  {display_name}", style="tool")
            if formatted_args:
                tool_text.append(f"({formatted_args})", style="muted")
            if idx < len(tool_calls):
                tool_text.append("\n")
        rich_console.print(tool_text)

    # Status footer — only in verbose/trace
    if output_mode in ("verbose", "trace"):
        from rich.table import Table
        info = Table(show_header=False, border_style="divider", padding=(0, 1))
        info.add_column(style="muted", width=15)
        info.add_column()
        info.add_row("Status", status or "unknown")
        info.add_row("Stop reason", stop_reason or "unknown")
        info.add_row("Output type", output_type or "answer")
        if skills_used:
            info.add_row("Skills used", ", ".join(str(s) for s in skills_used[:8]))
        if available_skills:
            info.add_row("Available", ", ".join(str(s) for s in available_skills[:8]))
        rich_console.print(render_panel(info, title="Runtime Info", border_style="divider"))
        rich_console.print(provider_line)

    if output_mode == "trace":
        from rich.text import Text
        trace_text = Text()
        for idx, event in enumerate(events, start=1):
            evt_type = safe_text(mask_fn, event.get("type", "unknown"))
            payload = event.get("payload") if isinstance(event, dict) else {}
            payload_text = safe_text(mask_fn, json.dumps(payload, ensure_ascii=False))
            trace_text.append(f"{idx}. {evt_type} ", style="number")
            trace_text.append(f"{payload_text[:180]}\n", style="muted")
        rich_console.print(render_panel(trace_text, title="Trace", border_style="divider"))

    if has_provider_error:
        rich_console.print(
            render_panel(
                "Possible causes:\n"
                "- Firewall or security software blocking network\n"
                "- Proxy not configured\n"
                "- Network limits external API access\n"
                "- base_url unreachable\n\n"
                "Run: python scripts/check_llm_api.py",
                title="Troubleshooting",
                border_style="warning",
            )
        )

    return string_out.getvalue().strip()
