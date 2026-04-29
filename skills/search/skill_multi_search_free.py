"""
multi-search-free — 免费多引擎搜索 Skill v1.0.0

支持 DuckDuckGo / Bing / Baidu / Sogou / Google / SearXNG
零外部依赖，仅使用 Python 标准库。

用法:
    from skills.search.skill_multi_search_free import execute_search, execute
    result = execute_search("Python asyncio 教程")
    text = execute("Docker compose", engines=["duckduckgo", "bing"])
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 浏览器 User-Agent（模拟正常浏览器）
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 搜索引擎 URL 模板
ENGINE_TEMPLATES: Dict[str, str] = {
    "duckduckgo": "https://duckduckgo.com/html/?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "baidu": "https://www.baidu.com/s?wd={query}",
    "sogou": "https://www.sogou.com/web?query={query}",
    "google": "https://www.google.com/search?q={query}",
    "searxng": "http://localhost:8080/search?q={query}&format=json",
}

# GitHub 搜索模板
_GITHUB_SEARCH = "https://github.com/search?q={query}&type=repositories"

# 请求超时（秒）
_DEFAULT_TIMEOUT = 15.0

# 最大结果数
_DEFAULT_TOP_K = 8


# ---------------------------------------------------------------------------
# HTML 解析器
# ---------------------------------------------------------------------------

class _SearchResultParser(HTMLParser):
    """
    通用搜索引擎结果解析器。
    根据配置的 CSS 类名/标签模式提取标题、链接、摘要。
    """

    def __init__(self, engine: str):
        super().__init__()
        self.engine = engine
        self.results: List[Dict[str, str]] = []
        self._current: Optional[Dict[str, str]] = None
        self._in_result = False
        self._in_title = False
        self._in_snippet = False
        self._in_link = False
        self._text_buf = ""
        self._href = ""
        self._depth = 0  # 标签嵌套深度

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        tag_lower = tag.lower()

        if self.engine == "duckduckgo":
            # DuckDuckGo HTML: <div class="result">
            if cls == "result" and tag_lower == "div":
                self._in_result = True
                self._current = {"title": "", "url": "", "snippet": ""}
            elif self._in_result and tag_lower == "a" and attrs_dict.get("href", "").startswith("/"):
                self._in_link = True
                self._href = attrs_dict.get("href", "")
            elif self._in_result and tag_lower == "a" and "class" in attrs_dict and "result__a" in cls:
                self._in_title = True
                self._text_buf = ""
                self._href = attrs_dict.get("href", "")

        elif self.engine == "bing":
            # Bing: <li class="b_algo"><h2><a href="...">
            if cls == "b_algo" and tag_lower == "li":
                self._in_result = True
                self._current = {"title": "", "url": "", "snippet": ""}
            elif self._in_result and tag_lower == "a":
                self._in_title = True
                self._text_buf = ""
                self._href = attrs_dict.get("href", "")
            elif self._in_result and cls == "b_caption" and tag_lower == "div":
                self._in_snippet = True
                self._text_buf = ""

        elif self.engine == "baidu":
            # Baidu: <div class="result c-container ">
            if "result" in cls and ("c-container" in cls or "container" in cls) and tag_lower == "div":
                self._in_result = True
                self._current = {"title": "", "url": "", "snippet": ""}
            elif self._in_result and tag_lower == "a" and "href" in attrs_dict:
                # baidu 的标题链接
                self._in_title = True
                self._text_buf = ""
                self._href = attrs_dict.get("href", "")
            elif self._in_result and (cls == "c-abstract" or cls == "c-span-last"):
                self._in_snippet = True
                self._text_buf = ""

        elif self.engine == "sogou":
            # Sogou: <div class="vrwrap"> 或 <div class="rb">
            if cls in ("vrwrap", "rb") and tag_lower == "div":
                self._in_result = True
                self._current = {"title": "", "url": "", "snippet": ""}
            elif self._in_result and tag_lower == "a" and attrs_dict.get("href", ""):
                if "title" not in cls or not self._current.get("url"):
                    self._in_title = True
                    self._text_buf = ""
                    self._href = attrs_dict.get("href", "")
            elif self._in_result and ("ft" in cls or "str_info" in cls or "str_text_info" in cls):
                self._in_snippet = True
                self._text_buf = ""

        elif self.engine == "google":
            # Google: <div class="g"> 包含结果
            if cls == "g" and tag_lower == "div":
                self._in_result = True
                self._current = {"title": "", "url": "", "snippet": ""}
            elif self._in_result and tag_lower == "a" and attrs_dict.get("href", "").startswith("http"):
                if not self._current.get("url"):
                    self._in_title = True
                    self._text_buf = ""
                    self._href = attrs_dict.get("href", "")
            elif self._in_result and (cls in ("VwiC3b", "st", "IsZvec") or "data-sncf" in attrs_dict):
                self._in_snippet = True
                self._text_buf = ""

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()

        if tag_lower == "a":
            if self._in_title:
                self._in_title = False
                if self._current and self._text_buf.strip():
                    self._current["title"] = self._text_buf.strip()
                    self._current["url"] = self._href
            self._in_link = False
            self._href = ""

        elif tag_lower in ("span", "p", "div"):
            if self._in_snippet:
                self._in_snippet = False
                if self._current:
                    snippet = self._text_buf.strip()
                    if snippet:
                        self._current["snippet"] = snippet

        # 结果块结束检测
        if self._in_result and self._current:
            title = self._current.get("title", "").strip()
            url = self._current.get("url", "").strip()
            if title and url and url.startswith("http"):
                self.results.append({
                    "title": html.unescape(title),
                    "url": url,
                    "snippet": html.unescape(self._current.get("snippet", "")),
                })
                self._current = None
                self._in_result = False

    def handle_data(self, data: str) -> None:
        if self._in_title or self._in_snippet:
            self._text_buf += data


# ---------------------------------------------------------------------------
# SearXNG JSON 解析
# ---------------------------------------------------------------------------

def _parse_searxng_json(raw_json: str) -> List[Dict[str, str]]:
    """解析 SearXNG JSON API 返回的结果。"""
    results = []
    try:
        data = json.loads(raw_json)
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
            })
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("SearXNG JSON 解析失败: %s", e)
    return results


# ---------------------------------------------------------------------------
# HTTP 请求
# ---------------------------------------------------------------------------

def _http_get(url: str, timeout: float = _DEFAULT_TIMEOUT) -> Optional[str]:
    """执行 HTTP GET 请求，返回响应文本。失败返回 None。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            raw = resp.read()
            return raw.decode(charset, errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as e:
        logger.debug("HTTP 请求失败 [%s]: %s", url[:80], e)
        return None


# ---------------------------------------------------------------------------
# 引擎选择
# ---------------------------------------------------------------------------

def _is_chinese(text: str) -> bool:
    """判断文本是否包含中文字符。"""
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _is_technical_query(text: str) -> bool:
    """判断是否是技术相关查询（含关键词）。"""
    tech_keywords = [
        "github", "gitlab", "stackoverflow", "npm", "pip", "docker", "kubernetes",
        "api", "sdk", "framework", "library", "bug", "issue", "error", "exception",
        "compile", "build", "deploy", "module", "package", "repository",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in tech_keywords)


def _select_engines(query: str, engines: Optional[List[str]] = None) -> List[str]:
    """
    根据查询特征自动选择搜索引擎列表。
    如果用户指定了 engines，直接使用。
    """
    if engines:
        return engines

    is_cn = _is_chinese(query)
    is_tech = _is_technical_query(query)

    if is_tech:
        # 技术查询：英文引擎优先 + GitHub
        selected = ["duckduckgo", "bing", "google"]
        if not is_cn:
            # 英文技术查询不需要百度/搜狗
            return selected
    elif is_cn:
        # 中文查询：百度/搜狗优先
        selected = ["baidu", "sogou", "bing"]
    else:
        # 默认英文查询
        selected = ["duckduckgo", "bing", "google"]

    return selected


# ---------------------------------------------------------------------------
# URL 处理
# ---------------------------------------------------------------------------

def _clean_url(raw_url: str, engine: str) -> str:
    """清理 URL，去除搜索引擎的重定向前缀。"""
    if not raw_url:
        return ""
    # DuckDuckGo HTML 使用 /l/?uddg=ENCODED_URL 重定向
    if engine == "duckduckgo" and raw_url.startswith("/l/"):
        match = re.search(r"uddg=([^&]+)", raw_url)
        if match:
            return urllib.parse.unquote(match.group(1))
    # Baidu 使用 bdurl 重定向
    if engine == "baidu" and "baidu.com/link" in raw_url:
        # 尝试保留原始 URL（后续可在浏览器中跟随重定向）
        return raw_url
    return raw_url


# ---------------------------------------------------------------------------
# 解析引擎结果
# ---------------------------------------------------------------------------

def _parse_engine_results(raw_html: str, engine: str) -> List[Dict[str, str]]:
    """根据引擎类型解析搜索结果。"""
    if engine == "searxng":
        return _parse_searxng_json(raw_html)

    parser = _SearchResultParser(engine)
    try:
        parser.feed(raw_html)
    except Exception as e:
        logger.warning("HTML 解析异常 [%s]: %s", engine, e)

    # 清理 URL
    for item in parser.results:
        item["url"] = _clean_url(item["url"], engine)

    return parser.results


# ---------------------------------------------------------------------------
# 核心搜索函数
# ---------------------------------------------------------------------------

def execute_search(
    query: str,
    engines: Optional[List[str]] = None,
    top_k: int = _DEFAULT_TOP_K,
    timeout_s: float = _DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """
    执行多引擎搜索。

    Args:
        query: 搜索关键词
        engines: 指定引擎列表，None 则自动选择
        top_k: 最大返回结果数
        timeout_s: 单引擎请求超时（秒）

    Returns:
        {
            "ok": True/False,
            "query": str,
            "engine_used": str,           # 首个成功返回结果的引擎
            "all_engines_tried": List[str],
            "results": [
                {"title": str, "url": str, "snippet": str, "rank": int}
            ],
            "opened_urls": List[str],     # 实际访问的 URL
            "errors": [{"engine": str, "error": str}],
            "total_results": int,
            "latency_ms": int,
        }
    """
    start_time = time.monotonic()
    query_encoded = urllib.parse.quote_plus(query)
    selected_engines = _select_engines(query, engines)

    all_results: List[Dict[str, str]] = []
    all_errors: List[Dict[str, str]] = []
    opened_urls: List[str] = []
    engine_used = ""

    for engine_name in selected_engines:
        template = ENGINE_TEMPLATES.get(engine_name)
        if not template:
            logger.warning("未知引擎: %s", engine_name)
            continue

        url = template.format(query=query_encoded)
        opened_urls.append(url)
        logger.debug("尝试引擎 %s: %s", engine_name, url)

        raw = _http_get(url, timeout=timeout_s)

        if raw is None:
            all_errors.append({"engine": engine_name, "error": "请求失败（网络错误或超时）"})
            continue

        parsed = _parse_engine_results(raw, engine_name)

        if not parsed:
            all_errors.append({"engine": engine_name, "error": "解析结果为空（可能被反爬）"})
            continue

        # 首个成功的引擎
        if not engine_used:
            engine_used = engine_name

        all_results.extend(parsed)
        logger.debug("引擎 %s 返回 %d 条结果", engine_name, len(parsed))

        # 如果已经收集到足够多的结果，停止尝试
        if len(all_results) >= top_k:
            break

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # 截取 top_k 条，添加 rank
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
        "all_engines_tried": selected_engines,
        "results": final_results,
        "opened_urls": opened_urls,
        "errors": all_errors,
        "total_results": len(final_results),
        "latency_ms": elapsed_ms,
    }


# ---------------------------------------------------------------------------
# 格式化输出
# ---------------------------------------------------------------------------

def _format_results(data: Dict[str, Any]) -> str:
    """将搜索结果格式化为人类可读文本。"""
    if not data["ok"]:
        lines = [
            f"🔍 搜索失败: \"{data['query']}\"",
            "",
            "尝试过的引擎: " + ", ".join(data.get("all_engines_tried", [])),
            "",
            "错误信息:",
        ]
        for err in data.get("errors", []):
            lines.append(f"  ⚠ {err['engine']}: {err['error']}")
        return "\n".join(lines)

    lines = [
        f"🔍 搜索: \"{data['query']}\"",
        f"引擎: {data['engine_used']} (耗时 {data['latency_ms']}ms)",
        "─" * 50,
    ]

    for item in data["results"]:
        lines.append(f"{item['rank']}. {item['title']}")
        lines.append(f"   {item['url']}")
        if item["snippet"]:
            # 截断过长摘要
            snippet = item["snippet"][:200] + ("..." if len(item["snippet"]) > 200 else "")
            lines.append(f"   {snippet}")
        lines.append("")

    lines.append("─" * 50)
    tried = data.get("all_engines_tried", [])
    used = data.get("engine_used", "")
    unused = [e for e in tried if e != used]
    if unused:
        lines.append(f"共 {data['total_results']} 条结果 | 备用引擎: {', '.join(unused)}(未使用)")
    else:
        lines.append(f"共 {data['total_results']} 条结果")

    # 错误信息（如果有）
    if data.get("errors"):
        for err in data["errors"]:
            lines.append(f"  ⚠ {err['engine']}: {err['error']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Skill 入口
# ---------------------------------------------------------------------------

def execute(query: str, **kwargs) -> str:
    """
    Skill 入口函数。返回人类可读的搜索结果字符串。

    Args:
        query: 搜索关键词
        **kwargs:
            engines: List[str] — 指定引擎列表
            top_k: int — 最大结果数（默认 8）
            timeout: float — 超时秒数（默认 15）

    Returns:
        格式化的搜索结果文本
    """
    engines = kwargs.get("engines")
    top_k = kwargs.get("top_k", _DEFAULT_TOP_K)
    timeout = kwargs.get("timeout", _DEFAULT_TIMEOUT)

    data = execute_search(
        query=query,
        engines=engines,
        top_k=top_k,
        timeout_s=timeout,
    )
    return _format_results(data)


# ---------------------------------------------------------------------------
# CLI 测试入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
    else:
        q = "Python asyncio 教程"

    print(f"\n{'='*60}")
    print(f"multi-search-free v1.0.0 — 免费多引擎搜索")
    print(f"{'='*60}\n")

    text = execute(q)
    print(text)
    print(f"\n{'='*60}\n")
