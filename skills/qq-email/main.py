from __future__ import annotations
import os
from typing import Any, Dict

DESCRIPTION = "QQ 邮箱收发适配入口"
ICON = "📧"

REQUIRED = ['QQ_EMAIL_ACCOUNT', 'QQ_EMAIL_AUTH_CODE']

def execute(action: str = "inbox", user_input: str = "", **kwargs) -> Dict[str, Any]:
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
      return {"status": "error", "code": "missing_config", "message": "missing_env", "required_env": missing}
    return {"status": "error", "code": "not_implemented", "message": "imap_smtp_runner_not_wired", "action": action}
