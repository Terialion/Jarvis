"""Summarize skill adapter.

Provides a standard execute() entrypoint for marketplace summarize skill docs.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from openai import OpenAI

DESCRIPTION = "通用文本总结（模型可用优先，否则抽取式回退）"
ICON = "📝"


def _extractive(text: str) -> Dict[str, Any]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    chunks = [x.strip() for x in re.split(r"[。！？!?；;]", cleaned) if x.strip()]
    points: List[str] = []
    for c in chunks:
        if len(c) >= 12:
            points.append(c)
        if len(points) >= 5:
            break
    return {
        "status": "success",
        "summary": cleaned[:400],
        "key_points": points,
        "notes": "extractive_fallback",
    }


def execute(text: str = "", user_input: str = "", max_sentences: int = 4, **kwargs) -> Dict[str, Any]:
    src = (text or user_input or "").strip()
    if not src:
        return {"status": "error", "code": "missing_input", "message": "missing_text"}

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return _extractive(src)

    prompt = f"""请总结下面文本，输出 JSON：
{{
  \"summary\": \"{max_sentences}句以内总结\",
  \"key_points\": [\"要点1\",\"要点2\",\"要点3\"]
}}

文本：
{src[:8000]}
"""
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=500,
        )
        raw = resp.choices[0].message.content or ""
        import json

        obj = json.loads(raw[raw.find("{"): raw.rfind("}") + 1]) if "{" in raw and "}" in raw else {}
        if isinstance(obj, dict) and obj.get("summary"):
            return {
                "status": "success",
                "summary": str(obj.get("summary", "")).strip(),
                "key_points": [str(x).strip() for x in obj.get("key_points", []) if str(x).strip()][:6],
                "notes": "llm_summary",
            }
    except Exception:
        pass

    return _extractive(src)
