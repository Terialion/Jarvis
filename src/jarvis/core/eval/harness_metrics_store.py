from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HarnessMetricsStore:
    def __init__(self, file_path: str | None = None) -> None:
        self.file_path = Path(file_path or "temp/harness_metrics/events.jsonl").resolve()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def append_event(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = {"ts": _utc_now(), **event}
        with self.file_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return {"ok": True, "data": payload}

    def read_events(self, *, run_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.file_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if run_id and item.get("run_id") != run_id:
                continue
            rows.append(item)
        if limit is not None and limit > 0:
            return rows[-limit:]
        return rows

    def summarize(self, *, run_id: str | None = None) -> dict[str, Any]:
        rows = self.read_events(run_id=run_id)
        by_kind: dict[str, int] = {}
        by_risk: dict[str, int] = {}
        for r in rows:
            kind = str(r.get("kind") or "unknown")
            by_kind[kind] = by_kind.get(kind, 0) + 1
            risk = str(r.get("risk_tier") or "none")
            by_risk[risk] = by_risk.get(risk, 0) + 1
        return {
            "run_id": run_id,
            "total_events": len(rows),
            "kind_distribution": by_kind,
            "risk_distribution": by_risk,
        }

