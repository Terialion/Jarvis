"""SQLite-backed durable ThreadStore for Phase 17."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..agent.skill_context import ActiveTaskState, HandoffSummary, SkillObservation
from ..agent.types import AgentRunResult, AgentTurn, ChatInput
from ..core.policy.approval import ApprovalRequest, ApprovalResponse
from ..web.research_context import ResearchObservation
from .redaction import redact_for_persistence, redact_text_for_persistence
from .schema import (
    SCHEMA_VERSION,
    ActiveTaskStateRecord,
    ApprovalAuditRecord,
    HandoffSummaryRecord,
    MessageRecord,
    ProjectFactsRecord,
    ResearchObservationRecord,
    SkillObservationRecord,
    ThreadRecord,
    ToolCallRecord,
    TurnRecord,
    UserMemoryRecord,
    ProjectMemoryRecord,
    utc_now,
)


class ThreadStoreError(RuntimeError):
    """Structured persistence failure."""


def _json_dumps(value: Any) -> str:
    return json.dumps(redact_for_persistence(value), ensure_ascii=False)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


class ThreadStore:
    """Durable session/thread persistence with compatibility helpers."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or self._default_db_path()).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @property
    def root(self) -> Path:
        return self.db_path.parent

    @staticmethod
    def _default_db_path() -> Path:
        current_test = os.environ.get("PYTEST_CURRENT_TEST")
        if current_test:
            safe = "".join(ch if ch.isalnum() else "_" for ch in current_test)[:80] or "pytest"
            return Path(tempfile.gettempdir()) / "jarvis_pytest_state" / safe / "jarvis.db"
        return Path(".jarvis/state/jarvis.db")

    def initialize(self) -> None:
        try:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS threads (
                        thread_id TEXT PRIMARY KEY,
                        title TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS turns (
                        turn_id TEXT PRIMARY KEY,
                        thread_id TEXT NOT NULL,
                        input_redacted TEXT NOT NULL,
                        output_summary_redacted TEXT NOT NULL,
                        output_type TEXT NOT NULL,
                        stop_reason TEXT,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS messages (
                        message_id TEXT PRIMARY KEY,
                        thread_id TEXT NOT NULL,
                        turn_id TEXT,
                        role TEXT NOT NULL,
                        content_redacted TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS summaries (
                        summary_id TEXT PRIMARY KEY,
                        thread_id TEXT NOT NULL,
                        turn_id TEXT,
                        summary_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS tool_calls (
                        call_id TEXT PRIMARY KEY,
                        thread_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        tool_name TEXT NOT NULL,
                        args_json TEXT NOT NULL,
                        result_json TEXT,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS skill_observations (
                        observation_id TEXT PRIMARY KEY,
                        thread_id TEXT NOT NULL,
                        turn_id TEXT,
                        skill_name TEXT NOT NULL,
                        summary_redacted TEXT NOT NULL,
                        related_files_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS research_observations (
                        observation_id TEXT PRIMARY KEY,
                        thread_id TEXT NOT NULL,
                        turn_id TEXT,
                        query_redacted TEXT NOT NULL,
                        sources_json TEXT NOT NULL,
                        evidence_json TEXT NOT NULL,
                        answer_summary_redacted TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        created_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS approval_audits (
                        approval_id TEXT PRIMARY KEY,
                        thread_id TEXT,
                        turn_id TEXT,
                        tool_name TEXT NOT NULL,
                        arguments_preview_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        decision TEXT,
                        reason_redacted TEXT,
                        created_at TEXT NOT NULL,
                        decided_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS active_tasks (
                        thread_id TEXT PRIMARY KEY,
                        summary_redacted TEXT NOT NULL,
                        related_files_json TEXT NOT NULL,
                        remaining_work_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS handoff_summaries (
                        thread_id TEXT PRIMARY KEY,
                        summary_redacted TEXT NOT NULL,
                        risks_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS project_facts (
                        project_id TEXT PRIMARY KEY,
                        facts_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS user_memory (
                        key TEXT PRIMARY KEY,
                        value_redacted TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS project_memory (
                        project_id TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value_redacted TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (project_id, key)
                    );
                    """
                )
                conn.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                    ("schema_version", str(SCHEMA_VERSION)),
                )
                conn.commit()
        except sqlite3.DatabaseError as exc:
            raise ThreadStoreError(f"thread_store_initialize_failed:{type(exc).__name__}") from exc

    def schema_version(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if row is None:
                return 0
            try:
                return int(row["value"])
            except Exception:
                return 0

    def create_thread(self, title: str | None = None, metadata: dict[str, Any] | None = None) -> ThreadRecord:
        record = ThreadRecord(thread_id=f"thread_{uuid4().hex[:12]}", title=title, metadata=dict(metadata or {}))
        self._upsert_thread(record)
        return record

    def get_thread(self, thread_id: str) -> ThreadRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM threads WHERE thread_id=?", (thread_id,)).fetchone()
        return self._thread_from_row(row) if row else None

    def list_threads(self, limit: int = 50) -> list[ThreadRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM threads ORDER BY updated_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [self._thread_from_row(row) for row in rows]

    def append_turn(self, thread_id: str, agent_result: AgentRunResult, user_input: str | None = None) -> TurnRecord:
        summary_human = str((agent_result.summary or {}).get("human") or agent_result.final_answer or "")[:1200]
        record = TurnRecord(
            turn_id=str(agent_result.turn_id),
            thread_id=thread_id,
            input_redacted=redact_text_for_persistence(user_input or ""),
            output_summary_redacted=redact_text_for_persistence(summary_human),
            output_type=str(agent_result.output_type),
            stop_reason=str(agent_result.stop_reason or ""),
            metadata={
                "status": agent_result.status,
                "skills_used": list(agent_result.skills_used or []),
                "tool_calls_count": len(agent_result.tool_calls or []),
                "events_count": len(agent_result.events or []),
            },
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO turns
                (turn_id, thread_id, input_redacted, output_summary_redacted, output_type, stop_reason, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.turn_id,
                    record.thread_id,
                    record.input_redacted,
                    record.output_summary_redacted,
                    record.output_type,
                    record.stop_reason,
                    record.created_at,
                    _json_dumps(record.metadata),
                ),
            )
            self._touch_thread(conn, thread_id)
            conn.commit()
        return record

    def append_message(self, thread_id: str, role: str, content: str, turn_id: str | None = None, metadata: dict[str, Any] | None = None) -> MessageRecord:
        record = MessageRecord(
            message_id=f"msg_{uuid4().hex[:12]}",
            thread_id=thread_id,
            turn_id=turn_id,
            role=role,
            content_redacted=redact_text_for_persistence(content),
            metadata=dict(redact_for_persistence(metadata or {})),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages(message_id, thread_id, turn_id, role, content_redacted, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.message_id,
                    record.thread_id,
                    record.turn_id,
                    record.role,
                    record.content_redacted,
                    record.created_at,
                    _json_dumps(record.metadata),
                ),
            )
            self._touch_thread(conn, thread_id)
            conn.commit()
        return record

    def append_tool_call(self, thread_id: str, turn_id: str, tool_call: dict[str, Any]) -> ToolCallRecord:
        record = ToolCallRecord(
            call_id=str(tool_call.get("id") or tool_call.get("call_id") or f"call_{uuid4().hex[:12]}"),
            thread_id=thread_id,
            turn_id=turn_id,
            tool_name=str(tool_call.get("name") or ""),
            args_redacted=redact_for_persistence(dict(tool_call.get("arguments") or {})),
            result_redacted=None,
            status="requested",
        )
        self._upsert_tool_call(record)
        return record

    def append_tool_result(self, thread_id: str, turn_id: str, tool_result: dict[str, Any]) -> ToolCallRecord:
        record = ToolCallRecord(
            call_id=str(tool_result.get("call_id") or f"call_{uuid4().hex[:12]}"),
            thread_id=thread_id,
            turn_id=turn_id,
            tool_name=str(tool_result.get("name") or ""),
            args_redacted={},
            result_redacted=redact_for_persistence(tool_result),
            status="completed" if bool(tool_result.get("ok")) else "failed",
        )
        self._upsert_tool_call(record)
        return record

    def append_skill_observation(self, thread_id: str, observation: SkillObservation, *, turn_id: str | None = None) -> SkillObservationRecord:
        record = SkillObservationRecord(
            observation_id=f"skillobs_{uuid4().hex[:12]}",
            thread_id=thread_id,
            turn_id=turn_id,
            skill_name=observation.skill_name,
            summary_redacted=redact_text_for_persistence(observation.summary),
            related_files=[str(x) for x in observation.related_files],
            created_at=observation.created_at,
            metadata=redact_for_persistence({"facts": observation.facts, "tool_calls": observation.tool_calls}),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO skill_observations
                (observation_id, thread_id, turn_id, skill_name, summary_redacted, related_files_json, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.observation_id,
                    record.thread_id,
                    record.turn_id,
                    record.skill_name,
                    record.summary_redacted,
                    _json_dumps(record.related_files),
                    record.created_at,
                    _json_dumps(record.metadata),
                ),
            )
            self._touch_thread(conn, thread_id)
            conn.commit()
        return record

    def append_research_observation(self, thread_id: str, observation: ResearchObservation, *, turn_id: str | None = None) -> ResearchObservationRecord:
        record = ResearchObservationRecord(
            observation_id=f"researchobs_{uuid4().hex[:12]}",
            thread_id=thread_id,
            turn_id=turn_id,
            query_redacted=redact_text_for_persistence(observation.query),
            sources_redacted=list(redact_for_persistence(observation.sources)),
            evidence_redacted=list(redact_for_persistence(observation.evidence)),
            answer_summary_redacted=redact_text_for_persistence(observation.answer_summary),
            confidence=float(observation.confidence),
            created_at=observation.created_at,
            metadata=redact_for_persistence({"search_tasks": observation.search_tasks, "remaining_questions": observation.remaining_questions}),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO research_observations
                (observation_id, thread_id, turn_id, query_redacted, sources_json, evidence_json, answer_summary_redacted, confidence, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.observation_id,
                    record.thread_id,
                    record.turn_id,
                    record.query_redacted,
                    _json_dumps(record.sources_redacted),
                    _json_dumps(record.evidence_redacted),
                    record.answer_summary_redacted,
                    record.confidence,
                    record.created_at,
                    _json_dumps(record.metadata),
                ),
            )
            self._touch_thread(conn, thread_id)
            conn.commit()
        return record

    def append_approval_audit(
        self,
        thread_id: str | None,
        turn_id: str | None,
        approval: ApprovalRequest | ApprovalResponse | dict[str, Any],
    ) -> ApprovalAuditRecord:
        raw = approval.to_dict() if hasattr(approval, "to_dict") else dict(approval)
        record = ApprovalAuditRecord(
            approval_id=str(raw.get("approval_id") or f"approval_{uuid4().hex[:12]}"),
            thread_id=thread_id,
            turn_id=turn_id,
            tool_name=str(raw.get("tool_name") or ""),
            arguments_preview_redacted=redact_for_persistence(raw.get("arguments_preview") or raw.get("arguments_preview_redacted") or {}),
            status=str(raw.get("status") or raw.get("decision") or ""),
            decision=str(raw.get("decision") or "") or None,
            reason_redacted=redact_text_for_persistence(str(raw.get("reason") or "")) or None,
            created_at=str(raw.get("created_at") or utc_now()),
            decided_at=str(raw.get("decided_at") or "") or None,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO approval_audits
                (approval_id, thread_id, turn_id, tool_name, arguments_preview_json, status, decision, reason_redacted, created_at, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.approval_id,
                    record.thread_id,
                    record.turn_id,
                    record.tool_name,
                    _json_dumps(record.arguments_preview_redacted),
                    record.status,
                    record.decision,
                    record.reason_redacted,
                    record.created_at,
                    record.decided_at,
                ),
            )
            if thread_id:
                self._touch_thread(conn, thread_id)
            conn.commit()
        return record

    def save_active_task(self, thread_id: str, active_task: ActiveTaskState | None) -> None:
        if active_task is None:
            return
        record = ActiveTaskStateRecord(
            thread_id=thread_id,
            summary_redacted=redact_text_for_persistence(active_task.user_goal),
            related_files=[str(x) for x in active_task.related_files],
            remaining_work=[str(x) for x in active_task.remaining_work],
            metadata=redact_for_persistence(active_task.to_dict()),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO active_tasks(thread_id, summary_redacted, related_files_json, remaining_work_json, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.thread_id,
                    record.summary_redacted,
                    _json_dumps(record.related_files),
                    _json_dumps(record.remaining_work),
                    record.updated_at,
                    _json_dumps(record.metadata),
                ),
            )
            self._touch_thread(conn, thread_id)
            conn.commit()

    def save_handoff_summary(self, thread_id: str, handoff: HandoffSummary | None) -> None:
        if handoff is None:
            return
        record = HandoffSummaryRecord(
            thread_id=thread_id,
            summary_redacted=redact_text_for_persistence(handoff.current_state),
            risks=[str(x) for x in handoff.risks],
            metadata=redact_for_persistence(handoff.to_dict()),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO handoff_summaries(thread_id, summary_redacted, risks_json, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.thread_id,
                    record.summary_redacted,
                    _json_dumps(record.risks),
                    record.updated_at,
                    _json_dumps(record.metadata),
                ),
            )
            self._touch_thread(conn, thread_id)
            conn.commit()

    def save_project_facts(self, project_id: str | None, facts: dict[str, Any] | None) -> None:
        if not project_id or not facts:
            return
        record = ProjectFactsRecord(
            project_id=project_id,
            facts_redacted=[str(x) for x in list(redact_for_persistence(facts).get("recent_files") or []) + list(redact_for_persistence(facts).get("recent_sources") or [])],
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO project_facts(project_id, facts_json, updated_at) VALUES (?, ?, ?)",
                (record.project_id, _json_dumps(record.facts_redacted), record.updated_at),
            )
            conn.commit()

    def get_recent_turns(self, thread_id: str, limit: int = 10) -> list[TurnRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM turns WHERE thread_id=? ORDER BY created_at DESC LIMIT ?",
                (thread_id, max(1, int(limit))),
            ).fetchall()
        return [self._turn_from_row(row) for row in rows][::-1]

    def get_recent_messages(self, thread_id: str, limit: int = 20) -> list[MessageRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE thread_id=? ORDER BY created_at DESC LIMIT ?",
                (thread_id, max(1, int(limit))),
            ).fetchall()
        return [self._message_from_row(row) for row in rows][::-1]

    def get_tool_calls(self, thread_id: str, limit: int = 20) -> list[ToolCallRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tool_calls WHERE thread_id=? ORDER BY created_at DESC LIMIT ?",
                (thread_id, max(1, int(limit))),
            ).fetchall()
        return [
            ToolCallRecord(
                call_id=str(row["call_id"]),
                thread_id=str(row["thread_id"]),
                turn_id=str(row["turn_id"]),
                tool_name=str(row["tool_name"]),
                args_redacted=_json_loads(row["args_json"], {}),
                result_redacted=_json_loads(row["result_json"], None),
                status=str(row["status"]),
                created_at=str(row["created_at"]),
            )
            for row in rows[::-1]
        ]

    def get_skill_observations(self, thread_id: str, limit: int = 10) -> list[SkillObservationRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM skill_observations WHERE thread_id=? ORDER BY created_at DESC LIMIT ?",
                (thread_id, max(1, int(limit))),
            ).fetchall()
        return [self._skill_obs_from_row(row) for row in rows][::-1]

    def get_research_observations(self, thread_id: str, limit: int = 10) -> list[ResearchObservationRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_observations WHERE thread_id=? ORDER BY created_at DESC LIMIT ?",
                (thread_id, max(1, int(limit))),
            ).fetchall()
        return [self._research_obs_from_row(row) for row in rows][::-1]

    def get_active_task(self, thread_id: str) -> ActiveTaskStateRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM active_tasks WHERE thread_id=?", (thread_id,)).fetchone()
        if row is None:
            return None
        return ActiveTaskStateRecord(
            thread_id=str(row["thread_id"]),
            summary_redacted=str(row["summary_redacted"]),
            related_files=list(_json_loads(row["related_files_json"], [])),
            remaining_work=list(_json_loads(row["remaining_work_json"], [])),
            updated_at=str(row["updated_at"]),
            metadata=dict(_json_loads(row["metadata_json"], {})),
        )

    def get_handoff_summary(self, thread_id: str) -> HandoffSummaryRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM handoff_summaries WHERE thread_id=?", (thread_id,)).fetchone()
        if row is None:
            return None
        return HandoffSummaryRecord(
            thread_id=str(row["thread_id"]),
            summary_redacted=str(row["summary_redacted"]),
            risks=list(_json_loads(row["risks_json"], [])),
            updated_at=str(row["updated_at"]),
            metadata=dict(_json_loads(row["metadata_json"], {})),
        )

    def get_project_facts(self, project_id: str | None) -> ProjectFactsRecord | None:
        if not project_id:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM project_facts WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            return None
        return ProjectFactsRecord(
            project_id=str(row["project_id"]),
            facts_redacted=list(_json_loads(row["facts_json"], [])),
            updated_at=str(row["updated_at"]),
        )

    def get_approval_audits(self, thread_id: str, limit: int = 20) -> list[ApprovalAuditRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM approval_audits WHERE thread_id=? ORDER BY created_at DESC LIMIT ?",
                (thread_id, max(1, int(limit))),
            ).fetchall()
        return [self._approval_from_row(row) for row in rows][::-1]

    # Compatibility methods for existing AgentLoop / ContextBuilder
    def create_or_resume_session(self, chat_input: ChatInput) -> dict[str, Any]:
        session_id = str(chat_input.session_id or f"session_{uuid4().hex[:12]}")
        existing = self.get_thread(session_id)
        if existing is None:
            record = ThreadRecord(
                thread_id=session_id,
                title=(str(chat_input.text or "").strip()[:80] or None),
                metadata={"project_id": chat_input.project_id, "cwd": chat_input.cwd, "source": "agent_loop"},
            )
            self._upsert_thread(record)
        else:
            self._touch_thread_id(session_id)
        return {"session_id": session_id, "project_id": chat_input.project_id, "cwd": chat_input.cwd}

    def create_turn(self, session_id: str, *, status: str = "running", metadata: dict[str, Any] | None = None) -> AgentTurn:
        turn = AgentTurn(turn_id=f"turn_{uuid4().hex[:12]}", session_id=session_id, status=status, metadata=dict(metadata or {}))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO turns
                (turn_id, thread_id, input_redacted, output_summary_redacted, output_type, stop_reason, created_at, metadata_json)
                VALUES (?, ?, '', '', ?, '', ?, ?)
                """,
                (
                    turn.turn_id,
                    session_id,
                    status,
                    turn.created_at,
                    _json_dumps(turn.to_dict()),
                ),
            )
            self._touch_thread(conn, session_id)
            conn.commit()
        return turn

    def save_final_answer(self, session_id: str, turn_id: str, answer: str) -> None:
        self.append_message(session_id, "assistant", answer, turn_id=turn_id, metadata={"kind": "final_answer"})
        with self._connect() as conn:
            row = conn.execute("SELECT metadata_json FROM turns WHERE turn_id=?", (turn_id,)).fetchone()
            metadata = dict(_json_loads(row["metadata_json"], {})) if row else {}
            conn.execute(
                "UPDATE turns SET output_summary_redacted=?, metadata_json=? WHERE turn_id=?",
                (redact_text_for_persistence(answer[:1200]), _json_dumps(metadata), turn_id),
            )
            self._touch_thread(conn, session_id)
            conn.commit()

    def save_summary(self, session_id: str, turn_id: str, summary: dict[str, Any]) -> None:
        created_at = utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO summaries(summary_id, thread_id, turn_id, summary_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (f"sum_{uuid4().hex[:12]}", session_id, turn_id, _json_dumps(summary), created_at),
            )
            output_type = str((summary.get("machine") or {}).get("output_type") or "answer")
            stop_reason = str((summary.get("machine") or {}).get("stop_reason") or "")
            human = str(summary.get("human") or "")
            conn.execute(
                "UPDATE turns SET output_summary_redacted=?, output_type=?, stop_reason=? WHERE turn_id=?",
                (redact_text_for_persistence(human[:1200]), output_type, stop_reason, turn_id),
            )
            self._touch_thread(conn, session_id)
            conn.commit()

    def load_messages(self, session_id: str, limit: int = 40) -> list[dict[str, Any]]:
        return [
            {
                "message_id": row.message_id,
                "session_id": row.thread_id,
                "turn_id": row.turn_id,
                "role": row.role,
                "content": row.content_redacted,
                "metadata": row.metadata,
            }
            for row in self.get_recent_messages(session_id, limit=limit)
        ]

    def load_turns(self, session_id: str, limit: int = 40) -> list[dict[str, Any]]:
        return [row.to_dict() for row in self.get_recent_turns(session_id, limit=limit)]

    def load_summaries(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT summary_id, thread_id, turn_id, summary_json, created_at FROM summaries WHERE thread_id=? ORDER BY created_at DESC LIMIT ?",
                (session_id, max(1, int(limit))),
            ).fetchall()
        out = []
        for row in rows[::-1]:
            out.append(
                {
                    "summary_id": str(row["summary_id"]),
                    "session_id": str(row["thread_id"]),
                    "turn_id": str(row["turn_id"] or ""),
                    "summary": dict(_json_loads(row["summary_json"], {})),
                    "created_at": str(row["created_at"]),
                }
            )
        return out

    def load_last_session_id(self) -> str | None:
        threads = self.list_threads(limit=1)
        return threads[0].thread_id if threads else None

    def update_turn_status(self, session_id: str, turn: AgentTurn, status: str) -> AgentTurn:
        turn.status = status
        with self._connect() as conn:
            row = conn.execute("SELECT metadata_json FROM turns WHERE turn_id=?", (turn.turn_id,)).fetchone()
            metadata = dict(_json_loads(row["metadata_json"], {})) if row else {}
            metadata["status"] = status
            conn.execute("UPDATE turns SET output_type=?, metadata_json=? WHERE turn_id=?", (status, _json_dumps(metadata), turn.turn_id))
            self._touch_thread(conn, session_id)
            conn.commit()
        return turn

    # Internal helpers
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
        except sqlite3.DatabaseError:
            pass
        return conn

    def _touch_thread_id(self, thread_id: str) -> None:
        with self._connect() as conn:
            self._touch_thread(conn, thread_id)
            conn.commit()

    def _touch_thread(self, conn: sqlite3.Connection, thread_id: str) -> None:
        now = utc_now()
        conn.execute("UPDATE threads SET updated_at=? WHERE thread_id=?", (now, thread_id))

    def _upsert_thread(self, record: ThreadRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO threads(thread_id, title, created_at, updated_at, metadata_json) VALUES (?, ?, ?, ?, ?)",
                (record.thread_id, record.title, record.created_at, record.updated_at, _json_dumps(record.metadata)),
            )
            conn.commit()

    def _upsert_tool_call(self, record: ToolCallRecord) -> None:
        with self._connect() as conn:
            existing = conn.execute("SELECT args_json FROM tool_calls WHERE call_id=?", (record.call_id,)).fetchone()
            args_payload = record.args_redacted if record.args_redacted else _json_loads(existing["args_json"], {}) if existing else {}
            conn.execute(
                """
                INSERT OR REPLACE INTO tool_calls(call_id, thread_id, turn_id, tool_name, args_json, result_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.call_id,
                    record.thread_id,
                    record.turn_id,
                    record.tool_name,
                    _json_dumps(args_payload),
                    _json_dumps(record.result_redacted) if record.result_redacted is not None else None,
                    record.status,
                    record.created_at,
                ),
            )
            self._touch_thread(conn, record.thread_id)
            conn.commit()

    @staticmethod
    def _thread_from_row(row: sqlite3.Row) -> ThreadRecord:
        return ThreadRecord(
            thread_id=str(row["thread_id"]),
            title=str(row["title"]) if row["title"] is not None else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            metadata=dict(_json_loads(row["metadata_json"], {})),
        )

    @staticmethod
    def _turn_from_row(row: sqlite3.Row) -> TurnRecord:
        return TurnRecord(
            turn_id=str(row["turn_id"]),
            thread_id=str(row["thread_id"]),
            input_redacted=str(row["input_redacted"]),
            output_summary_redacted=str(row["output_summary_redacted"]),
            output_type=str(row["output_type"]),
            stop_reason=str(row["stop_reason"]) if row["stop_reason"] is not None else None,
            created_at=str(row["created_at"]),
            metadata=dict(_json_loads(row["metadata_json"], {})),
        )

    @staticmethod
    def _message_from_row(row: sqlite3.Row) -> MessageRecord:
        return MessageRecord(
            message_id=str(row["message_id"]),
            thread_id=str(row["thread_id"]),
            turn_id=str(row["turn_id"]) if row["turn_id"] is not None else None,
            role=str(row["role"]),
            content_redacted=str(row["content_redacted"]),
            created_at=str(row["created_at"]),
            metadata=dict(_json_loads(row["metadata_json"], {})),
        )

    @staticmethod
    def _skill_obs_from_row(row: sqlite3.Row) -> SkillObservationRecord:
        return SkillObservationRecord(
            observation_id=str(row["observation_id"]),
            thread_id=str(row["thread_id"]),
            turn_id=str(row["turn_id"]) if row["turn_id"] is not None else None,
            skill_name=str(row["skill_name"]),
            summary_redacted=str(row["summary_redacted"]),
            related_files=list(_json_loads(row["related_files_json"], [])),
            created_at=str(row["created_at"]),
            metadata=dict(_json_loads(row["metadata_json"], {})),
        )

    @staticmethod
    def _research_obs_from_row(row: sqlite3.Row) -> ResearchObservationRecord:
        return ResearchObservationRecord(
            observation_id=str(row["observation_id"]),
            thread_id=str(row["thread_id"]),
            turn_id=str(row["turn_id"]) if row["turn_id"] is not None else None,
            query_redacted=str(row["query_redacted"]),
            sources_redacted=list(_json_loads(row["sources_json"], [])),
            evidence_redacted=list(_json_loads(row["evidence_json"], [])),
            answer_summary_redacted=str(row["answer_summary_redacted"]),
            confidence=float(row["confidence"] or 0.0),
            created_at=str(row["created_at"]),
            metadata=dict(_json_loads(row["metadata_json"], {})),
        )

    @staticmethod
    def _approval_from_row(row: sqlite3.Row) -> ApprovalAuditRecord:
        return ApprovalAuditRecord(
            approval_id=str(row["approval_id"]),
            thread_id=str(row["thread_id"]) if row["thread_id"] is not None else None,
            turn_id=str(row["turn_id"]) if row["turn_id"] is not None else None,
            tool_name=str(row["tool_name"]),
            arguments_preview_redacted=_json_loads(row["arguments_preview_json"], {}),
            status=str(row["status"]),
            decision=str(row["decision"]) if row["decision"] is not None else None,
            reason_redacted=str(row["reason_redacted"]) if row["reason_redacted"] is not None else None,
            created_at=str(row["created_at"]),
            decided_at=str(row["decided_at"]) if row["decided_at"] is not None else None,
        )
