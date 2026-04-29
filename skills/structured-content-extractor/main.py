"""Structured content extractor skill.

This skill focuses on extracting structured items from raw page text so
upstream summarization can be more stable and extensible across sites.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

DESCRIPTION = "把页面正文提取成结构化数据"
ICON = "🧩"


def _detect_site(site: str, url: str) -> str:
    low = (site or "").lower().strip()
    if low:
        return low
    u = (url or "").lower()
    if "zhihu.com" in u:
        return "zhihu"
    if "xiaohongshu.com" in u or "xhslink.com" in u:
        return "xiaohongshu"
    if "taobao.com" in u or "tmall.com" in u:
        return "taobao"
    if "jd.com" in u:
        return "jd"
    return "web"


def _is_noise(line: str) -> bool:
    low = (line or "").lower()
    if not line or len(line.strip()) < 3:
        return True
    noise = [
        "登录", "注册", "帮助中心", "查看历史", "购物车", "cookie", "copyright",
        "关于我们", "联系客服", "隐私", "条款"
    ]
    return any(x in low for x in noise)


def _extract_ecommerce_items(text: str) -> List[Dict[str, Any]]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    price_re = re.compile(r"(?:￥|¥)\s*([0-9]+(?:\.[0-9]{1,2})?)")

    items: List[Dict[str, Any]] = []
    for idx, ln in enumerate(lines):
        if len(ln) < 8 or len(ln) > 80 or _is_noise(ln):
            continue

        price = ""
        for j in (idx, idx + 1, idx + 2):
            if 0 <= j < len(lines):
                m = price_re.search(lines[j])
                if m:
                    price = m.group(1)
                    break

        if re.search(r"[\u4e00-\u9fffA-Za-z0-9]", ln):
            items.append({"title": ln, "price": price})
        if len(items) >= 12:
            break

    dedup: List[Dict[str, Any]] = []
    seen = set()
    for it in items:
        key = f"{it.get('title','')}|{it.get('price','')}"
        if key in seen:
            continue
        seen.add(key)
        dedup.append(it)
    return dedup


def _extract_social_items(text: str) -> List[Dict[str, Any]]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    items: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}

    for ln in lines:
        if len(ln) > 6 and len(ln) < 70 and not _is_noise(ln):
            if not current.get("title"):
                current["title"] = ln
                continue
        if re.search(r"赞|评论|收藏|转发|阅读", ln) and len(ln) < 80:
            current["engagement"] = ln
        if current.get("title") and len(current) >= 1:
            items.append(current)
            current = {}
        if len(items) >= 8:
            break

    return items


def _extract_generic_items(text: str) -> List[Dict[str, Any]]:
    chunks = [x.strip() for x in re.split(r"[。！？!?；;\n]", text or "") if x.strip()]
    items: List[Dict[str, Any]] = []
    for ch in chunks:
        if len(ch) < 12 or _is_noise(ch):
            continue
        items.append({"snippet": ch})
        if len(items) >= 8:
            break
    return items


def execute(source_url: str = "", site: str = "", page_text: str = "", **kwargs) -> Dict[str, Any]:
    actual_site = _detect_site(site, source_url)

    if actual_site in ["taobao", "jd"]:
        items = _extract_ecommerce_items(page_text)
        return {
            "status": "success",
            "site": actual_site,
            "mode": "ecommerce_search",
            "items": items,
            "summary_hint": "优先按商品候选列表总结"
        }

    if actual_site in ["zhihu", "xiaohongshu"]:
        items = _extract_social_items(page_text)
        return {
            "status": "success",
            "site": actual_site,
            "mode": "social_post",
            "items": items,
            "summary_hint": "优先按话题观点与互动信息总结"
        }

    items = _extract_generic_items(page_text)
    return {
        "status": "success",
        "site": actual_site,
        "mode": "generic",
        "items": items,
        "summary_hint": "按核心事实片段总结"
    }
