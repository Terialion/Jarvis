"""Compatibility wrapper around the Phase 17 durable ThreadStore."""

from __future__ import annotations

from pathlib import Path

from ..store.thread_store import ThreadStore as DurableThreadStore


class ThreadStore(DurableThreadStore):
    """Backwards-compatible alias used by AgentLoop and ContextBuilder."""

    def __init__(self, root: str | Path | None = None) -> None:
        if root is not None:
            root_path = Path(root)
            if root_path.suffix.lower() == ".db":
                db_path = root_path
            else:
                db_path = root_path / "jarvis.db"
        else:
            db_path = None
        super().__init__(db_path=db_path)

    def append_message(self, *args, **kwargs):
        metadata = kwargs.get("metadata")
        if len(args) >= 4:
            session_id, turn_id, role, content = args[:4]
            return super().append_message(str(session_id), str(role), str(content), turn_id=str(turn_id), metadata=metadata)
        if len(args) >= 3:
            session_id, role, content = args[:3]
            turn_id = kwargs.get("turn_id")
            return super().append_message(str(session_id), str(role), str(content), turn_id=str(turn_id) if turn_id else None, metadata=metadata)
        raise TypeError("append_message expects either (session_id, turn_id, role, content) or (session_id, role, content, *, turn_id=...)")
