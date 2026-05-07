"""Durable user/project memory store backed by ThreadStore tables."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .redaction import redact_text_for_persistence
from .schema import ProjectMemoryRecord, UserMemoryRecord, utc_now
from .thread_store import ThreadStore


class MemoryStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.thread_store = ThreadStore(db_path=db_path)

    def get_user_memory(self) -> dict[str, str]:
        with self.thread_store._connect() as conn:
            rows = conn.execute("SELECT key, value_redacted FROM user_memory ORDER BY key ASC").fetchall()
        return {str(row["key"]): str(row["value_redacted"]) for row in rows}

    def set_user_memory(self, key: str, value: str) -> UserMemoryRecord:
        record = UserMemoryRecord(key=str(key), value_redacted=redact_text_for_persistence(value), updated_at=utc_now())
        with self.thread_store._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_memory(key, value_redacted, updated_at) VALUES (?, ?, ?)",
                (record.key, record.value_redacted, record.updated_at),
            )
            conn.commit()
        return record

    def delete_user_memory(self, key: str) -> None:
        with self.thread_store._connect() as conn:
            conn.execute("DELETE FROM user_memory WHERE key=?", (str(key),))
            conn.commit()

    def clear_user_memory(self) -> None:
        with self.thread_store._connect() as conn:
            conn.execute("DELETE FROM user_memory")
            conn.commit()

    def get_project_memory(self, project_id: str) -> dict[str, str]:
        with self.thread_store._connect() as conn:
            rows = conn.execute(
                "SELECT key, value_redacted FROM project_memory WHERE project_id=? ORDER BY key ASC",
                (str(project_id),),
            ).fetchall()
        return {str(row["key"]): str(row["value_redacted"]) for row in rows}

    def set_project_memory(self, project_id: str, key: str, value: str) -> ProjectMemoryRecord:
        record = ProjectMemoryRecord(
            project_id=str(project_id),
            key=str(key),
            value_redacted=redact_text_for_persistence(value),
            updated_at=utc_now(),
        )
        with self.thread_store._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO project_memory(project_id, key, value_redacted, updated_at) VALUES (?, ?, ?, ?)",
                (record.project_id, record.key, record.value_redacted, record.updated_at),
            )
            conn.commit()
        return record

    def delete_project_memory(self, project_id: str, key: str) -> None:
        with self.thread_store._connect() as conn:
            conn.execute("DELETE FROM project_memory WHERE project_id=? AND key=?", (str(project_id), str(key)))
            conn.commit()

    def clear_project_memory(self, project_id: str) -> None:
        with self.thread_store._connect() as conn:
            conn.execute("DELETE FROM project_memory WHERE project_id=?", (str(project_id),))
            conn.commit()

    # Compatibility helpers for existing MemoryRetriever/PersistentMemoryStore callers
    def write(self, record: dict[str, Any]) -> dict[str, Any]:
        memory_type = str(record.get("memory_type") or "user").strip().lower()
        key = str(record.get("key") or "").strip() or "memory"
        value = str(record.get("value") or "")
        project_id = str(record.get("project_id") or "").strip()
        if memory_type == "project" and project_id:
            saved = self.set_project_memory(project_id, key, value)
            row = {
                "memory_type": "project",
                "project_id": project_id,
                "key": saved.key,
                "value": saved.value_redacted,
            }
        else:
            saved = self.set_user_memory(key, value)
            row = {"memory_type": "user", "key": saved.key, "value": saved.value_redacted}
        return {"ok": True, "data": row}

    def read(self, *, memory_type: str | None = None, key: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if memory_type in {None, "user"}:
            for mem_key, value in self.get_user_memory().items():
                if key and mem_key != key:
                    continue
                rows.append({"memory_type": "user", "key": mem_key, "value": value})
        if memory_type in {None, "project"}:
            with self.thread_store._connect() as conn:
                query = "SELECT project_id, key, value_redacted FROM project_memory"
                params: tuple[Any, ...] = ()
                if key:
                    query += " WHERE key=?"
                    params = (key,)
                rows_db = conn.execute(query, params).fetchall()
            for row in rows_db:
                rows.append(
                    {
                        "memory_type": "project",
                        "project_id": str(row["project_id"]),
                        "key": str(row["key"]),
                        "value": str(row["value_redacted"]),
                    }
                )
        return rows
