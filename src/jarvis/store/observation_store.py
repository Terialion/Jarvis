"""Thin helper around ThreadStore observation persistence."""

from __future__ import annotations

from pathlib import Path

from ..agent.skill_context import SkillObservation
from ..web.research_context import ResearchObservation
from .thread_store import ThreadStore


class ObservationStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.thread_store = ThreadStore(db_path=db_path)

    def save_skill_observation(self, thread_id: str, observation: SkillObservation, *, turn_id: str | None = None):
        return self.thread_store.append_skill_observation(thread_id, observation, turn_id=turn_id)

    def save_research_observation(self, thread_id: str, observation: ResearchObservation, *, turn_id: str | None = None):
        return self.thread_store.append_research_observation(thread_id, observation, turn_id=turn_id)

    def get_skill_observations(self, thread_id: str, limit: int = 10):
        return self.thread_store.get_skill_observations(thread_id, limit=limit)

    def get_research_observations(self, thread_id: str, limit: int = 10):
        return self.thread_store.get_research_observations(thread_id, limit=limit)
