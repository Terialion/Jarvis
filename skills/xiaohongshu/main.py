from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

DESCRIPTION = "小红书内容抓取与总结适配"
ICON = "📕"

def execute(source_url: str = "", user_input: str = "", **kwargs) -> Dict[str, Any]:
    url = (source_url or "").strip()
    if not url and user_input:
      import re
      m = re.search(r"https?://[^\s'\"]+", user_input)
      url = m.group(0) if m else ""
    if not url:
      return {"status": "error", "code": "missing_input", "message": "missing_source_url"}
    try:
      import sys
      root = Path(__file__).resolve().parents[2]
      if str(root) not in sys.path:
        sys.path.insert(0, str(root))
      from toolkit import Toolkit
      tk = Toolkit()
      raw = tk.execute_skill('web-content-summary', source_url=url, user_input=f'总结一下 {url}', open_in_browser=False)
      obj = json.loads(raw) if isinstance(raw, str) else raw
      return obj if isinstance(obj, dict) else {"status": "success", "data": obj}
    except Exception as exc:
      return {"status": "error", "code": "upstream_error", "message": str(exc)}
