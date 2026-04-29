"""
bug-verification-search — Bug/Issue 验证搜索 Skill v1.0.0

专门面向 Bug 复现和 Issue 验证场景。
优先搜索 GitHub Issues, Stack Overflow, 官方 Bug Tracker。

用法:
    from skills.search.skill_bug_verification_search import execute
    result = execute("Flink CDC NullPointerException checkpoint")
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
# Bug 验证搜索 URL 模板
# ---------------------------------------------------------------------------

_BUG_TEMPLATES: Dict[str, str] = {
    # GitHub Issues 搜索（限定 Issues 类型）
    "github_issues": "https://github.com/search?q={query}&type=issues",
    # Stack Overflow
    "stackoverflow": "https://stackoverflow.com/search?q={query}",
    # Google Buganizer / 一般搜索引擎限定 site
    "google_bug": "https://www.google.com/search?q={query}+site:github.com/issues+OR+site:stackoverflow.com",
    # Bing 限定技术站点
    "bing_bug": "https://www.bing.com/search?q={query}+site:github.com+OR+site:stackoverflow.com+OR+site:issues.apache.org",
    # DuckDuckGo 技术搜索
    "ddg_bug": "https://duckduckgo.com/html/?q={query}+github+issues",
}

# Bug 相关关键词
_BUG_KEYWORDS = [
    "bug", "issue", "error", "exception", "crash", "fail", "segfault",
    "nullpointer", "null reference", "assertion", "panic", "abort",
    "leak", "deadlock", "race condition", "timeout",
    "缺陷", "漏洞", "崩溃", "报错", "异常", "失败", "Bug",
]


def _is_bug_query(query: str) -> bool:
    """判断查询是否是 Bug/Issue 相关。"""
    q = query.lower()
    return any(kw in q for kw in _BUG_KEYWORDS)


def _extract_stack_trace_keywords(query: str) -> List[str]:
    """从查询中提取可能的堆栈跟踪关键词（类名、方法名等）。"""
    # 匹配 Java/C# 风格的全限定名
    java_style = re.findall(r"[A-Z][a-zA-Z0-9]*(?:\.[A-Z][a-zA-Z0-9]*)+", query)
    # 匹配 Python 风格的模块路径
    python_style = re.findall(r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+", query)
    return list(set(java_style + python_style))


def _build_bug_search_query(query: str) -> str:
    """
    增强 Bug 搜索查询：添加有用的限定词。
    例如: "NullPointerException" → "NullPointerException error github issue fix"
    """
    # 如果查询已经包含足够的 bug 关键词，不做增强
    if _is_bug_query(query):
        return query

    # 添加常用限定词
    enhanced_parts = [query]

    # 检测异常类名模式
    if re.search(r"[A-Z][a-zA-Z]*Error|[A-Z][a-zA-Z]*Exception", query):
        enhanced_parts.append("exception")
    elif re.search(r"error|fail|crash", query.lower()):
        pass  # 已经包含错误关键词
    else:
        enhanced_parts.append("issue")

    return " ".join(enhanced_parts)


def _select_bug_engines(query: str) -> List[str]:
    """选择最适合 Bug 验证的搜索引擎组合。"""
    # 总是优先技术社区
    return ["github_issues", "stackoverflow", "bing_bug", "ddg_bug"]


def execute_bug_search(
    query: str,
    engines: Optional[List[str]] = None,
    top_k: int = _DEFAULT_TOP_K,
    timeout_s: float = _DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    执行 Bug/Issue 验证导向的多引擎搜索。

    Args:
        query: 搜索关键词
        engines: 指定引擎列表，None 则自动选择
        top_k: 最大返回结果数
        timeout_s: 请求超时

    Returns:
        与 execute_search 相同格式的字典
    """
    start_time = time.monotonic()

    # 增强 Bug 搜索查询
    enhanced_query = _build_bug_search_query(query)

    if engines is None:
        engines = _select_bug_engines(query)

    # Fallback
    full_list = list(engines) + ["duckduckgo", "bing"]

    query_encoded = urllib.parse.quote_plus(enhanced_query)

    # 合并所有模板
    all_templates = {
        **_BUG_TEMPLATES,
        "duckduckgo": "https://duckduckgo.com/html/?q={query}",
        "bing": "https://www.bing.com/search?q={query}",
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

        # Stack Overflow 有独特的 HTML 结构
        if engine_name == "stackoverflow":
            parsed = _parse_stackoverflow(raw)
        else:
            parsed = _parse_engine_results(raw, engine_name)

        if not parsed:
            all_errors.append({"engine": engine_name, "error": "解析结果为空"})
            continue

        if not engine_used:
            engine_used = engine_name

        # 给结果添加来源标记
        for item in parsed:
            if engine_name == "github_issues":
                item["_source"] = "GitHub Issues"
            elif engine_name == "stackoverflow":
                item["_source"] = "Stack Overflow"

        all_results.extend(parsed)
        if len(all_results) >= top_k:
            break

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    final_results = []
    for i, item in enumerate(all_results[:top_k]):
        entry = {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", ""),
            "rank": i + 1,
        }
        if "_source" in item:
            entry["source_type"] = item["_source"]
        final_results.append(entry)

    return {
        "ok": len(final_results) > 0,
        "query": query,
        "enhanced_query": enhanced_query,
        "engine_used": engine_used,
        "all_engines_tried": full_list,
        "results": final_results,
        "opened_urls": opened_urls,
        "errors": all_errors,
        "total_results": len(final_results),
        "latency_ms": elapsed_ms,
    }


def _parse_stackoverflow(html_text: str) -> List[Dict[str, str]]:
    """
    解析 Stack Overflow 搜索结果。
    SO 结果结构: <div class="s-post-summary"> 或 <div class="question-summary">
    """
    results = []
    seen_urls = set()

    # 主要模式: <a class="question-hyperlink" href="/questions/...">
    q_link_pattern = re.compile(
        r'<a[^>]+class="[^"]*question-hyperlink[^"]*"[^>]+href="(/questions/\d+/[^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL,
    )
    # 摘要模式
    excerpt_pattern = re.compile(
        r'<div[^>]*class="[^"]*s-post-summary--content-excerpt[^"]*"[^>]*>(.*?)</div>',
        re.DOTALL,
    )
    # 标签/元信息
    meta_pattern = re.compile(
        r'<span[^>]*class="[^"]*relativetime[^"]*"[^>]*>(.*?)</span>',
        re.DOTALL,
    )

    for match in q_link_pattern.finditer(html_text):
        path = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()

        if not title or path in seen_urls:
            continue
        seen_urls.add(path)

        url = f"https://stackoverflow.com{path}"

        # 查找摘要
        snippet = ""
        pos = match.end()
        for sm in excerpt_pattern.finditer(html_text[pos:pos + 1000]):
            snippet = re.sub(r"<[^>]+>", "", sm.group(1)).strip()
            break

        # 查找时间
        meta = ""
        for mm in meta_pattern.finditer(html_text[pos:pos + 800]):
            meta = mm.group(1).strip()
            break

        result = {
            "title": title[:200],
            "url": url,
            "snippet": snippet[:300],
        }
        if meta:
            result["snippet"] = f"{snippet[:250]} | {meta}"

        results.append(result)

    # 如果新样式未匹配到，尝试旧样式
    if not results:
        old_pattern = re.compile(
            r'<div[^>]*class="[^"]*question-summary[^"]*"[^>]*>.*?'
            r'<a[^>]+href="(/questions/\d+/[^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        for match in old_pattern.finditer(html_text):
            path = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if not title or path in seen_urls:
                continue
            seen_urls.add(path)
            results.append({
                "title": title[:200],
                "url": f"https://stackoverflow.com{path}",
                "snippet": "",
            })

    return results


def _format_bug_results(data: Dict[str, Any]) -> str:
    """格式化 Bug 验证搜索结果。"""
    if not data["ok"]:
        lines = [
            f"🐛 Bug 搜索失败: \"{data['query']}\"",
            "",
            "尝试过的引擎: " + ", ".join(data.get("all_engines_tried", [])),
        ]
        for err in data.get("errors", []):
            lines.append(f"  ⚠ {err['engine']}: {err['error']}")
        return "\n".join(lines)

    lines = [
        f"🐛 Bug 搜索: \"{data['query']}\"",
    ]
    if data.get("enhanced_query") and data["enhanced_query"] != data["query"]:
        lines.append(f"   增强查询: \"{data['enhanced_query']}\"")
    lines.append(f"引擎: {data['engine_used']} (耗时 {data['latency_ms']}ms)")
    lines.append("─" * 50)

    for item in data["results"]:
        source_tag = f" [{item.get('source_type', '')}]" if item.get("source_type") else ""
        lines.append(f"{item['rank']}. {item['title']}{source_tag}")
        lines.append(f"   {item['url']}")
        if item["snippet"]:
            snippet = item["snippet"][:300] + ("..." if len(item["snippet"]) > 300 else "")
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
    Bug 验证搜索 Skill 入口函数。

    Args:
        query: 搜索关键词（可以是错误信息、异常类名、Bug 描述等）
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

    data = execute_bug_search(
        query=query,
        engines=engines,
        top_k=top_k,
        timeout_s=timeout,
    )
    return _format_bug_results(data)


if __name__ == "__main__":
    import sys
    import logging

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Flink CDC NullPointerException checkpoint"
    print(f"\n{'='*60}")
    print(f"bug-verification-search v1.0.0 — Bug/Issue 验证搜索")
    print(f"{'='*60}\n")
    print(execute(q))
