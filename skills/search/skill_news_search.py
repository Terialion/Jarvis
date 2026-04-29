"""
news-search — 新闻搜索 Skill v1.0.0

专门面向新闻/热点搜索场景。
优先获取最新资讯，关注时效性排序。

用法:
    from skills.search.skill_news_search import execute
    result = execute("AI 最新进展")
"""

from __future__ import annotations

import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from .skill_multi_search_free import (
    _DEFAULT_TIMEOUT,
    _DEFAULT_TOP_K,
    _http_get,
    _parse_engine_results,
)

# ---------------------------------------------------------------------------
# 新闻搜索 URL 模板（含时效性参数）
# ---------------------------------------------------------------------------

_NEWS_TEMPLATES: Dict[str, str] = {
    # Google News
    "google_news": "https://news.google.com/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    # Bing News（带 freshness 参数）
    "bing_news": "https://www.bing.com/news/search?q={query}&qft=interval%3d%227%22",
    # 百度新闻
    "baidu_news": "https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&ie=utf-8&word={query}",
    # 搜狗新闻/微信搜索
    "sogou_news": "https://www.sogou.com/web?query={query}&ie=utf8&s_from=result_up&tsn=1",
    # DuckDuckGo News
    "ddg_news": "https://duckduckgo.com/html/?q={query}&df=m",  # df=m = past month
}

# 通用新闻 fallback
_FALLBACK_NEWS_ENGINES = ["bing", "duckduckgo", "baidu"]


def _select_news_engines(query: str) -> List[str]:
    """根据查询语言选择新闻搜索引擎。"""
    is_cn = bool(re.search(r"[\u4e00-\u9fff]", query))

    if is_cn:
        return ["baidu_news", "bing_news", "sogou_news"]
    else:
        return ["google_news", "bing_news", "ddg_news"]


def execute_news_search(
    query: str,
    engines: Optional[List[str]] = None,
    top_k: int = _DEFAULT_TOP_K,
    timeout_s: float = _DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    执行新闻导向的多引擎搜索。

    Args:
        query: 搜索关键词
        engines: 指定引擎列表，None 则自动选择
        top_k: 最大返回结果数
        timeout_s: 请求超时

    Returns:
        与 execute_search 相同格式的字典
    """
    start_time = time.monotonic()
    query_encoded = urllib.parse.quote_plus(query)

    if engines is None:
        engines = _select_news_engines(query)

    # 追加 fallback
    full_list = list(engines)
    for e in _FALLBACK_NEWS_ENGINES:
        if e not in full_list:
            full_list.append(e)

    # 合并所有模板
    all_templates = {
        **_NEWS_TEMPLATES,
        "duckduckgo": "https://duckduckgo.com/html/?q={query}",
        "bing": "https://www.bing.com/search?q={query}",
        "baidu": "https://www.baidu.com/s?wd={query}",
    }

    all_results: List[Dict[str, str]] = []
    all_errors: List[Dict[str, str]] = []
    opened_urls: List[str] = []
    engine_used = ""

    for engine_name in full_list:
        template = all_templates.get(engine_name)
        if not template:
            continue

        url = template.format(query=query_encoded)
        opened_urls.append(url)

        raw = _http_get(url, timeout=timeout_s)

        if raw is None:
            all_errors.append({"engine": engine_name, "error": "请求失败"})
            continue

        # 新闻引擎可能使用不同 HTML 结构
        if engine_name == "baidu_news":
            parsed = _parse_baidu_news(raw)
        elif engine_name == "bing_news":
            parsed = _parse_bing_news(raw)
        elif engine_name == "google_news":
            parsed = _parse_google_news(raw)
        else:
            parsed = _parse_engine_results(raw, engine_name)

        if not parsed:
            all_errors.append({"engine": engine_name, "error": "解析结果为空"})
            continue

        if not engine_used:
            engine_used = engine_name

        all_results.extend(parsed)
        if len(all_results) >= top_k:
            break

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    final_results = []
    for i, item in enumerate(all_results[:top_k]):
        final_results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", ""),
            "rank": i + 1,
        })

    return {
        "ok": len(final_results) > 0,
        "query": query,
        "engine_used": engine_used,
        "all_engines_tried": full_list,
        "results": final_results,
        "opened_urls": opened_urls,
        "errors": all_errors,
        "total_results": len(final_results),
        "latency_ms": elapsed_ms,
    }


def _parse_baidu_news(html_text: str) -> List[Dict[str, str]]:
    """解析百度新闻搜索结果。"""
    results = []
    # 百度新闻结果格式: <div class="result-op c-container ..." data-tuiguang="...">
    # 包含 <h3 class="c-title"><a href="...">标题</a></h3>
    # 和 <div class="c-summary">摘要</div>
    pattern = re.compile(
        r'<h3[^>]*class="[^"]*c-title[^"]*"[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    summary_pattern = re.compile(
        r'<div[^>]*class="[^"]*c-summary[^"]*"[^>]*>(.*?)</div>',
        re.DOTALL,
    )

    seen_urls = set()
    for match in pattern.finditer(html_text):
        url = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()

        if not title or url in seen_urls:
            continue
        seen_urls.add(url)

        # 查找对应的摘要（在标题之后的文本中）
        snippet = ""
        pos = match.end()
        for sm in summary_pattern.finditer(html_text[pos:pos + 1000]):
            snippet = re.sub(r"<[^>]+>", "", sm.group(1)).strip()
            break

        results.append({
            "title": title[:200],
            "url": url[:500],
            "snippet": snippet[:300],
        })

    return results


def _parse_bing_news(html_text: str) -> List[Dict[str, str]]:
    """解析 Bing News 搜索结果。"""
    results = []
    # Bing News 结果: <li class="b_algo"> 或 <div class="newsitem">
    # 包含 <a class="title" href="...">标题</a>
    pattern = re.compile(
        r'<a[^>]+class="[^"]*title[^"]*"[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    # 摘要
    snippet_pattern = re.compile(
        r'<div[^>]*class="[^"]*(?:snippet|caption|abstract)[^"]*"[^>]*>(.*?)</div>',
        re.DOTALL,
    )

    seen_urls = set()
    for match in pattern.finditer(html_text):
        url = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()

        if not title or url in seen_urls:
            continue
        seen_urls.add(url)

        snippet = ""
        pos = match.end()
        for sm in snippet_pattern.finditer(html_text[pos:pos + 800]):
            snippet = re.sub(r"<[^>]+>", "", sm.group(1)).strip()
            break

        results.append({
            "title": title[:200],
            "url": url[:500],
            "snippet": snippet[:300],
        })

    # 如果上面的模式没匹配到，尝试通用模式
    if not results:
        pattern2 = re.compile(
            r'<a[^>]+href="(https?://[^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{10,}?)\s*(?:</[^>]+>\s*)*</a>',
            re.DOTALL,
        )
        for match in pattern2.finditer(html_text):
            url = match.group(1)
            title = match.group(2).strip()
            if not title or len(title) < 8 or url in seen_urls:
                continue
            # 排除导航链接
            skip = ("bing.com", "microsoft.com", "live.com")
            if any(d in url for d in skip):
                continue
            seen_urls.add(url)
            results.append({"title": title[:200], "url": url[:500], "snippet": ""})

    return results


def _parse_google_news(html_text: str) -> List[Dict[str, str]]:
    """解析 Google News 搜索结果。"""
    results = []
    # Google News 使用 JavaScript 渲染，HTML 中可能有 SSR 内容
    # 尝试从 SSR 的 JSON-LD 或 microdata 中提取
    # <article> 标签中包含结果
    article_pattern = re.compile(r"<article[^>]*>(.*?)</article>", re.DOTALL)

    for article_match in article_pattern.finditer(html_text):
        article_html = article_match.group(1)

        # 提取链接和标题
        link_m = re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', article_html, re.DOTALL)
        if not link_m:
            continue

        url = link_m.group(1)
        title = re.sub(r"<[^>]+>", "", link_m.group(2)).strip()

        if not title or len(title) < 5:
            continue

        # 提取来源和时间
        source_m = re.search(r'data-source="[^^"]*"', article_html)

        snippet = ""
        for p in re.finditer(r"<p[^>]*>(.*?)</p>", article_html, re.DOTALL):
            s = re.sub(r"<[^>]+>", "", p.group(1)).strip()
            if s and len(s) > 20:
                snippet = s
                break

        results.append({
            "title": title[:200],
            "url": url[:500],
            "snippet": snippet[:300],
        })

    # 如果 article 没匹配到，尝试从 JSON 数据中提取
    if not results:
        json_match = re.search(r'\["([^"]+)",\s*\["', html_text)
        if json_match:
            # Google News 可能嵌入 JSON 数据
            pass  # JS 渲染页面，HTML 中通常没有结构化数据

    return results


def _format_news_results(data: Dict[str, Any]) -> str:
    """格式化新闻搜索结果。"""
    if not data["ok"]:
        lines = [
            f"📰 新闻搜索失败: \"{data['query']}\"",
            "",
            "尝试过的引擎: " + ", ".join(data.get("all_engines_tried", [])),
        ]
        for err in data.get("errors", []):
            lines.append(f"  ⚠ {err['engine']}: {err['error']}")
        return "\n".join(lines)

    lines = [
        f"📰 新闻搜索: \"{data['query']}\"",
        f"引擎: {data['engine_used']} (耗时 {data['latency_ms']}ms)",
        "─" * 50,
    ]

    for item in data["results"]:
        lines.append(f"{item['rank']}. {item['title']}")
        lines.append(f"   {item['url']}")
        if item["snippet"]:
            snippet = item["snippet"][:250] + ("..." if len(item["snippet"]) > 250 else "")
            lines.append(f"   {snippet}")
        lines.append("")

    lines.append("─" * 50)
    lines.append(f"共 {data['total_results']} 条结果")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Skill 入口
# ---------------------------------------------------------------------------

def execute(query: str, **kwargs) -> str:
    """
    新闻搜索 Skill 入口函数。

    Args:
        query: 搜索关键词
        **kwargs:
            engines: List[str] — 指定引擎
            top_k: int — 最大结果数
            timeout: float — 超时秒数

    Returns:
        格式化的搜索结果文本
    """
    engines = kwargs.get("engines")
    top_k = kwargs.get("top_k", _DEFAULT_TOP_K)
    timeout = kwargs.get("timeout", _DEFAULT_TIMEOUT)

    data = execute_news_search(
        query=query,
        engines=engines,
        top_k=top_k,
        timeout_s=timeout,
    )
    return _format_news_results(data)


if __name__ == "__main__":
    import sys
    import logging

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "AI 最新进展"
    print(f"\n{'='*60}")
    print(f"news-search v1.0.0 — 新闻搜索")
    print(f"{'='*60}\n")
    print(execute(q))
