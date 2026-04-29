"""
内置工具 — 联网搜索

封装现有的 web_search.py，同时接入新配置系统。
API Key 不再依赖环境变量，而是从 SecretVault 读取。
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

# 确保项目根目录在 sys.path
_root = str(Path(__file__).resolve().parents[3])  # jarvis/tools/builtin → root
if _root not in sys.path:
    sys.path.insert(0, _root)

from jarvis.tools.base import BaseTool, ToolParam, ToolResult, tool
from jarvis.config.manager import get_config
from orchestrators.web_search_pipeline import WebSearchPipeline, load_pipeline_settings, run_web_search_pipeline_sync


def _format_search_bundle(bundle, *, fetch_content: bool, use_ai_summary: bool) -> str:
    keyword = str(bundle.get("keyword", "") or "")
    results = list(bundle.get("results", []) or [])
    docs = list(bundle.get("docs", []) or [])
    if not fetch_content:
        for row in results:
            row.pop("content", None)
        for doc in docs:
            doc.pop("content", None)

    observability = bundle.get("search_observability", {}) if isinstance(bundle, dict) else {}
    elapsed = int(observability.get("elapsed_ms", 0) or 0)
    source = results[0].get("source", "unknown") if results else "unknown"
    lines = [f"[搜索完成] 关键词: {keyword} | 耗时: {elapsed}ms | 来源: {source}", ""]
    if use_ai_summary and bundle.get("answer"):
        lines.extend(["=" * 60, "[AI 综合回答]", str(bundle.get("answer", "")), "=" * 60, ""])
    lines.append("[详细搜索结果]")
    for idx, row in enumerate(results, start=1):
        title = str(row.get("title", "无标题"))
        body = str(row.get("body", ""))
        href = str(row.get("href", ""))
        content = str(row.get("content", ""))
        lines.append(f"\n{idx}. {title}")
        if body:
            snippet = body[:120] + "..." if len(body) > 120 else body
            lines.append(f"   摘要: {snippet}")
        if fetch_content and content:
            preview = content[:200] + "..." if len(content) > 200 else content
            lines.append(f"   正文: {preview}")
        lines.append(f"   URL: {href}")
    return "\n".join(lines)


class WebSearchTool(BaseTool):
    """搜索互联网，返回相关网页摘要"""

    name             = "web_search"
    description      = "联网搜索，获取网页摘要。支持 Tavily / scrape.do / Bing 等多后端自动切换。"
    category         = "network"
    version          = "2.1.0"
    tags             = ["search", "web", "internet"]
    requires_network = True
    requires_config  = ["search.tavily_api_key"]

    params = [
        ToolParam("query",       str, "搜索词或问题",            required=True),
        ToolParam("max_results", int, "最大返回结果数",           required=False, default=10),
        ToolParam("fetch_content", bool, "是否抓取网页正文",      required=False, default=True),
        ToolParam("use_ai_summary", bool, "是否使用AI摘要综合",   required=False, default=True),
    ]

    def execute(
        self,
        query: str,
        max_results: int = 10,
        fetch_content: bool = True,
        use_ai_summary: bool = True,
    ) -> ToolResult:
        # ── 1. 从配置系统注入 API Key ────────────────────
        cfg = get_config()
        self._inject_api_keys(cfg)

        # ── 2. 调用新管线 ────────────────────────────────
        try:
            bundle = run_web_search_pipeline_sync(query, top_k=max_results)
            result_text = _format_search_bundle(bundle, fetch_content=fetch_content, use_ai_summary=use_ai_summary)
            return ToolResult.ok(
                data=result_text,
                message=f"搜索完成: {query}",
                query=query,
            )
        except Exception as e:
            return ToolResult.fail(f"搜索失败: {e}", error=e)

    @staticmethod
    def _inject_api_keys(cfg):
        """把保险箱里的密钥注入到环境变量（仅当前进程）"""
        key_map = {
            "search.tavily_api_key":  "TAVILY_API_KEY",
            "search.scrape_do_api_key": "SCRAPE_DO_API_KEY",
            "search.bing_api_key":    "BING_SEARCH_API_KEY",
            "search.serper_api_key":  "SERPER_API_KEY",
        }
        for cfg_key, env_key in key_map.items():
            value = cfg.get_secret(cfg_key)
            if value and not os.environ.get(env_key):
                os.environ[env_key] = value


class FetchPageTool(BaseTool):
    """抓取指定 URL 的网页正文"""

    name             = "fetch_page"
    description      = "访问指定 URL，提取网页正文内容。"
    category         = "network"
    version          = "1.0.0"
    tags             = ["web", "scrape", "fetch"]
    requires_network = True

    params = [
        ToolParam("url",        str, "要访问的网页 URL",    required=True),
        ToolParam("max_length", int, "正文最大字符数",       required=False, default=3000),
    ]

    def execute(self, url: str, max_length: int = 3000) -> ToolResult:
        cfg = get_config()
        WebSearchTool._inject_api_keys(cfg)

        try:
            pipeline = WebSearchPipeline(settings=load_pipeline_settings())

            async def _run_extract():
                try:
                    return await pipeline.extract_urls([url], query=url)
                finally:
                    await pipeline.close()

            rows = asyncio.run(_run_extract())
            if rows and rows[0].get("ok"):
                content = str(rows[0].get("content", "") or "")
                return ToolResult.ok(
                    data=content[:max_length],
                    url=url,
                    total_length=len(content),
                )
            return ToolResult.fail(f"无法获取页面内容: {url}")
        except Exception as e:
            return ToolResult.fail(f"抓取失败: {e}", error=e)
