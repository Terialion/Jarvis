"""JSONL-based session store — append-only transcripts + sidecar JSON for mutable state.

Follows Claude Code's approach: one .jsonl file per session, one .json sidecar
for mutable on-disk state (active_task, handoff, project_facts).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..agent.skill_context import ActiveTaskState, HandoffSummary, SkillObservation
from ..agent.types import AgentRunResult, AgentTurn, ChatInput
from ..core.policy.approval import ApprovalRequest, ApprovalResponse
from ..web.research_context import ResearchObservation
from .redaction import redact_for_persistence, redact_text_for_persistence
from .schema import SCHEMA_VERSION, utc_now


class SessionStoreError(RuntimeError):
    """Structured persistence failure."""


def _now() -> str:
    return utc_now()


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid4().hex[:12]}"


class SessionStore:
    """Durable session persistence backed by append-only JSONL + sidecar JSON."""

    def __init__(self, sessions_dir: str | Path | None = None) -> None:
        if sessions_dir is not None:
            self.sessions_dir = Path(sessions_dir)
        else:
            self.sessions_dir = self._default_sessions_dir()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        # In-memory cache: session_id -> list[dict] (parsed JSONL lines)
        self._cache: dict[str, list[dict[str, Any]]] = {}
        # Sidecar cache: session_id -> dict (the .json sidecar)
        self._sidecar_cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _default_sessions_dir() -> Path:
        current_test = os.environ.get("PYTEST_CURRENT_TEST")
        if current_test:
            safe = "".join(ch if ch.isalnum() else "_" for ch in current_test)[:80] or "pytest"
            return Path(tempfile.gettempdir()) / "jarvis_pytest_sessions" / safe
        return Path(".jarvis/sessions")

    # ── Path helpers ──────────────────────────────────────────────────

    def _jsonl_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.jsonl"

    def _sidecar_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    # ── Cache management ──────────────────────────────────────────────

    def _ensure_loaded(self, session_id: str) -> list[dict[str, Any]]:
        if session_id not in self._cache:
            with self._lock:
                if session_id not in self._cache:
                    self._cache[session_id] = self._read_jsonl(session_id)
        return self._cache[session_id]

    def _read_jsonl(self, session_id: str) -> list[dict[str, Any]]:
        path = self._jsonl_path(session_id)
        if not path.exists():
            return []
        lines: list[dict[str, Any]] = []
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            return []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    lines.append(obj)
            except json.JSONDecodeError:
                continue
        return lines

    def _append_line(self, session_id: str, obj: dict[str, Any]) -> None:
        with self._lock:
            obj.setdefault("timestamp", _now())
            line = json.dumps(obj, ensure_ascii=False) + "\n"
            path = self._jsonl_path(session_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            if session_id in self._cache:
                self._cache[session_id].append(obj)

    def _invalidate(self, session_id: str) -> None:
        self._cache.pop(session_id, None)

    # ── Sidecar (mutable state) ───────────────────────────────────────

    def _load_sidecar(self, session_id: str) -> dict[str, Any]:
        if session_id in self._sidecar_cache:
            return self._sidecar_cache[session_id]
        with self._lock:
            if session_id in self._sidecar_cache:
                return self._sidecar_cache[session_id]
            path = self._sidecar_path(session_id)
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    self._sidecar_cache[session_id] = data
                    return data
                except Exception:
                    pass
            data: dict[str, Any] = {
                "session_id": session_id,
                "title": None,
                "created_at": _now(),
                "updated_at": _now(),
                "project_id": None,
                "cwd": None,
            }
            self._sidecar_cache[session_id] = data
            return data

    def _save_sidecar(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._sidecar_cache:
                self._sidecar_cache[session_id]["updated_at"] = _now()
                path = self._sidecar_path(session_id)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(self._sidecar_cache[session_id], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

    def _touch_sidecar(self, session_id: str) -> None:
        data = self._load_sidecar(session_id)
        data["updated_at"] = _now()
        self._save_sidecar(session_id)

    # ── Session lifecycle ─────────────────────────────────────────────

    def create_or_resume_session(self, chat_input: ChatInput) -> dict[str, Any]:
        session_id = str(chat_input.session_id or _uid("session_"))
        sidecar = self._load_sidecar(session_id)
        if "created_at" not in sidecar or sidecar.get("title") is None:
            sidecar["title"] = str(chat_input.text or "").strip()[:80] or None
            sidecar["project_id"] = chat_input.project_id
            sidecar["cwd"] = chat_input.cwd
            if "created_at" not in sidecar:
                sidecar["created_at"] = _now()
            self._save_sidecar(session_id)
        else:
            self._touch_sidecar(session_id)
            if not sidecar.get("title"):
                title = str(chat_input.text or "").strip()[:80]
                if title:
                    sidecar["title"] = title
                    self._save_sidecar(session_id)
        return {"session_id": session_id, "project_id": chat_input.project_id, "cwd": chat_input.cwd}

    def load_last_session_id(self) -> str | None:
        sessions = self.list_sessions(limit=1)
        return sessions[0]["session_id"] if sessions else None

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        # Collect sessions from JSONL files (have data) and sidecar-only (created but empty)
        seen: set[str] = set()
        result: list[dict[str, Any]] = []

        jsonl_files = sorted(
            self.sessions_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in jsonl_files:
            sid = path.stem
            seen.add(sid)
            sc = self._load_sidecar(sid)
            result.append({
                "session_id": sid,
                "thread_id": sid,
                "title": sc.get("title"),
                "created_at": sc.get("created_at", ""),
                "updated_at": sc.get("updated_at", ""),
            })

        # Add sidecar-only sessions (no data written yet)
        sc_files = sorted(
            self.sessions_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in sc_files:
            sid = path.stem
            if sid not in seen and len(result) < max(1, int(limit)):
                sc = self._load_sidecar(sid)
                result.append({
                    "session_id": sid,
                    "thread_id": sid,
                    "title": sc.get("title"),
                    "created_at": sc.get("created_at", ""),
                    "updated_at": sc.get("updated_at", ""),
                })

        return result[:max(1, int(limit))]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        jsonl = self._jsonl_path(session_id)
        sc_path = self._sidecar_path(session_id)
        if not jsonl.exists() and not sc_path.exists():
            return None
        sc = self._load_sidecar(session_id)
        return {
            "session_id": session_id,
            "thread_id": session_id,
            "title": sc.get("title"),
            "created_at": sc.get("created_at", ""),
            "updated_at": sc.get("updated_at", ""),
        }

    def delete_session(self, session_id: str) -> bool:
        jsonl = self._jsonl_path(session_id)
        sidecar = self._sidecar_path(session_id)
        deleted = False
        if jsonl.exists():
            jsonl.unlink()
            deleted = True
        if sidecar.exists():
            sidecar.unlink()
            deleted = True
        self._cache.pop(session_id, None)
        self._sidecar_cache.pop(session_id, None)
        return deleted

    # ── Turn lifecycle ────────────────────────────────────────────────

    def create_turn(
        self,
        session_id: str,
        *,
        status: str = "running",
        metadata: dict[str, Any] | None = None,
    ) -> AgentTurn:
        turn = AgentTurn(
            turn_id=_uid("turn_"),
            session_id=session_id,
            status=status,
            metadata=dict(metadata or {}),
        )
        self._append_line(session_id, {
            "type": "turn",
            "event": "start",
            "turn_id": turn.turn_id,
            "status": status,
        })
        self._touch_sidecar(session_id)
        return turn

    def end_turn(self, session_id: str, agent_result: AgentRunResult, user_input: str | None = None) -> dict[str, Any]:
        summary_human = str((agent_result.summary or {}).get("human") or agent_result.final_answer or "")[:1200]
        turn_data = {
            "type": "turn",
            "event": "end",
            "turn_id": str(agent_result.turn_id),
            "input": redact_text_for_persistence(user_input or ""),
            "output_summary": redact_text_for_persistence(summary_human),
            "output_type": str(agent_result.output_type),
            "stop_reason": str(agent_result.stop_reason or ""),
            "skills_used": list(agent_result.skills_used or []),
            "tool_calls_count": len(agent_result.tool_calls or []),
            "events_count": len(agent_result.events or []),
            "status": agent_result.status,
        }
        self._append_line(session_id, turn_data)
        self._touch_sidecar(session_id)
        return turn_data

    def update_turn_status(self, session_id: str, turn: AgentTurn, status: str) -> AgentTurn:
        turn.status = status
        self._append_line(session_id, {
            "type": "turn",
            "event": "status_change",
            "turn_id": turn.turn_id,
            "status": status,
        })
        self._touch_sidecar(session_id)
        return turn

    # ── Messages ──────────────────────────────────────────────────────

    def append_message(
        self,
        *args: Any,
        turn_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Handle both calling conventions:
        # (session_id, turn_id, role, content) — 4 positional (legacy loop.py)
        # (session_id, role, content, *, turn_id=..., metadata=...) — 3 positional
        if len(args) >= 4:
            session_id, t_id, role, content = args[:4]
            turn_id = str(t_id)
        elif len(args) >= 3:
            session_id, role, content = args[:3]
        else:
            raise TypeError("append_message expects at least 3 positional args: (session_id, role, content) or (session_id, turn_id, role, content)")
        msg = {
            "type": "message",
            "message_id": _uid("msg_"),
            "role": role,
            "content": redact_text_for_persistence(content),
            "turn_id": turn_id,
            "metadata": dict(redact_for_persistence(metadata or {})),
        }
        self._append_line(session_id, msg)
        self._touch_sidecar(session_id)
        return msg

    def load_messages(self, session_id: str, limit: int = 40) -> list[dict[str, Any]]:
        lines = self._ensure_loaded(session_id)
        msg_lines = [l for l in lines if l.get("type") == "message"]
        recent = msg_lines[-max(1, int(limit)):]
        return [
            {
                "message_id": m.get("message_id", ""),
                "session_id": session_id,
                "turn_id": m.get("turn_id"),
                "role": m.get("role", ""),
                "content": m.get("content", ""),
                "metadata": m.get("metadata", {}),
            }
            for m in recent
        ]

    def get_recent_messages(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self.load_messages(session_id, limit=limit)

    def count_messages(self, session_id: str) -> int:
        lines = self._ensure_loaded(session_id)
        return sum(1 for l in lines if l.get("type") == "message")

    # ── Tool calls ────────────────────────────────────────────────────

    def append_tool_call(self, session_id: str, turn_id: str, tool_call: dict[str, Any]) -> dict[str, Any]:
        call = {
            "type": "tool_call",
            "call_id": str(tool_call.get("id") or tool_call.get("call_id") or _uid("call_")),
            "turn_id": turn_id,
            "tool_name": str(tool_call.get("name") or ""),
            "arguments": redact_for_persistence(dict(tool_call.get("arguments") or {})),
            "status": "requested",
        }
        self._append_line(session_id, call)
        self._touch_sidecar(session_id)
        return call

    def append_tool_result(self, session_id: str, turn_id: str, tool_result: dict[str, Any]) -> dict[str, Any]:
        call_id = str(tool_result.get("call_id") or "")
        result = {
            "type": "tool_result",
            "call_id": call_id,
            "turn_id": turn_id,
            "tool_name": str(tool_result.get("name") or ""),
            "ok": bool(tool_result.get("ok")),
            "content": redact_for_persistence(tool_result.get("content")),
            "error": redact_for_persistence(tool_result.get("error")),
            "status": "completed" if bool(tool_result.get("ok")) else "failed",
        }
        self._append_line(session_id, result)
        self._touch_sidecar(session_id)
        return result

    def get_tool_calls(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        lines = self._ensure_loaded(session_id)
        # Collect tool_call and tool_result lines, merge by call_id
        calls: dict[str, dict[str, Any]] = {}
        for l in lines:
            if l.get("type") == "tool_call":
                cid = str(l.get("call_id") or "")
                if cid not in calls:
                    calls[cid] = {
                        "call_id": cid,
                        "thread_id": session_id,
                        "turn_id": l.get("turn_id", ""),
                        "tool_name": l.get("tool_name", ""),
                        "args_redacted": l.get("arguments", {}),
                        "result_redacted": None,
                        "status": l.get("status", "requested"),
                        "created_at": l.get("timestamp", ""),
                    }
            elif l.get("type") == "tool_result":
                cid = str(l.get("call_id") or "")
                if cid in calls:
                    calls[cid]["result_redacted"] = {
                        "content": l.get("content"),
                        "error": l.get("error"),
                        "ok": l.get("ok"),
                    }
                    calls[cid]["status"] = l.get("status", "completed")
        result = list(calls.values())
        return result[-max(1, int(limit)):]

    # ── Summaries ─────────────────────────────────────────────────────

    def save_summary(self, session_id: str, turn_id: str, summary: dict[str, Any]) -> None:
        self._append_line(session_id, {
            "type": "summary",
            "summary_id": _uid("sum_"),
            "turn_id": turn_id,
            "human": str(summary.get("human") or ""),
            "machine": dict(summary.get("machine") or {}),
        })
        self._touch_sidecar(session_id)

    def load_summaries(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        lines = self._ensure_loaded(session_id)
        summary_lines = [l for l in lines if l.get("type") == "summary"]
        recent = summary_lines[-max(1, int(limit)):]
        return [
            {
                "summary_id": s.get("summary_id", ""),
                "session_id": session_id,
                "turn_id": s.get("turn_id", ""),
                "summary": {"human": s.get("human", ""), "machine": s.get("machine", {})},
                "created_at": s.get("timestamp", ""),
            }
            for s in recent
        ]

    # ── Skill observations ────────────────────────────────────────────

    def append_skill_obs(
        self,
        session_id: str,
        observation: SkillObservation,
        *,
        turn_id: str | None = None,
    ) -> dict[str, Any]:
        obs = {
            "type": "skill_obs",
            "observation_id": _uid("skillobs_"),
            "turn_id": turn_id,
            "skill_name": observation.skill_name,
            "summary": redact_text_for_persistence(observation.summary),
            "related_files": [str(x) for x in observation.related_files],
            "facts": redact_for_persistence(observation.facts),
            "tool_calls": redact_for_persistence(observation.tool_calls),
            "created_at": observation.created_at,
        }
        self._append_line(session_id, obs)
        self._touch_sidecar(session_id)
        return obs

    def get_skill_obs(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        lines = self._ensure_loaded(session_id)
        obs_lines = [l for l in lines if l.get("type") == "skill_obs"]
        recent = obs_lines[-max(1, int(limit)):]
        return [
            {
                "observation_id": o.get("observation_id", ""),
                "thread_id": session_id,
                "turn_id": o.get("turn_id"),
                "skill_name": o.get("skill_name", ""),
                "summary_redacted": o.get("summary", ""),
                "related_files": o.get("related_files", []),
                "created_at": o.get("created_at", o.get("timestamp", "")),
                "metadata": {"facts": o.get("facts", {}), "tool_calls": o.get("tool_calls", [])},
            }
            for o in recent
        ]

    # ── Research observations ─────────────────────────────────────────

    def append_research_obs(
        self,
        session_id: str,
        observation: ResearchObservation,
        *,
        turn_id: str | None = None,
    ) -> dict[str, Any]:
        obs = {
            "type": "research_obs",
            "observation_id": _uid("researchobs_"),
            "turn_id": turn_id,
            "query": redact_text_for_persistence(observation.query),
            "sources": redact_for_persistence(observation.sources),
            "evidence": redact_for_persistence(observation.evidence),
            "answer_summary": redact_text_for_persistence(observation.answer_summary),
            "confidence": float(observation.confidence),
            "search_tasks": redact_for_persistence(observation.search_tasks),
            "remaining_questions": redact_for_persistence(observation.remaining_questions),
            "created_at": observation.created_at,
        }
        self._append_line(session_id, obs)
        self._touch_sidecar(session_id)
        return obs

    def get_research_obs(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        lines = self._ensure_loaded(session_id)
        obs_lines = [l for l in lines if l.get("type") == "research_obs"]
        recent = obs_lines[-max(1, int(limit)):]
        return [
            {
                "observation_id": o.get("observation_id", ""),
                "thread_id": session_id,
                "turn_id": o.get("turn_id"),
                "query_redacted": o.get("query", ""),
                "sources_redacted": o.get("sources", []),
                "evidence_redacted": o.get("evidence", []),
                "answer_summary_redacted": o.get("answer_summary", ""),
                "confidence": float(o.get("confidence", 0.0)),
                "created_at": o.get("created_at", o.get("timestamp", "")),
                "metadata": {
                    "search_tasks": o.get("search_tasks", []),
                    "remaining_questions": o.get("remaining_questions", []),
                },
            }
            for o in recent
        ]

    # ── Approval audits ───────────────────────────────────────────────

    def append_approval(
        self,
        session_id: str,
        approval: ApprovalRequest | ApprovalResponse | dict[str, Any],
        *,
        turn_id: str | None = None,
    ) -> dict[str, Any]:
        raw = approval.to_dict() if hasattr(approval, "to_dict") else dict(approval)
        entry = {
            "type": "approval",
            "approval_id": str(raw.get("approval_id") or _uid("approval_")),
            "turn_id": turn_id,
            "tool_name": str(raw.get("tool_name") or ""),
            "arguments_preview": redact_for_persistence(raw.get("arguments_preview") or raw.get("arguments_preview_redacted") or {}),
            "status": str(raw.get("status") or raw.get("decision") or ""),
            "decision": str(raw.get("decision") or "") or None,
            "reason": redact_text_for_persistence(str(raw.get("reason") or "")) or None,
            "created_at": str(raw.get("created_at") or _now()),
            "decided_at": str(raw.get("decided_at") or "") or None,
        }
        self._append_line(session_id, entry)
        self._touch_sidecar(session_id)
        return entry

    def get_approvals(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        lines = self._ensure_loaded(session_id)
        app_lines = [l for l in lines if l.get("type") == "approval"]
        recent = app_lines[-max(1, int(limit)):]
        return [
            {
                "approval_id": a.get("approval_id", ""),
                "thread_id": session_id,
                "turn_id": a.get("turn_id"),
                "tool_name": a.get("tool_name", ""),
                "arguments_preview_redacted": a.get("arguments_preview", {}),
                "status": a.get("status", ""),
                "decision": a.get("decision"),
                "reason_redacted": a.get("reason"),
                "created_at": a.get("created_at", ""),
                "decided_at": a.get("decided_at"),
            }
            for a in recent
        ]

    # ── Mutable state (sidecar) ───────────────────────────────────────

    def save_active_task(self, session_id: str, active_task: ActiveTaskState | None) -> None:
        if active_task is None:
            return
        data = self._load_sidecar(session_id)
        data["active_task"] = {
            "summary": redact_text_for_persistence(active_task.user_goal),
            "related_files": [str(x) for x in active_task.related_files],
            "remaining_work": [str(x) for x in active_task.remaining_work],
            "metadata": redact_for_persistence(active_task.to_dict()),
        }
        self._save_sidecar(session_id)

    def get_active_task(self, session_id: str) -> dict[str, Any] | None:
        data = self._load_sidecar(session_id)
        task = data.get("active_task")
        if not task:
            return None
        return {
            "thread_id": session_id,
            "summary_redacted": task.get("summary", ""),
            "related_files": task.get("related_files", []),
            "remaining_work": task.get("remaining_work", []),
            "updated_at": data.get("updated_at", ""),
            "metadata": task.get("metadata", {}),
        }

    def save_handoff(self, session_id: str, handoff: HandoffSummary | None) -> None:
        if handoff is None:
            return
        data = self._load_sidecar(session_id)
        data["handoff_summary"] = {
            "summary": redact_text_for_persistence(handoff.current_state),
            "risks": [str(x) for x in handoff.risks],
            "metadata": redact_for_persistence(handoff.to_dict()),
        }
        self._save_sidecar(session_id)

    def get_handoff(self, session_id: str) -> dict[str, Any] | None:
        data = self._load_sidecar(session_id)
        hs = data.get("handoff_summary")
        if not hs:
            return None
        return {
            "thread_id": session_id,
            "summary_redacted": hs.get("summary", ""),
            "risks": hs.get("risks", []),
            "updated_at": data.get("updated_at", ""),
            "metadata": hs.get("metadata", {}),
        }

    def save_project_facts(self, session_id: str, project_id: str | None, facts: dict[str, Any] | None) -> None:
        if not project_id or not facts:
            return
        data = self._load_sidecar(session_id)
        raw = redact_for_persistence(facts)
        data.setdefault("projects", {})
        data["projects"][project_id] = {
            "recent_files": [str(x) for x in list(raw.get("recent_files") or [])],
            "recent_sources": [str(x) for x in list(raw.get("recent_sources") or [])],
        }
        self._save_sidecar(session_id)

    def get_project_facts(self, session_id: str, project_id: str | None = None) -> dict[str, Any] | None:
        if not project_id:
            return None
        data = self._load_sidecar(session_id)
        projects = data.get("projects", {})
        proj = projects.get(project_id)
        if not proj:
            return None
        facts = proj.get("recent_files", []) + proj.get("recent_sources", [])
        return {
            "project_id": project_id,
            "facts_redacted": facts,
            "updated_at": data.get("updated_at", ""),
        }

    # ── Task plans ────────────────────────────────────────────────────

    def save_task_plan(
        self,
        plan_id: str,
        session_id: str,
        goal: str,
        steps_json: str,
        status: str = "active",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan = {
            "type": "task_plan",
            "plan_id": plan_id,
            "session_id": session_id,
            "goal": goal,
            "steps": steps_json,
            "status": status,
            "metadata": json.dumps(metadata or {}, ensure_ascii=False),
        }
        self._append_line(session_id, plan)
        return {
            "plan_id": plan_id,
            "session_id": session_id,
            "goal": goal,
            "steps_json": steps_json,
            "status": status,
            "created_at": plan.get("timestamp", ""),
            "updated_at": plan.get("timestamp", ""),
            "metadata_json": plan["metadata"],
        }

    def load_task_plan(self, plan_id: str) -> dict[str, Any] | None:
        for sid in self._cache:
            lines = self._ensure_loaded(sid)
            for l in reversed(lines):
                if l.get("type") == "task_plan" and l.get("plan_id") == plan_id:
                    return {
                        "plan_id": l.get("plan_id", ""),
                        "session_id": l.get("session_id", ""),
                        "goal": l.get("goal", ""),
                        "steps_json": l.get("steps", "[]"),
                        "status": l.get("status", "active"),
                        "created_at": l.get("timestamp", ""),
                        "updated_at": l.get("timestamp", ""),
                        "metadata_json": l.get("metadata", "{}"),
                    }
        return None

    def load_active_plan(self, session_id: str) -> dict[str, Any] | None:
        lines = self._ensure_loaded(session_id)
        for l in reversed(lines):
            if l.get("type") == "task_plan" and l.get("status") == "active":
                return {
                    "plan_id": l.get("plan_id", ""),
                    "session_id": l.get("session_id", ""),
                    "goal": l.get("goal", ""),
                    "steps_json": l.get("steps", "[]"),
                    "status": l.get("status", "active"),
                    "created_at": l.get("timestamp", ""),
                    "updated_at": l.get("timestamp", ""),
                    "metadata_json": l.get("metadata", "{}"),
                }
        return None

    def list_task_plans(self, session_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        if session_id:
            lines = self._ensure_loaded(session_id)
            plans = [l for l in lines if l.get("type") == "task_plan"]
        else:
            plans = []
            for sid in list(self._cache.keys()):
                lines = self._ensure_loaded(sid)
                plans.extend(l for l in lines if l.get("type") == "task_plan")
        plans.sort(key=lambda p: p.get("timestamp", ""), reverse=True)
        return [
            {
                "plan_id": p.get("plan_id", ""),
                "session_id": p.get("session_id", ""),
                "goal": p.get("goal", ""),
                "steps_json": p.get("steps", "[]"),
                "status": p.get("status", "active"),
                "created_at": p.get("timestamp", ""),
                "updated_at": p.get("timestamp", ""),
                "metadata_json": p.get("metadata", "{}"),
            }
            for p in plans[:max(1, int(limit))]
        ]

    def update_task_plan(self, plan_id: str, *, steps_json: str | None = None, status: str | None = None) -> dict[str, Any] | None:
        record = self.load_task_plan(plan_id)
        if record is None:
            return None
        session_id = record["session_id"]
        new_steps = steps_json if steps_json is not None else record["steps_json"]
        new_status = status if status is not None else record["status"]
        plan = {
            "type": "task_plan",
            "plan_id": plan_id,
            "session_id": session_id,
            "goal": record["goal"],
            "steps": new_steps,
            "status": new_status,
            "metadata": record.get("metadata_json", "{}"),
        }
        self._append_line(session_id, plan)
        record["steps_json"] = new_steps
        record["status"] = new_status
        record["updated_at"] = plan.get("timestamp", "")
        return record

    # ── Compatibility: save_final_answer ──────────────────────────────

    def save_final_answer(self, session_id: str, turn_id: str, answer: str) -> None:
        self.append_message(
            session_id, "assistant", answer,
            turn_id=turn_id, metadata={"kind": "final_answer"},
        )
        self._append_line(session_id, {
            "type": "turn",
            "event": "final_answer",
            "turn_id": turn_id,
            "output_summary": redact_text_for_persistence(answer[:1200]),
        })
        self._touch_sidecar(session_id)

    # ── Batch-remap helpers for ContextStore hydration ────────────────

    def get_recent_turns(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        lines = self._ensure_loaded(session_id)
        # Collect all turn events, merge by turn_id
        turn_data: dict[str, dict[str, Any]] = {}
        for l in lines:
            if l.get("type") != "turn":
                continue
            tid = l.get("turn_id", "")
            if tid not in turn_data:
                turn_data[tid] = {
                    "turn_id": tid,
                    "thread_id": session_id,
                    "input_redacted": "",
                    "output_summary_redacted": "",
                    "output_type": "",
                    "stop_reason": None,
                    "created_at": l.get("timestamp", ""),
                    "metadata": {"status": "", "skills_used": []},
                }
            entry = turn_data[tid]
            event = l.get("event", "")
            if event == "start":
                entry["metadata"]["status"] = l.get("status", "")
            elif event in ("end", "final_answer"):
                entry["input_redacted"] = l.get("input", "") or entry["input_redacted"]
                entry["output_summary_redacted"] = l.get("output_summary", "") or entry["output_summary_redacted"]
                entry["output_type"] = l.get("output_type", "") or entry["output_type"]
                entry["stop_reason"] = l.get("stop_reason") or entry["stop_reason"]
                entry["metadata"]["status"] = l.get("status", "") or entry["metadata"]["status"]
                entry["metadata"]["skills_used"] = l.get("skills_used", []) or entry["metadata"]["skills_used"]
            elif event == "status_change":
                entry["metadata"]["status"] = l.get("status", "")
        recent = list(turn_data.values())[-max(1, int(limit)):]
        return recent

    def load_turns(self, session_id: str, limit: int = 40) -> list[dict[str, Any]]:
        return self.get_recent_turns(session_id, limit=limit)

    # ── Typed memory stubs (delegated to MemoryStore in Phase 2) ─────

    # ── Backward-compat aliases (old ThreadStore API) ──────────────────

    def create_thread(self, title: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        sid = _uid("thread_")
        data = self._load_sidecar(sid)
        data["title"] = title
        data["created_at"] = _now()
        data["updated_at"] = _now()
        data["project_id"] = (metadata or {}).get("project_id")
        self._save_sidecar(sid)
        return {
            "thread_id": sid,
            "title": title,
            "created_at": data["created_at"],
            "updated_at": data["updated_at"],
            "metadata": dict(metadata or {}),
        }

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        return self.get_session(thread_id)

    def list_threads(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_sessions(limit=limit)

    def schema_version(self) -> int:
        return 3  # JSONL-based, no SQLite schema

    def append_turn(self, session_id: str, agent_result, user_input: str | None = None) -> dict[str, Any]:
        return self.end_turn(session_id, agent_result, user_input=user_input)

    def append_skill_observation(self, session_id: str, observation, *, turn_id: str | None = None) -> dict[str, Any]:
        return self.append_skill_obs(session_id, observation, turn_id=turn_id)

    def append_research_observation(self, session_id: str, observation, *, turn_id: str | None = None) -> dict[str, Any]:
        return self.append_research_obs(session_id, observation, turn_id=turn_id)

    def save_handoff_summary(self, session_id: str, handoff) -> None:
        self.save_handoff(session_id, handoff)

    def get_skill_observations(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return self.get_skill_obs(session_id, limit=limit)

    def get_research_observations(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return self.get_research_obs(session_id, limit=limit)

    def get_handoff_summary(self, session_id: str) -> dict[str, Any] | None:
        return self.get_handoff(session_id)

    def append_approval_audit(self, session_id: str, turn_id: str | None, approval) -> dict[str, Any]:
        return self.append_approval(session_id, approval, turn_id=turn_id)

    def get_approval_audits(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self.get_approvals(session_id, limit=limit)

    @property
    def db_path(self) -> Path:
        """Compatibility: some callers pass this to MemoryStore. Returns sessions dir."""
        return self.sessions_dir
