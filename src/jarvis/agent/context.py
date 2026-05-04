"""Context assembly for agent turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.memory.retriever import MemoryRetriever
from ..core.memory.store import PersistentMemoryStore
from ..core.react_readiness.context_compactor import ContextCompactor, CompactionConfig
from ..core.react_readiness.context_manager import SessionContextManager
from .store import ThreadStore
from .types import ChatInput, ToolSpec


@dataclass
class MessageHistory:
    messages: list[dict[str, Any]] = field(default_factory=list)

    def append(self, role: str, content: str, **extra: Any) -> None:
        row = {"role": role, "content": content}
        row.update(extra)
        self.messages.append(row)


class ContextCompactorAdapter:
    """Adapter over existing ContextCompactor and context manager primitives."""

    def __init__(self, *, max_tokens: int = 12000) -> None:
        self.max_tokens = max_tokens
        self.session_context = SessionContextManager()
        # Existing readiness compactor budgets by characters, not tokens.
        self.compactor = ContextCompactor(CompactionConfig(max_chars_budget=max_tokens * 4))

    @staticmethod
    def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
        chars = sum(len(str(m.get("content") or "")) for m in messages)
        return max(1, chars // 4)

    def compact_if_needed(self, session_id: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._estimate_tokens(messages) <= self.max_tokens:
            return messages
        # For v0.1 we do deterministic tail compaction and keep a local compaction marker.
        head = messages[:2]
        tail = messages[-18:]
        compacted = head + [{"role": "system", "content": "[context compacted: middle turns omitted for token budget]"}] + tail
        return compacted


class ContextBuilder:
    """Build model messages from persisted history + memory + tool schemas."""

    def __init__(
        self,
        *,
        thread_store: ThreadStore,
        memory_store: PersistentMemoryStore | None = None,
        memory_retriever: MemoryRetriever | None = None,
        compactor: ContextCompactorAdapter | None = None,
        max_history_messages: int = 40,
    ) -> None:
        self.thread_store = thread_store
        self.memory_store = memory_store or PersistentMemoryStore()
        self.memory_retriever = memory_retriever or MemoryRetriever(self.memory_store)
        self.compactor = compactor or ContextCompactorAdapter()
        self.max_history_messages = max_history_messages

    def build_messages(
        self,
        *,
        session_id: str,
        chat_input: ChatInput,
        tool_specs: list[ToolSpec],
    ) -> list[dict[str, Any]]:
        system_prompt = self._build_system_prompt(chat_input, tool_specs)
        history_rows = self.thread_store.load_messages(session_id=session_id, limit=self.max_history_messages)

        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        memory_rows = self._recall_memory(chat_input)
        if memory_rows:
            messages.append(
                {
                    "role": "system",
                    "content": "Memory recall:\n" + "\n".join(memory_rows),
                }
            )

        for row in history_rows:
            role = str(row.get("role") or "user")
            content = str(row.get("content") or "")
            if not content:
                continue
            messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": chat_input.text})
        return self.compactor.compact_if_needed(session_id, messages)

    def _recall_memory(self, chat_input: ChatInput) -> list[str]:
        query = str(chat_input.text or "").strip()
        if not query:
            return []
        rows = self.memory_retriever.retrieve(project_id=chat_input.project_id, query=query)
        out: list[str] = []
        for item in rows[:5]:
            key = str(item.get("key") or "")
            value = str(item.get("value") or "")
            if key or value:
                out.append(f"- {key}: {value[:280]}")
        return out

    @staticmethod
    def _build_system_prompt(chat_input: ChatInput, tool_specs: list[ToolSpec]) -> str:
        tool_lines = []
        for spec in tool_specs:
            tool_lines.append(
                f"- {spec.name}: {spec.description} "
                f"(risk={spec.risk_level}, approval={spec.requires_approval})"
            )
        cwd = chat_input.cwd or "."
        project = chat_input.project_id or "default_project"
        return (
            "You are Jarvis AgentLoop. "
            "Use tool calls when needed, otherwise answer directly.\n"
            "Always respect safety and approval boundaries.\n"
            f"Project: {project}\n"
            f"CWD: {cwd}\n"
            "Available tools:\n"
            + ("\n".join(tool_lines) if tool_lines else "- <none>")
        )
