"""Adapter skill for marketplace arxiv-reader.

Provides a standard execute() entry so Toolkit can load and route it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict

DESCRIPTION = "读取并总结指定 arXiv 论文"
ICON = "📄"


def _extract_arxiv_id(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", s)
    if m:
        return m.group(1)
    m2 = re.search(r"arxiv\.org/(?:abs|pdf)/([^\s/?#]+)", s)
    if m2:
        return m2.group(1).replace(".pdf", "")
    return ""


def execute(user_input: str = "", arxiv_id: str = "", category: str = "", **kwargs) -> Dict[str, Any]:
    target = (arxiv_id or _extract_arxiv_id(user_input)).strip()
    if not target:
        return {
            "status": "error",
            "code": "missing_input",
            "message": "缺少 arXiv ID 或 URL",
        }

    skills_root = Path(__file__).resolve().parent.parent
    candidate_dirs = [
        skills_root / "arxiv-reader-upstream",
        skills_root / "marketplace-meta" / "skills" / "arxiv-reader",
        skills_root / "skills-marketplace" / "skills" / "arxiv-reader",
    ]
    market_dir = next((p for p in candidate_dirs if p.exists()), None)
    if market_dir is None:
        return {
            "status": "error",
            "code": "upstream_error",
            "message": "未找到 marketplace arxiv-reader 模块",
        }

    sys.path.insert(0, str(market_dir))
    try:
        from main import process_single_paper  # type: ignore
        import config as arxiv_config  # type: ignore

        # Marketplace skill has partial config defaults;补齐缺失字段以便可执行。
        if not hasattr(arxiv_config, "ARXIV_CATEGORIES"):
            arxiv_config.ARXIV_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG"]
        if not hasattr(arxiv_config, "ARXIV_MAX_RESULTS"):
            arxiv_config.ARXIV_MAX_RESULTS = 30

        notes = process_single_paper(target, category=category or None)
        text = str(notes or "").strip()
        return {
            "status": "success",
            "arxiv_id": target,
            "category": category or "auto",
            "summary": text[:1200],
            "notes": "arxiv_reader_adapter",
        }
    except Exception as exc:
        return {
            "status": "error",
            "code": "upstream_error",
            "message": str(exc),
            "arxiv_id": target,
        }
    finally:
        if str(market_dir) in sys.path:
            sys.path.remove(str(market_dir))
