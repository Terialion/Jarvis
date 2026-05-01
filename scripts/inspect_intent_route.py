#!/usr/bin/env python
"""Inspect hybrid intent routing examples."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.routing.examples import ROUTING_EXAMPLES_ZH
from src.jarvis.core.routing.hybrid_router import route_user_input
from src.jarvis.core.routing.safety_gate import apply_route_safety


def main() -> int:
    rows: list[dict[str, object]] = []
    failed = 0
    for sample in ROUTING_EXAMPLES_ZH:
        text = sample["input"]
        expected_intent = sample["intent"]
        expected_mode = sample["mode"]
        routed = route_user_input(text, source_surface="cli", input_kind="unknown_task")
        safe = apply_route_safety(routed, text, mode="safe")
        ok = safe.intent == expected_intent and safe.response_mode == expected_mode
        if not ok:
            failed += 1
        rows.append(
            {
                "input": text,
                "expected_intent": expected_intent,
                "actual_intent": safe.intent,
                "expected_mode": expected_mode,
                "actual_mode": safe.response_mode,
                "source": safe.source,
                "llm_called": (safe.routing_trace or {}).get("llm_fallback_called"),
                "pass": ok,
                "notes": "" if ok else "intent/mode mismatch",
            }
        )
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
