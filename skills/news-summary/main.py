"""News-summary adapter.

Fetches RSS headlines and returns concise grouped summaries.
"""
from __future__ import annotations

import re
import requests
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

DESCRIPTION = "抓取 RSS 新闻并生成简报"
ICON = "📰"

FEEDS = {
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "top": "https://feeds.bbci.co.uk/news/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "tech": "https://feeds.bbci.co.uk/news/technology/rss.xml",
}


def _fetch_titles(url: str, n: int = 5) -> List[str]:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    items = root.findall(".//item")
    out: List[str] = []
    for it in items:
        t = (it.findtext("title") or "").strip()
        t = re.sub(r"\s+", " ", t)
        if t:
            out.append(t)
        if len(out) >= n:
            break
    return out


def execute(topic: str = "world", user_input: str = "", max_items: int = 5, **kwargs) -> Dict[str, Any]:
    key = (topic or "").strip().lower()
    if not key and user_input:
        low = user_input.lower()
        if "tech" in low or "科技" in user_input:
            key = "tech"
        elif "business" in low or "财经" in user_input:
            key = "business"
        elif "top" in low or "头条" in user_input:
            key = "top"
        else:
            key = "world"
    if key not in FEEDS:
        key = "world"

    try:
        titles = _fetch_titles(FEEDS[key], n=max(1, min(12, int(max_items))))
        return {
            "status": "success",
            "topic": key,
            "count": len(titles),
            "summary": "；".join(titles[:3]) if titles else "暂无新闻",
            "headlines": titles,
            "notes": "rss_news",
        }
    except Exception as exc:
        # RSS 不可达时回退到核心联网搜索入口。
        try:
            import sys
            from pathlib import Path

            root = Path(__file__).resolve().parents[2]
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from orchestrators.web_search_pipeline import run_web_search_v2

            obj = run_web_search_v2(
                mode="structured",
                query=f"{key} latest news",
                max_results=max(3, min(10, int(max_items))),
            )
            results = obj.get("results", []) if isinstance(obj, dict) else []
            headlines = [str(x.get("title", "")).strip() for x in results if isinstance(x, dict) and str(x.get("title", "")).strip()][: max(1, min(12, int(max_items)))]
            return {
                "status": "success",
                "topic": key,
                "count": len(headlines),
                "summary": "；".join(headlines[:3]) if headlines else "暂无新闻",
                "headlines": headlines,
                "notes": "search_fallback",
            }
        except Exception:
            return {"status": "error", "code": "upstream_error", "message": str(exc), "topic": key}
