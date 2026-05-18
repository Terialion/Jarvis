from __future__ import annotations

from typing import Any


class MemoryRetriever:
    """Retrieve typed memory records from MemoryStore (now pure Markdown)."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def recall(
        self,
        *,
        memory_type: str | None = None,
        key: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        records = self._store.get_typed(memory_type=memory_type, limit=limit)
        out: list[dict[str, Any]] = []
        for r in records:
            r_key = r.get("key", "")
            if key and r_key != key:
                continue
            out.append(dict(r))
        return out[-max(1, limit):]

    def retrieve(
        self,
        project_id: str | None = None,
        query: str = "",
    ) -> list[dict[str, Any]]:
        q = (query or "").strip().lower()
        if not q:
            records = self._store.get_typed(limit=20)
        else:
            records = self._store.search(q, limit=20)
        out: list[dict[str, Any]] = []
        for r in records:
            r_proj = str(r.get("project_id") or "").strip()
            if project_id and r_proj and r_proj != str(project_id):
                continue
            out.append({
                "key": r.get("key", ""),
                "value": r.get("value_redacted", r.get("value", "")),
                "memory_type": r.get("memory_type", ""),
                "memory_id": r.get("memory_id", ""),
            })
        return out
