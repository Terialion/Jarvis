"""Context assembly for agent turns."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.memory.retriever import MemoryRetriever
from ..core.tokens import TokenEstimator, get_context_window
from .context_compactor import (
    build_compaction_summary_prefix,
    compact,
    micro_compact,
    should_auto_compact,
)
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


PROJECT_INSTRUCTION_FILES = ("CLAUDE.md", "JARVIS.md", "AGENTS.md", "README.md")


@dataclass
class MessageHistory:
    messages: list[dict[str, Any]] = field(default_factory=list)

    def append(self, role: str, content: str, **extra: Any) -> None:
        row = {"role": role, "content": content}
        row.update(extra)
        self.messages.append(row)


class ContextCompactorAdapter:
    """Compatibility wrapper that delegates to the 5-stage compaction pipeline."""

    def __init__(self, *, max_tokens: int = 12000, model_name: str | None = None) -> None:
        self.max_tokens = max_tokens
        self.model_name = model_name

    @staticmethod
    def estimate_tokens(messages: list[dict[str, Any]]) -> int:
        return TokenEstimator().count_messages(messages)

    def compact_if_needed(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        *,
        model_client: Any = None,
    ) -> list[dict[str, Any]]:
        result, report = compact(
            messages,
            session_id=session_id,
            model_name=self.model_name,
            model_client=model_client,
        )
        if report.stage != "none":
            import logging
            logging.getLogger("jarvis.context").info(
                "Compaction: stage=%s tokens=%d→%d msgs=%d→%d",
                report.stage, report.tokens_before, report.tokens_after,
                report.messages_before, report.messages_after,
            )
        return result


class ContextBuilder:
    """Build a TurnContext from persisted history, memory, and skill metadata."""

    def __init__(
        self,
        *,
        session_store: Any = None,
        memory_store: MemoryStore | None = None,
        memory_retriever: MemoryRetriever | None = None,
        compactor: ContextCompactorAdapter | None = None,
        skill_registry: Any | None = None,
        context_store: Any | None = None,
        model_info: dict[str, Any] | None = None,
        permission_mode: str = "workspace_write",
        max_history_messages: int = 40,
    ) -> None:
        self.session_store = session_store
        self.memory_store = memory_store or MemoryStore()
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
        from ..core.debug_log import debug_log as _dbg, is_debug_enabled as _dbg_on

        _enabled = _dbg_on()
        state = dict(runtime_state or {})
        model_info = dict(self.model_info)
        model_info.update({k: v for k, v in state.items() if k in {"model_backend", "model_provider", "model_name"}})

        cwd_path = Path(chat_input.cwd or state.get("cwd") or ".").resolve()
        _t0 = time.perf_counter() if _enabled else 0
        repo_root = self._discover_repo_root(cwd_path)
        if _enabled:
            _dbg("context", f"_discover_repo_root done in {time.perf_counter()-_t0:.2f}s root={repo_root}")
        _t0 = time.perf_counter() if _enabled else 0
        project = self._build_project_context(cwd_path, repo_root, user_text=chat_input.text)
        if _enabled:
            _dbg("context", f"_build_project_context done in {time.perf_counter()-_t0:.2f}s files={project.project_files_hint}")
        _t0 = time.perf_counter() if _enabled else 0
        conversation = self._build_conversation_context(session_id, turn_id)
        if _enabled:
            _dbg("context", f"_build_conversation_context done in {time.perf_counter()-_t0:.2f}s msgs={len(conversation.recent_messages)} compacted={conversation.compacted_summary is not None}")
        _t0 = time.perf_counter() if _enabled else 0
        memory = self._build_memory_context(chat_input)
        if _enabled:
            _dbg("context", f"_build_memory_context done in {time.perf_counter()-_t0:.2f}s short_term_keys={list(memory.short_term.keys())}")
        _t0 = time.perf_counter() if _enabled else 0
        stored_context = self._load_stored_context(session_id)
        if _enabled:
            _dbg("context", f"_load_stored_context done in {time.perf_counter()-_t0:.2f}s keys={list(stored_context.keys())}")
        _t0 = time.perf_counter() if _enabled else 0
        skills = self._build_skill_context(stored_context=stored_context, session_id=session_id)
        if _enabled:
            _dbg("context", f"_build_skill_context done in {time.perf_counter()-_t0:.2f}s available_skills={len(skills.available_skills)}")
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
        from ..core.debug_log import debug_log as _dbg, is_debug_enabled as _dbg_on

        _enabled = _dbg_on()
        _ = tool_specs
        _t0 = time.perf_counter() if _enabled else 0
        turn_context = self.build(
            session_id=session_id,
            turn_id=turn_id,
            chat_input=chat_input,
            runtime_state=runtime_state,
        )
        if _enabled:
            _dbg("context", f"build() total done in {time.perf_counter()-_t0:.2f}s")
        if prompt_builder is None:
            from .prompt_builder import PromptBuilder

            prompt_builder = PromptBuilder()
        _t0 = time.perf_counter() if _enabled else 0
        messages = prompt_builder.build_messages(turn_context)
        if _enabled:
            _dbg("context", f"prompt_builder.build_messages done in {time.perf_counter()-_t0:.2f}s {len(messages)} messages")
        _t0 = time.perf_counter() if _enabled else 0
        if should_auto_compact(turn_context.context_pack):
            messages = self.compactor.compact_if_needed(session_id, messages)
            if _enabled:
                _dbg("context", f"compaction done in {time.perf_counter()-_t0:.2f}s")
        return turn_context, messages

    def _build_project_context(self, cwd_path: Path, repo_root: Path | None, user_text: str | None = None) -> ProjectContext:
        root = repo_root or cwd_path
        files_hint: list[str] = []
        instructions_chunks: list[str] = []
        seen_paths: set[str] = set()
        total_chars = 0
        MAX_TOTAL_CHARS = 32000  # Codex-style cap

        # 1. Global user instructions (~/.jarvis/JARVIS.md)
        global_jarvis = Path.home() / ".jarvis" / "JARVIS.md"
        if global_jarvis.exists():
            files_hint.append("~/.jarvis/JARVIS.md")
            snippet = global_jarvis.read_text(encoding="utf-8", errors="replace")[:2000].strip()
            if snippet:
                instructions_chunks.append("[global: ~/.jarvis/JARVIS.md]\n" + snippet)
                total_chars += len(snippet)

        # 2. Hierarchical loading from cwd up to repo_root (Claude Code-style, up to 4 levels)
        hierarchy_roots: list[Path] = []
        if repo_root:
            try:
                cwd_path.resolve().relative_to(repo_root.resolve())
                # cwd is inside repo — walk from cwd up to repo_root
                current = cwd_path.resolve()
                while current != repo_root.resolve().parent:
                    hierarchy_roots.append(current)
                    if current == repo_root.resolve():
                        break
                    current = current.parent
            except ValueError:
                # cwd is outside repo — just use cwd and repo_root
                hierarchy_roots = [cwd_path.resolve(), repo_root.resolve()]
        else:
            hierarchy_roots = [cwd_path.resolve()]

        # Limit to 4 levels (Claude Code pattern)
        hierarchy_roots = list(dict.fromkeys(hierarchy_roots))[:4]

        for directory in hierarchy_roots:
            for name in PROJECT_INSTRUCTION_FILES:
                candidate = directory / name
                if not candidate.exists():
                    continue
                resolved = str(candidate.resolve())
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                files_hint.append(f"{name} ({directory.name})" if directory != root else name)
                remaining = MAX_TOTAL_CHARS - total_chars
                if remaining <= 0:
                    break
                snippet = candidate.read_text(encoding="utf-8", errors="replace")[:remaining].strip()
                if snippet:
                    label = f"[{directory.name}/{name}]" if directory != root else f"[{name}]"
                    instructions_chunks.append(label + "\n" + snippet)
                    total_chars += len(snippet)

        # 3. Mentioned-directory injection: if the user names a subdirectory that exists
        #    under repo_root, auto-load its README.md / CLAUDE.md so the model has
        #    immediate context rather than needing to discover it tool-call by tool-call.
        if user_text and repo_root:
            mentioned_dirs = self._find_mentioned_dirs(user_text, root, seen_paths)
            for m_dir in mentioned_dirs:
                for name in PROJECT_INSTRUCTION_FILES:
                    candidate = m_dir / name
                    if not candidate.exists():
                        continue
                    resolved = str(candidate.resolve())
                    if resolved in seen_paths:
                        continue
                    seen_paths.add(resolved)
                    remaining = MAX_TOTAL_CHARS - total_chars
                    if remaining <= 0:
                        break
                    snippet = candidate.read_text(encoding='utf-8', errors='replace')[:remaining].strip()
                    if snippet:
                        files_hint.append(f'{name} (mentioned: {m_dir.name})')
                        instructions_chunks.append(f'[mentioned:{m_dir.name}/{name}]\n' + snippet)
                        total_chars += len(snippet)

        return ProjectContext(
            cwd=str(cwd_path),
            repo_root=str(root) if root else None,
            project_name=root.name if root else cwd_path.name,
            project_files_hint=files_hint,
            project_instructions="\n\n".join(instructions_chunks) if instructions_chunks else None,
        )

    def _build_conversation_context(self, session_id: str, turn_id: str) -> ConversationContext:
        rows = self.session_store.load_messages(session_id=session_id, limit=self.max_history_messages)
        recent_messages: list[dict[str, Any]] = []
        for row in rows:
            # Skip messages from the current turn — they will be added separately
            # by PromptBuilder and should not appear in the history feed.
            if str(row.get("turn_id") or "") == turn_id:
                continue
            role = str(row.get("role") or "").strip()
            content = str(row.get("content") or "")
            if not role or not content:
                continue
            # Skip skill-context injection messages (Codex-style turn-scoped fragments).
            # These are turn-scoped instruction blocks and must NOT leak into the
            # next turn's conversation history.
            if "<skill-context" in content:
                continue
            if role == "tool" and content.startswith("skill.load:"):
                continue
            recent_messages.append({"role": role, "content": content})
        summaries = self.session_store.load_summaries(session_id=session_id, limit=1)
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
        long_term_refs: list[dict[str, Any]] = []
        project_id = str(chat_input.project_id or "").strip()

        # ── User profile memory (capped at 800 chars total) ──
        profile_records = self.memory_store.get_typed(memory_type="user_profile", limit=8)
        if profile_records:
            profile_parts: list[str] = []
            profile_chars = 0
            for r in profile_records:
                chunk = f"- {r['key']}: {r['value_redacted']}"
                if profile_chars + len(chunk) > 800:
                    break
                profile_parts.append(chunk)
                profile_chars += len(chunk)
            if profile_parts:
                short_term["user_preferences"] = "\n".join(profile_parts)

        # ── Project facts (capped at 1200 chars) ──
        if project_id:
            proj_records = self.memory_store.get_typed(memory_type="project_fact", project_id=project_id, limit=10)
        else:
            proj_records = self.memory_store.get_typed(memory_type="project_fact", limit=10)
        if proj_records:
            fact_parts: list[str] = []
            fact_chars = 0
            for r in proj_records:
                chunk = f"- {r['key']}: {r['value_redacted']}"
                if fact_chars + len(chunk) > 1200:
                    break
                fact_parts.append(chunk)
                fact_chars += len(chunk)
            if fact_parts:
                short_term["project_facts"] = "\n".join(fact_parts)

        # ── Backward-compat: existing KV user/project memory ──
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

        # ── Relevance-based search with user query ──
        if query:
            rows = self.memory_retriever.retrieve(project_id=chat_input.project_id, query=query)
            for item in rows[:5]:
                key = str(item.get("key") or "").strip()
                value = str(item.get("value") or "").strip()
                mem_type = str(item.get("memory_type") or "")
                if key and value:
                    labeled_key = f"memory:{mem_type}:{key}" if mem_type else key
                    short_term[labeled_key] = value[:280]
                    long_term_refs.append({"key": key, "value": value[:280], "memory_type": mem_type})

        # ── Markdown memory (supplements SQLite, human-editable source of truth) ──
        try:
            md_entries = self.memory_store.memory_md.load_all()
            for entry in md_entries[:10]:
                md_key = f"md_memory:{entry.memory_type}:{entry.name}"
                if md_key not in short_term:
                    short_term[md_key] = entry.content[:500]
        except Exception:
            pass

        return MemoryContext(short_term=short_term, long_term_refs=long_term_refs)

    def _build_skill_context(self, *, stored_context: dict[str, Any] | None = None, session_id: str = "") -> SkillContext:
        from ..core.debug_log import debug_log as _dbg, is_debug_enabled as _dbg_on
        _enabled = _dbg_on()
        _t0 = time.perf_counter() if _enabled else 0
        available: list[dict[str, Any]] = []
        if self.skill_registry is not None:
            try:
                available = list(self.skill_registry.export_index())
            except Exception:
                available = []
        if _enabled:
            _dbg("context", f"_build_skill_context export_index done in {time.perf_counter()-_t0:.2f}s rows={len(available)}")
            _t0 = time.perf_counter()
        stored_context = dict(stored_context or {})
        active_task = stored_context.get("active_task")
        if not active_task and session_id:
            active_task = self._load_active_plan(session_id)
        if _enabled:
            _dbg("context", f"_build_skill_context load_active_plan done in {time.perf_counter()-_t0:.3f}s")
        return SkillContext(
            available_skills=available,
            skill_observations=list(stored_context.get("skill_observations") or []),
            research_observations=list(stored_context.get("research_observations") or []),
            active_task=active_task,
        )

    def _load_active_plan(self, session_id: str) -> dict[str, Any] | None:
        try:
            record = self.session_store.load_active_plan(session_id)
        except Exception:
            return None
        if record is None:
            return None
        import json
        try:
            steps = json.loads(record["steps_json"])
        except Exception:
            steps = []
        return {
            "plan_id": record["plan_id"],
            "goal": record["goal"],
            "status": record["status"],
            "steps": steps,
        }

    def _load_stored_context(self, session_id: str) -> dict[str, Any]:
        if self.context_store is None:
            return {}
        try:
            return dict(self.context_store.retrieve_recent_context(session_id))
        except Exception:
            return {}

    @staticmethod
    def _find_mentioned_dirs(user_text: str, repo_root: Path, seen_paths: set[str]) -> list[Path]:
        """Find subdirectories of repo_root that are mentioned in user_text."""
        found: list[Path] = []
        lowered = user_text.lower()
        try:
            for entry in sorted(repo_root.iterdir()):
                if not entry.is_dir():
                    continue
                if entry.name.startswith('.') or entry.name.startswith('_'):
                    continue
                name_lower = entry.name.lower()
                if name_lower in lowered:
                    found.append(entry)
        except (OSError, PermissionError):
            pass
        return found

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
