from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_latest_benchmark_report(path: str | Path = "benchmarks/reports/latest.json") -> dict[str, Any]:
    report_path = Path(path)
    if not report_path.exists():
        return {"ok": False, "error": {"code": "BENCHMARK_REPORT_MISSING", "message": str(report_path)}}
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload.setdefault("report_source", str(report_path))
    return payload
