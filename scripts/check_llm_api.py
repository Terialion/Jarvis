from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.llm.config import load_llm_config


def _chat_completions_url(base_url: str) -> str:
    root = (base_url or "").rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def _post_json(url: str, payload: dict, api_key: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return {
            "status": int(getattr(resp, "status", 200) or 200),
            "body": json.loads(raw) if raw else {},
        }


def main() -> int:
    cfg = load_llm_config()
    report = {
        "provider": cfg.provider,
        "model": cfg.model,
        "base_url": cfg.base_url,
        "api_key_present": bool(cfg.api_key),
        "api_key_source": cfg.api_key_source,
        "api_key_masked": cfg.masked_api_key(),
        "base_url_source": cfg.base_url_source,
        "model_source": cfg.model_source,
        "deprecated_env_used": list(cfg.deprecated_env_used),
        "ok": False,
    }
    print(json.dumps({"config": report}, ensure_ascii=False, indent=2))

    if not cfg.api_key:
        print("RESULT: LLM_API_MISSING_KEY")
        return 2
    if not cfg.base_url:
        print("RESULT: LLM_API_MISSING_BASE_URL")
        return 2
    if not cfg.model:
        print("RESULT: LLM_API_MISSING_MODEL")
        return 2

    url = _chat_completions_url(cfg.base_url)
    payload = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "temperature": 0,
    }

    try:
        result = _post_json(url, payload, cfg.api_key)
        body = result["body"]
        text = (
            body.get("choices", [{}])[0].get("message", {}).get("content", "")
            if isinstance(body, dict)
            else ""
        )
        print(
            json.dumps(
                {
                    "ok": bool(str(text).strip()),
                    "http_status": result["status"],
                    "assistant_text_preview": str(text)[:200],
                    "response_keys": sorted(list(body.keys())) if isinstance(body, dict) else [],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if str(text).strip():
            print("RESULT: LLM_API_OK")
            return 0
        print("RESULT: LLM_API_EMPTY_RESPONSE")
        return 3
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        print(
            json.dumps(
                {
                    "ok": False,
                    "http_status": int(exc.code),
                    "error_preview": str(body)[:1500],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print("RESULT: LLM_API_HTTP_ERROR")
        return 4
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print("RESULT: LLM_API_FAILED")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())

