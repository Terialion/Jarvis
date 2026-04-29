"""Lightweight shared API server for Jarvis CLI + Web control surface.

This module intentionally keeps runtime coupling low and uses safe defaults.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from ..core.skill_harness.executor import execute_skill
from ..core.skill_harness.registry import get_skill_registry
from ..core.skill_harness.selector import select_skills_for_task
from ..core.skill_harness.telemetry import SkillTelemetryStore, SkillUsageRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class JarvisApiState:
    """In-memory state for shared API routes."""

    tasks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    task_events: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    chats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    chat_messages: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    terminal_sessions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    terminal_events: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    approvals: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.approvals:
            aid = _new_id("approval")
            self.approvals[aid] = {
                "approval_id": aid,
                "risk_tier": "high",
                "reason": "Risky command requires confirmation",
                "safe_alternative": "Run in safe mode with read-only plan",
                "status": "pending",
                "created_at": _now(),
            }


def _json_ok(data: Any) -> Dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _json_err(code: str, message: str) -> Dict[str, Any]:
    return {"ok": False, "data": None, "error": {"code": code, "message": message}}


def _split_path(path: str) -> List[str]:
    return [p for p in path.split("/") if p]


def _task_summary(state: JarvisApiState, task_id: str) -> Dict[str, Any]:
    task = state.tasks.get(task_id)
    if not task:
        return {}
    return {
        "task_id": task["task_id"],
        "run_id": task["run_id"],
        "trace_id": task["trace_id"],
        "status": task["status"],
        "mode": task["mode"],
        "input": task["input"],
        "created_at": task["created_at"],
        "events_url": f"/api/tasks/{task_id}/events",
        "websocket_url": f"/ws/tasks/{task_id}",
        "safe_use": task.get("safe_use", {}),
        "skills": task.get("skills", {}),
    }


def _operator_summary(state: JarvisApiState, task_id: str) -> Dict[str, Any]:
    task = state.tasks.get(task_id, {})
    events = state.task_events.get(task_id, [])
    skills = dict(task.get("skills") or {})
    return {
        "task_id": task_id,
        "route_summary": "safe_route" if task.get("mode", "safe") == "safe" else "edit_route",
        "skill_summary": "selected skills available" if skills.get("selected") else "no skill selected",
        "risk_summary": "high risk gated by approval" if task.get("require_approval") else "low risk",
        "recovery_summary": "none",
        "rethink_summary": "none",
        "hooks_summary": {"fired": 0, "failed": 0, "blocked": 0},
        "memory_summary": {"memory_used": 0, "memory_written": 0, "memory_rejected": 0, "memory_redacted": 0},
        "subagent_summary": {"count": 0},
        "demo_summary": None,
        "skills": {
            "loaded": int(skills.get("loaded", 0)),
            "selected": list(skills.get("selected") or []),
            "rejected": list(skills.get("rejected") or []),
            "quarantined": list(skills.get("quarantined") or []),
            "blocked": list(skills.get("blocked") or []),
            "approval_required": list(skills.get("approval_required") or []),
            "dry_run": list(skills.get("dry_run") or []),
            "usage_recorded": int(skills.get("usage_recorded", 0)),
            "instruction_sources": list(skills.get("instruction_sources") or []),
        },
        "changed_files": [],
        "diff_summary": "no edits",
        "tests_run": [],
        "rollback_available": False,
        "evidence_links": [f"/api/tasks/{task_id}/evidence"],
        "events_count": len(events),
    }


def _task_evidence(state: JarvisApiState, task_id: str) -> Dict[str, Any]:
    task = state.tasks.get(task_id, {})
    skills = dict(task.get("skills") or {})
    return {
        "task_id": task_id,
        "artifacts": [
            {"kind": "operator_summary", "url": f"/api/tasks/{task_id}/operator-summary"},
            {"kind": "replay", "url": f"/api/tasks/{task_id}/replay"},
            {
                "kind": "skill_selection",
                "detail": {
                    "selected": list(skills.get("selected") or []),
                    "rejected": list(skills.get("rejected") or []),
                    "policy": dict(skills.get("policy") or {}),
                },
            },
        ],
    }


def _skill_registry_snapshot() -> dict[str, Any]:
    registry = get_skill_registry(".", refresh=True)
    snap = registry.snapshot().get("data", {})
    items = list(snap.get("items") or [])
    skills: list[dict[str, Any]] = []
    for item in items:
        skills.append(
            {
                "id": str(item.get("id") or item.get("skill_id") or ""),
                "name": str(item.get("name") or item.get("skill_name") or ""),
                "status": "available" if str(item.get("status")) == "enabled" else str(item.get("status") or "invalid"),
                "trust": str(item.get("trust") or item.get("metadata", {}).get("trust", {}).get("trust_level", "unknown")),
                "quarantine": bool(item.get("quarantine") or item.get("metadata", {}).get("trust", {}).get("quarantined", False)),
                "source": str(item.get("source") or ""),
                "source_priority": int(item.get("source_priority") or 0),
                "invocation": str(item.get("invocation") or "auto"),
                "description": str(item.get("description") or ""),
                "triggers": list(item.get("tags") or item.get("triggers") or []),
                "shadowed_by": item.get("shadowed_by"),
            }
        )
    return {
        "roots": list((snap.get("discovery") or {}).get("roots") or []),
        "skills": skills,
        "count": len(skills),
    }


def _chat_summary(state: JarvisApiState, session_id: str) -> Dict[str, Any]:
    chat = state.chats.get(session_id, {})
    return {
        "session_id": session_id,
        "mode": chat.get("mode", "safe"),
        "created_at": chat.get("created_at", _now()),
        "messages_url": f"/api/chat/{session_id}/messages",
        "events_url": f"/api/chat/{session_id}/events",
        "websocket_url": f"/ws/chat/{session_id}",
    }


def _terminal_summary(state: JarvisApiState, session_id: str) -> Dict[str, Any]:
    session = state.terminal_sessions.get(session_id, {})
    return {
        "session_id": session_id,
        "mode": session.get("mode", "safe"),
        "created_at": session.get("created_at", _now()),
        "safe_use": session.get(
            "safe_use",
            {
                "command_execution_enabled": False,
                "require_approval": True,
            },
        ),
        "events_url": f"/api/terminal/sessions/{session_id}/events",
        "websocket_url": f"/ws/terminal/{session_id}",
    }


def route_request(
    state: JarvisApiState, method: str, path: str, body: Dict[str, Any] | None = None
) -> Tuple[int, Dict[str, Any]]:
    """Pure route handler for tests and HTTP adapter."""

    body = body or {}
    route = path.split("?", 1)[0]
    parts = _split_path(route)

    if method == "GET" and route == "/api/health":
        return 200, _json_ok({"status": "ok", "mode": "safe", "run_status": "idle", "updated_at": _now()})
    if method == "GET" and route == "/api/capabilities":
        return 200, _json_ok({"modes": ["safe", "edit", "review"], "tools": ["shell", "edit", "search", "test"]})
    if method == "GET" and route == "/api/settings/effective":
        return 200, _json_ok(
            {
                "mode": "safe",
                "safe_mode_default": True,
                "hooks_enabled": True,
                "memory_enabled": True,
                "metrics_enabled": True,
                "approval_policy": "require_approval_for_high_risk",
                "safe_use": {
                    "max_commands": 3,
                    "max_files_changed": 0,
                    "docker_enabled": False,
                    "external_benchmark_enabled": False,
                    "network_enabled": False,
                },
            }
        )

    if method == "POST" and route == "/api/chat":
        message = str(body.get("message") or "").strip()
        if not message:
            return 400, _json_err("COMMON_INVALID_ARGUMENT", "message is required")
        session_id = str(body.get("session_id") or _new_id("chat"))
        message_id = _new_id("msg")
        if session_id not in state.chats:
            state.chats[session_id] = {"session_id": session_id, "mode": str(body.get("mode") or "safe"), "created_at": _now()}
        bucket = state.chat_messages.setdefault(session_id, [])
        bucket.append(
            {
                "message_id": message_id,
                "role": "user",
                "content": message,
                "ts": _now(),
                "type": "chat.message.created",
            }
        )
        bucket.append(
            {
                "message_id": _new_id("msg"),
                "role": "assistant",
                "content": "Acknowledged. Running in safe mode.",
                "ts": _now(),
                "type": "chat.assistant.completed",
            }
        )
        return 200, _json_ok(
            {
                "session_id": session_id,
                "message_id": message_id,
                "status": "accepted",
                "events_url": f"/api/chat/{session_id}/events",
                "websocket_url": f"/ws/chat/{session_id}",
            }
        )

    if method == "GET" and route == "/api/gateway/status":
        return 200, _json_ok({"status": "ok", "safe_mode": True})
    if method == "GET" and route == "/api/channels":
        return 200, _json_ok([{"channel_id": "local", "status": "active"}])
    if method == "GET" and route == "/api/nodes":
        return 200, _json_ok([{"node_id": "primary", "status": "ready"}])
    if method == "GET" and route == "/api/skills":
        snapshot = _skill_registry_snapshot()
        return 200, _json_ok({"skills": snapshot["skills"], "count": snapshot["count"], "roots": snapshot["roots"]})
    if method == "GET" and route == "/api/skills/insights":
        telemetry = SkillTelemetryStore()
        return 200, _json_ok(telemetry.insights())
    if method == "GET" and route == "/api/logs":
        return 200, _json_ok([{"ts": _now(), "level": "info", "message": "api ready"}])
    if method == "GET" and route == "/api/resources":
        return 200, _json_ok([{"resource_id": "workspace", "path": "."}])

    if method == "POST" and route == "/api/tasks":
        input_text = str(body.get("input") or body.get("prompt") or "").strip()
        if not input_text:
            return 400, _json_err("COMMON_INVALID_ARGUMENT", "input is required")
        mode = str(body.get("mode") or "safe").lower()
        allow_code_changes = bool(body.get("allow_code_changes", False))
        max_commands = int(body.get("max_commands", 3))
        max_files_changed = int(body.get("max_files_changed", 0))
        require_approval = bool(body.get("require_approval", True))

        task_id = _new_id("task")
        run_id = _new_id("run")
        trace_id = _new_id("trace")
        skill_registry = get_skill_registry(".", refresh=True)
        selection_policy = {
            "safe_mode": mode == "safe",
            "network_enabled": False,
            "require_approval_for_untrusted": True,
        }
        selection = select_skills_for_task(input_text, skill_registry, selection_policy)
        selected_ids = [record.id for record in selection.selected]
        rejected = list(selection.rejected)
        quarantined = [
            record.id
            for record in skill_registry.list_skill_records(include_invalid=True)
            if record.quarantine or record.status in {"invalid", "quarantined"}
        ]
        execution_result = None
        if selected_ids:
            execution_result = execute_skill(
                selected_ids[0],
                input_text,
                registry=skill_registry,
                dry_run=True,
                policy=selection.policy,
            )
        telemetry = SkillTelemetryStore()
        usage_event = telemetry.append(
            SkillUsageRecord(
                skill_id=selected_ids[0] if selected_ids else "none",
                input_preview=input_text[:160],
                selected=bool(selected_ids),
                executed=False,
                mode=str(mode if mode in {"safe", "ask", "edit"} else "safe"),
                outcome=str((execution_result or {}).get("status") or ("selection_empty" if not selected_ids else "approval_required")),
                reason=str((execution_result or {}).get("reason") or selection.reason),
                policy=dict(selection.policy),
                instruction_sources=list(dict(selection.policy).get("instruction_context", {}).get("sources", [])),
            )
        )

        instruction_sources = list(dict(selection.policy).get("instruction_context", {}).get("sources", []))
        blocked_skills = [
            str(row.get("skill_id") or "")
            for row in rejected
            if str(row.get("reason") or "") in {"network_disabled", "denied_tool_by_policy", "blocked_by_project_instruction"}
        ]
        approval_required_skills = [
            str(row.get("skill_id") or "")
            for row in rejected
            if str(row.get("reason") or "") == "approval_required_for_untrusted"
        ]
        dry_run_skills = selected_ids[:1] if execution_result is not None else []

        state.tasks[task_id] = {
            "task_id": task_id,
            "run_id": run_id,
            "trace_id": trace_id,
            "status": "created",
            "input": input_text,
            "mode": mode if mode in {"safe", "edit", "review"} else "safe",
            "allow_code_changes": allow_code_changes,
            "max_commands": max_commands,
            "max_files_changed": max_files_changed,
            "require_approval": require_approval,
            "created_at": _now(),
            "safe_use": {
                "max_commands": min(max_commands, 3),
                "max_files_changed": 0 if mode == "safe" else max_files_changed,
                "docker_enabled": False,
                "external_benchmark_enabled": False,
                "network_enabled": False,
            },
            "skills": {
                "loaded": len(skill_registry.list_skill_records(include_invalid=True)),
                "selected": selected_ids,
                "rejected": rejected,
                "quarantined": quarantined,
                "blocked": blocked_skills,
                "approval_required": approval_required_skills,
                "dry_run": dry_run_skills,
                "usage_recorded": 1,
                "instruction_sources": instruction_sources,
                "policy": selection.policy,
                "execution": execution_result,
            },
        }
        state.task_events[task_id] = [
            {"type": "task.created", "ts": _now(), "detail": {"task_id": task_id}},
            {"type": "task.started", "ts": _now(), "detail": {"run_id": run_id}},
            {"type": "route.selected", "ts": _now(), "detail": {"mode": state.tasks[task_id]["mode"]}},
            {"type": "policy.checked", "ts": _now(), "detail": {"safe_mode": state.tasks[task_id]["mode"] == "safe"}},
            {"type": "plan.created", "ts": _now(), "detail": {"steps": 3}},
            {
                "type": "skill.registry.loaded",
                "ts": _now(),
                "detail": {
                    "loaded": len(skill_registry.list_skill_records(include_invalid=True)),
                    "roots": list((skill_registry.snapshot().get("data", {}).get("discovery") or {}).get("roots") or []),
                },
            },
            {
                "type": "skill.selected",
                "ts": _now(),
                "detail": {
                    "selected": selected_ids,
                    "rejected": rejected,
                    "reason": selection.reason,
                },
            },
            {
                "type": "skill.routing.context_loaded",
                "ts": _now(),
                "detail": {"instruction_sources": instruction_sources},
            },
            {
                "type": "skill.policy.checked",
                "ts": _now(),
                "detail": selection.policy,
            },
            {
                "type": "skill.usage.recorded",
                "ts": _now(),
                "detail": usage_event,
            },
        ]
        if execution_result is not None:
            state.task_events[task_id].append(
                {
                    "type": "skill.execution.dry_run",
                    "ts": _now(),
                    "detail": execution_result,
                }
            )
        if require_approval:
            aid = _new_id("approval")
            state.approvals[aid] = {
                "approval_id": aid,
                "risk_tier": "high",
                "reason": f"Task {task_id} requests risky action",
                "safe_alternative": "continue in safe mode",
                "status": "pending",
                "task_id": task_id,
                "parent_run_id": run_id,
                "created_at": _now(),
            }
            state.task_events[task_id].append(
                {"type": "approval.requested", "ts": _now(), "detail": {"approval_id": aid}}
            )

        return 200, _json_ok(
            {
                "task_id": task_id,
                "run_id": run_id,
                "trace_id": trace_id,
                "status": "created",
                "events_url": f"/api/tasks/{task_id}/events",
                "websocket_url": f"/ws/tasks/{task_id}",
            }
        )

    if len(parts) >= 2 and parts[0] == "api" and parts[1] == "chat":
        if method == "GET" and len(parts) == 3:
            session_id = parts[2]
            if session_id not in state.chats:
                return 404, _json_err("COMMON_NOT_FOUND", f"chat session not found: {session_id}")
            return 200, _json_ok(_chat_summary(state, session_id))
        if method == "GET" and len(parts) == 4 and parts[3] == "messages":
            session_id = parts[2]
            if session_id not in state.chats:
                return 404, _json_err("COMMON_NOT_FOUND", f"chat session not found: {session_id}")
            return 200, _json_ok(state.chat_messages.get(session_id, []))
        if method == "GET" and len(parts) == 4 and parts[3] == "events":
            session_id = parts[2]
            if session_id not in state.chats:
                return 404, _json_err("COMMON_NOT_FOUND", f"chat session not found: {session_id}")
            events = []
            for idx, msg in enumerate(state.chat_messages.get(session_id, []), start=1):
                events.append(
                    {
                        "index": idx,
                        "type": msg.get("type", "chat.message.created"),
                        "ts": msg.get("ts", _now()),
                        "detail": {"message_id": msg.get("message_id"), "role": msg.get("role")},
                    }
                )
            return 200, _json_ok(events)

    if method == "POST" and route == "/api/terminal/sessions":
        mode = str(body.get("mode") or "safe")
        session_id = _new_id("term")
        state.terminal_sessions[session_id] = {
            "session_id": session_id,
            "mode": mode,
            "created_at": _now(),
            "safe_use": {
                "command_execution_enabled": False,
                "require_approval": True,
            },
        }
        state.terminal_events[session_id] = [
            {
                "index": 1,
                "type": "terminal.output",
                "ts": _now(),
                "detail": {"line": "Terminal session created in safe mode (read-only)."},
            }
        ]
        return 200, _json_ok(_terminal_summary(state, session_id))

    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "terminal" and parts[2] == "sessions":
        session_id = parts[3]
        if session_id not in state.terminal_sessions:
            return 404, _json_err("COMMON_NOT_FOUND", f"terminal session not found: {session_id}")
        if method == "GET" and len(parts) == 4:
            return 200, _json_ok(_terminal_summary(state, session_id))
        if method == "GET" and len(parts) == 5 and parts[4] == "events":
            return 200, _json_ok(state.terminal_events.get(session_id, []))
        if method == "POST" and len(parts) == 5 and parts[4] == "input":
            text = str(body.get("input") or "").strip()
            state.terminal_events.setdefault(session_id, []).append(
                {
                    "index": len(state.terminal_events.get(session_id, [])) + 1,
                    "type": "terminal.output",
                    "ts": _now(),
                    "detail": {
                        "line": "Command execution blocked by safe mode.",
                        "input_echo": text[:64],
                        "blocked": True,
                    },
                }
            )
            return 200, _json_ok({"session_id": session_id, "accepted": False, "blocked_by": "safe_mode"})

    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "tasks":
        task_id = parts[2]
        if task_id not in state.tasks:
            return 404, _json_err("COMMON_NOT_FOUND", f"task not found: {task_id}")
        if method == "GET" and len(parts) == 3:
            return 200, _json_ok(_task_summary(state, task_id))
        if method == "GET" and len(parts) == 4 and parts[3] == "events":
            return 200, _json_ok(state.task_events.get(task_id, []))
        if method == "GET" and len(parts) == 4 and parts[3] == "replay":
            replay = [
                {"index": i + 1, **event}
                for i, event in enumerate(state.task_events.get(task_id, []))
            ]
            return 200, _json_ok(replay[-300:])
        if method == "GET" and len(parts) == 4 and parts[3] == "evidence":
            return 200, _json_ok(_task_evidence(state, task_id))
        if method == "GET" and len(parts) == 4 and parts[3] == "operator-summary":
            return 200, _json_ok(_operator_summary(state, task_id))

    if method == "GET" and route == "/api/approvals":
        return 200, _json_ok(list(state.approvals.values()))
    if len(parts) == 4 and parts[0] == "api" and parts[1] == "approvals" and method == "POST":
        approval_id = parts[2]
        action = parts[3]
        target = state.approvals.get(approval_id)
        if not target:
            return 404, _json_err("COMMON_NOT_FOUND", f"approval not found: {approval_id}")
        if action not in {"approve", "reject"}:
            return 404, _json_err("COMMON_NOT_FOUND", f"unknown approval action: {action}")
        target["status"] = "approved" if action == "approve" else "rejected"
        target["resolved_at"] = _now()
        task_id = target.get("task_id")
        if task_id and task_id in state.task_events:
            state.task_events[task_id].append(
                {
                    "type": "approval.resolved",
                    "ts": _now(),
                    "detail": {"approval_id": approval_id, "decision": target["status"]},
                }
            )
        return 200, _json_ok(target)

    return 404, _json_err("COMMON_NOT_FOUND", f"unknown route: {route}")


def make_handler(state: JarvisApiState) -> type[BaseHTTPRequestHandler]:
    """Build HTTP handler bound to given state."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _handle(self, method: str) -> None:
            parsed = urlparse(self.path)
            body: Dict[str, Any] | None = None
            if method == "POST":
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length > 0:
                    raw = self.rfile.read(length).decode("utf-8", "ignore")
                    try:
                        body = json.loads(raw)
                    except json.JSONDecodeError:
                        self._send(400, _json_err("COMMON_INVALID_ARGUMENT", "invalid json body"))
                        return
            status, payload = route_request(state, method, parsed.path + (f"?{parsed.query}" if parsed.query else ""), body)
            self._send(status, payload)

        def _send(self, status: int, payload: Dict[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run threaded API server."""
    state = JarvisApiState()
    server = ThreadingHTTPServer((host, port), make_handler(state))
    print(f"Jarvis API server listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


__all__ = ["JarvisApiState", "route_request", "make_handler", "run_server"]
