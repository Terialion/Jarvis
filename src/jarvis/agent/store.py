"""JSONL persistence for agent sessions and turns."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from .types import AgentTurn, ChatInput


class ThreadStore:
    """Persist session/turn/message/summary records under data/agent_threads."""

    def __init__(self, root: str | Path = "data/agent_threads") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.sessions_file = self.root / "sessions.jsonl"

    def create_or_resume_session(self, chat_input: ChatInput) -> dict[str, Any]:
        session_id = chat_input.session_id or f"session_{uuid4().hex[:12]}"
        session_record = {
            "session_id": session_id,
            "project_id": chat_input.project_id,
            "cwd": chat_input.cwd,
            "created_by": "agent_loop",
            "metadata": dict(chat_input.metadata or {}),
        }
        if not self._session_exists(session_id):
            self._append_jsonl(self.sessions_file, session_record)
        self._ensure_session_dir(session_id)
        return session_record

    def create_turn(self, session_id: str, *, status: str = "running", metadata: dict[str, Any] | None = None) -> AgentTurn:
        turn = AgentTurn(
            turn_id=f"turn_{uuid4().hex[:12]}",
            session_id=session_id,
            status=status,
            metadata=dict(metadata or {}),
        )
        self._append_jsonl(self._turns_file(session_id), turn.to_dict())
        return turn

    def append_message(
        self,
        session_id: str,
        turn_id: str,
        role: str,
        content: str,
        *,
        name: str | None = None,
        tool_call_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message = {
            "message_id": f"msg_{uuid4().hex[:12]}",
            "session_id": session_id,
            "turn_id": turn_id,
            "role": role,
            "content": content,
            "name": name,
            "tool_call_id": tool_call_id,
            "metadata": dict(metadata or {}),
        }
        self._append_jsonl(self._messages_file(session_id), message)
        return message

    def append_tool_call(self, session_id: str, turn_id: str, tool_call: dict[str, Any]) -> None:
        self.append_message(
            session_id,
            turn_id,
            "assistant",
            content=json.dumps({"tool_call": tool_call}, ensure_ascii=False),
            metadata={"kind": "tool_call"},
        )

    def append_tool_result(self, session_id: str, turn_id: str, tool_result: dict[str, Any]) -> None:
        self.append_message(
            session_id,
            turn_id,
            "tool",
            content=json.dumps({"tool_result": tool_result}, ensure_ascii=False),
            tool_call_id=str(tool_result.get("call_id") or ""),
            metadata={"kind": "tool_result"},
        )

    def save_final_answer(self, session_id: str, turn_id: str, answer: str) -> None:
        self.append_message(
            session_id,
            turn_id,
            "assistant",
            content=answer,
            metadata={"kind": "final_answer"},
        )

    def save_summary(self, session_id: str, turn_id: str, summary: dict[str, Any]) -> None:
        record = {"summary_id": f"sum_{uuid4().hex[:12]}", "session_id": session_id, "turn_id": turn_id, "summary": summary}
        self._append_jsonl(self._summaries_file(session_id), record)

    def load_messages(self, session_id: str, limit: int = 40) -> list[dict[str, Any]]:
        rows = self._read_jsonl(self._messages_file(session_id))
        return rows[-limit:] if limit > 0 else rows

    def load_turns(self, session_id: str, limit: int = 40) -> list[dict[str, Any]]:
        rows = self._read_jsonl(self._turns_file(session_id))
        return rows[-limit:] if limit > 0 else rows

    def load_summaries(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._read_jsonl(self._summaries_file(session_id))
        return rows[-limit:] if limit > 0 else rows

    def load_last_session_id(self) -> str | None:
        rows = self._read_jsonl(self.sessions_file)
        if not rows:
            return None
        return str(rows[-1].get("session_id") or "")

    def update_turn_status(self, session_id: str, turn: AgentTurn, status: str) -> AgentTurn:
        turn.status = status
        turn.updated_at = turn.updated_at
        self._append_jsonl(self._turns_file(session_id), turn.to_dict())
        return turn

    def _ensure_session_dir(self, session_id: str) -> Path:
        path = self.root / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _turns_file(self, session_id: str) -> Path:
        return self._ensure_session_dir(session_id) / "turns.jsonl"

    def _messages_file(self, session_id: str) -> Path:
        return self._ensure_session_dir(session_id) / "messages.jsonl"

    def _summaries_file(self, session_id: str) -> Path:
        return self._ensure_session_dir(session_id) / "summaries.jsonl"

    def _session_exists(self, session_id: str) -> bool:
        for row in self._read_jsonl(self.sessions_file):
            if str(row.get("session_id")) == session_id:
                return True
        return False

    @staticmethod
    def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
        return rows

