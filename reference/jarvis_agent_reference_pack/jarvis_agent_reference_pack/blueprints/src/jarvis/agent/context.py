"""Thread persistence and context assembly for AgentLoop."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from .types import ChatInput, ChatMessage, ToolSpec


class JsonlThreadStore:
    def __init__(self, root: str | Path = "data/agent_threads") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve_thread_id(self, chat_input: ChatInput) -> str:
        return chat_input.thread_id or f"thread_{uuid4().hex[:12]}"

    def _path(self, thread_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in thread_id)
        return self.root / f"{safe}.jsonl"

    def append(self, thread_id: str, message: ChatMessage) -> None:
        with self._path(thread_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(message), ensure_ascii=False) + "\n")

    def load(self, thread_id: str, limit: int = 80) -> list[ChatMessage]:
        path = self._path(thread_id)
        if not path.exists():
            return []
        rows = path.read_text(encoding="utf-8").splitlines()[-limit:]
        messages: list[ChatMessage] = []
        for row in rows:
            try:
                data = json.loads(row)
                messages.append(ChatMessage(**data))
            except Exception:
                continue
        return messages


class ContextBuilder:
    def __init__(self, thread_store: JsonlThreadStore, max_history_messages: int = 40) -> None:
        self.thread_store = thread_store
        self.max_history_messages = max_history_messages

    def build_messages(
        self,
        *,
        thread_id: str,
        chat_input: ChatInput,
        tools: Iterable[ToolSpec],
        extra_system: str | None = None,
    ) -> list[ChatMessage]:
        history = self.thread_store.load(thread_id, limit=self.max_history_messages)
        system = extra_system or self._default_system_prompt(tools)
        return [ChatMessage(role="system", content=system), *history, ChatMessage(role="user", content=chat_input.text)]

    @staticmethod
    def _default_system_prompt(tools: Iterable[ToolSpec]) -> str:
        tool_lines = [f"- {t.name}: {t.description}" for t in tools]
        return (
            "You are Jarvis, a local coding and research assistant. "
            "Use tools only when they help. After a tool result, continue reasoning and answer.\n\n"
            "Available tools:\n" + "\n".join(tool_lines[:80])
        )
