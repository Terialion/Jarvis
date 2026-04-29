"""Common result helpers for Core modules."""

from __future__ import annotations

from time import perf_counter
from typing import Any


def ok_result(data: Any, started_at: float | None = None) -> dict:
    duration_ms = _duration_ms(started_at)
    return {"ok": True, "data": data, "error": None, "meta": {"duration_ms": duration_ms}}


def error_result(
    code: str,
    message: str,
    details: dict | None = None,
    started_at: float | None = None,
) -> dict:
    duration_ms = _duration_ms(started_at)
    return {
        "ok": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details},
        "meta": {"duration_ms": duration_ms},
    }


def _duration_ms(started_at: float | None) -> int | None:
    if started_at is None:
        return None
    return max(0, int((perf_counter() - started_at) * 1000))

