"""Trace writer for repository inspections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_repo_inspection_trace(trace_path: Path, payload: dict[str, Any]) -> None:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
