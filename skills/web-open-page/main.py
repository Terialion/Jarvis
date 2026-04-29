"""Web open page skill.

Open a target URL quickly without running content summarization.
Optionally fetch lightweight metadata (title/final url) for confirmation.
"""
from __future__ import annotations

import os
import re
import webbrowser
from typing import Any, Dict

DESCRIPTION = "只打开网页并返回打开结果"
ICON = "🌐"


def _extract_url(text: str) -> str:
    m = re.search(r"https?://[^\s'\"]+", text or "")
    return m.group(0) if m else ""


def _fetch_meta(url: str, timeout_ms: int = 12000) -> Dict[str, Any]:
    from playwright.sync_api import sync_playwright

    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(timeout_ms)
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(600)
            title = ""
            try:
                title = page.title()
            except Exception:
                title = ""
            return {
                "title": title.strip(),
                "final_url": page.url or url,
            }
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


def execute(
    user_input: str = "",
    source_url: str = "",
    open_in_browser: bool = True,
    fetch_meta: bool = True,
    timeout_ms: int = 12000,
    **kwargs,
) -> Dict[str, Any]:
    url = source_url or _extract_url(user_input)
    if not url:
        return {
            "status": "error",
            "message": "missing_url",
        }

    opened = False
    if open_in_browser:
        try:
            webbrowser.open(url)
            opened = True
        except Exception:
            opened = False

    meta = {}
    if fetch_meta:
        try:
            meta = _fetch_meta(url, timeout_ms=timeout_ms)
        except Exception as exc:
            meta = {"error": str(exc), "final_url": url}

    return {
        "status": "success",
        "url": url,
        "opened": opened,
        "meta": meta,
        "notes": "open_only_skill",
    }
