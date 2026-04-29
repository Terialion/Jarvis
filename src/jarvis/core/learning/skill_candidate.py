from __future__ import annotations

from typing import Any


def build_skill_candidate(experience: dict[str, Any]) -> dict[str, Any]:
    calls = list(experience.get("tool_calls") or [])
    dominant = calls[0] if calls else "repo_reader.search_files"
    return {
        "candidate_id": f"skill_candidate_{experience.get('run_id', 'unknown')}",
        "proposed_tool": dominant,
        "confidence": 0.6 if calls else 0.2,
        "requires_approval": True,
        "source": "learning_loop",
    }

