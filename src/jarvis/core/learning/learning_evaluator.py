from __future__ import annotations

from typing import Any


def evaluate_learning_cycle(*, experiences: list[dict[str, Any]], accepted_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "experience_count": len(experiences),
        "candidate_count": len(accepted_candidates),
        "adoption_rate": round((len(accepted_candidates) / len(experiences) * 100.0), 2) if experiences else 0.0,
    }

