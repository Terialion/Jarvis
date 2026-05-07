"""Context assembly for agent turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.memory.retriever import MemoryRetriever
from .context_compactor import build_compaction_summary_prefix, micro_compact, should_auto_compact
from .store import ThreadStore
from ..store.memory_store import MemoryStore
from .types import (
    ChatInput,
    ContextPack,
    ConversationContext,
    MemoryContext,
    ProjectContext,
    SkillContext,
    TurnContext,
)


PROJECT_INSTRUCTION_FILES = ("AGENTS.md", "JARVIS.md", "README.md")


@dataclass
class MessageHistory:
    messages: list[dict[str, Any]] = field(default_factory=list)

    def append(self, role: str, content: str, **extra: Any) -> None:
        row = {"role": role, "content": content}
        row.update(extra)
        self.messages.append(row)


class ContextCompactorAdapter:
    """Compatibility wrapper that delegates to the Phase 8 compactor helpers."""

    def __init__(self, *, max_tokens: int = 12000) -> None:
        self.max_tokens = max_tokens

    @staticmethod
    def estimate_tokens(messages: list[dict[str, Any]]) -> int:
        chars = sum(len(str(m.get("content") or "")) for m in messages)
        return max(1, chars // 4)

    def compact_if_needed(self, session_id: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        _ = session_id
        return micro_compact(messages, max_messages=24)


class ContextBuilder:
    """Build a TurnContext from persisted history, memory, and skill metadata."""

    def __init__(
        self,
        *,
        thread_store: ThreadStore,
        memory_store: MemoryStore | None = None,
        memory_retriever: MemoryRetriever | None = None,
        compactor: ContextCompactorAdapter | None = None,
        skill_registry: Any | None = None,
        context_store: Any | None = None,
        model_info: dict[str, Any] | None = None,
        permission_mode: str = "workspace_write",
        max_history_messages: int = 40,
    ) -> None:
        self.thread_store = thread_store
        self.memory_store = memory_store or MemoryStore(thread_store.db_path)
        self.memory_retriever = memory_retriever or MemoryRetriever(self.memory_store)
        self.compactor = compactor or ContextCompactorAdapter()
        self.skill_registry = skill_registry
        self.context_store = context_store
        self.model_info = dict(model_info or {})
        self.permission_mode = permission_mode
        self.max_history_messages = max_history_messages

    def build(
        self,
        *,
        session_id: str,
        turn_id: str,
        chat_input: ChatInput,
        runtime_state: dict[str, Any] | None = None,
    ) -> TurnContext:
        state = dict(runtime_state or {})
        model_info = dict(self.model_info)
        model_info.update({k: v for k, v in state.items() if k in {"model_backend", "model_provider", "model_name"}})

        cwd_path = Path(chat_input.cwd or state.get("cwd") or ".").resolve()
        repo_root = self._discover_repo_root(cwd_path)
        project = self._build_project_context(cwd_path, repo_root)
        conversation = self._build_conversation_context(session_id, turn_id)
        memory = self._build_memory_context(chat_input)
        stored_context = self._load_stored_context(session_id)
        skills = self._build_skill_context(stored_context=stored_context)
        token_budget = {
            "history_messages": len(conversation.recent_messages),
            "estimated_history_tokens": self.compactor.estimate_tokens(conversation.recent_messages),
            "auto_compact_recommended": False,
        }
        pack = ContextPack(
            project=project,
            conversation=conversation,
            memory=memory,
            skills=skills,
            token_budget=token_budget,
            warnings=[],
        )
        if stored_context.get("handoff_summary"):
            pack.memory.short_term["handoff_summary"] = stored_context["handoff_summary"]
        if stored_context.get("project_facts"):
            pack.memory.short_term["project_facts"] = stored_context["project_facts"]
        pack.token_budget["auto_compact_recommended"] = should_auto_compact(pack)
        return TurnContext(
            user_input=chat_input.text,
            cwd=str(cwd_path),
            model_provider=str(model_info.get("model_provider") or "") or None,
            model_name=str(model_info.get("model_name") or "") or None,
            permission_mode=str(state.get("permission_mode") or self.permission_mode),
            context_pack=pack,
            model_backend=str(model_info.get("model_backend") or "") or None,
            project_id=chat_input.project_id,
            session_id=session_id,
            turn_id=turn_id,
        )

    def build_messages(
        self,
        *,
        session_id: str,
        turn_id: str,
        chat_input: ChatInput,
        tool_specs: list[Any] | None = None,
        runtime_state: dict[str, Any] | None = None,
        prompt_builder: Any | None = None,
    ) -> tuple[TurnContext, list[dict[str, Any]]]:
        _ = tool_specs
        turn_context = self.build(
            session_id=session_id,
            turn_id=turn_id,
            chat_input=chat_input,
            runtime_state=runtime_state,
        )
        if prompt_builder is None:
            from .prompt_builder import PromptBuilder

            prompt_builder = PromptBuilder()
        messages = prompt_builder.build_messages(turn_context)
        if should_auto_compact(turn_context.context_pack):
            messages = self.compactor.compact_if_needed(session_id, messages)
        return turn_context, messages

    def _build_project_context(self, cwd_path: Path, repo_root: Path | None) -> ProjectContext:
        root = repo_root or cwd_path
        files_hint: list[str] = []
        instructions_chunks: list[str] = []
        for name in PROJECT_INSTRUCTION_FILES:
            candidate = root / name
            if candidate.exists():
                files_hint.append(name)
                snippet = candidate.read_text(encoding="utf-8", errors="replace")[:1200].strip()
                if snippet:
                    instructions_chunks.append(f"[{name}]\n{snippet}")
        return ProjectContext(
            cwd=str(cwd_path),
            repo_root=str(root) if root else None,
            project_name=root.name if root else cwd_path.name,
            project_files_hint=files_hint,
            project_instructions="\n\n".join(instructions_chunks) if instructions_chunks else None,
        )

    def _build_conversation_context(self, session_id: str, turn_id: str) -> ConversationContext:
        rows = self.thread_store.load_messages(session_id=session_id, limit=self.max_history_messages)
        recent_messages: list[dict[str, Any]] = []
        for row in rows:
            role = str(row.get("role") or "").strip()
            content = str(row.get("content") or "")
            if not role or not content:
                continue
            recent_messages.append({"role": role, "content": content})
        summaries = self.thread_store.load_summaries(session_id=session_id, limit=1)
        compacted_summary = None
        if summaries:
            last_summary = dict(summaries[-1].get("summary") or {})
            human = str(last_summary.get("human") or "").strip()
            machine = dict(last_summary.get("machine") or {})
            compacted_summary = human or str(machine.get("handoff_summary") or "").strip() or None
            if compacted_summary:
                compacted_summary = build_compaction_summary_prefix(compacted_summary)
        return ConversationContext(
            thread_id=session_id,
            turn_id=turn_id,
            recent_messages=recent_messages,
            compacted_summary=compacted_summary,
        )

    def _build_memory_context(self, chat_input: ChatInput) -> MemoryContext:
        query = str(chat_input.text or "").strip()
        short_term: dict[str, Any] = {}
        project_id = str(chat_input.project_id or "").strip()
        user_memory = self.memory_store.get_user_memory()
        if user_memory:
            short_term["persistent_user_memory"] = {
                str(k): str(v)[:280] for k, v in list(user_memory.items())[:8]
            }
        if project_id:
            project_memory = self.memory_store.get_project_memory(project_id)
            if project_memory:
                short_term["persistent_project_memory"] = {
                    str(k): str(v)[:280] for k, v in list(project_memory.items())[:8]
                }
        if not query:
            return MemoryContext(short_term=short_term)
        rows = self.memory_retriever.retrieve(project_id=chat_input.project_id, query=query)
        long_term_refs: list[dict[str, Any]] = []
        for item in rows[:5]:
            key = str(item.get("key") or "").strip()
            value = str(item.get("value") or "").strip()
            if key and value:
                short_term[key] = value[:280]
                long_term_refs.append({"key": key, "value": value[:280]})
        return MemoryContext(short_term=short_term, long_term_refs=long_term_refs)

    def _build_skill_context(self, *, stored_context: dict[str, Any] | None = None) -> SkillContext:
        available: list[dict[str, Any]] = []
        if self.skill_registry is not None:
            try:
                available = list(self.skill_registry.export_index())
            except Exception:
                available = []
        stored_context = dict(stored_context or {})
        return SkillContext(
            available_skills=available,
            skill_observations=list(stored_context.get("skill_observations") or []),
            research_observations=list(stored_context.get("research_observations") or []),
            active_task=stored_context.get("active_task"),
        )

    def _load_stored_context(self, session_id: str) -> dict[str, Any]:
        if self.context_store is None:
            return {}
        try:
            return dict(self.context_store.retrieve_recent_context(session_id))
        except Exception:
            return {}

    @staticmethod
    def _discover_repo_root(cwd_path: Path) -> Path | None:
        candidates = [cwd_path, *cwd_path.parents]
        for candidate in candidates:
            if (candidate / ".git").exists():
                return candidate
        for candidate in candidates:
            if any((candidate / marker).exists() for marker in PROJECT_INSTRUCTION_FILES):
                return candidate
        return cwd_path


class ContextUpdater:
    """Minimal state updater for TurnContext after a completed turn."""

    def apply_result(self, turn_context: TurnContext, agent_result: Any) -> None:
        if turn_context.context_pack is None:
            return
        loaded = list(getattr(agent_result, "loaded_skills", []) or [])
        if loaded:
            turn_context.context_pack.skills.loaded_skills = list(dict.fromkeys(loaded))
        final_answer = str(getattr(agent_result, "final_answer", "") or "").strip()
        if final_answer:
            turn_context.context_pack.memory.short_term["last_final_answer"] = final_answer[:500]
