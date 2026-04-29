"""Weather skill adapter.

Provides executable entrypoint for marketplace weather skill docs.
"""
from __future__ import annotations

import requests
from typing import Any, Dict

DESCRIPTION = "查询实时天气与简要预报（wttr.in）"
ICON = "🌤"


def execute(city: str = "", user_input: str = "", unit: str = "m", **kwargs) -> Dict[str, Any]:
    q = (city or user_input or "Beijing").strip() or "Beijing"
    q = q.replace(" ", "+")
    unit_flag = "m" if unit not in ["u", "m"] else unit

    url = f"https://wttr.in/{q}?format=%l:+%c+%t+%h+%w&{unit_flag}"
    try:
        resp = requests.get(url, timeout=12)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text:
            return {"status": "error", "code": "upstream_error", "message": "weather_empty_response"}
        return {
            "status": "success",
            "query": q,
            "unit": unit_flag,
            "summary": text,
            "notes": "wttr_in",
        }
    except Exception as exc:
        return {
            "status": "error",
            "code": "upstream_error",
            "message": str(exc),
            "query": q,
        }
