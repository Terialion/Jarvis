"""In-memory session context store for skill observations and active tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .skill_context import ActiveTaskState, HandoffSummary, SkillObservation
from ..store.memory_store import MemoryStore
from ..store.session_store import SessionStore
from ..web.research_context import ResearchObservation


@dataclass
class SessionContextState:
    recent_turns: list[dict[str, Any]] = field(default_factory=list)
    skill_observations: list[SkillObservation] = field(default_factory=list)
    research_observations: list[ResearchObservation] = field(default_factory=list)
    project_facts: dict[str, Any] = field(default_factory=dict)
    active_task: ActiveTaskState | None = None
    handoff_summary: HandoffSummary | None = None


class ContextStore:
    """Small in-memory context store keyed by session/thread id."""

    def __init__(
        self,
        *,
        session_store: SessionStore | None = None,
        memory_store: MemoryStore | None = None,
    ) -> None:
        self._sessions: dict[str, SessionContextState] = {}
        self.session_store = session_store
        self.memory_store = memory_store

    def get_state(self, session_id: str) -> SessionContextState:
        key = str(session_id or "default")
        if key not in self._sessions:
            self._sessions[key] = SessionContextState()
            if self.session_store is not None:
                self._hydrate_from_session(key)
        return self._sessions[key]

    def append_turn(self, session_id: str, turn: dict[str, Any]) -> None:
        state = self.get_state(session_id)
        state.recent_turns.append(dict(turn))
        state.recent_turns = state.recent_turns[-20:]

    def add_skill_observation(self, session_id: str, observation: SkillObservation) -> None:
        state = self.get_state(session_id)
        state.skill_observations.append(observation)
        state.skill_observations = state.skill_observations[-20:]
        for file_path in observation.related_files:
            state.project_facts.setdefault("recent_files", [])
            if file_path not in state.project_facts["recent_files"]:
                state.project_facts["recent_files"].append(file_path)

    def add_research_observation(self, session_id: str, observation: ResearchObservation) -> None:
        state = self.get_state(session_id)
        state.research_observations.append(observation)
        state.research_observations = state.research_observations[-20:]
        for item in observation.sources:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            state.project_facts.setdefault("recent_sources", [])
            if url not in state.project_facts["recent_sources"]:
                state.project_facts["recent_sources"].append(url)

    def retrieve_recent_context(self, session_id: str, *, limit: int = 8) -> dict[str, Any]:
        state = self.get_state(session_id)
        user_memory = self.memory_store.get_user_memory() if self.memory_store is not None else {}
        return {
            "recent_turns": list(state.recent_turns[-limit:]),
            "skill_observations": [obs.to_dict() for obs in state.skill_observations[-limit:]],
            "research_observations": [obs.to_dict() for obs in state.research_observations[-limit:]],
            "project_facts": dict(state.project_facts),
            "active_task": state.active_task.to_dict() if state.active_task else None,
            "handoff_summary": state.handoff_summary.to_dict() if state.handoff_summary else None,
            "persistent_user_memory": dict(user_memory),
        }

    def retrieve_skill_observation(
        self,
        session_id: str,
        *,
        skill_name: str | None = None,
        related_file: str | None = None,
    ) -> SkillObservation | None:
        observations = list(reversed(self.get_state(session_id).skill_observations))
        for obs in observations:
            if skill_name and obs.skill_name != skill_name:
                continue
            if related_file and related_file not in obs.related_files:
                continue
            return obs
        return observations[0] if observations and not skill_name and not related_file else None

    def retrieve_research_observation(self, session_id: str) -> ResearchObservation | None:
        observations = list(reversed(self.get_state(session_id).research_observations))
        return observations[0] if observations else None

    def set_active_task(self, session_id: str, active_task: ActiveTaskState | None) -> None:
        self.get_state(session_id).active_task = active_task

    def set_handoff_summary(self, session_id: str, handoff: HandoffSummary | None) -> None:
        self.get_state(session_id).handoff_summary = handoff

    def clear(self, session_id: str | None = None) -> None:
        if session_id is None:
            self._sessions.clear()
        else:
            self._sessions.pop(str(session_id), None)

    def hydrate_thread(self, thread_id: str, *, project_id: str | None = None) -> dict[str, Any]:
        state = self._hydrate_from_session(thread_id, project_id=project_id)
        return {
            "thread_id": str(thread_id),
            "recent_turns": list(state.recent_turns),
            "skill_observations": [obs.to_dict() for obs in state.skill_observations],
            "research_observations": [obs.to_dict() for obs in state.research_observations],
            "project_facts": dict(state.project_facts),
            "active_task": state.active_task.to_dict() if state.active_task else None,
            "handoff_summary": state.handoff_summary.to_dict() if state.handoff_summary else None,
        }

    def _hydrate_from_session(self, thread_id: str, *, project_id: str | None = None) -> SessionContextState:
        state = self._sessions.setdefault(str(thread_id), SessionContextState())
        if self.session_store is None:
            return state
        turns = self.session_store.get_recent_turns(thread_id, limit=12)
        state.recent_turns = [
            {
                "turn_id": row["turn_id"],
                "user_input": row["input_redacted"],
                "final_answer": row["output_summary_redacted"],
                "skills_used": list((row.get("metadata") or {}).get("skills_used") or []),
                "related_files": [],
            }
            for row in turns
        ]
        state.skill_observations = [
            SkillObservation(
                skill_name=row["skill_name"],
                summary=row["summary_redacted"],
                facts=dict((row.get("metadata") or {}).get("facts") or {}),
                related_files=[str(x) for x in row.get("related_files", [])],
                tool_calls=[str(x) for x in list((row.get("metadata") or {}).get("tool_calls") or [])],
                created_at=row.get("created_at", ""),
            )
            for row in self.session_store.get_skill_obs(thread_id, limit=12)
        ]
        state.research_observations = [
            ResearchObservation(
                query=row["query_redacted"],
                search_tasks=[dict(x) for x in list((row.get("metadata") or {}).get("search_tasks") or []) if isinstance(x, dict)],
                sources=[dict(x) for x in row.get("sources_redacted", []) if isinstance(x, dict)],
                evidence=[dict(x) for x in row.get("evidence_redacted", []) if isinstance(x, dict)],
                answer_summary=row["answer_summary_redacted"],
                confidence=float(row.get("confidence", 0.0)),
                remaining_questions=[str(x) for x in list((row.get("metadata") or {}).get("remaining_questions") or [])],
                created_at=row.get("created_at", ""),
            )
            for row in self.session_store.get_research_obs(thread_id, limit=8)
        ]
        active_task = self.session_store.get_active_task(thread_id)
        if active_task is not None:
            metadata = dict(active_task.get("metadata") or {})
            state.active_task = ActiveTaskState(
                task_id=str(metadata.get("task_id") or f"task_{thread_id}"),
                user_goal=str(metadata.get("user_goal") or active_task["summary_redacted"]),
                current_phase=str(metadata.get("current_phase") or "resumed"),
                completed_steps=[str(x) for x in list(metadata.get("completed_steps") or [])],
                remaining_work=[str(x) for x in list(active_task.get("remaining_work") or [])],
                related_files=[str(x) for x in list(active_task.get("related_files") or [])],
                skills_used=[str(x) for x in list(metadata.get("skills_used") or [])],
                risks=[str(x) for x in list(metadata.get("risks") or [])],
            )
        handoff = self.session_store.get_handoff(thread_id)
        if handoff is not None:
            metadata = dict(handoff.get("metadata") or {})
            state.handoff_summary = HandoffSummary(
                user_goal=str(metadata.get("user_goal") or ""),
                current_state=str(metadata.get("current_state") or handoff["summary_redacted"]),
                completed_work=[str(x) for x in list(metadata.get("completed_work") or [])],
                remaining_work=[str(x) for x in list(metadata.get("remaining_work") or [])],
                context_to_keep=[str(x) for x in list(metadata.get("context_to_keep") or [])],
                risks=[str(x) for x in list(handoff.get("risks") or [])],
            )
        facts = self.session_store.get_project_facts(thread_id, project_id=project_id)
        if facts is not None:
            state.project_facts["persistent_project_facts"] = list(facts.get("facts_redacted", []))
        if self.memory_store is not None:
            state.project_facts["persistent_user_memory"] = self.memory_store.get_user_memory()
            if project_id:
                state.project_facts["persistent_project_memory"] = self.memory_store.get_project_memory(project_id)
        return state
