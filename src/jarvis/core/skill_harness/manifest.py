from __future__ import annotations

from typing import Any


def validate_skill_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    required = ["skill_id", "skill_name", "source"]
    missing = [k for k in required if k not in manifest]
    if missing:
        return {"ok": False, "error": {"code": "SKILL_MANIFEST_INVALID", "message": f"missing {missing}"}}
    return {"ok": True, "data": {"valid": True}}
