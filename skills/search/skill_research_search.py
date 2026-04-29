"""
research-search — 学术/研究搜索 Skill v1.0.0

专门面向研究场景的搜索引擎选择策略。
优先使用学术相关来源：Google Scholar, arXiv, GitHub, 官方文档。

用法:
    from skills.search.skill_research_search import execute
    result = execute("transformer attention mechanism")
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List, Optional

from .skill_multi_search_free import (
    _DEFAULT_TIMEOUT,
    _DEFAULT_TOP_K,
    _http_get,
    _parse_engine_results,
)

# ---------------------------------------------------------------------------
# 学术搜索 URL 模板
# ---------------------------------------------------------------------------

_RESEARCH_TEMPLATES: Dict[str, str] = {
    # Google Scholar（学术搜索首选）
    "google_scholar": "https://scholar.google.com/scholar?q={query}",
    # arXiv（预印本论文）
    "arxiv": "https://arxiv.org/search/?query={query}&searchtype=all",
    # GitHub（代码研究）
    "github": "https://github.com/search?q={query}&type=repositories",
    # MDN / 官方文档关键词搜索
    "mdn": "https://developer.mozilla.org/zh-CN/search?q={query}",
    # Semantic Scholar（开放学术搜索）
    "semantic_scholar": "https://www.semanticscholar.org/search?q={query}",
}

# 通用搜索引擎（作为 fallback）
_FALLBACK_ENGINES = ["duckduckgo", "bing", "google"]


def _is_paper_query(query: str) -> bool:
    """判断是否是论文/学术查询。"""
    academic_keywords = [
        "paper", "论文", "研究", "research", "survey", "综述",
        "arxiv", "conference", "期刊", "journal", "publication",
        "citation", "引用", "methodology", "实验", "empirical",
        "benchmark", "dataset", "evaluation",
    ]
    q = query.lower()
    return any(kw in q for kw in academic_keywords)


def _is_code_research(query: str) -> bool:
    """判断是否是代码/工程研究查询。"""
    code_keywords = [
        "github", "gitlab", "source code", "源码", "implementation",
        "实现", "library", "框架", "framework", "api documentation",
        "repo", "open source", "开源",
    ]
    q = query.lower()
    return any(kw in q for kw in code_keywords)


def _select_research_engines(query: str) -> List[str]:
    """根据查询特征选择最适合的学术搜索引擎组合。"""

    is_paper = _is_paper_query(query)
    is_code = _is_code_research(query)

    selected = []

    if is_paper:
        # 论文查询：学术引擎优先
        selected = ["google_scholar", "semantic_scholar", "arxiv"]
    elif is_code:
        # 代码研究：GitHub + 通用搜索
        selected = ["github", "duckduckgo", "bing"]
    else:
        # 一般研究：学术 + 通用混合
        selected = ["google_scholar", "duckduckgo", "bing"]

    return selected


def execute_research_search(
    query: str,
    engines: Optional[List[str]] = None,
    top_k: int = _DEFAULT_TOP_K,
    timeout_s: float = _DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    执行研究导向的多引擎搜索。

    Args:
        query: 搜索关键词
        engines: 指定引擎列表，None 则自动选择
        top_k: 最大返回结果数
        timeout_s: 请求超时

    Returns:
        与 execute_search 相同格式的字典
    """
    import time

    start_time = time.monotonic()
    query_encoded = urllib.parse.quote_plus(query)

    if engines is None:
        engines = _select_research_engines(query)

    # 将 fallback 引擎追加到列表末尾
    full_engine_list = list(engines)
    for e in _FALLBACK_ENGINES:
        if e not in full_engine_list:
            full_engine_list.append(e)

    all_results: List[Dict[str, str]] = []
    all_errors: List[Dict[str, str]] = []
    opened_urls: List[str] = []
    engine_used = ""

    # 合并学术模板和通用模板
    all_templates = {**_RESEARCH_TEMPLATES, **{
        "duckduckgo": "https://duckduckgo.com/html/?q={query}",
        "bing": "https://www.bing.com/search?q={query}",
        "google": "https://www.google.com/search?q={query}",
    }}

    for engine_name in full_engine_list:
        template = all_templates.get(engine_name)
        if not template:
            continue

        url = template.format(query=query_encoded)
        opened_urls.append(url)

        raw = _http_get(url, timeout=timeout_s)

        if raw is None:
            all_errors.append({"engine": engine_name, "error": "请求失败"})
            continue

        # 学术搜索引擎的 HTML 结构各不相同，统一用通用解析
        # 先尝试用引擎专用解析（如果有）
        parsed = _parse_engine_results(raw, engine_name)

        if not parsed:
            # 回退：尝试从 arXiv 的 JSON API 获取
            if engine_name == "arxiv":
                parsed = _parse_arxiv_results(query, timeout_s)
            else:
                # 尝试简单的正则提取
                parsed = _regex_fallback_parse(raw)

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
        "all_engines_tried": full_engine_list,
        "results": final_results,
        "opened_urls": opened_urls,
        "errors": all_errors,
        "total_results": len(final_results),
        "latency_ms": elapsed_ms,
    }


def _parse_arxiv_results(query: str, timeout_s: float) -> List[Dict[str, str]]:
    """通过 arXiv API 获取论文搜索结果。"""
    import json
    import urllib.request

    url = f"http://export.arxiv.org/api/query?search_query=all:{urllib.parse.quote_plus(query)}&start=0&max_results=5"
    raw = _http_get(url, timeout=timeout_s)
    if not raw:
        return []

    results = []
    # 简单解析 Atom XML
    # 提取 <entry> 块
    entries = re.findall(r"<entry>(.*?)</entry>", raw, re.DOTALL)
    for entry in entries[:5]:
        title_m = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        link_m = re.search(r"<id>(.*?)</id>", entry)
        summary_m = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)

        if title_m and link_m:
            results.append({
                "title": re.sub(r"\s+", " ", title_m.group(1)).strip(),
                "url": link_m.group(1).strip(),
                "snippet": re.sub(r"\s+", " ", summary_m.group(1)).strip()[:200] if summary_m else "",
            })

    return results


def _regex_fallback_parse(html_text: str) -> List[Dict[str, str]]:
    """正则表达式备用解析（当专用解析器无法提取结果时）。"""
    results = []

    # 通用模式：提取带 href 的 <a> 标签及其上下文
    # 匹配常见搜索引擎结果格式
    pattern = re.compile(
        r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>'
        r'(?:.*?(?:<p[^>]*>|<div[^>]*>|<span[^>]*>)(.*?)(?:</p>|</div>|</span>))?',
        re.DOTALL,
    )

    seen_urls = set()
    for match in pattern.finditer(html_text):
        url = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        snippet = re.sub(r"<[^>]+>", "", match.group(3) or "").strip()

        # 过滤低质量结果
        if not title or len(title) < 5:
            continue
        if url in seen_urls:
            continue
        # 排除搜索引擎自身的导航链接
        skip_domains = ("google.com", "bing.com", "baidu.com", "sogou.com", "duckduckgo.com")
        if any(d in url for d in skip_domains):
            continue

        seen_urls.add(url)
        results.append({
            "title": title[:200],
            "url": url[:500],
            "snippet": snippet[:300],
        })

    return results


def _format_research_results(data: Dict[str, Any]) -> str:
    """格式化研究搜索结果。"""
    if not data["ok"]:
        lines = [
            f"📚 研究搜索失败: \"{data['query']}\"",
            "",
            "尝试过的引擎: " + ", ".join(data.get("all_engines_tried", [])),
        ]
        for err in data.get("errors", []):
            lines.append(f"  ⚠ {err['engine']}: {err['error']}")
        return "\n".join(lines)

    lines = [
        f"📚 研究搜索: \"{data['query']}\"",
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
    研究搜索 Skill 入口函数。

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

    data = execute_research_search(
        query=query,
        engines=engines,
        top_k=top_k,
        timeout_s=timeout,
    )
    return _format_research_results(data)


if __name__ == "__main__":
    import sys
    import logging

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "transformer attention mechanism"
    print(f"\n{'='*60}")
    print(f"research-search v1.0.0 — 学术研究搜索")
    print(f"{'='*60}\n")
    print(execute(q))
