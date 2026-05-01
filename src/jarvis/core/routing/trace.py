"""Intent route trace persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def append_intent_route_trace(
    *,
    trace_path: Path,
    session_id: str,
    source_surface: str,
    user_input: str,
    route_before_safety: dict[str, Any],
    safety_decision: dict[str, Any],
    route_after_safety: dict[str, Any],
    final_response_mode: str,
    entered_task_flow: bool,
    notes: str = "",
    timestamp: str = "",
) -> None:
    payload = {
        "timestamp": timestamp,
        "session_id": session_id,
        "source_surface": source_surface,
        "user_input": user_input,
        "route_before_safety": route_before_safety,
        "safety_decision": safety_decision,
        "route_after_safety": route_after_safety,
        "final_response_mode": final_response_mode,
        "entered_task_flow": entered_task_flow,
        "notes": notes,
    }
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

