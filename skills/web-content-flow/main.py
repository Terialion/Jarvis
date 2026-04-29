"""Web content flow skill.

Plan first with an LLM, then execute step-by-step browser opens for websites
where the user wants a specific content target such as a first video, post,
or hot ranking.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import webbrowser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from openai import OpenAI

DESCRIPTION = "先由大模型分析网页目标，再按步骤执行打开/跳转"
ICON = "🌐"


def _get_client() -> Optional[OpenAI]:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def _parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    raw = text.strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _detect_site(user_input: str) -> str:
    low = user_input.lower()
    if any(key in low for key in ["b站", "哔哩哔哩", "bilibili"]):
        return "bilibili"
    if any(key in low for key in ["知乎", "zhihu"]):
        return "zhihu"
    if any(key in low for key in ["淘宝", "taobao"]):
        return "taobao"
    if any(key in low for key in ["京东", "jd"]):
        return "jd"
    if any(key in low for key in ["美团", "meituan", "饿了么", "ele.me"]):
        return "commerce"
    return "web"


def _extract_candidate_url(text: str) -> str:
    match = re.search(r"https?://[^\s'\"]+", text or "")
    return match.group(0) if match else ""


def _detect_target_mode(user_input: str) -> str:
    low = user_input.lower()
    if any(key in low for key in ["第一个视频", "第1个视频", "首个视频", "播放量最高", "最高播放", "热搜", "热门", "第一条帖子", "第一个帖子"]):
        return "content"
    return "search"


def _clean_query(user_input: str) -> str:
    query = user_input
    for sep in ["并且", "并", "然后", "，", ",", "以及", "再"]:
        if sep in query:
            query = query.split(sep, 1)[0]
            break
    for p in ["打开", "请", "帮我", "去", "在", "搜索", "搜", "一下", "网页", "网站", "b站", "哔哩哔哩", "bilibili", "知乎", "zhihu", "淘宝", "taobao", "京东", "jd"]:
        query = query.replace(p, "")
    return query.strip(" ：:，,。") or "日食记"


def _looks_like_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value or "", re.IGNORECASE))


def _resolve_bilibili_video(query: str, order: str = "totalrank") -> Tuple[str, str]:
    api = "https://api.bilibili.com/x/web-interface/search/type?" + urlencode(
        {
            "search_type": "video",
            "keyword": query,
            "order": order,
            "page": 1,
        }
    )
    try:
        req = Request(api, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com"})
        with urlopen(req, timeout=8) as resp:
            obj = json.loads(resp.read().decode("utf-8", errors="ignore"))
        data = obj.get("data", {}) if isinstance(obj, dict) else {}
        items = data.get("result", []) if isinstance(data, dict) else []
        if items:
            first = items[0]
            if isinstance(first, dict) and first.get("bvid"):
                return f"https://www.bilibili.com/video/{first['bvid']}", first.get("title", "")
    except Exception:
        pass

    # DOM 兜底：直接抓搜索页第一个视频链接
    try:
        from playwright.sync_api import sync_playwright

        search_url = f"https://search.bilibili.com/all?keyword={quote(query)}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(search_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            candidates = page.locator("a[href*='/video/']")
            count = min(candidates.count(), 8)
            for i in range(count):
                link = candidates.nth(i)
                href = link.get_attribute("href") or ""
                title = (link.inner_text() or "").strip()
                if "/video/" in href:
                    if href.startswith("//"):
                        href = "https:" + href
                    elif href.startswith("/"):
                        href = "https://www.bilibili.com" + href
                    browser.close()
                    return href, title
            browser.close()
    except Exception:
        pass

    return f"https://search.bilibili.com/all?keyword={quote(query)}", ""


def _resolve_first_link(search_url: str, link_selector: str, headless: bool = True) -> Tuple[str, str]:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page()
            page.goto(search_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            links = page.locator(link_selector)
            count = min(links.count(), 12)
            for i in range(count):
                node = links.nth(i)
                href = node.get_attribute("href") or ""
                title = (node.inner_text() or "").strip()
                if href:
                    if href.startswith("//"):
                        href = "https:" + href
                    elif href.startswith("/"):
                        href = urlparse(search_url).scheme + "://" + urlparse(search_url).netloc + href
                    browser.close()
                    return href, title
            browser.close()
    except Exception:
        pass
    return search_url, ""


def _resolve_zhihu_content(query: str, target_mode: str) -> Tuple[str, str]:
    search_url = f"https://www.zhihu.com/search?type=content&q={quote(query)}"
    if target_mode == "hot":
        return "https://www.zhihu.com/hot", ""
    return _resolve_first_link(search_url, "a[href*='/question/'], a[href*='/p/'], a[href*='/answer/']")


def _resolve_taobao_content(query: str) -> Tuple[str, str]:
    search_url = f"https://s.taobao.com/search?q={quote(query)}"
    return _resolve_first_link(search_url, "a[href*='item.htm'], a[href*='detail']")


def _resolve_jd_content(query: str) -> Tuple[str, str]:
    search_url = f"https://search.jd.com/Search?keyword={quote(query)}"
    return _resolve_first_link(search_url, "a[href*='item.jd.com'], a[href*='product']")


def _build_plan_with_llm(user_input: str) -> Dict[str, Any]:
    client = _get_client()
    fallback_site = _detect_site(user_input)
    fallback_mode = _detect_target_mode(user_input)
    fallback_query = _clean_query(user_input)

    if not client:
        return {
            "site": fallback_site,
            "query": fallback_query,
            "target_mode": fallback_mode,
            "reason": "llm_unavailable_fallback",
        }

    prompt = f"""你是网页目标分析器。请把用户指令拆成简洁可执行的网页步骤。

要求：
- 先分析站点、关键词、目标类型，再给出步骤
- 只返回 JSON，不要解释文字
- 如果用户想要的是视频/帖子/热榜，不要把完整句子当搜索词
- 如果目标是 B 站第一个视频/播放量最高/热搜，要明确写出 content_mode
- 如果是未知网站，不要只复述用户输入，请尽量给出 site_name、target_url、search_url、site_url 中至少一个
- 如果目标是帖子/商品/内容页，返回 content_mode 和你认为最合理的最终打开 URL

JSON 格式：
{{
  "site": "bilibili|zhihu|taobao|jd|commerce|web",
    "site_name": "站点名称或空",
  "query": "关键词",
  "target_mode": "search|content",
  "content_mode": "first_video|top_play|hot|first_post|search",
    "target_url": "最终应打开的页面 URL 或空",
    "search_url": "搜索页 URL 或空",
    "site_url": "站点首页 URL 或空",
  "reason": "简短说明",
  "steps": [
    {{"action": "analyze", "detail": "..."}},
    {{"action": "open_url", "url": "...", "detail": "..."}}
  ]
}}

用户指令：{user_input}
"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=350,
        )
        content = resp.choices[0].message.content or ""
        obj = _parse_json_object(content)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    return {
        "site": fallback_site,
        "site_name": "",
        "query": fallback_query,
        "target_mode": fallback_mode,
        "content_mode": "",
        "target_url": "",
        "search_url": "",
        "site_url": "",
        "reason": "llm_parse_failed_fallback",
    }


def _normalize_plan(user_input: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
    site = str(analysis.get("site") or _detect_site(user_input)).strip().lower()
    site_name = str(analysis.get("site_name") or "").strip()
    query = str(analysis.get("query") or _clean_query(user_input)).strip()
    target_mode = str(analysis.get("target_mode") or _detect_target_mode(user_input)).strip().lower()
    content_mode = str(analysis.get("content_mode") or "").strip().lower()
    target_url = str(analysis.get("target_url") or "").strip()
    search_url = str(analysis.get("search_url") or "").strip()
    site_url = str(analysis.get("site_url") or "").strip()
    steps: List[Dict[str, Any]] = []

    if site == "bilibili":
        if target_mode == "content" or content_mode in {"first_video", "top_play", "hot"}:
            if content_mode == "hot" or any(k in user_input.lower() for k in ["热搜", "热门"]):
                final_url = "https://www.bilibili.com/v/popular/all"
                steps.append({"action": "open_url", "url": final_url, "detail": "打开 B 站热门页"})
            else:
                order = "click" if content_mode == "top_play" or any(k in user_input.lower() for k in ["播放量最高", "最高播放"]) else "totalrank"
                final_url, title = _resolve_bilibili_video(query, order=order)
                steps.append({"action": "resolve_content", "detail": f"通过 B 站搜索接口解析 {order} 结果", "resolved_title": title, "url": final_url})
                steps.append({"action": "open_url", "url": final_url, "detail": "打开解析到的视频页或搜索页"})
        else:
            final_url = f"https://search.bilibili.com/all?keyword={quote(query)}"
            steps.append({"action": "open_url", "url": final_url, "detail": "打开 B 站搜索页"})
    elif site == "zhihu":
        if target_mode == "content" or any(k in user_input.lower() for k in ["第一个帖子", "第一条帖子", "帖子", "回答", "文章"]):
            resolved_url, resolved_title = _resolve_zhihu_content(query, content_mode or target_mode)
            final_url = target_url or resolved_url
            steps.append({"action": "resolve_content", "url": final_url, "resolved_title": resolved_title, "detail": "解析知乎首个内容链接"})
            steps.append({"action": "open_url", "url": final_url, "detail": "打开知乎内容页或搜索页"})
        else:
            final_url = search_url or f"https://www.zhihu.com/search?type=content&q={quote(query)}"
            steps.append({"action": "open_url", "url": final_url, "detail": "打开知乎搜索页"})
    elif site == "taobao":
        if target_mode == "content" or any(k in user_input.lower() for k in ["商品", "宝贝", "第一个商品", "第一个链接", "详情页"]):
            resolved_url, resolved_title = _resolve_taobao_content(query)
            final_url = target_url or resolved_url
            steps.append({"action": "resolve_content", "url": final_url, "resolved_title": resolved_title, "detail": "解析淘宝首个商品链接"})
            steps.append({"action": "open_url", "url": final_url, "detail": "打开淘宝商品页或搜索页"})
        else:
            final_url = search_url or f"https://s.taobao.com/search?q={quote(query)}"
            steps.append({"action": "open_url", "url": final_url, "detail": "打开淘宝搜索页"})
    elif site == "jd":
        if target_mode == "content" or any(k in user_input.lower() for k in ["商品", "产品", "第一个商品", "详情页"]):
            resolved_url, resolved_title = _resolve_jd_content(query)
            final_url = target_url or resolved_url
            steps.append({"action": "resolve_content", "url": final_url, "resolved_title": resolved_title, "detail": "解析京东首个商品链接"})
            steps.append({"action": "open_url", "url": final_url, "detail": "打开京东商品页或搜索页"})
        else:
            final_url = search_url or f"https://search.jd.com/Search?keyword={quote(query)}"
            steps.append({"action": "open_url", "url": final_url, "detail": "打开京东搜索页"})
    elif site == "commerce":
        final_url = f"https://www.meituan.com/s/{quote(query)}"
        steps.append({"action": "open_url", "url": final_url, "detail": "打开生活服务搜索页"})
    else:
        candidate_url = target_url or _extract_candidate_url(user_input) or site_url or search_url
        if candidate_url and _looks_like_url(candidate_url):
            final_url = candidate_url
            steps.append({"action": "open_url", "url": final_url, "detail": f"打开 LLM 解析到的站点目标页{f'（{site_name}）' if site_name else ''}"})
        else:
            fallback_query = query if query else user_input
            final_url = f"https://www.google.com/search?q={quote(fallback_query)}"
            steps.append({"action": "open_url", "url": final_url, "detail": "打开通用搜索页"})

    return {
        "site": site,
        "site_name": site_name,
        "query": query,
        "target_mode": target_mode,
        "content_mode": content_mode,
        "target_url": target_url,
        "search_url": search_url,
        "site_url": site_url,
        "steps": steps,
        "final_url": final_url,
    }


def execute(
    user_input: str = "",
    execute_steps: bool = True,
    open_in_browser: bool = True,
    max_steps: int = 6,
    **kwargs,
) -> Dict[str, Any]:
    """Analyze first, then execute browser-opening steps."""
    if not user_input:
        return {"status": "error", "message": "missing_user_input"}

    analysis = _build_plan_with_llm(user_input)
    plan = _normalize_plan(user_input, analysis)
    steps = plan.get("steps", [])[:max_steps]
    executed: List[Dict[str, Any]] = []

    if execute_steps and open_in_browser:
        for step in steps:
            if step.get("action") == "open_url" and step.get("url"):
                opened = webbrowser.open(step["url"])
                executed.append({"action": "open_url", "url": step["url"], "opened": opened})
            elif step.get("action") == "resolve_content":
                executed.append({"action": "resolve_content", "url": step.get("url", ""), "resolved_title": step.get("resolved_title", "")})

    return {
        "status": "success",
        "analysis": analysis,
        "steps": steps,
        "executed": executed,
        "final_url": plan.get("final_url", ""),
        "notes": "plan_first_then_execute",
    }
