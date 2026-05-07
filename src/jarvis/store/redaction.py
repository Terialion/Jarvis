"""Centralized redaction before persistence."""

from __future__ import annotations

from typing import Any

from ..agent.types import _redact_value, contains_secret_text, redact_secret_text


def redact_for_persistence(value: Any) -> Any:
    """Apply the shared Jarvis redaction policy to arbitrary values."""

    return _redact_value(value)


def redact_text_for_persistence(text: str) -> str:
    return str(redact_secret_text(str(text or "")))


def has_secret_like_content(value: Any) -> bool:
    if isinstance(value, str):
        return contains_secret_text(value)
    if isinstance(value, dict):
        return any(has_secret_like_content(v) for v in value.values())
    if isinstance(value, list):
        return any(has_secret_like_content(v) for v in value)
    return False
