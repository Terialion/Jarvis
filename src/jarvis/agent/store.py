"""Compatibility wrapper that delegates to JSONL SessionStore."""

from __future__ import annotations

from pathlib import Path

from ..store.session_store import SessionStore


class ThreadStore(SessionStore):
    """Backward-compatible alias used by AgentLoop and ContextBuilder."""

    def __init__(self, root: str | Path | None = None) -> None:
        if root is not None:
            root_path = Path(root)
            if root_path.suffix.lower() == ".db":
                # Old .db path → use parent dir for sessions
                sessions_dir = root_path.parent / "sessions"
            else:
                sessions_dir = root_path
        else:
            sessions_dir = None
        super().__init__(sessions_dir=sessions_dir)

    def append_message(self, *args, **kwargs):
        metadata = kwargs.get("metadata")
        tool_call_id = kwargs.get("tool_call_id")
        if len(args) >= 4:
            session_id, turn_id, role, content = args[:4]
            return super().append_message(str(session_id), str(role), str(content), turn_id=str(turn_id), metadata=metadata, tool_call_id=tool_call_id)
        if len(args) >= 3:
            session_id, role, content = args[:3]
            turn_id = kwargs.get("turn_id")
            return super().append_message(str(session_id), str(role), str(content), turn_id=str(turn_id) if turn_id else None, metadata=metadata, tool_call_id=tool_call_id)
        raise TypeError("append_message expects either (session_id, turn_id, role, content) or (session_id, role, content, *, turn_id=...)")
