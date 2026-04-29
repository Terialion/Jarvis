"""Web content summary skill.

Fetch a page or accept raw content, then use an LLM to produce a concise
summary with key points. If the LLM is unavailable, fall back to an extractive
summary so the skill still returns something actionable.
"""
from __future__ import annotations

import json
import os
import re
import webbrowser
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from openai import OpenAI

DESCRIPTION = "先抓取网页内容，再用大模型提炼总结"
ICON = "🧠"

DEFAULT_CLEAN_TEXT_MAX_CHARS = 3600

DEFAULT_NOISE_TOKENS = [
    "目录", "主菜单", "登录", "注册", "工具", "查看历史", "资助维基", "创建账号", "条目", "讨论",
    "外部链接", "参考文献", "扩展阅读", "查论编", "自由的百科全书", "请更新本文", "文內引註不足",
    "facebook粉絲專頁", "生日模式", "测试版", "本條目存在以下問題", "人工智能系列内容", "各地常用名稱",
    "disclaimer", "cookie", "copyright",
]

DEFAULT_SECTION_STOP_MARKERS = [
    "主条目：人工智能史",
    "40年代 20世紀",
    "發展史",
    "研究課題",
]

DEFAULT_ANCHORS = [
    "人工智能（",
    "人工智慧（",
    "artificial intelligence",
]

DEFAULT_DEEP_CRAWL_MAX_PAGES = 4
DEFAULT_DEEP_CRAWL_PAGE_MAX_CHARS = 2400


def _load_skill_config() -> Dict[str, Any]:
    config_path = Path(__file__).with_name("config.json")
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


_CFG = _load_skill_config()
_ACTIVE_SITE_PROFILE: Dict[str, Any] = {}


def _cfg_list(name: str, fallback: List[str]) -> List[str]:
    value = _ACTIVE_SITE_PROFILE.get(name, _CFG.get(name))
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return fallback


def _cfg_int(name: str, fallback: int) -> int:
    value = _ACTIVE_SITE_PROFILE.get(name, _CFG.get(name))
    if isinstance(value, int):
        return value
    return fallback


def _cfg_float(name: str, fallback: float) -> float:
    value = _ACTIVE_SITE_PROFILE.get(name, _CFG.get(name))
    if isinstance(value, (int, float)):
        return float(value)
    return fallback


def _detect_site_from_url(url: str) -> str:
    low = (url or "").lower()
    if "zhihu.com" in low:
        return "zhihu"
    if "taobao.com" in low or "tmall.com" in low:
        return "taobao"
    if "jd.com" in low:
        return "jd"
    if "xiaohongshu.com" in low or "xhslink.com" in low:
        return "xiaohongshu"
    return "web"


def _site_profiles() -> Dict[str, Any]:
    profiles = _CFG.get("site_profiles", {})
    return profiles if isinstance(profiles, dict) else {}


def _resolve_site_profile(site: str) -> Dict[str, Any]:
    profiles = _site_profiles()
    obj = profiles.get(site, {})
    return obj if isinstance(obj, dict) else {}


def _save_site_profile(site: str, profile: Dict[str, Any]) -> None:
    if not site or not isinstance(profile, dict):
        return
    merged = dict(_CFG)
    profiles = dict(_site_profiles())
    profiles[site] = profile
    merged["site_profiles"] = profiles

    path = Path(__file__).with_name("config.json")
    try:
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _CFG.clear()
        _CFG.update(merged)
    except Exception:
        return


def _merge_and_save_site_profile(site: str, delta: Dict[str, Any]) -> None:
    if not site or not isinstance(delta, dict):
        return
    current = _resolve_site_profile(site)
    merged: Dict[str, Any] = dict(current)
    for key in ["noise_tokens", "anchors", "section_stop_markers"]:
        base = current.get(key, []) if isinstance(current.get(key), list) else []
        add = delta.get(key, []) if isinstance(delta.get(key), list) else []
        uniq: List[str] = []
        for token in list(base) + list(add):
            t = str(token).strip()
            if t and t not in uniq:
                uniq.append(t)
        if uniq:
            merged[key] = uniq[:20]
    _save_site_profile(site, merged)


def _learn_site_profile_from_page(site: str, page_text: str) -> Dict[str, Any]:
    text = (page_text or "").strip()
    if not text:
        return {}

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:80]
    candidates: List[str] = []

    # 优先学习出现在页面前段的强噪声词，避免污染正文策略。
    for ln in lines[:35]:
        if len(ln) > 22:
            continue
        if re.search(r"登录|注册|购物车|客服|帮助中心|查看历史|条目|讨论|优惠|立即购买|加入购物车", ln):
            candidates.append(ln)

    # 从极短高频行提取噪声词。
    freq: Dict[str, int] = {}
    for ln in lines[:40]:
        if 1 <= len(ln) <= 8:
            freq[ln] = freq.get(ln, 0) + 1
    for token, cnt in freq.items():
        if cnt >= 2:
            candidates.append(token)

    noise_tokens: List[str] = []
    for x in candidates:
        t = x.strip()
        if t and t not in noise_tokens:
            noise_tokens.append(t)

    if not noise_tokens:
        return {}
    return {"noise_tokens": noise_tokens[:12]}


def _detect_page_state(url: str, title: str, text: str) -> str:
    low_url = (url or "").lower()
    low_title = (title or "").lower()
    low_text = (text or "").lower()

    blocked_markers = ["403", "访问异常", "暂时限制本次访问", "captcha", "verify", "机器人", "风控", "ip存在风险", "安全限制"]
    if any(m in low_text for m in blocked_markers):
        return "blocked"

    deleted_markers = [
        "问题不存在", "内容已删除", "被删除", "无法查看该内容", "not found",
        "该内容已被删除", "笔记已被删除", "你访问的页面不存在", "该话题已不存在",
    ]
    if any(m in low_text for m in deleted_markers):
        return "deleted"

    inaccessible_markers = [
        "该内容暂时无法查看", "仅对自己可见", "仅作者可见", "因违规无法查看",
        "内容不可见", "当前内容不可访问", "话题暂不可见", "当前笔记暂时无法浏览",
    ]
    if any(m in low_text for m in inaccessible_markers):
        return "inaccessible"

    login_markers = [
        "登录", "立即注册", "免费注册", "亲，请登录", "扫码登录", "欢迎登录", "password", "手机号登录",
    ]
    if "passport" in low_url or any(m.lower() in low_title for m in login_markers):
        return "login"
    if "login" in low_url and "error" not in low_url:
        return "login"
    if sum(1 for m in login_markers if m.lower() in low_text) >= 2:
        return "login"

    return "ok"


def _run_structured_extractor(site: str, url: str, text: str) -> Dict[str, Any]:
    skill_path = Path(__file__).resolve().parent.parent / "structured-content-extractor" / "main.py"
    if not skill_path.exists():
        return {}
    try:
        spec = importlib.util.spec_from_file_location("structured_content_extractor_main", str(skill_path))
        if not spec or not spec.loader:
            return {}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        execute_fn = getattr(module, "execute", None)
        if callable(execute_fn):
            result = execute_fn(source_url=url, site=site, page_text=text)
            return result if isinstance(result, dict) else {}
    except Exception:
        return {}
    return {}


def _extract_ecommerce_items(site: str, url: str, raw_text: str) -> List[Dict[str, str]]:
    if site not in ["taobao", "jd"]:
        return []
    if "search" not in (url or "").lower():
        return []

    lines = [ln.strip() for ln in (raw_text or "").splitlines() if ln.strip()]
    items: List[Dict[str, str]] = []
    price_re = re.compile(r"(?:￥|¥)\s*([0-9]+(?:\.[0-9]{1,2})?)")

    for i, ln in enumerate(lines):
        if len(ln) < 8 or len(ln) > 70:
            continue
        if _is_noise_segment(ln):
            continue

        price = ""
        for j in [i, i + 1, i + 2]:
            if 0 <= j < len(lines):
                m = price_re.search(lines[j])
                if m:
                    price = m.group(1)
                    break

        # 电商标题中常带中英文与数字，放宽匹配。
        if re.search(r"[\u4e00-\u9fffA-Za-z0-9]", ln):
            items.append({"title": ln, "price": price})
        if len(items) >= 10:
            break

    # 去重
    dedup: List[Dict[str, str]] = []
    seen = set()
    for it in items:
        key = f"{it.get('title','')}|{it.get('price','')}"
        if key in seen:
            continue
        seen.add(key)
        dedup.append(it)
    return dedup


def _infer_site_profile_with_llm(site: str, url: str, text_sample: str) -> Dict[str, Any]:
    client = _get_client()
    if not client:
        return {}

    prompt = f"""你是网页清洗策略生成器。请根据站点样本，生成可用于正文去噪的站点策略。

仅返回 JSON：
{{
  "noise_tokens": ["..."],
  "anchors": ["..."],
  "section_stop_markers": ["..."]
}}

要求：
- 字段必须是数组
- 每个数组最多 12 项
- 只给字符串，不要解释

站点标识：{site}
URL：{url}
页面样本：
{(text_sample or '')[:2500]}
"""

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=320,
        )
        obj = _parse_json_object(resp.choices[0].message.content or "")
        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for key in ["noise_tokens", "anchors", "section_stop_markers"]:
                val = obj.get(key)
                if isinstance(val, list):
                    out[key] = [str(x).strip() for x in val if str(x).strip()][:12]
            return out
    except Exception:
        return {}
    return {}


def _select_deep_crawl_links(site: str, page_url: str, links: List[str]) -> List[str]:
    if not links:
        return []

    selected: List[str] = []
    for link in links:
        low = link.lower()
        if site == "zhihu":
            if re.search(r"zhihu\.com/question/\d+", low) or re.search(r"zhihu\.com/p/\d+", low):
                selected.append(link)
                continue
        elif site == "xiaohongshu":
            if "xiaohongshu.com/explore/" in low:
                selected.append(link)
                continue

    if not selected:
        host = ""
        m = re.match(r"https?://([^/]+)", page_url or "")
        if m:
            host = m.group(1)
        for link in links:
            if host and host in link:
                selected.append(link)

    uniq: List[str] = []
    for link in selected:
        if link not in uniq:
            uniq.append(link)
    return uniq


def _crawl_related_pages(site: str, urls: List[str], cookies: Any, max_pages: int, max_chars_per_page: int) -> List[Dict[str, Any]]:
    crawled: List[Dict[str, Any]] = []
    for link in urls[:max_pages]:
        try:
            sub = _fetch_page_content(link, max_chars=max_chars_per_page, cookies=cookies)
            sub_state = _detect_page_state(sub.get("url", link), sub.get("title", ""), sub.get("text", ""))
            crawled.append(
                {
                    "url": sub.get("url", link),
                    "title": sub.get("title", ""),
                    "state": sub_state,
                    "text": sub.get("text", ""),
                }
            )
        except Exception as exc:
            crawled.append({"url": link, "title": "", "state": "error", "text": "", "error": str(exc)})
    return crawled


def _build_deep_crawl_seed(site: str, pages: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for idx, pg in enumerate(pages, start=1):
        state = str(pg.get("state", ""))
        if state not in ["ok", ""]:
            continue
        title = str(pg.get("title", "")).strip()
        text = _rule_denoise_text(str(pg.get("text", "")))
        if not text:
            continue
        snippet = _compress_clean_text(text, max_chars=800)
        header = f"第{idx}条" + (f"：{title}" if title else "")
        parts.append(f"{header}\n{snippet}")

    if not parts:
        return ""
    joined = "\n\n".join(parts)
    cap = _cfg_int("clean_text_max_chars", DEFAULT_CLEAN_TEXT_MAX_CHARS)
    return _compress_clean_text(joined, max_chars=cap)


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


def _extract_url(text: str) -> str:
    match = re.search(r"https?://[^\s'\"]+", text or "")
    return match.group(0) if match else ""


def _clean_query(text: str) -> str:
    query = text or ""
    for sep in ["并且", "并", "然后", "，", ",", "以及", "再"]:
        if sep in query:
            query = query.split(sep, 1)[0]
            break
    for p in ["总结", "概括", "提炼", "梳理", "摘要", "总结一下", "概括一下", "提炼一下", "帮我", "请", "这个", "网页", "页面", "帖子", "文章", "视频", "商品", "内容"]:
        query = query.replace(p, "")
    return query.strip(" ：:，,。")


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
    if any(key in low for key in ["小红书", "xiaohongshu", "xhslink"]):
        return "xiaohongshu"
    return "web"


def _build_fallback_analysis(user_input: str) -> Dict[str, Any]:
    url = _extract_url(user_input)
    site = _detect_site(user_input)
    query = _clean_query(user_input) or ""

    if not url:
        if site == "bilibili":
            url = f"https://search.bilibili.com/all?keyword={quote(query or '日食记')}"
        elif site == "zhihu":
            url = f"https://www.zhihu.com/search?type=content&q={quote(query or '日食记')}"
        elif site == "taobao":
            url = f"https://s.taobao.com/search?q={quote(query or '日食记')}"
        elif site == "jd":
            url = f"https://search.jd.com/Search?keyword={quote(query or '日食记')}"
        elif site == "commerce":
            url = f"https://www.meituan.com/s/{quote(query or '外卖')}"
        elif site == "xiaohongshu":
            url = f"https://www.xiaohongshu.com/search_result?keyword={quote(query or '穿搭')}"
        else:
            url = f"https://www.google.com/search?q={quote(query or user_input or '网页总结')}"

    return {
        "site": site,
        "query": query,
        "source_url": url,
        "summary_focus": "概括内容要点",
        "reason": "llm_unavailable_fallback",
    }


def _build_analysis(user_input: str, source_url: str = "") -> Dict[str, Any]:
    client = _get_client()
    if not client:
        return _build_fallback_analysis(user_input if not source_url else f"{user_input} {source_url}")

    prompt = f"""你是网页内容总结器。请把用户请求拆成页面分析与抓取目标，并尽量给出可抓取的 URL。

要求：
- 只返回 JSON，不要解释文字
- 如果用户给了 URL，优先使用该 URL
- 如果没有 URL，要根据站点和关键词给出 source_url
- 如果是未知网站，也要给出最可能的 source_url，不要只说无法处理
- 输出要适合后续抓取正文并总结

JSON 格式：
{{
  "site": "bilibili|zhihu|taobao|jd|commerce|web",
  "query": "关键词",
  "source_url": "最终抓取的 URL",
  "summary_focus": "用户最关心什么",
  "content_type": "video|post|product|article|search_result|unknown",
  "reason": "简短说明"
}}

用户请求：{user_input}
可选 URL：{source_url}
"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=280,
        )
        content = resp.choices[0].message.content or ""
        obj = _parse_json_object(content)
        if isinstance(obj, dict):
            if source_url and not obj.get("source_url"):
                obj["source_url"] = source_url
            return obj
    except Exception:
        pass

    fallback = _build_fallback_analysis(user_input if not source_url else f"{user_input} {source_url}")
    if source_url:
        fallback["source_url"] = source_url
    return fallback


def _parse_cookies(cookies: Any) -> List[Dict[str, Any]]:
    if not cookies:
        return []
    if isinstance(cookies, list):
        return [x for x in cookies if isinstance(x, dict)]
    if isinstance(cookies, str):
        raw = cookies.strip()
        if not raw:
            return []
        try:
            obj = json.loads(raw)
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)]
        except Exception:
            return []
    return []


def _load_cookies_from_file(cookie_file: str) -> List[Dict[str, Any]]:
    path = (cookie_file or "").strip()
    if not path:
        return []
    try:
        if not os.path.exists(path):
            return []
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    except Exception:
        return []
    return []


def _fetch_page_content(url: str, max_chars: int = 12000, cookies: Any = None) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            cookie_list = _parse_cookies(cookies) or _parse_cookies(os.getenv("JARVIS_FETCH_COOKIES", ""))
            if cookie_list:
                try:
                    context.add_cookies(cookie_list)
                except Exception:
                    pass

            page = context.new_page()
            page.set_default_timeout(15000)
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)

            title = ""
            try:
                title = page.title()
            except Exception:
                title = ""

            text = ""
            try:
                text = page.locator("body").inner_text()
            except Exception:
                try:
                    text = page.text_content("body") or ""
                except Exception:
                    text = ""

            headings = []
            try:
                headings = page.locator("h1, h2, h3").all_inner_texts()
            except Exception:
                headings = []

            links: List[str] = []
            try:
                hrefs = page.locator("a[href]").evaluate_all("els => els.map(e => e.href)")
                if isinstance(hrefs, list):
                    uniq: List[str] = []
                    for h in hrefs:
                        v = str(h).strip()
                        if not v.startswith("http"):
                            continue
                        if v not in uniq:
                            uniq.append(v)
                    links = uniq[:120]
            except Exception:
                links = []

            final_url = page.url or url
            # 保留段落换行，便于后续噪声过滤按行处理。
            normalized_text = text.replace("\r", "")
            normalized_text = re.sub(r"[ \t]+", " ", normalized_text)
            normalized_text = re.sub(r"\n{3,}", "\n\n", normalized_text)
            return {
                "title": title.strip(),
                "url": final_url,
                "text": normalized_text.strip()[:max_chars],
                "headings": [h.strip() for h in headings if h.strip()][:10],
                "links": links,
            }
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


def _is_noise_segment(text: str) -> bool:
    seg = (text or "").strip()
    min_segment_len = _cfg_int("min_segment_len", 8)
    if not seg or len(seg) < min_segment_len:
        return True

    low = seg.lower()
    noise_tokens = _cfg_list("noise_tokens", DEFAULT_NOISE_TOKENS)
    if any(tok in low for tok in noise_tokens):
        return True

    if "[编辑]" in seg or "[編輯]" in seg:
        return True

    # 维基导航与模板常见噪声
    if re.search(r"开关.{0,12}子章节", seg):
        return True
    if re.search(r"\b\d+种语言\b", seg):
        return True
    if re.search(r"此條目.{0,30}(問題|更新)", seg):
        return True

    # 符号或编号占比过高通常不是正文
    symbol_count = len(re.findall(r"[^\w\u4e00-\u9fff\s]", seg))
    if symbol_count > max(12, len(seg) // 3):
        return True

    return False


def _normalize_clean_text(text: str) -> str:
    if not text:
        return ""
    # 去掉维基脚注引用标记如 [1] [23]
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _compress_clean_text(text: str, max_chars: int = DEFAULT_CLEAN_TEXT_MAX_CHARS) -> str:
    if not text:
        return ""

    compact = _normalize_clean_text(text)

    # 遇到长时间线或大型章节时，优先保留前面的定义与概述内容。
    cut_pos = -1
    for marker in _cfg_list("section_stop_markers", DEFAULT_SECTION_STOP_MARKERS):
        idx = compact.find(marker)
        if idx > 0:
            cut_pos = idx if cut_pos < 0 else min(cut_pos, idx)
    if cut_pos > 0:
        compact = compact[:cut_pos]

    if len(compact) <= max_chars:
        return compact

    # 过长时按句子截断，避免在句中硬切。
    sentences = [s.strip() for s in re.split(r"(?<=[。！？!?；;])", compact) if s.strip()]
    if not sentences:
        return compact[:max_chars]

    out: List[str] = []
    total = 0
    digit_ratio_threshold = _cfg_float("digit_ratio_threshold", 0.2)
    for sent in sentences:
        # 丢弃数字密度过高的年表型句子，减少噪声和 token 占用。
        digit_ratio = sum(ch.isdigit() for ch in sent) / max(1, len(sent))
        if digit_ratio > digit_ratio_threshold:
            continue
        if total + len(sent) > max_chars:
            break
        out.append(sent)
        total += len(sent)

    if not out:
        return compact[:max_chars]
    return _normalize_clean_text(" ".join(out))


def _rule_denoise_text(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    if len(lines) <= 1:
        lines = re.split(r"(?<=[。！？!?；;])", text or "")
        lines = [ln.strip() for ln in lines if ln.strip()]

    clean_lines: List[str] = []
    for ln in lines:
        if not ln:
            continue
        if _is_noise_segment(ln):
            continue
        clean_lines.append(ln)

    if not clean_lines:
        merged = _normalize_clean_text(text or "")
    else:
        merged = _normalize_clean_text(" ".join(clean_lines))

    # 常见百科页面：从定义句开始，避免把页面横幅/模板当作正文。
    anchors = _cfg_list("anchors", DEFAULT_ANCHORS)
    lowered = merged.lower()
    start_idx = -1
    for anchor in anchors:
        idx = lowered.find(anchor.lower())
        if idx >= 0:
            start_idx = idx if start_idx < 0 else min(start_idx, idx)
    if start_idx > 0:
        merged = merged[start_idx:]

    return _compress_clean_text(merged, max_chars=_cfg_int("clean_text_max_chars", DEFAULT_CLEAN_TEXT_MAX_CHARS))


def _llm_denoise_text(user_input: str, text: str, max_chars: int = 9000) -> str:
    client = _get_client()
    if not client:
        return _rule_denoise_text(text)

    seed = _rule_denoise_text(text)[:max_chars]
    if not seed:
        return ""

    prompt = f"""你是网页正文清洗器。请移除导航、目录、版权、脚注、菜单等噪声，仅保留主要正文事实。

只返回 JSON：
{{
  "clean_text": "清洗后的正文"
}}

用户请求：{user_input}
原文：
{seed}
"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=700,
        )
        obj = _parse_json_object(resp.choices[0].message.content or "")
        if isinstance(obj, dict):
            clean = str(obj.get("clean_text", "")).strip()
            if clean:
                return re.sub(r"\s+", " ", clean)
    except Exception:
        pass

    return seed


def _extractive_summary(text: str, limit: int = 1200) -> Dict[str, Any]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    key_points: List[str] = []
    min_keypoint_len = _cfg_int("min_keypoint_len", 16)
    for chunk in re.split(r"[。！？!?；;\n]", cleaned):
        chunk = chunk.strip()
        if len(chunk) >= min_keypoint_len and not _is_noise_segment(chunk):
            key_points.append(chunk)
        if len(key_points) >= 5:
            break
    if not key_points and cleaned:
        key_points = [cleaned[:limit]]
    return {
        "summary": cleaned[:limit],
        "key_points": key_points,
        "notes": "extractive_fallback",
    }


def _rewrite_summary(user_input: str, analysis: Dict[str, Any], summary_payload: Dict[str, Any]) -> Dict[str, Any]:
    base_summary = str(summary_payload.get("summary", "")).strip()
    key_points = summary_payload.get("key_points", []) if isinstance(summary_payload.get("key_points", []), list) else []
    key_points = [str(x).strip() for x in key_points if str(x).strip() and not _is_noise_segment(str(x))][:5]

    client = _get_client()
    if client and (base_summary or key_points):
        prompt = f"""把下面总结重写成更自然、可读性更高的中文，不要照抄原文。

只返回 JSON：
{{
  "summary": "3-5句自然总结",
  "key_points": ["要点1", "要点2", "要点3"],
  "takeaway": "一句话结论"
}}

用户请求：{user_input}
站点分析：{json.dumps(analysis, ensure_ascii=False)}
原始总结：{base_summary}
原始要点：{json.dumps(key_points, ensure_ascii=False)}
"""
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=380,
            )
            obj = _parse_json_object(resp.choices[0].message.content or "")
            if isinstance(obj, dict) and obj.get("summary"):
                obj.setdefault("notes", "llm_rewrite")
                return obj
        except Exception:
            pass

    # 无模型时提供结构化重写
    if not key_points and base_summary:
        key_points = [
            seg.strip()
            for seg in re.split(r"[。！？!?；;]", base_summary)
            if seg.strip() and not _is_noise_segment(seg.strip())
        ][:3]
    compact = "；".join(key_points[:3]) if key_points else _normalize_clean_text(base_summary)[:160]
    return {
        "summary": f"这页内容主要围绕：{compact}。",
        "key_points": key_points[:5],
        "takeaway": key_points[0] if key_points else _normalize_clean_text(base_summary)[:80],
        "notes": "rule_rewrite",
    }


def _summarize_with_llm(user_input: str, analysis: Dict[str, Any], page: Dict[str, Any], content_text: str) -> Dict[str, Any]:
    client = _get_client()
    if not client:
        return _extractive_summary(content_text)

    prompt = f"""你是网页内容总结器。请根据网页正文做简明总结。

输出 JSON：
{{
  "summary": "2-5 句的简洁总结",
  "key_points": ["要点1", "要点2", "要点3"],
  "what_matters": ["最值得关注的内容"],
  "takeaway": "一句话结论",
  "confidence": 0.0
}}

要求：
- 不要复述大段原文
- 如果页面是搜索结果页，请总结搜索结果的共同主题与可用结论
- 如果是帖子/视频/商品页，请总结内容、结论、主要信息和下一步建议
- 尽量用中文输出

用户请求：{user_input}
站点分析：{json.dumps(analysis, ensure_ascii=False)}
页面标题：{page.get('title', '')}
页面 URL：{page.get('url', '')}
页面正文：
{content_text}
"""
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.15,
            max_tokens=520,
        )
        content = resp.choices[0].message.content or ""
        obj = _parse_json_object(content)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    return _extractive_summary(content_text)


def execute(
    user_input: str = "",
    source_url: str = "",
    content_text: str = "",
    open_in_browser: bool = True,
    max_chars: int = 12000,
    **kwargs,
) -> Dict[str, Any]:
    """Fetch content first, then summarize with the LLM."""
    if not user_input and not source_url and not content_text:
        return {"status": "error", "message": "missing_input"}

    analysis = _build_analysis(user_input or source_url, source_url=source_url)
    url = source_url or analysis.get("source_url", "") or _extract_url(user_input)

    site = str(analysis.get("site", "") or "").strip().lower() or _detect_site_from_url(url)
    if site in ["commerce"]:
        site = _detect_site_from_url(url)
    profile = _resolve_site_profile(site)

    global _ACTIVE_SITE_PROFILE
    _ACTIVE_SITE_PROFILE = profile

    page: Dict[str, Any] = {"title": "", "url": url, "text": "", "headings": []}
    cookie_payload = kwargs.get("cookies")
    cookie_file = str(kwargs.get("cookie_file", "") or "").strip()
    if cookie_file:
        file_cookies = _load_cookies_from_file(cookie_file)
        if file_cookies:
            cookie_payload = file_cookies
    deep_crawl = bool(kwargs.get("deep_crawl", True))
    deep_crawl_max_pages = int(kwargs.get("deep_crawl_max_pages", _cfg_int("deep_crawl_max_pages", DEFAULT_DEEP_CRAWL_MAX_PAGES)))
    deep_crawl_page_max_chars = int(kwargs.get("deep_crawl_page_max_chars", _cfg_int("deep_crawl_page_max_chars", DEFAULT_DEEP_CRAWL_PAGE_MAX_CHARS)))
    if content_text:
        page["text"] = content_text[:max_chars]
    elif url:
        if open_in_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        try:
            page = _fetch_page_content(url, max_chars=max_chars, cookies=cookie_payload)
        except Exception as exc:
            page = {"title": "", "url": url, "text": "", "headings": [], "error": str(exc)}
    else:
        page = {"title": "", "url": "", "text": "", "headings": [], "error": "no_url_resolved"}

    # 正文噪声过滤（规则 + LLM）
    cleaned_text = _llm_denoise_text(user_input or source_url, page.get("text", ""), max_chars=max_chars)

    page_state = _detect_page_state(page.get("url", url), page.get("title", ""), page.get("text", ""))

    # 增量学习站点噪声策略并回写配置，支持长期自我优化。
    learned = _learn_site_profile_from_page(site, page.get("text", ""))
    if learned:
        _merge_and_save_site_profile(site, learned)

    structured_payload = _run_structured_extractor(site, page.get("url", url), page.get("text", ""))
    structured_items: List[Dict[str, Any]] = []
    if isinstance(structured_payload, dict):
        maybe_items = structured_payload.get("items", [])
        if isinstance(maybe_items, list):
            structured_items = [x for x in maybe_items if isinstance(x, dict)]
        if structured_items:
            page["structured_data"] = structured_payload

    # 兜底结构化提取：独立 skill 异常或无结果时，仍保留基础电商提取能力。
    if not structured_items:
        structured_items = _extract_ecommerce_items(site, page.get("url", url), page.get("text", ""))
        if structured_items:
            page["structured_data"] = {
                "status": "success",
                "site": site,
                "mode": "ecommerce_search",
                "items": structured_items,
                "summary_hint": "优先按商品候选列表总结",
                "fallback": True,
            }

    # 若当前站点没有配置策略，尝试用大模型生成并持久化，后续可自我更新。
    if not profile:
        inferred = _infer_site_profile_with_llm(site, page.get("url", url), page.get("text", ""))
        if inferred:
            _merge_and_save_site_profile(site, inferred)
            _ACTIVE_SITE_PROFILE = inferred
            cleaned_text = _llm_denoise_text(user_input or source_url, page.get("text", ""), max_chars=max_chars)

    if page_state in ["blocked", "login", "deleted", "inaccessible"]:
        page["clean_text"] = cleaned_text
        if page_state == "blocked":
            state_msg = "检测到目标站点存在反爬限制"
            suggestion = "可尝试更换公开页面、提供可访问链接，或配置已登录抓取会话。"
        elif page_state == "login":
            state_msg = "检测到登录页，未进入目标内容"
            suggestion = "请提供可匿名访问链接，或通过 cookies 参数注入已登录会话。"
        elif page_state == "deleted":
            state_msg = "检测到内容已删除或话题不存在"
            suggestion = "可更换原始链接，或提供缓存文本进行离线总结。"
        else:
            state_msg = "检测到内容暂不可访问（可能仅作者可见或违规下线）"
            suggestion = "建议更换可公开访问页面，或提供页面截图/文本供总结。"
        return {
            "status": "success",
            "analysis": analysis,
            "page": page,
            "summary": f"{state_msg}，当前无法稳定提取正文。{suggestion}",
            "key_points": [state_msg, suggestion],
            "takeaway": state_msg,
            "notes": f"{page_state}_detected",
        }

    # 话题/列表页深读：自动打开候选帖子，聚合后再总结。
    related_pages: List[Dict[str, Any]] = []
    if deep_crawl and site in ["zhihu", "xiaohongshu"]:
        candidate_links = _select_deep_crawl_links(site, page.get("url", url), page.get("links", []))
        if candidate_links:
            related_pages = _crawl_related_pages(
                site=site,
                urls=candidate_links,
                cookies=cookie_payload,
                max_pages=max(1, min(8, deep_crawl_max_pages)),
                max_chars_per_page=max(1200, min(5000, deep_crawl_page_max_chars)),
            )
            if related_pages:
                page["related_pages"] = [
                    {
                        "url": x.get("url", ""),
                        "title": x.get("title", ""),
                        "state": x.get("state", ""),
                    }
                    for x in related_pages
                ]
                deep_seed = _build_deep_crawl_seed(site, related_pages)
                if deep_seed:
                    cleaned_text = _compress_clean_text(cleaned_text + "。" + deep_seed, max_chars=_cfg_int("clean_text_max_chars", DEFAULT_CLEAN_TEXT_MAX_CHARS))

    if structured_items:
        mode = ""
        if isinstance(page.get("structured_data"), dict):
            mode = str(page["structured_data"].get("mode", "")).strip()

        if mode == "ecommerce_search":
            top = structured_items[:5]
            formatted = [f"{idx+1}. {it.get('title','')}" + (f" | ￥{it.get('price')}" if it.get("price") else "") for idx, it in enumerate(top)]
            page["clean_text"] = cleaned_text
            return {
                "status": "success",
                "analysis": analysis,
                "page": page,
                "summary": "页面识别为电商搜索结果，已提取可读的商品候选列表。",
                "key_points": formatted,
                "takeaway": formatted[0] if formatted else "已完成结构化提取",
                "notes": "structured_search_items",
            }

        # 社区/通用页：把结构化条目前置给总结器，提高可读性与稳定性。
        snippets: List[str] = []
        for it in structured_items[:8]:
            title = str(it.get("title", "")).strip()
            snippet = str(it.get("snippet", "")).strip()
            engagement = str(it.get("engagement", "")).strip()
            line = title or snippet
            if line:
                if engagement:
                    line = f"{line}（{engagement}）"
                snippets.append(line)
        if snippets:
            enhanced_seed = "。".join(snippets)
            cleaned_text = _compress_clean_text(enhanced_seed + "。" + cleaned_text, max_chars=_cfg_int("clean_text_max_chars", DEFAULT_CLEAN_TEXT_MAX_CHARS))

    page["clean_text"] = cleaned_text

    summary_payload = _summarize_with_llm(user_input, analysis, page, cleaned_text)
    if not isinstance(summary_payload, dict):
        summary_payload = {"summary": str(summary_payload), "key_points": []}

    rewrite_payload = _rewrite_summary(user_input, analysis, summary_payload)
    summary = rewrite_payload.get("summary", "") if isinstance(rewrite_payload, dict) else ""

    key_points = []
    if isinstance(rewrite_payload, dict):
        maybe_points = rewrite_payload.get("key_points", [])
        if isinstance(maybe_points, list):
            key_points = [str(item) for item in maybe_points if str(item).strip()]

    return {
        "status": "success",
        "analysis": analysis,
        "page": page,
        "summary": summary,
        "key_points": key_points,
        "takeaway": rewrite_payload.get("takeaway", "") if isinstance(rewrite_payload, dict) else "",
        "notes": rewrite_payload.get("notes", summary_payload.get("notes", "llm_summary" if summary else "")),
    }
