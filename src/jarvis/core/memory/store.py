"""
DEPRECATED — Use MemoryStore from jarvis.store.memory_store instead.

This legacy file-based JSON store is kept only for backward compatibility.
New code should use the SQLite-backed MemoryStore with FTS5 full-text search.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .write_policy import sanitize_memory_value


class PersistentMemoryStore:
    def __init__(self, file_path: str | None = None) -> None:
        self.file_path = Path(file_path or "temp/memory/memory_store.json").resolve()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_text("[]", encoding="utf-8")

    def write(self, record: dict[str, Any]) -> dict[str, Any]:
        allowed, sanitized = sanitize_memory_value(str(record.get("value") or ""))
        row = dict(record)
        row["value"] = sanitized
        row["secret_rejected"] = not allowed
        if not allowed:
            row["confidence"] = 0.0
            row["secret_source"] = "write_policy_redaction"
        data = self._read_all()
        data.append(row)
        self.file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "data": row}

    def read(self, *, memory_type: str | None = None, key: str | None = None) -> list[dict[str, Any]]:
        rows = self._read_all()
        out: list[dict[str, Any]] = []
        for r in rows:
            if memory_type and r.get("memory_type") != memory_type:
                continue
            if key and r.get("key") != key:
                continue
            out.append(r)
        return out

    def _read_all(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return []
