"""Find-skills adapter.

Search local skill folders by keyword and return install/use hints.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

DESCRIPTION = "查找本地可用 skill 并给出调用建议"
ICON = "🧭"


def execute(query: str = "", user_input: str = "", limit: int = 10, **kwargs) -> Dict[str, Any]:
    q = (query or user_input or "").strip().lower()
    alias = {
        "天气": "weather",
        "新闻": "news",
        "搜索": "search",
        "文档": "docs",
        "知识库": "knowledge",
    }
    q2 = alias.get(q, q)
    root = Path(__file__).resolve().parent.parent

    rows: List[Dict[str, Any]] = []
    for d in sorted([p for p in root.iterdir() if p.is_dir() and p.name not in {"__pycache__", "marketplace-meta"}], key=lambda x: x.name.lower()):
        skill_md = d / "SKILL.md"
        if not skill_md.exists():
            continue
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
        if q and q not in d.name.lower() and q not in text.lower() and q2 not in d.name.lower() and q2 not in text.lower():
            continue
        rows.append(
            {
                "name": d.name,
                "path": str(d),
                "has_execute": (d / "main.py").exists() or (d / "skill.py").exists() or (d / "index.py").exists(),
            }
        )
        if len(rows) >= max(1, min(100, int(limit))):
            break

    return {
        "status": "success",
        "query": q,
        "normalized_query": q2,
        "count": len(rows),
        "results": rows,
        "notes": "local_skill_discovery",
    }
