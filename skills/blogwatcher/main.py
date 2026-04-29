from __future__ import annotations
from pathlib import Path
from typing import Any, Dict

DESCRIPTION = "博客动态追踪检索适配"
ICON = "📰"

def execute(topic: str = "", user_input: str = "", **kwargs) -> Dict[str, Any]:
    q = (topic or user_input or "AI engineering blog").strip()
    try:
      import sys
      root = Path(__file__).resolve().parents[2]
      if str(root) not in sys.path:
        sys.path.insert(0, str(root))
      from orchestrators.web_search_pipeline import run_web_search_v2

      obj = run_web_search_v2(mode='structured', query=f'{q} blog updates', max_results=8)
      if isinstance(obj, dict):
        obj.setdefault('notes', 'blogwatcher_adapter')
        return obj
      return {"status": "success", "data": obj, "notes": "blogwatcher_adapter"}
    except Exception as exc:
      return {"status": "error", "code": "upstream_error", "message": str(exc)}
