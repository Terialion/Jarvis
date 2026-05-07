from __future__ import annotations

import re
from html import unescape

from ..agent.types import redact_secret_text


ALLOWED_CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "text/markdown",
    "application/xhtml+xml",
}


def extract_readable_text(content: str, *, content_type: str, max_chars: int, extract_mode: str = "markdown") -> tuple[str, str]:
    raw = str(content or "")
    ctype = str(content_type or "text/plain").split(";", 1)[0].strip().lower()
    if ctype not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"unsupported_content_type:{ctype or 'unknown'}")
    text = raw
    title = ""
    if ctype in {"text/html", "application/xhtml+xml"}:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
        title = _clean_text(title_match.group(1)) if title_match else ""
        text = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
    text = _clean_text(text)
    text = redact_secret_text(text)[: max(1, int(max_chars or 12000))]
    return title, text


def _clean_text(value: str) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text

