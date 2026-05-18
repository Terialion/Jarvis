"""Headless browser transport using Playwright — renders SPA pages and extracts content.

Inspired by OpenClaw's browser tool:
- Accessibility tree snapshots with semantic element references
- JS-rendered page content extraction
- Screenshot capture (optional)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrowserSnapshot:
    url: str
    title: str
    text: str  # extracted readable text
    elements: list[dict[str, Any]] = field(default_factory=list)  # interactive elements with ref IDs
    screenshot_b64: str | None = None


class PlaywrightBrowser:
    """Headless browser via Playwright. Renders SPA pages and extracts content."""

    def __init__(self, *, headless: bool = True, timeout_ms: int = 15000) -> None:
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._browser: Any = None
        self._context: Any = None

    def _ensure_browser(self) -> Any:
        if self._browser is not None:
            return self._browser

        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        # Use system Chrome if available
        launch_args: dict[str, Any] = {
            "headless": self._headless,
            "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        }
        try:
            from shutil import which
            chrome = which("chrome") or which("google-chrome") or which("chromium")
            if not chrome:
                import os
                candidates = [
                    "C:/Program Files/Google/Chrome/Application/chrome.exe",
                    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
                ]
                for c in candidates:
                    if os.path.exists(c):
                        chrome = c
                        break
            if chrome:
                launch_args["executable_path"] = chrome
        except Exception:
            pass

        self._browser = self._pw.chromium.launch(**launch_args)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )
        return self._browser

    def navigate(self, url: str) -> BrowserSnapshot:
        """Navigate to URL, wait for render, and extract content."""
        self._ensure_browser()
        page = self._context.new_page()
        try:
            page.goto(url, timeout=self._timeout_ms, wait_until="domcontentloaded")
            # Wait a bit for JS to render
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            # Extra wait for SPAs
            page.wait_for_timeout(2000)

            title = page.title()
            elements = self._snapshot_elements(page)
            text = self._extract_text(page)
            page.close()
            return BrowserSnapshot(url=url, title=title, text=text, elements=elements)
        except Exception:
            try:
                page.close()
            except Exception:
                pass
            raise

    def screenshot(self, url: str) -> BrowserSnapshot:
        """Navigate and capture a screenshot (base64 PNG)."""
        import base64

        self._ensure_browser()
        page = self._context.new_page()
        try:
            page.goto(url, timeout=self._timeout_ms, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(2000)

            title = page.title()
            elements = self._snapshot_elements(page)
            text = self._extract_text(page)
            screenshot_bytes = page.screenshot(full_page=False)
            b64 = base64.b64encode(screenshot_bytes).decode("ascii")
            page.close()
            return BrowserSnapshot(url=url, title=title, text=text, elements=elements, screenshot_b64=b64)
        except Exception:
            try:
                page.close()
            except Exception:
                pass
            raise

    def _snapshot_elements(self, page: Any) -> list[dict[str, Any]]:
        """Extract interactive elements with reference IDs (OpenClaw-style)."""
        js_code = """
        () => {
            const interactive = 'a,button,input,select,textarea,[role="button"],[role="link"],[role="textbox"],[role="combobox"],[onclick]';
            const elMap = {a: 'link', button: 'button', input: 'input', select: 'select', textarea: 'textarea'};
            const results = [];
            const seen = new Set();
            document.querySelectorAll(interactive).forEach((el, i) => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;
                const text = (el.textContent || el.value || el.placeholder || el.ariaLabel || '').trim().slice(0, 200);
                if (!text && el.tagName !== 'INPUT') return;
                const key = text + '|' + el.tagName;
                if (seen.has(key)) return;
                seen.add(key);
                results.push({
                    ref: i + 1,
                    tag: el.tagName.toLowerCase(),
                    role: elMap[el.tagName.toLowerCase()] || 'element',
                    text: text,
                    href: el.href || '',
                    visible: true,
                });
            });
            return results.slice(0, 100);
        }
        """
        try:
            return page.evaluate(js_code) or []
        except Exception:
            return []

    def _extract_text(self, page: Any) -> str:
        """Extract readable text from the rendered page body."""
        js_code = """
        () => {
            // Remove scripts, styles, nav, footer
            const clone = document.body ? document.body.cloneNode(true) : document.documentElement.cloneNode(true);
            const remove = clone.querySelectorAll('script,style,nav,footer,header,iframe,noscript,svg');
            remove.forEach(el => el.remove());
            return (clone.textContent || '').replace(/\\s{3,}/g, '\\n').trim().slice(0, 30000);
        }
        """
        try:
            text = page.evaluate(js_code) or ""
            return text
        except Exception:
            return ""

    def close(self) -> None:
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if hasattr(self, "_pw") and self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._browser = None
        self._context = None


# Singleton for reuse across tool calls
_browser_instance: PlaywrightBrowser | None = None


def get_browser(*, headless: bool = True) -> PlaywrightBrowser:
    global _browser_instance
    if _browser_instance is None:
        _browser_instance = PlaywrightBrowser(headless=headless)
    return _browser_instance


def run_web_browse(url: str, *, action: str = "snapshot", headless: bool = True) -> dict[str, Any]:
    """Browse a URL using headless browser.

    Args:
        url: Page URL to browse
        action: "snapshot" (text + elements) or "screenshot" (includes base64 PNG)
        headless: Run browser headless (default True)
    """
    browser = get_browser(headless=headless)
    try:
        if action == "screenshot":
            snap = browser.screenshot(url)
        else:
            snap = browser.navigate(url)
        return {
            "ok": True,
            "url": snap.url,
            "title": snap.title,
            "text": snap.text[:12000],
            "elements": snap.elements[:50],
            "screenshot_b64": snap.screenshot_b64[:200] + "..." if snap.screenshot_b64 else None,
        }
    except Exception as exc:
        # Fallback: try regular HTTP fetch
        from .fetch import run_web_fetch
        from .schema import FetchRequest
        try:
            result = run_web_fetch(FetchRequest(url=url), timeout_s=15)
            if result.ok and result.documents:
                doc = result.documents[0]
                return {
                    "ok": True,
                    "url": url,
                    "title": doc.get("title", ""),
                    "text": doc.get("text", "")[:8000],
                    "elements": [],
                    "note": "fetched via HTTP (browser render failed: " + str(exc)[:100] + ")",
                }
        except Exception:
            pass
        return {"ok": False, "url": url, "error": str(exc)[:300]}
