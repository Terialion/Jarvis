from __future__ import annotations

from typing import Any


def make_jsonrpc_response(*, request_id: str | int | None, ok: bool, data: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    if ok:
        return {"jsonrpc": "2.0", "id": request_id, "result": data or {}}
    err = error or {"code": -32000, "message": "Unknown error"}
    return {"jsonrpc": "2.0", "id": request_id, "error": err}

