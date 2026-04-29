from __future__ import annotations

import re


SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key"),
    re.compile(r"(?i)password"),
    re.compile(r"(?i)private[_-]?key"),
    re.compile(r"(?i)token"),
    re.compile(r"(?i)secret"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{4,}\b"),
]


def is_secret_like(text: str) -> bool:
    value = text or ""
    return any(p.search(value) for p in SECRET_PATTERNS)


def sanitize_memory_value(value: str) -> tuple[bool, str]:
    if is_secret_like(value):
        return False, "[REDACTED_SECRET]"
    return True, value
