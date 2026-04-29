from __future__ import annotations
import os
from typing import Any, Dict

DESCRIPTION = "腾讯文档能力适配入口"
ICON = "📄"

REQUIRED = ['TENCENT_DOCS_APP_ID', 'TENCENT_DOCS_APP_SECRET']

def execute(action: str = "", user_input: str = "", **kwargs) -> Dict[str, Any]:
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
      return {"status": "error", "code": "missing_config", "message": "missing_env", "required_env": missing}
    return {"status": "error", "code": "not_implemented", "message": "upstream_sdk_not_wired", "action": action or user_input}
