from __future__ import annotations

from .store import PersistentMemoryStore


class MemoryRetriever:
    def __init__(self, store: PersistentMemoryStore) -> None:
        self.store = store

    def recall(self, *, memory_type: str | None = None, key: str | None = None, limit: int = 10) -> list[dict]:
        rows = self.store.read(memory_type=memory_type, key=key)
        return rows[-max(1, limit) :]

    def retrieve(self, project_id: str | None = None, query: str = "") -> list[dict]:
        rows = self.store.read()
        q = (query or "").strip().lower()
        out: list[dict] = []
        for row in rows:
            if project_id and str(row.get("project_id") or "") != project_id:
                continue
            if q:
                hay = " ".join(
                    [
                        str(row.get("key") or "").lower(),
                        str(row.get("value") or "").lower(),
                        str(row.get("memory_type") or "").lower(),
                    ]
                )
                if q not in hay:
                    continue
            out.append(row)
        return out
