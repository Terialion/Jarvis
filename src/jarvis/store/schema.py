"""Shared schema version and time helpers."""

from __future__ import annotations

from datetime import datetime, timezone


SCHEMA_VERSION = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
