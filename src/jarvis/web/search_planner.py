from __future__ import annotations

from .query_rewriter import RewriteOutput
from .schema import SearchQuery


class SearchPlanner:
    def __init__(self, *, max_search_tasks: int = 3, top_k: int = 5) -> None:
        self.max_search_tasks = max_search_tasks
        self.top_k = top_k

    def plan(self, rewrite: RewriteOutput, intent_type: str) -> list[SearchQuery]:
        seen: set[tuple[str, str]] = set()
        planned: list[SearchQuery] = []
        for task in rewrite.search_tasks:
            key = (task.query.strip().lower(), str(task.site or "").strip().lower())
            if key in seen:
                continue
            seen.add(key)
            task.top_k = min(max(1, int(task.top_k or self.top_k)), self.top_k)
            planned.append(task)
            if len(planned) >= self.max_search_tasks:
                break
        return planned

