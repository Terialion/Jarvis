"""Skill hit logging and lightweight evaluation."""

from __future__ import annotations

from statistics import mean
from time import perf_counter

from ..result import error_result, ok_result
from .models import SkillHitRecord


class SkillHitLogger:
    def __init__(self) -> None:
        self._records: list[SkillHitRecord] = []

    def log_hit(
        self,
        *,
        run_id: str,
        task_id: str,
        step_number: int,
        active_skills: list[str],
        matched_skill_ids: list[str],
        chosen_skill_id: str | None,
        chosen_tool: str | None,
        action_outcome: str,
        seeded_by_policy: bool = False,
        seed_sources: list[str] | None = None,
    ) -> dict:
        started = perf_counter()
        usefulness, label = self._score(action_outcome)
        record = SkillHitRecord(
            run_id=run_id,
            task_id=task_id,
            step_number=step_number,
            active_skills=list(active_skills or []),
            matched_skill_ids=list(matched_skill_ids or []),
            chosen_skill_id=chosen_skill_id,
            chosen_tool=chosen_tool,
            action_outcome=action_outcome,
            usefulness_score=usefulness,
            effectiveness_label=label,
            seeded_by_policy=bool(seeded_by_policy),
            seed_sources=list(seed_sources or []),
        )
        self._records.append(record)
        return ok_result(record.to_dict(), started)

    def list_hits(self, run_id: str | None = None) -> dict:
        started = perf_counter()
        items = [rec.to_dict() for rec in self._records if run_id is None or rec.run_id == run_id]
        return ok_result({"items": items, "count": len(items)}, started)

    def evaluate(self, run_id: str) -> dict:
        started = perf_counter()
        hits = [rec for rec in self._records if rec.run_id == run_id]
        if not hits:
            return error_result(
                "SKILL_EVAL_NOT_FOUND",
                f"No skill hits for run_id: {run_id}",
                {"run_id": run_id},
                started,
            )
        avg_usefulness = mean([h.usefulness_score for h in hits])
        chosen_count = sum(1 for h in hits if h.chosen_skill_id)
        return ok_result(
            {
                "run_id": run_id,
                "total_steps": len(hits),
                "chosen_skill_steps": chosen_count,
                "average_usefulness": round(avg_usefulness, 4),
                "labels": sorted({h.effectiveness_label for h in hits}),
                "seeded_hit_count": sum(1 for h in hits if h.seeded_by_policy),
            },
            started,
        )

    def aggregate_effectiveness(self, *, task_id: str | None = None) -> dict:
        started = perf_counter()
        rows = [rec for rec in self._records if task_id is None or rec.task_id == task_id]
        if not rows:
            return ok_result(
                {
                    "task_id": task_id,
                    "total_runs": 0,
                    "total_records": 0,
                    "skill_effectiveness_summary": {},
                },
                started,
            )
        by_skill: dict[str, list[SkillHitRecord]] = {}
        for rec in rows:
            skill_id = rec.chosen_skill_id or "__none__"
            by_skill.setdefault(skill_id, []).append(rec)
        summary: dict[str, dict] = {}
        for skill_id, hits in by_skill.items():
            usefulness = [h.usefulness_score for h in hits]
            high = sum(1 for h in hits if h.effectiveness_label == "high")
            low = sum(1 for h in hits if h.effectiveness_label == "low")
            summary[skill_id] = {
                "records": len(hits),
                "average_usefulness": round(mean(usefulness), 4),
                "high_ratio": round((high / len(hits)), 4),
                "low_ratio": round((low / len(hits)), 4),
                "seeded_hits": sum(1 for h in hits if h.seeded_by_policy),
                "seed_sources": sorted({src for h in hits for src in h.seed_sources}),
            }
        return ok_result(
            {
                "task_id": task_id,
                "total_runs": len({rec.run_id for rec in rows}),
                "total_records": len(rows),
                "skill_effectiveness_summary": summary,
            },
            started,
        )

    @staticmethod
    def _score(action_outcome: str) -> tuple[float, str]:
        low = (action_outcome or "").lower()
        if "success" in low or "passed" in low:
            return 1.0, "high"
        if "retry" in low:
            return 0.5, "medium"
        if "blocked" in low or "approval" in low:
            return 0.3, "low"
        return 0.2, "low"
